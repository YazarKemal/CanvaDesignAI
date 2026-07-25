"""Tests for src/template_ingest.py — the offline ingestion layer."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.schema import PromptValidationError
from src.template_ingest import (
    DECONSTRUCTION_PROMPT,
    TEMPLATE_CARD_SCHEMA,
    TemplateIngestError,
    append_template_card,
    approve_card,
    deconstruct_template,
    load_template_cards,
    validate_template_card,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fake_vision_client(content: str):
    """Return a mock vision client whose deconstruct_image returns *content*."""

    class _FakeClient:
        def deconstruct_image(self, image_bytes, mime_type, *, prompt):
            return content

    return _FakeClient()


def _valid_card_dict() -> dict:
    """A minimal but valid card dict that passes schema + code-level checks."""
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
            "thin_divider": "horizontal 0.5px rule in muted gold at 60% opacity, centered",
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


def _provenance_kwargs() -> dict:
    return {
        "source_type": "behance",
        "source_ref": "https://behance.net/gallery/12345-test-template",
        "archetype": "instagram_story",
        "category": "lansman",
        "canvas_format": "9:16",
    }


def _full_record(**overrides) -> dict:
    """Return a valid, approved record ready for append / validation."""
    record = _valid_card_dict()
    record.update(_provenance_kwargs())
    record["format"] = record.pop("canvas_format")  # provenance uses canvas_format kwarg
    record["ingested_at"] = "2026-07-25T00:00:00Z"
    record["approved"] = True
    record["approved_at"] = "2026-07-25T12:00:00Z"
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------
# deconstruct_template — happy path
# ---------------------------------------------------------------------------


def test_deconstruct_template_happy_path():
    """A valid JSON response from the vision model should produce a stamped,
    approved=False record with all provenance fields."""
    card_json = json.dumps(_valid_card_dict(), ensure_ascii=False)
    client = _fake_vision_client(card_json)

    record = deconstruct_template(
        b"fake-image-bytes",
        "image/png",
        **_provenance_kwargs(),
        client=client,
    )

    assert record["concept"] == "Test Template"
    assert record["approved"] is False
    assert record["source_type"] == "behance"
    assert record["source_ref"] == "https://behance.net/gallery/12345-test-template"
    assert record["archetype"] == "instagram_story"
    assert record["category"] == "lansman"
    assert record["format"] == "9:16"
    assert "ingested_at" in record
    assert "T" in record["ingested_at"]


def test_deconstruct_template_creates_client_when_none():
    """When no client is passed, deconstruct_template should try to create one
    from env vars.  If OPENAI_API_KEY is missing, VisionClientError propagates."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(Exception):  # VisionClientError or RuntimeError
            deconstruct_template(
                b"fake", "image/png",
                **_provenance_kwargs(),
                client=None,
            )


# ---------------------------------------------------------------------------
# deconstruct_template — error handling
# ---------------------------------------------------------------------------


def test_deconstruct_template_rejects_broken_json():
    """If the vision model returns prose instead of JSON, TemplateIngestError
    should be raised with the raw text preview in the message."""
    client = _fake_vision_client("Here is a nice description of the template... but no JSON.")

    with pytest.raises(TemplateIngestError, match="valid JSON"):
        deconstruct_template(
            b"fake", "image/png",
            **_provenance_kwargs(),
            client=client,
        )


def test_deconstruct_template_rejects_markdown_wrapped_json():
    """JSON inside markdown fences should still be extractable (llm_json.py
    strips fences first)."""
    card = _valid_card_dict()
    wrapped = f"```json\n{json.dumps(card, ensure_ascii=False)}\n```"
    client = _fake_vision_client(wrapped)

    record = deconstruct_template(
        b"fake", "image/png",
        **_provenance_kwargs(),
        client=client,
    )
    assert record["concept"] == "Test Template"
    assert record["approved"] is False


# ---------------------------------------------------------------------------
# approve_card — validation gate + metadata
# ---------------------------------------------------------------------------


def test_approve_card_sets_flag_and_timestamp():
    """approve_card validates, then sets approved=True + approved_at timestamp."""
    record = _full_record(approved=False)
    del record["approved_at"]  # not yet approved

    result = approve_card(record)
    assert result["approved"] is True
    assert result is record  # returns same object for chaining
    assert "approved_at" in result
    assert "T" in result["approved_at"]


def test_approve_card_rejects_invalid_record():
    """If the record fails validation, approve_card must NOT set approved=True."""
    record = _full_record(approved=False)
    del record["approved_at"]
    # Intentionally corrupt: remove required field
    del record["native_typography"]["headline"]

    with pytest.raises(Exception):  # PromptValidationError from jsonschema
        approve_card(record)
    # approved must remain False — the gate held
    assert record.get("approved") is not True


def test_approve_card_stores_reviewer_note():
    """When reviewer_note is passed, it should be written into the record."""
    record = _full_record(approved=False)
    del record["approved_at"]

    result = approve_card(record, reviewer_note="Looks good, palette matches brand.")
    assert result["reviewer_note"] == "Looks good, palette matches brand."
    assert result["approved"] is True


def test_approve_card_is_the_only_way():
    """deconstruct_template always sets approved=False; only approve_card flips it."""
    card = _valid_card_dict()
    client = _fake_vision_client(json.dumps(card))
    record = deconstruct_template(b"x", "image/png", **_provenance_kwargs(), client=client)
    assert record["approved"] is False

    # approve_card gate: needs a valid full record
    full = _full_record(approved=False)
    del full["approved_at"]
    approve_card(full)
    assert full["approved"] is True


# ---------------------------------------------------------------------------
# append_template_card — approval + validation gate + dedup
# ---------------------------------------------------------------------------


def test_append_rejects_unapproved_card(tmp_path):
    """append_template_card MUST raise TemplateIngestError when approved=False."""
    record = _valid_card_dict()
    record["approved"] = False
    for k, v in _provenance_kwargs().items():
        record[k] = v

    corpus = tmp_path / "test.jsonl"
    with pytest.raises(TemplateIngestError, match="Cannot append unapproved"):
        append_template_card(record, path=corpus)


def test_append_rejects_approved_but_invalid_card(tmp_path):
    """BLOCKER FIX: An approved=True but broken record must be rejected at
    the validation gate inside append_template_card.  Nothing is written."""
    record = _full_record()
    # Corrupt: give it an impossible headline word count
    record["native_typography"]["headline"] = "one two three four five six seven eight"

    corpus = tmp_path / "invalid.jsonl"
    with pytest.raises(PromptValidationError, match="headline"):
        append_template_card(record, path=corpus)

    # File must not exist or be empty — nothing was written
    assert not corpus.exists() or corpus.read_text(encoding="utf-8").strip() == ""


def test_append_accepts_approved_card(tmp_path):
    """After approve_card(), append should succeed and write a JSONL line."""
    record = _full_record()

    path = append_template_card(record, path=tmp_path / "test.jsonl")

    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1

    loaded = json.loads(lines[0])
    assert loaded["approved"] is True
    assert loaded["concept"] == "Test Template"


def test_append_rejects_duplicate_source_ref(tmp_path):
    """Same source_ref in corpus → TemplateIngestError unless force=True."""
    corpus = tmp_path / "dedup.jsonl"

    # First append — succeeds
    record1 = _full_record(source_ref="https://example.com/duplicate-test")
    append_template_card(record1, path=corpus)

    # Second append with same source_ref — rejected
    record2 = _full_record(
        source_ref="https://example.com/duplicate-test",
        concept="Different Template",
    )
    with pytest.raises(TemplateIngestError, match="already exists"):
        append_template_card(record2, path=corpus)

    # Only the first record should be in the file
    loaded = load_template_cards(corpus)
    assert len(loaded) == 1


def test_append_force_allows_duplicate_source_ref(tmp_path):
    """force=True should skip dedup and append even when source_ref exists."""
    corpus = tmp_path / "force.jsonl"

    record1 = _full_record(source_ref="https://example.com/force-test")
    append_template_card(record1, path=corpus)

    record2 = _full_record(
        source_ref="https://example.com/force-test",
        concept="Overridden Template",
    )
    append_template_card(record2, path=corpus, force=True)

    loaded = load_template_cards(corpus)
    assert len(loaded) == 2
    assert loaded[1]["concept"] == "Overridden Template"


# ---------------------------------------------------------------------------
# JSONL round-trip
# ---------------------------------------------------------------------------


def test_jsonl_round_trip(tmp_path):
    """Write two approved cards, read them back, verify order and content."""
    corpus = tmp_path / "roundtrip.jsonl"

    for i in range(2):
        card = _full_record(
            concept=f"Template {i}",
            source_ref=f"https://example.com/{i}",
        )
        append_template_card(card, path=corpus)

    loaded = load_template_cards(corpus)
    assert len(loaded) == 2
    assert loaded[0]["concept"] == "Template 0"
    assert loaded[1]["concept"] == "Template 1"
    assert all(c["approved"] for c in loaded)


def test_load_returns_empty_for_missing_file(tmp_path):
    """load_template_cards should return [] when the corpus file doesn't exist."""
    result = load_template_cards(tmp_path / "nonexistent.jsonl")
    assert result == []


def test_load_skips_malformed_lines(tmp_path):
    """Malformed JSON lines should be skipped with a warning, not crash."""
    corpus = tmp_path / "bad.jsonl"
    corpus.write_text('{"valid": true}\nthis is not json\n{"also": "valid"}\n', encoding="utf-8")

    loaded = load_template_cards(corpus)
    assert len(loaded) == 2


# ---------------------------------------------------------------------------
# validate_template_card
# ---------------------------------------------------------------------------


def test_validate_passes_for_valid_record():
    """A complete, well-formed record should pass validation."""
    record = _full_record()
    validate_template_card(record)


def test_validate_rejects_missing_provenance():
    """A record missing required provenance fields should fail schema validation."""
    record = _valid_card_dict()
    # Missing most provenance — only add the bare minimum
    record["source_type"] = "behance"
    record["source_ref"] = "x"
    record["archetype"] = "x"
    record["category"] = "x"
    record["format"] = "x"
    record["ingested_at"] = "2026-07-25T00:00:00Z"
    record["approved"] = False
    # Should pass — all required fields present
    validate_template_card(record)


def test_validate_rejects_invalid_source_type():
    """source_type must be one of the three allowed values."""
    record = _full_record()
    record["source_type"] = "instagram"  # not allowed

    with pytest.raises(Exception):
        validate_template_card(record)


def test_validate_rejects_forbidden_chat_language():
    """Cards with conversational filler should be rejected (reusing schema.py rules)."""
    record = _full_record()
    record["direct_action_tip"][0] = "Here is how you build this design..."

    with pytest.raises(PromptValidationError, match="banned"):
        validate_template_card(record)


def test_validate_rejects_too_many_headline_words():
    """Headline word limit (<=6 words) must be enforced."""
    record = _full_record()
    record["native_typography"]["headline"] = "This is way too many words for a good headline"

    with pytest.raises(PromptValidationError, match="headline"):
        validate_template_card(record)


# ---------------------------------------------------------------------------
# DECONSTRUCTION_PROMPT coverage & anti-copycat
# ---------------------------------------------------------------------------


def test_deconstruction_prompt_mentions_all_schema_fields():
    """Every required TEMPLATE_CARD_SCHEMA field (excluding provenance)
    must appear in DECONSTRUCTION_PROMPT so the vision model knows to
    output them.

    This replaces the removed _check_prompt_coverage() import-time warning
    with a real test assertion that cannot be silently ignored.
    """
    provenance = {
        "source_type", "source_ref", "ingested_at",
        "archetype", "category", "format", "approved",
    }

    for field in TEMPLATE_CARD_SCHEMA["required"]:
        if field in provenance:
            continue
        assert field in DECONSTRUCTION_PROMPT, (
            f"DECONSTRUCTION_PROMPT must mention field '{field}' "
            f"so the vision model includes it in the output."
        )


def test_deconstruction_prompt_has_no_concrete_values():
    """BLOCKER FIX: The example JSON in DECONSTRUCTION_PROMPT must NOT contain
    concrete values that the model might copy verbatim.  Every value must be
    a type placeholder like '<hex>' or '<observed ...>'."""
    # These concrete strings must NOT appear in the prompt
    forbidden_concrete = [
        "CRAFTED IN TURKEY",
        "VOL.01 / 2026",
        "EDITORIAL BRANDING",
        "Montserrat Bold",
        "Cormorant Garamond",
        "Inter Regular",
        "#3B2A1E",
        "#B8936E",
        "#E8DDD0",
        "#8B9D6B",
        "#D4C5B9",
        "Headline Text",
        "Supporting subtext line.",
    ]
    for value in forbidden_concrete:
        assert value not in DECONSTRUCTION_PROMPT, (
            f"DECONSTRUCTION_PROMPT must NOT contain concrete value {value!r}. "
            f"Replace it with a type placeholder like '<hex>' or '<observed headline font>' "
            f"so the vision model extracts from the actual image instead of copying."
        )

    # The prompt must include the anti-copycat rule
    assert "Never copy the placeholder values" in DECONSTRUCTION_PROMPT, (
        "DECONSTRUCTION_PROMPT must instruct the model not to copy placeholder values."
    )


def test_deconstruction_prompt_is_not_empty():
    """Sanity check — the prompt should be a substantial string."""
    assert len(DECONSTRUCTION_PROMPT) > 500


# ---------------------------------------------------------------------------
# Boundary test — runtime pipeline must NOT import OpenAI / vision
# ---------------------------------------------------------------------------


def test_generator_module_has_no_openai_or_vision_import():
    """The runtime Generator must remain DeepSeek-only.

    It may import the ``openai`` package (for DeepSeek-compatible chat via
    the SDK's base_url override — that's the normal single-engine path).
    But it must NEVER import or reference vision/image-analysis features.
    """
    generator_src = Path(__file__).resolve().parent.parent / "src" / "generator.py"
    text = generator_src.read_text(encoding="utf-8")

    # The word "vision" must never appear in the generator.
    assert "vision" not in text.lower(), (
        "src/generator.py must NOT contain 'vision' — the runtime pipeline "
        "must remain DeepSeek-only.  Vision is ONLY for ingestion."
    )

    # "openai" may appear (SDK import for DeepSeek-compatible chat).  But
    # "vision_client" or "template_ingest" must never be imported.
    assert "vision_client" not in text.lower(), (
        "src/generator.py must NOT import vision_client — ingestion modules "
        "are separate from the runtime pipeline."
    )
    assert "template_ingest" not in text.lower(), (
        "src/generator.py must NOT import template_ingest — ingestion modules "
        "are separate from the runtime pipeline."
    )
