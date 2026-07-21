"""Format-specific composition & negative-space recipes.

The Architect picks ONE aspect ratio and ONE text_zone; the Generator and
the Omni-Channel adapter then have to compose FOR that exact canvas. Rather
than hope the LLM reinvents good per-format composition every call, this
module holds those rules as structured data so they can be injected
deterministically (and unit-tested) — the same "push it into code, not just
the prompt" ethos as src/color_science.py's contrast math and src/schema.py's
text_zone check.

Each recipe carries the professional composition, lighting and depth cues
that suit a given aspect-ratio family, plus precise, per-`text_zone`
negative-space language ("reserve the upper 40% as a clean, minimal
background band for the typography overlay") so the reserved space is
described concretely instead of vaguely.
"""

from __future__ import annotations

import re
from typing import Any

# Ordered longest-token-first so "9:16" matches before "1:1" etc. when we
# scan a free-form aspect-ratio string like "1080x1920 (9:16)".
_RATIO_TO_FAMILY: dict[str, str] = {
    "9:16": "9:16",
    "16:9": "16:9",
    "1.91:1": "16:9",  # wide social (Facebook) — treat as horizontal
    "7:4": "16:9",     # business card — wide-ish, horizontal
    "4:5": "4:5",
    "3:4": "4:5",      # poster / flyer — tall portrait family
    "1:1": "1:1",
}

COMPOSITION_RULES: dict[str, dict[str, Any]] = {
    "9:16": {
        "label": "vertical story / reel",
        "composition": (
            "vertical leading lines guiding the eye top-to-bottom, elongated "
            "background depth, the hero subject grounded low in the frame"
        ),
        "lighting": "floating atmospheric lighting with soft, directional vertical falloff",
        "depth": "elongated foreground-to-background depth built from layered vertical planes",
        "negative_space": {
            "top": (
                "reserve the upper 40% as a clean, low-detail, minimalist background band "
                "for the typography overlay; ground the subject in the lower two-thirds"
            ),
            "bottom": (
                "ground the subject in the upper two-thirds and keep the lower 35% a clean, "
                "uncluttered backdrop reserved for the typography overlay"
            ),
            "center": (
                "keep a calm, low-contrast horizontal mid-band clear of busy detail so the "
                "centered text stays legible; push visual interest toward the top and bottom edges"
            ),
            "left": (
                "hold the subject to the right side, keeping the left vertical third a clean "
                "negative-space column reserved for text"
            ),
            "right": (
                "hold the subject to the left side, keeping the right vertical third a clean "
                "negative-space column reserved for text"
            ),
        },
    },
    "1:1": {
        "label": "square post",
        "composition": (
            "centered golden-ratio balance with a single crisp, isolated hero subject"
        ),
        "lighting": "clean studio softbox lighting, even and shadow-controlled",
        "depth": "shallow, controlled depth of field keeping the hero subject tack-sharp",
        "negative_space": {
            "top": (
                "reserve the top 40% as clean, evenly-lit negative space for the headline; "
                "seat the hero subject in the lower two-thirds"
            ),
            "bottom": (
                "reserve the bottom third as a clean, low-detail base for the typography; "
                "seat the hero subject in the upper two-thirds"
            ),
            "center": (
                "keep the golden-ratio center calm enough for text only when the hero subject "
                "is deliberately small or offset; otherwise the center stays subject-first"
            ),
            "left": (
                "isolate the hero subject on the right half against a clean studio backdrop, "
                "leaving the left vertical half as negative space for text"
            ),
            "right": (
                "isolate the hero subject on the left half against a clean studio backdrop, "
                "leaving the right vertical half as negative space for text"
            ),
        },
    },
    "16:9": {
        "label": "banner / thumbnail",
        "composition": (
            "dynamic horizontal framing with rule-of-thirds offset subject placement"
        ),
        "lighting": "wide directional light with cinematic, panoramic falloff",
        "depth": "panoramic depth of field with a deep, layered horizontal background",
        "negative_space": {
            "top": (
                "keep a clean horizontal upper band for the headline; anchor the subject along "
                "the lower edge"
            ),
            "bottom": (
                "anchor the subject along the upper edge; keep the lower horizontal band clean "
                "for the typography"
            ),
            "center": (
                "reserve a centered horizontal safe zone for text only when the subject is split "
                "to the far left and right edges"
            ),
            "left": (
                "offset the hero subject to the right third (rule of thirds); keep the left "
                "two-thirds an airy, panoramic negative space for headline and subtext"
            ),
            "right": (
                "offset the hero subject to the left third (rule of thirds); keep the right "
                "two-thirds an airy, panoramic negative space for headline and subtext"
            ),
        },
    },
    "4:5": {
        "label": "portrait feed / poster",
        "composition": (
            "tall portrait framing with the subject on a lower-third anchor and generous "
            "headroom above"
        ),
        "lighting": "soft diffused light with a gentle top-down gradient",
        "depth": "moderate depth of field with a calm, uncluttered background",
        "negative_space": {
            "top": (
                "reserve the top third as clean negative space for the headline; seat the "
                "subject in the lower two-thirds"
            ),
            "bottom": (
                "seat the subject in the upper two-thirds and keep the bottom third a clean "
                "base for the typography"
            ),
            "center": (
                "keep a low-contrast mid-band calm for centered text; frame the subject above "
                "and below it"
            ),
            "left": (
                "hold the subject to the right, leaving the left vertical third clean for text"
            ),
            "right": (
                "hold the subject to the left, leaving the right vertical third clean for text"
            ),
        },
    },
}

# Neutral fallback for any ratio not explicitly recognised.
DEFAULT_RULE: dict[str, Any] = {
    "label": "general canvas",
    "composition": "a balanced composition with one clear focal subject",
    "lighting": "soft, directional light that models the subject cleanly",
    "depth": "a controlled depth of field with an uncluttered background",
    "negative_space": {
        zone: (
            f"reserve deliberate, low-detail negative space at the {zone} of the frame for "
            "the typography overlay so the generated detail never clashes with the text"
        )
        for zone in ("top", "bottom", "center", "left", "right")
    },
}


def aspect_family(aspect_ratio: str) -> str | None:
    """Normalise a free-form aspect-ratio string to a known family key.

    Handles both the Architect's "1:1 (1080x1080)" and Omni-Channel's
    "1080x1920 (9:16)" formats by scanning for the ratio token. Returns the
    family key (e.g. "9:16", "1:1", "16:9", "4:5") or None if unrecognised.
    """
    text = aspect_ratio.replace(" ", "")
    for ratio, family in _RATIO_TO_FAMILY.items():
        if ratio in text:
            return family
    return None


def composition_for(aspect_ratio: str) -> dict[str, Any]:
    """Return the composition recipe for an aspect ratio (DEFAULT_RULE if
    the ratio isn't recognised)."""
    family = aspect_family(aspect_ratio)
    if family is None:
        return DEFAULT_RULE
    return COMPOSITION_RULES[family]


def negative_space_for(aspect_ratio: str, text_zone: str) -> str:
    """Return the precise negative-space instruction for a given aspect
    ratio and text_zone. Falls back to the default rule / a generic line
    for unknown zones."""
    rule = composition_for(aspect_ratio)
    zones = rule["negative_space"]
    zone = text_zone.lower().strip()
    if zone in zones:
        return zones[zone]
    return (
        f"reserve deliberate, low-detail negative space at the {zone} of the frame for "
        "the typography overlay"
    )


def as_prompt_block(aspect_ratio: str, text_zone: str | None = None) -> str:
    """Render the format-specific composition rules as an instruction block
    for the Generator / Omni-Channel system prompts.

    When `text_zone` is given, only that zone's precise negative-space line
    is included (the zone is already locked by the Architect); otherwise all
    zones are listed so the model can pick.
    """
    rule = composition_for(aspect_ratio)
    lines = [
        f"FORMAT-SPECIFIC COMPOSITION ({rule['label']}, {aspect_ratio}) — the "
        "magic_media_prompt MUST be composed FOR this exact canvas:",
        f"- Composition: {rule['composition']}.",
        f"- Lighting: {rule['lighting']}.",
        f"- Depth/space: {rule['depth']}.",
    ]
    if text_zone is not None:
        lines.append(
            f"- Negative space (text_zone '{text_zone}'): {negative_space_for(aspect_ratio, text_zone)}."
        )
    else:
        lines.append("- Negative space by text_zone:")
        for zone, text in rule["negative_space"].items():
            lines.append(f"    * {zone}: {text}.")
    return "\n".join(lines)


# Matches a directional keyword ONLY when it names the location of a reserved /
# negative-space region ("negative space at the top", "empty area toward the
# left"), so a zone rewrite fixes the spatial instruction without touching
# unrelated directions like the camera angle "top-down view" or the subject's
# own placement ("the cup on the right").
_NEG_SPACE_DIRECTION_RE = re.compile(
    r"(?P<cue>(?:negative|empty|open|blank|clean|reserved|clear|uncluttered|low-detail)\s+"
    r"(?:[\w-]+\s+){0,2}?(?:space|area|region|zone|band|section|portion|strip|margin)\b[^.]{0,32}?\bthe\s+)"
    r"(?P<zone>top|bottom|centre|center|left|right)\b(?!-)",
    re.IGNORECASE,
)


def align_zone_language(text: str, target_zone: str, *, append_clause: str) -> str:
    """Rewrite the negative-space direction in `text` to match `target_zone`.

    When a layout adaptation changes the text_zone (e.g. 'top' -> 'bottom'),
    the reused prose can still describe the OLD zone's reserved space, which
    then fails src/schema.py's text_zone-consistency check. This rewrites the
    directional keyword inside any negative-space clause to the new zone, and
    — as a guaranteed safety net — appends `append_clause` (which must name
    `target_zone`) if the zone word is still absent afterwards. Directional
    words that aren't describing reserved space (camera angles, the subject's
    own placement) are deliberately left untouched.
    """
    target = "center" if target_zone.strip().lower() == "centre" else target_zone.strip().lower()

    corrected = _NEG_SPACE_DIRECTION_RE.sub(lambda m: f"{m.group('cue')}{target}", text)

    if target not in corrected.lower():
        stripped = corrected.rstrip()
        if stripped.endswith("."):
            stripped = stripped[:-1].rstrip()
        corrected = f"{stripped}, {append_clause}."
    return corrected
