# AI Recruitment MCP Agent

An end-to-end prototype where an AI agent takes a natural-language recruiter
request (*"Find the top 5 Python developers with at least 2 years of
experience and shortlist them"*), and — through an authenticated, audited
MCP tool layer — searches real candidate data, scores and ranks it, and
persists a shortlist back to the database.

The agent runs entirely on a **local LLM (Ollama / Llama 3.2)** — no
external API key, and no candidate data ever leaves the machine it runs on.

## Workflow

```
Recruiter Request
   -> AI Recruitment Agent (Ollama / Llama 3.2, manual tool-call loop)
   -> MCP Client (ai_agent/agent.py's gateway client)
   -> MCP Gateway (auth + role-based authorization + audit logging)
   -> MCP Tools (mcp_server/server.py)
   -> Backend Services (backend/crud.py, backend/matching.py)
   -> Database (Postgres/Supabase; SQLite supported for local dev)
   -> Candidate Matching -> Ranking -> Shortlisting
   -> Final AI Response
```

A small FastAPI wrapper (`ai_agent/api.py`) also exposes the agent over
HTTP, so a browser-based frontend (`frnd/index.html`) can talk to it
instead of only a terminal command.

See `ARCHITECTURE.md` / `docs/architecture-diagram.png` for the full diagram
and component responsibilities.

## Project layout

```
database/       SQLAlchemy models, engine/session setup, demo seed data
backend/        FastAPI REST API (Candidate & Job management), matching engine
mcp_server/     MCP server exposing recruitment tools (FastMCP)
mcp_gateway/    Auth (JWT), authorization (RBAC), audit logging, proxies to mcp_server
ai_agent/       Local-LLM agent (agent.py) + HTTP wrapper (api.py) that drives
                the workflow via the gateway
frnd/           Recruiter-facing frontend (static HTML/JS) that talks to ai_agent/api.py
tests/          pytest suite - matching engine, backend API, auth/authz
docs/           API_DOCS.md, MCP_DOCS.md, architecture diagram
```

## Setup

```
python -m venv .venv && source .venv/bin/activate      # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env   # fill in JWT_SECRET_KEY, demo passwords, DATABASE_URL
```

Generate a real secret for `JWT_SECRET_KEY`:

```
python -c "import secrets; print(secrets.token_hex(32))"
```

Install Ollama and pull the model the agent uses:

```
# https://ollama.com - install for your OS, then:
ollama pull llama3.2
```

By default the project uses local SQLite. To use Postgres/Supabase instead,
set `DATABASE_URL` in `.env` to your connection string (see
`.env.example` for the format) and install the driver:

```
pip install psycopg2-binary
```

Seed the database (10 sample candidates, 2 open jobs):

```
python -m database.seed_data
```

## Running the full stack (4 terminals + Ollama)

```
# 0. Make sure Ollama's background server is running (it starts
#    automatically once installed; if not: ollama serve)

# 1. MCP server - exposes the recruitment tools
python -m mcp_server.server --http --port 8001

# 2. MCP Gateway - auth/authz/audit in front of the MCP server
uvicorn mcp_gateway.gateway:app --port 8000

# 3. Agent API - HTTP wrapper the frontend talks to
uvicorn ai_agent.api:app --port 8003

# 4. Or run the agent directly from the CLI instead of the API/frontend:
python -m ai_agent.agent "Find the top 5 Python developers with at least 2 years of experience for job 1 and shortlist them"
```

Then open `frnd/index.html` directly in a browser to use the recruiter
interface (it talks to the Agent API on port 8003).

(The plain Candidate/Job REST API in `backend/main.py` can also be run
standalone on another port — `uvicorn backend.main:app --port 8002` — it
shares the same database and matching logic.)

## Demo accounts (MCP Gateway)

| username   | password (set in .env)    | role            | can call                                                   |
| ---------- | ------------------------- | --------------- | ---------------------------------------------------------- |
| recruiter1 | DEMO_RECRUITER_PASSWORD   | recruiter       | search, rank, shortlist, view                              |
| manager1   | DEMO_MANAGER_PASSWORD     | hiring_manager  | search, view only                                          |
| admin1     | DEMO_ADMIN_PASSWORD       | admin           | everything, incl. create_candidate/create_job, audit log   |

## Tests

```
pytest -q
```

17 tests covering the matching/ranking algorithm, the backend REST API
(CRUD, validation errors, duplicate-key handling), and JWT/RBAC logic.

## Security & privacy notes

- No API keys, passwords, or DB credentials are hard-coded anywhere in the
  code - everything comes from environment variables (see `.env.example`).
  The gateway refuses to start if `JWT_SECRET_KEY` is unset.
- The AI agent runs on a local model (Ollama/Llama 3.2) - no candidate data
  is ever sent to a third-party AI API.
- Every MCP tool call is authenticated (JWT), authorized (role -> allowed
  tools, see `mcp_gateway/auth.py`), and audit-logged (`audit_logs` table)
  regardless of whether it succeeds, is denied, or errors.
- Input validation is enforced by Pydantic schemas at the REST API layer.

## Status / what's left

Core pipeline (DB -> matching -> MCP tools -> gateway auth/authz/audit ->
local-LLM agent orchestration -> recruiter frontend) is implemented and
passing tests. Still to harden: Alembic migration scripts for Postgres,
and expanding the demo dataset.