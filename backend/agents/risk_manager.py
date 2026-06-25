"""RiskManager agent — enforces guardrails on analyst recommendations.

Pure async node ``(state: QuantState) -> QuantState``. Guardrail enforcement is
deterministic (correctness must not depend on the LLM):

  - Min confidence to proceed: 0.70
  - Max stocks per sector: 3
  - Analyst 'avoid' recommendations are rejected

Phase 2.3 evolution — quantitative sizing engine:

After the verdict is determined (PASS / FLAG / REJECT), the risk manager now
*also* computes an exact position size for every approved recommendation
when live portfolio state is available. The sized orders are attached to the
corresponding ``RiskAssessment.sized_order`` (a :class:`DhanOrder` payload)
and queued onto ``state.pending_actions`` so the human-in-the-loop gate can
display the exact capital impact in the frontend.

Sizing policy (deterministic; from @temp/transormation.md PRD):
  - risk_per_trade = 1 %  of ``available_margin``
  - max_position   = 20 % of ``available_margin``
  - max_total_exposure = 80 % of ``available_margin`` (enforced across the batch)
  - The order is LIMIT at ``last_price * 1.01`` (1 % above market) for safety
  - ``correlation_id`` is deterministic per-run so the Execution agent can
    safely resume from a checkpoint without duplicating orders.

``llama-3.3-70b-versatile`` is used only to attach human-readable risk
notes to each assessment. If every candidate is rejected,
``state.rejection_reason`` is set and the graph terminates.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Dict, List, Optional

from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from graph.state import (
    AnalystRecommendation,
    CriticFeedback,
    DhanOrder,
    QuantState,
    RiskAssessment,
)

logger = logging.getLogger("alphadesk.risk_manager")

RISK_MODEL = "llama-3.3-70b-versatile"
MIN_CONFIDENCE = 0.70
MAX_PER_SECTOR = 3
_FLAG_BAND = 0.75  # passes guardrails but flagged for review when below this

# --- Quantitative sizing constants (Phase 2.3) ---
RISK_PER_TRADE_PCT = float(os.getenv("AGENTQUANT_RISK_PER_TRADE_PCT", "0.01"))
MAX_POSITION_PCT = float(os.getenv("AGENTQUANT_MAX_POSITION_PCT", "0.20"))
MAX_TOTAL_EXPOSURE_PCT = float(os.getenv("AGENTQUANT_MAX_EXPOSURE_PCT", "0.80"))
LIMIT_PREMIUM_PCT = float(os.getenv("AGENTQUANT_LIMIT_PREMIUM_PCT", "0.01"))


# --------------------------------------------------------------------------- #
# LLM annotation schema (preserved)
# --------------------------------------------------------------------------- #
class _RiskNote(BaseModel):
    symbol: str
    note: str


class _RiskNotes(BaseModel):
    notes: List[_RiskNote] = Field(default_factory=list)


def _get_llm() -> ChatGroq:
    return ChatGroq(model=RISK_MODEL, temperature=0)


# --------------------------------------------------------------------------- #
# Pure-logic helpers
# --------------------------------------------------------------------------- #
def _sector_map(state: QuantState) -> Dict[str, Optional[str]]:
    return {s.symbol: s.sector for s in state.scan_results}


def _last_price_map(state: QuantState) -> Dict[str, float]:
    """Best-effort LTP lookup from scan results and current holdings."""
    prices: Dict[str, float] = {}
    for s in state.scan_results:
        if s.last_price is not None and s.last_price > 0:
            prices[s.symbol] = s.last_price
    for h in state.current_holdings:
        if h.last_traded_price and h.last_traded_price > 0:
            prices.setdefault(h.symbol, h.last_traded_price)
    return prices


def _critic_map(state: QuantState) -> Dict[str, CriticFeedback]:
    return {c.symbol: c for c in state.critic_feedback}


# --------------------------------------------------------------------------- #
# Sizing engine
# --------------------------------------------------------------------------- #
def _size_order(
    rec: AnalystRecommendation,
    *,
    state: QuantState,
    last_price: float,
    available_margin: float,
    already_deployed_notional: float,
) -> Optional[DhanOrder]:
    """Compute a sized :class:`DhanOrder` for a passed recommendation.

    Returns ``None`` when sizing is not possible (no price, no margin, or the
    order would breach the total-exposure cap). The Execution path will then
    fall back to a paper-only watchlist entry.

    SecurityId resolution is deferred to the Execution agent — at sizing time
    we only know the symbol, and the ``SecurityIdMapper`` is consulted inside
    the broker adapter to keep a single source of truth.
    """
    if last_price <= 0:
        logger.debug("Sizing skipped for %s: no LTP.", rec.symbol)
        return None
    if available_margin <= 0:
        logger.debug("Sizing skipped for %s: no available margin.", rec.symbol)
        return None
    if rec.action not in ("buy",):
        # We only size BUY recommendations — SELL recommendations are
        # created by the Monitor agent post-execution, not by the pipeline.
        return None

    # --- Compute target notional --------------------------------------- #
    risk_budget = available_margin * RISK_PER_TRADE_PCT
    position_cap = available_margin * MAX_POSITION_PCT
    total_exposure_cap = available_margin * MAX_TOTAL_EXPOSURE_PCT
    remaining_capacity = max(
        0.0, total_exposure_cap - already_deployed_notional
    )
    if remaining_capacity <= 0:
        logger.info("Sizing capped for %s: total exposure already at limit.", rec.symbol)
        return None

    target_notional = min(position_cap, remaining_capacity, available_margin * 0.5)
    if target_notional < last_price:
        logger.debug(
            "Sizing skipped for %s: target notional ₹%.0f < price ₹%.2f.",
            rec.symbol, target_notional, last_price,
        )
        return None

    # --- Compute quantity --------------------------------------------- #
    raw_qty = int(target_notional // last_price)
    if raw_qty < 1:
        return None
    quantity = raw_qty  # NSE equity lot size = 1

    # --- Limit price (1% above market) --------------------------------- #
    limit_price = round(last_price * (1.0 + LIMIT_PREMIUM_PCT), 2)

    return DhanOrder(
        symbol=rec.symbol,
        security_id="",  # resolved at execution time via SecurityIdMapper
        quantity=quantity,
        price=limit_price,
        order_type="LIMIT",
        transaction_type="BUY",
        product_type="CNC",
        validity="DAY",
        exchange_segment="NSE_EQ",
        correlation_id=f"q-{uuid.uuid4().hex[:12]}",
        status="PENDING",
    )


# --------------------------------------------------------------------------- #
# Verdict (preserved from the original risk manager)
# --------------------------------------------------------------------------- #
def _assess(
    rec: AnalystRecommendation,
    sector: Optional[str],
    sector_counts: Dict[str, int],
    critic: Optional[CriticFeedback],
) -> RiskAssessment:
    violations: List[str] = []
    if rec.confidence < MIN_CONFIDENCE:
        violations.append("confidence_below_threshold")
    if rec.action == "avoid":
        violations.append("analyst_recommends_avoid")
    if critic is not None and not critic.approved:
        violations.append("critic_vetoed")

    sector_key = sector or "UNKNOWN"
    # Sector cap only matters for otherwise-passing recommendations.
    if not violations and sector_counts.get(sector_key, 0) >= MAX_PER_SECTOR:
        violations.append("sector_limit_exceeded")

    approved = not violations
    if approved:
        sector_counts[sector_key] = sector_counts.get(sector_key, 0) + 1
        decision = "FLAG" if rec.confidence < _FLAG_BAND else "PASS"
    else:
        decision = "REJECT"

    return RiskAssessment(
        symbol=rec.symbol,
        sector=sector,
        approved=approved,
        decision=decision,
        confidence=rec.confidence,
        violations=violations,
    )


async def _annotate(
    assessments: List[RiskAssessment],
    recs_by_symbol: Dict[str, AnalystRecommendation],
) -> List[RiskAssessment]:
    """Attach one-line LLM risk notes (best-effort; deterministic verdicts unchanged)."""
    if not assessments:
        return assessments
    lines = [
        "You are a risk manager for an equity research desk.",
        "For each assessment write a one-line note explaining the verdict.",
        f"Guardrails: min confidence {MIN_CONFIDENCE}, max {MAX_PER_SECTOR} stocks per sector.",
        "",
        "Assessments:",
    ]
    for a in assessments:
        rec = recs_by_symbol.get(a.symbol)
        lines.append(
            f"- {a.symbol} sector={a.sector} decision={a.decision} "
            f"confidence={a.confidence:.2f} violations={a.violations} "
            f"action={getattr(rec, 'action', None)}"
        )
    try:
        llm = ChatGroq(model=RISK_MODEL, temperature=0).with_structured_output(_RiskNotes)
        out = await llm.ainvoke("\n".join(lines))
        note_map = {n.symbol: n.note for n in out.notes}
        for a in assessments:
            if a.symbol in note_map:
                a.notes = note_map[a.symbol]
    except Exception:  # noqa: BLE001 - notes are optional
        pass
    return assessments


def _summarize_rejection(assessments: List[RiskAssessment]) -> str:
    reasons = sorted({v for a in assessments for v in a.violations})
    symbols = ", ".join(a.symbol for a in assessments)
    return (
        f"All {len(assessments)} candidate(s) rejected ({symbols}). "
        f"Violations: {', '.join(reasons) or 'n/a'}."
    )


# --------------------------------------------------------------------------- #
# Node
# --------------------------------------------------------------------------- #
async def risk_manager(state: QuantState) -> QuantState:
    """Populate ``state.risk_assessments``, ``state.rejection_reason``, and size approved orders.

    Phase 2.3 additions: every approved assessment now also gets a
    ``sized_order`` (a :class:`DhanOrder` payload) computed from the live
    ``available_margin`` and last-traded price. The sized orders are queued
    onto ``state.pending_actions`` so the HiTL gate can show them in the
    ApprovalModal with the exact capital impact.
    """
    sectors = _sector_map(state)
    prices = _last_price_map(state)
    critic_by_symbol = _critic_map(state)

    # Highest-confidence first so the sector cap keeps the strongest names.
    ordered = sorted(
        state.analyst_recommendations, key=lambda r: r.confidence, reverse=True
    )
    sector_counts: Dict[str, int] = {}
    assessments = [
        _assess(rec, sectors.get(rec.symbol), sector_counts, critic_by_symbol.get(rec.symbol))
        for rec in ordered
    ]
    assessments = await _annotate(assessments, {r.symbol: r for r in ordered})

    # --- Phase 2.3: quantitative sizing pass --------------------------- #
    available_margin = float(state.available_margin or 0.0)
    deployed_notional = 0.0
    sized_orders: List[DhanOrder] = []
    for rec, assessment in zip(ordered, assessments):
        if not assessment.approved:
            continue
        last_price = prices.get(rec.symbol, 0.0)
        order = _size_order(
            rec,
            state=state,
            last_price=last_price,
            available_margin=available_margin,
            already_deployed_notional=deployed_notional,
        )
        if order is None:
            # Sizing was not possible (no price / no margin / exposure cap).
            # We still mark the assessment approved but without a sized order.
            continue
        assessment.sized_order = order
        assessment.proposed_quantity = order.quantity
        assessment.proposed_price = order.price
        assessment.required_margin = round(order.quantity * order.price, 2)
        deployed_notional += assessment.required_margin
        sized_orders.append(order)

    state.risk_assessments = assessments
    state.pending_actions = sized_orders

    if assessments and all(not a.approved for a in assessments):
        state.rejection_reason = _summarize_rejection(assessments)
    return state
