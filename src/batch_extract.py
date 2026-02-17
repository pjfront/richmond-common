"""
Richmond Transparency Project — Batch Meeting Extraction

Processes downloaded meeting PDFs through Claude Sonnet for structured
extraction. Requires ANTHROPIC_API_KEY to be set in .env or environment.

Usage:
    # Extract all downloaded meetings that haven't been extracted yet
    python batch_extract.py

    # Extract specific meeting by ADID
    python batch_extract.py --adid 17205

    # Dry run — show what would be extracted
    python batch_extract.py --dry-run

    # Re-extract already-extracted meetings
    python batch_extract.py --force

    # Use tool_use mode for more reliable schema compliance
    python batch_extract.py --tool-use
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from pipeline import extract_text_from_document, extract_meeting_data, extract_with_tool_use, save_extracted_data


DATA_DIR = Path("./data")
RAW_DIR = DATA_DIR / "raw"
EXTRACTED_DIR = DATA_DIR / "extracted"
SAMPLE_DIR = Path("./sample_output")

for d in [RAW_DIR, EXTRACTED_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def get_pending_meetings(force: bool = False) -> list[dict]:
    """Find downloaded meetings that haven't been extracted yet."""
    # Load inventory if available
    inventory_path = DATA_DIR / "meeting_inventory.json"
    if inventory_path.exists():
        with open(inventory_path) as f:
            inventory = json.load(f)
    else:
        # Build inventory from raw files
        inventory = []
        for pdf in sorted(RAW_DIR.glob("adid_*.pdf")):
            adid = pdf.stem.replace("adid_", "")
            inventory.append({"adid": adid, "title": f"ADID {adid}", "status": "clean"})

    pending = []
    for meeting in inventory:
        adid = meeting["adid"]
        pdf_path = RAW_DIR / f"adid_{adid}.pdf"
        txt_path = RAW_DIR / f"adid_{adid}.txt"

        if not pdf_path.exists() and not txt_path.exists():
            continue  # No source file

        # Check if already extracted
        if not force:
            # Look for any JSON file that might be this meeting's extraction
            already_extracted = False
            for json_file in list(EXTRACTED_DIR.glob("*_council_meeting.json")) + list(SAMPLE_DIR.glob("*_council_meeting.json")):
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                    meta = data.get("_extraction_metadata", {})
                    source_url = meta.get("source_url", "")
                    if f"ADID={adid}" in source_url:
                        already_extracted = True
                        break
                except (json.JSONDecodeError, KeyError):
                    continue

            if already_extracted:
                continue

        meeting["pdf_path"] = str(pdf_path)
        meeting["txt_path"] = str(txt_path) if txt_path.exists() else None
        pending.append(meeting)

    return pending


def extract_single_meeting(adid: str, title: str, pdf_path: str, txt_path: str = None,
                           use_tool_use: bool = False) -> dict:
    """Extract structured data from a single meeting."""
    # Use pre-extracted text if available
    if txt_path and Path(txt_path).exists():
        text = Path(txt_path).read_text(encoding="utf-8")
        print(f"  Using cached text ({len(text):,} chars)")
    else:
        print(f"  Extracting text from PDF...")
        text = extract_text_from_document(Path(pdf_path))
        print(f"  Extracted {len(text):,} chars")

    print(f"  Sending to Claude for structured extraction...")
    start_time = time.time()

    if use_tool_use:
        data = extract_with_tool_use(text)
    else:
        data = extract_meeting_data(text)

    elapsed = time.time() - start_time
    print(f"  Extraction completed in {elapsed:.1f}s")

    meeting_date = data.get("meeting_date", "unknown")
    source_url = f"https://www.ci.richmond.ca.us/Archive.aspx?ADID={adid}"
    save_extracted_data(data, meeting_date, source_url=source_url)

    return data


def main():
    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — Batch Meeting Extraction"
    )
    parser.add_argument("--adid", help="Extract specific meeting by ADID")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be extracted")
    parser.add_argument("--force", action="store_true", help="Re-extract already-extracted meetings")
    parser.add_argument("--tool-use", action="store_true", help="Use tool_use mode for extraction")
    parser.add_argument("--limit", type=int, default=0, help="Max meetings to extract (0 = all)")

    args = parser.parse_args()

    # Check API key (not needed for dry-run)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    has_api_key = api_key and api_key != "sk-ant-..."
    if not has_api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set or still has placeholder value.")
        print("Set it in .env or environment before running extraction.")
        print()
        print("Tip: You can still preview what would be extracted with --dry-run")
        print("  python batch_extract.py --dry-run")
        sys.exit(1)

    if args.adid:
        # Single meeting extraction
        pdf_path = RAW_DIR / f"adid_{args.adid}.pdf"
        txt_path = RAW_DIR / f"adid_{args.adid}.txt"
        if not pdf_path.exists():
            print(f"ERROR: No PDF found for ADID {args.adid}")
            print(f"  Expected: {pdf_path}")
            sys.exit(1)

        print(f"Extracting ADID {args.adid}...")
        data = extract_single_meeting(
            args.adid, f"ADID {args.adid}", str(pdf_path),
            str(txt_path) if txt_path.exists() else None,
            use_tool_use=args.tool_use,
        )
        print(f"Done! Meeting date: {data.get('meeting_date', 'unknown')}")
        return

    # Batch extraction
    pending = get_pending_meetings(force=args.force)

    if args.limit > 0:
        pending = pending[:args.limit]

    if not pending:
        print("No meetings pending extraction.")
        print(f"  {len(list(EXTRACTED_DIR.glob('*.json')))} already extracted")
        print(f"  {len(list(RAW_DIR.glob('adid_*.pdf')))} PDFs downloaded")
        if not args.force:
            print("  Use --force to re-extract existing meetings")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Meetings to extract: {len(pending)}")
    print()

    # Estimate cost
    total_chars = 0
    for m in pending:
        txt = m.get("txt_path")
        if txt and Path(txt).exists():
            total_chars += Path(txt).stat().st_size
        else:
            total_chars += 40000  # rough estimate

    est_tokens = total_chars // 4  # ~4 chars per token
    est_cost = (est_tokens / 1000000) * 3.0 + (9000 * len(pending) / 1000000) * 15.0  # input + output
    print(f"Estimated cost: ~${est_cost:.2f} ({est_tokens:,} input tokens + ~{9000 * len(pending):,} output tokens)")
    print()

    if args.dry_run:
        for m in pending:
            print(f"  Would extract: ADID {m['adid']} — {m['title']}")
        return

    # Process each meeting
    successes = 0
    failures = 0
    for i, m in enumerate(pending, 1):
        print(f"[{i}/{len(pending)}] ADID {m['adid']}: {m['title']}")
        try:
            data = extract_single_meeting(
                m["adid"], m["title"], m["pdf_path"], m.get("txt_path"),
                use_tool_use=args.tool_use,
            )
            successes += 1
            print(f"  Meeting date: {data.get('meeting_date', 'unknown')}")
            print()

            # Brief pause between API calls to be nice
            if i < len(pending):
                time.sleep(2)

        except Exception as e:
            failures += 1
            print(f"  ERROR: {e}")
            print()
            continue

    print("=" * 60)
    print(f"Batch extraction complete: {successes} succeeded, {failures} failed")
    print(f"Estimated total cost: ~${est_cost:.2f}")


if __name__ == "__main__":
    main()
