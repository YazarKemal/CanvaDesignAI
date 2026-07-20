"""CLI entrypoint for CanvaDesignAI's dual-agent design pipeline.

Usage:
    python main.py "Grand Opening Cafe"
    python main.py "Grand Opening Cafe" --max-attempts 5
    python main.py "Grand Opening Cafe" --publish-to-canva --canva-design-type poster
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from src.canva_client import CanvaClient
from src.canva_pipeline import DEFAULT_CANVA_DESIGN_TYPE, publish_design_to_canva
from src.image_provider import OpenAIImageProvider
from src.orchestrator import DEFAULT_MAX_ATTEMPTS, run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a Canva design via the dual-agent pipeline.")
    parser.add_argument("concept", help='Design concept, e.g. "Grand Opening Cafe"')
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument(
        "--publish-to-canva",
        action="store_true",
        help="Generate the main visual (OpenAI) and push the design into a real Canva design.",
    )
    parser.add_argument("--canva-design-type", default=DEFAULT_CANVA_DESIGN_TYPE)
    args = parser.parse_args(argv)

    result = run_pipeline(args.concept, max_attempts=args.max_attempts)

    print(json.dumps(result.design, ensure_ascii=False, indent=2))
    status = "APPROVED" if result.approved else "BEST EFFORT (did not reach pass threshold)"
    print(f"\n--- {status} | score={result.review.score:.1f} | attempts={result.attempts} ---", file=sys.stderr)
    if not result.approved:
        print(f"Last feedback: {result.review.feedback}", file=sys.stderr)

    if args.publish_to_canva:
        if not result.approved:
            print("Skipping Canva publish: design was not approved.", file=sys.stderr)
            return 1

        canva_client = CanvaClient(access_token=os.environ["CANVA_ACCESS_TOKEN"])
        image_provider = OpenAIImageProvider()
        published = publish_design_to_canva(
            result.design,
            canva_client=canva_client,
            image_provider=image_provider,
            design_type=args.canva_design_type,
        )
        print(json.dumps(published, ensure_ascii=False, indent=2), file=sys.stderr)

    return 0 if result.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
