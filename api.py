"""FastAPI backend for CaVDesign — the Canva Prompt Workbench.

Single-engine architecture: exposes POST /api/chat, which given a plain
design request runs the three-stage DeepSeek pipeline (Architect ->
Generator -> Reviewer) and returns a Canva automation card the Next.js
chat UI renders. Never chats, never asks a question — card only.

Run locally:
    uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.orchestrator import DEFAULT_MAX_ATTEMPTS, run_pipeline
from src.paste_render import render_for_assistant_paste

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
    paste_text: str


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
        paste_text=render_for_assistant_paste(result.card),
    )
