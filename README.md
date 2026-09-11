# AI Project Builder Agent

A full-stack, AI-powered application that turns a short project idea into a complete,
professional software blueprint. Enter something like *"Hospital Management System"* and the
system acts as a team of software architects — producing requirements analysis, architecture
diagrams, database design, API specifications, UI/UX planning, a development roadmap, testing
strategy, deployment assets, documentation and AI recommendations.

Built as a **multi-agent AI application** orchestrated with **LangGraph**.

---

## What it generates

| Section | Contents |
|---------|----------|
| Requirements Analysis | Problem statement, objectives, target audience, functional & non-functional requirements, technology recommendations, complexity analysis, time/team estimates, suggested improvements, risks |
| Architecture | High-level architecture, component diagram, data flow, service communication and deployment diagrams — rendered as Mermaid diagrams |
| Folder Structure | Production-ready monorepo layout (backend, frontend, database, tests, docs, docker) |
| Database Design | ERD, tables with columns/constraints/indexes, relationships, SQL DDL, migration scripts, seed data |
| API Specification | Endpoints with method, auth, request/response examples, validation rules and status codes |
| UI/UX Plan | Screen list, navigation flow, components, forms, tables, dashboard layout, colors, typography |
| Development Roadmap | Weekly milestones with tasks, hour estimates, critical path and team plan |
| Git Commit History | Realistic commit sequence for the project's development lifecycle |
| Testing Strategy | Unit, integration, API, security and performance tests, edge cases, test data, QA checklist |
| Deployment & DevOps | Dockerfile, docker-compose, environment variables, GitHub Actions, production guide, monitoring and logging strategy |
| Documentation | README, installation guide, API/architecture/database/deployment docs, contribution guide |
| AI Recommendations | Libraries, design patterns, security, performance, scalability, future features, risk analysis, cost optimization |

Every blueprint is **editable, exportable and stored per user** (save / edit / duplicate / delete / continue later).

### Export formats
Markdown · PDF · DOCX · JSON · ZIP (starter repository with docs, SQL schema, Docker assets and CI workflow)

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  Frontend — Next.js 15 / React 19 / TypeScript / Tailwind      │
│  shadcn-style UI · Mermaid rendering · JWT session             │
└──────────────┬─────────────────────────────────────────────────┘
               │ REST (JSON, Bearer token)
┌──────────────▼─────────────────────────────────────────────────┐
│  Backend — FastAPI / SQLAlchemy 2.0 / Pydantic v2              │
│                                                                │
│  Auth (JWT) · Projects CRUD · Statistics · Suggestions         │
│  Export service (md/pdf/docx/json/zip)                         │
│                                                                │
│  ┌────────────────── Orchestration layer ─────────────────┐    │
│  │  LangGraph StateGraph (multi-agent pipeline)            │    │
│  │  requirements → parallel agents → api → documentation   │    │
│  │  OpenAI-compatible LLM client (configurable provider)   │    │
│  │  + deterministic template engine (fallback / no-key)    │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ChromaDB project memory (optional) · SMTP (optional)           │
└──────────────┬─────────────────────────────────────────────────┘
               │
   ┌───────────▼───────────┐        ┌──────────────────────────┐
   │  PostgreSQL / SQLite  │        │  Docker + GitHub Actions │
   └───────────────────────┘        └──────────────────────────┘
```

### The AI agents

The pipeline runs as a LangGraph state machine. Each agent owns one blueprint section:

1. **Requirement Analysis Agent** — the foundation; everything else builds on it
2. **Architecture Agent**, **Folder Structure Agent**, **Database Agent**, **UI/UX Agent**, **Roadmap Agent**, **Git History Agent**, **Testing Agent**, **DevOps Agent**, **Recommendations Agent** — run in parallel after requirements
3. **API Design Agent** — runs after the database agent (it depends on the schema)
4. **Documentation Agent** — runs last, composing every section

The LLM layer is **provider-agnostic**: any OpenAI-compatible Chat Completions endpoint works
(OpenAI, Azure, Ollama, vLLM…). When no API key is configured — or an LLM call fails — a
**built-in template engine** produces the same complete blueprint deterministically, so the
application is fully functional out of the box and tests never depend on external APIs.

---

## Quick start

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3010
- Backend API + Swagger: http://localhost:8010/docs

### Option B — Local development

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m app                         # uses BACKEND_PORT (default 8010)
# — or pick any free port yourself —
# uvicorn app.main:app --port 8021    # http://localhost:8021/docs
#
# TIP: to run several projects side by side, add a BACKEND_PORT per
# project in backend/.env, e.g. BACKEND_PORT=8021, and set
# NEXT_PUBLIC_API_URL=http://localhost:8021/api/v1 in frontend/.env.local
```

**Frontend** (Node 20+):

```bash
cd frontend
npm install
cp .env.local.example .env.local     # set NEXT_PUBLIC_API_URL if needed
npm run dev                          # http://localhost:3010
```

**Configure AI** (optional — without this the template engine is used):

```bash
# in .env (backend root) — any OpenAI-compatible provider
# Pick a preset with LLM_PROVIDER; OPENAI_BASE_URL/OPENAI_MODEL override it.

# OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-5.5

# xAI Grok
LLM_PROVIDER=grok
OPENAI_API_KEY=xai-...
# OPENAI_BASE_URL=https://api.x.ai/v1
# OPENAI_MODEL=grok-4.5
```

---

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy connection string (PostgreSQL or SQLite) |
| `SECRET_KEY` | *(none)* | JWT signing key — **required in production** (≥32 random chars). Production refuses to start without it; in `DEBUG=true` a random per-process key is generated |
| `DEBUG` | `false` | Development mode: enables the dev-only reset-token fallback and random dev `SECRET_KEY`. Never set in production |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token lifetime |
| `LLM_PROVIDER` | `openai` | Provider preset: `openai` or `grok` |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | presets | LLM provider (any OpenAI-compatible API); URL/model override the preset |
| `LLM_TEMPERATURE` | `0.3` | Generation creativity |
| `CHROMA_ENABLED` / `CHROMA_PATH` | `false` | Semantic project memory (ChromaDB) |
| `SMTP_HOST/…` | empty | Password-reset email. Reset tokens are never returned through the API in production; in `DEBUG=true` (SMTP unavailable) a dev token is returned so local flows stay testable |
| `CORS_ORIGINS` | `http://localhost:3010` | Allowed browser origins (comma separated). **Required in production** — the backend refuses to start with the dev default or with `*` while credentials are in use |
| `RATE_LIMIT_ENABLED` | `true` | DB-backed fixed-window auth rate limiting (no Redis needed) |
| `RATE_LIMIT_LOGIN` / `RATE_LIMIT_LOGIN_WINDOW` | `10` / `900` | Login attempts per (IP, account) per window (seconds) |
| `RATE_LIMIT_REGISTER` / `RATE_LIMIT_REGISTER_WINDOW` | `5` / `3600` | Registrations per IP per window |
| `RATE_LIMIT_FORGOT` / `RATE_LIMIT_FORGOT_WINDOW` | `5` / `900` | Forgot-password requests per (IP, account) per window |
| `RATE_LIMIT_FORGOT_IP` | `20` | Forgot-password requests per IP per window (bulk reset-mail flooding) |
| `RATE_LIMIT_RESET` / `RATE_LIMIT_RESET_WINDOW` | `5` / `900` | Reset-password attempts per IP per window |
| `MAX_REQUEST_BODY_BYTES` | `2000000` | Request body size cap (oversized bodies get HTTP 413) |

---

## Development

### Backend

```bash
cd backend
ruff check app tests      # lint
pytest -q                 # 197+ tests: auth, projects, pipeline, exports, jobs, security
```

### Frontend

```bash
cd frontend
npm run lint
npm run test
npm run build
```

### CI

`.github/workflows/ci.yml` runs backend lint + tests, frontend lint + tests + build, and `docker compose config` validation on every push/PR.

---

## Project layout

```
.
├── backend/                  # FastAPI service
│   ├── app/
│   │   ├── api/              # routers: auth, projects, export
│   │   ├── core/             # security (JWT + bcrypt), email
│   │   ├── models/           # SQLAlchemy models (User, Project)
│   │   ├── schemas/          # Pydantic contracts
│   │   └── services/
│   │       ├── ai/           # agents.py (LangGraph graph), llm.py, prompts.py, templates.py
│   │       ├── export/       # markdown, json, zip, docx, pdf
│   │       ├── memory.py     # ChromaDB / fallback project memory
│   │       └── orchestrator.py
│   └── tests/                # pytest suite
├── frontend/                 # Next.js 15 client
│   └── src/
│       ├── app/              # routes (dashboard, wizard, blueprint, templates, …)
│       ├── components/       # UI kit, sidebar, mermaid, blueprint sections
│       └── lib/              # API client, auth context, types
├── .github/workflows/ci.yml
├── docker-compose.yml
└── .env.example
```

---

## Roadmap / future improvements

- Streaming (SSE) blueprint generation for live agent-by-agent updates
- Git diff-style comparison between blueprint versions
- Blueprint template marketplace and community sharing
- PDF/DOCX styling options and multi-language exports
- Team workspaces with shared projects and roles
- CLI export (generate a blueprint from the terminal)

## License

MIT
