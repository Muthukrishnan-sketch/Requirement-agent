"""Unit tests for backend/matching.py - the scoring logic has no DB or
network dependency, so these run instantly and deterministically."""

from types import SimpleNamespace

from backend.matching import score_candidate, rank_candidates


def make_candidate(skills, years_experience, name="Test Candidate"):
    return SimpleNamespace(full_name=name, skills=skills, years_experience=years_experience)


def test_perfect_skill_and_experience_match_scores_high():
    c = make_candidate(["python", "fastapi", "sql"], 5.0)
    result = score_candidate(c, ["python", "fastapi", "sql"], 2.0)
    assert result["score"] > 90


def test_missing_all_required_skills_scores_low():
    c = make_candidate(["java", "spring"], 5.0)
    result = score_candidate(c, ["python", "fastapi"], 2.0)
    assert result["score"] < 40
    assert set(result["breakdown"]["missing_skills"]) == {"python", "fastapi"}


def test_below_minimum_experience_is_penalized():
    c = make_candidate(["python"], 0.5)
    result = score_candidate(c, ["python"], 2.0)
    assert result["breakdown"]["experience_score"] < 50


def test_no_required_skills_does_not_penalize():
    c = make_candidate(["cobol"], 10.0)
    result = score_candidate(c, [], 0.0)
    assert result["breakdown"]["skill_score"] == 100.0


def test_rank_candidates_orders_best_first_and_respects_top_k():
    candidates = [
        make_candidate(["python", "fastapi"], 3.0, "Strong Match"),
        make_candidate(["python"], 1.0, "Partial Match"),
        make_candidate(["java"], 6.0, "No Skill Match"),
    ]
    ranked = rank_candidates(candidates, ["python", "fastapi"], 2.0, top_k=2)
    assert len(ranked) == 2
    assert ranked[0]["candidate"].full_name == "Strong Match"
    assert ranked[0]["rank"] == 1
    assert ranked[0]["score"] >= ranked[1]["score"]
