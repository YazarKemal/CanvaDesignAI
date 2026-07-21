#!/usr/bin/env python3
"""Generate 3 new elite style presets via Claude Fable 5 (Anthropic Messages API).

This script is a standalone tool — it does NOT touch generator.py, architect.py,
reviewer.py, or http_client.py. It carries its own minimal Anthropic Messages
client (pure httpx, no SDK required) and calls Fable 5 with the design_rules.json
aesthetic_taxonomy + the existing 3 presets as reference material.

Each generated preset is validated against the same structural rules the
pipeline enforces (required_keywords ⊆ magic_media_keywords, all schema fields
present). A preset that fails validation is sent back to Fable 5 with the error
message for up to 2 correction attempts.

Usage:
    ANTHROPIC_API_KEY=sk-ant-... python3 scripts/generate_style_presets.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv(override=True)

import httpx

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config" / "styles"
RULES_PATH = PROJECT_ROOT / "design_rules.json"

EXISTING_PRESETS = [
    "corporate-dynamic-vector",
    "holographic-glassmorphism",
    "neo-grunge-streetwear",
]

MODEL = "claude-fable-5"
MAX_RETRIES = 2

# ---------------------------------------------------------------------------
# Minimal Anthropic Messages client (standalone — no SDK, no http_client reuse)
# ---------------------------------------------------------------------------


@dataclass
class FableMessage:
    content: list[dict[str, Any]]


class FableClient:
    """Minimal drop-in for `anthropic.Anthropic().messages.create(...)`.

    Talks directly to the Anthropic Messages API via httpx. No `anthropic`
    SDK required — just like `DeepSeekClient` in src/http_client.py but for
    Claude / Fable models.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it in your shell or pass "
                "api_key= to FableClient()."
            )

    class messages:
        @staticmethod
        def create(
            *,
            model: str,
            max_tokens: int,
            system: str,
            messages: list[dict[str, str]],
            temperature: float = 0.7,
            api_key: str,
        ) -> FableMessage:
            url = "https://api.anthropic.com/v1/messages"
            resp = httpx.post(
                url,
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": messages,
                    "temperature": temperature,
                },
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2024-02-15",
                    "Content-Type": "application/json",
                },
                timeout=180.0,
            )
            if resp.status_code >= 400:
                print(f"[FableClient] HTTP {resp.status_code}: {resp.text[:500]}",
                      file=sys.stderr)
            resp.raise_for_status()
            data = resp.json()
            return FableMessage(content=data.get("content", []))


# ---------------------------------------------------------------------------
# Reference material loaders
# ---------------------------------------------------------------------------


def load_aesthetic_taxonomy() -> dict[str, Any]:
    """Extract the aesthetic_taxonomy block from design_rules.json."""
    with open(RULES_PATH, encoding="utf-8") as f:
        rules = json.load(f)
    return rules.get("aesthetic_taxonomy", {})


def load_existing_presets() -> list[dict[str, Any]]:
    """Load all 3 existing style presets as reference examples."""
    presets: list[dict[str, Any]] = []
    for slug in EXISTING_PRESETS:
        path = CONFIG_DIR / f"{slug}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                presets.append(json.load(f))
    return presets


# ---------------------------------------------------------------------------
# Validation (mirrors schema.py's style compliance logic)
# ---------------------------------------------------------------------------

REQUIRED_PRESET_FIELDS = [
    "slug",
    "name",
    "description",
    "recommended_magic_media_style",
    "magic_media_keywords",
    "required_keywords",
    "palette_hint",
]


class PresetValidationError(ValueError):
    """Raised when a generated preset fails structural validation."""


def validate_preset(preset: dict[str, Any]) -> None:
    """Validate a generated preset against the required schema.

    Checks performed (mirroring what the pipeline enforces):
    1. All 7 required fields present and non-empty
    2. slug is kebab-case and unique
    3. required_keywords is a list of >=2 strings
    4. Every required_keyword appears verbatim in magic_media_keywords
    5. magic_media_keywords >= 50 chars
    6. name and description are non-empty strings
    """
    # 1. Required fields
    for field in REQUIRED_PRESET_FIELDS:
        if field not in preset:
            raise PresetValidationError(f"Missing required field: '{field}'")
        if not preset[field] and field != "palette_hint":
            raise PresetValidationError(f"Field '{field}' is empty")

    slug = preset["slug"]
    # 2. Slug format
    if not all(c.islower() or c.isdigit() or c == "-" for c in slug):
        raise PresetValidationError(
            f"slug '{slug}' must be kebab-case (lowercase letters, digits, hyphens only)"
        )
    if slug in EXISTING_PRESETS:
        raise PresetValidationError(
            f"slug '{slug}' collides with an existing preset — pick a different slug"
        )

    # 3. required_keywords
    keywords = preset["required_keywords"]
    if not isinstance(keywords, list) or len(keywords) < 2:
        raise PresetValidationError(
            f"required_keywords must be a list of >=2 strings, got {len(keywords)}"
        )
    for kw in keywords:
        if not isinstance(kw, str) or len(kw.strip()) < 3:
            raise PresetValidationError(
                f"Each required_keyword must be a string >=3 chars, got: '{kw}'"
            )

    # 4. Every required_keyword must appear in magic_media_keywords
    block = preset["magic_media_keywords"].lower()
    for kw in keywords:
        if kw.lower() not in block:
            raise PresetValidationError(
                f"required_keyword '{kw}' does NOT appear in magic_media_keywords. "
                "Every required_keyword must be a verbatim substring of "
                "magic_media_keywords."
            )

    # 5. magic_media_keywords minimum length
    if len(preset["magic_media_keywords"]) < 50:
        raise PresetValidationError(
            f"magic_media_keywords is only {len(preset['magic_media_keywords'])} chars "
            "(need >=50 for meaningful image steering)"
        )

    # 6. name and description
    if len(preset["name"].strip()) < 3:
        raise PresetValidationError("name must be >=3 chars")
    if len(preset["description"].strip()) < 10:
        raise PresetValidationError("description must be >=10 chars")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_system_prompt() -> str:
    """Build the system prompt with taxonomy reference + existing preset examples."""
    taxonomy = load_aesthetic_taxonomy()
    existing = load_existing_presets()

    taxonomy_json = json.dumps(taxonomy, ensure_ascii=False, indent=2)
    existing_json = json.dumps(existing, ensure_ascii=False, indent=2)

    return f"""You are an elite design curator and prompt engineer specializing in
Canva Magic Media / DALL-E 3 image-generation presets. Your job: create
3 NEW, distinct style presets — each rooted in a concrete, named art
direction (a specific photography tradition, print technique, design
movement / era, or a well-defined visual subculture). Generic names
like "Modern Clean" or "Bold & Vibrant" are rejected — every preset
must anchor itself to a REAL, recognizable aesthetic lineage.

REFERENCE — Aesthetic Taxonomy (from design_rules.json):
Use the material_texture_lexicon, light_quality_lexicon, and
register_lexicon below as your concrete vocabulary. Every preset's
magic_media_keywords MUST draw from these specific, high-signal terms
— never resort to generic adjectives.
{taxonomy_json}

REFERENCE — Existing 3 Presets (exact format to match):
These are the 3 presets that already exist. Study their schema, tone,
and keyword density. Your 3 new presets must follow the IDENTICAL JSON
structure but explore 3 ENTIRELY DIFFERENT aesthetic territories.
{existing_json}

FORMAT — Output a single JSON object with this exact structure:
{{
  "presets": [
    {{
      "slug": "kebab-case-slug",
      "name": "Human-Readable Style Name",
      "description": "One-sentence visual description of the look.",
      "recommended_magic_media_style": "One of: Flat Vector, Photographic, 3D Model, Watercolor, Minimalist, Cyberpunk, Neon, Retro Anime, Paper Cut, Concept Art, Vibrant",
      "magic_media_keywords": "Flowing sentence of photographic/textural keywords (>=80 chars). These keywords will be injected directly into generated image prompts — make them dense, concrete, and distinctive. Draw from the aesthetic_taxonomy lexicons above.",
      "required_keywords": ["distinctive phrase 1", "distinctive phrase 2", "distinctive phrase 3", "distinctive phrase 4"],
      "palette_hint": "Color guidance with real HEX examples and a contrast anchor."
    }}
    // + 2 more presets
  ]
}}

HARD RULES:
- Exactly 3 presets, each in its own aesthetic territory with ZERO overlap.
- Every required_keyword MUST appear VERBATIM inside magic_media_keywords.
- Slugs must be kebab-case, unique, and descriptive of the aesthetic.
- Each preset must feel like it was curated by a designer who deeply
  understands that specific art movement / photographic tradition.
- DO NOT repeat or remix the 3 existing presets — these must be NEW
  aesthetic territories.
- recommended_magic_media_style must be one of the 11 values listed.
- palette_hint must include 3-4 real HEX codes with a light/dark anchor.

Respond with the JSON object ONLY — no markdown fences, no commentary."""


def build_user_message(feedback: str | None = None) -> str:
    """Build the user message, optionally with correction feedback."""
    base = (
        "Generate 3 new elite style presets for the CaVDesign Canva prompt engine. "
        "Each must be grounded in a distinct, named art direction (photography "
        "tradition, print technique, design movement/era, or visual subculture). "
        "Avoid any overlap with the existing 3 (corporate-dynamic-vector, "
        "holographic-glassmorphism, neo-grunge-streetwear)."
    )
    if feedback:
        return (
            f"{base}\n\nThe previous attempt had validation errors. Fix them "
            f"in this new response:\n\nVALIDATION ERRORS:\n{feedback}"
        )
    return base


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def generate_presets(client: FableClient) -> list[dict[str, Any]]:
    """Call Fable 5 to generate 3 presets, with retry loop for validation."""
    system = build_system_prompt()
    api_key = client.api_key

    for attempt in range(1, MAX_RETRIES + 2):  # initial + 2 retries = 3 total
        feedback = None if attempt == 1 else validation_feedback
        user = build_user_message(feedback)

        print(f"\n{'='*60}")
        print(f"Attempt {attempt}/{MAX_RETRIES + 1} — calling {MODEL}...")
        print(f"{'='*60}")

        resp = FableClient.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=0.8,
            api_key=api_key,
        )

        raw_text = "".join(
            b.get("text", "") for b in resp.content if b.get("type") == "text"
        )

        # Parse JSON from response
        try:
            text = raw_text.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[len("json"):]
                text = text.strip()
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            print(f"❌ Failed to parse JSON: {exc}")
            print(f"Raw (first 500 chars): {raw_text[:500]}")
            validation_feedback = f"Response was not valid JSON: {exc}. Raw output: {raw_text[:300]}"
            continue

        presets = data.get("presets", [])
        if not isinstance(presets, list) or len(presets) != 3:
            print(f"❌ Expected exactly 3 presets, got {len(presets)}")
            validation_feedback = (
                f"Expected exactly 3 presets in a 'presets' array, got {len(presets)}."
            )
            continue

        # Validate each preset
        errors: list[str] = []
        for i, preset in enumerate(presets):
            try:
                validate_preset(preset)
                print(f"  ✅ Preset {i+1}: '{preset['name']}' ({preset['slug']}) — valid")
            except PresetValidationError as exc:
                msg = f"Preset {i+1} ('{preset.get('name', '?')}'): {exc}"
                print(f"  ❌ {msg}")
                errors.append(msg)

        if not errors:
            print(f"\n🎯 All 3 presets passed validation on attempt {attempt}!")
            return presets

        validation_feedback = "\n".join(errors)
        print(f"\n⚠️  {len(errors)} preset(s) failed — retrying with feedback...")

    raise RuntimeError(
        f"Failed to produce 3 valid presets after {MAX_RETRIES + 1} attempts. "
        f"Last errors:\n{validation_feedback}"
    )


def save_presets(presets: list[dict[str, Any]]) -> list[Path]:
    """Write presets to config/styles/<slug>.json. Returns saved paths."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for preset in presets:
        path = CONFIG_DIR / f"{preset['slug']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(preset, f, ensure_ascii=False, indent=2)
            f.write("\n")
        paths.append(path)
    return paths


def print_summary(presets: list[dict[str, Any]]) -> None:
    """Print a terminal summary of the generated presets."""
    print(f"\n{'='*60}")
    print("FINAL — 3 New Style Presets")
    print(f"{'='*60}")
    for i, p in enumerate(presets, 1):
        print(f"\n─── Preset {i}: {p['name']} ───")
        print(f"  slug:           {p['slug']}")
        print(f"  style:          {p['recommended_magic_media_style']}")
        print(f"  description:    {p['description']}")
        print(f"  palette_hint:   {p['palette_hint']}")
        print(f"  required_keywords ({len(p['required_keywords'])}):")
        for kw in p["required_keywords"]:
            print(f"    • {kw}")
        keywords = p["magic_media_keywords"]
        print(f"  magic_media_keywords ({len(keywords)} chars):")
        print(f"    {keywords[:200]}...")
        print(f"  💾 saved: config/styles/{p['slug']}.json")
    print(f"\n{'='*60}")
    print("SCRİPT DURDU — onayını bekliyor.")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    print("╔══════════════════════════════════════════════════════╗")
    print("║  CaVDesign — Elite Style Preset Generator (Fable 5) ║")
    print("╚══════════════════════════════════════════════════════╝")

    # 1. Connect to Fable 5
    print(f"\n🔑 API key: ...{os.environ.get('ANTHROPIC_API_KEY', '')[-8:]}")
    client = FableClient()

    # 2. Generate presets (with internal retry loop)
    try:
        presets = generate_presets(client)
    except RuntimeError as exc:
        print(f"\n❌ FATAL: {exc}", file=sys.stderr)
        return 1

    # 3. Save to disk
    paths = save_presets(presets)
    for p in paths:
        print(f"💾 Wrote: {p}")

    # 4. Print summary and STOP — wait for user approval
    print_summary(presets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
