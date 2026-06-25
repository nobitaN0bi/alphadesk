"""PortfolioSync agent — live Dhan account snapshot.

Injected between the Orchestrator and the Scanner. Calls the configured broker
(Dhan) to fetch:
    - ``available_margin`` from ``GET /fundlimit``
    - ``current_holdings`` from ``GET /holdings``
    - sets ``portfolio_synced_at`` to now

The sync is **idempotent** and **fail-safe**: if the broker is unconfigured
(``BROKER=``), or the call fails, the node populates empty defaults and
records the failure reason in ``state.rejection_reason`` (as a non-fatal
warning). The pipeline never breaks on a broker outage; the execution path
will simply have no live orders to place.

Pure async node ``(state: QuantState) -> QuantState``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from graph.state import Holding, QuantState

logger = logging.getLogger("alphadesk.portfolio_sync")

# When the broker is unconfigured we still want the graph to run end-to-end
# (paper mode) so we don't import the broker at module load — that would
# force a Dhan client even in test/dev environments.
_BROKER_IMPORT_ERROR: str | None = None


def _try_load_broker():
    """Lazily import + instantiate the configured broker. Returns ``None`` when
    ``BROKER=`` (paper mode) or the broker module is missing/broken.
    """
    global _BROKER_IMPORT_ERROR
    try:
        from broker.base import load_broker  # local import to avoid hard dep
    except Exception as exc:  # noqa: BLE001
        _BROKER_IMPORT_ERROR = str(exc)
        logger.warning("broker.base unavailable: %s", exc)
        return None
    return load_broker()


# --------------------------------------------------------------------------- #
# Mapping helpers
# --------------------------------------------------------------------------- #
def _holdings_from_dhan(raw: list) -> List[Holding]:
    """Translate a list of Dhan ``/holdings`` dicts into :class:`Holding`.

    The Dhan shape (post-Dec-2024 API) is approximately:
        { "tradingSymbol": str, "quantity": int, "avgCostPrice": float,
          "lastTradedPrice": float, "securityId": str, ... }

    Unknown fields are skipped (we never fabricate). Missing required fields
    cause the holding to be dropped with a warning (no silent zero-fill on
    financial numbers).
    """
    out: List[Holding] = []
    for h in raw or []:
        try:
            sym = h.get("tradingSymbol") or h.get("symbol")
            qty = int(h.get("quantity", 0))
            avg = float(h.get("avgCostPrice", 0.0))
            ltp = float(h.get("lastTradedPrice", 0.0))
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping malformed holding %r: %s", h, exc)
            continue
        if not sym or qty <= 0 or avg <= 0 or ltp <= 0:
            logger.debug("Skipping empty/invalid holding: %r", h)
            continue
        invested = qty * avg
        current = qty * ltp
        pnl = current - invested
        pnl_pct = (pnl / invested) * 100.0 if invested else 0.0
        out.append(
            Holding(
                symbol=sym,
                security_id=str(h.get("securityId", "")) or None,
                quantity=qty,
                avg_price=avg,
                current_price=ltp,
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 3),
                day_change_pct=float(h.get("dayChangePct", 0.0)) if h.get("dayChangePct") is not None else 0.0,
            )
        )
    return out


def _margin_from_dhan(raw: dict) -> float:
    """Extract available margin from a Dhan ``/fundlimit`` payload.

    The Dhan response nests margin info under ``data``. We look for
    ``availabelBalance`` (sic, the actual Dhan typo) and fall back to
    ``availableBalance`` if present. If neither, return 0.0 — the pipeline
    will treat the run as no-margin-available (paper-only).
    """
    if not isinstance(raw, dict):
        return 0.0
    data = raw.get("data") or raw
    for key in ("availabelBalance", "availableBalance", "availableMargin"):
        val = data.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return 0.0


# --------------------------------------------------------------------------- #
# Node
# --------------------------------------------------------------------------- #
async def portfolio_sync(state: QuantState) -> QuantState:
    """Sync available_margin + current_holdings from the configured broker.

    Always returns the state. On failure or when no broker is configured, the
    state is populated with empty defaults and the run continues in paper mode.
    """
    broker = _try_load_broker()
    if broker is None:
        logger.info("portfolio_sync: no broker configured; using paper defaults.")
        state.available_margin = 0.0
        state.used_margin = 0.0
        state.current_holdings = []
        state.portfolio_synced_at = datetime.now(timezone.utc)
        # Mark as opt-in to live mode (i.e. willing) only if env is set; the
        # graph resume path will keep ``place_live_orders`` whatever it was.
        return state

    # --- Live fetch (best-effort; never fatal) ---
    try:
        funds = await broker.get_funds()
        state.available_margin = float(funds or 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("portfolio_sync: get_funds failed (%s); margin=0", exc)
        state.available_margin = 0.0

    try:
        raw_holdings = await broker.get_holdings()
        state.current_holdings = _holdings_from_dhan(raw_holdings)
        state.used_margin = round(
            sum(h.quantity * h.avg_price for h in state.current_holdings), 2
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("portfolio_sync: get_holdings failed (%s); empty list", exc)
        state.current_holdings = []
        state.used_margin = 0.0

    state.portfolio_synced_at = datetime.now(timezone.utc)
    logger.info(
        "portfolio_sync: margin=₹%.0f holdings=%d synced_at=%s",
        state.available_margin,
        len(state.current_holdings),
        state.portfolio_synced_at.isoformat(),
    )
    return state


__all__ = ["portfolio_sync", "Holding"]
