"""Offline tests for the CaVDesign Mockup Director backend."""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from PIL import Image

from src.mockup_engine import (
    MOCKUP_TYPES,
    PRESERVATION_CLAUSE,
    MockupEngineError,
    generate_mockup_set,
)


def _image_bytes(width: int = 600, height: int = 900) -> bytes:
    img = Image.new("RGB", (width, height), (22, 30, 42))
    # Add a second large colour region so palette extraction has real work.
    for x in range(width // 2, width):
        for y in range(height):
            img.putpixel((x, y), (180, 72, 60))
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _valid_payload() -> dict:
    mockups = []
    for mockup_type in MOCKUP_TYPES:
        mockups.append(
            {
                "type": mockup_type,
                "title": f"{mockup_type} scene",
                "purpose": f"Purpose for {mockup_type}",
                "prompt": (
                    "Photorealistic premium interior product mockup with controlled side light, "
                    "realistic materials, natural perspective, editorial 50mm photography and "
                    "the uploaded design presented as the clear visual hero."
                ),
                "negative_prompt": "watermark, low resolution, visual clutter",
            }
        )

    return {
        "asset_analysis": {
            "product_type": "movie poster",
            "asset_category": "printable wall art",
            "orientation": "landscape",  # intentionally wrong; engine must override it
            "visual_style": "cinematic neo-noir",
            "mood": ["dramatic", "moody"],
            "dominant_colors": ["#FFFFFF"],  # intentionally fake; engine must override it
            "composition_notes": "Central focal image with strong title hierarchy.",
            "target_customer": "Film and cinema decor enthusiasts.",
            "physical_presentation_assumption": "Best presented as a framed matte art print.",
        },
        "mockup_strategy": {
            "presentation_goal": "Premium cinematic collectible presentation.",
            "primary_environment": "Dark editorial apartment interior.",
            "material_direction": "Matte fine-art paper and black aluminium frame.",
            "lighting_direction": "Warm low-key side lighting.",
            "camera_direction": "Eye-level editorial interior photography, 50mm lens.",
            "styling_notes": "Sparse props and restrained cinematic styling.",
        },
        "mockups": mockups,
    }


class _FakeVisionClient:
    def __init__(self, payload: dict, repaired: dict | None = None):
        self.payload = payload
        self.repaired = repaired
        self.prompt = ""
        self.repair_called = False

    def deconstruct_image(self, image_bytes: bytes, mime_type: str, *, prompt: str) -> str:
        self.prompt = prompt
        return json.dumps(self.payload)

    def repair_json(self, card_json: str, error_message: str, *, prompt: str = "") -> str:
        self.repair_called = True
        return json.dumps(self.repaired if self.repaired is not None else self.payload)


def test_generates_six_ordered_mockups_and_preserves_artwork():
    fake = _FakeVisionClient(_valid_payload())
    result = generate_mockup_set(
        _image_bytes(),
        "image/png",
        marketplace="Etsy",
        vision_client=fake,  # type: ignore[arg-type]
    )

    assert [item["type"] for item in result["mockups"]] == list(MOCKUP_TYPES)
    assert len(result["mockups"]) == 6
    assert result["prompt_version"] == "mockup-director-v1"

    for item in result["mockups"]:
        assert PRESERVATION_CLAUSE in item["prompt"]
        assert "changed typography" in item["negative_prompt"]


def test_pixel_palette_and_orientation_override_model_guesses():
    fake = _FakeVisionClient(_valid_payload())
    result = generate_mockup_set(
        _image_bytes(width=400, height=800),
        "image/png",
        vision_client=fake,  # type: ignore[arg-type]
    )

    assert result["asset_analysis"]["orientation"] == "portrait"
    assert result["source"]["orientation"] == "portrait"
    assert result["asset_analysis"]["dominant_colors"] == result["source"]["dominant_palette"]
    assert "#FFFFFF" not in result["source"]["dominant_palette"]


def test_prompt_contains_real_source_metadata_and_context():
    fake = _FakeVisionClient(_valid_payload())
    generate_mockup_set(
        _image_bytes(width=500, height=500),
        "image/png",
        marketplace="Etsy",
        product_type_hint="film poster",
        audience_hint="cinephiles",
        creative_direction="premium dark editorial",
        vision_client=fake,  # type: ignore[arg-type]
    )

    assert "500x500" in fake.prompt
    assert "source orientation: square" in fake.prompt
    assert "marketplace context: Etsy" in fake.prompt
    assert "product type hint: film poster" in fake.prompt
    assert "audience hint: cinephiles" in fake.prompt
    assert "premium dark editorial" in fake.prompt


def test_invalid_first_payload_uses_one_repair_pass():
    broken = _valid_payload()
    broken["mockups"] = broken["mockups"][:2]
    repaired = _valid_payload()
    fake = _FakeVisionClient(broken, repaired=repaired)

    result = generate_mockup_set(
        _image_bytes(),
        "image/png",
        vision_client=fake,  # type: ignore[arg-type]
    )

    assert fake.repair_called is True
    assert len(result["mockups"]) == 6


def test_unreadable_image_is_rejected_before_api_call():
    fake = _FakeVisionClient(_valid_payload())
    with pytest.raises(MockupEngineError, match="readable image"):
        generate_mockup_set(
            b"this-is-not-an-image",
            "image/png",
            vision_client=fake,  # type: ignore[arg-type]
        )
