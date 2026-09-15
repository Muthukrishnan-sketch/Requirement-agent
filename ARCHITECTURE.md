# Architecture

## Component diagram

See `docs/architecture-diagram.png` for the visual version presented in the
. Text form:

```
 ┌────────────────┐
 │ Recruiter (NL   │
 │ request, e.g.   │
 │ "top 5 Python   │
 │ devs, 2+ yrs")  │
 └────────┬────────┘
          │
          v
 ┌─────────────────────┐        Claude decides which tool(s) to call
 │ AI Recruitment Agent │──────────────────────────────────┐
 │ (ai_agent/agent.py)  │                                  │
 └────────┬─────────────┘                                  │
          │ HTTP (acts as the MCP Client)                  │
          v                                                 │
 ┌─────────────────────────────────────────┐                │
 │ MCP Gateway (mcp_gateway/gateway.py)     │<───────────────┘
 │  1. Authenticate (JWT, /token)           │
 │  2. Authorize (role -> allowed tools)    │
 │  3. Audit log every call                 │
 │  4. Forward to the real MCP server       │
 └────────┬──────────────────────────────────┘
          │ MCP protocol (Streamable HTTP)
          v
 ┌─────────────────────────────────────────┐
 │ MCP Server (mcp_server/server.py)        │
 │  search_candidates, get_candidate,       │
 │  list_jobs, get_job, create_job,         │
 │  match_candidates, rank_candidates_tool, │
 │  shortlist_candidates, get_shortlist     │
 └────────┬──────────────────────────────────┘
          │ plain Python calls
          v
 ┌─────────────────────────────────────────┐
 │ Backend Services                         │
 │  backend/crud.py    (data access)        │
 │  backend/matching.py (scoring/ranking)   │
 └────────┬──────────────────────────────────┘
          │ SQLAlchemy ORM
          v
 ┌─────────────────────────────────────────┐
 │ Database (SQLite for the demo;           │
 │ swap DATABASE_URL for Postgres/Supabase) │
 │  candidates, jobs, shortlists,           │
 │  shortlist_items, audit_logs             │
 └───────────────────────────────────────────┘
```

The same `backend/crud.py` and `backend/matching.py` also power a
conventional REST API (`backend/main.py`) for a future recruiter-facing
web UI — the MCP tools and the REST endpoints are two front doors onto one
shared business logic layer, so behavior never diverges between "a human
using the dashboard" and "the AI agent using MCP tools."

## Why a separate MCP Gateway instead of putting auth in the MCP server?

Keeping authentication/authorization/audit logging in a layer above the
MCP server means:

- The MCP server stays a clean, reusable tool provider — any properly
  authorized MCP client could use it, not just this one agent.
- Security policy (who can call what) lives in one place
  (`mcp_gateway/auth.py`) instead of being scattered across tool
  implementations.
- Every tool call — human or AI-driven — passes through the same
  audit trail, which is what "Security & Audit Logging" as a requirement
  is really asking for.

## Why a transparent scoring function instead of an LLM-based ranker?

`backend/matching.py` computes scores from skill overlap + experience fit
rather than asking an LLM to "just rank these candidates." This is
deliberate: recruiting decisions need to be explainable ("why is this
candidate #1?"), reproducible (the same inputs always give the same score),
and fast/cheap to run against hundreds of candidates. The AI agent still
does the natural-language understanding (parsing "top 5 Python devs, 2+
years" into `required_skills=["python"], min_experience=2.0, top_k=5`) and
the final summarization — but the actual scoring is deterministic.

## Data model

- `candidates` - profile, skills (JSON list), years of experience
- `jobs` - title, required skills, minimum experience, status
- `shortlists` / `shortlist_items` - a saved, ranked result set tied to a
  job and (optionally) the original recruiter query text
- `audit_logs` - actor, role, tool name, arguments, status
  (success/denied/error), latency, for every MCP tool call

## Tech stack

- **Backend**: Python, FastAPI, SQLAlchemy
- **Database**: SQLite (demo) / PostgreSQL (Supabase-compatible via
  `DATABASE_URL`)
- **MCP**: official `mcp` Python SDK (FastMCP, v1.x API), Streamable HTTP
  transport between the gateway and the MCP server
- **Auth**: JWT (python-jose, HS256), role-based authorization
- **AI Agent**: Anthropic Claude (tool-use / function-calling loop)
- **Testing**: pytest
