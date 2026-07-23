"""Renders a Canva card as a paste-ready text block for a Claude/ChatGPT
chat that has a Canva tool/connector enabled.

IMPORTANT — what this is and isn't:

Text pasted into a Claude or ChatGPT conversation is always ordinary user
content to the receiving assistant. There is no wording (fake "SYSTEM:"
tags, "override" claims, etc.) that elevates pasted text to a higher
privilege level or that forces the receiving assistant to call a tool
regardless of its own judgment — that pattern is prompt injection, and
production assistants are specifically hardened against exactly this
trick. It would not reliably work even for a user's own benign purpose,
and building a feature around it would be encoding a broken assumption.

What DOES work: writing a clear, direct, first-person instruction — the
same way you'd tell any assistant "just do X, don't ask me questions."
This function puts exactly that at the top of the pasted block: a plain
directive to use the connected Canva tool and proceed without clarifying
questions, followed by the full card so the assistant has everything it
needs to act. Whether the receiving assistant actually invokes a Canva
tool still depends entirely on that assistant's own configuration and
judgment — this maximizes the odds, it does not guarantee it.
"""

from __future__ import annotations

from typing import Any


def render_for_assistant_paste(card: dict[str, Any]) -> str:
    """Render `card` as a plain-text block to paste into a Claude/ChatGPT
    chat that has a Canva tool connected.

    Supports both the new hybrid-split-layer format (raster_background /
    vector_elements / native_typography) and the legacy flat format.

    The block leads with a unified holistic-design instruction — the full
    magic_media_prompt + headline + subtext + palette + fonts + format +
    composition in one block so the receiving AI assistant can generate the
    complete design in a single pass. Alternative manual Magic Media steps
    follow as a secondary path.
    """
    # -- Resolve fields from either new (hybrid) or legacy (flat) format ----
    raster = card.get("raster_background", {})
    native = card.get("native_typography", {})
    vector = card.get("vector_elements", {})

    legacy_layer = card.get("layer_typography_architecture", {})

    magic_prompt = raster.get("magic_media_prompt", card.get("magic_media_prompt", ""))
    neg_prompt = raster.get("negative_prompt", card.get("negative_prompt", ""))
    media_style = raster.get("magic_media_style", legacy_layer.get("magic_media_style", "N/A"))

    headline = native.get("headline", legacy_layer.get("headline", ""))
    subtext = native.get("subtext", legacy_layer.get("subtext", ""))
    palette_list = native.get("color_palette", legacy_layer.get("color_palette", []))
    palette = ", ".join(palette_list)
    fonts = native.get("fonts", legacy_layer.get("fonts", {}))

    if fonts:
        font_line = f"{fonts.get('headline_font', '')} / {fonts.get('body_font', '')}"
    else:
        font_line = "N/A"

    alignment = native.get(
        "alignment_zone",
        legacy_layer.get("background_layers", f"typography at {card.get('text_zone', 'top')}"),
    )

    hl_pt = native.get("headline_pt")
    sub_pt = native.get("subtext_pt")

    lines = [
        f"Using your connected Canva tool, generate this design now at "
        f"{card['aspect_ratio']} — a single holistic composition with all "
        f"three hybrid layers (raster background + vector elements + native "
        f"typography) composed together in one pass. Do not ask me any "
        f"clarifying questions.",
        "",
        "UNIFIED DESIGN BRIEF (Hybrid Split Layer):",
        "",
        "-- Layer 1: Raster Background (image only — absolutely NO text) --",
        f"  Visual direction: {magic_prompt}",
        f"  Negative prompt: {neg_prompt}",
        f"  Magic Media style: {media_style}",
        "",
        "-- Layer 2: Vector Elements (CTA, badge, cutout — pure graphics) --",
    ]

    # Vector elements from new format ...
    for key, label in [
        ("cta_button", "CTA button"),
        ("badge", "Badge"),
        ("person_cutout", "Person cutout"),
        ("giant_typography", "Giant typography"),
    ]:
        val = vector.get(key)
        if val:
            lines.append(f"  {label}: {val}")

    # ... or legacy graphic_layers
    legacy_gc = legacy_layer.get("graphic_layers")
    if legacy_gc and not vector:
        for key, label in [
            ("cta_button", "CTA button"),
            ("badge", "Badge"),
            ("person_cutout", "Person cutout"),
            ("giant_typography", "Giant typography"),
        ]:
            val = legacy_gc.get(key)
            if val:
                lines.append(f"  {label}: {val}")

    if not vector and not legacy_gc:
        lines.append("  (none — this design has no vector overlay elements)")

    lines.extend(
        [
            "",
            "-- Layer 3: Native Typography (text only — separate overlay) --",
            f"  Headline (this is the visible title text on the design): {headline}",
        ]
    )
    if hl_pt:
        lines.append(f"  Headline point size: {hl_pt} pt")
    lines.append(f"  Subtext (this is the visible supporting text on the design): {subtext}")
    if sub_pt:
        lines.append(f"  Subtext point size: {sub_pt} pt")
    lines.extend(
        [
            f"  Color palette (typography styling only — apply these HEX codes as "
            f"fill/stroke colors; do NOT render the codes as visible text): {palette}",
            f"  Fonts (typography styling only — apply these as the font family "
            f"for the headline/subtext layers; do NOT render the font names as "
            f"visible text on the design): {font_line}",
            f"  Alignment zone: {alignment}",
            f"  Format: {card['aspect_ratio']}",
            f"  Target tool: {card['target_tool']}",
            f"  Text zone: {card['text_zone']}",
        ]
    )

    lines.extend(["", "Alternative — manual Canva steps:"])
    lines.extend(f"  {i}. {step}" for i, step in enumerate(card["direct_action_tip"], start=1))

    return "\n".join(lines)
