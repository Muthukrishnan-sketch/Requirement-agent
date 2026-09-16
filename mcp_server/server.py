"""
MCP Server - exposes recruitment operations as MCP tools.

Each tool is a thin, validated wrapper around backend/crud.py and
backend/matching.py. This file has NO auth logic - authentication and
authorization live one layer up, in mcp_gateway/gateway.py. That separation
is deliberate: the MCP server should be usable by any properly-authorized
MCP client, and the gateway is what decides who counts as "properly
authorized".

Run standalone (stdio) for local testing:
    python -m mcp_server.server

Run over HTTP/SSE for the gateway to connect to:
    python -m mcp_server.server --http
"""

import argparse
import json

from mcp.server.fastmcp import FastMCP

from database.db import init_db, session_scope
from backend import crud
from backend.matching import rank_candidates
from backend.schemas import CandidateOut, JobOut

mcp = FastMCP("recruitment-mcp-server")


def _candidate_dict(c) -> dict:
    return json.loads(CandidateOut.model_validate(c).model_dump_json())


def _job_dict(j) -> dict:
    return json.loads(JobOut.model_validate(j).model_dump_json())


@mcp.tool()
def search_candidates(skill: str | None = None, limit: int = 20) -> list[dict]:
    """Search candidates, optionally filtered by a single required skill."""
    with session_scope() as db:
        candidates = crud.list_candidates(db, skill=skill, limit=limit)
        return [_candidate_dict(c) for c in candidates]


@mcp.tool()
def get_candidate(candidate_id: int) -> dict | None:
    """Fetch one candidate's full profile by id."""
    with session_scope() as db:
        c = crud.get_candidate(db, candidate_id)
        return _candidate_dict(c) if c else None


@mcp.tool()
def create_candidate(full_name: str, email: str, skills: list[str],
                      years_experience: float = 0.0, phone: str | None = None,
                      location: str | None = None, current_title: str | None = None,
                      resume_summary: str | None = None) -> dict:
    """Create a new candidate record. Admin-only (enforced at the gateway)."""
    with session_scope() as db:
        c = crud.create_candidate(db, dict(
            full_name=full_name, email=email, skills=skills,
            years_experience=years_experience, phone=phone, location=location,
            current_title=current_title, resume_summary=resume_summary,
        ))
        return _candidate_dict(c)


@mcp.tool()
def list_jobs(status: str | None = "open") -> list[dict]:
    """List job requisitions, optionally filtered by status (open/closed)."""
    with session_scope() as db:
        jobs = crud.list_jobs(db, status=status)
        return [_job_dict(j) for j in jobs]


@mcp.tool()
def get_job(job_id: int) -> dict | None:
    """Fetch one job requisition by id."""
    with session_scope() as db:
        j = crud.get_job(db, job_id)
        return _job_dict(j) if j else None


@mcp.tool()
def create_job(title: str, required_skills: list[str], min_experience: float = 0.0,
               department: str | None = None, description: str | None = None) -> dict:
    """Create a new job requisition. Admin-only (enforced at the gateway)."""
    with session_scope() as db:
        j = crud.create_job(db, dict(
            title=title, required_skills=required_skills, min_experience=min_experience,
            department=department, description=description,
        ))
        return _job_dict(j)


@mcp.tool()
def match_candidates(required_skills: list[str], min_experience: float = 0.0) -> list[dict]:
    """
    Score every candidate against a set of required skills and a minimum
    experience threshold. Returns unranked scores with a full breakdown -
    use rank_candidates if you just want the ordered top-K.
    """
    with session_scope() as db:
        candidates = crud.list_candidates(db, limit=1000)
        from backend.matching import match_candidates as _match
        results = _match(candidates, required_skills, min_experience)
        return [
            {"candidate": _candidate_dict(r["candidate"]), "score": r["score"],
             "score_breakdown": r["breakdown"]}
            for r in results
        ]


@mcp.tool()
def rank_candidates_tool(required_skills: list[str], min_experience: float = 0.0,
                          top_k: int = 5) -> list[dict]:
    """
    Score, sort, and return the top_k candidates for a set of required
    skills and a minimum years of experience. This is the core "find me
    the best N candidates" tool the AI agent uses.
    """
    with session_scope() as db:
        candidates = crud.list_candidates(db, limit=1000)
        results = rank_candidates(candidates, required_skills, min_experience, top_k)
        return [
            {"rank": r["rank"], "candidate": _candidate_dict(r["candidate"]),
             "score": r["score"], "score_breakdown": r["breakdown"]}
            for r in results
        ]


@mcp.tool()
def shortlist_candidates(job_id: int, candidate_ids_ranked: list[int],
                          scores: list[float], score_breakdowns: list[dict],
                          query_text: str | None = None,
                          created_by: str = "ai-agent") -> dict:
    """
    Persist a ranked shortlist for a job. candidate_ids_ranked, scores, and
    score_breakdowns must be parallel lists, already in rank order (best
    first) - typically produced by rank_candidates_tool.
    """
    ranked_matches = [
        {"candidate_id": cid, "rank": i + 1, "score": scores[i],
         "score_breakdown": score_breakdowns[i]}
        for i, cid in enumerate(candidate_ids_ranked)
    ]
    with session_scope() as db:
        shortlist = crud.create_shortlist(db, job_id, query_text, created_by, ranked_matches)
        return {
            "shortlist_id": shortlist.id,
            "job_id": shortlist.job_id,
            "created_at": shortlist.created_at.isoformat(),
            "num_candidates": len(ranked_matches),
        }


@mcp.tool()
def get_shortlist(shortlist_id: int) -> dict | None:
    """Retrieve a previously created shortlist with its ranked candidates."""
    with session_scope() as db:
        s = crud.get_shortlist(db, shortlist_id)
        if not s:
            return None
        return {
            "shortlist_id": s.id,
            "job_id": s.job_id,
            "query_text": s.query_text,
            "created_by": s.created_by,
            "created_at": s.created_at.isoformat(),
            "items": [
                {"rank": item.rank, "score": item.score,
                 "score_breakdown": item.score_breakdown,
                 "candidate": _candidate_dict(item.candidate)}
                for item in s.items
            ],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    init_db()

    if args.http:
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()

if __name__ == "__main__":
    main()
