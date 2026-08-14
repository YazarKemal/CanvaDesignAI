"""AI mockup director for turning uploaded artwork into listing-ready mockup prompts.

This module deliberately does not render images. It analyses an uploaded design
with the existing OpenAI vision client, combines that analysis with a real
pixel-derived colour palette, and returns six image-to-image mockup prompts.

The UI is intentionally out of scope: callers can use this module directly or
through ``mockup_api.py``.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, UnidentifiedImageError

from src.llm_json import extract_json
from src.palette import extract_palette
from src.vision_client import OpenAIVisionClient, VisionClientError


class MockupEngineError(RuntimeError):
    """Raised when a mockup set cannot be generated or validated."""


MOCKUP_TYPES = (
    "hero",
    "lifestyle",
    "close_up",
    "scale",
    "alternative_scene",
    "clean_product",
)

PRESERVATION_CLAUSE = (
    "Use the uploaded artwork as the exact source artwork inside the mockup. "
    "Preserve every visible design element, colour, face, illustration, symbol, "
    "letter, word and typographic relationship exactly as supplied. Do not "
    "redesign, repaint, recolour, rewrite, replace, retouch, crop or invent any "
    "part of the artwork. Only apply the physically necessary perspective, "
    "surface curvature, reflections, shadows and lighting interaction required "
    "to place the unchanged artwork naturally into the mockup scene."
)

NEGATIVE_SUFFIX = (
    "altered artwork, changed typography, misspelled text, invented text, "
    "recoloured artwork, redesigned composition, cropped artwork content, "
    "replacement logo, watermark, duplicate artwork, warped letters, fake frame text"
)

REPAIR_PROMPT = """\
Repair the JSON so it matches this contract exactly.
Root keys: asset_analysis, mockup_strategy, mockups.
mockups must contain exactly six objects with unique type values:
hero, lifestyle, close_up, scale, alternative_scene, clean_product.
Every mockup object must contain: type, title, purpose, prompt, negative_prompt.
Do not add markdown or commentary. Return one JSON object only.
"""


def _orientation(width: int, height: int) -> str:
    if width == height:
        return "square"
    return "portrait" if height > width else "landscape"


def _image_metadata(image_bytes: bytes) -> tuple[int, int, str]:
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MockupEngineError(f"Uploaded file is not a readable image: {exc}") from exc

    if width <= 0 or height <= 0:
        raise MockupEngineError("Uploaded image has invalid dimensions.")
    return width, height, _orientation(width, height)


def _build_prompt(
    *,
    width: int,
    height: int,
    orientation: str,
    palette: list[str],
    marketplace: str,
    product_type_hint: str,
    audience_hint: str,
    creative_direction: str,
) -> str:
    palette_text = ", ".join(palette) if palette else "not available"
    return f"""\
You are CaVDesign Mockup Director, a senior commercial art director specialised
in marketplace listing imagery. Analyse the uploaded artwork and design a
cohesive, photorealistic mockup presentation system around that exact artwork.

SOURCE METADATA
- source dimensions: {width}x{height}
- source orientation: {orientation}
- pixel-derived dominant palette: {palette_text}
- marketplace context: {marketplace or 'Etsy'}
- product type hint: {product_type_hint or 'auto-detect from the artwork'}
- audience hint: {audience_hint or 'infer from the artwork'}
- creative direction: {creative_direction or 'infer the strongest commercially appropriate direction'}

FIRST: analyse only what is visually supportable from the uploaded artwork.
Infer the likely product presentation category (for example wall art, poster,
printable, invitation, book cover, journal cover, sticker sheet, apparel
artwork, phone wallpaper, album artwork or another sensible category). When
uncertain, state the assumption explicitly instead of pretending certainty.

SECOND: create a mockup strategy whose environment, materials, lighting,
props, camera language and styling are visually compatible with the uploaded
artwork. The mockup should improve perceived value without competing with the
artwork. Avoid generic stock-photo scenes when a more specific art-directed
scene would fit better.

THIRD: return EXACTLY SIX mockup concepts, one for each required type:
1. hero — strongest marketplace thumbnail / first listing image
2. lifestyle — believable real-world use context
3. close_up — material, print, texture or finish detail
4. scale — clearly communicates real-world size or proportion
5. alternative_scene — a second aesthetically distinct but compatible setting
6. clean_product — distraction-free product presentation

PROMPT QUALITY RULES FOR EACH MOCKUP
- Write a complete image-to-image generation prompt, not notes or fragments.
- Specify environment, surface/material, frame or presentation method where
  relevant, props, lighting direction/quality, camera angle, lens/photographic
  language, depth of field, composition and realism cues.
- Keep the artwork as the visual hero; scene styling must support it.
- Do not request new text, labels, logos, signatures or watermarks in the scene.
- If the product is digital-only, choose a realistic device/screen or digital
  delivery presentation rather than pretending it is physically printed.
- If the product is printable wall art/poster, favour realistic frames, paper,
  wall/interior context and physically plausible print presentation.
- The six scenes should feel like one premium listing set, not six unrelated ads.

ASSET PRESERVATION — NON-NEGOTIABLE
{PRESERVATION_CLAUSE}

Return ONE JSON object and NOTHING else with this exact shape:
{{
  "asset_analysis": {{
    "product_type": "...",
    "asset_category": "...",
    "orientation": "{orientation}",
    "visual_style": "...",
    "mood": ["..."],
    "dominant_colors": {palette},
    "composition_notes": "...",
    "target_customer": "...",
    "physical_presentation_assumption": "..."
  }},
  "mockup_strategy": {{
    "presentation_goal": "...",
    "primary_environment": "...",
    "material_direction": "...",
    "lighting_direction": "...",
    "camera_direction": "...",
    "styling_notes": "..."
  }},
  "mockups": [
    {{"type":"hero","title":"...","purpose":"...","prompt":"...","negative_prompt":"..."}},
    {{"type":"lifestyle","title":"...","purpose":"...","prompt":"...","negative_prompt":"..."}},
    {{"type":"close_up","title":"...","purpose":"...","prompt":"...","negative_prompt":"..."}},
    {{"type":"scale","title":"...","purpose":"...","prompt":"...","negative_prompt":"..."}},
    {{"type":"alternative_scene","title":"...","purpose":"...","prompt":"...","negative_prompt":"..."}},
    {{"type":"clean_product","title":"...","purpose":"...","prompt":"...","negative_prompt":"..."}}
  ]
}}
"""


def _require_string(container: dict[str, Any], key: str, where: str) -> None:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MockupEngineError(f"{where}.{key} must be a non-empty string.")


def _normalise_and_validate(
    payload: dict[str, Any],
    *,
    palette: list[str],
    width: int,
    height: int,
    orientation: str,
    mime_type: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MockupEngineError("Vision response must be a JSON object.")

    analysis = payload.get("asset_analysis")
    strategy = payload.get("mockup_strategy")
    mockups = payload.get("mockups")

    if not isinstance(analysis, dict):
        raise MockupEngineError("asset_analysis must be an object.")
    if not isinstance(strategy, dict):
        raise MockupEngineError("mockup_strategy must be an object.")
    if not isinstance(mockups, list):
        raise MockupEngineError("mockups must be an array.")

    for key in (
        "product_type",
        "asset_category",
        "orientation",
        "visual_style",
        "composition_notes",
        "target_customer",
        "physical_presentation_assumption",
    ):
        _require_string(analysis, key, "asset_analysis")

    mood = analysis.get("mood")
    if not isinstance(mood, list):
        raise MockupEngineError("asset_analysis.mood must be an array.")

    for key in (
        "presentation_goal",
        "primary_environment",
        "material_direction",
        "lighting_direction",
        "camera_direction",
        "styling_notes",
    ):
        _require_string(strategy, key, "mockup_strategy")

    if len(mockups) != len(MOCKUP_TYPES):
        raise MockupEngineError(
            f"mockups must contain exactly {len(MOCKUP_TYPES)} items; got {len(mockups)}."
        )

    seen: set[str] = set()
    ordered: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(mockups):
        if not isinstance(item, dict):
            raise MockupEngineError(f"mockups[{index}] must be an object.")
        for key in ("type", "title", "purpose", "prompt", "negative_prompt"):
            _require_string(item, key, f"mockups[{index}]")

        mockup_type = item["type"].strip()
        if mockup_type not in MOCKUP_TYPES:
            raise MockupEngineError(f"Unsupported mockup type: {mockup_type}")
        if mockup_type in seen:
            raise MockupEngineError(f"Duplicate mockup type: {mockup_type}")
        seen.add(mockup_type)

        prompt = item["prompt"].strip()
        if PRESERVATION_CLAUSE not in prompt:
            prompt = f"{prompt.rstrip()} {PRESERVATION_CLAUSE}"
        item["prompt"] = prompt

        negative = item["negative_prompt"].strip().rstrip(", ")
        item["negative_prompt"] = f"{negative}, {NEGATIVE_SUFFIX}"
        ordered[mockup_type] = item

    missing = [mockup_type for mockup_type in MOCKUP_TYPES if mockup_type not in seen]
    if missing:
        raise MockupEngineError(f"Missing mockup types: {', '.join(missing)}")

    # Pixel truth overrides model-estimated colours and source orientation.
    analysis["dominant_colors"] = palette
    analysis["orientation"] = orientation

    payload["mockups"] = [ordered[mockup_type] for mockup_type in MOCKUP_TYPES]
    payload["source"] = {
        "width": width,
        "height": height,
        "orientation": orientation,
        "mime_type": mime_type,
        "dominant_palette": palette,
    }
    payload["prompt_version"] = "mockup-director-v1"
    return payload


def generate_mockup_set(
    image_bytes: bytes,
    mime_type: str,
    *,
    marketplace: str = "Etsy",
    product_type_hint: str = "",
    audience_hint: str = "",
    creative_direction: str = "",
    vision_client: OpenAIVisionClient | None = None,
) -> dict[str, Any]:
    """Analyse artwork and return a validated six-scene mockup prompt set.

    One multimodal call performs the visual analysis and scene direction. If
    the returned JSON breaks the contract, one text-only repair call is tried.
    Actual source colours are always extracted locally and override model colour
    guesses before the response is returned.
    """

    if not image_bytes:
        raise MockupEngineError("Uploaded image is empty.")

    width, height, orientation = _image_metadata(image_bytes)
    try:
        palette = extract_palette(image_bytes, n=5)
    except Exception as exc:
        raise MockupEngineError(f"Could not extract source palette: {exc}") from exc

    prompt = _build_prompt(
        width=width,
        height=height,
        orientation=orientation,
        palette=palette,
        marketplace=marketplace,
        product_type_hint=product_type_hint,
        audience_hint=audience_hint,
        creative_direction=creative_direction,
    )

    client = vision_client or OpenAIVisionClient()
    try:
        raw = client.deconstruct_image(image_bytes, mime_type, prompt=prompt)
    except VisionClientError as exc:
        raise MockupEngineError(str(exc)) from exc

    try:
        parsed = extract_json(raw)
        return _normalise_and_validate(
            parsed,
            palette=palette,
            width=width,
            height=height,
            orientation=orientation,
            mime_type=mime_type,
        )
    except Exception as first_error:
        try:
            repaired_raw = client.repair_json(raw, str(first_error), prompt=REPAIR_PROMPT)
            repaired = extract_json(repaired_raw)
            return _normalise_and_validate(
                repaired,
                palette=palette,
                width=width,
                height=height,
                orientation=orientation,
                mime_type=mime_type,
            )
        except Exception as repair_error:
            raise MockupEngineError(
                f"Mockup director returned an invalid payload and repair failed: {repair_error}"
            ) from repair_error
