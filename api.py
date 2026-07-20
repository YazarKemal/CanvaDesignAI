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


# ---------------------------------------------------------------------------
# Hard Canva system prompt — injected into every request so the pipeline
# always produces copy-paste-ready Canva Magic Media / Canva GPT output.
# ---------------------------------------------------------------------------
CANVA_SYSTEM_PREAMBLE = """\
[CANVA SYSTEM INSTRUCTION — STRICT MODE]
You are generating a design prompt for Canva. Follow these hard rules:

1. OUTPUT MUST be a single, self-contained image-generation prompt suitable for:
   - Canva Magic Media (primary target)
   - Canva GPT / DALL-E 3 (secondary)
   - Adobe Firefly (tertiary)

2. The prompt MUST include deliberate empty negative space — at least 20-30% of the
   composition reserved for the user to overlay text, logos, or UI elements in Canva.

3. Embed these Canva library keywords naturally in the prompt text:
   "flat vector illustration", "isolated element on transparent background",
   "clean composition", "minimalist"

4. NEVER put embedded text, words, letters, logos or watermarks in the image.
   The design must be a blank canvas ready for the user's own typography.

5. Aspect ratio MUST match the detected use-case:
   - Instagram/Square → 1:1 (1080×1080)
   - YouTube/Thumbnail → 16:9 (1920×1080)
   - TikTok/Reels → 9:16 (1080×1920)

6. Color palette: prefer on-trend, harmonious palettes suitable for social media.
   Default to warm, professional tones unless the user specifies otherwise.

7. Target Tool default: "Canva Magic Media". The prompt must be in English
   regardless of the user's input language — Canva's ML models perform best
   with English prompts.

END CANVA SYSTEM INSTRUCTION

User request: """


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    # Inject hard Canva system instructions before the user's message.
    augmented_message = CANVA_SYSTEM_PREAMBLE + request.message
    try:
        result = run_pipeline(augmented_message, max_attempts=request.max_attempts)
    except Exception as exc:  # surface engine/LLM failures as 502s
        raise HTTPException(status_code=502, detail=f"Pipeline failed: {exc}") from exc

    return ChatResponse(
        card=result.card,
        approved=result.approved,
        score=result.review.score,
        attempts=result.attempts,
        paste_text=render_for_assistant_paste(result.card),
    )
