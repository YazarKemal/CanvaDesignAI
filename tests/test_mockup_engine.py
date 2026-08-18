"""Offline tests for the CaVDesign Mockup Director backend."""

from __future__ import annotations

import json
import os
from io import BytesIO

import pytest
from PIL import Image

from src.mockup_engine import (
    ART_DIRECTION_FIELDS,
    MOCKUP_TYPES,
    PRESERVATION_CLAUSE,
    VISION_TARGET_BYTES,
    MockupEngineError,
    _archetype_for,
    _assert_scene_diversity,
    _composite_for_encoding,
    _prepare_vision_image,
    _presentation_is_appropriate,
    _resolve_product_category,
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


_DISTINCT_PROMPTS = {
    "hero": "The artwork presented as the hero on a clean studio backdrop with soft directional light.",
    "lifestyle": "The artwork placed in a bright modern living space with a sofa and side table.",
    "close_up": "Close-up detail of the artwork surface and material finish.",
    "scale": "Wide shot showing the artwork's real size against surrounding objects.",
    "alternative_scene": "The artwork styled in an alternate contemporary interior setting.",
    "clean_product": "Isolated product shot of the artwork on a seamless neutral background.",
}


def _mockup_item(mockup_type: str, *, with_art_direction: bool = True) -> dict:
    item = {
        "type": mockup_type,
        "title": f"{mockup_type} scene",
        "purpose": f"Purpose for {mockup_type}",
        "prompt": _DISTINCT_PROMPTS[mockup_type],
        "negative_prompt": "watermark, low resolution",
    }
    if with_art_direction:
        item.update(
            {
                "scene_direction": f"{mockup_type} direction",
                "environment": f"{mockup_type} environment",
                "surface_or_frame": f"{mockup_type} surface",
                "lighting": "soft light",
                "camera": "50mm",
                "composition": f"{mockup_type} composition",
                "artwork_placement": f"{mockup_type} placement",
                "realism_notes": f"{mockup_type} realism",
            }
        )
    return item


def _valid_payload(*, with_art_direction: bool = True) -> dict:
    return {
        "asset_analysis": {
            "product_type": "movie poster",
            "asset_category": "printable wall art",
            "orientation": "landscape",  # intentionally wrong; engine must override it
            "aspect_ratio": "4:3",  # intentionally wrong; engine must override it
            "visual_style": "cinematic neo-noir",
            "mood": ["dramatic", "moody"],
            "dominant_colors": ["#FFFFFF"],  # intentionally fake; engine must override it
            "content_summary": "A moody central character with dramatic title typography.",
            "composition_notes": "Central focal image with strong title hierarchy.",
            "audience": "Film and cinema decor enthusiasts.",
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
        "mockups": [
            _mockup_item(mockup_type, with_art_direction=with_art_direction)
            for mockup_type in MOCKUP_TYPES
        ],
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


class _RecordingVisionClient(_FakeVisionClient):
    """A fake that also records the exact bytes/mime it was handed for Vision."""

    def __init__(self, payload: dict, repaired: dict | None = None):
        super().__init__(payload, repaired)
        self.received_bytes: bytes | None = None
        self.received_mime: str | None = None

    def deconstruct_image(self, image_bytes: bytes, mime_type: str, *, prompt: str) -> str:
        self.received_bytes = image_bytes
        self.received_mime = mime_type
        return super().deconstruct_image(image_bytes, mime_type, prompt=prompt)


# --------------------------------------------------------------------------- #
# Core generation.
# --------------------------------------------------------------------------- #


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
    assert result["prompt_version"] == "mockup-director-v2"

    for item in result["mockups"]:
        assert PRESERVATION_CLAUSE in item["prompt"]
        assert "changed typography" in item["negative_prompt"]
        for field in ("scene_direction", *ART_DIRECTION_FIELDS):
            assert isinstance(item.get(field), str) and item[field]


def test_pixel_palette_and_orientation_override_model_guesses():
    fake = _FakeVisionClient(_valid_payload())
    result = generate_mockup_set(
        _image_bytes(width=400, height=800),
        "image/png",
        vision_client=fake,  # type: ignore[arg-type]
    )

    assert result["asset_analysis"]["orientation"] == "portrait"
    assert result["asset_analysis"]["aspect_ratio"] == "1:2"
    assert result["source"]["orientation"] == "portrait"
    assert result["source"]["aspect_ratio"] == "1:2"
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
    assert "source aspect ratio: 1:1" in fake.prompt
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


# --------------------------------------------------------------------------- #
# Phase 2: product-aware routing.
# --------------------------------------------------------------------------- #


def test_resolve_product_category_routes_common_hints():
    assert _resolve_product_category("film poster") == "poster"
    assert _resolve_product_category("phone wallpaper") == "phone_wallpaper"
    assert _resolve_product_category("wall art print") == "wall_art"
    assert _resolve_product_category("t-shirt") == "apparel_graphic"
    assert _resolve_product_category("book cover") == "book_cover"
    assert _resolve_product_category("planner page") == "journal_planner"
    assert _resolve_product_category("sticker sheet") == "sticker"
    assert _resolve_product_category("album cover") == "album_art"
    assert _resolve_product_category("wedding invitation") == "invitation"
    assert _resolve_product_category("") is None
    assert _resolve_product_category(None) is None  # type: ignore[arg-type]


def test_category_surfaces_on_response_and_source():
    fake = _FakeVisionClient(_valid_payload())
    result = generate_mockup_set(
        _image_bytes(),
        "image/png",
        product_type_hint="book cover",
        vision_client=fake,  # type: ignore[arg-type]
    )

    assert result["asset_analysis"]["product_category"] == "book_cover"
    assert result["asset_analysis"]["presentation_mode"] == "physical"
    assert result["source"]["product_category"] == "book_cover"


# --------------------------------------------------------------------------- #
# Phase 2: deterministic archetype / presentation.
# --------------------------------------------------------------------------- #


def test_archetype_is_physically_or_digitally_appropriate():
    # Physical print category -> framed/printed surface.
    wall_hero = _archetype_for("wall_art", "hero")
    assert "frame" in wall_hero["surface_or_frame"]
    assert "printed" in _archetype_for("poster", "clean_product")["surface_or_frame"]

    # Digital-only category -> device surface, never paper/frame.
    phone_hero = _archetype_for("phone_wallpaper", "hero")
    assert phone_hero["surface_or_frame"] == "smartphone OLED screen"
    assert "paper" not in phone_hero["surface_or_frame"]
    assert "frame" not in phone_hero["surface_or_frame"]


def test_art_direction_fields_backfilled_from_archetype():
    # Payload omits scene_direction + art-direction fields; engine must fill them.
    fake = _FakeVisionClient(_valid_payload(with_art_direction=False))
    result = generate_mockup_set(
        _image_bytes(),
        "image/png",
        product_type_hint="phone wallpaper",
        vision_client=fake,  # type: ignore[arg-type]
    )

    hero = next(item for item in result["mockups"] if item["type"] == "hero")
    assert hero["scene_direction"] == "smartphone on a display stand as the hero"
    assert hero["environment"] == "modern minimal desk or clean background"
    assert hero["surface_or_frame"] == "smartphone OLED screen"
    for field in ART_DIRECTION_FIELDS:
        assert isinstance(hero.get(field), str) and hero[field]


def test_digital_category_rejects_physical_presentation():
    payload = _valid_payload()
    # Inject a clearly inappropriate physical-presentation prompt into the hero.
    hero = next(item for item in payload["mockups"] if item["type"] == "hero")
    hero["prompt"] = "Artwork printed on canvas and framed on a gallery wall."
    assert (
        _presentation_is_appropriate("phone_wallpaper", hero) is False
    )


def test_physical_category_rejects_device_presentation():
    payload = _valid_payload()
    hero = next(item for item in payload["mockups"] if item["type"] == "hero")
    hero["prompt"] = "Poster displayed as a smartphone lock screen wallpaper."
    assert _presentation_is_appropriate("wall_art", hero) is False
    # Hybrid categories are never rejected on presentation grounds.
    assert _presentation_is_appropriate("album_art", hero) is True


def test_valid_presentation_passes_appropriateness():
    hero = _valid_payload()["mockups"][0]
    assert _presentation_is_appropriate("wall_art", hero) is True
    assert _presentation_is_appropriate("phone_wallpaper", hero) is True


# --------------------------------------------------------------------------- #
# Phase 2: scene diversity.
# --------------------------------------------------------------------------- #


def test_near_duplicate_scenes_rejected():
    with pytest.raises(MockupEngineError, match="near-duplicates"):
        _assert_scene_diversity(
            {
                "hero": "A premium framed print on a gallery wall with soft light.",
                "lifestyle": "A premium framed print on a gallery wall with soft light.",
            }
        )


def test_distinct_scenes_pass_diversity():
    _assert_scene_diversity(
        {
            "hero": "Framed print on a gallery wall.",
            "lifestyle": "Print styled on a desk with a laptop and coffee.",
            "close_up": "Macro detail of the paper texture.",
        }
    )


# --------------------------------------------------------------------------- #
# Vision payload optimisation.
# --------------------------------------------------------------------------- #


def _noise_png(width: int = 1024, height: int = 1536) -> bytes:
    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _noise_rgba_png(width: int = 400, height: int = 600) -> bytes:
    img = Image.frombytes("RGBA", (width, height), os.urandom(width * height * 4))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_large_png_is_compressed_for_vision():
    data = _noise_png()
    vision_bytes, mime, meta = _prepare_vision_image(data, "image/png")
    assert mime == "image/jpeg"
    assert meta["vision_optimized"] is True
    assert meta["vision_byte_size"] < meta["original_byte_size"]
    assert meta["vision_byte_size"] <= VISION_TARGET_BYTES
    assert len(vision_bytes) <= VISION_TARGET_BYTES


def test_vision_optimisation_keeps_original_metadata_and_palette():
    data = _noise_png(1024, 1536)
    fake = _RecordingVisionClient(_valid_payload())
    result = generate_mockup_set(data, "image/png", vision_client=fake)  # type: ignore[arg-type]

    source = result["source"]
    # Everything pixel-derived stays anchored to the ORIGINAL bytes.
    assert source["width"] == 1024 and source["height"] == 1536
    assert result["asset_analysis"]["orientation"] == "portrait"
    assert result["asset_analysis"]["aspect_ratio"] == "2:3"
    assert result["asset_analysis"]["dominant_colors"] == source["dominant_palette"]

    # The Vision copy is optimised and diagnostics are surfaced (no base64).
    assert source["vision_optimized"] is True
    assert source["vision_mime_type"] == "image/jpeg"
    assert source["original_byte_size"] == len(data)
    assert source["vision_byte_size"] < len(data)
    assert source["vision_byte_size"] <= VISION_TARGET_BYTES
    assert "base64" not in {key.lower() for key in source}

    # The fake Vision client actually received the optimised JPEG copy.
    assert fake.received_mime == "image/jpeg"
    assert fake.received_bytes is not None
    assert len(fake.received_bytes) == source["vision_byte_size"]
    assert len(fake.received_bytes) < len(data)


def test_small_image_not_unnecessarily_upscaled():
    img = Image.new("RGB", (120, 160), (200, 30, 40))
    buf = BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    _, mime, meta = _prepare_vision_image(data, "image/png")
    assert meta["vision_optimized"] is False
    assert mime == "image/png"
    assert meta["vision_width"] == 120 and meta["vision_height"] == 160
    assert meta["vision_byte_size"] == meta["original_byte_size"]


def test_transparent_image_composited_safely():
    # A large transparent image must not crash and must be flattened to RGB JPEG.
    data = _noise_rgba_png()
    vision_bytes, mime, meta = _prepare_vision_image(data, "image/png")
    assert mime == "image/jpeg"
    assert meta["vision_optimized"] is True
    assert len(vision_bytes) <= VISION_TARGET_BYTES


def test_composite_flattens_alpha_to_rgb():
    img = Image.new("RGBA", (12, 12), (255, 0, 0, 128))
    assert _composite_for_encoding(img).mode == "RGB"
