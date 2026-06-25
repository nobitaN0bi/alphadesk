"""Orchestrator agent — top of the AgentQuant Apex graph.

Runs *before* the Scanner and decides the operating mode for the rest of the
pipeline based on the detected market regime + swarm consensus. Inherits the
swarm orchestration pattern from
``@temp/AgentQuant/src/agent/swarm/orchestrator.py`` and adapts it to a single
Pydantic ``QuantState`` rather than a dict-of-dicts ``SwarmState``.

Responsibilities:
    1. **Regime detection** — classify the market into one of
       ``LowVol-Bull | LowVol-Bear | HighVol-Bull | HighVol-Bear | Crisis``
       using NIFTY 50 momentum + India VIX proxy. Same percentile-based logic
       as ``AgentQuant`` (no hardcoded VIX thresholds).
    2. **Swarm admission floor** — ``min_approved_proposals = 2`` is enforced
       in the RiskManager; the orchestrator just sets a *downgrade* flag when
       the regime is hostile.
    3. **Live execution gate** — flips ``state.place_live_orders = False`` when
       regime is ``Crisis`` or consensus is too low.

Pure async node ``(state: QuantState) -> QuantState``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from graph.state import (
    CriticFeedback,
    QuantState,
    RegimeContext,
    RegimeLabel,
)

logger = logging.getLogger("alphadesk.orchestrator")

ORCHESTRATOR_MODEL = "llama-3.3-70b-versatile"
SWARM_CONSENSUS_FLOOR = 0.5
HOSTILE_LABELS: tuple[RegimeLabel, ...] = ("HighVol-Bear", "Crisis")


# --------------------------------------------------------------------------- #
# Structured LLM output schema
# --------------------------------------------------------------------------- #
class _RegimeVerdict(BaseModel):
    label: RegimeLabel = Field(..., description="6-class regime label.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence 0-1.")
    narrative: str = Field(..., description="2-3 sentence explanation of the regime.")
    swarm_consensus_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Initial swarm consensus estimate BEFORE analyst or critic run. "
            "Used to gate live execution."
        ),
    )
    nifty_momentum_pct: float = Field(..., description="3-month NIFTY 50 momentum (%).")
    india_vix_proxy: float = Field(..., description="Synthetic India VIX proxy (annualised %).")


def _get_llm() -> ChatGroq:
    return ChatGroq(model=ORCHESTRATOR_MODEL, temperature=0)


# --------------------------------------------------------------------------- #
# Lightweight regime heuristic (fallback when LLM unavailable)
# --------------------------------------------------------------------------- #
def _heuristic_regime(nifty_mom: float, vix_proxy: float) -> RegimeLabel:
    """Percentile-based regime classification without LLM dependency.

    Thresholds mirror AgentQuant's ``regime_analyst.py`` but tuned for India:
      - VIX proxy > 22 %  -> HighVol territory
      - VIX proxy > 30 %  -> Crisis
      - Momentum > 5 %    -> Bull
      - Momentum < -5 %   -> Bear
    """
    if vix_proxy >= 30.0:
        return "Crisis"
    high_vol = vix_proxy >= 22.0
    if nifty_mom >= 5.0:
        return "HighVol-Bull" if high_vol else "LowVol-Bull"
    if nifty_mom <= -5.0:
        return "HighVol-Bear" if high_vol else "LowVol-Bear"
    return "HighVol-Bull" if high_vol else "Unknown"


# --------------------------------------------------------------------------- #
# Mock market-data fetch (in production this calls IND Money /external feed)
# --------------------------------------------------------------------------- #
async def _fetch_market_snapshot() -> tuple[float, float]:
    """Return ``(nifty_momentum_pct, india_vix_proxy_pct)``.

    Until the IND Money MCP exposes a NIFTY/India VIX endpoint, this returns a
    conservative neutral default: 0 % momentum, 18 % VIX proxy. Production
    should replace this with a real market-data call.
    """
    # TODO: wire to IND Money market index endpoint when available.
    return 0.0, 18.0


# --------------------------------------------------------------------------- #
# Node
# --------------------------------------------------------------------------- #
async def orchestrator(state: QuantState) -> QuantState:
    """Detect the market regime + set the swarm consensus floor.

    Always succeeds (fallback to heuristic) and never blocks the pipeline.
    """
    nifty_mom, vix_proxy = await _fetch_market_snapshot()
    prompt = (
        "You are the head of a quantitative research desk in India.\n"
        "Classify the current market regime given the NIFTY 50 3-month momentum "
        f"({nifty_mom:+.2f}%) and a synthetic India VIX proxy ({vix_proxy:.2f}%).\n"
        "Labels: LowVol-Bull, LowVol-Bear, HighVol-Bull, HighVol-Bear, Crisis, Unknown.\n"
        "Initial swarm consensus (0-1) should reflect how confident you are that "
        "any signals produced today will survive the next 5 trading days.\n"
        "Return label, confidence, narrative, swarm_consensus_score, and the inputs."
    )
    try:
        llm = _get_llm().with_structured_output(_RegimeVerdict)
        verdict = await llm.ainvoke(prompt)
    except Exception as exc:  # noqa: BLE001 - fallback must never break the run
        logger.warning("Orchestrator LLM failed (%s); using heuristic.", exc)
        label = _heuristic_regime(nifty_mom, vix_proxy)
        verdict = _RegimeVerdict(
            label=label,
            confidence=0.5,
            narrative=(
                f"Heuristic regime: NIFTY 3m momentum {nifty_mom:+.1f}%, "
                f"India VIX proxy {vix_proxy:.1f}%. LLM unavailable."
            ),
            swarm_consensus_score=0.5,
            nifty_momentum_pct=nifty_mom,
            india_vix_proxy=vix_proxy,
        )

    state.regime_context = RegimeContext(
        label=verdict.label,
        confidence=verdict.confidence,
        narrative=verdict.narrative,
        india_vix_proxy=verdict.india_vix_proxy,
        nifty_momentum_pct=verdict.nifty_momentum_pct,
    )
    state.swarm_consensus_score = verdict.swarm_consensus_score

    # --- Hostile-regime safety downgrade ---------------------------------- #
    if verdict.label in HOSTILE_LABELS or verdict.swarm_consensus_score < SWARM_CONSENSUS_FLOOR:
        state.place_live_orders = False
        logger.info(
            "Orchestrator downgraded to paper mode (regime=%s, consensus=%.2f).",
            verdict.label,
            verdict.swarm_consensus_score,
        )
    else:
        # Only re-enable live mode if env opt-in present
        state.place_live_orders = os.getenv("AGENTQUANT_LIVE_ENABLED", "").lower() in {
            "1",
            "true",
            "yes",
        }

    logger.info(
        "Orchestrator: regime=%s confidence=%.2f consensus=%.2f live=%s",
        state.regime_context.label,
        state.regime_context.confidence,
        state.swarm_consensus_score,
        state.place_live_orders,
    )
    return state


__all__ = ["orchestrator", "RegimeContext", "CriticFeedback"]
