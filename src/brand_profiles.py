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


def as_prompt_block(brand: dict[str, Any]) -> str:
    """Render a brand profile as an instruction block for LLM prompts."""
    return (
        f"BRAND PROFILE (mandatory — this design MUST use ONLY this brand's fonts "
        f"and colors, overriding the generic Art Director typography/color "
        f"defaults):\n{json.dumps(brand, ensure_ascii=False, indent=2)}"
    )
