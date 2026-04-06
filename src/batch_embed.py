"""
Batch embedding CLI for Layer 3 activation.

Generates OpenAI text-embedding-3-small embeddings for all content
tables. Unlike batch_recategorize.py (Anthropic Batch API), this
uses synchronous OpenAI calls — embeddings are fast (~100ms per
batch of 100 texts) and don't need the async batch workflow.

Usage:
  python batch_embed.py generate                    # All tables
  python batch_embed.py generate --table agenda_items  # Single table
  python batch_embed.py generate --limit 100        # Test subset
  python batch_embed.py stats                       # Coverage report
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, RICHMOND_FIPS  # noqa: E402
from embedding_generator import embed_table, get_coverage_stats, TABLE_CONFIGS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TABLES = list(TABLE_CONFIGS.keys())


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate embeddings for un-embedded rows."""
    conn = get_connection()
    tables = [args.table] if args.table else TABLES
    total = 0

    for table in tables:
        if table not in TABLE_CONFIGS:
            logger.error(f"Unknown table: {table}. Valid: {TABLES}")
            sys.exit(1)

        count = embed_table(
            conn,
            table,
            city_fips=args.city_fips,
            limit=args.limit,
        )
        total += count

    logger.info(f"Done — {total} rows embedded across {len(tables)} table(s)")
    conn.close()


def cmd_stats(args: argparse.Namespace) -> None:
    """Show embedding coverage per table."""
    conn = get_connection()
    stats = get_coverage_stats(conn, city_fips=args.city_fips)
    conn.close()

    print("\n  Embedding Coverage")
    print("  " + "─" * 50)
    total_all = 0
    embedded_all = 0
    for table, s in stats.items():
        pct = (s["embedded"] / s["total"] * 100) if s["total"] > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {table:<20s} {bar} {s['embedded']:>6d}/{s['total']:<6d} ({pct:.0f}%)")
        total_all += s["total"]
        embedded_all += s["embedded"]

    pct_all = (embedded_all / total_all * 100) if total_all > 0 else 0
    print("  " + "─" * 50)
    print(f"  {'TOTAL':<20s} {'':>22s} {embedded_all:>6d}/{total_all:<6d} ({pct_all:.0f}%)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch embedding generator for Layer 3"
    )
    parser.add_argument(
        "--city-fips", default=RICHMOND_FIPS,
        help="City FIPS code (default: Richmond 0660620)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate embeddings")
    gen.add_argument("--table", choices=TABLES, help="Single table to embed")
    gen.add_argument("--limit", type=int, help="Max rows per table (for testing)")

    sub.add_parser("stats", help="Show coverage statistics")

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
