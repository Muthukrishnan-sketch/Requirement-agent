"""
Candidate matching & ranking engine.

This is a transparent, explainable scoring function rather than a black-box
model - important for a recruitment tool, where "why was this candidate
ranked #1" needs a real answer. It combines:

    - skill overlap (Jaccard-style overlap between required and candidate skills)
    - experience fit (meets/exceeds the minimum, with a mild bonus for more,
      but no reward for wildly over-qualified candidates)

Score is 0-100. The AI agent / MCP tool layer can call `rank_candidates`
directly; `match_candidates` is the lower-level per-candidate scorer.
"""

from database.models import Candidate


def _normalize_skills(skills: list[str]) -> set[str]:
    return {s.strip().lower() for s in skills if s and s.strip()}


def score_candidate(candidate: Candidate, required_skills: list[str],
                     min_experience: float) -> dict:
    """Returns {"score": float, "breakdown": dict} for one candidate."""
    required = _normalize_skills(required_skills)
    have = _normalize_skills(candidate.skills or [])

    if required:
        overlap = required & have
        skill_score = len(overlap) / len(required)
    else:
        overlap = set()
        skill_score = 1.0  # no specific skills required -> don't penalize

    # Experience score: 0 if below minimum, scales up to 1.0 at min_experience,
    # with a small capped bonus for extra years (diminishing returns after +3y).
    exp = candidate.years_experience or 0.0
    if min_experience <= 0:
        experience_score = 1.0
    elif exp < min_experience:
        # Partial credit for being close to the bar, but heavily penalized.
        experience_score = max(0.0, exp / min_experience) * 0.5
    else:
        bonus = min((exp - min_experience) / 3.0, 1.0) * 0.15
        experience_score = min(1.0, 0.85 + bonus)

    # Weighted combination: skills matter more than raw tenure.
    final = (skill_score * 0.7 + experience_score * 0.3) * 100

    breakdown = {
        "skill_score": round(skill_score * 100, 1),
        "experience_score": round(experience_score * 100, 1),
        "matched_skills": sorted(overlap),
        "missing_skills": sorted(required - have),
        "years_experience": exp,
        "final_score": round(final, 1),
    }
    return {"score": round(final, 1), "breakdown": breakdown}


def match_candidates(candidates: list[Candidate], required_skills: list[str],
                      min_experience: float, min_score: float = 0.0) -> list[dict]:
    """Score every candidate; filter out anyone below min_score."""
    results = []
    for c in candidates:
        result = score_candidate(c, required_skills, min_experience)
        if result["score"] >= min_score:
            results.append({"candidate": c, **result})
    return results


def rank_candidates(candidates: list[Candidate], required_skills: list[str],
                     min_experience: float, top_k: int = 5) -> list[dict]:
    """Score, sort descending by score, and return the top_k with a rank field."""
    scored = match_candidates(candidates, required_skills, min_experience)
    scored.sort(key=lambda r: r["score"], reverse=True)
    top = scored[:top_k]
    for i, r in enumerate(top, start=1):
        r["rank"] = i
    return top
