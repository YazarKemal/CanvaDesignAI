"""Canva Brand Template Autofill adapter — Stage 4 (post-Generator).

Takes a validated CaVDesign card (the Generator's JSON output) and transforms
it into a Canva Data Autofill API payload.  This module is a PURE DATA
TRANSFORM: it never calls the Canva API itself (real HTTP lives in
``src/canva_http.py``, to be added in Step 4).

Architecture
------------
Generator JSON card  →  as_canva_autofill_payload()  →  autofill payload dict
                                                           │
                                                           ▼
                                              POST /rest/v1/autofills
                                                           │
                                                           ▼
                                              Editable Canva design URL

Design decisions (v1)
---------------------
- Text fields (Headline, Subtext, CTA_Text, …) map directly from the card's
  ``native_typography`` and ``vector_elements`` sections.
- The background image is NOT autofilled inline — the caller must first run
  ``upload_background_asset()`` to push an image to Canva (obtaining an
  ``asset_id``), then pass it into the payload separately.
- Palette and fonts are **not** autofilled — they are baked into the Brand
  Template's static styling.  Canva's autofill text fields only replace the
  text content, not the font family / colour / size.
- ``brand_template_id`` is a mandatory parameter.  A future style_id→template_id
  registry (``TEMPLATE_REGISTRY``) is scaffolded so callers can look up the
  right template without hard-coding IDs everywhere.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------------
# Future: style_id → brand_template_id registry
# ---------------------------------------------------------------------------
# When you have more than one Brand Template, add entries here:
#
#   TEMPLATE_REGISTRY: dict[str, str] = {
#       "warm-editorial-minimalist": "tpl_abc123",
#       "brutalist-mono":            "tpl_def456",
#   }
#
# Then ``resolve_template_id()`` can accept a style_id OR a raw template id
# and return the mapped value.  The registry is consulted FIRST; if no match
# is found the raw id is returned as-is (so direct template-id usage always
# works).
# ---------------------------------------------------------------------------

TEMPLATE_REGISTRY: dict[str, str] = {}  # style_id → brand_template_id


def resolve_template_id(style_id_or_template_id: str) -> str:
    """Look up a brand template id from the registry if *style_id_or_template_id*
    is a known style slug; otherwise return it unchanged.

    >>> resolve_template_id("tpl_abc123")
    'tpl_abc123'
    """
    return TEMPLATE_REGISTRY.get(style_id_or_template_id, style_id_or_template_id)


# ---------------------------------------------------------------------------
# Field-name constants — the canonical set of placeholder names that the
# Canva Brand Template MUST use.  These become the keys of the ``data``
# object in the autofill payload.
# ---------------------------------------------------------------------------

# Text placeholders (always present)
FIELD_HEADLINE = "Headline"
FIELD_SUBTEXT = "Subtext"

# Optional text placeholders
FIELD_CTA_TEXT = "CTA_Text"
FIELD_BADGE_TEXT = "Badge_Text"
FIELD_VOLUME_LINE = "VolumeLine"
FIELD_CATEGORY_LINE = "CategoryLine"
FIELD_ORIGIN_LINE = "OriginLine"

# Image placeholders
FIELD_BACKGROUND_IMAGE = "BackgroundImage"

# Ordered set of ALL known placeholder names (used as the default when
# ``template_fields`` is not provided).
DEFAULT_TEMPLATE_FIELDS: tuple[str, ...] = (
    FIELD_HEADLINE,
    FIELD_SUBTEXT,
    FIELD_CTA_TEXT,
    FIELD_BADGE_TEXT,
    FIELD_VOLUME_LINE,
    FIELD_CATEGORY_LINE,
    FIELD_ORIGIN_LINE,
    FIELD_BACKGROUND_IMAGE,
)

# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

# Regex for Canva brand template ids observed in the wild:
#   tpl_<alphanumeric>  (e.g. "tpl_abc123def")
_TEMPLATE_ID_RE = re.compile(r"^tpl_[a-zA-Z0-9]+$")


def _extract_text(card: dict[str, Any], *path: str) -> str | None:
    """Walk a nested dict by *path*, returning the string value or None."""
    node: Any = card
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return str(node).strip() if node else None


def _text_field(text: str) -> dict[str, str]:
    """Build a Canva autofill text field object."""
    return {"type": "text", "text": text}


def _image_field(asset_id: str) -> dict[str, str]:
    """Build a Canva autofill image field object."""
    return {"type": "image", "asset_id": asset_id}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def as_canva_autofill_payload(
    card: dict[str, Any],
    brand_template_id: str,
    *,
    template_fields: list[str] | None = None,
    title: str | None = None,
    background_asset_id: str | None = None,
) -> dict[str, Any]:
    """Transform a CaVDesign card into a Canva Data Autofill payload.

    Parameters
    ----------
    card:
        A validated CaVDesign card dict (the Generator's JSON output).  Must
        conform to ``PROMPT_CARD_SCHEMA`` (hybrid split-layer format).
    brand_template_id:
        **Mandatory.** The Canva Brand Template ID to autofill (e.g.
        ``"tpl_abc123def"``).  Use :func:`resolve_template_id` if you have a
        style_id and want registry lookup.
    template_fields:
        The exact list of data-field names this template declares (as returned
        by ``GET /brand-templates/{id}/dataset``).  Fields in the payload that
        are NOT in this list are dropped so Canva never sees unknown keys.
        When ``None`` (the default), **all** known fields from
        ``DEFAULT_TEMPLATE_FIELDS`` are included (useful for testing without a
        real template).
    title:
        Design title shown in Canva (max 255 chars).  Defaults to the card's
        ``concept`` field.
    background_asset_id:
        Pre-uploaded Canva asset id for the background image.  If omitted, the
        ``BackgroundImage`` field is excluded from the payload (the template's
        default background remains).  Obtain this via
        :func:`upload_background_asset`.

    Returns
    -------
    dict
        A payload ready for ``POST /rest/v1/autofills``:

        .. code-block:: json

            {
              "brand_template_id": "tpl_abc123",
              "title": "Grand Opening Cafe",
              "data": {
                "Headline": { "type": "text", "text": "Grand Opening" },
                "Subtext":  { "type": "text", "text": "Freshly roasted." }
              }
            }
    """
    # -- Resolve allowed fields ------------------------------------------------
    allowed: set[str] = (
        set(template_fields)
        if template_fields is not None
        else set(DEFAULT_TEMPLATE_FIELDS)
    )

    # -- Build the full data object --------------------------------------------
    data: dict[str, dict[str, str]] = {}

    # Text fields — always extracted from the card
    _add_if_allowed(data, FIELD_HEADLINE, _extract_text(card, "native_typography", "headline"), allowed, _text_field)
    _add_if_allowed(data, FIELD_SUBTEXT, _extract_text(card, "native_typography", "subtext"), allowed, _text_field)
    _add_if_allowed(data, FIELD_CTA_TEXT, _extract_text(card, "vector_elements", "cta_button"), allowed, _text_field)
    _add_if_allowed(data, FIELD_BADGE_TEXT, _extract_text(card, "vector_elements", "badge"), allowed, _text_field)

    # Micro-tag text fields
    _add_if_allowed(data, FIELD_VOLUME_LINE, _extract_text(card, "native_typography", "micro_tags", "volume_line"), allowed, _text_field)
    _add_if_allowed(data, FIELD_CATEGORY_LINE, _extract_text(card, "native_typography", "micro_tags", "category_line"), allowed, _text_field)
    _add_if_allowed(data, FIELD_ORIGIN_LINE, _extract_text(card, "native_typography", "micro_tags", "origin_line"), allowed, _text_field)

    # Image field — only include if an asset_id was provided
    if background_asset_id and FIELD_BACKGROUND_IMAGE in allowed:
        data[FIELD_BACKGROUND_IMAGE] = _image_field(background_asset_id)

    # -- Assemble payload ------------------------------------------------------
    payload: dict[str, Any] = {
        "brand_template_id": brand_template_id,
        "data": data,
    }
    if title is not None:
        payload["title"] = str(title)[:255]
    else:
        concept = card.get("concept")
        if concept:
            payload["title"] = str(concept)[:255]

    return payload


def _add_if_allowed(
    data: dict[str, dict[str, str]],
    field_name: str,
    value: str | None,
    allowed: set[str],
    builder: Any,
) -> None:
    """Add *field_name* → *builder(value)* to *data* only when *field_name*
    is in *allowed* and *value* is a non-empty string."""
    if field_name not in allowed:
        return
    if not value:
        return
    data[field_name] = builder(value)


# ---------------------------------------------------------------------------
# Asset upload (mock / stub — real HTTP in Step 4)
# ---------------------------------------------------------------------------

def upload_background_asset(
    image_path_or_bytes: str | bytes,
) -> str:
    """Upload an image to Canva's asset library and return its ``asset_id``.

    **Current status: MOCK.**  This stub always returns a synthetic asset id
    so the rest of the pipeline can be developed and tested end-to-end without
    a real Canva API connection.  The real implementation (Step 4) will:

    1. Accept a local file path (``str``) or raw image bytes (``bytes``).
    2. Call ``POST /rest/v1/assets`` with multipart/form-data.
    3. Poll ``GET /rest/v1/assets/{jobId}`` for completion.
    4. Return the ``asset_id`` string (e.g. ``"Msd59349ff"``).

    Parameters
    ----------
    image_path_or_bytes:
        Either a path to an image file on disk, or raw image bytes.

    Returns
    -------
    str
        A synthetic Canva ``asset_id`` (mock).  Real ids look like
        ``"Msd59349ff"``; mocks are ``"mock_<uuid_hex>"``.
    """
    # Determine a deterministic-ish label for logging
    if isinstance(image_path_or_bytes, str):
        label = image_path_or_bytes
    else:
        label = f"<{len(image_path_or_bytes)} bytes>"

    asset_id = f"mock_{uuid4().hex[:12]}"
    # In the real implementation, this would be:
    #   1. POST /rest/v1/assets  (upload)
    #   2. GET  /rest/v1/assets/{jobId} (poll until success)
    #   3. return response["asset"]["id"]
    return asset_id


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------

def validate_payload(payload: dict[str, Any]) -> None:
    """Validate that *payload* conforms to the Canva Autofill API contract.

    Raises ``ValueError`` with a human-readable message on the first violation.
    This is a **client-side** check — it catches mistakes before a round-trip
    to Canva's servers.

    Checks performed
    ----------------
    * ``brand_template_id`` is present and matches the expected pattern.
    * ``data`` is a non-empty dict.
    * Every data value is a dict with a valid ``type`` key (``"text"`` or
      ``"image"``).
    * ``text`` fields have a non-empty ``text`` string.
    * ``image`` fields have a non-empty ``asset_id`` string.
    * ``title``, if present, is ≤ 255 characters.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    # brand_template_id
    tid = payload.get("brand_template_id")
    if not tid or not isinstance(tid, str):
        raise ValueError("payload.brand_template_id is required and must be a string")
    if not _TEMPLATE_ID_RE.match(tid):
        raise ValueError(
            f"payload.brand_template_id '{tid}' does not match expected "
            f"pattern tpl_<alphanumeric>"
        )

    # data
    data = payload.get("data")
    if not isinstance(data, dict) or len(data) == 0:
        raise ValueError("payload.data must be a non-empty dict")

    for field_name, value in data.items():
        if not isinstance(value, dict):
            raise ValueError(
                f"payload.data['{field_name}'] must be a dict, got {type(value).__name__}"
            )
        ftype = value.get("type")
        if ftype not in ("text", "image"):
            raise ValueError(
                f"payload.data['{field_name}'].type must be 'text' or 'image', "
                f"got {ftype!r}"
            )
        if ftype == "text":
            if not value.get("text"):
                raise ValueError(
                    f"payload.data['{field_name}'].text is required and must not be empty"
                )
        elif ftype == "image":
            if not value.get("asset_id"):
                raise ValueError(
                    f"payload.data['{field_name}'].asset_id is required and must not be empty"
                )

    # title (optional but length-limited)
    title = payload.get("title")
    if title is not None:
        if not isinstance(title, str):
            raise ValueError("payload.title must be a string")
        if len(title) > 255:
            raise ValueError(
                f"payload.title is {len(title)} chars (max 255)"
            )
