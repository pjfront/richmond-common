"""
Richmond Transparency Project — End-to-End Pipeline Automation

Single command to run the complete pre-meeting analysis pipeline:
  1. Scrape eSCRIBE for full agenda packet (items + attachments)
  2. Convert eSCRIBE data to scanner-compatible JSON format
  3. Enrich with staff report text from attachments
  4. Scan for conflicts against campaign contributions
  5. Generate formatted public comment
  6. (Optional) Load extracted data into Supabase database

Usage:
  python run_pipeline.py --date 2026-03-03
  python run_pipeline.py --date 2026-03-03 --send
  python run_pipeline.py --date 2026-03-03 --load-db
  python run_pipeline.py --date 2026-03-03 --contributions path/to/contribs.json
  python run_pipeline.py --date 2026-03-03 --skip-escribemeetings --meeting-json path/to/meeting.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from escribemeetings_scraper import (
    create_session,
    discover_meetings,
    find_meeting_by_date,
    scrape_meeting,
)
from conflict_scanner import scan_meeting_json
from comment_generator import (
    generate_comment_from_scan,
    detect_missing_documents,
)
from escribemeetings_enricher import enrich_meeting_data


# ── Default Paths ────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_CONTRIBUTIONS = DATA_DIR / "combined_contributions.json"
DEFAULT_FORM700 = DATA_DIR / ".." / "src" / "test_data" / "sample_form700.json"


# ── eSCRIBE → Scanner Format Conversion

from text_utils import extract_financial_amount  # noqa: E402, F401

def categorize_item(title: str, description: str) -> str:
    """Assign a category based on title/description keywords."""
    combined = f"{title} {description}".lower()

    categories = [
        ("procedural", ["roll call", "pledge of allegiance", "pledge to the flag",
                        "approval of minutes", "approve minutes", "approval of the agenda",
                        "approve the agenda", "agenda reorder", "adjournment", "adjourned",
                        "recess", "open forum", "statement of conflict",
                        "agenda review", "adjourn to closed", "open session",
                        "city council minutes", "meeting minutes",
                        "public comment before"]),
        ("housing", ["housing", "affordable", "homeless", "tenant", "rent", "homekey"]),
        ("zoning", ["zoning", "rezoning", "land use", "ceqa", "environmental", "planning commission"]),
        ("budget", ["budget", "appropriation", "fiscal", "revenue", "expenditure", "financial plan"]),
        ("public_safety", ["police", "fire department", "public safety", "emergency", "crime"]),
        ("environment", ["environmental", "climate", "pollution", "clean energy", "sustainability"]),
        ("infrastructure", ["infrastructure", "road", "sewer", "water system", "construction", "paving"]),
        ("personnel", ["appointment", "personnel", "hiring", "employee", "commissioner", "board member"]),
        ("contracts", ["contract", "agreement", "vendor", "consultant", "services agreement", "amendment"]),
        ("governance", ["closed session", "minutes", "ordinance", "resolution", "proclamation", "council rules"]),
    ]

    for category, keywords in categories:
        for keyword in keywords:
            if keyword in combined:
                return category

    return "other"


def convert_escribemeetings_to_scanner_format(escribemeetings_data: dict) -> dict:
    """Convert eSCRIBE meeting_data.json to conflict scanner schema.

    The scanner expects:
      consent_calendar.items[], action_items[], housing_authority_items[]
    Each item has: item_number, title, description, category, financial_amount

    eSCRIBE data has:
      items[] with item_number, title, description, attachments[]

    Routing rules:
      - V.* items → consent_calendar
      - M.* items → housing_authority_items
      - Everything else → action_items
    """
    meeting_name = escribemeetings_data.get("meeting_name", "")
    meeting_type = "special" if "special" in meeting_name.lower() else "regular"

    consent_items = []
    action_items = []
    housing_items = []

    for item in escribemeetings_data.get("items", []):
        item_num = item.get("item_number", "")
        title = item.get("title", "")
        description = item.get("description", "")

        # Skip top-level section headers (no dot = section header like V, M, C)
        # These are parent containers ("CITY COUNCIL CONSENT CALENDAR",
        # "CLOSED SESSION") that have no actionable content of their own.
        # Sub-items (V.1.a, V.5.b) carry the real agenda item data.
        # Matches the skip logic in escribemeetings_to_agenda.py:127.
        if "." not in item_num:
            continue

        converted = {
            "item_number": item_num,
            "title": title,
            "description": description,
            "category": categorize_item(title, description),
            "financial_amount": extract_financial_amount(description),
        }

        # Route by item number prefix
        # Check longer prefixes first to avoid "V" matching "VI", "VII", etc.
        if item_num.startswith("M"):
            housing_items.append(converted)
        elif item_num.startswith(("VI", "VII", "VIII", "IX", "X")):
            action_items.append(converted)
        elif item_num.startswith("V"):
            consent_items.append(converted)
        elif item_num in ("A", "B", "C", "D", "I", "II", "III", "IV"):
            # Procedural items (call to order, roll call, etc.) → action
            action_items.append(converted)
        else:
            action_items.append(converted)

    return {
        "meeting_date": escribemeetings_data.get("meeting_date", ""),
        "meeting_type": meeting_type,
        "city_fips": escribemeetings_data.get("city_fips", "0660620"),
        "members_present": [],
        "members_absent": [],
        "conflict_of_interest_declared": [],
        "closed_session_items": [],
        "consent_calendar": {"items": consent_items},
        "action_items": action_items,
        "housing_authority_items": housing_items,
    }


# ── Pipeline Orchestration ───────────────────────────────────

def run_pipeline(
    date: str,
    contributions_path: str | None = None,
    form700_path: str | None = None,
    dry_run: bool = True,
    skip_escribemeetings: bool = False,
    meeting_json_path: str | None = None,
    output_path: str | None = None,
    load_db: bool = False,
) -> str:
    """Run the full pre-meeting analysis pipeline.

    Args:
        date: Meeting date in YYYY-MM-DD format
        contributions_path: Path to contributions JSON (default: combined_contributions.json)
        form700_path: Path to Form 700 JSON (optional)
        dry_run: If True, print comment instead of emailing
        skip_escribemeetings: If True, skip eSCRIBE scraping (use meeting_json_path instead)
        meeting_json_path: Path to pre-existing meeting JSON (use with skip_escribemeetings)
        output_path: Path to save generated comment text
        load_db: If True, load extracted meeting data into the database

    Returns:
        The generated comment text
    """
    print(f"\n{'='*60}")
    print(f"Richmond Transparency Project — Pipeline")
    print(f"Meeting date: {date}")
    print(f"{'='*60}\n")

    # Step 1: Get meeting data
    if skip_escribemeetings and meeting_json_path:
        print(f"Step 1: Loading pre-existing meeting JSON from {meeting_json_path}")
        with open(meeting_json_path) as f:
            meeting_data = json.load(f)
        escribemeetings_data = None
    else:
        print("Step 1: Scraping eSCRIBE for meeting agenda packet...")
        session = create_session()
        meetings = discover_meetings(session)
        meeting = find_meeting_by_date(meetings, date)

        if not meeting:
            print(f"ERROR: No meeting found for {date}")
            print("Use --date YYYY-MM-DD with a valid council meeting date.")
            sys.exit(1)

        escribemeetings_result = scrape_meeting(session, meeting)

        # Save raw eSCRIBE data
        output_dir = DATA_DIR / "raw" / "escribemeetings" / f"{date}_pipeline"
        output_dir.mkdir(parents=True, exist_ok=True)
        escribemeetings_json = output_dir / "meeting_data.json"
        with open(escribemeetings_json, "w") as f:
            json.dump(escribemeetings_result, f, indent=2)
        print(f"  Saved eSCRIBE data to {escribemeetings_json}")

        # Convert to scanner format
        print("Step 2: Converting eSCRIBE data to scanner format...")
        meeting_data = convert_escribemeetings_to_scanner_format(escribemeetings_result)
        escribemeetings_data = escribemeetings_result

        # Save converted JSON
        converted_json = DATA_DIR / "extracted" / f"{date}_pipeline.json"
        converted_json.parent.mkdir(parents=True, exist_ok=True)
        with open(converted_json, "w") as f:
            json.dump(meeting_data, f, indent=2)
        print(f"  Saved scanner-format JSON to {converted_json}")

        consent_count = len(meeting_data["consent_calendar"]["items"])
        action_count = len(meeting_data["action_items"])
        housing_count = len(meeting_data["housing_authority_items"])
        print(f"  Items: {consent_count} consent, {action_count} action, {housing_count} housing")

    # Step 3: Enrich with eSCRIBE attachment text
    enriched_items = []
    if escribemeetings_data:
        print("Step 3: Enriching with staff report text...")
        # Create temp file for enricher (it reads from disk)
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(escribemeetings_data, tmp, indent=2)
            tmp_path = tmp.name
        meeting_data, enriched_items = enrich_meeting_data(meeting_data, tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
        print(f"  Enriched {len(enriched_items)} items with attachment text")
    else:
        print("Step 3: Skipped (no eSCRIBE data)")

    # Step 4: Load contributions and scan
    print("Step 4: Scanning for conflicts...")
    contributions = []
    contrib_path = contributions_path or str(DEFAULT_CONTRIBUTIONS)
    if Path(contrib_path).exists():
        with open(contrib_path) as f:
            contributions = json.load(f)
        print(f"  Loaded {len(contributions):,} contributions from {contrib_path}")
    else:
        print(f"  WARNING: No contributions file found at {contrib_path}")

    form700 = []
    if form700_path and Path(form700_path).exists():
        with open(form700_path) as f:
            form700 = json.load(f)
        print(f"  Loaded {len(form700)} Form 700 interests")

    scan_result = scan_meeting_json(meeting_data, contributions, form700)
    scan_result.enriched_items = enriched_items
    print(f"  Found {len(scan_result.flags)} flags, {len(scan_result.clean_items)} clean items")

    # Save audit sidecar
    audit_dir = DATA_DIR / "audit_runs"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"{scan_result.scan_run_id}.json"
    scan_result.audit_log.save(audit_path)
    print(f"  Audit sidecar saved to {audit_path}")

    # Step 5: Generate comment
    print("Step 5: Generating public comment...")
    missing_docs = detect_missing_documents(meeting_data)
    contribution_count = f"{len(contributions):,}" if contributions else "0"
    comment = generate_comment_from_scan(scan_result, missing_docs, contribution_count)

    # Output
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(comment)
        print(f"  Saved comment to {output_path}")

    if dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN — Comment text:")
        print(f"{'='*60}\n")
        print(comment)
    else:
        from comment_generator import submit_comment_to_clerk
        submit_comment_to_clerk(comment, date, dry_run=False)

    # Step 6: Load to database (optional)
    if load_db:
        print("Step 6: Loading meeting data into database...")
        try:
            from db import get_connection, load_meeting_to_db
            conn = get_connection()
            try:
                load_meeting_to_db(conn, meeting_data)
                conn.commit()
                print("  Meeting data loaded successfully")
            finally:
                conn.close()
        except Exception as e:
            print(f"  WARNING: Database loading failed: {e}")
            print("  Pipeline results are still saved to disk. You can load manually later.")
    else:
        print("Step 6: Skipped database loading (use --load-db to enable)")

    print(f"\n{'='*60}")
    print(f"Pipeline complete for {date}")
    tier1 = sum(1 for f in scan_result.flags if f.publication_tier == 1)
    tier2 = sum(1 for f in scan_result.flags if f.publication_tier == 2)
    tier3 = sum(1 for f in scan_result.flags if f.publication_tier == 3)
    print(f"  Tier 1 (Potential Conflicts): {tier1}")
    print(f"  Tier 2 (Financial Connections): {tier2}")
    print(f"  Tier 3 (Internal Only): {tier3}")
    print(f"  Clean items: {len(scan_result.clean_items)}")
    print(f"{'='*60}")

    return comment


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — End-to-End Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py --date 2026-03-03
  python run_pipeline.py --date 2026-03-03 --output comment.txt
  python run_pipeline.py --date 2026-03-03 --contributions data/combined_contributions.json
  python run_pipeline.py --date 2026-03-03 --skip-escribemeetings --meeting-json data/extracted/2026-03-03_agenda.json
        """,
    )
    parser.add_argument("--date", required=True, help="Meeting date (YYYY-MM-DD)")
    parser.add_argument("--contributions", help="Path to contributions JSON")
    parser.add_argument("--form700", help="Path to Form 700 interests JSON")
    parser.add_argument("--send", action="store_true", help="Actually email the comment (default: dry run)")
    parser.add_argument("--output", help="Save comment to file")
    parser.add_argument(
        "--skip-escribemeetings",
        action="store_true",
        help="Skip eSCRIBE scraping, use --meeting-json instead",
    )
    parser.add_argument("--meeting-json", help="Pre-existing meeting JSON (with --skip-escribemeetings)")
    parser.add_argument("--load-db", action="store_true", help="Load extracted data into the database")
    args = parser.parse_args()

    run_pipeline(
        date=args.date,
        contributions_path=args.contributions,
        form700_path=args.form700,
        dry_run=not args.send,
        skip_escribemeetings=args.skip_escribemeetings,
        meeting_json_path=args.meeting_json,
        output_path=args.output,
        load_db=args.load_db,
    )


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
