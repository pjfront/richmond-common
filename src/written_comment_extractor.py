"""
S21 Phase E — Written Public Comment Extraction

Extracts individual written comments (emails submitted to the City Clerk)
from Archive Center PDFs and eSCRIBE eComments. Writes to `public_comments`
with comment_type='written' so theme_extractor.py can include them.

Two document types in AMID=31:
  - Standalone comment compilations (no ROLL CALL markers, entire doc is emails)
  - Minutes with appendix (comments after ADJOURNMENT marker)

Both are handled by the same parser: find the comment boundary, split on
From: headers, extract speaker/subject/body per email.

Usage:
  python written_comment_extractor.py extract                    # All documents
  python written_comment_extractor.py extract --meeting-date 2026-02-03
  python written_comment_extractor.py extract --dry-run
  python written_comment_extractor.py extract --limit 5
  python written_comment_extractor.py extract --force            # Re-extract already-processed
  python written_comment_extractor.py status                     # Coverage report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, RICHMOND_FIPS  # noqa: E402
from text_utils import normalize_item_number, resolve_item_id  # noqa: E402

# -- Constants ------------------------------------------------

MINUTES_AMID = 31
SOURCE_ARCHIVE = "archive_center"
SOURCE_ESCRIBEMEETINGS = "escribemeetings"
BOILERPLATE = "This email originated from outside of the City's email system."
ESCRIBEMEETINGS_DIR = Path(__file__).parent / "data" / "raw" / "escribemeetings"

# Regex: multi-line From: header (Format A) — most common
# Matches "From:\n{name}\n" at start of a line
_FROM_MULTILINE = re.compile(r"^From:\s*\n", re.MULTILINE)

# Regex: inline uppercase FROM: header (Format B) — rare, clerk-typed
# Matches "FROM:  NAME" at start of a line
_FROM_INLINE = re.compile(r"^FROM:\s{2,}\S", re.MULTILINE)

# Item reference patterns in subject lines, tried in order
_ITEM_PATTERNS = [
    re.compile(r"[Aa]genda\s+[Ii]tem\s+#?\s*([A-Za-z][\-.]?\d+(?:[.\-]\w+)*)"),
    re.compile(r"[Ii]tem\s+#?\s*([A-Za-z][\-.]?\d+(?:[.\-]\w+)*)"),
    re.compile(r"[Cc]onsent\s+[Cc]alendar\s+[Ii]tem\s+([A-Za-z]?[\d]+(?:[.\-]\w+)*)"),
    re.compile(r"\b([A-Z][\-.]?\d+(?:\.\w+)?)\b"),  # bare "O-1", "P2", "V.1"
]

# Subjects that indicate open forum (no specific agenda item)
_OPEN_FORUM_KEYWORDS = [
    "open forum", "public comment", "general comment", "general public",
    "open session", "public comments",
]


# ── Pure Parsing Functions ───��──────────────────────────────────────────────


def find_comment_boundary(raw_text: str) -> str:
    """Return the portion of text that contains written comments.

    For minutes-with-appendix: everything after the last ADJOURNMENT marker.
    For standalone compilations: the entire text.
    """
    # Find the last ADJOURNMENT marker
    idx = raw_text.rfind("ADJOURNMENT")
    if idx >= 0:
        # Take everything after the marker line
        after = raw_text[idx:]
        newline = after.find("\n")
        return after[newline + 1:] if newline >= 0 else ""
    return raw_text


def split_emails(text: str) -> list[str]:
    """Split text into individual email blocks at From: boundaries.

    Handles both Format A (multi-line From:\\n) and Format B (FROM:  NAME).
    """
    # Find all boundary positions
    boundaries: list[int] = []
    for m in _FROM_MULTILINE.finditer(text):
        boundaries.append(m.start())
    for m in _FROM_INLINE.finditer(text):
        boundaries.append(m.start())

    if not boundaries:
        return []

    boundaries.sort()

    # Split at boundaries
    blocks: list[str] = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)

    return blocks


def parse_email_block(block: str) -> dict[str, str] | None:
    """Parse a single email block into structured fields.

    Returns dict with: speaker_name, subject, body, date_sent, item_ref
    or None if the block can't be parsed.
    """
    lines = block.split("\n")
    if not lines:
        return None

    # Detect format
    first_line = lines[0].strip()
    is_format_b = first_line.startswith("FROM:")

    speaker_name = ""
    subject = ""
    date_sent = ""
    body_start = 0

    if is_format_b:
        # Format B: FROM:  NAME / DATE: ... / SUBJECT: ... / COMMENTS:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("FROM:"):
                speaker_name = stripped[5:].strip()
            elif stripped.startswith("DATE:"):
                date_sent = stripped[5:].strip()
            elif stripped.startswith("SUBJECT:"):
                subject = stripped[8:].strip()
            elif stripped.startswith("COMMENTS:"):
                body_start = i + 1
                break
            elif stripped == "" and i > 3:
                # Empty line after headers = body start
                body_start = i + 1
                break
        if body_start == 0:
            body_start = min(4, len(lines))
    else:
        # Format A: From:\nName\nTo:\n...\nSubject:\n...\nDate:\n...
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped == "From:" and i + 1 < len(lines):
                speaker_name = lines[i + 1].strip()
                i += 2
            elif stripped == "To:" or stripped.startswith("To:"):
                # Skip To: and the next line(s) of recipients
                i += 1
                while i < len(lines) and lines[i].strip() and not _is_header_label(lines[i]):
                    i += 1
            elif stripped == "Subject:" and i + 1 < len(lines):
                subject = lines[i + 1].strip()
                i += 2
            elif stripped.startswith("Subject:"):
                subject = stripped[8:].strip()
                i += 1
            elif stripped == "Date:" and i + 1 < len(lines):
                date_sent = lines[i + 1].strip()
                i += 2
            elif stripped.startswith("Date:"):
                date_sent = stripped[5:].strip()
                i += 1
            elif stripped.startswith(BOILERPLATE):
                # Skip boilerplate (may be doubled)
                i += 1
                continue
            elif stripped == "":
                # Empty line after headers
                if speaker_name:  # Only if we've found at least a name
                    body_start = i + 1
                    break
                i += 1
            else:
                # First non-header, non-empty line = body
                if speaker_name:
                    body_start = i
                    break
                i += 1

        if body_start == 0:
            body_start = min(8, len(lines))

    if not speaker_name:
        return None

    # Extract body, strip boilerplate
    body_lines = lines[body_start:]
    body = _strip_boilerplate("\n".join(body_lines))

    if not body.strip():
        return None

    # Extract item reference from subject
    item_ref = extract_item_reference(subject)

    return {
        "speaker_name": _clean_name(speaker_name),
        "subject": subject,
        "body": body.strip(),
        "date_sent": date_sent,
        "item_ref": item_ref,
    }


def _is_header_label(line: str) -> bool:
    """Check if a line is a standard email header label."""
    s = line.strip()
    return s in ("From:", "To:", "Subject:", "Date:", "Cc:", "Bcc:") or \
        any(s.startswith(h) for h in ("From:", "Subject:", "Date:", "Cc:"))


def _clean_name(name: str) -> str:
    """Clean up a speaker name: strip email addresses, extra whitespace."""
    # Remove email addresses in angle brackets
    name = re.sub(r"<[^>]+>", "", name).strip()
    # Remove trailing semicolons, commas
    name = name.rstrip(";,").strip()
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)
    return name


def _strip_boilerplate(text: str) -> str:
    """Remove known boilerplate from email body text."""
    # Remove the "This email originated..." warning (may appear 1-2 times)
    text = text.replace(BOILERPLATE + " Do not open links or attachments from untrusted\nsources.", "")
    text = text.replace(BOILERPLATE + " Do not open links or attachments from untrusted sources.", "")
    text = text.replace(BOILERPLATE, "")
    # Remove "Attachments:" sections at the end
    text = re.sub(r"\nAttachments:.*$", "", text, flags=re.DOTALL)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_item_reference(subject: str) -> str | None:
    """Extract an agenda item number from an email subject line.

    Returns the item reference string (e.g., 'P2', 'O-1', 'V.7.a')
    or None if the subject refers to open forum / general public comment.
    """
    if not subject:
        return None

    # Try specific patterns first (most reliable)
    for pattern in _ITEM_PATTERNS[:3]:
        m = pattern.search(subject)
        if m:
            return m.group(1)

    # Check for open forum keywords — but only if no bare item number follows
    subject_lower = subject.lower()
    bare_match = _ITEM_PATTERNS[3].search(subject)

    for kw in _OPEN_FORUM_KEYWORDS:
        if kw in subject_lower:
            # "Public Comment O.2" should still match O.2
            if bare_match:
                candidate = bare_match.group(1)
                # Filter out false positives like date fragments
                if len(candidate) <= 6 and not candidate.isdigit():
                    return candidate
            return None

    # Bare pattern fallback
    if bare_match:
        candidate = bare_match.group(1)
        if len(candidate) <= 6 and not candidate.isdigit():
            return candidate

    return None


def parse_email_comments(raw_text: str) -> list[dict[str, str]]:
    """Parse all written comments from a document's raw text.

    Handles both standalone compilations and minutes-with-appendix
    by finding the comment boundary first.
    """
    comment_text = find_comment_boundary(raw_text)
    blocks = split_emails(comment_text)
    results = []
    for block in blocks:
        parsed = parse_email_block(block)
        if parsed:
            results.append(parsed)
    return results


# ── eSCRIBE eComment Parsing ────────────��───────────────────────────────────


def parse_ecomments_from_json(meeting_data: dict) -> list[dict[str, Any]]:
    """Extract eComments from an eSCRIBE meeting_data.json.

    Looks for 'ecomments' key on each item (added by scraper's
    fetch_ecomments). Returns flat list with item_number attached.
    """
    results = []
    for item in meeting_data.get("items", []):
        item_number = item.get("item_number", "")
        for ec in item.get("ecomments", []):
            results.append({
                "speaker_name": ec.get("name", "").strip(),
                "body": ec.get("text", "").strip(),
                "item_number": item_number,
                "position": ec.get("position", ""),
            })
    return results


# ── DB Helpers ──────���───────────────────────────────────────────────────────


def _get_agenda_item_ids(conn, meeting_id: str) -> dict[str, str]:
    """Get mapping of item_number -> agenda_item UUID for a meeting."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT item_number, id FROM agenda_items WHERE meeting_id = %s",
            (meeting_id,),
        )
        return {r[0]: str(r[1]) for r in cur.fetchall()}


def _find_meeting_by_date(
    conn, meeting_date: str, city_fips: str = RICHMOND_FIPS
) -> str | None:
    """Find a meeting ID by date. Returns UUID string or None."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM meetings
               WHERE city_fips = %s AND meeting_date = %s AND meeting_type = 'regular'
               LIMIT 1""",
            (city_fips, meeting_date),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None


def _parse_metadata_date(metadata: dict) -> str | None:
    """Parse meeting date from document metadata to YYYY-MM-DD format."""
    raw = (metadata or {}).get("date", "")
    if not raw:
        return None

    # Try various formats the archive center uses
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _find_comment_documents(
    conn, city_fips: str = RICHMOND_FIPS, meeting_date: str | None = None
) -> list[dict[str, Any]]:
    """Find all AMID=31 documents that may contain written comments.

    Returns both standalone compilations AND minutes with appended comments.
    The parser's ADJOURNMENT-split handles the distinction.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.id, d.metadata, d.raw_text
               FROM documents d
               WHERE d.city_fips = %s
                 AND d.source_type = 'archive_center'
                 AND (d.metadata->>'amid')::int = %s
                 AND d.raw_text IS NOT NULL
                 AND d.raw_text != ''
               ORDER BY d.metadata->>'date' DESC""",
            (city_fips, MINUTES_AMID),
        )
        docs = cur.fetchall()

    results = []
    for doc_id, metadata, raw_text in docs:
        parsed_date = _parse_metadata_date(metadata)
        if meeting_date and parsed_date != meeting_date:
            continue

        # Try parsing — skip docs with zero extractable emails
        emails = parse_email_comments(raw_text)
        if emails:
            results.append({
                "doc_id": str(doc_id),
                "metadata": metadata,
                "meeting_date": parsed_date,
                "adid": (metadata or {}).get("adid", "?"),
                "title": (metadata or {}).get("title", "unknown"),
                "email_count": len(emails),
                "emails": emails,
            })

    return results


def _already_has_written_comments(conn, meeting_id: str) -> int:
    """Count existing written comments from archive_center for a meeting."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FROM public_comments
               WHERE meeting_id = %s AND comment_type = 'written'
                 AND source = %s""",
            (meeting_id, SOURCE_ARCHIVE),
        )
        return cur.fetchone()[0]


# ── Import to DB ─────────────────────��──────────────────────────────────────


def import_written_comments(
    meeting_id: str,
    emails: list[dict[str, str]],
    source: str = SOURCE_ARCHIVE,
    city_fips: str = RICHMOND_FIPS,
    dry_run: bool = False,
) -> dict[str, int]:
    """Import parsed email comments into public_comments table."""
    conn = get_connection()
    item_id_map = _get_agenda_item_ids(conn, meeting_id)
    now = datetime.now(timezone.utc)

    stats = {"inserted": 0, "open_forum": 0, "skipped_no_item": 0, "skipped_duplicate": 0}

    for email in emails:
        item_ref = email.get("item_ref") or email.get("item_number")
        agenda_item_id = None

        if item_ref:
            agenda_item_id = resolve_item_id(item_ref, item_id_map)
            if not agenda_item_id:
                stats["skipped_no_item"] += 1
                # Still insert — just without an item link
        if not item_ref:
            stats["open_forum"] += 1

        method = "ecomment" if source == SOURCE_ESCRIBEMEETINGS else "email"

        if dry_run:
            stats["inserted"] += 1
            continue

        with conn.cursor() as cur:
            try:
                cur.execute(
                    """INSERT INTO public_comments
                       (meeting_id, agenda_item_id, speaker_name, method, summary,
                        comment_type, source, confidence, name_confidence,
                        extracted_at, city_fips)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (meeting_id, COALESCE(agenda_item_id::text, ''),
                                    COALESCE(speaker_name, ''), COALESCE(summary, ''))
                       DO NOTHING""",
                    (
                        meeting_id,
                        agenda_item_id,
                        email["speaker_name"],
                        method,
                        email["body"],
                        "written",
                        source,
                        0.9,
                        "high",
                        now,
                        city_fips,
                    ),
                )
                if cur.rowcount > 0:
                    stats["inserted"] += 1
                else:
                    stats["skipped_duplicate"] += 1
            except Exception as e:
                print(f"    ERROR inserting {email['speaker_name']}: {e}")
                conn.rollback()
                continue

    if not dry_run:
        conn.commit()
    conn.close()
    return stats


# ── CLI Commands ────────────��───────────────────────��───────────────────────


def cmd_extract(
    meeting_date: str | None = None,
    *,
    dry_run: bool = False,
    limit: int = 0,
    force: bool = False,
    city_fips: str = RICHMOND_FIPS,
) -> None:
    """Extract written comments from Archive Center documents."""
    print("Finding documents with written comments...")
    conn = get_connection()

    docs = _find_comment_documents(conn, city_fips, meeting_date)
    if not docs:
        print("  No documents with extractable written comments found.")
        conn.close()
        return

    if limit:
        docs = docs[:limit]

    total_emails = sum(d["email_count"] for d in docs)
    print(f"  Found {len(docs)} documents with {total_emails} total emails")
    if dry_run:
        print("  [DRY RUN]")

    processed = 0
    total_inserted = 0
    for doc in docs:
        meeting_id = _find_meeting_by_date(conn, doc["meeting_date"], city_fips)
        if not meeting_id:
            print(f"  SKIP ADID {doc['adid']}: no meeting for date {doc['meeting_date']}")
            continue

        if not force:
            existing = _already_has_written_comments(conn, meeting_id)
            if existing > 0:
                print(f"  SKIP {doc['meeting_date']}: already has {existing} written comments (use --force)")
                continue

        print(f"  {doc['meeting_date']} (ADID {doc['adid']}): {doc['email_count']} emails")

        stats = import_written_comments(
            meeting_id, doc["emails"], SOURCE_ARCHIVE, city_fips, dry_run
        )

        print(
            f"    Imported: {stats['inserted']}, "
            f"open forum: {stats['open_forum']}, "
            f"unmatched items: {stats['skipped_no_item']}, "
            f"duplicates: {stats['skipped_duplicate']}"
        )
        total_inserted += stats["inserted"]
        processed += 1

    conn.close()

    # Also process eSCRIBE eComments if available
    if not meeting_date or ESCRIBEMEETINGS_DIR.exists():
        _process_ecomments(meeting_date, dry_run=dry_run, city_fips=city_fips)

    print(f"\nDone. Processed {processed} documents, {total_inserted} comments imported.")


def _process_ecomments(
    meeting_date: str | None = None,
    *,
    dry_run: bool = False,
    city_fips: str = RICHMOND_FIPS,
) -> None:
    """Process eSCRIBE eComments from saved meeting_data.json files."""
    if not ESCRIBEMEETINGS_DIR.exists():
        return

    conn = get_connection()
    total = 0

    for meeting_dir in sorted(ESCRIBEMEETINGS_DIR.iterdir()):
        json_path = meeting_dir / "meeting_data.json"
        if not json_path.exists():
            continue

        data = json.loads(json_path.read_text(encoding="utf-8"))
        date_str = data.get("meeting_date", "")

        if meeting_date and date_str != meeting_date:
            continue

        ecomments = parse_ecomments_from_json(data)
        if not ecomments:
            continue

        meeting_id = _find_meeting_by_date(conn, date_str, city_fips)
        if not meeting_id:
            continue

        # Convert to the same format as email comments
        emails = [
            {
                "speaker_name": ec["speaker_name"],
                "body": ec["body"],
                "item_ref": ec.get("item_number"),
            }
            for ec in ecomments
            if ec["speaker_name"] and ec["body"]
        ]

        if emails:
            stats = import_written_comments(
                meeting_id, emails, SOURCE_ESCRIBEMEETINGS, city_fips, dry_run
            )
            if stats["inserted"] > 0:
                print(f"  eComments {date_str}: {stats['inserted']} imported")
                total += stats["inserted"]

    conn.close()
    if total:
        print(f"  Total eComments imported: {total}")


def cmd_status(city_fips: str = RICHMOND_FIPS) -> None:
    """Show written comment extraction coverage."""
    conn = get_connection()
    with conn.cursor() as cur:
        # Count by source
        cur.execute(
            """SELECT source, method, COUNT(*)
               FROM public_comments
               WHERE city_fips = %s AND comment_type = 'written'
               GROUP BY source, method
               ORDER BY source, method""",
            (city_fips,),
        )
        rows = cur.fetchall()

        # Meetings with written comments
        cur.execute(
            """SELECT m.meeting_date, COUNT(pc.id)
               FROM public_comments pc
               JOIN meetings m ON m.id = pc.meeting_id
               WHERE pc.city_fips = %s AND pc.comment_type = 'written'
               GROUP BY m.meeting_date
               ORDER BY m.meeting_date DESC""",
            (city_fips,),
        )
        meetings = cur.fetchall()

        # Available documents
        cur.execute(
            """SELECT COUNT(*)
               FROM documents d
               WHERE d.city_fips = %s
                 AND d.source_type = 'archive_center'
                 AND (d.metadata->>'amid')::int = %s
                 AND d.raw_text IS NOT NULL AND d.raw_text != ''""",
            (city_fips, MINUTES_AMID),
        )
        total_docs = cur.fetchone()[0]

    conn.close()

    print("Written Comment Coverage")
    print("=" * 40)

    if rows:
        print("\nBy source:")
        for source, method, count in rows:
            print(f"  {source}/{method}: {count}")
    else:
        print("\nNo written comments extracted yet.")

    print(f"\nMeetings with written comments: {len(meetings)}")
    for date, count in meetings[:10]:
        print(f"  {date}: {count} comments")
    if len(meetings) > 10:
        print(f"  ... and {len(meetings) - 10} more")

    print(f"\nAMID=31 documents available: {total_docs}")


# ── Main ────────────��───────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract written public comments from Archive Center PDFs"
    )
    sub = parser.add_subparsers(dest="command")

    extract_p = sub.add_parser("extract", help="Extract written comments")
    extract_p.add_argument("--meeting-date", help="Process single meeting date (YYYY-MM-DD)")
    extract_p.add_argument("--dry-run", action="store_true", help="Preview without DB writes")
    extract_p.add_argument("--limit", type=int, default=0, help="Max documents to process")
    extract_p.add_argument("--force", action="store_true", help="Re-extract already-processed meetings")

    sub.add_parser("status", help="Show extraction coverage")

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(
            args.meeting_date,
            dry_run=args.dry_run,
            limit=args.limit,
            force=args.force,
        )
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
