# AI Recruitment MCP Agent

An end-to-end prototype where an AI agent takes a natural-language recruiter
request (*"Find the top 5 Python developers with at least 2 years of
experience and shortlist them"*), and — through an authenticated, audited
MCP tool layer — searches real candidate data, scores and ranks it, and
persists a shortlist back to the database.

## Workflow

```
Recruiter Request
   -> AI Recruitment Agent (Claude, tool-use)
   -> MCP Client (ai_agent/agent.py's gateway client)
   -> MCP Gateway (auth + role-based authorization + audit logging)
   -> MCP Tools (mcp_server/server.py)
   -> Backend Services (backend/crud.py, backend/matching.py)
   -> Database (SQLite by default; Postgres/Supabase-ready)
   -> Candidate Matching -> Ranking -> Shortlisting
   -> Final AI Response
```

See `ARCHITECTURE.md` / `docs/architecture-diagram.png` for the full diagram
and component responsibilities.

## Project layout

```
database/       SQLAlchemy models, engine/session setup, demo seed data
backend/        FastAPI REST API (Candidate & Job management), matching engine
mcp_server/     MCP server exposing recruitment tools (FastMCP)
mcp_gateway/    Auth (JWT), authorization (RBAC), audit logging, proxies to mcp_server
ai_agent/       Claude-powered agent that drives the whole workflow via the gateway
tests/          pytest suite - matching engine, backend API, auth/authz
docs/           API_DOCS.md, MCP_DOCS.md, architecture diagram
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in JWT_SECRET_KEY, demo passwords, ANTHROPIC_API_KEY
```

Generate a real secret for `JWT_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Seed the demo database (10 sample candidates, 2 open jobs):

```bash
python -m database.seed_data
```

## Running the full stack (3 terminals)

```bash
# 1. MCP server - exposes the recruitment tools
export $(cat .env | xargs)
python -m mcp_server.server --http --port 8001

# 2. MCP Gateway - auth/authz/audit in front of the MCP server
export $(cat .env | xargs)
uvicorn mcp_gateway.gateway:app --port 8000

# 3. Run the AI agent against a natural-language request
export $(cat .env | xargs)
python -m ai_agent.agent "Find the top 5 Python developers with at least 2 years of experience for job 1 and shortlist them"
```

(The plain Candidate/Job REST API in `backend/main.py` can also be run
standalone on another port — `uvicorn backend.main:app --port 8002` — for a
future HR-portal frontend; it shares the same database and matching logic.)

## Demo accounts (MCP Gateway)

| username    | password (set in .env) | role            | can call                                             |
|-------------|--------------------------|-----------------|-------------------------------------------------------|
| recruiter1  | DEMO_RECRUITER_PASSWORD  | recruiter       | search, rank, shortlist, view                         |
| manager1    | DEMO_MANAGER_PASSWORD    | hiring_manager  | search, view only                                     |
| admin1      | DEMO_ADMIN_PASSWORD      | admin           | everything, incl. create_candidate/create_job, audit log |

## Tests

```bash
pytest -q
```

17 tests covering the matching/ranking algorithm, the backend REST API
(CRUD, validation errors, duplicate-key handling), and JWT/RBAC logic.

## Security notes

- No API keys, passwords, or DB credentials are hard-coded anywhere in the
  code - everything comes from environment variables (see `.env.example`).
  The gateway refuses to start if `JWT_SECRET_KEY` is unset.
- Every MCP tool call is authenticated (JWT), authorized (role -> allowed
  tools, see `mcp_gateway/auth.py`), and audit-logged (`audit_logs` table)
  regardless of whether it succeeds, is denied, or errors.
- Input validation is enforced by Pydantic schemas at the REST API layer.

## Status / what's left

Core pipeline (DB -> matching -> MCP tools -> gateway auth/authz/audit ->
agent orchestration) is implemented and passing tests. Still to harden
before final delivery: a lightweight frontend for recruiters, Postgres
migration scripts (Alembic), and expanding the demo dataset.
