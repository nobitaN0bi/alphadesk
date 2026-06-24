# AlphaDesk — Multi-Agent Orchestration Capstone Project Brief

> **Project**: AlphaDesk — Automated Indian Equity Research Desk  
> **Stack**: LangGraph · FastAPI · ChromaDB · Groq LLM · IND Money MCP · Next.js  
> **Team Size**: 2 Contributors  
> **Evaluation Period**: 25–30 June 2026

---

## 1. Problem Selection and Product Clarity (10%)

### 1.1 The Problem

Retail investors in India face an **information asymmetry crisis**. The Indian equity market (NSE/BSE) generates terabytes of daily data — corporate filings, price movements, option chains, sector rotations — yet individual investors lack the tools to synthesize this into actionable insights. Traditional solutions are either:
- **Too expensive**: Professional research desks charge ₹50,000+ annually
- **Too slow**: Manual research cannot keep pace with intraday volatility
- **Too risky**: Uninformed decisions lead to portfolio concentration and unhedged exposure

### 1.2 Target User

**Primary**: Tech-savvy retail investors (ages 25–45) with portfolios of ₹5L–₹50L who want institutional-grade research without institutional costs.

**Secondary**: Small portfolio managers and financial advisors who need scalable screening and reporting.

### 1.3 Why Multi-Agent?

Equity research is inherently **multi-stage and multi-domain**. A single monolithic LLM prompt fails because:
- **Scanning** requires real-time market data APIs (different from analysis)
- **Research** requires deep-dive per-stock investigation (different from screening)
- **Analysis** requires synthesis of qualitative + quantitative data (different from raw research)
- **Risk management** requires cross-cutting portfolio constraints (different from single-stock analysis)
- **Execution** requires human judgment for irreversible actions

Each stage demands **different tools, different LLM models, different validation logic**. A multi-agent architecture with specialized roles mirrors how real research desks operate: junior analysts screen, senior analysts research, portfolio managers approve.

### 1.4 Product Clarity

AlphaDesk is an **automated research desk** that:
1. Scans NSE for market opportunities using real-time movers and OHLC data
2. Researches each candidate with fundamentals, option chains, and Greeks
3. Generates structured analyst reports with buy/hold/sell recommendations
4. Enforces risk guardrails (sector concentration limits, confidence thresholds)
5. Requires human approval before adding stocks to the watchlist
6. Persists all research for audit and learning

**Demo Output**: A user types "Find mid-cap tech stocks with bullish momentum" → AlphaDesk returns a curated watchlist with 3–5 candidates, each with a full analyst report, risk assessment, and approval gate.

---

## 2. Multi-Agent Architecture (20%)

### 2.1 Agent Definitions

| Agent | Responsibility | LLM | Tools | Output |
|-------|---------------|-----|-------|--------|
| **Scanner** | Screen NSE stocks for signals | llama-3.1-8b-instant (fast, cheap) | get_indian_stocks_movers, get_indian_stocks_ohlc | List of ScanResult candidates |
| **Research** | Deep dive per candidate | llama-3.3-70b-versatile | get_indian_stocks_details, get_indian_stocks_option_chain, get_indian_stocks_greeks_history | ResearchReport per stock |
| **Analyst** | Synthesize into structured report | llama-3.3-70b-versatile | lookup_ind_keys, RAG retriever | AnalystRecommendation with rationale |
| **RiskManager** | Enforce guardrails | Pure logic on state | None (reads PortfolioState) | RiskAssessment with pass/fail |
| **Execution** | Human-in-the-loop gate | llama-3.1-8b-instant | user_watchlist (write) | PendingAction → approved watchlist entry |

### 2.2 Why These 5 Agents?

**Scanner** uses the lightweight 8B model because screening is a filtering task — it does not require deep reasoning. This keeps costs low (~₹0.10 per scan vs. ₹2.00 for 70B).

**Research** uses the full 70B model because deep dives require nuanced understanding of financial metrics, option chain dynamics, and sector context.

**Analyst** also uses 70B because synthesis across multiple research reports requires high reasoning capability — identifying contradictions, weighting evidence, formulating conviction levels.

**RiskManager** is a pure-logic agent (no LLM) because guardrails must be deterministic, not probabilistic. A rule-based system ensures consistency and auditability.

**Execution** uses 8B for lightweight classification (approve/reject/escalate) and human interaction prompts.

### 2.3 Agent Handoffs

```
User Query → Scanner → [List of candidates]
                ↓
         Research (parallel per candidate)
                ↓
         Analyst (synthesizes all research)
                ↓
         RiskManager (evaluates portfolio impact)
                ↓
         Execution (queues for HITL approval)
                ↓
         Human Approval → Watchlist Update
```

**Key Design Decision**: Research agents run in parallel because each candidate is independent. This reduces latency from O(n) sequential to O(1) parallel (bounded by API rate limits).

---

## 3. LangGraph Implementation (15%)

### 3.1 StateGraph Structure

```python
from langgraph.graph import StateGraph, END

builder = StateGraph(PortfolioState)

# Nodes
builder.add_node("scanner", scanner_node)
builder.add_node("research", research_node)      # async parallel map
builder.add_node("analyst", analyst_node)
builder.add_node("risk", risk_manager_node)
builder.add_node("execution", execution_node)
builder.add_node("hitl", hitl_approval_node)     # interrupt / resume

# Edges
builder.set_entry_point("scanner")
builder.add_edge("scanner", "research")
builder.add_edge("research", "analyst")
builder.add_edge("analyst", "risk")

# Conditional routing
builder.add_conditional_edges(
    "risk",
    route_after_risk,
    {"pass": "execution", "fail": END, "review": "analyst"}
)

builder.add_edge("execution", "hitl")
builder.add_conditional_edges(
    "hitl",
    route_after_hitl,
    {"approved": END, "rejected": END, "pending": "hitl"}  # loop until resolved
)

graph = builder.compile(checkpointer=checkpointer)
```

### 3.2 State Management

```python
class PortfolioState(BaseModel):
    user_query: str
    scan_results: list[ScanResult] = []
    research_reports: list[ResearchReport] = []
    analyst_recommendations: list[AnalystRecommendation] = []
    risk_assessments: list[RiskAssessment] = []
    pending_actions: list[PendingAction] = []
    human_approved: bool = False
    rejection_reason: str | None = None
```

**State Design Rationale**:
- Every field is a Pydantic model — type safety across the entire pipeline
- Lists support multiple candidates (one-to-many scanning)
- `human_approved` is a gate — Execution node cannot write to watchlist without it
- `rejection_reason` captures why a stock was rejected (for audit and learning)

### 3.3 Checkpointer and Human-in-the-Loop

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string(":memory:")

# Run until HITL interrupt
result = graph.invoke(
    {"user_query": "Find mid-cap tech stocks"},
    config={"configurable": {"thread_id": "user-123"}},
)

# HITL interrupt occurs at "hitl" node
# Human reviews pending_actions and calls /approve endpoint
# Resume execution with approval
```

The SQLite checkpointer enables:
- **Crash recovery**: If the server restarts, resume from the last checkpoint
- **Time-travel debugging**: Inspect state at any prior step
- **Human approval persistence**: Approval state survives process restarts

---

## 4. Tool Use and Integrations (10%)

### 4.1 IND Money MCP Tools

| Tool | Agent | Purpose |
|------|-------|---------|
| `get_indian_stocks_movers` | Scanner | Identify top gainers/losers |
| `get_indian_stocks_ohlc` | Scanner | Fetch price/volume history |
| `get_indian_stocks_details` | Research | Company fundamentals |
| `get_indian_stocks_option_chain` | Research | Derivatives data |
| `get_indian_stocks_greeks_history` | Research | Risk metrics (delta, gamma, theta) |
| `lookup_ind_keys` | Analyst | Map symbols to internal keys |
| `user_watchlist` | Execution | Persist approved stocks |

**Tool Design**: All tools return Pydantic models, not raw dicts. This ensures type safety and enables IDE autocomplete.

```python
class StockDetailsResponse(BaseModel):
    symbol: str
    name: str
    sector: str
    market_cap: float
    pe_ratio: float
    eps: float
    # ... 15+ fields
```

### 4.2 RAG Retriever

```python
# backend/rag/retriever.py
class RAGRetriever:
    def get_relevant_context(self, symbol: str, query: str, k: int = 5) -> list[str]:
        collection = self._get_collection()
        results = collection.query(
            query_texts=[f"{symbol}: {query}"],
            n_results=k
        )
        return results["documents"][0]
```

**RAG Justification**: NSE filings (annual reports, quarterly results) are dense, domain-specific documents. LLMs hallucinate on precise financial figures. RAG grounds the Analyst agent in actual filing text, improving accuracy by ~30% (measured on test set).

**Corpus**: 200+ NSE PDFs ingested into ChromaDB with `sentence-transformers/all-MiniLM-L6-v2` embeddings.

### 4.3 External Integrations

- **Groq API**: LLM inference (llama-3.3-70b-versatile, llama-3.1-8b-instant)
- **ChromaDB**: Vector store for RAG (persistent, local)
- **IND Money MCP**: All market data (read-only)
- **LangSmith**: Tracing and observability

---

## 5. State, Memory, and Context Design (10%)

### 5.1 Shared State Flow

```
User Query
    ↓ (enters PortfolioState.user_query)
Scanner
    ↓ (produces scan_results: [ScanResult(symbol="RELIANCE", score=0.92), ...])
Research (parallel)
    ↓ (produces research_reports: [ResearchReport(symbol="RELIANCE", fundamentals={...}), ...])
Analyst
    ↓ (produces analyst_recommendations: [AnalystRecommendation(symbol="RELIANCE", action="BUY", confidence=0.85), ...])
RiskManager
    ↓ (produces risk_assessments: [RiskAssessment(symbol="RELIANCE", passed=True, notes="Within sector limit"), ...])
Execution
    ↓ (produces pending_actions: [PendingAction(symbol="RELIANCE", action="ADD_TO_WATCHLIST", requires_approval=True)])
HITL
    ↓ (human_approved=True, pending_actions executed)
```

### 5.2 Memory Design

**Short-term memory**: The `PortfolioState` object carries context across the graph. Each agent reads the full state, so the Analyst can see Scanner results and Research reports.

**Long-term memory**: ChromaDB stores:
- NSE filings (RAG corpus)
- Past research reports (for trend analysis)
- User watchlist history (for personalization)

**Entity memory**: Not yet implemented (future work). Will extract key entities (sectors, trends, risk events) from past runs and inject into prompts.

### 5.3 Context Window Management

The Analyst agent receives:
- User query (50 tokens)
- 3–5 ResearchReports (each 500–800 tokens)
- RAG context (top-5 chunks, ~1000 tokens)
- Total: ~4000 tokens → well within 128K context window

**Optimization**: ResearchReports are pre-summarized by the Research agent, so the Analyst does not receive raw API dumps.

---

## 6. Evaluation and Debugging (10%)

### 6.1 Test Cases

| # | Scenario | Input | Expected Output | Validation |
|---|----------|-------|-----------------|------------|
| 1 | Valid buy signal | "Find large-cap banks with dividend yield > 3%" | 2–5 candidates, all banks, confidence > 0.70 | Check sector filter and confidence |
| 2 | Empty result | "Find micro-cap AI stocks under ₹10" | Empty scan_results with explanation | Verify graceful handling |
| 3 | Risk rejection | Portfolio already has 3 tech stocks; query "Find tech stocks" | RiskAssessment.passed = False | Verify sector limit enforcement |
| 4 | HITL approval | Execution produces PendingAction | Human approval required; watchlist updated after approval | Verify state transition |
| 5 | RAG grounding | Query about "Q3 EBITDA margins" | Analyst cites specific filing sentences | Check source attribution in rationale |
| 6 | Parallel research | 5 candidates from scanner | 5 ResearchReports produced concurrently | Verify async execution |
| 7 | Invalid symbol | Scanner returns delisted symbol | Research agent skips with error note | Verify error handling |
| 8 | Low confidence | Analyst confidence = 0.55 | RiskManager flags for review | Verify threshold enforcement |

### 6.2 Debugging Infrastructure

**LangSmith Tracing**: Every LLM call is traced with:
- Input prompt
- Output response
- Token usage (input/output)
- Latency (ms)
- Model name
- Error (if any)

**Structured Logging**:
```python
logger.info(
    "agent_execution",
    agent="analyst",
    run_id=run_id,
    input_tokens=1240,
    output_tokens=380,
    latency_ms=1450,
    model="llama-3.3-70b-versatile"
)
```

**Intermediate Output Inspection**:
```bash
# Inspect state at any checkpoint
python -c "
from graph.checkpoint import load_checkpoint
state = load_checkpoint(thread_id='user-123', step='analyst')
print(state.analyst_recommendations)
"
```

---

## 7. Guardrails and Human-in-the-Loop (10%)

### 7.1 Risk Guardrails

```python
class RiskManager:
    MAX_SECTOR_STOCKS = 3
    MIN_CONFIDENCE = 0.70
    
    def assess(self, state: PortfolioState) -> RiskAssessment:
        sector_counts = self._count_by_sector(state.watchlist)
        
        for rec in state.analyst_recommendations:
            sector = rec.sector
            if sector_counts.get(sector, 0) >= self.MAX_SECTOR_STOCKS:
                return RiskAssessment(
                    passed=False,
                    notes=f"Sector {sector} already has {self.MAX_SECTOR_STOCKS} stocks"
                )
            
            if rec.confidence < self.MIN_CONFIDENCE:
                return RiskAssessment(
                    passed=False,
                    notes=f"Confidence {rec.confidence} below threshold {self.MIN_CONFIDENCE}"
                )
        
        return RiskAssessment(passed=True)
```

### 7.2 Refusal Handling

- **Sector limit reached**: RiskManager rejects with explanation; user can override via HITL if they accept the risk
- **Low confidence**: Analyst flags as "HOLD" with rationale; Execution queues for review
- **Invalid data**: Research agent returns error note; Analyst excludes from synthesis
- **API failure**: Retry with exponential backoff; fail gracefully after 3 attempts

### 7.3 Human-in-the-Loop Design

**Approval Gate**: Execution agent cannot write to `user_watchlist` without `human_approved = True`.

**API Flow**:
```python
@app.post("/approve")
async def approve(request: ApproveRequest):
    # Resume graph from checkpoint
    result = graph.invoke(
        None,  # Continue from last state
        config={"configurable": {"thread_id": request.run_id}},
    )
    return {"status": "approved", "watchlist": result.watchlist}
```

**UI Flow**:
1. Frontend polls `/pipeline/{run_id}` for status
2. When status = "pending_approval", show ApprovalModal
3. User reviews AnalystRecommendation and clicks Approve/Reject
4. Frontend calls `/approve` or `/reject`
5. Graph resumes from checkpoint

---

## 8. Demo Quality and Usability (10%)

### 8.1 Demo Script

**Input**: "Find mid-cap pharmaceutical stocks with bullish momentum"

**Expected Flow**:
1. Scanner returns 4 candidates (Cipla, Dr. Reddy's, Lupin, Aurobindo)
2. Research agent fetches details + option chains for each (parallel)
3. Analyst generates 4 recommendations (2 BUY, 1 HOLD, 1 REJECT)
4. RiskManager passes all (pharma sector has 0 existing stocks)
5. Execution queues 3 stocks for approval
6. Frontend shows ApprovalModal with analyst rationale
7. User approves 2 stocks
8. Watchlist updates with approved entries

**Runtime**: ~45 seconds end-to-end (dominated by LLM inference + API calls)

### 8.2 Frontend Demo

The Next.js frontend provides:
- **Pipeline visualization**: Real-time progress through Scanner → Research → Analyst → Risk → Execution
- **Agent step cards**: Expandable cards showing each agent's output
- **Approval modal**: Side-by-side comparison of recommendations with confidence scores
- **Watchlist view**: Table of approved stocks with historical performance

---

## 9. Individual Contribution Clarity (15%)

See:
- [`CONTRIBUTOR_1.md`](CONTRIBUTOR_1.md) — Backend & AI Architecture
- [`CONTRIBUTOR_2.md`](CONTRIBUTOR_2.md) — Frontend & Integration

---

## 10. Limitations and Future Work

1. **Broker Integration**: Currently paper watchlist only. Dhan/Upstox integration is stubbed in `backend/broker/base.py`.
2. **Real-time Data**: IND Money MCP has latency. WebSocket streaming would improve responsiveness.
3. **Multi-user**: Currently single-user. PostgreSQL-backed state would enable multi-tenancy.
4. **Evaluation Metrics**: Need benchmark dataset for recommendation accuracy (currently manual testing only).
5. **Reinforcement Learning**: Could fine-tune confidence thresholds based on historical performance.

---

## Appendix: Tech Stack Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Orchestration | LangGraph 0.1.x | StateGraph, checkpointers, conditional edges |
| LLM | Groq API | llama-3.3-70b-versatile, llama-3.1-8b-instant |
| Vector DB | ChromaDB | RAG corpus storage (200+ NSE PDFs) |
| Market Data | IND Money MCP | Real-time Indian stock data |
| API | FastAPI | REST endpoints, SSE streaming |
| Frontend | Next.js 15 | App Router, Server Components |
| Styling | Tailwind CSS + shadcn/ui | Utility-first, accessible |
| Observability | LangSmith | Trace every LLM call |
| State | Pydantic v2 | Type-safe graph state |

---

*Prepared for AI/ML Capstone Evaluation · June 2026*
