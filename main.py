"""CLI entrypoint for CaVDesign — the Canva Prompt Workbench / Design Agency.

Single-engine architecture: takes a plain concept and runs the three-stage
DeepSeek pipeline (Architect -> Generator -> Reviewer/Critic) to produce a
Canva automation card (magic_media_prompt, layer_typography_architecture,
direct_action_tip). Never chats, never asks a question — card only.

Usage:
    python main.py "Kafe acilisi icin Instagram gonderisi"
    python main.py "Grand Opening Cafe" --max-attempts 5
    python main.py "Grand Opening Cafe" --raw     # print just the Magic Media prompt string
    python main.py "Grand Opening Cafe" --paste   # print a block ready to paste into a
                                                   # Claude/ChatGPT chat with Canva connected
    python main.py "Grand Opening Cafe" --brand example-cafe
    python main.py "Grand Opening Cafe" --adapt-to instagram_story,banner
"""

from __future__ import annotations

import argparse
import json
import sys

from src.brand_profiles import BrandNotFoundError, load_brand
from src.omni_channel import UnknownFormatError, generate_omni_channel_set
from src.orchestrator import DEFAULT_MAX_ATTEMPTS, PipelineError, run_pipeline
from src.paste_render import render_for_assistant_paste
from src.schema import PromptValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Canva automation card via the single-engine DeepSeek workbench."
    )
    parser.add_argument("concept", help='Plain concept, e.g. "Grand Opening Cafe"')
    parser.add_argument("--brand", default=None, help="Brand profile slug (config/brands/<slug>.json).")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print only the magic_media_prompt string (ready to paste into Canva Magic Media / DALL-E 3).",
    )
    parser.add_argument(
        "--paste",
        action="store_true",
        help="Print a plain-text block (directive + full card) ready to paste into a "
        "Claude/ChatGPT chat that has a Canva tool connected.",
    )
    parser.add_argument(
        "--adapt-to",
        default=None,
        help="Comma-separated target formats (e.g. instagram_story,banner) to additionally "
        "adapt the approved card to, once it passes.",
    )
    args = parser.parse_args(argv)

    try:
        result = run_pipeline(args.concept, brand=args.brand, max_attempts=args.max_attempts)
    except (PipelineError, BrandNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.raw:
        print(result.card["magic_media_prompt"])
    elif args.paste:
        print(render_for_assistant_paste(result.card))
    else:
        print(json.dumps(result.card, ensure_ascii=False, indent=2))

    status = "APPROVED" if result.approved else "BEST EFFORT (did not reach pass threshold)"
    print(f"\n--- {status} | score={result.review.score:.1f} | attempts={result.attempts} ---", file=sys.stderr)
    if not result.approved:
        print(f"Last feedback: {result.review.feedback}", file=sys.stderr)

    if args.adapt_to and result.approved:
        formats = [f.strip() for f in args.adapt_to.split(",") if f.strip()]
        brand_profile = load_brand(args.brand) if args.brand else None
        try:
            variants = generate_omni_channel_set(result.card, formats, brand=brand_profile)
        except (UnknownFormatError, PromptValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for fmt, card in variants.items():
            print(f"\n--- {fmt} ---", file=sys.stderr)
            print(json.dumps(card, ensure_ascii=False, indent=2))

    return 0 if result.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
