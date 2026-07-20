"""FastAPI backend for CaVDesign — the Canva Prompt Workbench.

Exposes POST /api/chat: given a plain design request, runs the three-stage
pipeline (DeepSeek Architect -> Claude Generator -> DeepSeek Reviewer) and
returns a prompt card the Next.js chat UI renders.

Run locally:
    uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.orchestrator import DEFAULT_MAX_ATTEMPTS, run_pipeline

app = FastAPI(title="CaVDesign API", version="1.0.0")

# The Next.js dev server (or its /api/chat proxy) calls this service.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's plain design request.")
    max_attempts: int = Field(DEFAULT_MAX_ATTEMPTS, ge=1, le=6)


class ChatResponse(BaseModel):
    card: dict[str, Any]
    approved: bool
    score: float
    attempts: int


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = run_pipeline(request.message, max_attempts=request.max_attempts)
    except Exception as exc:  # surface engine/LLM failures as 502s
        raise HTTPException(status_code=502, detail=f"Pipeline failed: {exc}") from exc

    return ChatResponse(
        card=result.card,
        approved=result.approved,
        score=result.review.score,
        attempts=result.attempts,
    )
