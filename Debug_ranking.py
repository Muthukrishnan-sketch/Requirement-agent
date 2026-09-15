"""Standalone diagnostic - bypasses HTTP/Gateway/MCP entirely, calls the
exact same functions rank_candidates_tool calls, printing counts at every
step so we can see exactly where results get lost."""
import sys
sys.path.insert(0, ".")

from database.db import session_scope
from backend import crud
from backend.matching import rank_candidates, match_candidates, _normalize_skills

with session_scope() as db:
    candidates = crud.list_candidates(db, limit=1000)
    print(f"Step 1 - crud.list_candidates returned: {len(candidates)} candidates")
    for c in candidates:
        print(f"    id={c.id} name={c.full_name!r} skills={c.skills}")

    print()
    required_skills = ["python"]
    min_experience = 2
    top_k = 5

    print(f"Step 2 - calling match_candidates(required_skills={required_skills}, "
          f"min_experience={min_experience})")
    matched = match_candidates(candidates, required_skills, min_experience)
    print(f"    match_candidates returned: {len(matched)} results")
    for m in matched:
        print(f"    {m['candidate'].full_name}: score={m['score']}")

    print()
    print(f"Step 3 - calling rank_candidates(top_k={top_k})")
    ranked = rank_candidates(candidates, required_skills, min_experience, top_k)
    print(f"    rank_candidates returned: {len(ranked)} results")
    for r in ranked:
        print(f"    rank={r['rank']} {r['candidate'].full_name}: score={r['score']}")