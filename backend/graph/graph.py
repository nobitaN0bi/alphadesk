"""LangGraph assembly for AgentQuant Apex (Phase 1.2).

Wires **eight** agent nodes into a single ``StateGraph`` over :class:`QuantState`
(``PortfolioState`` is preserved as an alias in ``graph.state``):

    START
      -> orchestrator            (regime + swarm consensus)
      -> portfolio_sync          (Dhan live margin + holdings)
      -> scanner                 (existing — preserve)
      -> research                (existing — preserve, parallel)
      -> analyst                 (existing — preserve)
      -> critic                  (regime-aware vetoes)
      -> risk_manager            (existing — guardrails + sizing in Phase 2.3)
      --(PASS|FLAG)--> execution (existing — paper or live, evolved in Phase 2.4)
      --(REJECT)------> END

Conditional routing after ``risk_manager``:
    - any assessment PASS or FLAG  -> execution
    - otherwise (all REJECT / none) -> END (rejection_reason set upstream)

HiTL pause: ``interrupt_before=["execution"]`` — graph stops before execution so
a human can inspect risk assessments + capital impact. Resume by setting
``human_approved=True`` on the thread and re-invoking.

Persistence: ``SqliteSaver`` (promoted from ``MemorySaver``) — required for
Phase 2 idempotency. The checkpointer is stored at ``backend/.quantdesk.db``.

Backward compatibility: the module exports the same ``alphaDesk_graph``,
``run_graph``, ``resume_after_approval``, and ``route_after_risk`` symbols
that the rest of the codebase already imports. The state type is widened
to ``QuantState`` but every original field is preserved (see graph.state).
"""

from __future__ import annotations

import os
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agents.analyst import analyst
from agents.critic import critic
from agents.execution import execution
from agents.orchestrator import orchestrator
from agents.portfolio_sync import portfolio_sync
from agents.research import research
from agents.risk_manager import risk_manager
from agents.scanner import scanner
from graph.state import PortfolioState, QuantState


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def route_after_risk(state: QuantState) -> str:
    """Route to execution if anything passed risk, otherwise end the run."""
    if any(a.decision in ("PASS", "FLAG") for a in state.risk_assessments):
        return "execution"
    return END


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #
def _build_graph():
    """Construct and compile the AgentQuant Apex graph."""
    builder = StateGraph(QuantState)

    # --- NEW (Phase 1.2): swarm pre-amble ---
    builder.add_node("orchestrator", orchestrator)
    builder.add_node("portfolio_sync", portfolio_sync)
    # --- NEW (Phase 1.2): post-Analyst veto ---
    builder.add_node("critic", critic)

    # --- EXISTING AlphaDesk research pipeline (preserved) ---
    builder.add_node("scanner", scanner)
    builder.add_node("research", research)
    builder.add_node("analyst", analyst)
    builder.add_node("risk_manager", risk_manager)
    builder.add_node("execution", execution)

    # --- Edges ---
    # Swarm pre-amble
    builder.add_edge(START, "orchestrator")
    builder.add_edge("orchestrator", "portfolio_sync")
    builder.add_edge("portfolio_sync", "scanner")

    # Research pipeline (preserved, with critic inserted)
    builder.add_edge("scanner", "research")
    builder.add_edge("research", "analyst")
    builder.add_edge("analyst", "critic")               # NEW
    builder.add_edge("critic", "risk_manager")          # NEW
    builder.add_conditional_edges(
        "risk_manager",
        route_after_risk,
        {"execution": "execution", END: END},
    )
    builder.add_edge("execution", END)

    # --- Persistence ---
    # Use SqliteSaver so an interrupted run can be resumed without losing
    # the in-flight DhanOrder payloads (idempotency requirement, Phase 2.1).
    # Falls back to in-memory saver for unit tests / dev when no writable
    # filesystem is available.
    checkpointer = _build_checkpointer()

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["execution"],
    )


def _build_checkpointer():
    """Return a SqliteSaver in production, MemorySaver when sqlite is unavailable.

    Honours ``AGENTQUANT_CHECKPOINTER_PATH`` env var; default
    ``backend/.quantdesk.db`` relative to the project root.
    """
    path = os.getenv("AGENTQUANT_CHECKPOINTER_PATH", ".quantdesk.db")
    try:
        return SqliteSaver.from_conn_string(path)
    except Exception as exc:  # noqa: BLE001
        # Degrade gracefully — MemorySaver keeps the dev/test loop working.
        import logging
        logging.getLogger("alphadesk.graph").warning(
            "SqliteSaver unavailable (%s); falling back to MemorySaver.", exc
        )
        return MemorySaver()


alphaDesk_graph = _build_graph()


# --------------------------------------------------------------------------- #
# Public helpers (backward-compatible signatures)
# --------------------------------------------------------------------------- #
def _as_state(result: object) -> QuantState:
    if isinstance(result, QuantState):
        return result
    if isinstance(result, dict):
        return QuantState.model_validate(result)
    return QuantState.model_validate(result)


async def run_graph(user_query: str, thread_id: str = "default") -> QuantState:
    """Run the research desk for ``user_query`` and return the resulting state.

    With the HiTL interrupt, this returns the state *paused before execution*
    (orchestrator + portfolio_sync + research + critic + risk assessments
    populated, awaiting human approval). Call :func:`resume_after_approval`
    to finalize.
    """
    config = {"configurable": {"thread_id": thread_id}}
    initial = QuantState(user_query=user_query)
    result = await alphaDesk_graph.ainvoke(initial, config)
    return _as_state(result)


async def resume_after_approval(
    thread_id: str = "default",
    approved: bool = True,
    rejection_reason: Optional[str] = None,
) -> QuantState:
    """Resume a paused run after a human decision; returns the final state.

    Sets ``human_approved`` (and optionally ``rejection_reason``) on the thread,
    then resumes execution. If ``approved`` is True the Execution agent stages PASS
    stocks and finalizes them into ``approved_actions`` / ``paper_watchlist``.
    """
    config = {"configurable": {"thread_id": thread_id}}
    update: dict = {"human_approved": approved}
    if rejection_reason is not None:
        update["rejection_reason"] = rejection_reason
    await alphaDesk_graph.aupdate_state(config, update)
    result = await alphaDesk_graph.ainvoke(None, config)
    return _as_state(result)


# Backward-compat re-export — every existing ``PortfolioState`` import keeps working.
__all__ = [
    "alphaDesk_graph",
    "run_graph",
    "resume_after_approval",
    "route_after_risk",
    "PortfolioState",
    "QuantState",
]
