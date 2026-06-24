# AlphaDesk Agent Persona Explanations

> **Derived from graph analysis**: 541 nodes · 1044 edges · 40 communities · 105 source files · ~68K words
>
> **Graph outputs**: `../graphify-out/GRAPH_REPORT.md` · `../graphify-out/graph.html` · `../graphify-out/graph.json`

---

## What This Directory Contains

This directory contains **exam-focused persona explanations** for AI engineering certification. Each document is derived from:

1. **Graph community analysis** — which communities each persona belongs to and how they connect
2. **God node connections** — which critical system abstractions each persona touches
3. **Hyperedge relationships** — which multi-agent workflows each persona participates in
4. **Cross-community bridges** — how personas connect disparate parts of the system

---

## Persona Index

### Core AI Engineering Roles

| Persona | Graph Communities | God Nodes | Word Count | Focus |
|---------|------------------|-----------|------------|-------|
| [**AI Engineer**](ai-engineer.md) | AI Agent Personas (C3) · Performance Optimization (C20, 0.83 cohesion) · Knowledge Graph (C12) · RAG & Docs (C13) · Vector Search (C31) | PortfolioState (40 edges) · MCPAuthError (23 edges) | ~4,000 | LLM integration, RAG, agents, vector search, production systems |
| [**Backend Specialist**](backend-specialist.md) | Backend Financial Tools (C2) · API Endpoints (C4) · Database Architecture (C18) · DevOps (C19) | MCPAuthError (23 edges) · _call_mcp_tool() (15 edges) · StockDetailsResponse (18 edges) | ~3,000 | FastAPI, async, auth, databases, infrastructure |
| [**Frontend Specialist**](frontend-specialist.md) | Frontend Application (C1) · Frontend Dependencies (C6) · UI Components (C10) · TypeScript Config (C8) | compilerOptions (16 edges) · StockDetailsResponse (shared, 18 edges) | ~3,000 | React/Next.js, TypeScript, state management, performance |

---

## Graph Community Map

The following communities from the AlphaDesk knowledge graph are referenced throughout these persona explanations:

### High-Cohesion Communities (Most Critical)

| Community | Name | Cohesion | Nodes | Why It Matters |
|-----------|------|----------|-------|----------------|
| C20 | Performance Optimization | **0.83** | 4 | AI Engineer sits here — highest cohesion in the entire graph |
| C19 | DevOps & Infrastructure | 0.40 | 5 | Infrastructure Agent Ecosystem hyperedge (0.95) |
| C18 | Database Architecture | 0.29 | 5 | TopBar, WatchlistButton — frontend-backend data bridge |
| C15 | Agent Orchestration | 0.29 | 5 | Auth token management for MCP |
| C17 | Security & Compliance | 0.29 | 9 | RAG retriever with security context |
| C13 | RAG & Document Processing | 0.27 | 12 | ChromaDB PDF ingestion pipeline |
| C12 | Knowledge Graph Systems | 0.22 | 12 | LangGraph assembly, PortfolioState |
| C7 | Business Analysis Agents | 0.23 | 22 | Assumption Mapping, Backlog Grooming |
| C11 | Code Quality & Review | 0.15 | 14 | AI Writing Auditor, Code Reviewer |

### Largest Communities (By Node Count)

| Community | Name | Nodes | Key Members |
|-----------|------|-------|-------------|
| C0 | Data Analysis & Intelligence | 86 | analyst(), AnalystRecommendation, _build_prompt() |
| C1 | Frontend Application Layer | 51 | AgentStepCard, ApprovalModal, StageStatus |
| C2 | Backend Financial Tools | 42 | MCPAuthError, _call_mcp_tool(), IND Money auth |
| C3 | AI Agent Personas | 35 | All agent definitions — compliance, debugger, devops |
| C4 | API Endpoints & Routing | 29 | analyze(), approve(), get_watchlist() |
| C5 | Project & Product Management | 28 | Product Manager, Product Owner, Orchestrator |

---

## God Nodes (System-Critical Abstractions)

These nodes have the highest betweenness centrality — they are the **cross-community bridges**:

| Rank | Node | Edges | Communities Bridged |
|------|------|-------|---------------------|
| 1 | **PortfolioState** | 40 | Data Analysis · Agent Execution · API Routing · Knowledge Graph |
| 2 | **MCPAuthError** | 23 | Backend Financial Tools · Data Analysis · Agent Orchestration |
| 3 | **StockDetailsResponse** | 18 | API Endpoints · Frontend Application |
| 4 | **ResearchReport** | 17 | Data Analysis · Agent Execution |
| 5 | **ScanResult** | 16 | Security · Data Analysis |
| 6 | **AnalystRecommendation** | 16 | Data Analysis · Agent Execution |
| 7 | **_Base** | 16 | Backend Financial Tools · Data Analysis |
| 8 | **compilerOptions** | 16 | TypeScript Config · Frontend Dependencies |

---

## Hyperedges (Multi-Agent Workflows)

These group relationships reveal how personas collaborate:

| Hyperedge | Confidence | Members | Description |
|-----------|-----------|---------|-------------|
| **AlphaDesk Tech Stack** | 1.00 | requirements, lang_graph, fast_api, chroma_db, lang_chain_groq, alpha_desk_frontend, hitl_approval | Core technology dependencies |
| **Infrastructure Agent Ecosystem** | 0.95 | Cloud Architect, DB Admin, Deployment Engineer, DevOps, Docker Expert, Kubernetes Specialist, Platform Engineer, Security Engineer, SRE, Terraform Engineer | Full infrastructure team |
| **FastAPI Best Practice Concepts** | 0.95 | Project Structure, Async Routes, Pydantic Models, Dependency Injection, BaseSettings, Alembic, Ruff | Backend development standards |
| **Security Assessment Pipeline** | 0.95 | Orchestrator, Security Auditor, Penetration Tester, OWASP Top 10, Supply Chain Security | Security workflow |
| **Product Definition Pipeline** | 0.95 | Orchestrator, Product Manager, Product Owner, Project Planner, MoSCoW, User Stories | Product development workflow |
| **Content Quality Pipeline** | 0.85 | AI Writing Auditor, Content Quality Editor, Content Marketer | Content review workflow |
| **Product Validation and Growth** | 0.80 | Assumption Mapping, Growth Loops, Product Manager, UX Researcher | Validation cycle |
| **Agile Delivery Cluster** | 1.00 | Backlog Grooming, Scrum Master, Product Manager, Project Manager | Agile ceremonies |

---

## Surprising Connections (Cross-Cutting Insights)

These edges reveal non-obvious relationships that exam questions might probe:

| Source | Relation | Target | Type | Insight |
|--------|----------|--------|------|---------|
| StreamingResponse | uses | PortfolioState | INFERRED | Frontend streams partial results while maintaining shared state |
| database-architect | semantically_similar_to | database-administrator | INFERRED (0.85) | These roles share deep knowledge despite different filenames |
| _Base | connects | Data Analysis | INFERRED | Base model classes bridge backend and analysis communities |

---

## Exam Topic Coverage Matrix

| Exam Topic | Primary Persona | Graph Communities | Key Concepts |
|------------|----------------|-------------------|--------------|
| LLM Integration & Model Selection | AI Engineer | C3, C20 | GPT-5.2, Claude 4.6, routing, caching |
| Advanced RAG Systems | AI Engineer | C13, C31 | Chunking, hybrid search, reranking, GraphRAG |
| Agent Frameworks & Orchestration | AI Engineer | C12, C15 | LangGraph, StateGraph, checkpointers, HITL |
| Vector Search & Embeddings | AI Engineer | C31 | HNSW, cosine similarity, pgvector |
| API Design & Development | Backend Specialist | C4 | FastAPI, REST, OpenAPI, SSE |
| Authentication & Security | Backend Specialist | C2, C17 | JWT, MCPAuthError, OAuth, RBAC |
| Database Architecture | Backend Specialist | C18 | PostgreSQL, pgvector, ORM patterns |
| Async Processing | Backend Specialist | C4, C19 | async/await, background tasks, queues |
| React & Next.js Architecture | Frontend Specialist | C1 | Server Components, App Router, streaming |
| TypeScript & Type Safety | Frontend Specialist | C8, C10 | Strict mode, generics, Pydantic bridge |
| State Management | Frontend Specialist | C1, C10 | TanStack Query, Zustand, URL state |
| Performance Optimization | Frontend Specialist | C1, C20 | Core Web Vitals, code splitting, memoization |
| Accessibility | Frontend Specialist | C10 | WCAG 2.1, focus management, ARIA |

---

## How to Use These Explanations

1. **For Exam Prep**: Each persona includes a checklist of competencies. Verify you can answer each item.
2. **For System Understanding**: Read the Graph Community Map to understand how roles interact.
3. **For Architecture Decisions**: Reference the God Nodes and Hyperedges to see which abstractions connect which teams.
4. **For Cross-Functional Work**: Check the Cross-Community Integration sections to understand how your role connects to others.

---

## Graph Artifacts

- **Interactive Graph**: Open `../graphify-out/graph.html` in a browser
- **Full Report**: Read `../graphify-out/GRAPH_REPORT.md` for community details and suggested questions
- **Raw Data**: `../graphify-out/graph.json` contains the full NetworkX graph

---

*Generated from AlphaDesk codebase analysis on 2026-06-25 · 541 nodes · 1044 edges · 40 communities*
