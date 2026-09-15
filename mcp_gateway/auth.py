"""
Authentication & authorization for the MCP Gateway.

- Authentication: HS256 JWTs. The signing secret comes ONLY from the
  JWT_SECRET_KEY environment variable - never hard-coded. See .env.example.
- Authorization: a simple role -> allowed-tools map. Every MCP tool call is
  checked against this before it is allowed to reach mcp_server.

In a production deployment, JWT_SECRET_KEY would be a long random value
from a secrets manager, and roles/permissions would likely live in the
database rather than in code.
"""

import os
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is not set. Copy .env.example to .env and set a real "
        "secret - the gateway refuses to start with a hard-coded default."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# role -> set of MCP tool names that role may invoke
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "recruiter": {
        "search_candidates",
        "get_candidate",
        "list_jobs",
        "get_job",
        "match_candidates",
        "rank_candidates_tool",
        "shortlist_candidates",
        "get_shortlist",
    },
    "hiring_manager": {
        "search_candidates",
        "get_candidate",
        "list_jobs",
        "get_job",
        "get_shortlist",
    },
    "admin": "*",  # all tools, including create_job / create_candidate
}


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises JWTError on an invalid/expired token."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def is_authorized(role: str, tool_name: str) -> bool:
    allowed = ROLE_PERMISSIONS.get(role)
    if allowed is None:
        return False
    if allowed == "*":
        return True
    return tool_name in allowed
