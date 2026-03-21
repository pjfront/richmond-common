"""
Batch API runner for R1 summary regeneration.

Uses Anthropic Message Batches API to regenerate all plain language
summaries and headlines at 50% cost discount. Designed for bulk
regeneration (~15K items), not incremental updates.

Workflow:
  1. Export:  Build JSONL request file from DB items
  2. Submit:  Send batch to Anthropic API
  3. Poll:    Wait for completion (typically <24h)
  4. Import:  Parse results and write to DB

Usage:
  python batch_summarize.py export                    # Build requests JSONL
  python batch_summarize.py export --limit 100        # Test with subset
  python batch_summarize.py submit                    # Submit batch to API
  python batch_summarize.py status                    # Check batch status
  python batch_summarize.py status BATCH_ID           # Check specific batch
  python batch_summarize.py import                    # Import completed results
  python batch_summarize.py import BATCH_ID           # Import specific batch
"""

from __future__ import annotations

import argparse
import json
import sys
import time
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
from plain_language_summarizer import _load_prompt, _parse_response, should_summarize  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
BATCH_DIR = DATA_DIR / "batch_runs"

# Model for R1 regeneration
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 300


def _ensure_dirs() -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)


def _latest_batch_file(suffix: str) -> Path | None:
    """Find the most recent batch file with the given suffix."""
    files = sorted(BATCH_DIR.glob(f"*{suffix}"), reverse=True)
    return files[0] if files else None


# ── Export ───────────────────────────────────────────────────


def export_requests(
    city_fips: str = RICHMOND_FIPS,
    *,
    limit: int | None = None,
    meeting_id: str | None = None,
) -> Path:
    """Build JSONL request file for the Batch API.

    Each line is a JSON object with custom_id and params matching
    the Anthropic Message Batches API format.
    """
    _ensure_dirs()
    conn = get_connection()

    conditions = ["m.city_fips = %s"]
    params: list[Any] = [city_fips]

    if meeting_id:
        conditions.append("ai.meeting_id = %s")
        params.append(meeting_id)

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT ai.id, ai.title, ai.description, ai.category,
               ai.department, ai.financial_amount, ai.item_number,
               m.meeting_date,
               (SELECT string_agg(aia.extracted_text, E'\n\n---\n\n'
                    ORDER BY aia.created_at)
                FROM agenda_item_attachments aia
                WHERE aia.agenda_item_id = ai.id
               ) AS staff_report
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

    system_prompt = _load_prompt("plain_language_system.txt")
    user_template = _load_prompt("plain_language_user.txt")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = BATCH_DIR / f"r1_requests_{timestamp}.jsonl"

    exported = 0
    skipped = 0

    with open(output_path, "w") as f:
        for item in items:
            if not should_summarize(item["category"]):
                skipped += 1
                continue

            title_text = (item.get("title") or "").strip()
            description_text = (item.get("description") or "").strip()
            if len(f"{title_text} {description_text}".strip()) < 20:
                skipped += 1
                continue

            # Truncate staff report to keep token budget reasonable
            staff_report = item.get("staff_report") or ""
            if staff_report and len(staff_report.strip()) > 50:
                staff_report = staff_report.strip()[:4000]
            else:
                staff_report = "(No staff report available)"

            user_prompt = user_template.format(
                title=item["title"],
                description=item.get("description") or "(No description provided)",
                category=item.get("category") or "unknown",
                department=item.get("department") or "Not specified",
                financial_amount=item.get("financial_amount") or "None",
                staff_report=staff_report,
            )

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
    return output_path


# ── Submit ───────────────────────────────────────────────────


def submit_batch(requests_path: Path | None = None) -> str:
    """Submit a JSONL request file to the Anthropic Batch API."""
    if anthropic is None:
        raise ImportError("anthropic package required")

    if requests_path is None:
        requests_path = _latest_batch_file("_requests_*.jsonl")
        if requests_path is None:
            print("No request files found. Run 'export' first.")
            sys.exit(1)

    # Count requests for confirmation
    with open(requests_path) as f:
        count = sum(1 for _ in f)

    print(f"Submitting {count} requests from {requests_path.name}")
    print(f"Model: {MODEL}")
    print(f"Estimated cost: ~${count * 0.00003:.2f} (Batch API 50% discount)")

    client = anthropic.Anthropic()

    # Read requests as list of dicts
    requests = []
    with open(requests_path) as f:
        for line in f:
            requests.append(json.loads(line))

    batch = client.messages.batches.create(requests=requests)

    # Save batch metadata
    meta_path = BATCH_DIR / f"r1_batch_{batch.id}.json"
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
        meta_file = _latest_batch_file("_batch_*.json")
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


def import_results(batch_id: str | None = None) -> dict[str, int]:
    """Download and import results from a completed batch."""
    if anthropic is None:
        raise ImportError("anthropic package required")

    if batch_id is None:
        meta_file = _latest_batch_file("_batch_*.json")
        if meta_file is None:
            print("No batch metadata found. Run 'submit' first.")
            sys.exit(1)
        with open(meta_file) as f:
            meta = json.load(f)
        batch_id = meta["batch_id"]

    client = anthropic.Anthropic()

    # Check if batch is complete
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        print(f"Batch not complete yet. Status: {batch.processing_status}")
        print(f"Counts: {batch.request_counts}")
        sys.exit(1)

    print(f"Downloading results for batch {batch_id}...")

    # Stream results and save to JSONL for audit trail
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = BATCH_DIR / f"r1_results_{batch_id}_{timestamp}.jsonl"

    results = []
    with open(results_path, "w") as f:
        for result in client.messages.batches.results(batch_id):
            result_dict = result.model_dump()
            f.write(json.dumps(result_dict) + "\n")
            results.append(result_dict)

    print(f"Downloaded {len(results)} results to {results_path.name}")

    # Import to database
    conn = get_connection()
    stats = {"imported": 0, "errors": 0, "no_headline": 0}

    for result_dict in results:
        custom_id = result_dict["custom_id"]
        result_obj = result_dict["result"]

        if result_obj["type"] != "succeeded":
            error_type = result_obj.get("type", "unknown")
            print(f"  FAILED {custom_id}: {error_type}")
            stats["errors"] += 1
            continue

        message = result_obj["message"]
        text = message["content"][0]["text"]
        model = message["model"]

        parsed = _parse_response(text)

        if parsed["summary"] is None:
            print(f"  EMPTY {custom_id}: no summary parsed")
            stats["errors"] += 1
            continue

        if parsed["headline"] is None:
            stats["no_headline"] += 1

        with conn.cursor() as cur:
            cur.execute(
                """UPDATE agenda_items
                   SET plain_language_summary = %s,
                       summary_headline = %s,
                       plain_language_generated_at = %s,
                       plain_language_model = %s
                   WHERE id = %s""",
                (
                    parsed["summary"],
                    parsed["headline"],
                    datetime.now(timezone.utc),
                    model,
                    custom_id,
                ),
            )
        stats["imported"] += 1

        if stats["imported"] % 500 == 0:
            conn.commit()
            print(f"  ... imported {stats['imported']}...")

    conn.commit()
    conn.close()

    print(f"\nImport complete:")
    print(f"  {stats['imported']} summaries imported")
    print(f"  {stats['no_headline']} missing headline (fallback: summary only)")
    if stats["errors"]:
        print(f"  {stats['errors']} errors")

    return stats


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch API runner for R1 summary regeneration"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Export
    export_parser = subparsers.add_parser("export", help="Build JSONL request file")
    export_parser.add_argument("--limit", type=int, help="Limit number of items")
    export_parser.add_argument("--meeting-id", help="Single meeting UUID")
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

    args = parser.parse_args()

    if args.command == "export":
        export_requests(
            args.fips,
            limit=args.limit,
            meeting_id=args.meeting_id,
        )
    elif args.command == "submit":
        submit_batch(args.file)
    elif args.command == "status":
        check_status(args.batch_id)
    elif args.command == "import":
        import_results(args.batch_id)


if __name__ == "__main__":
    main()
