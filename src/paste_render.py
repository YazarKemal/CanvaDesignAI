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
    chat that has a Canva tool connected."""
    art = card.get("art_direction", {})

    lines = [
        f"Instruction: Using your connected Canva tool, generate this design now "
        f"at {card['aspect_ratio']} in {card['target_tool']}. Do not ask me any "
        f"clarifying questions — apply the parameters below exactly and proceed "
        f"directly.",
        "",
        f"Concept: {card['concept']}",
        "",
        "Magic Media prompt:",
        card["prompt_text"],
        "",
        f"Negative prompt: {card['negative_prompt']}",
        "",
        "Art direction:",
        f"- Color palette: {', '.join(art.get('color_palette', []))}",
        f"- Lighting: {art.get('lighting', 'natural')}",
        f"- Mood: {art.get('mood', 'professional')}",
        f"- Style: {art.get('magic_media_style', 'Flat Vector')}",
        "",
        f"Canva tip: {card.get('canva_tip', 'Paste into Magic Media and generate.')}",
    ]

    return "\n".join(lines)
