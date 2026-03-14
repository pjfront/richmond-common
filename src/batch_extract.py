"""
Richmond Common — Batch Meeting Extraction

Downloads meeting PDFs from Richmond Archive Center and processes them
through Claude Sonnet for structured extraction.
Requires ANTHROPIC_API_KEY to be set in .env or environment for extraction.

Usage:
    # Download all meeting PDFs from inventory (no API key needed)
    python batch_extract.py --download

    # Extract all downloaded meetings that haven't been extracted yet
    python batch_extract.py

    # Download + extract in one shot
    python batch_extract.py --download

    # Extract specific meeting by ADID
    python batch_extract.py --adid 17205

    # Dry run — show what would be extracted
    python batch_extract.py --dry-run

    # Re-extract already-extracted meetings
    python batch_extract.py --force

    # Use tool_use mode for more reliable schema compliance
    python batch_extract.py --tool-use

    # Limit number of meetings to extract
    python batch_extract.py --limit 5

    # Skip public comment compilations (not actual minutes)
    python batch_extract.py --skip-comments

    # Download documents from all Tier 1+2 Archive Center AMIDs
    python batch_extract.py --archive-download

    # Download only Tier 1 archive documents
    python batch_extract.py --archive-download --archive-tiers 1
"""
from __future__ import annotations

import json
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

import requests

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from city_config import get_data_source_config

DEFAULT_FIPS = "0660620"

from pipeline import (
    extract_text_from_document,
    extract_meeting_data,
    extract_with_tool_use,
    save_extracted_data,
    download_document,
    discover_meeting_minutes_urls,
)


DATA_DIR = Path("./data")
RAW_DIR = DATA_DIR / "raw"
EXTRACTED_DIR = DATA_DIR / "extracted"
SAMPLE_DIR = Path("./sample_output")

for d in [RAW_DIR, EXTRACTED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ADIDs confirmed as standalone public comment compilations (not actual minutes).
# Identified by checking file content — compilations start with citizen comments,
# actual minutes start with roll call. Title patterns are unreliable:
#   "(public comments received)" can be EITHER minutes or compilations
#   "(with public comments received)" = actual minutes (Dec 2025)
#   "(public comments attached)" = actual minutes (always)
# When in doubt, check the first 500 chars for "ROLL CALL" or "called to order".
KNOWN_COMMENT_COMPILATION_ADIDS = {"17313", "17289", "17274", "17234"}


def is_comment_compilation(title: str, adid: str = "") -> bool:
    """Check if a meeting entry is a public comment compilation, not actual minutes."""
    return adid in KNOWN_COMMENT_COMPILATION_ADIDS


def download_missing_pdfs(inventory: list[dict]) -> int:
    """Download PDFs for all inventory entries that don't have local files."""
    downloaded = 0
    for meeting in inventory:
        adid = meeting["adid"]
        pdf_path = RAW_DIR / f"adid_{adid}.pdf"
        txt_path = RAW_DIR / f"adid_{adid}.txt"

        if pdf_path.exists() or txt_path.exists():
            continue

        url = f"https://www.ci.richmond.ca.us/Archive.aspx?ADID={adid}"
        print(f"  Downloading ADID {adid}: {meeting.get('title', 'unknown')}...")
        try:
            download_document(url, adid)
            downloaded += 1
            # Be polite to the server
            time.sleep(1)
        except Exception as e:
            print(f"    ERROR downloading ADID {adid}: {e}")

    return downloaded


def cache_text_from_pdf(adid: str) -> str | None:
    """Extract text from PDF and cache as .txt file. Returns text or None."""
    pdf_path = RAW_DIR / f"adid_{adid}.pdf"
    txt_path = RAW_DIR / f"adid_{adid}.txt"

    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8")

    if not pdf_path.exists():
        return None

    text = extract_text_from_document(pdf_path)
    txt_path.write_text(text, encoding="utf-8")
    return text


def load_inventory() -> list[dict]:
    """Load meeting inventory, or build from raw files."""
    inventory_path = DATA_DIR / "meeting_inventory.json"
    if inventory_path.exists():
        with open(inventory_path) as f:
            return json.load(f)

    # Build inventory from raw files
    inventory = []
    for pdf in sorted(RAW_DIR.glob("adid_*.pdf")):
        adid = pdf.stem.replace("adid_", "")
        inventory.append({"adid": adid, "title": f"ADID {adid}", "status": "clean"})
    return inventory


def get_pending_meetings(force: bool = False, skip_comments: bool = False) -> list[dict]:
    """Find meetings that need extraction (have source files, not yet extracted)."""
    inventory = load_inventory()
    pending = []

    for meeting in inventory:
        adid = meeting["adid"]
        title = meeting.get("title", "")

        # Skip public comment compilations if requested
        if skip_comments and is_comment_compilation(title, adid):
            continue

        pdf_path = RAW_DIR / f"adid_{adid}.pdf"
        txt_path = RAW_DIR / f"adid_{adid}.txt"

        if not pdf_path.exists() and not txt_path.exists():
            continue  # No source file

        # Check if already extracted
        if not force:
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
    # Use pre-extracted text if available, otherwise extract and cache
    if txt_path and Path(txt_path).exists():
        text = Path(txt_path).read_text(encoding="utf-8")
        print(f"  Using cached text ({len(text):,} chars)")
    else:
        print(f"  Extracting text from PDF...")
        text = extract_text_from_document(Path(pdf_path))
        # Cache extracted text for future runs
        cached_path = RAW_DIR / f"adid_{adid}.txt"
        cached_path.write_text(text, encoding="utf-8")
        print(f"  Extracted {len(text):,} chars (cached to {cached_path.name})")

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


def download_archive_amids(fips: str = DEFAULT_FIPS, tiers: list[str] | None = None) -> int:
    """Download documents from configured Tier 1+2 Archive Center AMIDs.

    Uses city_config.py to discover which AMIDs to download from,
    then uses discover_meeting_minutes_urls to find document URLs
    within each AMID, and downloads any documents not already on disk.

    Args:
        fips: City FIPS code. Defaults to Richmond (0660620).
        tiers: Which tiers to download. List of "1", "2", or ["all"].
               Defaults to ["all"].

    Returns:
        Total number of documents downloaded across all AMIDs.
    """
    if tiers is None:
        tiers = ["all"]

    config = get_data_source_config(fips, "archive_center")
    base_url = config["base_url"]
    document_path = config["document_path"]

    # Collect AMIDs based on requested tiers
    amids: list[tuple[int, str]] = []  # (amid, tier_label)
    if "all" in tiers or "1" in tiers:
        for amid in config.get("tier_1_amids", []):
            amids.append((amid, "Tier 1"))
    if "all" in tiers or "2" in tiers:
        for amid in config.get("tier_2_amids", []):
            amids.append((amid, "Tier 2"))

    if not amids:
        print("No AMIDs found for the requested tiers.")
        return 0

    print(f"Archive download: {len(amids)} AMIDs across tiers {tiers}")
    total_downloaded = 0

    for amid, tier_label in amids:
        archive_dir = DATA_DIR / "archive" / f"amid_{amid}"
        archive_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n  [{tier_label}] AMID {amid}: discovering documents...")
        try:
            documents = discover_meeting_minutes_urls(archive_id=amid, limit=1000)
        except Exception as e:
            print(f"    ERROR discovering AMID {amid}: {e}")
            continue

        print(f"    Found {len(documents)} documents")
        downloaded = 0
        skipped = 0

        for doc in documents:
            adid = doc["adid"]
            output_path = archive_dir / f"adid_{adid}.pdf"

            if output_path.exists():
                skipped += 1
                continue

            doc_url = base_url + document_path.format(adid=adid)
            try:
                response = requests.get(doc_url, timeout=30)
                response.raise_for_status()
                output_path.write_bytes(response.content)
                downloaded += 1
                # Be polite to the server
                time.sleep(1)
            except Exception as e:
                print(f"    ERROR downloading ADID {adid}: {e}")

        total_downloaded += downloaded
        print(f"    Downloaded {downloaded}, skipped {skipped} (already on disk)")

    return total_downloaded


def main():
    parser = argparse.ArgumentParser(
        description="Richmond Common — Batch Meeting Extraction"
    )
    parser.add_argument("--adid", help="Extract specific meeting by ADID")
    parser.add_argument("--download", action="store_true",
                        help="Download missing PDFs before extraction")
    parser.add_argument("--download-only", action="store_true",
                        help="Only download PDFs, don't extract")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be extracted")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract already-extracted meetings")
    parser.add_argument("--tool-use", action="store_true",
                        help="Use tool_use mode for extraction")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max meetings to extract (0 = all)")
    parser.add_argument("--skip-comments", action="store_true",
                        help="Skip public comment compilations (not actual minutes)")
    parser.add_argument("--cache-text", action="store_true",
                        help="Extract text from all PDFs and cache as .txt (no API needed)")
    parser.add_argument("--archive-download", action="store_true",
                        help="Download documents from all Tier 1+2 Archive Center AMIDs")
    parser.add_argument("--archive-tiers", nargs="+", default=["all"],
                        help="Which tiers to download: 1, 2, or all (default: all)")

    args = parser.parse_args()

    inventory = load_inventory()
    print(f"Meeting inventory: {len(inventory)} entries")

    # Download missing PDFs if requested
    if args.download or args.download_only:
        print(f"\nDownloading missing PDFs...")
        downloaded = download_missing_pdfs(inventory)
        print(f"Downloaded {downloaded} new PDFs")
        if args.download_only:
            return

    # Cache text from PDFs (no API key needed)
    if args.cache_text:
        print(f"\nCaching text from PDFs...")
        cached = 0
        for meeting in inventory:
            adid = meeting["adid"]
            txt_path = RAW_DIR / f"adid_{adid}.txt"
            pdf_path = RAW_DIR / f"adid_{adid}.pdf"
            if txt_path.exists() or not pdf_path.exists():
                continue
            print(f"  Extracting text from ADID {adid}: {meeting.get('title', '')}")
            text = cache_text_from_pdf(adid)
            if text:
                print(f"    {len(text):,} chars")
                cached += 1
        print(f"Cached text for {cached} meetings")
        return

    # Download from configured Archive Center AMIDs (no API key needed)
    if args.archive_download:
        print(f"\nDownloading Archive Center documents (tiers: {args.archive_tiers})...")
        total = download_archive_amids(tiers=args.archive_tiers)
        print(f"\nTotal downloaded: {total} documents")
        return

    # Check API key (not needed for dry-run)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    has_api_key = api_key and api_key != "sk-ant-..."
    if not has_api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set or still has placeholder value.")
        print("Set it in .env or environment before running extraction.")
        print()
        print("Tip: You can still preview what would be extracted with --dry-run")
        print("  python batch_extract.py --dry-run")
        print()
        print("Or download PDFs and cache text without an API key:")
        print("  python batch_extract.py --download-only")
        print("  python batch_extract.py --cache-text")
        sys.exit(1)

    if args.adid:
        # Single meeting extraction
        pdf_path = RAW_DIR / f"adid_{args.adid}.pdf"
        txt_path = RAW_DIR / f"adid_{args.adid}.txt"

        # Try to download if missing
        if not pdf_path.exists() and not txt_path.exists():
            if args.download:
                url = f"https://www.ci.richmond.ca.us/Archive.aspx?ADID={args.adid}"
                print(f"Downloading ADID {args.adid}...")
                download_document(url, args.adid)
            else:
                print(f"ERROR: No PDF found for ADID {args.adid}")
                print(f"  Expected: {pdf_path}")
                print(f"  Use --download to fetch it from the Archive Center")
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
    pending = get_pending_meetings(force=args.force, skip_comments=args.skip_comments)

    if args.limit > 0:
        pending = pending[:args.limit]

    if not pending:
        print("\nNo meetings pending extraction.")
        extracted_count = len(list(EXTRACTED_DIR.glob("*.json")))
        pdf_count = len(list(RAW_DIR.glob("adid_*.pdf")))
        txt_count = len(list(RAW_DIR.glob("adid_*.txt")))
        print(f"  {extracted_count} already extracted")
        print(f"  {pdf_count} PDFs + {txt_count} text files downloaded")
        if not args.force:
            print("  Use --force to re-extract existing meetings")
        return

    # Separate actual minutes from comment compilations for display
    actual_minutes = [m for m in pending if not is_comment_compilation(m.get("title", ""), m.get("adid", ""))]
    comments = [m for m in pending if is_comment_compilation(m.get("title", ""), m.get("adid", ""))]

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Meetings to extract: {len(pending)}")
    if comments:
        print(f"  ({len(actual_minutes)} actual minutes + {len(comments)} public comment compilations)")
        if not args.skip_comments:
            print(f"  Tip: Use --skip-comments to skip comment compilations")
    print()

    # Estimate cost
    total_chars = 0
    for m in pending:
        txt = m.get("txt_path")
        if txt and Path(txt).exists():
            total_chars += Path(txt).stat().st_size
        else:
            total_chars += m.get("chars", 40000)  # use inventory chars if available

    est_tokens = total_chars // 4  # ~4 chars per token
    est_cost = (est_tokens / 1000000) * 3.0 + (9000 * len(pending) / 1000000) * 15.0
    print(f"Estimated cost: ~${est_cost:.2f} ({est_tokens:,} input tokens + ~{9000 * len(pending):,} output tokens)")
    print()

    if args.dry_run:
        for m in pending:
            marker = " [COMMENTS]" if is_comment_compilation(m.get("title", ""), m.get("adid", "")) else ""
            has_source = "txt" if m.get("txt_path") else ("pdf" if Path(m.get("pdf_path", "")).exists() else "MISSING")
            print(f"  [{has_source}] ADID {m['adid']}: {m['title']}{marker}")
        return

    # Process each meeting
    successes = 0
    failures = 0
    total_cost = 0.0

    for i, m in enumerate(pending, 1):
        print(f"[{i}/{len(pending)}] ADID {m['adid']}: {m['title']}")
        try:
            data = extract_single_meeting(
                m["adid"], m["title"], m["pdf_path"], m.get("txt_path"),
                use_tool_use=args.tool_use,
            )
            successes += 1
            meeting_date = data.get("meeting_date", "unknown")
            n_consent = len(data.get("consent_calendar", {}).get("items", []))
            n_action = len(data.get("action_items", []))
            print(f"  -> {meeting_date}: {n_consent} consent + {n_action} action items")
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
