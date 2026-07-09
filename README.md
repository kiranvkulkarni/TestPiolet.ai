# QA Task Assigner

A web app for **Samsung Android QA teams** to manage test tasks, track leave, view
timelines, and report progress — with a **built-in AI agent** (floating chat) that
assigns tasks, checks workload, updates statuses, and drafts plans in natural language,
powered by a **fully on-premises LLM** (Ollama / Samsung Gauss / Intel OpenVINO via an
OpenAI-compatible API).

**Stack:** FastAPI · SQLAlchemy 2.0 · SQLite/PostgreSQL · React 19 · Vite · TypeScript ·
Tailwind v4 · TanStack Query · Zustand · Radix UI · Recharts · gantt-task-react.

## Run it

```bash
# Backend  →  http://localhost:8000  (interactive docs at /docs)
cd backend
pip install -r requirements.txt
cp .env.example .env            # set SECRET_KEY; DATABASE_URL defaults to SQLite
python -m app.seed              # demo data
python run.py                   # or: uvicorn app.main:app --reload

# Frontend  →  http://localhost:5173  (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Default logins (from seed): manager `admin@qa.local` / `admin123`; testers
`<first-name>@qa.local` / `tester123` (e.g. `priya@qa.local`).

The AI agent is **off** until you set `AGENT_ENABLED=true` in `backend/.env` and have a
local LLM reachable at `LLM_BASE_URL` (e.g. `ollama serve` with `LLM_MODEL=qwen2.5:7b` —
a tool-calling-capable model is required; see the model-choice note in `docs/USER_GUIDE.md`).

## Where everything is

- **Complete feature guide (with examples)** → `docs/USER_GUIDE.md`
- **How to work on this repo** → `CLAUDE.md` (read it first, every session)
- Vision & USPs → `docs/PRODUCT_VISION.md` · Architecture → `docs/ARCHITECTURE.md`
- Schema & enums → `docs/DATA_MODEL.md` · API surface → `docs/API_MAP.md`
- AI agent & extension plan → `docs/AI_ASSISTANT.md`
- Conventions → `docs/CODING_STANDARDS.md` · UX invariants → `docs/UX_GUIDELINES.md`
- Decisions → `docs/adr/` · What to build next → `build-plan/ROADMAP.md` +
  ready-to-paste prompts in `build-plan/prompts/` (E0–E5)

## Keep it honest

The docs describe reality. When the code changes, update the matching doc (and the ADRs)
in the same PR — that's what keeps the context accurate over months.
