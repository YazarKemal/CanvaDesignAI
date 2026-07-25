"""Tests for the /ingest/deconstruct and /ingest/approve FastAPI endpoints."""

import json
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_card_dict() -> dict:
    """A valid card dict matching TEMPLATE_CARD_SCHEMA."""
    return {
        "concept": "Test Template",
        "aspect_ratio": "1:1 (1080x1080)",
        "target_tool": "Canva Native Layout Engine",
        "text_zone": "top",
        "canva_keywords": ["editorial", "minimal"],
        "raster_background": {
            "magic_media_prompt": (
                "A Canva stock photo search query for a warm coffee shop interior "
                "with natural window light, editorial composition, and deliberate "
                "negative space at the top for typography overlay."
            ),
            "negative_prompt": "no AI-generated imagery, no text, no watermark, busy background",
            "layout_style": "Minimalist",
        },
        "vector_elements": {
            "thin_divider": "horizontal 0.5px rule in muted gold, centered",
        },
        "native_typography": {
            "headline": "Hello World",
            "subtext": "A short subtext line.",
            "headline_pt": 72,
            "subtext_pt": 18,
            "color_palette": ["#3B2A1E", "#B8936E", "#E8DDD0", "#8B9D6B", "#D4C5B9"],
            "fonts": {"headline_font": "Montserrat Bold", "body_font": "Cormorant Garamond Regular"},
            "alignment_zone": "top 30% of canvas, left-aligned with 48px margin in the top zone",
            "micro_tags": {
                "volume_line": "VOL.01 / 2026",
                "category_line": "EDITORIAL BRANDING",
                "origin_line": "CRAFTED IN TURKEY",
                "micro_pt": 9,
                "micro_color": "#B8936E",
                "micro_font": "Inter Regular",
                "micro_spacing": "24 px below subtext",
            },
        },
        "direct_action_tip": [
            "PRIMARY: Use Canva Native Layout Engine to search stock photos for...",
            "ALTERNATIVE: Open Canva → Create Design → 1080x1080...",
        ],
    }


def _deconstructed_card() -> dict:
    """A card as returned by deconstruct_template (with provenance, approved=False)."""
    card = _valid_card_dict()
    card["source_type"] = "upload"
    card["source_ref"] = "test-template.png"
    card["ingested_at"] = "2026-07-25T00:00:00Z"
    card["archetype"] = "instagram_story"
    card["category"] = "lansman"
    card["format"] = "9:16"
    card["approved"] = False
    return card


def _make_fake_image(mime: str = "image/png", size: int = 1024) -> bytes:
    """Return minimal valid bytes for a given mime type."""
    if "png" in mime:
        # Minimal valid PNG (1x1 pixel, black)
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
            b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        ).ljust(size, b"\x00")
    if "jpeg" in mime:
        # Minimal valid JPEG
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
            b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
            b"\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00"
            b"\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01"
            b"\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02"
            b"\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03"
            b"\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04"
            b"\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15"
            b"\x52\xd1\xf0$3br\x82\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVW"
            b"XYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95"
            b"\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4"
            b"\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3"
            b"\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea"
            b"\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00"
            b"\x02\x11\x03\x11\x00?\x00\xf9\xff\x00"
        ).ljust(size, b"\x00")
    # webp — minimal RIFF/WEBP header
    return (
        b"RIFF\x04\x00\x00\x00WEBPVP8 \x00\x00\x00\x00\x00\x00\x00\x00"
    ).ljust(size, b"\x00")


def _fake_deconstruct(image_bytes, mime_type, *, source_type, source_ref,
                      archetype, category, canvas_format, client=None):
    """Fake deconstruct_template that returns a stamped card."""
    card = _valid_card_dict()
    card["source_type"] = source_type
    card["source_ref"] = source_ref
    card["ingested_at"] = "2026-07-25T00:00:00Z"
    card["archetype"] = archetype
    card["category"] = category
    card["format"] = canvas_format
    card["approved"] = False
    return card


# ---------------------------------------------------------------------------
# /ingest/deconstruct tests
# ---------------------------------------------------------------------------


class TestIngestDeconstruct:
    """POST /ingest/deconstruct — multipart form upload."""

    def test_happy_path(self):
        """Valid image + metadata → 200 with deconstructed card."""
        with patch.object(api, "deconstruct_template", wraps=_fake_deconstruct):
            client = TestClient(api.app)
            resp = client.post(
                "/ingest/deconstruct",
                data={
                    "source_type": "upload",
                    "source_ref": "test.png",
                    "archetype": "instagram_story",
                    "category": "lansman",
                    "canvas_format": "9:16",
                },
                files={"file": ("test.png", io.BytesIO(_make_fake_image("image/png")), "image/png")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["approved"] is False
        assert body["concept"] == "Test Template"
        assert body["source_type"] == "upload"
        assert body["source_ref"] == "test.png"
        assert body["archetype"] == "instagram_story"
        assert body["category"] == "lansman"
        assert body["format"] == "9:16"
        assert "ingested_at" in body

    def test_rejects_wrong_mime_type(self):
        """Non-image mime type → 400."""
        client = TestClient(api.app)
        resp = client.post(
            "/ingest/deconstruct",
            data={
                "source_type": "upload",
                "source_ref": "test.pdf",
                "archetype": "x",
                "category": "x",
                "canvas_format": "x",
            },
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )

        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    def test_rejects_oversized_file(self):
        """File exceeding 10 MB → 400."""
        client = TestClient(api.app)
        big = b"\x89PNG\r\n" + b"\x00" * (api.MAX_FILE_SIZE + 1)
        resp = client.post(
            "/ingest/deconstruct",
            data={
                "source_type": "upload",
                "source_ref": "big.png",
                "archetype": "x",
                "category": "x",
                "canvas_format": "x",
            },
            files={"file": ("big.png", io.BytesIO(big), "image/png")},
        )

        assert resp.status_code == 400
        assert "too large" in resp.json()["detail"].lower()

    def test_rejects_empty_file(self):
        """Empty file upload → 400."""
        client = TestClient(api.app)
        resp = client.post(
            "/ingest/deconstruct",
            data={
                "source_type": "upload",
                "source_ref": "empty.png",
                "archetype": "x",
                "category": "x",
                "canvas_format": "x",
            },
            files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
        )

        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_surfaces_vision_client_error(self):
        """VisionClientError from deconstruct_template → 400 with message."""
        from src.vision_client import VisionClientError

        def boom(*args, **kwargs):
            raise VisionClientError("OPENAI_API_KEY is not set.")

        with patch.object(api, "deconstruct_template", boom):
            client = TestClient(api.app)
            resp = client.post(
                "/ingest/deconstruct",
                data={
                    "source_type": "upload",
                    "source_ref": "x",
                    "archetype": "x",
                    "category": "x",
                    "canvas_format": "x",
                },
                files={"file": ("test.png", io.BytesIO(_make_fake_image()), "image/png")},
            )

        assert resp.status_code == 400
        assert "OPENAI_API_KEY" in resp.json()["detail"]

    def test_surfaces_template_ingest_error(self):
        """TemplateIngestError (e.g. broken JSON from vision) → 400."""
        from src.template_ingest import TemplateIngestError

        def boom(*args, **kwargs):
            raise TemplateIngestError("Vision model did not return valid JSON.")

        with patch.object(api, "deconstruct_template", boom):
            client = TestClient(api.app)
            resp = client.post(
                "/ingest/deconstruct",
                data={
                    "source_type": "upload",
                    "source_ref": "x",
                    "archetype": "x",
                    "category": "x",
                    "canvas_format": "x",
                },
                files={"file": ("test.png", io.BytesIO(_make_fake_image()), "image/png")},
            )

        assert resp.status_code == 400
        assert "valid JSON" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /ingest/approve tests
# ---------------------------------------------------------------------------


class TestIngestApprove:
    """POST /ingest/approve — JSON body."""

    def test_happy_path(self, tmp_path):
        """Valid approved card is appended to the corpus."""
        card = _deconstructed_card()

        # Use a temp corpus so we don't touch the real data file.
        with patch.object(api, "append_template_card") as mock_append:
            mock_append.return_value = tmp_path / "test.jsonl"

            with patch.object(api, "load_template_cards", return_value=[card]):
                client = TestClient(api.app)
                resp = client.post(
                    "/ingest/approve",
                    json={"card": card, "reviewer_note": "Looks great."},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["total_cards"] == 1

        # append_template_card should have been called with an approved card
        call_args = mock_append.call_args[0]
        approved_record = call_args[0]
        assert approved_record["approved"] is True
        assert approved_record["reviewer_note"] == "Looks great."
        assert "approved_at" in approved_record

    def test_rejects_broken_card(self):
        """A card that fails validation (missing required field) → 400."""
        # Remove a required field so validation fails
        broken = _deconstructed_card()
        broken["approved"] = False
        del broken["concept"]

        client = TestClient(api.app)
        resp = client.post("/ingest/approve", json={"card": broken})

        assert resp.status_code == 400
        # Error message should mention the validation failure
        detail = resp.json()["detail"]
        assert "concept" in detail.lower() or "schema" in detail.lower()

    def test_rejects_duplicate_source_ref(self, tmp_path):
        """A duplicate source_ref should be rejected at the dedup gate."""
        card = _deconstructed_card()
        card["source_ref"] = "https://example.com/already-exists"

        # Simulate dedup rejection from append_template_card
        from src.template_ingest import TemplateIngestError

        def fake_append(record, path=None, *, force=False):
            raise TemplateIngestError(
                "Template with source_ref='https://example.com/already-exists' already exists in the corpus."
            )

        with patch.object(api, "append_template_card", fake_append):
            client = TestClient(api.app)
            resp = client.post("/ingest/approve", json={"card": card})

        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_reviewer_note_optional(self, tmp_path):
        """reviewer_note is optional — approve should work without it."""
        card = _deconstructed_card()

        with patch.object(api, "append_template_card") as mock_append:
            mock_append.return_value = tmp_path / "test.jsonl"

            with patch.object(api, "load_template_cards", return_value=[card]):
                client = TestClient(api.app)
                resp = client.post("/ingest/approve", json={"card": card})

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_rejects_missing_card_field(self):
        """Request body without 'card' → 422 (Pydantic validation)."""
        client = TestClient(api.app)
        resp = client.post("/ingest/approve", json={"reviewer_note": "no card here"})

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /ingest/deconstruct — WebP support
# ---------------------------------------------------------------------------


def test_deconstruct_accepts_webp():
    """WebP images should be accepted alongside PNG and JPEG."""
    with patch.object(api, "deconstruct_template", wraps=_fake_deconstruct):
        client = TestClient(api.app)
        resp = client.post(
            "/ingest/deconstruct",
            data={
                "source_type": "canva",
                "source_ref": "template.webp",
                "archetype": "poster",
                "category": "acilis",
                "canvas_format": "1:1",
            },
            files={"file": ("template.webp", io.BytesIO(_make_fake_image("image/webp")), "image/webp")},
        )

    assert resp.status_code == 200
    assert resp.json()["approved"] is False


def test_deconstruct_accepts_jpeg():
    """JPEG images should be accepted."""
    with patch.object(api, "deconstruct_template", wraps=_fake_deconstruct):
        client = TestClient(api.app)
        resp = client.post(
            "/ingest/deconstruct",
            data={
                "source_type": "behance",
                "source_ref": "ref.jpg",
                "archetype": "flyer",
                "category": "etkinlik",
                "canvas_format": "4:5",
            },
            files={"file": ("ref.jpg", io.BytesIO(_make_fake_image("image/jpeg")), "image/jpeg")},
        )

    assert resp.status_code == 200
