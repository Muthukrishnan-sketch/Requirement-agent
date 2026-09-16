"""
AI Recruitment Agent - local Ollama edition.

Runs entirely against a LOCAL Ollama server (no external API key, no
candidate data ever leaves this machine):

    Recruiter Request -> AI Agent (Ollama / Llama 3.2, manual tool-call loop)
    -> MCP Client (MCPGatewayClient below) -> MCP Gateway -> MCP Tools
    -> Backend Services -> Database -> Matching -> Ranking -> Shortlisting
    -> Final AI Response

Unlike Gemini's automatic function calling, Ollama only tells us WHICH tool
it wants to call and with what arguments - it does not execute the call
itself. run_agent() below is a manual loop: send messages -> if the model
asks for a tool, actually call the matching Python function, feed the
result back as a "tool" message, and repeat until the model gives a final
text answer. Each tool function is still just a thin wrapper that calls the
MCP Gateway over HTTP, so the Gateway's auth/authz/audit-logging layer
applies exactly the same as before - the model never touches the database
directly.

Setup (one-time, on this machine):
    1. Install Ollama from https://ollama.com
    2. Run: ollama pull llama3.2
    3. Make sure the Ollama app/service is running (it runs a local server
       at http://localhost:11434 automatically once installed).

Usage:
    python -m ai_agent.agent "Find the top 5 Python developers with at
    least 2 years of experience for job 1 and shortlist them"

Requires:
    OLLAMA_MODEL        - defaults to "llama3.2"
    GATEWAY_URL         - default http://127.0.0.1:8000
    AGENT_USERNAME / AGENT_PASSWORD - demo credentials for the gateway's
                          /token endpoint (defaults to the "recruiter1" demo user)
"""

import json
import os
import sys

import httpx
import ollama

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000")
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "recruiter1")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "changeme")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

SYSTEM_PROMPT = """You are an AI recruitment assistant. You have a STRICT tool-call
budget - every tool call is expensive, so be efficient. Never explore or "browse" -
go straight to the right tool with the arguments you already have.

Tools available: get_job, list_jobs, search_candidates, rank_candidates_tool,
shortlist_candidates, get_shortlist.

CRITICAL - deciding which skills/experience to search for:
  - If the recruiter's message itself states a role or skills (e.g. "java
    developers", "data scientists", "python and fastapi"), you MUST use exactly
    those skills for rank_candidates_tool. This ALWAYS overrides a job's stored
    required_skills, even if a job id is also mentioned in the same message
    (the job id is only for recording which job the shortlist belongs to).
  - Only fall back to a job's own required_skills/min_experience (via get_job)
    when the recruiter does NOT state any skills themselves - e.g. "shortlist
    candidates for job 1" with no role or skills mentioned.
  - Never reuse skills from a previous request in this conversation for a new
    request that specifies different skills.

For any "find/rank/shortlist top N candidates" request, follow EXACTLY these steps,
in this order, and do not deviate:
  1. Decide the required_skills and min_experience using the CRITICAL rule above.
     Only call get_job if you need the job's stored skills per that rule.
     Do NOT call list_jobs to look for a job.
  2. Call rank_candidates_tool EXACTLY ONCE, passing those required_skills,
     min_experience, and the requested top_k (default 5 if not stated).
     This tool already does all scoring and filtering - trust its result
     completely, and keep ALL candidates it returns, not just the top one.
  3. NEVER call search_candidates to "explore" what skills exist, try alternate
     skill spellings, or double check rank_candidates_tool's output. It is
     forbidden to call search_candidates more than once per request, and only if
     the recruiter explicitly asked to search/browse candidates rather than rank
     them.
  4. If asked to shortlist AND a job_id is available, do NOT call rank_candidates_tool
     and shortlist_candidates separately - call rank_and_shortlist_candidates ONCE
     instead. It ranks and shortlists in a single atomic step and always includes
     every candidate, so skip step 2 entirely in this case and go straight to this tool.
  5. For EVERY candidate returned, in rank order, output EXACTLY this format -
     fill in the REAL values from the tool result, never paraphrase them away
     and never write a generic sentence like "100% matched skills" instead of
     the actual data:

     N. **<full_name>**
        - Score: <score>
        - Skills: <comma-separated list from candidate.skills>
        - Years Experience: <years_experience>
        - Current Title: <current_title>
        - Matched Skills: <matched_skills from score_breakdown>
        - Missing Skills: <missing_skills from score_breakdown, or "None">
        - Summary: <resume_summary, verbatim>

     Do not add commentary beyond this template. Do not omit any of these
     fields for any candidate. Never invent candidates, scores, or ids not
     returned by a tool.

Total tool calls for a typical request should be 2-3, never more than 5.

IMPORTANT ON ARGUMENT FORMATTING: when a tool parameter is a list (like
required_skills), pass it as a REAL JSON array, e.g. ["python", "fastapi"] -
never as a string containing that text.
"""


class MCPGatewayClient:
    """Thin HTTP client for the MCP Gateway - this IS the 'MCP Client' box
    in the architecture diagram, from the agent's point of view."""

    def __init__(self):
        self._client = httpx.Client(base_url=GATEWAY_URL, timeout=30.0)
        self._token = None

    def login(self):
        resp = self._client.post("/token", data={
            "username": AGENT_USERNAME, "password": AGENT_PASSWORD,
        })
        resp.raise_for_status()
        self._token = resp.json()["access_token"]

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if not self._token:
            self.login()
        resp = self._client.post(
            "/call_tool",
            json={"tool_name": tool_name, "arguments": arguments},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if resp.status_code == 403:
            return {"error": f"Not authorized to call {tool_name}: {resp.json()['detail']}"}
        resp.raise_for_status()
        payload = resp.json()

        # IMPORTANT: MCP tool results can come back as MULTIPLE content
        # blocks (e.g. one block per list item for a tool returning a
        # list), not always a single block. Reading only result[0] silently
        # truncates any multi-item tool result down to just its first
        # element - collect every block instead.
        parsed_blocks = []
        for block in payload.get("result", []):
            if block.get("type") == "text":
                try:
                    parsed_blocks.append(json.loads(block["text"]))
                except json.JSONDecodeError:
                    parsed_blocks.append(block["text"])

        if not parsed_blocks:
            return payload
        if len(parsed_blocks) == 1:
            # Single-object tools (get_job, get_shortlist, shortlist_candidates,
            # rank_and_shortlist_candidates) return exactly one block - keep
            # returning that object directly, unchanged behavior.
            return parsed_blocks[0]
        # Multiple blocks - e.g. rank_candidates_tool/search_candidates/list_jobs
        # split their list result into one block per item. Reassemble the
        # full list instead of dropping everything but the first item.
        return parsed_blocks


gateway = MCPGatewayClient()


def _coerce_list(value):
    """Local models (like Llama 3.2) sometimes double-encode list/dict
    arguments as a JSON string instead of a real list/dict, e.g. passing
    '["python"]' instead of ["python"]. This unwraps that case so tool
    calls don't fail silently on a formatting quirk."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        # Fallback: a single skill passed as a bare string, e.g. "python"
        return [value]
    return value


# ---------------------------------------------------------------------------
# Plain Python functions below = the tools Gemini can call automatically.
# Gemini reads each function's type hints and docstring to build its own
# schema - no manual JSON schema needed like the Claude version required.
# Each one just forwards the call to the Gateway and logs it to stderr so
# you can see, live, which tools the model chose to use.
# ---------------------------------------------------------------------------

def search_candidates(skill: str = "", limit: int = 20) -> dict:
    """Search candidates, optionally filtered by one required skill.

    Args:
        skill: A single skill to filter by, e.g. "python". Leave empty for no filter.
        limit: Maximum number of candidates to return.
    """
    print(f"  [agent] calling MCP tool: search_candidates(skill={skill!r}, limit={limit})", file=sys.stderr)
    return gateway.call_tool("search_candidates", {"skill": skill or None, "limit": limit})


def list_jobs(status: str = "open") -> dict:
    """List job requisitions, optionally filtered by status.

    Args:
        status: Job status to filter by, either "open" or "closed".
    """
    print(f"  [agent] calling MCP tool: list_jobs(status={status!r})", file=sys.stderr)
    return gateway.call_tool("list_jobs", {"status": status})


def get_job(job_id: int) -> dict:
    """Fetch one job requisition by its id.

    Args:
        job_id: The numeric id of the job.
    """
    print(f"  [agent] calling MCP tool: get_job(job_id={job_id})", file=sys.stderr)
    return gateway.call_tool("get_job", {"job_id": job_id})


def rank_candidates_tool(required_skills: list[str], min_experience: float = 0.0, top_k: int = 5) -> dict:
    """Score, sort, and return the top_k candidates for a set of required skills
    and a minimum years of experience. This is the main "find the best N
    candidates" tool.

    Args:
        required_skills: List of skill names the candidate should have, e.g. ["python", "fastapi"].
        min_experience: Minimum years of experience required.
        top_k: How many top candidates to return.
    """
    required_skills = _coerce_list(required_skills)
    # De-duplicate (case-insensitive) - local models sometimes repeat the
    # same skill several times in the list, which is harmless for scoring
    # but noisy in logs/prompts.
    required_skills = list(dict.fromkeys(s.lower() for s in required_skills))
    print(f"  [agent] calling MCP tool: rank_candidates_tool(required_skills={required_skills}, "
          f"min_experience={min_experience}, top_k={top_k})", file=sys.stderr)
    return gateway.call_tool("rank_candidates_tool", {
        "required_skills": required_skills, "min_experience": min_experience, "top_k": top_k,
    })


def shortlist_candidates(job_id: int, candidate_ids_ranked: list[int], scores: list[float],
                          score_breakdowns: list[dict], query_text: str = "") -> dict:
    """Persist a ranked shortlist for a job. candidate_ids_ranked, scores, and
    score_breakdowns must be parallel lists, already in rank order (best
    first) - typically produced by rank_candidates_tool.

    Args:
        job_id: The id of the job this shortlist is for.
        candidate_ids_ranked: Candidate ids in rank order, best first.
        scores: Score for each candidate, in the same order as candidate_ids_ranked.
        score_breakdowns: Score breakdown dict for each candidate, same order.
        query_text: The original recruiter request, for record-keeping.
    """
    print(f"  [agent] calling MCP tool: shortlist_candidates(job_id={job_id}, "
          f"candidate_ids_ranked={candidate_ids_ranked})", file=sys.stderr)
    return gateway.call_tool("shortlist_candidates", {
        "job_id": job_id, "candidate_ids_ranked": candidate_ids_ranked,
        "scores": scores, "score_breakdowns": score_breakdowns,
        "query_text": query_text, "created_by": "ai-agent",
    })


def get_shortlist(shortlist_id: int) -> dict:
    """Retrieve a previously created shortlist with its ranked candidates.

    Args:
        shortlist_id: The id of the shortlist to fetch.
    """
    print(f"  [agent] calling MCP tool: get_shortlist(shortlist_id={shortlist_id})", file=sys.stderr)
    return gateway.call_tool("get_shortlist", {"shortlist_id": shortlist_id})


def rank_and_shortlist_candidates(job_id: int, required_skills: list[str],
                                   min_experience: float = 0.0, top_k: int = 5,
                                   query_text: str = "") -> dict:
    """Rank candidates for a set of required skills and minimum experience, and
    immediately save ALL of the ranked results as a shortlist for a job - in one
    atomic step. This is the ONLY tool to use whenever asked to "find AND
    shortlist" candidates for a job - it guarantees every ranked candidate is
    included in the shortlist, in rank order, with no candidates dropped.
    Use rank_candidates_tool by itself only if the recruiter wants to see
    rankings WITHOUT saving a shortlist.

    Args:
        job_id: The id of the job this shortlist is for.
        required_skills: Skills the candidate should have, e.g. ["python", "fastapi"].
        min_experience: Minimum years of experience required.
        top_k: How many top candidates to rank and shortlist.
        query_text: The original recruiter request, for record-keeping.
    """
    required_skills = _coerce_list(required_skills)
    required_skills = list(dict.fromkeys(s.lower() for s in required_skills))
    print(f"  [agent] calling MCP tool: rank_and_shortlist_candidates(job_id={job_id}, "
          f"required_skills={required_skills}, min_experience={min_experience}, top_k={top_k})",
          file=sys.stderr)
    ranked = gateway.call_tool("rank_candidates_tool", {
        "required_skills": required_skills, "min_experience": min_experience, "top_k": top_k,
    })
    if isinstance(ranked, dict) and "error" in ranked:
        # A real error (auth, validation, etc.) - surface it, don't disguise
        # it as "no candidates matched".
        return {"ranked": None, "shortlist": None, "error": ranked["error"]}
    if not isinstance(ranked, list):
        return {"ranked": None, "shortlist": None,
                "error": f"Unexpected tool response, not a list: {ranked!r}"}
    if not ranked:
        return {"ranked": [], "shortlist": None,
                "note": "rank_candidates_tool genuinely returned zero candidates."}

    candidate_ids = [r["candidate"]["id"] for r in ranked]
    scores = [r["score"] for r in ranked]
    breakdowns = [r["score_breakdown"] for r in ranked]
    shortlist = gateway.call_tool("shortlist_candidates", {
        "job_id": job_id, "candidate_ids_ranked": candidate_ids,
        "scores": scores, "score_breakdowns": breakdowns,
        "query_text": query_text, "created_by": "ai-agent",
    })
    # Return the full ranked list too, so the model can summarize every
    # candidate by name/title, not just ids.
    return {"ranked": ranked, "shortlist": shortlist}


TOOLS = [search_candidates, list_jobs, get_job, rank_candidates_tool,
         shortlist_candidates, get_shortlist, rank_and_shortlist_candidates]


def run_agent(user_request: str, max_turns: int = 6) -> str:
    """Run the agent loop against a local Ollama server. Unlike the Gemini
    version, Ollama does NOT execute tool calls automatically - the model
    just tells us which tool it wants and with what arguments, and this loop
    is responsible for actually calling the function and feeding the result
    back, turn by turn, until the model gives a final text answer (or we hit
    max_turns as a safety limit)."""
    tool_map = {f.__name__: f for f in TOOLS}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_request},
    ]

    for _ in range(max_turns):
        response = ollama.chat(model=OLLAMA_MODEL, messages=messages, tools=TOOLS)
        msg = response.message
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": msg.tool_calls,
        })

        if not msg.tool_calls:
            return msg.content or "(no response)"

        for call in msg.tool_calls:
            name = call.function.name
            args = dict(call.function.arguments or {})
            func = tool_map.get(name)
            if func is None:
                result = {"error": f"Unknown tool: {name}"}
            else:
                try:
                    result = func(**args)
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result, default=str),
            })

    return ("Agent stopped after reaching the maximum number of tool-call "
            "turns without producing a final answer - this usually means "
            "it got stuck retrying. Check the printed tool calls above.")


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or (
        "Find the top 5 Python developers with at least 2 years of "
        "experience for job 1 and shortlist them."
    )
    print(f"Recruiter request: {query}\n")
    print(run_agent(query))

def call_tool(self, tool_name: str, arguments: dict) -> dict:
    if not self._token:
        self.login()
    resp = self._client.post(
        "/call_tool",
        json={"tool_name": tool_name, "arguments": arguments},
        headers={"Authorization": f"Bearer {self._token}"},
    )
    if resp.status_code == 403:
        return {"error": f"Not authorized to call {tool_name}: {resp.json()['detail']}"}

    # ADD THESE 3 LINES to see real errors:
    if not resp.ok:
        print(f"  [gateway error] {resp.status_code}: {resp.text}", file=sys.stderr)
        return {"error": f"Gateway returned {resp.status_code}: {resp.text}"}

    resp.raise_for_status()
    payload = resp.json()
    results = []
    for block in payload["result"]:
        if block.get("type") == "text":
            try:
                results.append(json.loads(block["text"]))
            except json.JSONDecodeError:
                results.append(block["text"])
    if not results:
        return payload
    if len(results) == 1:
        return results[0]
    return results