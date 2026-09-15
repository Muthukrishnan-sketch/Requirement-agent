"""
Integration tests for the FastAPI backend. Uses a throwaway in-memory
SQLite database (via dependency override) so tests never touch
recruitment.db and can run in any order.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import Base
from database.db import get_db
from backend.main import app

# StaticPool is required for an in-memory SQLite DB: without it, every new
# connection SQLAlchemy opens gets its own separate (empty) database.
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_create_and_fetch_candidate():
    resp = client.post("/candidates", json={
        "full_name": "Test Candidate", "email": "test.candidate@example.com",
        "skills": ["python", "fastapi"], "years_experience": 3.0,
    })
    assert resp.status_code == 201
    candidate_id = resp.json()["id"]

    resp = client.get(f"/candidates/{candidate_id}")
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Test Candidate"


def test_get_nonexistent_candidate_returns_404():
    resp = client.get("/candidates/9999")
    assert resp.status_code == 404


def test_duplicate_email_returns_409():
    payload = {"full_name": "A", "email": "dup@example.com", "skills": [], "years_experience": 1.0}
    assert client.post("/candidates", json=payload).status_code == 201
    resp = client.post("/candidates", json=payload)
    assert resp.status_code == 409


def test_invalid_candidate_payload_returns_422():
    resp = client.post("/candidates", json={"full_name": "No Email"})
    assert resp.status_code == 422


def test_match_endpoint_ranks_candidates():
    client.post("/candidates", json={
        "full_name": "Good Fit", "email": "good.fit@example.com",
        "skills": ["python", "fastapi"], "years_experience": 3.0,
    })
    client.post("/candidates", json={
        "full_name": "Bad Fit", "email": "bad.fit@example.com",
        "skills": ["cobol"], "years_experience": 1.0,
    })
    resp = client.post("/match", json={
        "required_skills": ["python", "fastapi"], "min_experience": 2.0, "top_k": 5,
    })
    assert resp.status_code == 200
    results = resp.json()
    assert results[0]["candidate"]["full_name"] == "Good Fit"
    assert results[0]["score"] > results[-1]["score"]


def test_job_management_crud():
    resp = client.post("/jobs", json={
        "title": "Backend Engineer", "required_skills": ["python"], "min_experience": 1.0,
    })
    assert resp.status_code == 201
    job_id = resp.json()["id"]

    resp = client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Backend Engineer"
