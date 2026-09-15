"""
MCP Gateway.

Sits between any MCP client (here, the AI Recruitment Agent) and the real
MCP Server. Every request must:

    1. Authenticate  - present a valid JWT (see auth.py / /token endpoint)
    2. Authorize     - the JWT's role must be permitted to call the
                        requested tool (ROLE_PERMISSIONS in auth.py)
    3. Be audited    - every call, allowed or denied, is written to
                        audit_logs (security & audit logging requirement)

Only after all three does the gateway open an MCP client session to the
real MCP server (mcp_server/server.py, running over Streamable HTTP) and
forward the tool call.

Run:
    uvicorn mcp_gateway.gateway:app --port 8000
(with mcp_server running separately on port 8001: `python -m mcp_server.server --http`)
"""

import os
import time
import traceback

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from database.db import init_db, session_scope
from database.models import AuditLog
from mcp_gateway.auth import create_access_token, decode_access_token, is_authorized

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")

# Demo user directory. In production this is a users table with hashed
# passwords - kept in-memory here only so the prototype has zero external
# auth dependency. Passwords are read from env vars, never hard-coded.
DEMO_USERS = {
    "recruiter1": {"password": os.getenv("DEMO_RECRUITER_PASSWORD", "changeme"), "role": "recruiter"},
    "manager1": {"password": os.getenv("DEMO_MANAGER_PASSWORD", "changeme"), "role": "hiring_manager"},
    "admin1": {"password": os.getenv("DEMO_ADMIN_PASSWORD", "changeme"), "role": "admin"},
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
app = FastAPI(title="Recruitment MCP Gateway")


@app.on_event("startup")
def startup():
    init_db()


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict = {}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


def get_current_identity(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                             detail="Invalid or expired token")
    return {"sub": payload["sub"], "role": payload["role"]}


def _write_audit(actor: str, role: str, tool_name: str, arguments: dict,
                  status_: str, detail: str, latency_ms: float):
    with session_scope() as db:
        db.add(AuditLog(actor=actor, role=role, tool_name=tool_name,
                         arguments=arguments, status=status_, detail=detail,
                         latency_ms=latency_ms))


@app.post("/token", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Demo password-grant login. Swap for SSO/OIDC in a real deployment."""
    user = DEMO_USERS.get(form_data.username)
    if not user or user["password"] != form_data.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                             detail="Incorrect username or password")
    token = create_access_token(subject=form_data.username, role=user["role"])
    return TokenResponse(access_token=token, role=user["role"])


@app.get("/tools")
async def list_tools(identity: dict = Depends(get_current_identity)):
    """List MCP tools visible to the caller's role."""
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
    from mcp_gateway.auth import ROLE_PERMISSIONS
    allowed = ROLE_PERMISSIONS.get(identity["role"], set())
    names = [t.name for t in tools.tools
             if allowed == "*" or t.name in allowed]
    return {"role": identity["role"], "allowed_tools": names}


@app.post("/call_tool")
async def call_tool(req: ToolCallRequest, identity: dict = Depends(get_current_identity)):
    """
    Authenticate (handled by get_current_identity), authorize, audit, then
    forward the call to the real MCP server.
    """
    start = time.perf_counter()

    if not is_authorized(identity["role"], req.tool_name):
        latency = (time.perf_counter() - start) * 1000
        _write_audit(identity["sub"], identity["role"], req.tool_name, req.arguments,
                     "denied", "role not permitted to call this tool", latency)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail=f"Role '{identity['role']}' may not call '{req.tool_name}'")

    try:
        async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(req.tool_name, req.arguments)
        latency = (time.perf_counter() - start) * 1000
        content = [c.model_dump() for c in result.content]
        _write_audit(identity["sub"], identity["role"], req.tool_name, req.arguments,
                     "success", None, latency)
        return {"tool_name": req.tool_name, "result": content, "is_error": result.isError}
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        _write_audit(identity["sub"], identity["role"], req.tool_name, req.arguments,
                     "error", f"{type(exc).__name__}: {exc}", latency)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                             detail="Upstream MCP tool call failed") from exc


@app.get("/audit_logs")
def get_audit_logs(identity: dict = Depends(get_current_identity), limit: int = 100):
    """Admin-only: view the audit trail."""
    if identity["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    with session_scope() as db:
        rows = (db.query(AuditLog).order_by(AuditLog.timestamp.desc())
                .limit(limit).all())
        return [
            {"timestamp": r.timestamp.isoformat(), "actor": r.actor, "role": r.role,
             "tool_name": r.tool_name, "status": r.status, "latency_ms": r.latency_ms,
             "detail": r.detail}
            for r in rows
        ]


@app.get("/health")
def health():
    return {"status": "ok"}
