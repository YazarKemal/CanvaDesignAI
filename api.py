"""FastAPI backend for CaVDesign — the Canva Prompt Workbench / Design Agency.

Single-engine architecture: exposes POST /api/chat, which given a plain
design request (and an optional brand profile) runs the three-stage
DeepSeek pipeline (Architect -> Generator -> Reviewer/Critic) and returns a
Canva automation card the Next.js chat UI renders. Never chats, never
asks a question — card only.

Also exposes GET /api/brands (available brand profiles for a picker) and
POST /api/adapt (on-demand Omni-Channel adaptation of an already-approved
card to other formats).

Run locally:
    uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv(override=True)

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.brand_profiles import BrandNotFoundError, list_brands, load_brand
from src.color_science import best_contrast_pair
from src.omni_channel import TARGET_FORMATS, UnknownFormatError, generate_omni_channel_set
from src.orchestrator import DEFAULT_MAX_ATTEMPTS, run_pipeline
from src.paste_render import render_for_assistant_paste
from src.schema import PromptValidationError
from src.style_presets import StyleNotFoundError, list_styles, load_style

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
    brand: str | None = Field(None, description="Brand profile slug (config/brands/<slug>.json).")
    style: str | None = Field(None, description="Elite style preset slug (config/styles/<slug>.json).")
    max_attempts: int = Field(DEFAULT_MAX_ATTEMPTS, ge=1, le=6)


class ChatResponse(BaseModel):
    card: dict[str, Any]
    approved: bool
    score: float
    attempts: int
    paste_text: str
    contrast_ratio: float
    text_zone: str


class BrandSummary(BaseModel):
    slug: str
    name: str


class BrandsResponse(BaseModel):
    brands: list[BrandSummary]


class StyleSummary(BaseModel):
    slug: str
    name: str
    description: str


class StylesResponse(BaseModel):
    styles: list[StyleSummary]


class AdaptRequest(BaseModel):
    card: dict[str, Any] = Field(..., description="An already-approved Canva card.")
    formats: list[str] = Field(..., min_length=1, description=f"Target formats: {sorted(TARGET_FORMATS)}")
    brand: str | None = None
    style: str | None = Field(None, description="Elite style preset slug (config/styles/<slug>.json).")


class AdaptVariant(BaseModel):
    card: dict[str, Any]
    paste_text: str
    contrast_ratio: float


class AdaptResponse(BaseModel):
    variants: dict[str, AdaptVariant]


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


@app.get("/api/brands", response_model=BrandsResponse)
def brands() -> BrandsResponse:
    return BrandsResponse(
        brands=[BrandSummary(slug=slug, name=load_brand(slug)["name"]) for slug in list_brands()]
    )


@app.get("/api/styles", response_model=StylesResponse)
def styles() -> StylesResponse:
    summaries = []
    for slug in list_styles():
        preset = load_style(slug)
        summaries.append(
            StyleSummary(slug=slug, name=preset["name"], description=preset.get("description", ""))
        )
    return StylesResponse(styles=summaries)


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    # Inject hard Canva system instructions before the user's message.
    augmented_message = CANVA_SYSTEM_PREAMBLE + request.message
    try:
        result = run_pipeline(
            augmented_message,
            brand=request.brand,
            style=request.style,
            max_attempts=request.max_attempts,
        )
    except (BrandNotFoundError, StyleNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # surface engine/LLM failures as 502s
        raise HTTPException(status_code=502, detail=f"Pipeline failed: {exc}") from exc

    _a, _b, ratio = best_contrast_pair(result.card["layer_typography_architecture"]["color_palette"])

    return ChatResponse(
        card=result.card,
        approved=result.approved,
        score=result.review.score,
        attempts=result.attempts,
        paste_text=render_for_assistant_paste(result.card),
        contrast_ratio=round(ratio, 1),
        text_zone=result.card["text_zone"],
    )


@app.post("/api/adapt", response_model=AdaptResponse)
def adapt(request: AdaptRequest) -> AdaptResponse:
    brand_profile = None
    style_preset = None
    try:
        if request.brand:
            brand_profile = load_brand(request.brand)
        if request.style:
            style_preset = load_style(request.style)
        variants = generate_omni_channel_set(
            request.card, request.formats, brand=brand_profile, style=style_preset
        )
    except (BrandNotFoundError, StyleNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnknownFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PromptValidationError as exc:
        raise HTTPException(status_code=502, detail=f"Adaptation failed: {exc}") from exc

    response_variants = {}
    for fmt, variant_card in variants.items():
        _a, _b, ratio = best_contrast_pair(variant_card["layer_typography_architecture"]["color_palette"])
        response_variants[fmt] = AdaptVariant(
            card=variant_card,
            paste_text=render_for_assistant_paste(variant_card),
            contrast_ratio=round(ratio, 1),
        )

    return AdaptResponse(variants=response_variants)
