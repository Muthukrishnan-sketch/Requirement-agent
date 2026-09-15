# MCP Server & Gateway Documentation

## Overview

- **MCP Server** (`mcp_server/server.py`) exposes recruitment operations as
  MCP tools, over Streamable HTTP, on port `8001` by default
  (`python -m mcp_server.server --http --port 8001`). It has **no** auth of
  its own — it trusts whatever calls it, which is why it must never be
  exposed directly; only the gateway should be able to reach it.
- **MCP Gateway** (`mcp_gateway/gateway.py`) is the only thing that should
  ever call the MCP server. It's a normal FastAPI app on port `8000` that
  authenticates callers (JWT), authorizes them per-tool by role, logs every
  call to the `audit_logs` table, and only then opens an MCP client session
  to the real server and forwards the call.

## Authenticating with the Gateway

```
POST /token
Content-Type: application/x-www-form-urlencoded
username=recruiter1&password=<DEMO_RECRUITER_PASSWORD>
```
Response:
```json
{"access_token": "<jwt>", "token_type": "bearer", "role": "recruiter"}
```
Include the token on every subsequent call: `Authorization: Bearer <jwt>`.

## Calling a tool through the Gateway

```
POST /call_tool
Authorization: Bearer <jwt>
Content-Type: application/json

{"tool_name": "rank_candidates_tool",
 "arguments": {"required_skills": ["python", "fastapi"],
               "min_experience": 2.0, "top_k": 5}}
```
- `200` -> `{"tool_name": ..., "result": [...], "is_error": false}`
- `403` -> caller's role isn't permitted to call that tool
- `502` -> the MCP server itself errored (also audit-logged as `error`)

## Roles & permissions

Defined in `mcp_gateway/auth.py` (`ROLE_PERMISSIONS`):

| Role            | Allowed tools |
|-----------------|---------------|
| `recruiter`     | search_candidates, get_candidate, list_jobs, get_job, match_candidates, rank_candidates_tool, shortlist_candidates, get_shortlist |
| `hiring_manager`| search_candidates, get_candidate, list_jobs, get_job, get_shortlist |
| `admin`         | all tools, including create_candidate and create_job |

## MCP tools reference

| Tool | Arguments | Returns |
|---|---|---|
| `search_candidates` | `skill?: str`, `limit?: int=20` | list of candidates matching the skill |
| `get_candidate` | `candidate_id: int` | one candidate or null |
| `create_candidate` | `full_name, email, skills, years_experience?, phone?, location?, current_title?, resume_summary?` | the created candidate (admin only) |
| `list_jobs` | `status?: str="open"` | list of jobs |
| `get_job` | `job_id: int` | one job or null |
| `create_job` | `title, required_skills, min_experience?, department?, description?` | the created job (admin only) |
| `match_candidates` | `required_skills: list[str], min_experience?: float` | every candidate scored (unranked, unfiltered by top_k) |
| `rank_candidates_tool` | `required_skills: list[str], min_experience?: float, top_k?: int=5` | top_k candidates, sorted best-first, with `rank`, `score`, `score_breakdown` |
| `shortlist_candidates` | `job_id, candidate_ids_ranked, scores, score_breakdowns, query_text?, created_by?` | `{shortlist_id, job_id, created_at, num_candidates}` |
| `get_shortlist` | `shortlist_id: int` | the saved shortlist with all ranked items, or null |

## Audit log

### `GET /audit_logs` (admin only)
Returns the most recent tool calls:
```json
[{"timestamp": "...", "actor": "recruiter1", "role": "recruiter",
  "tool_name": "rank_candidates_tool", "status": "success",
  "latency_ms": 60.4, "detail": null}]
```
`status` is one of `success`, `denied` (failed authorization), or `error`
(the tool call itself raised an exception). Every call is logged regardless
of outcome — this is the "Security & Audit Logging" requirement.

## End-to-end example (manually driving the gateway, no AI agent)

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/token \
  -d "username=recruiter1&password=$DEMO_RECRUITER_PASSWORD" | jq -r .access_token)

curl -s -X POST http://127.0.0.1:8000/call_tool \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"tool_name":"rank_candidates_tool",
       "arguments":{"required_skills":["python","fastapi"],
                     "min_experience":2.0,"top_k":5}}'
```

For the full natural-language flow ("Find the top 5 Python developers...")
see `ai_agent/agent.py`, which wraps this exact HTTP flow behind a Claude
tool-use loop.
