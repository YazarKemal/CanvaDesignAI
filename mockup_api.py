"""Standalone backend API for CaVDesign Mockup Director.

UI/UX is intentionally untouched. Run this service separately with:

    uvicorn mockup_api:app --reload --port 8001

The existing project can later call this endpoint without redesigning the UI.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv(override=True)

from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.mockup_engine import MockupEngineError, generate_mockup_set
from src.mockup_workflow import analyze_artwork, build_final_prompt, refine_strategy


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


async def _read_upload(file: UploadFile) -> bytes:
    """Validate a file upload's type/size and return its bytes (in memory)."""
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
    return image_bytes


@app.post("/api/mockup/workflow/analyze")
async def workflow_analyze(
    file: UploadFile = File(...),
    marketplace: str = Form("Etsy"),
    product_type_hint: str = Form(""),
    audience_hint: str = Form(""),
    creative_direction: str = Form(""),
) -> dict[str, Any]:
    """Step 1: analyse the artwork and ask clarifying questions.

    Returns asset_analysis, recommended directions, and 3-5 category-aware
    clarifying questions. Pass the full response back as ``analysis`` to the
    refine and generate steps to keep the workflow stateless.
    """
    image_bytes = await _read_upload(file)
    try:
        return analyze_artwork(
            image_bytes,
            file.content_type or "",
            marketplace=marketplace.strip() or "Etsy",
            product_type_hint=product_type_hint.strip(),
            audience_hint=audience_hint.strip(),
            creative_direction=creative_direction.strip(),
        )
    except MockupEngineError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/mockup/workflow/refine")
async def workflow_refine(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Step 2: refine the strategy from the selected direction + user answers."""
    analysis = payload.get("analysis")
    selected_direction = payload.get("selected_direction")
    answers = payload.get("answers") or {}
    listing_role = payload.get("listing_role", "hero")

    if not isinstance(analysis, dict):
        raise HTTPException(status_code=400, detail="Field 'analysis' must be an object.")
    if not isinstance(selected_direction, str) or not selected_direction:
        raise HTTPException(status_code=400, detail="Field 'selected_direction' is required.")

    try:
        return refine_strategy(analysis, selected_direction, answers, listing_role)
    except MockupEngineError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/mockup/workflow/generate")
async def workflow_generate(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Step 3: emit the final image-generation prompt for the chosen direction."""
    analysis = payload.get("analysis")
    selected_direction = payload.get("selected_direction")
    answers = payload.get("answers") or {}
    listing_role = payload.get("listing_role", "hero")

    if not isinstance(analysis, dict):
        raise HTTPException(status_code=400, detail="Field 'analysis' must be an object.")
    if not isinstance(selected_direction, str) or not selected_direction:
        raise HTTPException(status_code=400, detail="Field 'selected_direction' is required.")

    try:
        return build_final_prompt(analysis, selected_direction, listing_role, answers)
    except MockupEngineError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
