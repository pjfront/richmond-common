"""
Backfill agenda_item_attachments from scraped eSCRIBE data on disk.

Reads meeting_data.json files from src/data/raw/escribemeetings/,
matches eSCRIBE items to DB agenda items by title similarity,
loads .txt attachment files, and inserts into agenda_item_attachments.

Usage:
  python backfill_attachments.py                   # Process all scraped meetings
  python backfill_attachments.py --meeting-dir DIR  # Process single meeting
  python backfill_attachments.py --dry-run          # Show what would be inserted
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, RICHMOND_FIPS  # noqa: E402
from escribemeetings_enricher import match_items, title_similarity  # noqa: E402

ESCRIBEMEETINGS_DIR = Path(__file__).parent / "data" / "raw" / "escribemeetings"


def find_meeting_dirs() -> list[Path]:
    """Find all scraped eSCRIBE meeting directories with meeting_data.json."""
    if not ESCRIBEMEETINGS_DIR.exists():
        return []
    dirs = []
    for d in sorted(ESCRIBEMEETINGS_DIR.iterdir()):
        if d.is_dir() and (d / "meeting_data.json").exists():
            dirs.append(d)
    return dirs


def load_meeting_data(meeting_dir: Path) -> dict:
    """Load meeting_data.json from a scraped meeting directory."""
    path = meeting_dir / "meeting_data.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_db_items_for_date(
    conn, meeting_date: str, city_fips: str = RICHMOND_FIPS
) -> list[dict[str, Any]]:
    """Get agenda items from DB for a specific meeting date."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT ai.id, ai.item_number, ai.title, ai.meeting_id
               FROM agenda_items ai
               JOIN meetings m ON ai.meeting_id = m.id
               WHERE m.city_fips = %s AND m.meeting_date = %s
               ORDER BY ai.item_number""",
            (city_fips, meeting_date),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def load_attachment_texts(
    meeting_dir: Path, escribe_items: list[dict]
) -> dict[str, list[dict[str, Any]]]:
    """Load attachment text files for each eSCRIBE item.

    Returns dict mapping eSCRIBE item_number -> list of attachment dicts
    with keys: filename, document_id, source_url, extracted_text, char_count
    """
    attachments_dir = meeting_dir / "attachments"
    result: dict[str, list[dict[str, Any]]] = {}

    for item in escribe_items:
        item_num = item.get("item_number", "")
        if not item_num:
            continue

        item_attachments = []
        for att in item.get("attachments", []):
            doc_id = str(att.get("document_id", ""))
            filename = att.get("name", "")
            url = att.get("url", "")

            # Find the .txt file on disk by doc_id
            text = ""
            if attachments_dir.exists():
                for txt_file in attachments_dir.glob(f"*doc{doc_id}.txt"):
                    try:
                        text = txt_file.read_text(encoding="utf-8").strip()
                    except (OSError, UnicodeDecodeError):
                        pass
                    break

            if text and len(text) > 50:
                # Strip NUL bytes from PDF extraction artifacts
                text = text.replace("\x00", "")
                item_attachments.append({
                    "filename": filename,
                    "document_id": doc_id,
                    "source_url": url,
                    "extracted_text": text,
                    "char_count": len(text),
                })

        if item_attachments:
            result[item_num] = item_attachments

    return result


def check_existing(conn, agenda_item_id: str) -> bool:
    """Check if attachments already exist for this agenda item."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM agenda_item_attachments WHERE agenda_item_id = %s",
            (agenda_item_id,),
        )
        return cur.fetchone()[0] > 0


def process_meeting(
    conn,
    meeting_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Process a single scraped meeting directory."""
    stats = {"matched": 0, "inserted": 0, "skipped_existing": 0, "no_text": 0}

    data = load_meeting_data(meeting_dir)
    meeting_date = data.get("meeting_date", "") or data.get("date", "")
    escribe_items = data.get("items", [])

    if not meeting_date or not escribe_items:
        print(f"  Skipping {meeting_dir.name}: no date or items")
        return stats

    print(f"  Meeting: {meeting_date} ({len(escribe_items)} eSCRIBE items)")

    # Get DB items for this date
    db_items = get_db_items_for_date(conn, meeting_date)
    if not db_items:
        print(f"  No DB agenda items found for {meeting_date}")
        return stats

    print(f"  DB items: {len(db_items)}")

    # Match eSCRIBE items to DB items
    matches = match_items(db_items, escribe_items)
    print(f"  Matched: {len(matches)} items")

    # Load attachment texts
    att_by_escribe = load_attachment_texts(meeting_dir, escribe_items)

    # Build reverse map: agenda item_number -> DB item
    db_by_num = {item["item_number"]: item for item in db_items}

    for agenda_num, escribe_num in matches.items():
        db_item = db_by_num.get(agenda_num)
        if not db_item:
            continue

        attachments = att_by_escribe.get(escribe_num, [])
        if not attachments:
            stats["no_text"] += 1
            continue

        stats["matched"] += 1

        if check_existing(conn, str(db_item["id"])):
            stats["skipped_existing"] += 1
            continue

        for att in attachments:
            if dry_run:
                print(f"    [DRY] {agenda_num} <- {att['filename'][:50]} ({att['char_count']} chars)")
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO agenda_item_attachments
                           (agenda_item_id, document_id, filename, source_url,
                            extracted_text, char_count)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (
                            str(db_item["id"]),
                            att["document_id"],
                            att["filename"],
                            att["source_url"],
                            att["extracted_text"],
                            att["char_count"],
                        ),
                    )
                stats["inserted"] += 1

    if not dry_run:
        conn.commit()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill agenda item attachments from scraped eSCRIBE data"
    )
    parser.add_argument("--meeting-dir", type=Path, help="Single meeting directory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fips", default=RICHMOND_FIPS)
    args = parser.parse_args()

    if args.meeting_dir:
        meeting_dirs = [args.meeting_dir]
    else:
        meeting_dirs = find_meeting_dirs()

    if not meeting_dirs:
        print("No scraped meeting directories found.")
        sys.exit(1)

    print(f"Found {len(meeting_dirs)} meeting directories")
    conn = get_connection()

    totals = {"matched": 0, "inserted": 0, "skipped_existing": 0, "no_text": 0}

    for meeting_dir in meeting_dirs:
        print(f"\n--{meeting_dir.name} --")
        stats = process_meeting(conn, meeting_dir, dry_run=args.dry_run)
        for k, v in stats.items():
            totals[k] += v

    conn.close()

    print(f"\n{'='*50}")
    print(f"Total: {totals['matched']} items with attachments")
    print(f"  {totals['inserted']} attachments inserted")
    print(f"  {totals['skipped_existing']} items already had attachments")
    print(f"  {totals['no_text']} matched items with no readable text")


if __name__ == "__main__":
    main()
