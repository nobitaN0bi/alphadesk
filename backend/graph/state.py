"""Shared graph state for AgentQuant Apex.

Defines ``QuantState`` — the single Pydantic v2 model that flows through every
node of the LangGraph — together with all nested models the agents read from and
write to. Each agent is a pure function ``(state: QuantState) -> QuantState``
that accretes its output onto the state.

This file is the **evolved** state schema for the AgentQuant Apex migration.
It supersedes the original ``PortfolioState`` (kept as a backward-compatible
alias) and merges three lineages:

1.  **AlphaDesk spine** (preserved verbatim) — Scanner, Research, Analyst,
    RiskManager, Execution agents' input/output models, ``user_query``,
    ``human_approved`` gate, and the ``rejection_reason`` audit trail.
2.  **AgentQuant swarm fields** (inherited from
    ``@temp/AgentQuant/src/agent/swarm/state.py``) — ``RegimeContext``,
    ``CriticFeedback``, ``swarm_consensus_score`` injected by the new
    Orchestrator and Critic nodes (Phase 1).
3.  **QuantDinger execution fields** (inherited from
    ``@temp/QuantDinger/backend_api_python/app/services/live_trading/``) —
    ``available_margin``, ``current_holdings``, ``DhanOrder`` payloads with
    ``security_id`` + ``correlation_id`` for idempotent live placement.

Field semantics tie back to the guardrails in CLAUDE.md: analyst confidence must
reach 0.70 to proceed, no more than 3 stocks per sector, any user_watchlist
write requires ``human_approved = True``, and any live broker order requires
both ``human_approved = True`` AND a successful ``portfolio_sync`` snapshot
of ``available_margin`` and ``current_holdings``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Scanner output (preserved)
# --------------------------------------------------------------------------- #
class ScanResult(BaseModel):
    """A single candidate surfaced by the Scanner agent."""

    symbol: str = Field(..., description="NSE ticker symbol, e.g. 'RELIANCE'.")
    ind_key: Optional[str] = Field(
        None, description="IND Money instrument key (e.g. 'INDS00577'); required by downstream tools."
    )
    name: Optional[str] = Field(None, description="Company display name, if known.")
    sector: Optional[str] = Field(
        None, description="Sector classification used by the per-sector guardrail."
    )
    signal: str = Field(
        ..., description="Why this stock was flagged, e.g. 'top gainer', 'volume spike'."
    )
    last_price: Optional[float] = Field(None, description="Latest traded price at scan time.")
    change_percent: Optional[float] = Field(
        None, description="Percent move that triggered the signal."
    )
    score: Optional[float] = Field(
        None, description="Scanner-assigned interest score (higher = stronger signal)."
    )
    source: Optional[str] = Field(
        None, description="IND Money tool the signal came from, e.g. 'get_indian_stocks_movers'."
    )


# --------------------------------------------------------------------------- #
# Research output (preserved)
# --------------------------------------------------------------------------- #
class ResearchReport(BaseModel):
    """Deep-dive findings produced by the Research agent for one candidate."""

    symbol: str = Field(..., description="NSE ticker the report covers.")
    summary: str = Field(..., description="Narrative summary of the research findings.")
    fundamentals: Dict[str, float] = Field(
        default_factory=dict,
        description="Key fundamental metrics, e.g. {'pe_ratio': 22.4, 'market_cap': 1.2e12}.",
    )
    technicals: Dict[str, float] = Field(
        default_factory=dict,
        description="Key technical metrics derived from OHLC, e.g. {'rsi': 61.0}.",
    )
    options_insight: Optional[str] = Field(
        None,
        description="Notes from option chain / greeks history (IV, OI skew, etc.), if analyzed.",
    )
    sources: List[str] = Field(
        default_factory=list,
        description="IND Money tools or documents consulted to build the report.",
    )


# --------------------------------------------------------------------------- #
# Analyst output (preserved)
# --------------------------------------------------------------------------- #
class AnalystRecommendation(BaseModel):
    """Structured recommendation written by the Analyst agent."""

    symbol: str = Field(..., description="NSE ticker the recommendation applies to.")
    action: Literal["buy", "hold", "avoid"] = Field(
        ..., description="Recommended stance on the stock."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score in [0, 1]; must reach 0.70 to clear the RiskManager.",
    )
    thesis: Optional[str] = Field(
        None, description="Optional one-paragraph synthesis of the bull and bear cases."
    )
    bull_thesis: str = Field(..., description="The case for the stock outperforming.")
    bear_thesis: str = Field(
        ..., description="The downside case / reasons the stock could underperform."
    )
    key_risks: List[str] = Field(
        default_factory=list, description="Principal risks that could break the thesis."
    )
    catalysts: List[str] = Field(
        default_factory=list, description="Events/catalysts that could move the stock."
    )
    target_price: Optional[float] = Field(
        None, description="Optional price target underpinning the thesis."
    )
    time_horizon: Optional[str] = Field(
        None, description="Intended holding horizon, e.g. 'short-term', '6-12 months'."
    )
    citations: List[str] = Field(
        default_factory=list,
        description="RAG passages or ind_keys references backing the thesis.",
    )


# --------------------------------------------------------------------------- #
# Risk output (preserved)
# --------------------------------------------------------------------------- #
class RiskAssessment(BaseModel):
    """RiskManager verdict on a single recommendation (pure logic on state)."""

    symbol: str = Field(..., description="NSE ticker being assessed.")
    sector: Optional[str] = Field(
        None, description="Sector used to enforce the max-3-stocks-per-sector rule."
    )
    approved: bool = Field(
        ..., description="True if the recommendation passes all guardrails (PASS or FLAG)."
    )
    decision: Literal["PASS", "REJECT", "FLAG"] = Field(
        ...,
        description=(
            "RiskManager verdict: PASS (queue for execution), REJECT (drop), "
            "FLAG (clears guardrails but needs human review before queueing)."
        ),
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence carried over from the recommendation (checked against 0.70).",
    )
    violations: List[str] = Field(
        default_factory=list,
        description="Guardrails breached, e.g. ['confidence_below_threshold', 'sector_limit'].",
    )
    notes: Optional[str] = Field(
        None, description="Human-readable explanation of the verdict."
    )
    # --- Phase 2 additions (AgentQuant Apex) ---
    proposed_quantity: Optional[int] = Field(
        None,
        description=(
            "Quantity sized by the RiskManager's quantitative sizing engine. "
            "Only populated when decision in (PASS, FLAG) and a live price was available."
        ),
    )
    proposed_price: Optional[float] = Field(
        None,
        description="Limit price (rounded) the RiskManager recommends for the order.",
    )
    required_margin: Optional[float] = Field(
        None,
        description="Notional capital required for ``proposed_quantity`` x ``proposed_price``.",
    )


# --------------------------------------------------------------------------- #
# NEW (AgentQuant Apex) — Regime + Critic swarm fields
# --------------------------------------------------------------------------- #
RegimeLabel = Literal[
    "LowVol-Bull",
    "LowVol-Bear",
    "HighVol-Bull",
    "HighVol-Bear",
    "Crisis",
    "Unknown",
]


class RegimeContext(BaseModel):
    """Market regime snapshot produced by the Orchestrator (Phase 1, AgentQuant lineage)."""

    label: RegimeLabel = Field(..., description="6-class regime label.")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in the regime label (0-1)."
    )
    narrative: str = Field(..., description="One-paragraph explanation of the regime.")
    nifty_momentum_pct: Optional[float] = Field(
        None,
        description="3-month NIFTY 50 momentum used as the regime's trend proxy.",
    )
    india_vix_proxy: Optional[float] = Field(
        None,
        description="Synthetic India VIX proxy derived from IND Money mover volatility.",
    )
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of regime detection.",
    )


class CriticFeedback(BaseModel):
    """LLM-as-judge verdict from the Critic node (Phase 1, AgentQuant lineage)."""

    symbol: str = Field(..., description="NSE ticker being reviewed.")
    approved: bool = Field(
        ..., description="True if the critic does not veto the recommendation."
    )
    reason: str = Field(..., description="Plain-English reasoning for the verdict.")
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Critic's risk score; higher = more dangerous given the regime.",
    )


# --------------------------------------------------------------------------- #
# NEW (AgentQuant Apex) — QuantDinger execution lineage
# --------------------------------------------------------------------------- #
OrderSide = Literal["BUY", "SELL"]
OrderKind = Literal["MARKET", "LIMIT"]
ProductType = Literal["CNC", "INTRADAY", "MARGIN"]
OrderValidity = Literal["DAY", "IOC"]
OrderStatus = Literal[
    "PENDING", "PLACED", "EXECUTED", "REJECTED", "FAILED", "CANCELLED"
]


class DhanOrder(BaseModel):
    """Typed live-order payload for the Dhan HQ adapter.

    Replaces the lightweight ``PendingAction`` for the live-execution path.
    Inherits fields from the @temp/transormation.md PRD and the Dhan HQ REST
    schema. ``correlation_id`` is the idempotency key — re-submitting the same
    correlation id will NOT place a duplicate order.
    """

    symbol: str = Field(..., description="NSE trading symbol, e.g. 'RELIANCE'.")
    security_id: str = Field(
        ...,
        description=(
            "Dhan-assigned NSE securityId resolved via security_id_mapper. "
            "NEVER fabricated — execution will reject if missing."
        ),
    )
    quantity: int = Field(..., gt=0, description="Whole-share quantity to trade.")
    price: float = Field(
        0.0,
        ge=0.0,
        description="Limit price (0 for MARKET orders).",
    )
    order_type: OrderKind = Field("LIMIT", description="MARKET or LIMIT.")
    transaction_type: OrderSide = Field("BUY", description="BUY or SELL.")
    product_type: ProductType = Field("CNC", description="CNC (delivery), INTRADAY, or MARGIN.")
    validity: OrderValidity = Field("DAY", description="DAY or IOC.")
    exchange_segment: Literal["NSE_EQ", "BSE_EQ", "NSE_FO"] = Field(
        "NSE_EQ", description="Exchange segment — NSE cash equity by default."
    )
    correlation_id: str = Field(
        ...,
        description=(
            "Idempotency key. Dhan's dhanOrderCorrelationId. "
            "Format: 'q-' + 12 hex chars; reused on graph resume to prevent duplicate orders."
        ),
    )
    dhan_order_id: Optional[str] = Field(
        None, description="Dhan-assigned order id, populated after a successful placement."
    )
    status: OrderStatus = Field(
        "PENDING", description="Lifecycle status of the order."
    )
    rejection_reason: Optional[str] = Field(
        None, description="Broker-supplied or adapter-supplied rejection reason."
    )
    placed_at: Optional[datetime] = Field(
        None, description="UTC timestamp of successful placement."
    )
    executed_at: Optional[datetime] = Field(
        None, description="UTC timestamp of fill (status=EXECUTED)."
    )
    filled_quantity: Optional[int] = Field(
        None, description="Filled quantity (may be < quantity for partial fills)."
    )
    average_price: Optional[float] = Field(
        None, description="Average execution price across all fills."
    )

    # --- Analytics fields, populated by the Monitor node after execution ---
    regime_at_placement: Optional[RegimeLabel] = Field(
        None, description="Regime label at the moment of placement (post-trade analytics)."
    )
    critic_risk_score: Optional[float] = Field(
        None, description="Critic risk score at the moment of placement."
    )


class Holding(BaseModel):
    """Live portfolio position (mirrors Dhan's /holdings payload)."""

    symbol: str = Field(..., description="NSE trading symbol.")
    security_id: Optional[str] = Field(None, description="Dhan securityId for the position.")
    quantity: int = Field(..., description="Current share quantity held.")
    avg_price: float = Field(..., description="Average buy price across all lots.")
    current_price: float = Field(..., description="Last traded price at snapshot time.")
    pnl: float = Field(..., description="Unrealised P&L in absolute INR.")
    pnl_pct: float = Field(..., description="Unrealised P&L as a percentage of cost basis.")
    day_change_pct: float = Field(0.0, description="Intraday move (%).")
    sector: Optional[str] = Field(None, description="Sector for downstream analytics.")


# --------------------------------------------------------------------------- #
# Legacy compatibility — keep PendingAction as a thin alias
# --------------------------------------------------------------------------- #
class PendingAction(BaseModel):
    """Legacy action object (paper-watchlist era).

    Retained for backward compatibility with the existing Execution agent and
    the paper-trading path when ``BROKER=`` is unset. New live-execution code
    must use :class:`DhanOrder` instead.
    """

    action_type: Literal["add_to_watchlist", "place_order"] = Field(
        ..., description="What the Execution agent will do once approved."
    )
    symbol: str = Field(..., description="NSE ticker the action targets.")
    rationale: Optional[str] = Field(
        None, description="Why this action is being proposed (links back to the thesis)."
    )
    payload: Dict[str, object] = Field(
        default_factory=dict,
        description="Action parameters, e.g. {'quantity': 10} for a future order.",
    )
    requires_human: bool = Field(
        True, description="Whether explicit human approval is required before execution."
    )
    status: Literal["pending", "approved", "rejected", "executed"] = Field(
        "pending", description="Lifecycle status of the action."
    )


# --------------------------------------------------------------------------- #
# Top-level graph state (EVOLVED)
# --------------------------------------------------------------------------- #
class QuantState(BaseModel):
    """Single shared state object threaded through every node of the LangGraph.

    Evolution from ``PortfolioState`` (preserved as alias below):

    - **Additive** — every original field is preserved with identical semantics.
    - **Swarm fields** — ``regime_context``, ``critic_feedback``,
      ``swarm_consensus_score`` populated by the new Orchestrator and Critic nodes.
    - **Execution fields** — ``available_margin``, ``current_holdings``,
      ``pending_actions`` (now ``DhanOrder``), ``executed_trades`` (new), plus
      explicit ``place_live_orders`` toggle so the same state can drive both
      paper and live execution paths.

    Backward compat: ``pending_actions`` and ``approved_actions`` now hold
    ``DhanOrder`` instances instead of ``PendingAction``. Code that consumed
    ``PendingAction`` must be updated (the existing execution.py evolves in
    Phase 2.4).
    """

    # --- AlphaDesk spine (preserved verbatim) ---
    user_query: str = Field(
        ..., description="Natural-language research request that kicked off the run."
    )
    scan_results: List[ScanResult] = Field(
        default_factory=list, description="Candidates surfaced by the Scanner agent."
    )
    research_reports: Dict[str, ResearchReport] = Field(
        default_factory=dict,
        description="Research reports keyed by NSE symbol.",
    )
    analyst_recommendations: List[AnalystRecommendation] = Field(
        default_factory=list, description="Structured recommendations from the Analyst agent."
    )
    risk_assessments: List[RiskAssessment] = Field(
        default_factory=list, description="RiskManager verdicts on the recommendations."
    )
    # --- legacy paper-watchlist plumbing (kept for backward compat) ---
    paper_watchlist: List[str] = Field(
        default_factory=list,
        description=(
            "Application-level watchlist of NSE symbols that passed research and risk checks. "
            "Not connected to any brokerage; the read-only IND Money MCP cannot modify real watchlists."
        ),
    )

    # --- Human-in-the-loop gate (preserved) ---
    human_approved: bool = Field(
        False,
        description="Set True by the human gate; required before any user_watchlist write.",
    )
    rejection_reason: Optional[str] = Field(
        None, description="Reason supplied by the human when approval is withheld."
    )

    # --- NEW (Phase 1): AgentQuant swarm fields ---
    regime_context: Optional[RegimeContext] = Field(
        None, description="Market regime produced by the Orchestrator node before Scanner."
    )
    critic_feedback: List[CriticFeedback] = Field(
        default_factory=list,
        description="Per-symbol vetoes from the Critic node (inserted between Analyst and RiskManager).",
    )
    swarm_consensus_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Aggregate confidence that the swarm agrees on the recommendations. "
            "Below 0.5 the Execution path is downgraded to paper/watchlist only."
        ),
    )

    # --- NEW (Phase 2): QuantDinger execution lineage ---
    available_margin: float = Field(
        0.0,
        description=(
            "Available cash margin (INR) from Dhan's /fundlimit endpoint. "
            "Populated by the PortfolioSync node at the start of every run."
        ),
    )
    used_margin: float = Field(
        0.0,
        description="Margin currently deployed (INR) computed from current_holdings.",
    )
    current_holdings: List[Holding] = Field(
        default_factory=list,
        description="Live positions from Dhan's /holdings endpoint, snapshot at run start.",
    )
    portfolio_synced_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp of the last successful PortfolioSync. Stale snapshots invalidate sizing.",
    )
    place_live_orders: bool = Field(
        False,
        description=(
            "Master switch for live execution. True only when BROKER=dhan env is set AND "
            "human_approved=True AND the user has explicitly opted in via the ApprovalModal."
        ),
    )

    # --- Pending + approved + execution-history queues ---
    pending_actions: List[DhanOrder] = Field(
        default_factory=list,
        description=(
            "Live orders staged by the RiskManager sizing engine, awaiting "
            "human_approved=True before placement."
        ),
    )
    approved_actions: List[DhanOrder] = Field(
        default_factory=list,
        description=(
            "Live orders promoted from pending_actions after human_approved=True. "
            "Once the broker reports EXECUTED, they move to executed_trades."
        ),
    )
    execution_history: List[DhanOrder] = Field(
        default_factory=list,
        description="Append-only audit trail of every order the Execution agent has processed.",
    )
    executed_trades: List[DhanOrder] = Field(
        default_factory=list,
        description="Filled orders (Dhan status=EXECUTED), used by the Monitor node for reconciliation.",
    )


# --------------------------------------------------------------------------- #
# Backward-compatible alias — every legacy import keeps working.
# --------------------------------------------------------------------------- #
PortfolioState = QuantState  # type: ignore[misc,assignment]
