"""Offline tests for the interactive mockup art-direction workflow."""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from PIL import Image

from src.mockup_engine import PRESERVATION_CLAUSE, MOCKUP_TYPES, MockupEngineError
from src.mockup_workflow import (
    CREATIVE_SEEDS,
    USAGE_MAP,
    analyze_artwork,
    build_final_prompt,
    clarifying_questions_for,
    creative_directions_from,
    refine_strategy,
)


def _image_bytes(width: int = 600, height: int = 900) -> bytes:
    img = Image.new("RGB", (width, height), (22, 30, 42))
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


_DISTINCT_PROMPTS = {
    "hero": "The artwork presented as the hero on a clean studio backdrop with soft directional light.",
    "lifestyle": "The artwork placed in a bright modern living space with a sofa and side table.",
    "close_up": "Close-up detail of the artwork surface and material finish.",
    "scale": "Wide shot showing the artwork's real size against surrounding objects.",
    "alternative_scene": "The artwork styled in an alternate contemporary interior setting.",
    "clean_product": "Isolated product shot of the artwork on a seamless neutral background.",
}


def _asset_analysis(*, product_category: str = "wall_art") -> dict:
    return {
        "product_type": "movie poster",
        "asset_category": "printable wall art",
        "product_category": product_category,
        "presentation_mode": "physical",
        "orientation": "portrait",
        "aspect_ratio": "2:3",
        "visual_style": "cinematic",
        "mood": ["dramatic"],
        "dominant_colors": ["#1A1A2E"],
        "content_summary": "A moody central character.",
        "composition_notes": "Centered.",
        "audience": "Cinephiles.",
        "target_customer": "Film decor enthusiasts.",
        "physical_presentation_assumption": "Framed print.",
    }


def _engine_payload(*, product_category: str = "wall_art") -> dict:
    mockups = []
    for mockup_type in MOCKUP_TYPES:
        mockups.append(
            {
                "type": mockup_type,
                "title": f"{mockup_type} scene",
                "purpose": f"Purpose for {mockup_type}",
                "prompt": _DISTINCT_PROMPTS[mockup_type],
                "negative_prompt": "watermark, low resolution",
            }
        )
    return {
        "asset_analysis": _asset_analysis(product_category=product_category),
        "mockup_strategy": {
            "presentation_goal": "Premium presentation.",
            "primary_environment": "Styled interior.",
            "material_direction": "Matte paper.",
            "lighting_direction": "Warm side light.",
            "camera_direction": "50mm.",
            "styling_notes": "Sparse props.",
        },
        "mockups": mockups,
    }


def _valid_analysis(*, product_category: str = "wall_art") -> dict:
    """A workflow-ready analysis dict (asset_analysis + recommended_directions)."""
    seeds = CREATIVE_SEEDS.get(product_category, CREATIVE_SEEDS["generic"])
    directions = [
        {
            "id": seed["id"],
            "title": seed["title"],
            "rationale": f"Rationale for {seed['id']}.",
            "environment": seed["environment"],
            "mood": seed["mood"],
            "presentation_style": seed["presentation_style"],
            "recommended": i == 0,
        }
        for i, seed in enumerate(seeds)
    ]
    return {
        "asset_analysis": _asset_analysis(product_category=product_category),
        "recommended_directions": directions,
        "mockups": [],
    }


class _FakeVisionClient:
    def __init__(self, payload: dict):
        self.payload = payload

    def deconstruct_image(self, image_bytes: bytes, mime_type: str, *, prompt: str) -> str:
        return json.dumps(self.payload)

    def repair_json(self, card_json: str, error_message: str, *, prompt: str = "") -> str:
        return json.dumps(self.payload)


# --------------------------------------------------------------------------- #
# Creative direction inference.
# --------------------------------------------------------------------------- #


def test_creative_directions_are_not_mockup_type_ids():
    analysis = _valid_analysis()
    ids = [d["id"] for d in analysis["recommended_directions"]]
    assert ids
    assert set(ids).isdisjoint(set(MOCKUP_TYPES))


def test_creative_directions_mark_exactly_one_recommended_with_rationale():
    directions = creative_directions_from(_asset_analysis())
    assert 2 <= len(directions) <= 4
    recommended = [d for d in directions if d["recommended"]]
    assert len(recommended) == 1
    for direction in directions:
        assert direction["title"]
        assert direction["rationale"]
        assert direction["environment"]
        assert direction["presentation_style"]
    assert set(d["id"] for d in directions).isdisjoint(set(MOCKUP_TYPES))


def test_recommendation_matches_artwork_mood():
    # A dark, cinematic artwork should recommend a dark cinematic direction.
    directions = creative_directions_from(_asset_analysis())
    best = next(d for d in directions if d["recommended"])
    assert best["id"] == "moody_collector"


# --------------------------------------------------------------------------- #
# Step 1: analyze.
# --------------------------------------------------------------------------- #


def test_analyze_includes_recommended_directions_and_questions():
    fake = _FakeVisionClient(_engine_payload(product_category="wall_art"))
    result = analyze_artwork(
        _image_bytes(),
        "image/png",
        product_type_hint="wall art",
        vision_client=fake,  # type: ignore[arg-type]
    )

    directions = result["recommended_directions"]
    assert 2 <= len(directions) <= 4
    assert len([d for d in directions if d["recommended"]]) == 1
    assert set(d["id"] for d in directions).isdisjoint(set(MOCKUP_TYPES))

    best = result["best_recommendation"]
    assert best["id"] == next(d for d in directions if d["recommended"])["id"]
    assert "because" in best["message"].lower()

    assert result["clarification_needed"] is True
    questions = result["clarifying_questions"]
    assert 1 <= len(questions) <= 5


def test_clarifying_questions_respect_count_limit():
    for category in ("wall_art", "poster", "phone_wallpaper", "album_art", "generic"):
        analysis = {"asset_analysis": _asset_analysis(product_category=category)}
        assert 1 <= len(clarifying_questions_for(analysis["asset_analysis"])) <= 5


def test_clarifying_questions_are_category_aware():
    wall = clarifying_questions_for(_asset_analysis(product_category="wall_art"))
    phone = clarifying_questions_for(_asset_analysis(product_category="phone_wallpaper"))

    wall_text = " ".join(q["question"] for q in wall).lower()
    phone_text = " ".join(q["question"] for q in phone).lower()

    assert "framed or unframed" in wall_text
    assert "portrait phone" in phone_text
    # Physical print questions should not drive a digital-only product.
    assert "framed or unframed" not in phone_text


def test_clarifying_questions_reflect_artwork_mood():
    dark = clarifying_questions_for(_asset_analysis())
    dark_text = " ".join(q["question"] for q in dark).lower()
    assert "darker cinematic" in dark_text

    bright_asset = _asset_analysis()
    bright_asset["mood"] = ["minimal", "clean"]
    bright_asset["visual_style"] = "modern minimal"
    bright = clarifying_questions_for(bright_asset)
    bright_text = " ".join(q["question"] for q in bright).lower()
    assert "clean gallery" in bright_text


# --------------------------------------------------------------------------- #
# Step 2: refine.
# --------------------------------------------------------------------------- #


def test_refine_applies_answer_overrides_and_selected_direction():
    strategy = refine_strategy(
        _valid_analysis(),
        "moody_collector",
        {"setting": "Home interior", "lighting": "Dramatic moody lighting"},
    )

    assert strategy["direction"]["id"] == "moody_collector"
    assert strategy["category"] == "wall_art"
    assert strategy["listing_role"] == "hero"
    assert strategy["environment"] == "realistic styled home interior"
    assert strategy["lighting"] == "dramatic moody lighting"
    assert strategy["applied_answers"] == {
        "setting": "Home interior",
        "lighting": "Dramatic moody lighting",
    }


def test_refine_honours_listing_role():
    strategy = refine_strategy(_valid_analysis(), "moody_collector", {}, listing_role="close_up")
    assert strategy["listing_role"] == "close_up"
    assert strategy["surface_or_frame"]  # archetype surface for close_up


def test_refine_surfaces_only_remaining_questions():
    partial = refine_strategy(_valid_analysis(), "moody_collector", {"setting": "Studio scene"})
    answered = {"setting"}
    expected_remaining = [
        q["key"]
        for q in clarifying_questions_for(_asset_analysis())
        if q["key"] not in answered
    ]
    assert [q["key"] for q in partial["remaining_questions"]] == expected_remaining

    full_answers = {
        "framing": "Framed",
        "tone": "Premium editorial",
        "setting": "Studio scene",
        "lighting": "Dramatic moody lighting",
        "audience": "Collector-style",
    }
    complete = refine_strategy(_valid_analysis(), "moody_collector", full_answers)
    assert complete["remaining_questions"] == []


def test_refine_rejects_unknown_direction():
    with pytest.raises(MockupEngineError, match="Unknown creative direction"):
        refine_strategy(_valid_analysis(), "not_a_direction", {})


def test_refine_rejects_unknown_listing_role():
    with pytest.raises(MockupEngineError, match="Unknown listing role"):
        refine_strategy(_valid_analysis(), "moody_collector", {}, listing_role="bogus")


# --------------------------------------------------------------------------- #
# Step 3: generate.
# --------------------------------------------------------------------------- #


def test_generate_returns_final_prompt_with_preservation():
    result = build_final_prompt(
        _valid_analysis(),
        "moody_collector",
        "hero",
        {"framing": "Framed"},
    )

    assert result["direction"]["id"] == "moody_collector"
    assert result["listing_role"] == "hero"
    assert result["recommended_usage"] == "Etsy hero image / first listing image"
    assert PRESERVATION_CLAUSE in result["final_prompt"]
    assert result["negative_prompt"]
    assert isinstance(result["preservation_notes"], list) and result["preservation_notes"]
    assert "Client preferences: framing=Framed" in result["final_prompt"]


def test_generate_combines_creative_direction_and_listing_role():
    analysis = _valid_analysis()
    result = build_final_prompt(analysis, "moody_collector", "clean_product")
    assert "Moody Collector Apartment" in result["final_prompt"]
    assert "clean product mockup" in result["final_prompt"]
    assert result["recommended_usage"] == "Clean product-only listing image"


def test_generate_falls_back_when_no_mockups_available():
    analysis = _valid_analysis()
    analysis["mockups"] = []
    result = build_final_prompt(analysis, "moody_collector", "hero")
    assert PRESERVATION_CLAUSE in result["final_prompt"]
    assert result["recommended_usage"] == "Etsy hero image / first listing image"


def test_generate_rejects_unknown_direction():
    with pytest.raises(MockupEngineError, match="Unknown creative direction"):
        build_final_prompt(_valid_analysis(), "bogus", "hero")


def test_generate_usage_map_covers_all_directions():
    analysis = _valid_analysis()
    assert set(USAGE_MAP) == set(MOCKUP_TYPES)
    for listing_role in MOCKUP_TYPES:
        result = build_final_prompt(analysis, "moody_collector", listing_role)
        assert result["recommended_usage"]
        assert PRESERVATION_CLAUSE in result["final_prompt"]
