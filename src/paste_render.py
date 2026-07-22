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

    The block leads with a unified holistic-design instruction — the full
    magic_media_prompt + headline + subtext + palette + fonts + format +
    composition in one block so the receiving AI assistant can generate the
    complete design in a single pass. Alternative manual Magic Media steps
    follow as a secondary path.
    """
    layer = card["layer_typography_architecture"]
    fonts = layer["fonts"]
    palette = ", ".join(layer["color_palette"])

    lines = [
        f"Using your connected Canva tool, generate this design now at "
        f"{card['aspect_ratio']} — a single holistic composition with the "
        f"visual, typography, palette, and fonts all composed together in "
        f"one pass. Do not ask me any clarifying questions.",
        "",
        "UNIFIED DESIGN BRIEF:",
        f"  Visual direction: {card['magic_media_prompt']}",
        f"  Negative prompt: {card['negative_prompt']}",
        f"  Headline (this is the visible title text on the design): {layer['headline']}",
        f"  Subtext (this is the visible supporting text on the design): {layer['subtext']}",
        f"  Color palette (typography styling only — apply these HEX codes as "
        f"fill/stroke colors; do NOT render the codes as visible text): {palette}",
        f"  Fonts (typography styling only — apply these as the font family "
        f"for the headline/subtext layers; do NOT render the font names as "
        f"visible text on the design): {fonts['headline_font']} / {fonts['body_font']}",
        f"  Format: {card['aspect_ratio']}",
        f"  Target tool: {card['target_tool']}",
        f"  Composition: {layer['background_layers']}",
        f"  Text zone: {card['text_zone']}",
        f"  Magic Media style: {layer.get('magic_media_style', 'N/A')}",
    ]

    # -- Graphic layers (person cutout, CTA, giant type, badge) --------------
    graphic = layer.get("graphic_layers")
    if graphic and isinstance(graphic, dict):
        lines.append("")
        lines.append(
            "Graphic composition layers (decorative elements — add each as a "
            "separate Canva shape or text layer on top of the generated image):"
        )
        if graphic.get("person_cutout"):
            lines.append(f"  Person cutout: {graphic['person_cutout']}")
        if graphic.get("cta_button"):
            lines.append(f"  CTA button: {graphic['cta_button']}")
        if graphic.get("giant_typography"):
            lines.append(f"  Giant typography: {graphic['giant_typography']}")
        if graphic.get("badge"):
            lines.append(f"  Badge: {graphic['badge']}")

    lines.extend(["", "Alternative — manual Canva steps:"])
    # Render the direct_action_tip steps; the first is the primary AI-assistant
    # path and the rest are the manual alternative.
    lines.extend(f"  {i}. {step}" for i, step in enumerate(card["direct_action_tip"], start=1))

    return "\n".join(lines)
