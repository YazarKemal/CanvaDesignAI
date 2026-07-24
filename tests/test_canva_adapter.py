"""Tests for src/canva_adapter.py — Canva Brand Template Autofill adapter."""

import csv
import io
import json
import tempfile
from pathlib import Path

import pytest

from src.canva_adapter import (
    DEFAULT_TEMPLATE_FIELDS,
    TEMPLATE_REGISTRY,
    FIELD_BADGE_TEXT,
    FIELD_BACKGROUND_IMAGE,
    FIELD_HEADLINE,
    FIELD_SUBTEXT,
    FIELD_CTA_TEXT,
    as_canva_autofill_payload,
    as_csv_string,
    export_payload_as_csv,
    export_payload_as_json,
    resolve_template_id,
    upload_background_asset,
    validate_payload,
)


# ---------------------------------------------------------------------------
# Sample card fixtures (abridged but schema-conformant)
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_card() -> dict:
    """A minimal valid CaVDesign card."""
    return {
        "concept": "Grand Opening Cafe",
        "aspect_ratio": "1:1 (1080x1080)",
        "target_tool": "Canva Native Layout Engine",
        "text_zone": "top",
        "canva_keywords": ["editorial"],
        "raster_background": {
            "magic_media_prompt": "Canva Stock Library: modern coffee shop "
            "interior, warm lighting, negative space at top",
            "negative_prompt": "no AI-generated imagery, no text, no watermark",
        },
        "vector_elements": {
            "cta_button": "Shop Now",
            "badge": "NEW",
        },
        "native_typography": {
            "headline": "Grand Opening",
            "subtext": "Freshly roasted, every morning.",
            "headline_pt": 72,
            "subtext_pt": 18,
            "color_palette": ["#3B2A1E", "#B8936E", "#E8DDD0", "#8B9D6B", "#D4C5B9"],
            "fonts": {
                "headline_font": "Montserrat Bold",
                "body_font": "Cormorant Garamond Regular",
            },
            "alignment_zone": "top 30% of canvas, left-aligned",
            "micro_tags": {
                "volume_line": "VOL.01 / 2026",
                "category_line": "EDITORIAL BRANDING",
                "origin_line": "CRAFTED IN TURKEY",
                "micro_pt": 9,
                "micro_color": "#B8936E",
                "micro_font": "Inter Regular",
            },
        },
        "direct_action_tip": [
            "PRIMARY (Canva Native Layout Engine): Build this design...",
            "ALTERNATIVE: Manual steps...",
        ],
    }


@pytest.fixture
def card_no_optionals() -> dict:
    """Card without micro_tags or vector_elements text fields."""
    return {
        "concept": "Minimal Poster",
        "aspect_ratio": "4:5 (1080x1350)",
        "target_tool": "Canva Native Layout Engine",
        "text_zone": "center",
        "raster_background": {
            "magic_media_prompt": "Solid #FFFFFF white background, "
            "completely empty canvas with typography at center",
            "negative_prompt": "no AI-generated imagery, no text",
        },
        "vector_elements": {},
        "native_typography": {
            "headline": "Less Is More",
            "subtext": "A design philosophy.",
            "color_palette": ["#000000", "#333333", "#F5F5F5"],
            "fonts": {"headline_font": "Helvetica Bold", "body_font": "Inter Regular"},
            "alignment_zone": "center of canvas",
        },
        "direct_action_tip": ["Step 1...", "Step 2..."],
    }


# ---------------------------------------------------------------------------
# resolve_template_id
# ---------------------------------------------------------------------------

class TestResolveTemplateId:
    def test_returns_raw_id_when_registry_empty(self):
        assert resolve_template_id("tpl_abc123") == "tpl_abc123"

    def test_returns_raw_id_when_not_in_registry(self):
        TEMPLATE_REGISTRY["warm-editorial-minimalist"] = "tpl_warm_001"
        assert resolve_template_id("tpl_unknown") == "tpl_unknown"

    def test_maps_style_slug_to_template_id(self):
        TEMPLATE_REGISTRY["warm-editorial-minimalist"] = "tpl_warm_001"
        assert resolve_template_id("warm-editorial-minimalist") == "tpl_warm_001"


# ---------------------------------------------------------------------------
# as_canva_autofill_payload — structure
# ---------------------------------------------------------------------------

class TestAsCanvaAutofillPayload:
    def test_mandatory_brand_template_id_in_output(self, minimal_card: dict):
        payload = as_canva_autofill_payload(minimal_card, "tpl_test123")
        assert payload["brand_template_id"] == "tpl_test123"

    def test_title_defaults_to_concept(self, minimal_card: dict):
        payload = as_canva_autofill_payload(minimal_card, "tpl_test123")
        assert payload["title"] == "Grand Opening Cafe"

    def test_explicit_title_overrides_concept(self, minimal_card: dict):
        payload = as_canva_autofill_payload(
            minimal_card, "tpl_test123", title="Custom Title"
        )
        assert payload["title"] == "Custom Title"

    def test_title_truncated_at_255_chars(self, minimal_card: dict):
        long_title = "A" * 300
        payload = as_canva_autofill_payload(
            minimal_card, "tpl_test123", title=long_title
        )
        assert len(payload["title"]) <= 255

    def test_headline_and_subtext_mapped(self, minimal_card: dict):
        payload = as_canva_autofill_payload(minimal_card, "tpl_test123")
        data = payload["data"]
        assert data[FIELD_HEADLINE] == {"type": "text", "text": "Grand Opening"}
        assert data[FIELD_SUBTEXT] == {"type": "text", "text": "Freshly roasted, every morning."}

    def test_cta_and_badge_mapped_when_present(self, minimal_card: dict):
        payload = as_canva_autofill_payload(minimal_card, "tpl_test123")
        data = payload["data"]
        assert data[FIELD_CTA_TEXT] == {"type": "text", "text": "Shop Now"}
        assert data[FIELD_BADGE_TEXT] == {"type": "text", "text": "NEW"}

    def test_micro_tags_mapped_when_present(self, minimal_card: dict):
        payload = as_canva_autofill_payload(minimal_card, "tpl_test123")
        data = payload["data"]
        assert data["VolumeLine"] == {"type": "text", "text": "VOL.01 / 2026"}
        assert data["CategoryLine"] == {"type": "text", "text": "EDITORIAL BRANDING"}
        assert data["OriginLine"] == {"type": "text", "text": "CRAFTED IN TURKEY"}

    def test_optional_fields_omitted_when_absent(self, card_no_optionals: dict):
        payload = as_canva_autofill_payload(card_no_optionals, "tpl_test123")
        data = payload["data"]
        assert FIELD_HEADLINE in data
        assert FIELD_SUBTEXT in data
        assert FIELD_CTA_TEXT not in data  # no cta_button in card
        assert "VolumeLine" not in data     # no micro_tags in card

    # -- template_fields filtering ------------------------------------------

    def test_respects_template_fields_allowlist(self, minimal_card: dict):
        payload = as_canva_autofill_payload(
            minimal_card,
            "tpl_test123",
            template_fields=[FIELD_HEADLINE, FIELD_SUBTEXT],
        )
        data = payload["data"]
        assert set(data.keys()) == {FIELD_HEADLINE, FIELD_SUBTEXT}
        # CTA and micro-tags must be stripped
        assert FIELD_CTA_TEXT not in data
        assert "VolumeLine" not in data

    def test_empty_template_fields_produces_empty_data(self, minimal_card: dict):
        payload = as_canva_autofill_payload(
            minimal_card, "tpl_test123", template_fields=[]
        )
        assert payload["data"] == {}

    def test_template_fields_case_sensitive(self, minimal_card: dict):
        payload = as_canva_autofill_payload(
            minimal_card,
            "tpl_test123",
            template_fields=["headline", "subtext"],  # lowercase — won't match
        )
        assert payload["data"] == {}

    # -- background_asset_id ------------------------------------------------

    def test_background_image_included_when_asset_id_given(self, minimal_card: dict):
        payload = as_canva_autofill_payload(
            minimal_card, "tpl_test123", background_asset_id="Msd59349ff"
        )
        assert payload["data"][FIELD_BACKGROUND_IMAGE] == {
            "type": "image",
            "asset_id": "Msd59349ff",
        }

    def test_background_image_excluded_when_asset_id_omitted(self, minimal_card: dict):
        payload = as_canva_autofill_payload(minimal_card, "tpl_test123")
        assert FIELD_BACKGROUND_IMAGE not in payload["data"]

    def test_background_image_filtered_when_not_in_template_fields(self, minimal_card: dict):
        payload = as_canva_autofill_payload(
            minimal_card,
            "tpl_test123",
            template_fields=[FIELD_HEADLINE],
            background_asset_id="Msd59349ff",
        )
        assert FIELD_BACKGROUND_IMAGE not in payload["data"]


# ---------------------------------------------------------------------------
# upload_background_asset — mock
# ---------------------------------------------------------------------------

class TestUploadBackgroundAsset:
    def test_returns_mock_asset_id_from_path(self):
        asset_id = upload_background_asset("/tmp/test_bg.png")
        assert asset_id.startswith("mock_")
        assert len(asset_id) > len("mock_")

    def test_returns_mock_asset_id_from_bytes(self):
        asset_id = upload_background_asset(b"\x89PNG\r\n\x1a\n")
        assert asset_id.startswith("mock_")

    def test_different_inputs_yield_different_ids(self):
        id1 = upload_background_asset("/tmp/a.png")
        id2 = upload_background_asset("/tmp/b.png")
        assert id1 != id2


# ---------------------------------------------------------------------------
# validate_payload
# ---------------------------------------------------------------------------

class TestValidatePayload:
    def test_valid_full_payload_passes(self):
        payload = {
            "brand_template_id": "tpl_abc123def",
            "title": "Test Design",
            "data": {
                "Headline": {"type": "text", "text": "Hello"},
                "BackgroundImage": {"type": "image", "asset_id": "Msd123"},
            },
        }
        validate_payload(payload)  # must not raise

    def test_missing_brand_template_id_raises(self):
        with pytest.raises(ValueError, match="brand_template_id"):
            validate_payload({"data": {"H": {"type": "text", "text": "x"}}})

    def test_invalid_template_id_pattern_raises(self):
        with pytest.raises(ValueError, match="tpl_"):
            validate_payload({
                "brand_template_id": "invalid-format",
                "data": {"H": {"type": "text", "text": "x"}},
            })

    def test_empty_data_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            validate_payload({
                "brand_template_id": "tpl_test",
                "data": {},
            })

    def test_wrong_field_type_raises(self):
        with pytest.raises(ValueError, match="must be 'text' or 'image'"):
            validate_payload({
                "brand_template_id": "tpl_test",
                "data": {"H": {"type": "unknown", "text": "x"}},
            })

    def test_text_field_without_text_raises(self):
        with pytest.raises(ValueError, match="text.*required"):
            validate_payload({
                "brand_template_id": "tpl_test",
                "data": {"H": {"type": "text"}},
            })

    def test_image_field_without_asset_id_raises(self):
        with pytest.raises(ValueError, match="asset_id.*required"):
            validate_payload({
                "brand_template_id": "tpl_test",
                "data": {"Img": {"type": "image"}},
            })

    def test_title_over_255_raises(self):
        with pytest.raises(ValueError, match="255"):
            validate_payload({
                "brand_template_id": "tpl_test",
                "title": "X" * 256,
                "data": {"H": {"type": "text", "text": "x"}},
            })

    def test_non_dict_payload_raises(self):
        with pytest.raises(ValueError, match="must be a dict"):
            validate_payload("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration: round-trip payload validates
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_generated_payload_passes_own_validator(self, minimal_card: dict):
        payload = as_canva_autofill_payload(
            minimal_card,
            "tpl_test123",
            background_asset_id="Msd59349ff",
        )
        validate_payload(payload)  # must not raise

    def test_generated_payload_includes_all_default_fields(self, minimal_card: dict):
        payload = as_canva_autofill_payload(
            minimal_card,
            "tpl_test123",
            background_asset_id="Msd59349ff",
        )
        data = payload["data"]
        # All 8 default fields should be present (with full card + asset)
        assert len(data) == 8
        for f in DEFAULT_TEMPLATE_FIELDS:
            assert f in data, f"Expected {f} in payload data"


# ---------------------------------------------------------------------------
# as_csv_string
# ---------------------------------------------------------------------------

class TestAsCsvString:
    def test_produces_valid_csv_with_header_and_one_data_row(self, minimal_card: dict):
        csv_text = as_csv_string(minimal_card, "tpl_test123")
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 2  # header + 1 data row
        assert rows[0] == rows[0]  # header is not empty
        assert len(rows[0]) > 0

    def test_header_row_contains_text_field_names(self, minimal_card: dict):
        csv_text = as_csv_string(minimal_card, "tpl_test123")
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        assert FIELD_HEADLINE in header
        assert FIELD_SUBTEXT in header
        assert FIELD_CTA_TEXT in header

    def test_data_row_contains_text_values(self, minimal_card: dict):
        csv_text = as_csv_string(minimal_card, "tpl_test123")
        reader = csv.reader(io.StringIO(csv_text))
        next(reader)  # skip header
        data_row = next(reader)
        # Find the headline column positionally or by value
        flat = " ".join(data_row)
        assert "Grand Opening" in flat
        assert "Freshly roasted, every morning." in flat

    def test_background_image_excluded_from_csv(self, minimal_card: dict):
        """BackgroundImage MUST NOT appear in CSV — Bulk Create can't use it."""
        csv_text = as_csv_string(minimal_card, "tpl_test123")
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        assert FIELD_BACKGROUND_IMAGE not in header

    def test_background_image_excluded_even_when_asset_id_given(self, minimal_card: dict):
        """Even if we have a background_asset_id, it must still be excluded."""
        payload = as_canva_autofill_payload(
            minimal_card, "tpl_test123", background_asset_id="Msd123"
        )
        # Payload has it, but CSV must drop it
        assert FIELD_BACKGROUND_IMAGE in payload["data"]
        csv_text = as_csv_string(minimal_card, "tpl_test123")
        assert FIELD_BACKGROUND_IMAGE not in csv_text

    def test_proper_quoting_for_commas_in_text(self, minimal_card: dict):
        """Subtext with commas must be properly quoted."""
        minimal_card["native_typography"]["subtext"] = "Fresh, roasted, every morning."
        csv_text = as_csv_string(minimal_card, "tpl_test123")
        # The entire field should be quoted, protecting the commas
        assert '"Fresh, roasted, every morning."' in csv_text

    def test_proper_quoting_for_quotes_in_text(self, minimal_card: dict):
        """Double-quotes inside fields must be escaped per RFC 4180."""
        minimal_card["native_typography"]["headline"] = 'The "Best" Coffee'
        csv_text = as_csv_string(minimal_card, "tpl_test123")
        # csv.QUOTE_ALL will double the internal quotes
        assert 'The ""Best"" Coffee' in csv_text

    def test_template_fields_filters_csv_columns(self, minimal_card: dict):
        """template_fields filtering must work for CSV too."""
        csv_text = as_csv_string(
            minimal_card,
            "tpl_test123",
            template_fields=[FIELD_HEADLINE, FIELD_SUBTEXT],
        )
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        assert set(header) == {FIELD_HEADLINE, FIELD_SUBTEXT}
        assert FIELD_CTA_TEXT not in header

    def test_empty_template_fields_produces_empty_csv(self, minimal_card: dict):
        """When template_fields is an empty list, no text fields survive
        filtering, so CSV output should be empty (no header, no row)."""
        csv_text = as_csv_string(
            minimal_card, "tpl_test123", template_fields=[]
        )
        # csv.writerow([]) produces only newlines, which rstrip removes.
        assert csv_text == ""

    def test_optional_fields_omitted_when_not_in_card(self, card_no_optionals: dict):
        csv_text = as_csv_string(card_no_optionals, "tpl_test123")
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        assert FIELD_HEADLINE in header
        assert FIELD_SUBTEXT in header
        assert FIELD_CTA_TEXT not in header  # no cta_button in card

    def test_csv_column_order_matches_template_fields(self, minimal_card: dict):
        """When template_fields is given, CSV columns should match its order.
        All three fields (Subtext, Headline, OriginLine) are present in the
        minimal_card via native_typography.micro_tags.origin_line."""
        order = ["Subtext", "Headline", "OriginLine"]
        csv_text = as_csv_string(
            minimal_card,
            "tpl_test123",
            template_fields=order,
        )
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        # OriginLine IS present in the card (via micro_tags)
        assert header == ["Subtext", "Headline", "OriginLine"]

    def test_csv_does_not_contain_image_type_fields(self, minimal_card: dict):
        """Sanity check: no 'type':'image' field names leak into CSV."""
        csv_text = as_csv_string(minimal_card, "tpl_test123")
        # BackgroundImage must be absent
        assert "BackgroundImage" not in csv_text
        # No type metadata should appear
        assert '"type"' not in csv_text


# ---------------------------------------------------------------------------
# export_payload_as_csv (disk I/O)
# ---------------------------------------------------------------------------

class TestExportPayloadAsCsv:
    def test_writes_csv_file_to_disk(self, minimal_card: dict):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            f.close()
            try:
                path = export_payload_as_csv(minimal_card, "tpl_test123", f.name)
                assert path.exists()
                content = path.read_text(encoding="utf-8")
                assert FIELD_HEADLINE in content
                assert "Grand Opening" in content
            finally:
                Path(f.name).unlink(missing_ok=True)

    def test_file_has_trailing_newline(self, minimal_card: dict):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            f.close()
            try:
                path = export_payload_as_csv(minimal_card, "tpl_test123", f.name)
                content = path.read_text(encoding="utf-8")
                assert content.endswith("\n")
            finally:
                Path(f.name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# export_payload_as_json (Plan A readiness)
# ---------------------------------------------------------------------------

class TestExportPayloadAsJson:
    def test_writes_valid_json_file_to_disk(self, minimal_card: dict):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.close()
            try:
                path = export_payload_as_json(minimal_card, "tpl_test123", f.name)
                assert path.exists()
                content = path.read_text(encoding="utf-8")
                payload = json.loads(content)
                assert payload["brand_template_id"] == "tpl_test123"
                assert "data" in payload
                assert "title" in payload
            finally:
                Path(f.name).unlink(missing_ok=True)

    def test_json_includes_background_image_when_asset_id_given(self, minimal_card: dict):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.close()
            try:
                path = export_payload_as_json(
                    minimal_card,
                    "tpl_test123",
                    f.name,
                    background_asset_id="Msd59349ff",
                )
                payload = json.loads(path.read_text(encoding="utf-8"))
                assert FIELD_BACKGROUND_IMAGE in payload["data"]
                assert payload["data"][FIELD_BACKGROUND_IMAGE]["asset_id"] == "Msd59349ff"
            finally:
                Path(f.name).unlink(missing_ok=True)

    def test_json_payload_passes_validation(self, minimal_card: dict):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.close()
            try:
                path = export_payload_as_json(
                    minimal_card,
                    "tpl_test123",
                    f.name,
                    background_asset_id="Msd59349ff",
                )
                payload = json.loads(path.read_text(encoding="utf-8"))
                validate_payload(payload)
            finally:
                Path(f.name).unlink(missing_ok=True)

    def test_json_respects_template_fields(self, minimal_card: dict):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.close()
            try:
                path = export_payload_as_json(
                    minimal_card,
                    "tpl_test123",
                    f.name,
                    template_fields=[FIELD_HEADLINE],
                )
                payload = json.loads(path.read_text(encoding="utf-8"))
                assert list(payload["data"].keys()) == [FIELD_HEADLINE]
            finally:
                Path(f.name).unlink(missing_ok=True)
