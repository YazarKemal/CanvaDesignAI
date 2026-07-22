"""Few-shot golden-card store — loaded once at import time, indexed by style_id.

Each line of ``data/golden_cards.jsonl`` is a JSON object produced by the
pipeline that scored >= 9.0 on the review rubric.  When the Generator is
about to produce a card for a given style preset, the matching golden card
is injected into its system prompt as a concrete "this is what a 9.0+ card
for this style looks like" reference.

If no golden card exists for a style_id (e.g. a newly added preset) the
lookup returns ``None`` silently — the Generator proceeds without a
reference example rather than failing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GOLDEN_CARDS_PATH = Path(__file__).resolve().parent.parent / "data" / "golden_cards.jsonl"

# Loaded once at module-import time and kept in a module-level dict so
# every Generator call reuses the same in-memory index (zero disk I/O after
# the first import). A style_id may have MULTIPLE golden cards (one per
# brief archetype — launch, story/carousel, ...), so the index maps to a
# list rather than letting the last line silently shadow earlier ones.
_index: dict[str, list[dict[str, Any]]] = {}


def _load() -> dict[str, list[dict[str, Any]]]:
    """Parse golden_cards.jsonl, index by style_id.  Called once at import."""
    if not GOLDEN_CARDS_PATH.exists():
        return {}
    index: dict[str, list[dict[str, Any]]] = {}
    with open(GOLDEN_CARDS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = obj.get("style_id")
            if sid:
                index.setdefault(sid, []).append(obj)
    return index


_index = _load()


def _best(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Highest-scored card wins; on a tie, the earliest line (stable)."""
    return max(cards, key=lambda c: c.get("score", 0))


def get_golden_cards(style_id: str) -> list[dict[str, Any]]:
    """All golden cards for *style_id* (empty list if none)."""
    return list(_index.get(style_id, []))


def get_golden_card(style_id: str) -> dict[str, Any] | None:
    """Return the single BEST golden card for *style_id* (highest score),
    or ``None`` if the style has no golden cards.

    When a style has cards from several brief archetypes, only the
    top-scoring one is returned — injecting one reference instead of all
    of them keeps the few-shot block (and thus every Generator call)
    at roughly half the token cost for no measured quality loss.
    """
    cards = _index.get(style_id)
    if not cards:
        return None
    return _best(cards)


def as_few_shot_block(style_id: str) -> str:
    """Render the matching golden card as a compact few-shot injection block.

    Returns an empty string when no golden card exists for *style_id* so
    the caller can unconditionally inject the result without an extra
    existence check.
    """
    gc = get_golden_card(style_id)
    if gc is None:
        return ""

    card = gc.get("card_json", {})
    score = gc.get("score", 0)
    brief = gc.get("brief", "")

    # Build a compact reference — full card JSON so the Generator sees
    # exactly what a high-scoring output looks like for this style.
    return (
        f"\n\nGOLDEN REFERENCE CARD — style '{style_id}' (score {score:.1f}/10, "
        f"brief: \"{brief}\").  This card passed the full review rubric at "
        f">= 9.0 for this exact style preset.  Study its "
        f"magic_media_prompt structure, layer_typography_architecture precision, "
        f"and direct_action_tip concreteness — your output must match or exceed "
        f"this quality level:\n"
        f"{json.dumps(card, ensure_ascii=False, indent=2)}"
    )
