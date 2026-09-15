"""
SQLAlchemy ORM models for the AI Recruitment MCP system.

Tables:
    - candidates       : candidate profiles + parsed skills/experience
    - jobs              : open job requisitions
    - shortlists        : a saved shortlist produced by the matching engine
    - shortlist_items   : candidates belonging to a shortlist, with their score/rank
    - audit_logs        : every MCP tool invocation, who called it, and the result
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    phone = Column(String(30), nullable=True)
    location = Column(String(120), nullable=True)

    # Stored as JSON list, e.g. ["python", "fastapi", "sql"]
    skills = Column(JSON, default=list, nullable=False)

    years_experience = Column(Float, default=0.0, nullable=False)
    current_title = Column(String(150), nullable=True)
    resume_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    shortlist_items = relationship("ShortlistItem", back_populates="candidate")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(150), nullable=False)
    department = Column(String(120), nullable=True)

    # Stored as JSON list of required skills
    required_skills = Column(JSON, default=list, nullable=False)
    min_experience = Column(Float, default=0.0, nullable=False)

    description = Column(Text, nullable=True)
    status = Column(String(30), default="open", nullable=False)  # open | closed

    created_at = Column(DateTime, default=utcnow)

    shortlists = relationship("Shortlist", back_populates="job")


class Shortlist(Base):
    __tablename__ = "shortlists"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    query_text = Column(Text, nullable=True)  # original recruiter NL request
    created_by = Column(String(120), nullable=True)  # recruiter / agent user
    created_at = Column(DateTime, default=utcnow)

    job = relationship("Job", back_populates="shortlists")
    items = relationship(
        "ShortlistItem", back_populates="shortlist", order_by="ShortlistItem.rank"
    )


class ShortlistItem(Base):
    __tablename__ = "shortlist_items"

    id = Column(Integer, primary_key=True, index=True)
    shortlist_id = Column(Integer, ForeignKey("shortlists.id"), nullable=False)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    rank = Column(Integer, nullable=False)
    score = Column(Float, nullable=False)
    score_breakdown = Column(JSON, default=dict, nullable=False)

    shortlist = relationship("Shortlist", back_populates="items")
    candidate = relationship("Candidate", back_populates="shortlist_items")


class AuditLog(Base):
    """
    Security & audit trail. One row per MCP tool call that passes through
    the MCP Gateway - regardless of success or failure.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    actor = Column(String(120), nullable=False)  # subject from the JWT
    role = Column(String(30), nullable=False)
    tool_name = Column(String(120), nullable=False, index=True)
    arguments = Column(JSON, default=dict)
    status = Column(String(20), nullable=False)  # success | denied | error
    detail = Column(Text, nullable=True)
    latency_ms = Column(Float, nullable=True)
