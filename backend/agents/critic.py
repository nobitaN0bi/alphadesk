"""Critic agent — sits between the Analyst and the RiskManager.

Inherits the LLM-as-judge pattern from
``@temp/AgentQuant/src/agent/swarm/critic_agent.py``. Reviews each
``AnalystRecommendation`` against the detected regime + current portfolio and
issues a per-symbol :class:`CriticFeedback` verdict that can veto trades in
hostile regimes.

The Critic NEVER modifies the analyst recommendations or the risk guardrails
themselves. It only attaches vetoes + risk scores that the downstream
RiskManager may consult (the RiskManager currently ignores these for backward
compatibility — wiring them in is Phase 2.3's job).

Pure async node ``(state: QuantState) -> QuantState``.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from graph.state import (
    AnalystRecommendation,
    CriticFeedback,
    QuantState,
    RegimeContext,
)

logger = logging.getLogger("alphadesk.critic")

CRITIC_MODEL = "llama-3.3-70b-versatile"
# Veto thresholds (conservative defaults).
VETO_RISK_SCORE = 0.85
HIGH_RISK_SCORE = 0.65


# --------------------------------------------------------------------------- #
# Structured LLM output
# --------------------------------------------------------------------------- #
class _CriticVerdict(BaseModel):
    symbol: str = Field(..., description="NSE ticker the verdict applies to.")
    approved: bool = Field(..., description="False = veto this recommendation.")
    reason: str = Field(..., description="One-line explanation of the verdict.")
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Regime-aware risk score (0 = safe, 1 = hostile).",
    )


class _CriticBatch(BaseModel):
    verdicts: List[_CriticVerdict] = Field(
        default_factory=list,
        description="One verdict per analyst recommendation.",
    )


def _get_llm() -> ChatGroq:
    return ChatGroq(model=CRITIC_MODEL, temperature=0)


def _format_recommendation(rec: AnalystRecommendation) -> str:
    return (
        f"- {rec.symbol} action={rec.action} confidence={rec.confidence:.2f}\n"
        f"  bull: {rec.bull_thesis[:120]}\n"
        f"  bear: {rec.bear_thesis[:120]}\n"
        f"  risks: {', '.join(rec.key_risks) or 'n/a'}\n"
        f"  catalysts: {', '.join(rec.catalysts) or 'n/a'}"
    )


def _heuristic_critic(
    rec: AnalystRecommendation, regime: Optional[RegimeContext]
) -> CriticFeedback:
    """Regime- and confidence-aware fallback when the LLM is unavailable.

    Vetoes:
        - any 'buy' in a Crisis regime
        - any 'buy' with confidence < 0.65 (we're already below the
          RiskManager's 0.70 floor, but the critic is stricter)
    """
    approved = True
    reason = "Heuristic: passes regime + confidence check."
    risk_score = 0.4
    if regime is not None:
        if regime.label == "Crisis" and rec.action == "buy":
            approved = False
            reason = "Heuristic veto: BUY in Crisis regime."
            risk_score = 0.95
        elif regime.label in ("HighVol-Bear",) and rec.action == "buy":
            risk_score = 0.75
            reason = "Heuristic: elevated risk in HighVol-Bear."
    if rec.confidence < 0.65 and rec.action == "buy":
        risk_score = max(risk_score, 0.8)
        reason = "Heuristic: low-confidence BUY."
    return CriticFeedback(
        symbol=rec.symbol,
        approved=approved,
        reason=reason,
        risk_score=risk_score,
    )


# --------------------------------------------------------------------------- #
# Node
# --------------------------------------------------------------------------- #
async def critic(state: QuantState) -> QuantState:
    """Produce per-recommendation critic feedback (does not modify recs)."""
    if not state.analyst_recommendations:
        return state

    regime = state.regime_context
    regime_label = regime.label if regime is not None else "Unknown"
    regime_confidence = regime.confidence if regime is not None else 0.0
    regime_narrative = regime.narrative if regime is not None else ""

    rec_lines = "\n".join(_format_recommendation(r) for r in state.analyst_recommendations)
    prompt = (
        "You are the head of risk at a quantitative trading desk. Review each "
        "analyst recommendation against the current market regime and the live "
        "portfolio context. Veto any recommendation that is reckless given the "
        "regime (e.g. aggressive BUY in Crisis or HighVol-Bear). Output a "
        "verdict per symbol with: approved (bool), reason (1 sentence), "
        "risk_score (0=safe, 1=hostile).\n\n"
        f"REGIME: {regime_label} (confidence={regime_confidence:.2f})\n"
        f"NARRATIVE: {regime_narrative}\n\n"
        f"RECOMMENDATIONS ({len(state.analyst_recommendations)}):\n{rec_lines}\n\n"
        f"PORTFOLIO: {len(state.current_holdings)} positions, "
        f"available_margin=₹{state.available_margin:,.0f}\n"
    )

    try:
        llm = _get_llm().with_structured_output(_CriticBatch)
        out = await llm.ainvoke(prompt)
        verdicts = out.verdicts
    except Exception as exc:  # noqa: BLE001 - heuristic must never break the run
        logger.warning("Critic LLM failed (%s); using heuristic.", exc)
        verdicts = [
            _CriticVerdict(**fb.model_dump())
            for fb in (_heuristic_critic(r, regime) for r in state.analyst_recommendations)
        ]

    # Dedupe to one verdict per symbol, prefer LLM verdict on collision.
    by_symbol: dict[str, CriticFeedback] = {}
    for v in verdicts:
        by_symbol[v.symbol] = CriticFeedback(
            symbol=v.symbol,
            approved=v.approved,
            reason=v.reason,
            risk_score=v.risk_score,
        )
    # Ensure every analyst symbol has at least a heuristic verdict.
    for r in state.analyst_recommendations:
        if r.symbol not in by_symbol:
            by_symbol[r.symbol] = _heuristic_critic(r, regime)

    state.critic_feedback = list(by_symbol.values())
    vetoed = [c.symbol for c in state.critic_feedback if not c.approved]
    if vetoed:
        logger.info("Critic vetoed: %s", ", ".join(vetoed))
    return state


__all__ = ["critic", "CriticFeedback"]
