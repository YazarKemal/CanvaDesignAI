"""Loader for per-brand design constraints (config/brands/<slug>.json).

Mirrors src/constitution.py's loader pattern. When a brand is active, the
Architect, Generator and Reviewer all embed the same brand block so a
design's fonts, colors, and voice are constrained by the brand rather than
the generic Art Director defaults — and src/schema.py enforces the
factual parts (exact font match, palette membership) at the code level,
the same way contrast/text_zone are enforced today.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BRANDS_DIR = Path(__file__).resolve().parent.parent / "config" / "brands"


class BrandNotFoundError(ValueError):
    pass


def load_brand(slug: str, *, brands_dir: Path | str = BRANDS_DIR) -> dict[str, Any]:
    """Load a brand profile by slug. Raises BrandNotFoundError if missing."""
    path = Path(brands_dir) / f"{slug}.json"
    if not path.exists():
        available = ", ".join(list_brands(brands_dir=brands_dir)) or "(none configured)"
        raise BrandNotFoundError(f"No brand profile named '{slug}'. Available: {available}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_brands(*, brands_dir: Path | str = BRANDS_DIR) -> list[str]:
    """List available brand slugs (config/brands/*.json, sorted)."""
    path = Path(brands_dir)
    if not path.exists():
        return []
    return sorted(p.stem for p in path.glob("*.json"))


def approved_hex_colors(brand: dict[str, Any]) -> set[str]:
    """Flatten primary/secondary/accent into one set of approved HEX codes."""
    colors = brand.get("approved_colors", {})
    flat: set[str] = set()
    for group in colors.values():
        flat.update(c.upper() for c in group)
    return flat


def visual_identity_block(brand: dict[str, Any]) -> str:
    """Render a brand's visual_identity as explicit image-prompt steering.

    Brand deep integration: the profile must influence not just the text
    overlays' fonts/colors but the *image itself* — its mood, lighting
    warmth, and material/texture cues must be embedded into
    magic_media_prompt. Returns an empty string if the brand has no
    visual_identity block (older profiles stay backward-compatible).
    """
    vi = brand.get("visual_identity")
    if not vi:
        return ""

    parts: list[str] = []
    if vi.get("mood"):
        parts.append(f"- Mood to embody in the image: {vi['mood']}.")
    if vi.get("lighting_warmth"):
        parts.append(f"- Lighting warmth: {vi['lighting_warmth']}.")
    if vi.get("texture_cues"):
        parts.append(f"- Material/texture cues to weave in: {', '.join(vi['texture_cues'])}.")
    if vi.get("photographic_style"):
        parts.append(f"- Photographic/illustrative register: {vi['photographic_style']}.")

    body = "\n".join(parts)
    return (
        "BRAND VISUAL IDENTITY (mandatory — embed these directly into "
        "magic_media_prompt so the generated image itself reads on-brand, not "
        "only the typography overlay):\n" + body
    )


def as_prompt_block(
    brand: dict[str, Any], *, exclude_visual_identity: bool = False
) -> str:
    """Render a brand profile as an instruction block for LLM prompts.

    When *exclude_visual_identity* is True (because a Style Preset is active
    and its visual architecture overrides the brand's default aesthetic), the
    brand's ``visual_identity`` key is stripped from the embedded JSON and
    the ``visual_identity_block`` is suppressed entirely — only Color Palette,
    Typography (fonts) and Logo placement rules are included so the brand
    constrains the typography *layer* without competing with the style
    preset's image-direction keywords.
    """
    brand_for_prompt = dict(brand)
    if exclude_visual_identity:
        brand_for_prompt.pop("visual_identity", None)

    block = (
        f"BRAND PROFILE (mandatory — this design MUST use ONLY this brand's fonts "
        f"and colors, overriding the generic Art Director typography/color "
        f"defaults):\n{json.dumps(brand_for_prompt, ensure_ascii=False, indent=2)}"
    )
    if not exclude_visual_identity:
        visual = visual_identity_block(brand)
        if visual:
            block += f"\n\n{visual}"
    return block
