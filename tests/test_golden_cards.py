"""Tests for src/golden_cards.py — few-shot injection of scored reference cards."""

import json
from io import StringIO

from src.golden_cards import _best, as_few_shot_block, get_golden_card, get_golden_cards
from src.style_presets import list_styles, load_style


def test_get_golden_card_returns_card_for_known_style():
    """Every style with a golden card must return a non-None dict with the
    expected fields."""
    # All wave-1/2/3 presets have golden cards
    for slug in list_styles():
        gc = get_golden_card(slug)
        if gc is None:
            # New presets added after the golden set was created won't have
            # entries — that's fine, the lookup silently returns None.
            continue
        assert "style_id" in gc
        assert gc["style_id"] == slug
        assert "card_json" in gc
        assert "score" in gc
        assert gc["score"] >= 9.0
        assert "brief" in gc


def test_get_golden_card_returns_none_for_unknown_style():
    """An unknown style_id must return None without raising."""
    assert get_golden_card("this-style-does-not-exist") is None


def test_as_few_shot_block_includes_score_and_brief():
    """The few-shot block must mention the score and the original brief so
    the Generator sees what concept produced this reference card."""
    block = as_few_shot_block("warm-editorial-minimalist")
    assert "GOLDEN REFERENCE CARD" in block
    assert "warm-editorial-minimalist" in block
    assert "9." in block  # score prefix
    assert "brief" in block.lower()


def test_as_few_shot_block_includes_card_json():
    """The golden card's full card_json must be embedded so the Generator
    sees the exact output format and quality level."""
    block = as_few_shot_block("neo-grunge-streetwear")
    assert "magic_media_prompt" in block
    assert "layer_typography_architecture" in block
    assert "direct_action_tip" in block
    assert "score" in block.lower()


def test_as_few_shot_block_returns_empty_for_unknown_style():
    """Unknown style_id must return empty string (silent skip, no crash)."""
    block = as_few_shot_block("this-style-does-not-exist")
    assert block == ""


def test_every_preset_has_two_archetype_cards():
    """After the story/carousel batch, every preset carries exactly two
    golden cards (launch + story/carousel) — appends must never shadow
    earlier archetypes."""
    for slug in list_styles():
        cards = get_golden_cards(slug)
        assert len(cards) == 2, f"{slug}: expected 2 golden cards, got {len(cards)}"
        assert all(c["score"] >= 9.0 for c in cards)


def test_get_golden_card_picks_highest_scored_archetype():
    """With multiple archetypes per style, the single-card lookup must return
    the best-scored one (one reference = roughly half the few-shot token cost)."""
    for slug in list_styles():
        cards = get_golden_cards(slug)
        if not cards:
            continue
        best = get_golden_card(slug)
        assert best is not None
        assert best["score"] == max(c["score"] for c in cards)


def test_best_is_stable_on_ties():
    a = {"style_id": "x", "score": 9.2, "brief": "first"}
    b = {"style_id": "x", "score": 9.2, "brief": "second"}
    assert _best([a, b])["brief"] == "first"  # earliest line wins on a tie


def test_as_few_shot_block_injects_exactly_one_card():
    """Even with two golden cards per style, the block embeds a single
    reference — the token-cheap choice."""
    for slug in ("warm-editorial-minimalist", "utility-planner-ornamental"):
        block = as_few_shot_block(slug)
        assert block.count("GOLDEN REFERENCE CARD") == 1
        best = get_golden_card(slug)
        assert f"{best['score']:.1f}" in block


def test_every_golden_card_style_exists_in_presets():
    """Every golden card's style_id must correspond to an actual preset file."""
    valid_slugs = set(list_styles())
    for slug in list_styles():
        gc = get_golden_card(slug)
        if gc is not None:
            assert gc["style_id"] in valid_slugs


def test_every_golden_card_has_required_card_fields():
    """Each golden card's card_json must pass basic schema inspection
    (all mandatory fields present)."""
    required = [
        "concept",
        "magic_media_prompt",
        "negative_prompt",
        "aspect_ratio",
        "target_tool",
        "text_zone",
        "layer_typography_architecture",
        "direct_action_tip",
    ]
    for slug in list_styles():
        gc = get_golden_card(slug)
        if gc is None:
            continue
        card = gc["card_json"]
        for field in required:
            assert field in card, f"{slug}: golden card missing '{field}'"
