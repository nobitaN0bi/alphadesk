# Graph Report - .  (2026-06-25)

## Corpus Check
- 105 files · ~68,478 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 541 nodes · 1044 edges · 40 communities (21 shown, 19 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 188 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Data Analysis & Intelligence|Data Analysis & Intelligence]]
- [[_COMMUNITY_Frontend Application Layer|Frontend Application Layer]]
- [[_COMMUNITY_Backend Financial Tools|Backend Financial Tools]]
- [[_COMMUNITY_AI Agent Personas|AI Agent Personas]]
- [[_COMMUNITY_API Endpoints & Routing|API Endpoints & Routing]]
- [[_COMMUNITY_Project & Product Management|Project & Product Management]]
- [[_COMMUNITY_Frontend Dependencies|Frontend Dependencies]]
- [[_COMMUNITY_Business Analysis Agents|Business Analysis Agents]]
- [[_COMMUNITY_TypeScript Configuration|TypeScript Configuration]]
- [[_COMMUNITY_Agent Execution Engine|Agent Execution Engine]]
- [[_COMMUNITY_UI Components & Design|UI Components & Design]]
- [[_COMMUNITY_Code Quality & Review|Code Quality & Review]]
- [[_COMMUNITY_Knowledge Graph Systems|Knowledge Graph Systems]]
- [[_COMMUNITY_RAG & Document Processing|RAG & Document Processing]]
- [[_COMMUNITY_System Architecture|System Architecture]]
- [[_COMMUNITY_Agent Orchestration|Agent Orchestration]]
- [[_COMMUNITY_Testing & Validation|Testing & Validation]]
- [[_COMMUNITY_Security & Compliance|Security & Compliance]]
- [[_COMMUNITY_Database Architecture|Database Architecture]]
- [[_COMMUNITY_DevOps & Infrastructure|DevOps & Infrastructure]]
- [[_COMMUNITY_Performance Optimization|Performance Optimization]]
- [[_COMMUNITY_Mobile Development|Mobile Development]]
- [[_COMMUNITY_Game Development|Game Development]]
- [[_COMMUNITY_SEO & Marketing|SEO & Marketing]]
- [[_COMMUNITY_Documentation Systems|Documentation Systems]]
- [[_COMMUNITY_UIUX Design|UI/UX Design]]
- [[_COMMUNITY_Full-Stack Integration|Full-Stack Integration]]
- [[_COMMUNITY_FastAPI Patterns|FastAPI Patterns]]
- [[_COMMUNITY_Content Marketing|Content Marketing]]
- [[_COMMUNITY_Security Auditing|Security Auditing]]
- [[_COMMUNITY_Prompt Engineering|Prompt Engineering]]
- [[_COMMUNITY_Vector Search & Embeddings|Vector Search & Embeddings]]
- [[_COMMUNITY_Agent Memory Systems|Agent Memory Systems]]
- [[_COMMUNITY_Multimodal AI|Multimodal AI]]
- [[_COMMUNITY_AI Safety & Governance|AI Safety & Governance]]
- [[_COMMUNITY_Pipeline Orchestration|Pipeline Orchestration]]
- [[_COMMUNITY_Exploration & Discovery|Exploration & Discovery]]
- [[_COMMUNITY_Debugging Systems|Debugging Systems]]
- [[_COMMUNITY_Compliance Framework|Compliance Framework]]
- [[_COMMUNITY_Infrastructure Automation|Infrastructure Automation]]

## God Nodes (most connected - your core abstractions)
1. `PortfolioState` - 40 edges
2. `MCPAuthError` - 23 edges
3. `StockDetailsResponse` - 18 edges
4. `ResearchReport` - 17 edges
5. `ScanResult` - 16 edges
6. `AnalystRecommendation` - 16 edges
7. `_Base` - 16 edges
8. `compilerOptions` - 16 edges
9. `_call_mcp_tool()` - 15 edges
10. `Infrastructure Audit Report` - 15 edges

## Surprising Connections (you probably didn't know these)
- `StreamingResponse` --uses--> `PortfolioState`  [INFERRED]
  backend/api/main.py → backend/graph/state.py
- `PendingAction` --uses--> `PendingAction`  [INFERRED]
  backend/broker/base.py → backend/graph/state.py
- `object` --uses--> `PortfolioState`  [INFERRED]
  backend/graph/graph.py → backend/graph/state.py
- `bool` --uses--> `PortfolioState`  [INFERRED]
  backend/graph/graph.py → backend/graph/state.py
- `database-architect` --semantically_similar_to--> `database-administrator`  [INFERRED] [semantically similar]
  agents/database-architect.md → agents/infrastructure/database-administrator.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Agile Delivery Cluster** — business_backlog-grooming, business_scrum-master, business_product-manager, business_project-manager [EXTRACTED 1.00]
- **Content Quality Pipeline** — agents_ai-writing-auditor, business_content-quality-editor, business_content-marketer [INFERRED 0.85]
- **Product Validation and Growth Cycle** — business_assumption-mapping, business_growth-loops, business_product-manager, business_ux-researcher [INFERRED 0.80]
- **Infrastructure Agent Ecosystem** — agents_infrastructure_cloud_architect, agents_infrastructure_database_administrator, agents_infrastructure_deployment_engineer, agents_infrastructure_devops_engineer, agents_infrastructure_docker_expert, agents_infrastructure_kubernetes_specialist, agents_infrastructure_platform_engineer, agents_infrastructure_security_engineer, agents_infrastructure_sre_engineer, agents_infrastructure_terraform_engineer [EXTRACTED 0.95]
- **Sprint 1-2 Quick Wins** — agents_infrastructure_docker_expert, agents_infrastructure_database_administrator, agents_infrastructure_security_engineer, agents_infrastructure_terraform_engineer [EXTRACTED 1.00]
- **FastAPI Best Practice Concepts** — concept_fastapi_project_structure, concept_async_routes, concept_pydantic_models, concept_fastapi_dependency_injection, concept_pydantic_basesettings, concept_sqlalchemy_naming_conventions, concept_alembic_migrations, concept_ruff_linter [EXTRACTED 0.95]
- **Security Assessment Pipeline** — agents_orchestrator, agents_security_auditor, agents_penetration_tester, owasp_top_10, supply_chain_security [EXTRACTED 0.95]
- **Product Definition Pipeline** — agents_orchestrator, agents_product_manager, agents_product_owner, agents_project_planner, moscow_prioritization, user_story_format [EXTRACTED 0.95]
- **AlphaDesk Tech Stack** — requirements, lang_graph, fast_api, chroma_db, lang_chain_groq, alpha_desk_frontend, hitl_approval [EXTRACTED 1.00]

## Communities (40 total, 19 thin omitted)

### Community 0 - "Data Analysis & Intelligence"
Cohesion: 0.07
Nodes (80): analyst(), _AnalystOutput, _analyze_one(), _build_prompt(), _gather_context(), _get_llm(), Analyst agent — synthesizes research into structured recommendations.  Pure asyn, Structured LLM output mapped onto AnalystRecommendation. (+72 more)

### Community 1 - "Frontend Application Layer"
Cohesion: 0.06
Nodes (51): PIPELINE, SAMPLES, AgentStepCard(), AgentStepCardProps, META, StageStatus, ApprovalModal(), ApprovalModalProps (+43 more)

### Community 2 - "Backend Financial Tools"
Cohesion: 0.11
Nodes (42): Any, bool, int, str, Exception, MCPAuthError, OAuth token management for the IND Money MCP server.  The IND Money MCP authenti, Raised when a valid IND Money access token cannot be obtained. (+34 more)

### Community 3 - "AI Agent Personas"
Cohesion: 0.14
Nodes (35): compliance-auditor, content-marketer, debugger, devops-engineer, explorer-agent, frontend-specialist, fullstack-developer, cloud-architect (+27 more)

### Community 4 - "API Endpoints & Routing"
Cohesion: 0.14
Nodes (29): analyze(), approve(), ApproveRequest, _as_dict(), get_watchlist(), _now_iso(), FastAPI entrypoint for AlphaDesk.  Serves the LangGraph research desk over HTTP., Config that ties the LangGraph/LangSmith root run id to our run_id. (+21 more)

### Community 5 - "Project & Product Management"
Cohesion: 0.11
Nodes (28): Acceptance Criteria, Agent Boundary Enforcement, Mobile Developer, Orchestrator, Penetration Tester, Performance Optimizer, Product Manager, Product Owner (+20 more)

### Community 6 - "Frontend Dependencies"
Cohesion: 0.07
Nodes (27): dependencies, class-variance-authority, clsx, lucide-react, next, @radix-ui/react-dialog, @radix-ui/react-slot, react (+19 more)

### Community 7 - "Business Analysis Agents"
Cohesion: 0.23
Nodes (22): Assumption Mapping, Backlog Grooming, Business Analyst, Content Marketer, Customer Success Manager, Growth Loops, Legal Advisor, License Engineer (+14 more)

### Community 8 - "TypeScript Configuration"
Cohesion: 0.10
Nodes (19): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+11 more)

### Community 9 - "Agent Execution Engine"
Cohesion: 0.15
Nodes (16): ABC, execution(), _process_approved(), Execution agent — paper watchlist + human-in-the-loop gate.  IMPORTANT: the IND, Phase 1: queue PASS stocks for approval and add them to the paper watchlist., Phase 2: human approved -> place orders if a broker exists, else persist., Stage PASS stocks, then finalize them once a human has approved.      The graph, _stage_pending() (+8 more)

### Community 10 - "UI Components & Design"
Cohesion: 0.11
Nodes (17): aliases, components, hooks, lib, ui, utils, iconLibrary, rsc (+9 more)

### Community 11 - "Code Quality & Review"
Cohesion: 0.15
Nodes (14): AI Writing Auditor, Backend Specialist, Code Archaeologist, Code Reviewer, Content Quality Editor, WordPress Master, AI Writing Pattern Detection, Code Best Practices (DRY/KISS/YAGNI) (+6 more)

### Community 12 - "Knowledge Graph Systems"
Cohesion: 0.22
Nodes (12): bool, object, PortfolioState, str, _as_state(), LangGraph assembly for AlphaDesk.  Wires the five agent nodes into a single Stat, Route to execution if anything passed risk, otherwise end the run., Run the research desk for ``user_query`` and return the resulting state.      Wi (+4 more)

### Community 13 - "RAG & Document Processing"
Cohesion: 0.27
Nodes (12): int, str, Path, _get_collection(), ingest(), _iter_pdf_pages(), main(), RAG ingestion — load NSE PDFs into ChromaDB.  Reads every PDF under ``data/nse_d (+4 more)

### Community 14 - "System Architecture"
Cohesion: 0.18
Nodes (11): AlphaDesk Frontend, Broker Integration README, BrokerAdapter, ChromaDB, FastAPI, 5-Stage Analysis Pipeline, AlphaDesk Frontend README, Human-in-the-Loop Approval (+3 more)

### Community 15 - "Agent Orchestration"
Cohesion: 0.29
Nodes (5): str, _Auth, get_access_token(), Return a valid IND Money bearer token, refreshing if needed., Bootstrap from an existing Claude Code `indmoney` OAuth login.

### Community 16 - "Testing & Validation"
Cohesion: 0.22
Nodes (10): database-architect, FastAPI Best Practices, Alembic Migrations, Async Routes (FastAPI), FastAPI Dependency Injection, FastAPI Project Structure, Pydantic BaseSettings, Pydantic Models (+2 more)

### Community 17 - "Security & Compliance"
Cohesion: 0.29
Nodes (9): int, str, _get_collection(), get_relevant_context(), RAG retriever — semantic search over the ``nse_filings`` ChromaDB collection.  C, Lazily open the persistent collection; cache it, tolerate any failure., Return the top ``k`` filing chunks relevant to ``symbol`` + ``query``.      Args, Backward-compatible symbol-less retrieval; delegates to get_relevant_context. (+1 more)

### Community 18 - "Database Architecture"
Cohesion: 0.29
Nodes (5): inter, metadata, mono, TopBar(), WatchlistButton()

### Community 19 - "DevOps & Infrastructure"
Cohesion: 0.40
Nodes (5): Easing Blueprint, GPU Acceleration, prefers-reduced-motion, Spring Animation, Web Animation Designer

### Community 20 - "Performance Optimization"
Cohesion: 0.83
Nodes (4): AI Engineer, Agent Frameworks and Orchestration, Advanced RAG Systems, Vector Search and Embeddings

## Ambiguous Edges - Review These
- `Backend Specialist` → `Code Reviewer`  [AMBIGUOUS]
  agents/code-reveiw.md · relation: references

## Knowledge Gaps
- **129 isolated node(s):** `@opencode-ai/plugin`, `inter`, `mono`, `metadata`, `SAMPLES` (+124 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Backend Specialist` and `Code Reviewer`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `PortfolioState` connect `Data Analysis & Intelligence` to `Agent Execution Engine`, `API Endpoints & Routing`, `Knowledge Graph Systems`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `MCPAuthError` connect `Backend Financial Tools` to `Data Analysis & Intelligence`, `Agent Orchestration`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Why does `_Base` connect `Backend Financial Tools` to `Data Analysis & Intelligence`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Are the 37 inferred relationships involving `PortfolioState` (e.g. with `_AnalystOutput` and `_RiskNote`) actually correct?**
  _`PortfolioState` has 37 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `MCPAuthError` (e.g. with `Any` and `bool`) actually correct?**
  _`MCPAuthError` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `StockDetailsResponse` (e.g. with `_Candidate` and `_Intent`) actually correct?**
  _`StockDetailsResponse` has 14 INFERRED edges - model-reasoned connections that need verification._