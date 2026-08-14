"""Standalone backend API for CaVDesign Mockup Director.

UI/UX is intentionally untouched. Run this service separately with:

    uvicorn mockup_api:app --reload --port 8001

The existing project can later call this endpoint without redesigning the UI.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv(override=True)

from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.mockup_engine import MockupEngineError, generate_mockup_set


app = FastAPI(title="CaVDesign Mockup Director API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cavdesign-mockup-director"}


@app.get("/api/mockup/types")
def mockup_types() -> dict[str, Any]:
    return {
        "types": [
            {"id": "hero", "label": "Hero Mockup"},
            {"id": "lifestyle", "label": "Lifestyle Mockup"},
            {"id": "close_up", "label": "Close-up Mockup"},
            {"id": "scale", "label": "Scale Mockup"},
            {"id": "alternative_scene", "label": "Alternative Scene"},
            {"id": "clean_product", "label": "Clean Product Mockup"},
        ]
    }


@app.post("/api/mockup/analyze")
async def analyze_mockup(
    file: UploadFile = File(...),
    marketplace: str = Form("Etsy"),
    product_type_hint: str = Form(""),
    audience_hint: str = Form(""),
    creative_direction: str = Form(""),
) -> dict[str, Any]:
    """Analyse uploaded artwork and generate six listing-ready mockup prompts.

    The image is processed in memory and is not persisted to disk. OpenAI Vision
    performs the visual interpretation; the source colour palette is sampled
    locally from the actual pixels and is included in the response.
    """

    mime_type = file.content_type or ""
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{mime_type}'. "
                f"Accepted: {', '.join(sorted(ALLOWED_MIME_TYPES))}."
            ),
        )

    try:
        image_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {exc}") from exc

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum upload size is {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    try:
        return generate_mockup_set(
            image_bytes,
            mime_type,
            marketplace=marketplace.strip() or "Etsy",
            product_type_hint=product_type_hint.strip(),
            audience_hint=audience_hint.strip(),
            creative_direction=creative_direction.strip(),
        )
    except MockupEngineError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
