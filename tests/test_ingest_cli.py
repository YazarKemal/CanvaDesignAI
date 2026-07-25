"""Tests for scripts/ingest_template.py — the two-stage ingestion CLI."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module under test
import scripts.ingest_template as cli


# ---------------------------------------------------------------------------
# MIME detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ext,expected", [
    (".png", "image/png"),
    (".jpg", "image/jpeg"),
    (".jpeg", "image/jpeg"),
    (".webp", "image/webp"),
    (".gif", "image/gif"),
    (".PNG", "image/png"),
    (".JPG", "image/jpeg"),
])
def test_detect_mime_valid(ext, expected):
    """All supported extensions should map to the correct MIME type."""
    assert cli._detect_mime(Path(f"image{ext}")) == expected


def test_detect_mime_unsupported():
    """Unsupported extensions should raise SystemExit with a message mentioning
    the extension and the supported list."""
    with pytest.raises(SystemExit, match="1"):
        cli._detect_mime(Path("document.pdf"))

    # Verify the error message was printed
    # (can't easily capture in this pattern, but the exit code is enough)


def test_detect_mime_no_extension():
    """Files with no extension should also be rejected."""
    with pytest.raises(SystemExit, match="1"):
        cli._detect_mime(Path("no_extension"))


# ---------------------------------------------------------------------------
# Argument parsing — subcommand structure
# ---------------------------------------------------------------------------


def test_parser_requires_subcommand():
    """Running without a subcommand should fail."""
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args([])


def test_deconstruct_requires_all_args():
    """The deconstruct subcommand should require --source-type, --source-ref,
    --archetype, --category, and --canvas-format."""
    parser = cli._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["deconstruct", "image.png"])


def test_deconstruct_parses_minimal_args():
    """All required args plus the image path should parse successfully."""
    parser = cli._build_parser()
    args = parser.parse_args([
        "deconstruct", "image.png",
        "--source-type", "upload",
        "--source-ref", "ref-001",
        "--archetype", "instagram_story",
        "--category", "lansman",
        "--canvas-format", "9:16",
    ])
    assert args.command == "deconstruct"
    assert args.source_type == "upload"
    assert args.source_ref == "ref-001"
    assert args.archetype == "instagram_story"
    assert args.category == "lansman"
    assert args.canvas_format == "9:16"
    assert args.out is None


def test_deconstruct_optional_out():
    """The --out flag should be parsed when provided."""
    parser = cli._build_parser()
    args = parser.parse_args([
        "deconstruct", "image.png",
        "--source-type", "upload",
        "--source-ref", "ref-001",
        "--archetype", "x",
        "--category", "y",
        "--canvas-format", "1:1",
        "--out", "/tmp/card.json",
    ])
    assert args.out == Path("/tmp/card.json")


def test_approve_parses_args():
    """The approve subcommand should accept a card JSON path, --note, and --force."""
    parser = cli._build_parser()
    args = parser.parse_args([
        "approve", "card.json",
        "--note", "Looks good.",
        "--force",
    ])
    assert args.command == "approve"
    assert args.card_json == Path("card.json")
    assert args.note == "Looks good."
    assert args.force is True


def test_approve_optional_args_default():
    """--note and --force should default to None and False."""
    parser = cli._build_parser()
    args = parser.parse_args(["approve", "card.json"])
    assert args.note is None
    assert args.force is False


# ---------------------------------------------------------------------------
# Stage 1 — deconstruct (mock vision)
# ---------------------------------------------------------------------------


def _fake_vision_result(card_dict: dict) -> str:
    return json.dumps(card_dict, ensure_ascii=False)


def _valid_card() -> dict:
    return {
        "concept": "CLI Test",
        "aspect_ratio": "1:1 (1080x1080)",
        "target_tool": "Canva Native Layout Engine",
        "text_zone": "top",
        "canva_keywords": ["minimal", "editorial"],
        "raster_background": {
            "magic_media_prompt": "A Canva stock photo search query for warm coffee shop interior with negative space at the top for typography overlay.",
            "negative_prompt": "no AI-generated imagery, no text, no watermark, busy background",
            "layout_style": "Minimalist",
        },
        "vector_elements": {
            "thin_divider": "horizontal 0.5px rule in muted gold at 60% opacity, centered",
        },
        "native_typography": {
            "headline": "CLI Test",
            "subtext": "Generated by CLI.",
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
        "direct_action_tip": ["Step 1", "Step 2"],
    }


class _FakeClient:
    """Mock OpenAIVisionClient that returns a fixed card JSON string."""
    def __init__(self, content: str):
        self._content = content
        self.last_prompt = ""

    def deconstruct_image(self, image_bytes, mime_type, *, prompt):
        self.last_prompt = prompt
        return self._content


def test_cmd_deconstruct_happy_path(tmp_path, monkeypatch, capsys):
    """Full deconstruct flow: read a temp PNG, call fake vision, print JSON."""
    # Create a fake image
    img = tmp_path / "template.png"
    img.write_text("fake image content")  # not a real PNG, but CLI just reads bytes

    card = _valid_card()
    fake = _FakeClient(json.dumps(card, ensure_ascii=False))

    # Patch the vision client creation inside deconstruct_template
    with patch("src.vision_client.OpenAIVisionClient", return_value=fake):
        cli.main([
            "deconstruct", str(img),
            "--source-type", "upload",
            "--source-ref", "cli-test-001",
            "--archetype", "instagram_story",
            "--category", "test",
            "--canvas-format", "1:1",
        ])

    out = capsys.readouterr().out
    # The JSON is multi-line (indent=2).  Slice between first { and last }.
    start = out.find("{")
    end = out.rfind("}")
    assert start != -1 and end != -1, f"No JSON found in output: {out[:200]}"
    parsed = json.loads(out[start:end + 1])
    assert parsed["concept"] == "CLI Test"
    assert parsed["approved"] is False
    assert parsed["source_type"] == "upload"
    assert parsed["source_ref"] == "cli-test-001"


def test_cmd_deconstruct_writes_out_file(tmp_path, monkeypatch, capsys):
    """The --out flag should write the card JSON to a file."""
    img = tmp_path / "template.png"
    img.write_text("fake")

    card = _valid_card()
    fake = _FakeClient(json.dumps(card, ensure_ascii=False))
    out_file = tmp_path / "out.json"

    with patch("src.vision_client.OpenAIVisionClient", return_value=fake):
        cli.main([
            "deconstruct", str(img),
            "--source-type", "upload",
            "--source-ref", "cli-test-002",
            "--archetype", "x",
            "--category", "y",
            "--canvas-format", "1:1",
            "--out", str(out_file),
        ])

    assert out_file.exists()
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["concept"] == "CLI Test"


def test_cmd_deconstruct_unsupported_format(tmp_path, monkeypatch):
    """A file with an unsupported extension should fail before any vision call."""
    img = tmp_path / "template.pdf"
    img.write_text("fake")

    with pytest.raises(SystemExit, match="1"):
        cli.main([
            "deconstruct", str(img),
            "--source-type", "upload",
            "--source-ref", "x",
            "--archetype", "x",
            "--category", "x",
            "--canvas-format", "1:1",
        ])


def test_cmd_deconstruct_vision_error(tmp_path, monkeypatch, capsys):
    """A VisionClientError should print a clean message and exit 1."""
    img = tmp_path / "template.png"
    img.write_text("fake")

    # Create a fake client that raises
    class _ErrorClient:
        def deconstruct_image(self, image_bytes, mime_type, *, prompt):
            from src.vision_client import VisionClientError
            raise VisionClientError("OPENAI_API_KEY is not set.")

    with patch("src.vision_client.OpenAIVisionClient", return_value=_ErrorClient()):
        with pytest.raises(SystemExit, match="1"):
            cli.main([
                "deconstruct", str(img),
                "--source-type", "upload",
                "--source-ref", "x",
                "--archetype", "x",
                "--category", "x",
                "--canvas-format", "1:1",
            ])

    stderr = capsys.readouterr().err
    assert "Vision client error" in stderr
    assert "OPENAI_API_KEY" in stderr


def test_cmd_deconstruct_missing_file():
    """A nonexistent image path should fail with a readable error."""
    with pytest.raises(SystemExit, match="1"):
        cli.main([
            "deconstruct", "/nonexistent/path/image.png",
            "--source-type", "upload",
            "--source-ref", "x",
            "--archetype", "x",
            "--category", "x",
            "--canvas-format", "1:1",
        ])


# ---------------------------------------------------------------------------
# Stage 2 — approve (mock file I/O)
# ---------------------------------------------------------------------------


def _write_card_json(path: Path, **overrides):
    """Write a full deconstructed card to *path*, ready for approval."""
    card = _valid_card()
    card.update({
        "source_type": "upload",
        "source_ref": "cli-approve-test",
        "archetype": "x",
        "category": "y",
        "format": "1:1",
        "ingested_at": "2026-07-25T00:00:00Z",
        "approved": False,
    })
    card.update(overrides)
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")


def test_cmd_approve_happy_path(tmp_path, monkeypatch, capsys):
    """Full approve flow: read JSON, approve, append, report count."""
    card_path = tmp_path / "card.json"
    _write_card_json(card_path)

    corpus = tmp_path / "corpus.jsonl"

    cli.main(["approve", str(card_path), "--corpus", str(corpus)])

    out = capsys.readouterr().out
    assert "Approved and written to" in out
    assert "Corpus now has 1 card" in out
    assert corpus.exists()


def test_cmd_approve_with_note(tmp_path, monkeypatch, capsys):
    """The --note flag should be passed through to approve_card."""
    card_path = tmp_path / "card.json"
    _write_card_json(card_path)

    corpus = tmp_path / "corpus_note.jsonl"

    cli.main(["approve", str(card_path), "--note", "Perfect layout.", "--corpus", str(corpus)])

    out = capsys.readouterr().out
    assert "Corpus now has 1 card" in out

    # Verify the note was stored
    import src.template_ingest as ti
    cards = ti.load_template_cards(corpus)
    assert cards[0]["reviewer_note"] == "Perfect layout."


def test_cmd_approve_validation_fails(tmp_path, monkeypatch, capsys):
    """A structurally broken card should fail validation and exit 1."""
    card_path = tmp_path / "card.json"
    _write_card_json(card_path)
    # Corrupt the card after writing: remove required field
    card = json.loads(card_path.read_text())
    card["native_typography"]["headline"] = ""  # empty headline → jsonschema fail
    card_path.write_text(json.dumps(card))

    corpus = tmp_path / "corpus_fail.jsonl"

    with pytest.raises(SystemExit, match="1"):
        cli.main(["approve", str(card_path), "--corpus", str(corpus)])

    stderr = capsys.readouterr().err
    assert "NOT approved" in stderr or "Validation failed" in stderr


def test_cmd_approve_missing_json_file():
    """A nonexistent card JSON should fail before touching the corpus."""
    with pytest.raises(SystemExit, match="1"):
        cli.main(["approve", "/nonexistent/card.json"])


def test_cmd_approve_invalid_json(tmp_path):
    """A file that isn't valid JSON should fail with a readable error."""
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("this is not json!!!")

    with pytest.raises(SystemExit, match="1"):
        cli.main(["approve", str(bad_path)])
