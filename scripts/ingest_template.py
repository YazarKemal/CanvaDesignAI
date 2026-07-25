#!/usr/bin/env python3
"""Two-stage CLI for template ingestion: deconstruct → approve.

Stage 1 — deconstruct (vision call, NO corpus write):
    python scripts/ingest_template.py deconstruct template.png \\
        --source-type upload --source-ref my-template-001 \\
        --archetype instagram_story --category lansman --canvas-format 9:16 \\
        [--out /tmp/card.json]

Stage 2 — approve (human reviews card JSON, then commits to corpus):
    python scripts/ingest_template.py approve /tmp/card.json \\
        [--note "Palette matches brand."] [--force]

The two stages are deliberately SEPARATE — the human-approval gate lives
between them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# -- MIME detection (extension → type) -----------------------------------

_MIME_MAP: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _detect_mime(path: Path) -> str:
    """Return the IANA media type for *path* based on its file extension.

    Raises
    ------
    SystemExit
        If the extension is not in the supported list.
    """
    ext = path.suffix.lower()
    mime = _MIME_MAP.get(ext)
    if mime is None:
        supported = ", ".join(sorted(_MIME_MAP))
        print(f"Error: unsupported image format '{ext}'.  Supported: {supported}", file=sys.stderr)
        raise SystemExit(1)
    return mime


# -- CLI argument parser -------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest_template",
        description="Two-stage template ingestion: deconstruct (vision) → approve (corpus).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- deconstruct ------------------------------------------------------
    dec = sub.add_parser("deconstruct", help="Run vision model on an image → card JSON (no corpus write).")
    dec.add_argument("image", type=Path, help="Path to the template image (PNG, JPEG, WebP, GIF).")
    dec.add_argument("--source-type", required=True, choices=["canva", "behance", "upload"],
                     help="Origin of the template.")
    dec.add_argument("--source-ref", required=True, help="URL, filename, or free-text source reference.")
    dec.add_argument("--archetype", required=True, help="Design archetype (e.g. instagram_story).")
    dec.add_argument("--category", required=True, help="Template category (e.g. lansman).")
    dec.add_argument("--canvas-format", required=True, help="Canvas format (e.g. 9:16).")
    dec.add_argument("--out", type=Path, default=None, help="Optional path to write the card JSON to.")

    # -- approve ----------------------------------------------------------
    app = sub.add_parser("approve", help="Validate, approve, and write a card JSON to the corpus.")
    app.add_argument("card_json", type=Path, help="Path to the card JSON file produced by 'deconstruct'.")
    app.add_argument("--note", default=None, help="Optional reviewer note.")
    app.add_argument("--force", action="store_true", help="Allow duplicate source_ref in corpus.")
    app.add_argument("--corpus", type=Path, default=None,
                     help="Path to the JSONL corpus file (default: data/template_cards.jsonl).")

    return parser


# -- Stage 1: deconstruct ------------------------------------------------

def _cmd_deconstruct(args: argparse.Namespace) -> None:
    from src.template_ingest import deconstruct_template
    from src.vision_client import VisionClientError

    mime = _detect_mime(args.image)

    try:
        image_bytes = args.image.read_bytes()
    except OSError as exc:
        print(f"Error: cannot read image file '{args.image}': {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        card = deconstruct_template(
            image_bytes,
            mime,
            source_type=args.source_type,
            source_ref=args.source_ref,
            archetype=args.archetype,
            category=args.category,
            canvas_format=args.canvas_format,
        )
    except VisionClientError as exc:
        print(f"Vision client error: {exc}", file=sys.stderr)
        if "OPENAI_API_KEY" in str(exc):
            print(
                "Set OPENAI_API_KEY in your environment or .env file.  "
                "Get a key at https://platform.openai.com/api-keys",
                file=sys.stderr,
            )
        raise SystemExit(1)

    payload = json.dumps(card, ensure_ascii=False, indent=2)
    print(payload)

    if args.out:
        args.out.write_text(payload, encoding="utf-8")
        print(f"\nCard written to {args.out}", file=sys.stderr)


# -- Stage 2: approve ----------------------------------------------------

def _cmd_approve(args: argparse.Namespace) -> None:
    from src.template_ingest import (
        TemplateIngestError,
        append_template_card,
        approve_card,
        load_template_cards,
    )
    from src.schema import PromptValidationError

    # Read the card JSON
    try:
        card = json.loads(args.card_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: cannot read card JSON '{args.card_json}': {exc}", file=sys.stderr)
        raise SystemExit(1)

    # Approve
    try:
        approve_card(card, reviewer_note=args.note)
    except PromptValidationError as exc:
        print(f"Validation failed — card NOT approved: {exc}", file=sys.stderr)
        raise SystemExit(1)

    # Append to corpus
    append_kwargs: dict[str, Any] = {"force": args.force}
    if args.corpus is not None:
        append_kwargs["path"] = args.corpus

    try:
        out_path = append_template_card(card, **append_kwargs)
    except TemplateIngestError as exc:
        print(f"Cannot append to corpus: {exc}", file=sys.stderr)
        raise SystemExit(1)

    # Report
    corpus_path = args.corpus if args.corpus is not None else None
    total = len(load_template_cards() if corpus_path is None else load_template_cards(corpus_path))
    print(f"Approved and written to {out_path}")
    print(f"Corpus now has {total} card(s)")


# -- entry point ---------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "deconstruct":
            _cmd_deconstruct(args)
        elif args.command == "approve":
            _cmd_approve(args)
    except BrokenPipeError:
        # stdout closed (e.g. piped to head) — clean exit
        pass


if __name__ == "__main__":
    main()
