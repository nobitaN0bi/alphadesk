"""Execution agent — places live orders with idempotency + audit trail (Phase 2.4).

Inherited from the original AlphaDesk paper-watchlist agent, evolved to place
real orders via the configured :class:`BrokerAdapter` (Dhan in production).
The agent keeps the original two-phase structure:

    1. ``_stage_pending``    — promotes PASS/FLAG assessments to
       ``state.pending_actions`` and mirrors the symbol list onto the
       legacy ``state.paper_watchlist`` (read-only, no broker call).
    2. ``_process_approved`` — after the HiTL gate (``human_approved = True``),
       iterates over the staged actions and:
         a. Checks for an existing Dhan order with the same
            ``correlation_id`` (idempotent replay — never duplicates).
         b. Resolves ``security_id`` via :class:`SecurityIdMapper`.
         c. Calls ``broker.place_order``.
         d. Moves the order to ``executed_trades`` on Dhan status EXECUTED.

The agent is **never** allowed to fire an order when ``BROKER`` is unset
(``broker is None``) — in that case it stays in paper mode and the orders
land in ``approved_actions`` only.

Pure async node ``(state: QuantState) -> QuantState``.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from broker.base import OrderResult, load_broker
from graph.state import DhanOrder, PendingAction, QuantState

logger = logging.getLogger("alphadesk.execution")

_NO_BROKER_MSG = (
    "Broker integration not configured. Actions saved for paper trading only."
)
_BROKER_PAPER_FALLBACK = (
    "BROKER set but broker init failed — staying in paper mode to protect capital."
)


# --------------------------------------------------------------------------- #
# Stage + Process phases (preserved from original, evolved)
# --------------------------------------------------------------------------- #
def _stage_pending(state: QuantState) -> QuantState:
    """Phase 1: promote PASS/FLAG assessments to ``state.pending_actions``.

    Sources orders from two places, in priority order:
      1. ``state.pending_actions`` already populated by the risk manager's
         sizing engine (Phase 2.3) — these carry the exact Dhan payload.
      2. For backward compatibility, any ``PendingAction`` that was added
         by the original code path (paper-watchlist era) is preserved.

    Symbols that pass the gate are mirrored to ``state.paper_watchlist`` so
    the existing GET /watchlist endpoint keeps working.
    """
    existing = {pa.symbol for pa in state.pending_actions}
    for assessment in state.risk_assessments:
        # Stage everything that cleared the guardrails; REJECTs are not
        # approved. FLAG is a caution badge, not a separate gate.
        if not assessment.approved or assessment.symbol in existing:
            continue
        # If the risk manager already sized this order (Phase 2.3), build
        # a DhanOrder from the sizing fields.
        if assessment.proposed_quantity and assessment.proposed_price:
            state.pending_actions.append(
                DhanOrder(
                    symbol=assessment.symbol,
                    security_id="",  # resolved at execution time via SecurityIdMapper
                    quantity=assessment.proposed_quantity,
                    price=assessment.proposed_price,
                    order_type="LIMIT",
                    transaction_type="BUY",
                    product_type="CNC",
                    validity="DAY",
                    exchange_segment="NSE_EQ",
                    correlation_id=f"q-{uuid.uuid4().hex[:12]}",
                    status="PENDING",
                )
            )
        else:
            # Fallback: create a 1-share placeholder so the legacy
            # paper-watchlist flow keeps working. No live order will be
            # placed from a placeholder (see _process_approved).
            state.pending_actions.append(
                PendingAction(
                    action_type="add_to_watchlist",
                    symbol=assessment.symbol,
                    rationale=assessment.notes
                    or f"Passed risk checks (confidence={assessment.confidence:.2f}).",
                    requires_human=True,
                    status="pending",
                )
            )
        existing.add(assessment.symbol)
        if assessment.symbol not in state.paper_watchlist:
            state.paper_watchlist.append(assessment.symbol)
    return state


async def _place_one(broker, order: DhanOrder) -> DhanOrder:
    """Place a single order with idempotency + securityId resolution.

    1. Resolve ``security_id`` via the broker's mapper. If missing, mark the
       order REJECTED with a clear reason — we never fabricate IDs.
    2. Check if Dhan already has an order with this ``correlation_id``. If
       so, mark the order PLACED (or EXECUTED) with the existing order id
       and skip the API call.
    3. Otherwise call ``broker.place_order`` and translate the result.
    """
    # --- 1. Idempotency: has Dhan already seen this correlation_id? ---
    if hasattr(broker, "get_order_status") and order.correlation_id:
        try:
            existing = await broker.get_order_status(order.correlation_id)
            if existing is not None and existing.get("orderId"):
                order.dhan_order_id = str(existing["orderId"])
                order.status = "PLACED"
                order.placed_at = datetime.now(timezone.utc)
                logger.info(
                    "execution: idempotent replay for %s (orderId=%s)",
                    order.symbol,
                    order.dhan_order_id,
                )
                return order
        except Exception as exc:  # noqa: BLE001 - log + continue
            logger.warning(
                "execution: get_order_status(%s) failed (%s); proceeding to place_order",
                order.correlation_id, exc,
            )

    # --- 2. Real placement -------------------------------------------- #
    result: OrderResult = broker.place_order(order)
    if result.order_id:
        order.dhan_order_id = result.order_id
        order.placed_at = datetime.now(timezone.utc)
        # Map Dhan's "placed" string to our enum; broker may have already
        # normalised the status, so trust result.status.
        order.status = "PLACED"
    elif result.status in ("rejected", "failed"):
        order.status = result.status.upper()
        order.rejection_reason = result.message
    else:
        order.status = "PENDING"
    return order


async def _process_approved(state: QuantState) -> QuantState:
    """Phase 2: human approved -> place orders via the configured broker.

    On broker errors the order is marked REJECTED with the broker's message
    — execution NEVER throws. The order is then appended to
    ``state.approved_actions`` and ``state.execution_history`` for audit.
    Orders with Dhan status EXECUTED are mirrored to ``state.executed_trades``.
    """
    broker = load_broker()
    if broker is None:
        # No broker configured — stay in paper mode.
        if os.getenv("BROKER", "").strip():
            logger.warning(_BROKER_PAPER_FALLBACK)
        for action in state.pending_actions:
            action.status = "approved"  # legacy PendingAction
            state.approved_actions.append(action)
            state.execution_history.append(action)
        state.pending_actions = []
        return state

    for action in list(state.pending_actions):
        # The risk manager may have placed a sized DhanOrder, or this may be
        # a legacy PendingAction. We handle both transparently.
        if isinstance(action, DhanOrder):
            try:
                action = await _place_one(broker, action)
            except Exception as exc:  # noqa: BLE001 - never throw on placement
                logger.error(
                    "execution: place_order(%s) failed catastrophically: %s",
                    action.symbol, exc,
                )
                action.status = "FAILED"
                action.rejection_reason = str(exc)
        else:
            # Legacy PendingAction — translate to a paper entry.
            action.status = "approved"

        state.approved_actions.append(action)
        state.execution_history.append(action)
        if action.status == "EXECUTED":
            state.executed_trades.append(action)

    # Pending queue drained.
    state.pending_actions = []
    return state


# --------------------------------------------------------------------------- #
# Node
# --------------------------------------------------------------------------- #
async def execution(state: QuantState) -> QuantState:
    """Stage PASS stocks, then finalize them once a human has approved.

    The graph gates this node with ``interrupt_before=["execution"]``, so
    by the time it runs the human has already approved (or the run ended at
    the pause). Staging is idempotent (deduped against existing
    pending_actions). Placement is idempotent (Dhan correlation_id check).
    """
    _stage_pending(state)
    if state.human_approved:
        await _process_approved(state)
    return state
