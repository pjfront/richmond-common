"""
Operator Decision Briefing -- Session-start summary of pending decisions (S7).

Run at the start of a Claude Code session to see what needs attention.

Usage:
    python decision_briefing.py                       # Text briefing
    python decision_briefing.py --format json          # JSON output
    python decision_briefing.py --include-resolved     # Show recently resolved
    python decision_briefing.py --check                # Exit code 1 if critical pending
    python decision_briefing.py --city-fips 0660620   # Explicit city
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection  # noqa: E402
from decision_queue import (  # noqa: E402
    get_decision_briefing,
    get_decision_summary,
    get_pending,
    get_recently_resolved,
)

DEFAULT_FIPS = "0660620"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project -- Operator Decision Briefing",
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--city-fips", default=DEFAULT_FIPS,
        help=f"City FIPS code (default: {DEFAULT_FIPS})",
    )
    parser.add_argument(
        "--include-resolved", action="store_true",
        help="Include recently resolved decisions",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Exit code 1 if critical or high severity decisions are pending",
    )
    args = parser.parse_args()

    conn = get_connection()

    try:
        if args.format == "json":
            summary = get_decision_summary(conn, args.city_fips)
            pending = get_pending(conn, args.city_fips)
            output: dict = {
                "summary": summary,
                "pending": pending,
            }
            if args.include_resolved:
                output["recently_resolved"] = get_recently_resolved(
                    conn, args.city_fips,
                )
            # Convert datetimes for JSON serialization
            print(json.dumps(output, indent=2, default=str))
        else:
            briefing = get_decision_briefing(
                conn, args.city_fips,
                include_resolved=args.include_resolved,
            )
            print(briefing)

        if args.check:
            summary = get_decision_summary(conn, args.city_fips)
            critical_or_high = (
                summary["counts"].get("critical", 0)
                + summary["counts"].get("high", 0)
            )
            if critical_or_high > 0:
                sys.exit(1)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
