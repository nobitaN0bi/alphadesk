"""FastAPI entrypoint for AlphaDesk.

Serves the LangGraph research desk over HTTP. Run with::

    cd backend && uvicorn api.main:app --reload --port 8000

Endpoints:
    POST /analyze          -> kick off a run; streams agent updates via SSE,
                              ends with analyst recommendations + risk assessments.
    POST /approve          -> resume a run paused at the human-in-the-loop gate.
    GET  /status/{run_id}  -> current state of a run.

Tracking: each run gets a UUID that is passed to LangGraph as the ``run_id`` in
the config, so it becomes the LangSmith trace root id — the same id is used as
the checkpointer thread id and the app-level run handle. LangSmith tracing stays
on via env (LANGCHAIN_TRACING_V2); it is never disabled here.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Load backend/.env so GROQ_API_KEY, LANGCHAIN_*, IND_MONEY_MCP_URL are present
# before the graph and agents read them.
load_dotenv()

from broker.base import load_broker  # noqa: E402
from graph.graph import alphaDesk_graph, resume_after_approval  # noqa: E402
from graph.state import PortfolioState  # noqa: E402

logger = logging.getLogger("alphadesk.api")

app = FastAPI(title="AlphaDesk", version="0.1.0")

# Frontend dev server (Next.js). Allow both localhost and 127.0.0.1 on any port
# so the browser reaches the API regardless of how the dev URL is opened.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# In-memory run registry (swap for a store/DB in production)
# --------------------------------------------------------------------------- #
# run_id -> {"run_uuid": UUID, "query": str, "status": str, "action_id": str|None, ...}
_RUNS: Dict[str, Dict[str, Any]] = {}
# action_id -> run_id (the pending approval batch a /approve call targets)
_ACTIONS: Dict[str, str] = {}
# symbol -> {symbol, run_id, query, added_at}; the cumulative paper watchlist
# across runs (in-memory; swap for a store in production).
_PAPER_WATCHLIST: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_watchlist(run_id: str, symbols: list) -> None:
    query = _RUNS.get(run_id, {}).get("query")
    for sym in symbols or []:
        if sym not in _PAPER_WATCHLIST:
            _PAPER_WATCHLIST[sym] = {
                "symbol": sym,
                "run_id": run_id,
                "query": query,
                "added_at": _now_iso(),
            }

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

_PROGRESS_FIELDS = (
    "scan_results",
    "research_reports",
    "analyst_recommendations",
    "risk_assessments",
    "pending_actions",
    "approved_actions",
    "paper_watchlist",
)


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class AnalyzeRequest(BaseModel):
    query: str = Field(..., description="Natural-language research request.")


class ApproveRequest(BaseModel):
    action_id: str = Field(..., description="Pending approval id returned by /analyze.")
    approved: bool = Field(..., description="True to execute, False to reject.")


# --------------------------------------------------------------------------- #
# Config + serialization helpers
# --------------------------------------------------------------------------- #
def _trace_config(run_id: str, run_uuid: uuid.UUID) -> Dict[str, Any]:
    """Config that ties the LangGraph/LangSmith root run id to our run_id."""
    return {
        "configurable": {"thread_id": run_id},
        "run_id": run_uuid,
        "run_name": "alphaDesk",
        "tags": ["alphaDesk", "api"],
        "metadata": {"app_run_id": run_id},
    }


def _thread_config(run_id: str) -> Dict[str, Any]:
    """Thread-only config for resume / state reads (no new trace root)."""
    return {"configurable": {"thread_id": run_id}}


def _as_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return {}


def _state_dict(snapshot: Any) -> Dict[str, Any]:
    """JSON-serializable view of a graph state snapshot."""
    values = getattr(snapshot, "values", None) or {}
    try:
        return PortfolioState.model_validate(values).model_dump()
    except Exception:  # noqa: BLE001 - best-effort fallback
        return {k: (v.model_dump() if isinstance(v, BaseModel) else v) for k, v in values.items()}


def _summarize_update(node: str, payload: Any) -> Dict[str, Any]:
    """Compact per-node progress event (counts only — never raw payloads)."""
    data = _as_dict(payload)
    summary: Dict[str, Any] = {"node": node}
    for key in _PROGRESS_FIELDS:
        value = data.get(key)
        if isinstance(value, (list, dict)):
            summary[f"{key}_count"] = len(value)
    if data.get("rejection_reason"):
        summary["rejection_reason"] = data["rejection_reason"]
    return summary


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/")
async def root() -> Dict[str, str]:
    return {"service": "AlphaDesk", "version": "0.1.0"}


@app.post("/analyze")
async def analyze(body: AnalyzeRequest) -> StreamingResponse:
    """Run the research graph, streaming agent updates as Server-Sent Events.

    The stream ends with a ``complete`` event carrying the analyst
    recommendations and risk assessments. If anything passed risk, the run pauses
    at the human-in-the-loop gate and the event includes an ``action_id`` to pass
    to /approve.
    """
    run_uuid = uuid.uuid4()
    run_id = str(run_uuid)
    _RUNS[run_id] = {
        "run_uuid": run_uuid,
        "query": body.query,
        "status": "running",
        "action_id": None,
    }

    async def event_stream():
        config = _trace_config(run_id, run_uuid)
        yield _sse("start", {"run_id": run_id, "status": "running"})
        try:
            initial = PortfolioState(user_query=body.query)
            async for chunk in alphaDesk_graph.astream(initial, config, stream_mode="updates"):
                for node, payload in chunk.items():
                    if node.startswith("__"):  # skip interrupt/control markers
                        continue
                    yield _sse("update", _summarize_update(node, payload))

            snapshot = await alphaDesk_graph.aget_state(config)
            state = _state_dict(snapshot)
            awaiting = bool(getattr(snapshot, "next", None))

            action_id: Optional[str] = None
            if awaiting:
                status = "awaiting_approval"
                action_id = str(uuid.uuid4())
                _ACTIONS[action_id] = run_id
                _RUNS[run_id]["action_id"] = action_id
            elif state.get("rejection_reason"):
                status = "rejected"
            else:
                status = "completed"
            _RUNS[run_id]["status"] = status

            yield _sse(
                "complete",
                {
                    "run_id": run_id,
                    "status": status,
                    "awaiting_approval": awaiting,
                    "action_id": action_id,
                    "analyst_recommendations": state.get("analyst_recommendations", []),
                    "risk_assessments": state.get("risk_assessments", []),
                    "rejection_reason": state.get("rejection_reason"),
                },
            )
        except Exception as exc:  # noqa: BLE001 - surface error to the client
            _RUNS[run_id]["status"] = "error"
            _RUNS[run_id]["error"] = str(exc)
            yield _sse("error", {"run_id": run_id, "error": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


@app.post("/approve")
async def approve(body: ApproveRequest) -> Dict[str, Any]:
    """Resume a paused run after the human decision.

    approved=True  -> Execution stages PASS stocks into the paper watchlist and
                      finalizes them into approved_actions (placing real orders
                      only if a BrokerAdapter is configured).
    approved=False -> the staged batch is abandoned; nothing is added to the
                      paper watchlist. rejection_reason is recorded.
    """
    run_id = _ACTIONS.get(body.action_id) or (body.action_id if body.action_id in _RUNS else None)
    if run_id is None:
        raise HTTPException(status_code=404, detail="Unknown action_id")

    if body.approved:
        final = await resume_after_approval(thread_id=run_id, approved=True)
        _RUNS[run_id]["status"] = "completed"
        _record_watchlist(run_id, final.paper_watchlist)
        return {"run_id": run_id, "status": "completed", "state": final.model_dump()}

    # Rejected: record reason, do not resume execution (no paper-watchlist writes).
    config = _thread_config(run_id)
    await alphaDesk_graph.aupdate_state(
        config, {"human_approved": False, "rejection_reason": "Rejected by human."}
    )
    _RUNS[run_id]["status"] = "rejected"
    snapshot = await alphaDesk_graph.aget_state(config)
    return {"run_id": run_id, "status": "rejected", "state": _state_dict(snapshot)}


@app.get("/watchlist")
async def get_watchlist() -> Dict[str, Any]:
    """Return the cumulative paper watchlist (stocks approved across runs)."""
    items = sorted(
        _PAPER_WATCHLIST.values(), key=lambda x: x.get("added_at", ""), reverse=True
    )
    return {"count": len(items), "items": items}


# --------------------------------------------------------------------------- #
# AgentQuant Apex — Phase 3.1 / 3.2 (NEW)
# --------------------------------------------------------------------------- #
@app.get("/portfolio")
async def get_portfolio() -> Dict[str, Any]:
    """Live Dhan portfolio snapshot for the LivePortfolio frontend panel.

    Returns the most recent ``QuantState`` fields populated by the
    PortfolioSync node. When no run has synced yet (or no broker is
    configured), returns zeroed defaults with ``place_live_orders=False``
    so the frontend renders a benign empty state.
    """
    broker = load_broker()
    if broker is None:
        return {
            "available_margin": 0.0,
            "used_margin": 0.0,
            "current_holdings": [],
            "portfolio_synced_at": None,
            "place_live_orders": False,
            "regime_label": None,
            "regime_confidence": None,
            "swarm_consensus_score": None,
        }
    try:
        funds = float(await broker.get_funds() or 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("/portfolio: get_funds failed: %s", exc)
        funds = 0.0
    try:
        raw_holdings = await broker.get_holdings() or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("/portfolio: get_holdings failed: %s", exc)
        raw_holdings = []

    holdings = []
    for h in raw_holdings:
        try:
            sym = h.get("tradingSymbol") or h.get("symbol")
            qty = int(h.get("totalQty") or h.get("quantity") or 0)
            avg = float(h.get("avgCostPrice") or h.get("averagePrice") or 0.0)
            ltp = float(h.get("ltp") or h.get("lastTradedPrice") or 0.0)
            if not sym or qty <= 0 or avg <= 0 or ltp <= 0:
                continue
            invested = qty * avg
            current = qty * ltp
            pnl = current - invested
            pnl_pct = (pnl / invested) * 100.0 if invested else 0.0
            holdings.append({
                "symbol": sym,
                "security_id": str(h.get("securityId")) if h.get("securityId") else None,
                "quantity": qty,
                "average_price": round(avg, 2),
                "last_traded_price": round(ltp, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 3),
                "day_change_pct": float(h.get("dayChangePercentage") or 0.0),
            })
        except Exception:  # noqa: BLE001
            continue
    return {
        "available_margin": funds,
        "used_margin": round(sum(h["average_price"] * h["quantity"] for h in holdings), 2),
        "current_holdings": holdings,
        "portfolio_synced_at": _now_iso(),
        "place_live_orders": True,
        "regime_label": None,
        "regime_confidence": None,
        "swarm_consensus_score": None,
    }


@app.get("/orders/{run_id}")
async def get_orders_for_run(run_id: str) -> Dict[str, Any]:
    """Return the pending + executed orders for a specific run.

    Used by the ExecutionLogs panel to show the live order timeline.
    """
    config = _thread_config(run_id)
    snapshot = await alphaDesk_graph.aget_state(config)
    state = _state_dict(snapshot)
    return {
        "run_id": run_id,
        "pending_actions": state.get("pending_actions", []),
        "approved_actions": state.get("approved_actions", []),
        "executed_trades": state.get("executed_trades", []),
        "execution_history": state.get("execution_history", []),
    }


@app.delete("/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str) -> Dict[str, Any]:
    """Remove a symbol from the paper watchlist."""
    removed = _PAPER_WATCHLIST.pop(symbol, None) is not None
    return {"count": len(_PAPER_WATCHLIST), "symbol": symbol, "removed": removed}


@app.get("/status/{run_id}")
async def status(run_id: str) -> Dict[str, Any]:
    """Return the current state and status of a graph run."""
    record = _RUNS.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")

    snapshot = await alphaDesk_graph.aget_state(_thread_config(run_id))
    next_nodes = list(getattr(snapshot, "next", ()) or ())
    return {
        "run_id": run_id,
        "status": record["status"],
        "query": record.get("query"),
        "action_id": record.get("action_id"),
        "awaiting_approval": bool(next_nodes),
        "next": next_nodes,
        "state": _state_dict(snapshot),
    }


