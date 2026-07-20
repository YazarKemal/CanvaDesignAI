"""CLI entrypoint for CanvaDesignAI's dual-agent design pipeline.

Usage:
    python main.py "Grand Opening Cafe"
    python main.py "Grand Opening Cafe" --max-attempts 5
"""

from __future__ import annotations

import argparse
import json
import sys

from src.orchestrator import DEFAULT_MAX_ATTEMPTS, run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a Canva design via the dual-agent pipeline.")
    parser.add_argument("concept", help='Design concept, e.g. "Grand Opening Cafe"')
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    args = parser.parse_args(argv)

    result = run_pipeline(args.concept, max_attempts=args.max_attempts)

    print(json.dumps(result.design, ensure_ascii=False, indent=2))
    status = "APPROVED" if result.approved else "BEST EFFORT (did not reach pass threshold)"
    print(f"\n--- {status} | score={result.review.score:.1f} | attempts={result.attempts} ---", file=sys.stderr)
    if not result.approved:
        print(f"Last feedback: {result.review.feedback}", file=sys.stderr)

    return 0 if result.approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
