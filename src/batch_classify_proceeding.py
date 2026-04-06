"""
Batch API runner for proceeding type classification (S22).

Uses Anthropic Message Batches API to classify agenda items into
proceeding types: resolution, ordinance, contract, appropriation,
appointment, hearing, proclamation, report, censure, appeal,
consent, other.

Follows the same 4-step workflow as batch_recategorize.py:
  1. Export:  Build JSONL request file from DB items
  2. Submit:  Send batch to Anthropic API
  3. Poll:    Wait for completion
  4. Import:  Parse results and write to DB

Usage:
  python batch_classify_proceeding.py export                    # Build requests
  python batch_classify_proceeding.py export --limit 200        # Test subset
  python batch_classify_proceeding.py submit                    # Submit batch
  python batch_classify_proceeding.py status                    # Check status
  python batch_classify_proceeding.py status BATCH_ID           # Specific batch
  python batch_classify_proceeding.py import                    # Import results
  python batch_classify_proceeding.py import --dry-run          # Preview
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from db import get_connection, RICHMOND_FIPS  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
BATCH_DIR = DATA_DIR / "batch_runs"
PROMPT_DIR = Path(__file__).parent / "prompts"

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 20  # Single word response
FILE_PREFIX = "proceeding"

VALID_TYPES = {
    "resolution", "ordinance", "contract", "appropriation",
    "appointment", "hearing", "proclamation", "report",
    "censure", "appeal", "consent", "other",
}


def _ensure_dirs() -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)


def _latest_batch_file(suffix: str) -> Path | None:
    files = sorted(BATCH_DIR.glob(f"*{suffix}"), reverse=True)
    return files[0] if files else None


def _load_prompt(filename: str) -> str:
    return (PROMPT_DIR / filename).read_text(encoding="utf-8").strip()


# ── Export ───────────────────────────────────────────────────


def export_requests(
    city_fips: str = RICHMOND_FIPS,
    *,
    limit: int | None = None,
    only_unclassified: bool = True,
) -> Path:
    """Build JSONL request file for the Batch API."""
    _ensure_dirs()
    conn = get_connection()

    conditions = ["m.city_fips = %s", "LENGTH(ai.title) >= 10"]
    params: list[Any] = [city_fips]

    if only_unclassified:
        conditions.append("ai.proceeding_type IS NULL")

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT ai.id, ai.title, ai.description, ai.category,
               ai.item_number, ai.is_consent_calendar,
               ai.financial_amount, ai.resolution_number,
               m.meeting_date
        FROM agenda_items ai
        JOIN meetings m ON ai.meeting_id = m.id
        WHERE {where_clause}
        ORDER BY m.meeting_date ASC, ai.item_number ASC
    """

    if limit:
        query += f" LIMIT {limit}"

    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [desc[0] for desc in cur.description]
        items = [dict(zip(cols, row)) for row in cur.fetchall()]

    conn.close()

    system_prompt = _load_prompt("proceeding_type_system.txt")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = BATCH_DIR / f"{FILE_PREFIX}_requests_{timestamp}.jsonl"

    exported = 0
    skipped = 0

    with open(output_path, "w") as f:
        for item in items:
            title = (item.get("title") or "").strip()
            if not title:
                skipped += 1
                continue

            # Build user prompt with available context
            parts = [f"Title: {title}"]

            description = (item.get("description") or "").strip()
            if description and len(description) > 10:
                parts.append(f"Description: {description[:1000]}")

            if item.get("resolution_number"):
                parts.append(f"Resolution number: {item['resolution_number']}")

            if item.get("financial_amount"):
                parts.append(f"Financial amount: {item['financial_amount']}")

            if item.get("category"):
                parts.append(f"Category: {item['category']}")

            consent = "Yes" if item.get("is_consent_calendar") else "No"
            parts.append(f"Consent calendar: {consent}")

            request = {
                "custom_id": str(item["id"]),
                "params": {
                    "model": MODEL,
                    "max_tokens": MAX_TOKENS,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": "\n".join(parts)}],
                },
            }

            f.write(json.dumps(request) + "\n")
            exported += 1

    print(f"Exported {exported} requests ({skipped} skipped)")
    print(f"Output: {output_path}")
    print(f"Estimated cost: ~${exported * 0.0005:.2f} (Batch API 50% discount)")
    return output_path


# ── Submit ───────────────────────────────────────────────────


def submit_batch(requests_path: Path | None = None) -> str:
    """Submit JSONL to Anthropic Batch API."""
    if anthropic is None:
        raise ImportError("anthropic package required")

    if requests_path is None:
        requests_path = _latest_batch_file(f"{FILE_PREFIX}_requests_*.jsonl")
        if requests_path is None:
            print("No request files found. Run 'export' first.")
            sys.exit(1)

    with open(requests_path) as f:
        count = sum(1 for _ in f)

    print(f"Submitting {count} requests from {requests_path.name}")
    print(f"Model: {MODEL}")

    client = anthropic.Anthropic()

    requests_list = []
    with open(requests_path) as f:
        for line in f:
            requests_list.append(json.loads(line))

    batch = client.messages.batches.create(requests=requests_list)

    meta_path = BATCH_DIR / f"{FILE_PREFIX}_batch_{batch.id}.json"
    meta = {
        "batch_id": batch.id,
        "requests_file": str(requests_path),
        "request_count": count,
        "model": MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "processing_status": batch.processing_status,
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Batch submitted: {batch.id}")
    print(f"Status: {batch.processing_status}")
    return batch.id


# ── Status ───────────────────────────────────────────────────


def check_status(batch_id: str | None = None) -> dict[str, Any]:
    """Check batch status."""
    if anthropic is None:
        raise ImportError("anthropic package required")

    if batch_id is None:
        meta_file = _latest_batch_file(f"{FILE_PREFIX}_batch_*.json")
        if meta_file is None:
            print("No batch metadata found. Run 'submit' first.")
            sys.exit(1)
        with open(meta_file) as f:
            meta = json.load(f)
        batch_id = meta["batch_id"]

    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(batch_id)

    print(f"Batch: {batch.id}")
    print(f"Status: {batch.processing_status}")
    print(f"Counts: {batch.request_counts}")

    if batch.ended_at:
        print(f"Ended at: {batch.ended_at}")

    return {
        "batch_id": batch.id,
        "status": batch.processing_status,
        "counts": batch.request_counts,
    }


# ── Import ───────────────────────────────────────────────────


def import_results(
    batch_id: str | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Download and import proceeding type results."""
    if anthropic is None:
        raise ImportError("anthropic package required")

    if batch_id is None:
        meta_file = _latest_batch_file(f"{FILE_PREFIX}_batch_*.json")
        if meta_file is None:
            print("No batch metadata found. Run 'submit' first.")
            sys.exit(1)
        with open(meta_file) as f:
            meta = json.load(f)
        batch_id = meta["batch_id"]

    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(batch_id)

    if batch.processing_status != "ended":
        print(f"Batch not complete. Status: {batch.processing_status}")
        sys.exit(1)

    print(f"Downloading results for batch {batch_id}...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = BATCH_DIR / f"{FILE_PREFIX}_results_{batch_id}_{timestamp}.jsonl"

    results = []
    with open(results_path, "w") as f:
        for result in client.messages.batches.results(batch_id):
            result_dict = result.model_dump()
            f.write(json.dumps(result_dict) + "\n")
            results.append(result_dict)

    print(f"Downloaded {len(results)} results")

    # Parse and validate
    updates: list[tuple[str, str]] = []  # (item_id, proceeding_type)
    stats: dict[str, int] = {
        "total": len(results),
        "valid": 0,
        "invalid_type": 0,
        "errors": 0,
    }
    type_counts: dict[str, int] = {}

    for result_dict in results:
        custom_id = result_dict["custom_id"]
        result_obj = result_dict["result"]

        if result_obj["type"] != "succeeded":
            stats["errors"] += 1
            continue

        text = result_obj["message"]["content"][0]["text"].strip().lower()
        text = text.strip('"\'.- ')

        if text not in VALID_TYPES:
            print(f"  INVALID {custom_id}: '{text}'")
            stats["invalid_type"] += 1
            continue

        updates.append((custom_id, text))
        stats["valid"] += 1
        type_counts[text] = type_counts.get(text, 0) + 1

    print(f"\nParsed: {stats['valid']} valid, {stats['invalid_type']} invalid, {stats['errors']} errors")

    # Distribution summary
    print(f"\nType distribution:")
    for ptype in sorted(type_counts, key=lambda k: -type_counts[k]):
        print(f"  {ptype:<20s}: {type_counts[ptype]:>5d}")

    if not updates or dry_run:
        if dry_run:
            print(f"\n[DRY RUN] No changes written.")
        return stats

    # Apply updates
    conn = get_connection()
    applied = 0
    chunk_size = 500

    for i in range(0, len(updates), chunk_size):
        chunk = updates[i:i + chunk_size]
        with conn.cursor() as cur:
            for item_id, ptype in chunk:
                cur.execute(
                    "UPDATE agenda_items SET proceeding_type = %s WHERE id = %s",
                    (ptype, item_id),
                )
                applied += 1
        conn.commit()

    conn.close()
    stats["applied"] = applied
    print(f"\nApplied {applied} proceeding type classifications")
    return stats


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch proceeding type classification (S22)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    exp = sub.add_parser("export", help="Build JSONL requests")
    exp.add_argument("--limit", type=int, help="Max items to export")
    exp.add_argument("--all", action="store_true", help="Include already-classified items")

    sub.add_parser("submit", help="Submit batch to Anthropic API")

    status = sub.add_parser("status", help="Check batch status")
    status.add_argument("batch_id", nargs="?", help="Specific batch ID")

    imp = sub.add_parser("import", help="Import completed results")
    imp.add_argument("batch_id", nargs="?", help="Specific batch ID")
    imp.add_argument("--dry-run", action="store_true", help="Preview without writing")

    args = parser.parse_args()

    if args.command == "export":
        export_requests(limit=args.limit, only_unclassified=not args.all)
    elif args.command == "submit":
        submit_batch()
    elif args.command == "status":
        check_status(getattr(args, "batch_id", None))
    elif args.command == "import":
        import_results(getattr(args, "batch_id", None), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
