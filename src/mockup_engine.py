"""AI mockup director for turning uploaded artwork into listing-ready mockup prompts.

This module deliberately does not render images. It analyses an uploaded design
with the existing OpenAI vision client, combines that analysis with a real
pixel-derived colour palette, and returns six image-to-image mockup prompts.

Phase 2 adds product-aware commercial art direction:

- ``PRODUCT_CATEGORIES`` / ``SCENE_ARCHETYPES`` route each artwork to a category
  (wall_art, poster, printable, invitation, book_cover, journal_planner,
  sticker, apparel_graphic, phone_wallpaper, album_art) that carries a
  deterministic six-scene presentation skeleton.
- The art-direction fields (``environment``, ``surface_or_frame``, ``lighting``,
  ``camera``, ``composition``, ``artwork_placement``, ``realism_notes``) are
  backfilled from the archetype when the model omits them, and every final
  ``prompt`` receives the preservation constraints programmatically.
- Scene diversity and physical/digital presentation appropriateness are
  enforced deterministically after the model response.

The UI is intentionally out of scope: callers can use this module directly or
through ``mockup_api.py``.
"""

from __future__ import annotations

import re
from io import BytesIO
from math import gcd
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

ART_DIRECTION_FIELDS = (
    "environment",
    "surface_or_frame",
    "lighting",
    "camera",
    "composition",
    "artwork_placement",
    "realism_notes",
)

PRODUCT_CATEGORIES = (
    "wall_art",
    "poster",
    "printable",
    "invitation",
    "book_cover",
    "journal_planner",
    "sticker",
    "apparel_graphic",
    "phone_wallpaper",
    "album_art",
    "generic",
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

# Presentation tokens that are wrong for the opposite presentation mode.
DIGITAL_FORBIDDEN_TOKENS = (
    "framed",
    "matte print",
    "printed on",
    "paper stock",
    "on canvas",
    "poster frame",
    "gallery wall",
    "wall frame",
)
PHYSICAL_FORBIDDEN_TOKENS = (
    "phone screen",
    "smartphone",
    "lock screen",
    "mobile screen",
    "on a phone",
    "phone wallpaper",
)

# Maximum pairwise token-similarity allowed between two mockup prompts.
DIVERSITY_MAX_SIMILARITY = 0.8

REPAIR_PROMPT = """\
Repair the JSON so it matches this contract exactly.
Root keys: asset_analysis, mockup_strategy, mockups.
mockups must contain exactly six objects with unique type values:
hero, lifestyle, close_up, scale, alternative_scene, clean_product.
Every mockup object must contain: type, title, purpose, prompt, negative_prompt,
environment, surface_or_frame, lighting, camera, composition, artwork_placement,
realism_notes.
The six scenes must be visually distinct from one another (no near-duplicate
prompts). Present the artwork in a way that is appropriate for its product
category: printed/framed media for physical products, on-device/screen scenes
for digital-only products. Do not add markdown or commentary. Return one JSON
object only.
"""


# --------------------------------------------------------------------------- #
# Product-aware archetype table.
# --------------------------------------------------------------------------- #
#
# Each category carries a presentation mode and a shared context (the seven
# art-direction fields) plus per-mockup-type scene overrides. The engine
# backfills the art-direction fields from this table when the model omits them,
# so the final set is deterministic and physically/digitally appropriate.

SCENE_ARCHETYPES: dict[str, dict[str, Any]] = {
    "wall_art": {
        "label": "Wall Art",
        "mode": "physical",
        "context": {
            "environment": "curated gallery wall in a styled living space",
            "surface_or_frame": "matte fine-art paper in a slim frame",
            "lighting": "soft directional window light",
            "camera": "eye-level editorial, 50mm lens",
            "composition": "artwork centered on the wall with clean negative space",
            "artwork_placement": "exact artwork fills the frame with no cropping",
            "realism_notes": "photorealistic interior photography",
        },
        "scenes": {
            "hero": {"direction": "framed hero print centered on a clean gallery wall"},
            "lifestyle": {
                "direction": "print styled into a lived-in interior (sofa, plant, shelving)",
                "environment": "lived-in living room styled around the artwork",
            },
            "close_up": {
                "direction": "close-up of the frame edge and paper/print texture",
                "camera": "macro close-up, 100mm lens",
            },
            "scale": {
                "direction": "wide shot showing the print's real size against the room and furniture",
                "camera": "wide interior shot",
            },
            "alternative_scene": {
                "direction": "alternate interior setting (bedroom, office, or cafe)",
                "environment": "different interior setting",
            },
            "clean_product": {
                "direction": "studio product shot of the framed print on a neutral background",
                "environment": "neutral studio backdrop",
            },
        },
    },
    "poster": {
        "label": "Poster",
        "mode": "physical",
        "context": {
            "environment": "gallery wall or framed wall display in a styled room",
            "surface_or_frame": "printed poster paper in a thin frame",
            "lighting": "soft directional light",
            "camera": "eye-level editorial, 50mm lens",
            "composition": "poster centered with clean wall negative space",
            "artwork_placement": "exact poster fills the frame with no cropping",
            "realism_notes": "photorealistic interior photography",
        },
        "scenes": {
            "hero": {"direction": "framed poster hero on a clean wall"},
            "lifestyle": {"direction": "poster styled into a room with period-appropriate decor"},
            "close_up": {"direction": "close-up of the paper grain and print texture"},
            "scale": {"direction": "wide shot placing the poster in real room-scale context"},
            "alternative_scene": {"direction": "alternate interior setting with different wall treatment"},
            "clean_product": {"direction": "clean studio shot of the framed poster on a neutral background"},
        },
    },
    "printable": {
        "label": "Printable / Digital Download",
        "mode": "physical",
        "context": {
            "environment": "clean flat-lay studio surface",
            "surface_or_frame": "premium textured paper sheet",
            "lighting": "soft even studio light",
            "camera": "top-down flat-lay, 90mm lens",
            "composition": "printed sheet as the hero on the flat-lay",
            "artwork_placement": "exact artwork printed on the sheet with no cropping",
            "realism_notes": "photorealistic flat-lay styling",
        },
        "scenes": {
            "hero": {"direction": "flat-lay hero of the printed sheet on textured paper"},
            "lifestyle": {"direction": "printed page styled into a desk or tabletop scene in use"},
            "close_up": {"direction": "macro detail of the paper grain and ink finish"},
            "scale": {"direction": "printed sheet held or placed beside objects to show its real size"},
            "alternative_scene": {"direction": "alternate flat-lay styling on a different surface or paper"},
            "clean_product": {"direction": "single printed sheet isolated on a clean neutral background"},
        },
    },
    "invitation": {
        "label": "Invitation / Card",
        "mode": "physical",
        "context": {
            "environment": "elegant tabletop flat-lay with light florals",
            "surface_or_frame": "thick premium cardstock",
            "lighting": "soft warm natural light",
            "camera": "45-degree flat-lay, 85mm lens",
            "composition": "invitation card as the hero of the flat-lay",
            "artwork_placement": "exact artwork on the card with no cropping",
            "realism_notes": "photorealistic wedding/event stationery styling",
        },
        "scenes": {
            "hero": {"direction": "elegant card flat-lay as the hero"},
            "lifestyle": {"direction": "card styled on a real event table with stationery and florals"},
            "close_up": {"direction": "macro of the cardstock texture and printed detail"},
            "scale": {"direction": "card held in hand or with envelopes to show real size"},
            "alternative_scene": {"direction": "alternate styling matching a different season or theme"},
            "clean_product": {"direction": "single card isolated on a clean neutral background"},
        },
    },
    "book_cover": {
        "label": "Book Cover",
        "mode": "physical",
        "context": {
            "environment": "cozy reading nook beside a bookshelf",
            "surface_or_frame": "hardcover with matte finish",
            "lighting": "warm ambient reading light",
            "camera": "three-quarter view, 85mm lens",
            "composition": "book cover as the hero facing the camera",
            "artwork_placement": "exact artwork on the cover with no cropping",
            "realism_notes": "photorealistic book photography",
        },
        "scenes": {
            "hero": {"direction": "hardcover book standing upright, cover facing camera"},
            "lifestyle": {"direction": "book placed on a nightstand, desk, or bookshelf in a styled room"},
            "close_up": {"direction": "close-up of the cover texture, spine, and print finish"},
            "scale": {"direction": "book on a table with a hand or other books to show real size"},
            "alternative_scene": {"direction": "book styled into a different setting (cafe, study, shelf)"},
            "clean_product": {"direction": "studio shot of the book on a neutral background"},
        },
    },
    "journal_planner": {
        "label": "Journal / Planner",
        "mode": "physical",
        "context": {
            "environment": "styled desk setup",
            "surface_or_frame": "soft-touch cover with lay-flat paper pages",
            "lighting": "bright natural desk light",
            "camera": "top-down, 50mm lens",
            "composition": "journal/planner as the hero on the desk",
            "artwork_placement": "exact artwork on the cover or pages with no cropping",
            "realism_notes": "photorealistic desk/workspace photography",
        },
        "scenes": {
            "hero": {"direction": "open planner or journal as the hero on a styled desk"},
            "lifestyle": {"direction": "planner in real use on a desk with pens, washi tape, and notes"},
            "close_up": {"direction": "macro of the cover texture and paper pages"},
            "scale": {"direction": "planner beside a hand or desk objects to show real size"},
            "alternative_scene": {"direction": "alternate desk style or workspace setting"},
            "clean_product": {"direction": "studio shot of the journal/planner on a neutral background"},
        },
    },
    "sticker": {
        "label": "Sticker Sheet",
        "mode": "physical",
        "context": {
            "environment": "bright playful flat-lay surface",
            "surface_or_frame": "glossy vinyl die-cut sticker sheet",
            "lighting": "bright even studio light",
            "camera": "top-down, 90mm lens",
            "composition": "full sticker sheet as the hero",
            "artwork_placement": "exact artwork reproduced on the stickers with no cropping",
            "realism_notes": "photorealistic product photography with punchy colour",
        },
        "scenes": {
            "hero": {"direction": "full die-cut sticker sheet flat-lay hero"},
            "lifestyle": {"direction": "stickers applied to a laptop, water bottle, or journal in use"},
            "close_up": {"direction": "macro of the die-cut edges and glossy finish"},
            "scale": {"direction": "sheet beside a hand or everyday objects to show real size"},
            "alternative_scene": {"direction": "alternate background surface styling"},
            "clean_product": {"direction": "single sticker sheet isolated on a clean neutral background"},
        },
    },
    "apparel_graphic": {
        "label": "Apparel Graphic",
        "mode": "physical",
        "context": {
            "environment": "clean studio garment presentation",
            "surface_or_frame": "garment fabric (t-shirt / hoodie)",
            "lighting": "soft studio lighting",
            "camera": "front flat product view, 100mm lens",
            "composition": "garment centered with the graphic as the hero",
            "artwork_placement": "exact artwork printed on the garment with no cropping",
            "realism_notes": "photorealistic apparel product photography",
        },
        "scenes": {
            "hero": {"direction": "folded or flat-lay garment showing the graphic"},
            "lifestyle": {"direction": "garment worn by a model in a styled setting"},
            "close_up": {"direction": "macro of the fabric and print texture"},
            "scale": {"direction": "garment on a hanger or folded with objects to show real size"},
            "alternative_scene": {"direction": "styled outfit or alternate backdrop"},
            "clean_product": {"direction": "flat-lay garment isolated on a clean neutral background"},
        },
    },
    "phone_wallpaper": {
        "label": "Phone Wallpaper",
        "mode": "digital",
        "context": {
            "environment": "modern minimal desk or clean background",
            "surface_or_frame": "smartphone OLED screen",
            "lighting": "soft ambient light with subtle screen glow",
            "camera": "angled hero device shot, 50mm lens",
            "composition": "phone centered as the hero",
            "artwork_placement": "exact artwork fills the device screen with no cropping",
            "realism_notes": "photorealistic device photography",
        },
        "scenes": {
            "hero": {"direction": "smartphone on a display stand as the hero"},
            "lifestyle": {"direction": "phone held or resting on a desk in a lifestyle setting"},
            "close_up": {"direction": "screen detail showing the wallpaper at full clarity"},
            "scale": {"direction": "phone beside a hand or furniture to show real size"},
            "alternative_scene": {"direction": "alternate device or setting (tablet, portrait display)"},
            "clean_product": {"direction": "single isolated smartphone centered on a clean background"},
        },
    },
    "album_art": {
        "label": "Album Art",
        "mode": "hybrid",
        "context": {
            "environment": "styled studio or listening setup",
            "surface_or_frame": "vinyl sleeve / album cover card",
            "lighting": "moody dramatic light",
            "camera": "three-quarter view, 85mm lens",
            "composition": "album cover as the hero",
            "artwork_placement": "exact artwork on the cover with no cropping",
            "realism_notes": "photorealistic, editorial and atmospheric",
        },
        "scenes": {
            "hero": {"direction": "album sleeve or cover card as the hero"},
            "lifestyle": {"direction": "record player listening setup styled around the cover"},
            "close_up": {"direction": "close-up of the sleeve texture and record detail"},
            "scale": {"direction": "record and sleeve together to show real size"},
            "alternative_scene": {"direction": "streaming screen device presenting the cover"},
            "clean_product": {"direction": "isolated cover card on a clean neutral background"},
        },
    },
    "generic": {
        "label": "Generic",
        "mode": "hybrid",
        "context": {
            "environment": "clean styled marketplace presentation",
            "surface_or_frame": "surface or screen chosen to suit the artwork",
            "lighting": "soft natural light",
            "camera": "eye-level editorial, 50mm lens",
            "composition": "centered hero with clean negative space",
            "artwork_placement": "exact artwork displayed with no cropping",
            "realism_notes": "photorealistic, commercially polished",
        },
        "scenes": {
            "hero": {"direction": "clean hero presentation of the artwork"},
            "lifestyle": {"direction": "believable real-world use context"},
            "close_up": {"direction": "material, print, or texture detail"},
            "scale": {"direction": "clearly communicates real-world size or proportion"},
            "alternative_scene": {"direction": "a second aesthetically distinct compatible setting"},
            "clean_product": {"direction": "distraction-free product presentation"},
        },
    },
}

# Category resolution: ordered (keyword, category) pairs; first match wins.
CATEGORY_ALIASES: tuple[tuple[str, str], ...] = (
    ("phone wallpaper", "phone_wallpaper"),
    ("wallpaper", "phone_wallpaper"),
    ("wall art", "wall_art"),
    ("wallart", "wall_art"),
    ("book cover", "book_cover"),
    ("ebook cover", "book_cover"),
    ("bookcover", "book_cover"),
    ("journal cover", "journal_planner"),
    ("journal", "journal_planner"),
    ("planner", "journal_planner"),
    ("notebook", "journal_planner"),
    ("diary", "journal_planner"),
    ("wedding invitation", "invitation"),
    ("invitation", "invitation"),
    ("invite", "invitation"),
    ("sticker sheet", "sticker"),
    ("sticker", "sticker"),
    ("decals", "sticker"),
    ("die-cut", "sticker"),
    ("die cut", "sticker"),
    ("apparel", "apparel_graphic"),
    ("t-shirt", "apparel_graphic"),
    ("tshirt", "apparel_graphic"),
    ("shirt", "apparel_graphic"),
    ("clothing", "apparel_graphic"),
    ("hoodie", "apparel_graphic"),
    ("graphic tee", "apparel_graphic"),
    ("album art", "album_art"),
    ("album cover", "album_art"),
    ("single cover", "album_art"),
    ("album", "album_art"),
    ("film poster", "poster"),
    ("movie poster", "poster"),
    ("poster", "poster"),
    ("printable", "printable"),
    ("digital download", "printable"),
    ("instant download", "printable"),
    ("print", "printable"),
)


def _resolve_product_category(text: str) -> str | None:
    """Map free text (a user hint or model product_type) to a canonical category."""
    if not text:
        return None
    lowered = text.strip().lower()
    for keyword, category in CATEGORY_ALIASES:
        if keyword in lowered:
            return category
    return None


def _archetype_for(category: str, mockup_type: str) -> dict[str, str]:
    entry = SCENE_ARCHETYPES.get(category, SCENE_ARCHETYPES["generic"])
    context = entry["context"]
    overrides = entry.get("scenes", {}).get(mockup_type, {})
    fields: dict[str, str] = {}
    for field in ART_DIRECTION_FIELDS:
        value = overrides.get(field)
        fields[field] = value if value else context[field]
    fields["direction"] = overrides.get("direction", "")
    return fields


def _scene_guidance_block(category: str | None) -> str:
    if category is None:
        return (
            "- routed product category: infer from the artwork and choose one of: "
            "wall_art, poster, printable, invitation, book_cover, journal_planner, "
            "sticker, apparel_graphic, phone_wallpaper, album_art. "
            "Present the artwork only in a way that is physically or digitally "
            "appropriate for that category."
        )
    arch = SCENE_ARCHETYPES[category]
    lines = [
        f"- routed product category: {category} ({arch['label']})",
        f"- presentation mode: {arch['mode']} (choose only appropriate scenes)",
        "DETERMINISTIC SCENE GUIDANCE PER MOCKUP TYPE:",
    ]
    for mockup_type in MOCKUP_TYPES:
        lines.append(f"  {mockup_type}: {_archetype_for(category, mockup_type)['direction']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Geometry / pixel helpers.
# --------------------------------------------------------------------------- #


def _orientation(width: int, height: int) -> str:
    if width == height:
        return "square"
    return "portrait" if height > width else "landscape"


def _aspect_ratio(width: int, height: int) -> str:
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _image_metadata(image_bytes: bytes) -> tuple[int, int, str]:
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MockupEngineError(f"Uploaded file is not a readable image: {exc}") from exc

    if width <= 0 or height <= 0:
        raise MockupEngineError("Uploaded image has invalid dimensions.")
    return width, height, _orientation(width, height)


# --------------------------------------------------------------------------- #
# Vision payload optimisation.
# --------------------------------------------------------------------------- #
#
# Termux/Android closes connections on very large multipart bodies (a 4.7 MB
# PNG reliably fails with "Connection reset by peer"; the same image as a ~1.1 MB
# JPEG succeeds). The original artwork is always kept byte-for-byte untouched:
# pixel metadata, dimensions, aspect ratio and the dominant palette are derived
# from the ORIGINAL bytes. Only the in-memory copy sent to OpenAI Vision is
# resized/compressed, so this is a product-side preprocessing decision that stays
# out of the transport/vision-client layer.

VISION_MAX_LONG_EDGE = 1536
VISION_TARGET_BYTES = 1_500_000
VISION_QUALITY_STEPS = (85, 78, 70)
VISION_DOWNSHIFT = 0.85
VISION_COMPOSITE_BACKGROUND = (255, 255, 255)


def _needs_optimisation(image_bytes: bytes, width: int, height: int) -> bool:
    """A large/heavy image needs a Vision copy; a reasonably small one is kept."""
    return len(image_bytes) > VISION_TARGET_BYTES or max(width, height) > VISION_MAX_LONG_EDGE


def _composite_for_encoding(img: Image.Image) -> Image.Image:
    """Flatten transparency onto a neutral background, then convert to RGB."""
    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if has_alpha:
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, VISION_COMPOSITE_BACKGROUND + (255,))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return img.convert("RGB")


def _encode_jpeg_with_target(img: Image.Image) -> tuple[bytes, str, int, int]:
    """Encode a JPEG within the target byte budget, dropping quality then size."""
    for quality in VISION_QUALITY_STEPS:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        if len(data) <= VISION_TARGET_BYTES:
            return data, "image/jpeg", img.width, img.height

    resized = img
    while True:
        nw = max(1, round(resized.width * VISION_DOWNSHIFT))
        nh = max(1, round(resized.height * VISION_DOWNSHIFT))
        if nw == resized.width and nh == resized.height:
            break
        resized = resized.resize((nw, nh), Image.LANCZOS)
        buf = BytesIO()
        resized.save(buf, format="JPEG", quality=VISION_QUALITY_STEPS[-1])
        data = buf.getvalue()
        if len(data) <= VISION_TARGET_BYTES:
            return data, "image/jpeg", resized.width, resized.height
    return data, "image/jpeg", resized.width, resized.height


def _prepare_vision_image(
    image_bytes: bytes, mime_type: str
) -> tuple[bytes, str, dict[str, Any]]:
    """Build a compact in-memory analysis copy for Vision.

    Returns ``(vision_bytes, vision_mime_type, meta)``. The original bytes are
    never mutated; ``meta`` carries diagnostics for the ``source`` payload.
    """
    original_size = len(image_bytes)
    with Image.open(BytesIO(image_bytes)) as src:
        src.load()
        width, height = src.size

        if not _needs_optimisation(image_bytes, width, height):
            return image_bytes, mime_type, {
                "original_byte_size": original_size,
                "vision_byte_size": original_size,
                "vision_mime_type": mime_type,
                "vision_width": width,
                "vision_height": height,
                "vision_optimized": False,
            }

        working = _composite_for_encoding(src)
        longest = max(width, height)
        if longest > VISION_MAX_LONG_EDGE:
            scale = VISION_MAX_LONG_EDGE / longest
            working = working.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.LANCZOS,
            )
        vision_bytes, vision_mime_type, vision_width, vision_height = (
            _encode_jpeg_with_target(working)
        )

    return vision_bytes, vision_mime_type, {
        "original_byte_size": original_size,
        "vision_byte_size": len(vision_bytes),
        "vision_mime_type": vision_mime_type,
        "vision_width": vision_width,
        "vision_height": vision_height,
        "vision_optimized": True,
    }


# --------------------------------------------------------------------------- #
# Prompt builder.
# --------------------------------------------------------------------------- #


def _build_prompt(
    *,
    width: int,
    height: int,
    orientation: str,
    aspect_ratio: str,
    palette: list[str],
    marketplace: str,
    product_type_hint: str,
    audience_hint: str,
    creative_direction: str,
    category: str | None,
) -> str:
    palette_text = ", ".join(palette) if palette else "not available"
    guidance = _scene_guidance_block(category)
    return f"""\
You are CaVDesign Mockup Director, a senior commercial art director specialised
in marketplace listing imagery. Analyse the uploaded artwork and design a
cohesive, photorealistic mockup presentation system around that exact artwork.

SOURCE METADATA
- source dimensions: {width}x{height}
- source orientation: {orientation}
- source aspect ratio: {aspect_ratio}
- pixel-derived dominant palette: {palette_text}
- marketplace context: {marketplace or 'Etsy'}
- product type hint: {product_type_hint or 'auto-detect from the artwork'}
- audience hint: {audience_hint or 'infer from the artwork'}
- creative direction: {creative_direction or 'infer the strongest commercially appropriate direction'}

{guidance}

FIRST: analyse only what is visually supportable from the uploaded artwork.
Infer the likely product presentation category and the mood, style and audience.
When uncertain, state the assumption explicitly instead of pretending certainty.

SECOND: create a mockup strategy whose environment, materials, lighting,
props, camera language and styling are visually compatible with the uploaded
artwork. The mockup should improve perceived value without competing with the
artwork. Avoid generic stock-photo scenes when a more specific art-directed
scene would fit better. Keep the artwork as the visual hero.

THIRD: return EXACTLY SIX mockup concepts, one for each required type:
1. hero — strongest marketplace thumbnail / first listing image
2. lifestyle — believable real-world use context
3. close_up — material, print, texture or finish detail
4. scale — clearly communicates real-world size or proportion
5. alternative_scene — a second aesthetically distinct but compatible setting
6. clean_product — distraction-free product presentation

Each mockup carries a scene_direction plus these art-direction fields:
environment, surface_or_frame, lighting, camera, composition, artwork_placement,
realism_notes — written specifically for that scene. The six scenes must be
visually distinct from one another; they should feel like one premium listing
set, not six near-duplicate or unrelated ads.

PROMPT QUALITY RULES FOR EACH MOCKUP
- Write a complete image-to-image generation prompt, not notes or fragments.
- Specify environment, surface/material, frame or presentation method where
  relevant, props, lighting direction/quality, camera angle, lens/photographic
  language, depth of field, composition and realism cues.
- Do not request new text, labels, logos, signatures or watermarks in the scene.
- Match the presentation to the product category: printed/framed media for
  physical products, device/screen scenes for digital-only products. Do not
  present a digital-only product as if it were physically printed, and do not
  present a physical product primarily on a phone screen.

ASSET PRESERVATION — NON-NEGOTIABLE
{PRESERVATION_CLAUSE}

Return ONE JSON object and NOTHING else with this exact shape:
{{
  "asset_analysis": {{
    "product_type": "...",
    "asset_category": "...",
    "product_category": "{category or 'infer'}",
    "orientation": "{orientation}",
    "aspect_ratio": "{aspect_ratio}",
    "visual_style": "...",
    "mood": ["..."],
    "dominant_colors": {palette},
    "content_summary": "...",
    "composition_notes": "...",
    "audience": "...",
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
    {{"type":"hero","title":"...","purpose":"...","prompt":"...","negative_prompt":"...",
      "scene_direction":"...","environment":"...","surface_or_frame":"...","lighting":"...",
      "camera":"...","composition":"...","artwork_placement":"...","realism_notes":"..."}}
  ]
}}
The mockups array must contain six objects total, one per type, each with the
same field set as the hero object shown above (types: hero, lifestyle,
close_up, scale, alternative_scene, clean_product).
"""


# --------------------------------------------------------------------------- #
# Validation / normalisation.
# --------------------------------------------------------------------------- #


def _require_string(container: dict[str, Any], key: str, where: str) -> None:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MockupEngineError(f"{where}.{key} must be a non-empty string.")


def _prompt_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _assert_scene_diversity(prompts_by_type: dict[str, str]) -> None:
    types = list(prompts_by_type)
    for i in range(len(types)):
        for j in range(i + 1, len(types)):
            left, right = types[i], types[j]
            similarity = _jaccard(
                _prompt_tokens(prompts_by_type[left]), _prompt_tokens(prompts_by_type[right])
            )
            if similarity >= DIVERSITY_MAX_SIMILARITY:
                raise MockupEngineError(
                    f"Mockup scenes '{left}' and '{right}' are near-duplicates "
                    f"(similarity {similarity:.2f})."
                )


def _presentation_is_appropriate(category: str, item: dict[str, Any]) -> bool:
    mode = SCENE_ARCHETYPES.get(category, SCENE_ARCHETYPES["generic"])["mode"]
    haystack = " ".join(
        str(item.get(key, "")) for key in ("prompt", "environment", "surface_or_frame")
    ).lower()
    if mode == "digital":
        return not any(token in haystack for token in DIGITAL_FORBIDDEN_TOKENS)
    if mode == "physical":
        # Only enforce on hero/clean_product, where a device presentation is wrong.
        if item.get("type") in ("hero", "clean_product"):
            return not any(token in haystack for token in PHYSICAL_FORBIDDEN_TOKENS)
    return True


def _inject_preservation(prompt: str) -> str:
    """Programmatically attach the preservation clause to a final prompt."""
    cleaned = prompt.strip()
    if PRESERVATION_CLAUSE in cleaned:
        return cleaned
    return f"{cleaned} {PRESERVATION_CLAUSE}"


def _normalise_and_validate(
    payload: dict[str, Any],
    *,
    palette: list[str],
    width: int,
    height: int,
    orientation: str,
    aspect_ratio: str,
    mime_type: str,
    product_type_hint: str = "",
    vision_meta: dict[str, Any] | None = None,
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
        "aspect_ratio",
        "visual_style",
        "content_summary",
        "composition_notes",
        "audience",
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

    # Resolve the canonical product category: prefer the user hint, fall back to
    # the model's inferred product_type, then to the generic archetype.
    category = (
        _resolve_product_category(product_type_hint)
        or _resolve_product_category(str(analysis.get("product_type", "")))
        or "generic"
    )
    analysis["product_category"] = category
    analysis["presentation_mode"] = SCENE_ARCHETYPES[category]["mode"]

    if len(mockups) != len(MOCKUP_TYPES):
        raise MockupEngineError(
            f"mockups must contain exactly {len(MOCKUP_TYPES)} items; got {len(mockups)}."
        )

    seen: set[str] = set()
    ordered: dict[str, dict[str, Any]] = {}
    orig_prompts: dict[str, str] = {}
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

        # Capture the model-authored prompt for diversity checking *before* we
        # append shared deterministic clauses (which would inflate similarity).
        orig_prompts[mockup_type] = item["prompt"].strip()
        ordered[mockup_type] = item

    missing = [mockup_type for mockup_type in MOCKUP_TYPES if mockup_type not in seen]
    if missing:
        raise MockupEngineError(f"Missing mockup types: {', '.join(missing)}")

    _assert_scene_diversity(orig_prompts)

    # Second pass: backfill deterministic art-direction fields from the category
    # archetype, enforce preservation, and check presentation appropriateness.
    for mockup_type in MOCKUP_TYPES:
        item = ordered[mockup_type]
        archetype = _archetype_for(category, mockup_type)

        for field in ART_DIRECTION_FIELDS:
            if not item.get(field):
                item[field] = archetype[field]
        if not item.get("scene_direction"):
            item["scene_direction"] = archetype["direction"]

        for key in ("scene_direction", *ART_DIRECTION_FIELDS):
            _require_string(item, key, f"mockups[{mockup_type}]")

        if not _presentation_is_appropriate(category, item):
            raise MockupEngineError(
                f"Mockup '{mockup_type}' uses a presentation inappropriate for "
                f"category '{category}' (mode '{SCENE_ARCHETYPES[category]['mode']}')."
            )

        prompt = item["prompt"].strip()
        if archetype["direction"] and archetype["direction"] not in prompt:
            prompt = f"{prompt} Scene direction: {archetype['direction']}."
        item["prompt"] = _inject_preservation(prompt)

        negative = item["negative_prompt"].strip().rstrip(", ")
        item["negative_prompt"] = f"{negative}, {NEGATIVE_SUFFIX}"

    # Pixel truth overrides model-estimated colours, orientation and ratio.
    analysis["dominant_colors"] = palette
    analysis["orientation"] = orientation
    analysis["aspect_ratio"] = aspect_ratio

    payload["mockups"] = [ordered[mockup_type] for mockup_type in MOCKUP_TYPES]
    payload["source"] = {
        "width": width,
        "height": height,
        "orientation": orientation,
        "aspect_ratio": aspect_ratio,
        "mime_type": mime_type,
        "dominant_palette": palette,
        "product_category": category,
    }
    if vision_meta:
        payload["source"].update(vision_meta)
    payload["prompt_version"] = "mockup-director-v2"
    return payload


# --------------------------------------------------------------------------- #
# Public entry point.
# --------------------------------------------------------------------------- #


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

    A user-supplied ``product_type_hint`` routes the archetype deterministically;
    otherwise the category is inferred from the model's analysis after the call.
    """

    if not image_bytes:
        raise MockupEngineError("Uploaded image is empty.")

    width, height, orientation = _image_metadata(image_bytes)
    aspect_ratio = _aspect_ratio(width, height)
    try:
        palette = extract_palette(image_bytes, n=5)
    except Exception as exc:
        raise MockupEngineError(f"Could not extract source palette: {exc}") from exc

    pre_category = _resolve_product_category(product_type_hint)
    prompt = _build_prompt(
        width=width,
        height=height,
        orientation=orientation,
        aspect_ratio=aspect_ratio,
        palette=palette,
        marketplace=marketplace,
        product_type_hint=product_type_hint,
        audience_hint=audience_hint,
        creative_direction=creative_direction,
        category=pre_category,
    )

    # Only the Vision copy is optimised; metadata/palette stay on the original.
    vision_bytes, vision_mime_type, vision_meta = _prepare_vision_image(
        image_bytes, mime_type
    )

    client = vision_client or OpenAIVisionClient()
    try:
        raw = client.deconstruct_image(vision_bytes, vision_mime_type, prompt=prompt)
    except VisionClientError as exc:
        raise MockupEngineError(str(exc)) from exc

    def _validate(parsed: dict[str, Any]) -> dict[str, Any]:
        return _normalise_and_validate(
            parsed,
            palette=palette,
            width=width,
            height=height,
            orientation=orientation,
            aspect_ratio=aspect_ratio,
            mime_type=mime_type,
            product_type_hint=product_type_hint,
            vision_meta=vision_meta,
        )

    try:
        return _validate(extract_json(raw))
    except Exception as first_error:
        try:
            repaired_raw = client.repair_json(raw, str(first_error), prompt=REPAIR_PROMPT)
            return _validate(extract_json(repaired_raw))
        except Exception as repair_error:
            raise MockupEngineError(
                f"Mockup director returned an invalid payload and repair failed: {repair_error}"
            ) from repair_error
