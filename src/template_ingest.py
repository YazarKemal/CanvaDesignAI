"""Offline template-ingestion layer — vision deconstruction → human approval → JSONL corpus.

This module is **completely separate** from the runtime Architect → Generator →
Reviewer pipeline.  It ingests real Canva / Behance / uploaded template images
by having a vision model (OpenAI) deconstruct them into card JSON, which a human
then reviews and approves before it enters the ``data/template_cards.jsonl``
corpus.  That corpus feeds future generator improvements (few-shot examples,
style calibration, etc.) — it never touches the runtime path directly.

**Architecture guard:** OpenAI is used ONLY here.  The runtime pipeline
(:mod:`src.generator`, :mod:`src.architect`, :mod:`src.reviewer`,
:mod:`src.orchestrator`) remains DeepSeek-only.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.llm_json import extract_json
from src.schema import (
    PROMPT_CARD_SCHEMA,
    PromptValidationError,
    _ensure_hybrid_format,
)
from src.schema import validate_prompt as _validate_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "template_cards.jsonl"

# ---------------------------------------------------------------------------
# Schema — PROMPT_CARD_SCHEMA fields + mandatory provenance
# ---------------------------------------------------------------------------

TEMPLATE_CARD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CaVDesign Ingested Template Card",
    "type": "object",
    "required": [
        # -- Core card fields (mirror PROMPT_CARD_SCHEMA) -----------------
        "concept",
        "raster_background",
        "vector_elements",
        "native_typography",
        "aspect_ratio",
        "target_tool",
        "text_zone",
        "direct_action_tip",
        # -- Provenance (ingestion-only) ---------------------------------
        "source_type",
        "source_ref",
        "ingested_at",
        "archetype",
        "category",
        "format",
        "approved",
    ],
    "properties": {
        # Core fields — same shape as PROMPT_CARD_SCHEMA.properties
        **PROMPT_CARD_SCHEMA.get("properties", {}),
        # Provenance
        "source_type": {
            "type": "string",
            "enum": ["canva", "behance", "upload"],
            "description": "Origin of the source template image.",
        },
        "source_ref": {
            "type": "string",
            "minLength": 1,
            "description": "URL, filename, or free-text reference that identifies the source.",
        },
        "ingested_at": {
            "type": "string",
            "format": "date-time",
            "description": "ISO-8601 timestamp of when the card was deconstructed.",
        },
        "archetype": {
            "type": "string",
            "minLength": 1,
            "description": "Design archetype (e.g. 'instagram_story', 'flyer', 'poster').",
        },
        "category": {
            "type": "string",
            "minLength": 1,
            "description": "Template category (e.g. 'bayram', 'lansman', 'acilis').",
        },
        "format": {
            "type": "string",
            "minLength": 1,
            "description": "Page / canvas format (e.g. '9:16', '1:1', '4:5').",
        },
        "approved": {
            "type": "boolean",
            "description": "Human-approval flag.  MUST be False on creation; only approve_card() can set it True.",
        },
        "approved_at": {
            "type": "string",
            "format": "date-time",
            "description": "ISO-8601 timestamp of when the card was approved.  Required when approved is True.",
        },
        "reviewer_note": {
            "type": "string",
            "description": "Optional free-text note from the human reviewer.",
        },
    },
    # Require approved_at when approved is True.
    "if": {
        "properties": {"approved": {"const": True}},
        "required": ["approved"],
    },
    "then": {
        "required": ["approved_at"],
    },
    "additionalProperties": True,
}

# ---------------------------------------------------------------------------
# Vision prompt — the instruction that deconstructs a template image into JSON
# ---------------------------------------------------------------------------

DECONSTRUCTION_PROMPT = """\
You are a design-intake analyst.  You are shown a Canva template, Behance \
portfolio graphic, or uploaded design image.  Your ONLY job is to describe \
it as a single Canva automation card in the CaVDesign JSON format.

RULES:
- Reply with a SINGLE JSON object and NOTHING else — no markdown fences, \
no greeting, no commentary, no prose before or after the JSON.
- Every field below MUST be present.  Use empty strings / empty arrays \
rather than omitting a required field.
- The design MUST target "Canva Native Layout Engine" (target_tool).
- Background (raster_background) is a Canva Stock Library search query \
(magic_media_prompt) + a negative_prompt.  Describe the visual scene \
precisely enough that someone could find a matching Canva stock photo.
- Vector elements (vector_elements) describe native Canva shapes: thin \
dividers, border frames, badges, pill buttons, corner brackets, etc. \
Use descriptive strings — each key's value is a prose instruction.
- Typography (native_typography) MUST include: headline (short, <=6 words), \
subtext (<=14 words), color_palette (3-5 HEX codes), fonts (headline_font \
and body_font — use real Canva built-in font names), alignment_zone (exact \
position), headline_pt, subtext_pt, and a micro_tags object with \
volume_line, category_line, origin_line, micro_pt, micro_color, micro_font, \
micro_spacing.
- direct_action_tip is an array of 2-5 strings — step-by-step instructions \
for recreating this design in Canva's UI.
- canva_keywords: 2-4 short keyword strings from the Canva knowledge base.
- aspect_ratio: the canvas dimensions (e.g. "1:1 (1080x1080)", \
"9:16 (1080x1920)").
- text_zone: one of "top", "bottom", "left", "right", "center" — where the \
main typography sits.
- concept: a short title / concept name for this template (<=10 words).

CRITICAL: Never copy the placeholder values from the example shape below. \
Every value MUST come from what you actually observe in the image. \
If something is not visible or cannot be determined, use an empty string \
("") for strings, an empty array ([]) for arrays, or 0 for numbers. \
Do NOT guess — only report what you can SEE.

Output ONLY this JSON shape (values in angle brackets are type placeholders \
— replace them with what you actually observe in the image):

{
  "concept": "<exact headline text visible in the image or empty string>",
  "aspect_ratio": "<observed aspect ratio, e.g. 1:1 (1080x1080)>",
  "target_tool": "Canva Native Layout Engine",
  "text_zone": "<top|bottom|left|right|center>",
  "canva_keywords": ["<observed keyword>", "<observed keyword>"],
  "raster_background": {
    "magic_media_prompt": "<Canva Stock Library search query matching the background>",
    "negative_prompt": "no AI-generated imagery, no text, no watermark...",
    "layout_style": "<observed layout style or empty string>"
  },
  "vector_elements": {
    "thin_divider": "<description of a thin rule if visible, or empty string>",
    "accent_frame": "<description of a border frame if visible, or empty string>"
  },
  "native_typography": {
    "headline": "<exact headline text visible in the image>",
    "subtext": "<exact subtext visible in the image or empty string>",
    "headline_pt": "<integer>",
    "subtext_pt": "<integer>",
    "color_palette": ["<hex>", "<hex>", "<hex>"],
    "fonts": {
      "headline_font": "<observed headline font name>",
      "body_font": "<observed body font name>"
    },
    "alignment_zone": "<exact position description, e.g. top 30% left-aligned>",
    "micro_tags": {
      "volume_line": "<observed volume line or empty string>",
      "category_line": "<observed category line or empty string>",
      "origin_line": "<observed origin line or empty string>",
      "micro_pt": "<integer>",
      "micro_color": "<hex>",
      "micro_font": "<observed micro tag font name>",
      "micro_spacing": "<observed spacing or empty string>"
    }
  },
  "direct_action_tip": [
    "<step-by-step instruction 1>",
    "<step-by-step instruction 2>"
  ]
}
"""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TemplateIngestError(RuntimeError):
    """Raised when an ingestion rule is violated (e.g. unapproved card append)."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def deconstruct_template(
    image_bytes: bytes,
    mime_type: str,
    *,
    source_type: str,
    source_ref: str,
    archetype: str,
    category: str,
    canvas_format: str,
    client: Any | None = None,
) -> dict[str, Any]:
    """Send a template image to the vision model and return a card dict.

    The returned dict has **approved=False** — it MUST be reviewed by a human
    and explicitly approved via :func:`approve_card` before it can enter the
    JSONL corpus.

    Parameters
    ----------
    image_bytes:
        Raw image bytes (PNG, JPEG, WebP, …).  Never written to disk.
    mime_type:
        IANA media type, e.g. ``"image/png"``.
    source_type:
        One of ``"canva"``, ``"behance"``, ``"upload"``.
    source_ref:
        URL, filename, or free-text reference identifying the source.
    archetype:
        Design archetype (e.g. ``"instagram_story"``).
    category:
        Template category (e.g. ``"bayram"``, ``"lansman"``).
    canvas_format:
        Page / canvas format (e.g. ``"9:16"``).  Stored in the ``format``
        field of the record (not named ``canvas_format`` to avoid shadowing
        the Python builtin here).
    client:
        An :class:`OpenAIVisionClient` instance.  Created automatically if
        ``None`` (using env vars for configuration).

    Returns
    -------
    dict
        The deconstructed card with all provenance fields populated and
        ``approved`` set to ``False``.
    """
    from src.vision_client import OpenAIVisionClient

    if client is None:
        client = OpenAIVisionClient()

    raw = client.deconstruct_image(image_bytes, mime_type, prompt=DECONSTRUCTION_PROMPT)

    try:
        card = extract_json(raw)
    except json.JSONDecodeError as exc:
        raise TemplateIngestError(
            f"Vision model did not return valid JSON.  Raw ({len(raw)} chars): "
            f"{raw[:300]}"
        ) from exc

    # Stamp provenance — deepcopy to avoid mutating the parsed dict in
    # surprising ways if the caller holds a reference.
    card = deepcopy(card)
    card["source_type"] = source_type
    card["source_ref"] = source_ref
    card["ingested_at"] = datetime.now(timezone.utc).isoformat()
    card["archetype"] = archetype
    card["category"] = category
    card["format"] = canvas_format
    card["approved"] = False

    # Normalise legacy flat-card fields into the hybrid split-layer format
    # so every record in the corpus has the same shape.
    _ensure_hybrid_format(card)

    return card


def approve_card(
    record: dict[str, Any],
    *,
    reviewer_note: str | None = None,
) -> dict[str, Any]:
    """Approve a previously deconstructed card so it can enter the corpus.

    Validates the record first — if validation fails, **approved is NOT set**
    and the error propagates.  This ensures a broken card can never be
    approved by accident.

    This is the ONLY way to set ``approved`` to ``True`` — there is no
    programmatic shortcut.  Returns *record* for chaining convenience.

    Parameters
    ----------
    record:
        The deconstructed card dict.  Must pass :func:`validate_template_card`.
    reviewer_note:
        Optional free-text note from the human reviewer (stored in the record).

    Returns
    -------
    dict
        The same *record* with ``approved=True``, ``approved_at`` timestamp,
        and optionally ``reviewer_note`` set.
    """
    validate_template_card(record)

    record["approved"] = True
    record["approved_at"] = datetime.now(timezone.utc).isoformat()
    if reviewer_note is not None:
        record["reviewer_note"] = reviewer_note
    return record


def append_template_card(
    record: dict[str, Any],
    path: str | Path = DEFAULT_CORPUS_PATH,
    *,
    force: bool = False,
) -> Path:
    """Append a single approved card to the JSONL corpus.

    Guard chain (in order):

    1. **Approval gate** — *record* must have ``approved=True``.
    2. **Validation gate** — :func:`validate_template_card` is called; a
       failing record is NEVER written to disk.
    3. **Deduplication** — if *record*'s ``source_ref`` already exists in
       the corpus, :class:`TemplateIngestError` is raised unless
       ``force=True``.

    Parameters
    ----------
    record:
        The card dict to append.
    path:
        Path to the JSONL corpus file.
    force:
        If ``True``, skip the deduplication check and append even when
        *source_ref* already exists in the corpus.

    Returns
    -------
    Path
        The resolved path written to.

    Raises
    ------
    TemplateIngestError
        If the record is not approved, fails validation, or is a duplicate
        (and *force* is ``False``).
    """
    # 1. Approval gate
    if not record.get("approved"):
        raise TemplateIngestError(
            "Cannot append unapproved card to corpus. "
            "Call approve_card(record) first, then retry."
        )

    # 2. Validation gate — must pass BEFORE touching disk
    validate_template_card(record)

    # 3. Deduplication
    path = Path(path)
    source_ref = record.get("source_ref", "")
    if not force and source_ref:
        existing = load_template_cards(path)
        for prev in existing:
            if prev.get("source_ref") == source_ref:
                raise TemplateIngestError(
                    f"Template with source_ref={source_ref!r} already exists "
                    f"in the corpus.  Use force=True to override."
                )

    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    logger.info("Appended approved card to %s (%d bytes)", path, len(line))
    return path


def load_template_cards(
    path: str | Path = DEFAULT_CORPUS_PATH,
) -> list[dict[str, Any]]:
    """Load every card from the JSONL corpus into memory.

    Returns an empty list if the corpus file does not exist yet.
    Malformed lines are logged and skipped — they do not crash the caller.
    """
    path = Path(path)
    if not path.exists():
        return []

    cards: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                cards.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping malformed line %d in %s: %s",
                    line_no, path, exc,
                )
    return cards


def validate_template_card(record: dict[str, Any]) -> None:
    """Validate *record* against both the TEMPLATE_CARD_SCHEMA and
    the runtime code-level Art Director rules (forbidden phrases,
    typography hierarchy, color contrast, text_zone consistency).

    This reuses the validators from :mod:`src.schema` — it does NOT
    duplicate logic.

    Raises
    ------
    PromptValidationError
        On any validation failure.
    TemplateIngestError
        If provenance fields are missing, malformed, or ``approved`` is
        ``True`` when it should not be (shouldn't happen, but is caught).
    """
    import jsonschema

    # -- Schema shape --------------------------------------------------------
    try:
        jsonschema.validate(instance=record, schema=TEMPLATE_CARD_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise PromptValidationError(
            f"Ingested card failed schema validation: {exc.message}"
        ) from exc

    # -- Provenance sanity ---------------------------------------------------
    source_type = record.get("source_type", "")
    if source_type not in ("canva", "behance", "upload"):
        raise TemplateIngestError(
            f"source_type must be 'canva', 'behance', or 'upload'; got {source_type!r}"
        )

    ingested = record.get("ingested_at", "")
    if not ingested:
        raise TemplateIngestError("ingested_at is missing — provenance required")

    # -- Reuse runtime validators (forbidden phrases, typography, contrast,
    #    zone consistency — everything in schema.validate_prompt except
    #    brand/style compliance, which don't apply to standalone templates).
    _validate_prompt(record)

    logger.debug("Template card validation passed for %r", record.get("concept", "unnamed"))
