"""
Backend REST API - Candidate Management & Job Management.

This is the conventional HTTP API an HR portal/UI would call directly.
The MCP server (mcp_server/server.py) wraps the same crud/matching logic
for consumption by the AI agent - the two front ends share one source of
truth so behavior never diverges.

Run:
    uvicorn backend.main:app --port 8002 --reload
"""

import logging

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.db import get_db, init_db
from backend import crud
from backend.matching import rank_candidates as _rank_candidates
from backend.schemas import (
    CandidateCreate, CandidateOut, JobCreate, JobOut,
    MatchRequest, MatchResult, ShortlistOut,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recruitment-backend")

app = FastAPI(title="Recruitment Backend API", version="1.0.0")
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # demo only - restrict this in a real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


# ---------- centralized error handling ----------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.warning("Validation error on %s: %s", request.url, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request, exc):
    logger.warning("Integrity error on %s: %s", request.url, str(exc.orig))
    return JSONResponse(
        status_code=409,
        content={"detail": "A record with these unique fields already exists."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled error on %s", request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# ---------- Candidate Management ----------

@app.post("/candidates", response_model=CandidateOut, status_code=201)
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)):
    candidate = crud.create_candidate(db, payload.model_dump())
    return candidate


@app.get("/candidates/{candidate_id}", response_model=CandidateOut)
def read_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = crud.get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@app.get("/candidates", response_model=list[CandidateOut])
def search_candidates(skill: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_candidates(db, skill=skill, limit=limit)


# ---------- Job Management ----------

@app.post("/jobs", response_model=JobOut, status_code=201)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    return crud.create_job(db, payload.model_dump())


@app.get("/jobs/{job_id}", response_model=JobOut)
def read_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs", response_model=list[JobOut])
def read_jobs(status: str | None = "open", db: Session = Depends(get_db)):
    return crud.list_jobs(db, status=status)


# ---------- Matching & Shortlisting (also reachable via MCP tools) ----------

@app.post("/match", response_model=list[MatchResult])
def match(payload: MatchRequest, db: Session = Depends(get_db)):
    required_skills = payload.required_skills
    min_experience = payload.min_experience

    if payload.job_id:
        job = crud.get_job(db, payload.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        required_skills = required_skills or job.required_skills
        min_experience = min_experience or job.min_experience

    candidates = crud.list_candidates(db, limit=1000)
    ranked = _rank_candidates(candidates, required_skills, min_experience, payload.top_k)
    return [
        MatchResult(candidate=r["candidate"], score=r["score"], score_breakdown=r["breakdown"])
        for r in ranked
    ]


@app.get("/shortlists/{shortlist_id}", response_model=ShortlistOut)
def read_shortlist(shortlist_id: int, db: Session = Depends(get_db)):
    shortlist = crud.get_shortlist(db, shortlist_id)
    if not shortlist:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    return ShortlistOut(
        id=shortlist.id, job_id=shortlist.job_id, query_text=shortlist.query_text,
        created_by=shortlist.created_by, created_at=shortlist.created_at,
        items=[
            MatchResult(candidate=item.candidate, score=item.score,
                        score_breakdown=item.score_breakdown)
            for item in shortlist.items
        ],
    )


@app.get("/health")
def health():
    return {"status": "ok"}
