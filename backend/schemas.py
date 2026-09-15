"""Pydantic schemas used by the FastAPI backend and, indirectly, by the MCP tools."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class CandidateCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    location: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    years_experience: float = 0.0
    current_title: Optional[str] = None
    resume_summary: Optional[str] = None


class CandidateOut(CandidateCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class JobCreate(BaseModel):
    title: str
    department: Optional[str] = None
    required_skills: list[str] = Field(default_factory=list)
    min_experience: float = 0.0
    description: Optional[str] = None
    status: str = "open"


class JobOut(JobCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class MatchRequest(BaseModel):
    job_id: Optional[int] = None
    required_skills: list[str] = Field(default_factory=list)
    min_experience: float = 0.0
    top_k: int = 5


class MatchResult(BaseModel):
    candidate: CandidateOut
    score: float
    score_breakdown: dict


class ShortlistCreate(BaseModel):
    job_id: int
    candidate_ids: list[int]
    query_text: Optional[str] = None
    created_by: Optional[str] = "system"


class ShortlistOut(BaseModel):
    id: int
    job_id: int
    query_text: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    items: list[MatchResult]

    class Config:
        from_attributes = True
