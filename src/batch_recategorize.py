"""
Batch API runner for D28 category recategorization.

Uses Anthropic Message Batches API to recategorize all non-procedural
agenda items using LLM understanding instead of keyword matching.
Modeled on batch_summarize.py.

Workflow:
  1. Export:  Build JSONL request file from DB items
  2. Submit:  Send batch to Anthropic API
  3. Poll:    Wait for completion (typically <24h)
  4. Import:  Parse results and write to DB

Usage:
  python batch_recategorize.py export                    # Build requests JSONL
  python batch_recategorize.py export --limit 100        # Test with subset
  python batch_recategorize.py submit                    # Submit batch to API
  python batch_recategorize.py status                    # Check batch status
  python batch_recategorize.py status BATCH_ID           # Check specific batch
  python batch_recategorize.py import                    # Import completed results
  python batch_recategorize.py import BATCH_ID           # Import specific batch
  python batch_recategorize.py import --dry-run          # Preview changes without writing
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from repo root
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

VALID_CATEGORIES = {
    "zoning", "budget", "housing", "public_safety", "environment",
    "infrastructure", "personnel", "contracts", "governance",
    "proclamation", "litigation", "other", "appointments", "procedural",
}


def _ensure_dirs() -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)


def _latest_batch_file(suffix: str) -> Path | None:
    """Find the most recent batch file with the given suffix."""
    files = sorted(BATCH_DIR.glob(f"*{suffix}"), reverse=True)
    return files[0] if files else None


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    return (PROMPT_DIR / filename).read_text(encoding="utf-8").strip()


# ── Export ───────────────────────────────────────────────────


def export_requests(
    city_fips: str = RICHMOND_FIPS,
    *,
    limit: int | None = None,
    category_filter: str | None = None,
) -> Path:
    """Build JSONL request file for the Batch API.

    Args:
        city_fips: FIPS code to filter by.
        limit: Max number of items to export (for testing).
        category_filter: Only export items with this current category.
    """
    _ensure_dirs()
    conn = get_connection()

    conditions = ["m.city_fips = %s", "LENGTH(ai.title) >= 20"]
    params: list[Any] = [city_fips]

    if category_filter:
        conditions.append("ai.category = %s")
        params.append(category_filter)

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT ai.id, ai.title, ai.description, ai.category,
               ai.item_number, ai.is_consent_calendar,
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

    system_prompt = _load_prompt("categorize_system.txt")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = BATCH_DIR / f"d28_requests_{timestamp}.jsonl"

    exported = 0
    skipped = 0

    with open(output_path, "w") as f:
        for item in items:
            title = (item.get("title") or "").strip()
            if not title or len(title) < 10:
                skipped += 1
                continue

            description = (item.get("description") or "").strip()
            consent = "Yes" if item.get("is_consent_calendar") else "No"

            user_prompt = f"Title: {title}"
            if description and len(description) > 10:
                # Truncate long descriptions
                desc_text = description[:1000]
                user_prompt += f"\nDescription: {desc_text}"
            user_prompt += f"\nConsent calendar: {consent}"

            request = {
                "custom_id": str(item["id"]),
                "params": {
                    "model": MODEL,
                    "max_tokens": MAX_TOKENS,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
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
    """Submit a JSONL request file to the Anthropic Batch API."""
    if anthropic is None:
        raise ImportError("anthropic package required")

    if requests_path is None:
        requests_path = _latest_batch_file("d28_requests_*.jsonl")
        if requests_path is None:
            print("No request files found. Run 'export' first.")
            sys.exit(1)

    with open(requests_path) as f:
        count = sum(1 for _ in f)

    print(f"Submitting {count} requests from {requests_path.name}")
    print(f"Model: {MODEL}")
    print(f"Estimated cost: ~${count * 0.0005:.2f} (Batch API 50% discount)")

    client = anthropic.Anthropic()

    requests = []
    with open(requests_path) as f:
        for line in f:
            requests.append(json.loads(line))

    batch = client.messages.batches.create(requests=requests)

    meta_path = BATCH_DIR / f"d28_batch_{batch.id}.json"
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
    print(f"Metadata saved: {meta_path.name}")
    return batch.id


# ── Status ───────────────────────────────────────────────────


def check_status(batch_id: str | None = None) -> dict[str, Any]:
    """Check the status of a submitted batch."""
    if anthropic is None:
        raise ImportError("anthropic package required")

    if batch_id is None:
        meta_file = _latest_batch_file("d28_batch_*.json")
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
    """Download and import results from a completed batch.

    Args:
        dry_run: Preview changes without writing to DB.
    """
    if anthropic is None:
        raise ImportError("anthropic package required")

    if batch_id is None:
        meta_file = _latest_batch_file("d28_batch_*.json")
        if meta_file is None:
            print("No batch metadata found. Run 'submit' first.")
            sys.exit(1)
        with open(meta_file) as f:
            meta = json.load(f)
        batch_id = meta["batch_id"]

    client = anthropic.Anthropic()

    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        print(f"Batch not complete yet. Status: {batch.processing_status}")
        print(f"Counts: {batch.request_counts}")
        sys.exit(1)

    print(f"Downloading results for batch {batch_id}...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = BATCH_DIR / f"d28_results_{batch_id}_{timestamp}.jsonl"

    results = []
    with open(results_path, "w") as f:
        for result in client.messages.batches.results(batch_id):
            result_dict = result.model_dump()
            f.write(json.dumps(result_dict) + "\n")
            results.append(result_dict)

    print(f"Downloaded {len(results)} results to {results_path.name}")

    # First pass: parse and validate all categories
    updates: list[tuple[str, str, str]] = []  # (item_id, new_category, old_raw)
    stats: dict[str, int] = {
        "total": len(results),
        "valid": 0,
        "invalid_category": 0,
        "errors": 0,
        "changed": 0,
        "unchanged": 0,
    }
    change_counts: dict[str, dict[str, int]] = {}  # old -> new -> count

    for result_dict in results:
        custom_id = result_dict["custom_id"]
        result_obj = result_dict["result"]

        if result_obj["type"] != "succeeded":
            stats["errors"] += 1
            continue

        message = result_obj["message"]
        text = message["content"][0]["text"].strip().lower()

        # Clean up response — handle minor formatting variations
        text = text.strip('"\'.- ')

        if text not in VALID_CATEGORIES:
            print(f"  INVALID {custom_id}: '{text}'")
            stats["invalid_category"] += 1
            continue

        updates.append((custom_id, text, ""))
        stats["valid"] += 1

    print(f"\nParsed: {stats['valid']} valid, {stats['invalid_category']} invalid, {stats['errors']} errors")

    if not updates:
        print("No valid updates to apply.")
        return stats

    # Second pass: fetch current categories and compute diff
    conn = get_connection()
    item_ids = [u[0] for u in updates]
    new_cats = {u[0]: u[1] for u in updates}

    # Fetch current categories in chunks
    current_cats: dict[str, str] = {}
    chunk_size = 500
    for i in range(0, len(item_ids), chunk_size):
        chunk = item_ids[i:i + chunk_size]
        placeholders = ",".join(["%s"] * len(chunk))
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, category FROM agenda_items WHERE id IN ({placeholders})",
                chunk,
            )
            for row in cur.fetchall():
                current_cats[str(row[0])] = row[1] or "other"

    # Compute change summary
    for item_id, new_cat in new_cats.items():
        old_cat = current_cats.get(item_id, "unknown")
        if old_cat == new_cat:
            stats["unchanged"] += 1
        else:
            stats["changed"] += 1
            key = f"{old_cat} -> {new_cat}"
            change_counts.setdefault(old_cat, {})
            change_counts[old_cat][new_cat] = change_counts[old_cat].get(new_cat, 0) + 1

    # Print change summary
    print(f"\n{'='*60}")
    print(f"CHANGE SUMMARY: {stats['changed']} changed, {stats['unchanged']} unchanged")
    print(f"{'='*60}")

    for old_cat in sorted(change_counts.keys()):
        transitions = change_counts[old_cat]
        for new_cat in sorted(transitions.keys(), key=lambda k: -transitions[k]):
            count = transitions[new_cat]
            print(f"  {old_cat:20s} -> {new_cat:20s}: {count:5d}")

    if dry_run:
        print(f"\n[DRY RUN] No changes written to database.")
        conn.close()
        return stats

    # Apply updates
    print(f"\nApplying {stats['changed']} category updates...")
    applied = 0
    for item_id, new_cat in new_cats.items():
        old_cat = current_cats.get(item_id, "unknown")
        if old_cat == new_cat:
            continue

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE agenda_items SET category = %s WHERE id = %s",
                (new_cat, item_id),
            )
        applied += 1

        if applied % 500 == 0:
            conn.commit()
            print(f"  ... applied {applied}...")

    conn.commit()
    conn.close()

    print(f"\nImport complete: {applied} categories updated")
    return stats


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch API runner for D28 category recategorization"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Export
    export_parser = subparsers.add_parser("export", help="Build JSONL request file")
    export_parser.add_argument("--limit", type=int, help="Limit number of items")
    export_parser.add_argument("--category", help="Only recategorize items with this current category")
    export_parser.add_argument("--fips", default=RICHMOND_FIPS)

    # Submit
    submit_parser = subparsers.add_parser("submit", help="Submit batch to API")
    submit_parser.add_argument("--file", type=Path, help="Specific request file")

    # Status
    status_parser = subparsers.add_parser("status", help="Check batch status")
    status_parser.add_argument("batch_id", nargs="?", help="Batch ID")

    # Import
    import_parser = subparsers.add_parser("import", help="Import completed results")
    import_parser.add_argument("batch_id", nargs="?", help="Batch ID")
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )

    args = parser.parse_args()

    if args.command == "export":
        export_requests(args.fips, limit=args.limit, category_filter=args.category)
    elif args.command == "submit":
        submit_batch(args.file)
    elif args.command == "status":
        check_status(args.batch_id)
    elif args.command == "import":
        import_results(args.batch_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
