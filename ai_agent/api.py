"""
Thin HTTP wrapper around ai_agent.agent.run_agent(), so a browser-based
frontend can call the AI agent instead of only a terminal command.

This does NOT change the architecture - it's a new, separate entry point
alongside the CLI one. The agent still talks to the Gateway exactly the
same way; this file only adds an HTTP door in front of run_agent().

Run with:
    uvicorn ai_agent.api:app --port 8003

Requires the MCP Server (8001), Gateway (8000), and a running local Ollama
server to all be up, exactly like the CLI version.
"""

import sys
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_agent.agent import run_agent

app = FastAPI(title="AI Recruitment Agent API", version="1.0.0")

# Demo-only: allow any origin so a local static frontend file can call this
# freely. Restrict this to your real frontend's origin before any real
# deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    message: str


class AskResponse(BaseModel):
    response: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        answer = run_agent(req.message)
        return AskResponse(response=answer)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return AskResponse(response=f"Something went wrong: {type(e).__name__}: {e}")