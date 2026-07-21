"""Loader for elite aesthetic style presets (config/styles/<slug>.json).

Mirrors src/brand_profiles.py's loader pattern, but style presets are
orthogonal to brands: a brand locks a design's fonts/colors, while a style
preset injects a fixed block of elite photographic/textural keywords into
`magic_media_prompt` (inspired by top-tier Canva creators). Both can be
active at once — a brand constrains typography/palette, a style steers the
image's look and feel.

Each preset carries:
- `magic_media_keywords`: the exact keyword block the Generator must weave
  into magic_media_prompt.
- `required_keywords`: the distinctive substrings src/schema.py enforces at
  the code level (retried if missing), so the style is guaranteed to land in
  the image prompt rather than being silently paraphrased away.
- `recommended_magic_media_style` / `palette_hint`: soft steering for the
  Architect/Generator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STYLES_DIR = Path(__file__).resolve().parent.parent / "config" / "styles"


class StyleNotFoundError(ValueError):
    pass


def load_style(slug: str, *, styles_dir: Path | str = STYLES_DIR) -> dict[str, Any]:
    """Load a style preset by slug. Raises StyleNotFoundError if missing."""
    path = Path(styles_dir) / f"{slug}.json"
    if not path.exists():
        available = ", ".join(list_styles(styles_dir=styles_dir)) or "(none configured)"
        raise StyleNotFoundError(f"No style preset named '{slug}'. Available: {available}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_styles(*, styles_dir: Path | str = STYLES_DIR) -> list[str]:
    """List available style preset slugs (config/styles/*.json, sorted)."""
    path = Path(styles_dir)
    if not path.exists():
        return []
    return sorted(p.stem for p in path.glob("*.json"))


def required_keywords(style: dict[str, Any]) -> list[str]:
    """The distinctive substrings that MUST appear in magic_media_prompt."""
    return list(style.get("required_keywords", []))


def best_for_summaries(*, styles_dir: Path | str = STYLES_DIR) -> str:
    """Render all preset slugs with their `best_for` one-liners for the
    Architect's system prompt, so the Architect can auto-select the most
    appropriate style preset for the user's concept without an extra LLM call.

    Returns a compact bullet list suitable for injection into a prompt.
    """
    lines: list[str] = []
    for slug in list_styles(styles_dir=styles_dir):
        try:
            style = load_style(slug, styles_dir=styles_dir)
        except StyleNotFoundError:
            continue
        best = style.get("best_for", "")
        name = style.get("name", slug)
        if best:
            lines.append(f"- {slug}: {best}")
        else:
            lines.append(f"- {slug}: {name}")
    return "\n".join(lines)


def as_prompt_block(
    style: dict[str, Any], *, override_brand: bool = False
) -> str:
    """Render a style preset as a mandatory image-prompt directive.

    When *override_brand* is True (a Brand Profile is also active), the block
    includes a strict hierarchy directive: the Style Preset's visual
    architecture REPLACES the Brand Profile's default visual identity (mood,
    lighting, textures, photographic style). The Brand Profile only contributes
    Color Palette, Typography, and Logo placement to the *typography layer* —
    it does NOT steer the generated image's look.
    """
    lines = [
        f"ELITE STYLE PRESET — '{style['name']}' (mandatory image direction). The "
        "magic_media_prompt MUST weave in these exact photographic and textural "
        "keywords, verbatim, so the generated image lands this look:",
        f"  {style['magic_media_keywords']}",
    ]
    if override_brand:
        lines.append(
            "\nSTYLE OVERRIDE RULE (token hierarchy — strict): This Style Preset's "
            "visual architecture REPLACES and OVERRIDES the Brand Profile's default "
            "visual identity (mood, lighting warmth, material/texture cues, "
            "photographic/illustrative register). The Brand Profile ONLY contributes "
            "its Color Palette, Typography (headline_font / body_font), and Logo "
            "placement rules to the typography layer — it does NOT contribute any "
            "visual mood or photographic direction to magic_media_prompt. The style "
            "preset wins on all image-aesthetic decisions. Do NOT describe the "
            "brand's default visual mood anywhere in magic_media_prompt — use ONLY "
            "the style preset's visual architecture."
        )
    if style.get("recommended_magic_media_style"):
        lines.append(
            f"- Set layer_typography_architecture.magic_media_style to "
            f"'{style['recommended_magic_media_style']}'."
        )
    if style.get("palette_hint"):
        lines.append(
            f"- Palette guidance (still emit real HEX with a valid contrast anchor): "
            f"{style['palette_hint']}."
        )
    lines.append(
        "- Any negative-space wording in these keywords must defer to the brief's "
        "text_zone — reserve that empty space at the text_zone location, not "
        "wherever the preset's example phrasing suggests."
    )
    return "\n".join(lines)
