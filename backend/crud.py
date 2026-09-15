"""
Plain data-access functions. Both the FastAPI routes (backend/main.py) and
the MCP tools (mcp_server/server.py) call into this module, so business
logic lives in exactly one place.
"""

from sqlalchemy.orm import Session

from database.models import Candidate, Job, Shortlist, ShortlistItem


# ---------- Candidates ----------

def create_candidate(db: Session, data: dict) -> Candidate:
    candidate = Candidate(**data)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def get_candidate(db: Session, candidate_id: int) -> Candidate | None:
    return db.query(Candidate).filter(Candidate.id == candidate_id).first()


def list_candidates(db: Session, skill: str | None = None, limit: int = 100) -> list[Candidate]:
    q = db.query(Candidate)
    if skill:
        # SQLite/Postgres JSON contains check done in Python for portability
        candidates = q.all()
        skill = skill.lower()
        return [c for c in candidates if skill in [s.lower() for s in (c.skills or [])]][:limit]
    return q.limit(limit).all()


# ---------- Jobs ----------

def create_job(db: Session, data: dict) -> Job:
    job = Job(**data)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: int) -> Job | None:
    return db.query(Job).filter(Job.id == job_id).first()


def list_jobs(db: Session, status: str | None = None) -> list[Job]:
    q = db.query(Job)
    if status:
        q = q.filter(Job.status == status)
    return q.all()


# ---------- Shortlists ----------

def create_shortlist(db: Session, job_id: int, query_text: str | None,
                      created_by: str, ranked_matches: list[dict]) -> Shortlist:
    """
    ranked_matches: list of {"candidate_id": int, "rank": int, "score": float,
                              "score_breakdown": dict}
    """
    shortlist = Shortlist(job_id=job_id, query_text=query_text, created_by=created_by)
    db.add(shortlist)
    db.flush()  # get shortlist.id before adding items

    for m in ranked_matches:
        db.add(ShortlistItem(
            shortlist_id=shortlist.id,
            candidate_id=m["candidate_id"],
            rank=m["rank"],
            score=m["score"],
            score_breakdown=m["score_breakdown"],
        ))

    db.commit()
    db.refresh(shortlist)
    return shortlist


def get_shortlist(db: Session, shortlist_id: int) -> Shortlist | None:
    return db.query(Shortlist).filter(Shortlist.id == shortlist_id).first()
