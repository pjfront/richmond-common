"""
Richmond Transparency Project -- eSCRIBE Meeting Portal Scraper

Scrapes full agenda packets from Richmond's eSCRIBE portal including
staff reports, contracts, and all attachments for each agenda item.

The eSCRIBE portal (pub-richmond.escribemeetings.com) provides:
- Full agenda packets with individual PDF attachments per item
- Staff reports, contracts, RFPs, bid matrices, applications
- Much richer data than the summary agenda PDF from Archive Center

Discovery approach:
- POST to /MeetingsCalendarView.aspx/GetCalendarMeetings with date range
- Returns JSON with meeting GUIDs, names, dates
- Individual meeting pages parseable with requests + BeautifulSoup (no JS needed)

Usage:
    # List upcoming meetings
    python escribemeetings_scraper.py --list

    # Download full packet for a specific meeting by date
    python escribemeetings_scraper.py --date 2026-02-17

    # Download full packet by GUID
    python escribemeetings_scraper.py --guid 00711755-eda3-4813-a8e9-5f5bdc8b2f2f

    # Download all meetings in a date range
    python escribemeetings_scraper.py --from 2026-01-01 --to 2026-03-01

    # Dry run -- show what would be downloaded
    python escribemeetings_scraper.py --date 2026-02-17 --dry-run

    # Skip PDF downloads, just get the meeting structure
    python escribemeetings_scraper.py --date 2026-02-17 --no-attachments
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# ── Constants ────────────────────────────────────────────────────────────────

BASE_URL = "https://pub-richmond.escribemeetings.com"
CALENDAR_ENDPOINT = f"{BASE_URL}/MeetingsCalendarView.aspx/GetCalendarMeetings"
MEETING_PAGE_URL = f"{BASE_URL}/Meeting.aspx"
FILESTREAM_URL = f"{BASE_URL}/filestream.ashx"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Headers for AJAX API calls
AJAX_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Content-Type": "application/json; charset=utf-8",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# Headers for regular page fetches
PAGE_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# City FIPS code -- every record gets tagged
CITY_FIPS = "0660620"

# Output directories (relative to src/)
DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw" / "escribemeetings"
EXTRACTED_DIR = DATA_DIR / "extracted"


# ── Meeting Discovery ────────────────────────────────────────────────────────

def create_session() -> requests.Session:
    """Create a requests session with browser-like headers."""
    session = requests.Session()
    session.headers.update({"User-Agent": BROWSER_UA})
    # Hit the calendar page first to establish cookies
    session.get(f"{BASE_URL}/MeetingsCalendarView.aspx", headers=PAGE_HEADERS, timeout=30)
    return session


def discover_meetings(
    session: requests.Session,
    start_date: str = "2020-01-01",
    end_date: str = "2027-01-01",
) -> list[dict]:
    """
    Discover meetings from the eSCRIBE calendar API.

    Returns list of dicts with keys:
        ID, MeetingName, StartDate, EndDate, FormattedStart, Description, IsCancelled
    """
    payload = {
        "calendarStartDate": start_date,
        "calendarEndDate": end_date,
    }

    resp = session.post(
        CALENDAR_ENDPOINT,
        json=payload,
        headers=AJAX_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    meetings = data.get("d", [])

    # Filter out cancelled meetings and sort by date
    active = [m for m in meetings if not m.get("IsCancelled", False)]
    active.sort(key=lambda m: m.get("StartDate", ""))

    return active


def find_meeting_by_date(meetings: list[dict], target_date: str) -> dict | None:
    """
    Find a meeting matching a target date (YYYY-MM-DD).
    Prefers "City Council" type over "Special" meetings.
    """
    matches = []
    for m in meetings:
        # StartDate format: "YYYY/MM/DD HH:MM:SS"
        start = m.get("StartDate", "")
        meeting_date = start.split(" ")[0].replace("/", "-") if start else ""
        if meeting_date == target_date:
            matches.append(m)

    if not matches:
        return None

    # Prefer regular City Council meetings
    for m in matches:
        if m.get("MeetingName", "") == "City Council":
            return m

    return matches[0]


# ── Meeting Page Parsing ─────────────────────────────────────────────────────

def fetch_meeting_page(session: requests.Session, guid: str) -> str:
    """Fetch the full HTML of a meeting's agenda page."""
    url = f"{MEETING_PAGE_URL}?Id={guid}&Agenda=Agenda&lang=English"
    resp = session.get(url, headers=PAGE_HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.text


def parse_meeting_page(html: str) -> dict:
    """
    Parse eSCRIBE meeting HTML into structured data.

    Returns dict with:
        title: str
        items: list of agenda item dicts, each with:
            item_number: str
            title: str
            description: str
            attachments: list of {name, document_id, url}
    """
    soup = BeautifulSoup(html, "html.parser")

    # Get meeting title
    title_el = soup.select_one("h1, .MeetingTitle, #MeetingTitle")
    meeting_title = title_el.get_text(strip=True) if title_el else "Unknown Meeting"

    # Find all agenda item containers
    items = []
    containers = soup.select("[class*='AgendaItemContainer']")

    for container in containers:
        item = parse_agenda_item(container)
        if item:
            items.append(item)

    # If no containers found, try alternative selectors
    if not items:
        for el in soup.select("[id*='AgendaItem'], .agenda-item, .meetingItem"):
            item = parse_agenda_item(el)
            if item:
                items.append(item)

    # ── Deduplicate attachments across parent/child items ────────────────
    # eSCRIBE nests containers, so parent items (V) include all child (V.1)
    # attachments. Assign each doc_id to only the deepest/most-specific item.
    doc_id_to_deepest_item = {}
    for item in items:
        num = item.get("item_number", "")
        for att in item.get("attachments", []):
            doc_id = att["document_id"]
            existing = doc_id_to_deepest_item.get(doc_id)
            if existing is None:
                doc_id_to_deepest_item[doc_id] = num
            else:
                # Deeper item = longer item_number (V.1.a > V.1 > V)
                if len(num) > len(existing):
                    doc_id_to_deepest_item[doc_id] = num

    # Now filter: each item keeps only attachments assigned to it
    for item in items:
        num = item.get("item_number", "")
        item["attachments"] = [
            att for att in item.get("attachments", [])
            if doc_id_to_deepest_item.get(att["document_id"]) == num
        ]

    unique_attachments = sum(len(it.get("attachments", [])) for it in items)

    return {
        "title": meeting_title,
        "items": items,
        "total_items": len(items),
        "total_attachments": unique_attachments,
    }


def parse_agenda_item(container) -> dict | None:
    """Parse a single agenda item container element.

    eSCRIBE HTML structure:
        .AgendaItemContainer
            .AgendaItemTitleRow
                .AgendaItemCounter          -> "V.1"
                .AgendaItemTitle a          -> "City Attorney's Office"
            .AgendaItemDescription.RichText -> formal description
            .RichText                       -> item body text (may be multiple)
            .AgendaItemAttachment a         -> filestream.ashx?DocumentId=XXXXX
    """
    # ── Item number from .AgendaItemCounter ──────────────────────────────
    counter_el = container.select_one(".AgendaItemCounter")
    item_number = ""
    if counter_el:
        raw = counter_el.get_text(strip=True)
        # Strip trailing period: "V.1" from "V.1.", "A." -> "A"
        item_number = raw.rstrip(".")

    # ── Title from .AgendaItemTitle link (cleanest text) ─────────────────
    title_link = container.select_one(".AgendaItemTitle a")
    title_el = container.select_one(".AgendaItemTitle")

    if title_link:
        title_text = title_link.get_text(strip=True)
    elif title_el:
        title_text = title_el.get_text(strip=True)
    else:
        # Fallback: try any h2/h3 inside the container
        header = container.select_one("h2, h3")
        title_text = header.get_text(strip=True) if header else ""

    if not title_text and not item_number:
        return None

    # Clean up: if counter text leaked into title, strip it
    if item_number and title_text.startswith(item_number):
        title_text = title_text[len(item_number):].strip().lstrip(".")

    # ── Description from .AgendaItemDescription ──────────────────────────
    desc_el = container.select_one(".AgendaItemDescription")
    description = ""
    if desc_el:
        description = desc_el.get_text(separator="\n", strip=True)

    # ── Body text from .RichText divs (staff report summaries) ───────────
    # Multiple .RichText blocks may exist — collect all text
    body_parts = []
    for rt in container.select(".RichText"):
        # Skip if it's the same as the description element
        if desc_el and rt == desc_el:
            continue
        text = rt.get_text(separator="\n", strip=True)
        if text and text != description:
            body_parts.append(text)

    body_text = "\n\n".join(body_parts) if body_parts else ""

    # Combine description + body for full text
    if body_text and description:
        full_description = f"{description}\n\n{body_text}"
    elif body_text:
        full_description = body_text
    else:
        full_description = description

    # ── Attachments from filestream.ashx links ───────────────────────────
    attachments = []
    seen_doc_ids = set()

    for link in container.select("a[href*='filestream.ashx']"):
        href = link.get("href", "")
        doc_id_match = re.search(r'DocumentId=(\d+)', href)
        if not doc_id_match:
            continue

        doc_id = doc_id_match.group(1)
        if doc_id in seen_doc_ids:
            continue  # Dedup (mobile + desktop views have duplicates)
        seen_doc_ids.add(doc_id)

        name = link.get_text(strip=True) or "Unnamed"
        attachments.append({
            "name": name,
            "document_id": doc_id,
            "url": f"{FILESTREAM_URL}?DocumentId={doc_id}",
        })

    return {
        "item_number": item_number,
        "title": title_text,
        "description": full_description,
        "attachments": attachments,
    }


# ── Attachment Download ──────────────────────────────────────────────────────

def download_attachment(
    session: requests.Session,
    doc_id: str,
    output_dir: Path,
    filename_prefix: str = "",
) -> Path | None:
    """
    Download a single attachment PDF by DocumentId.

    Returns the path to the downloaded file, or None if download failed.
    """
    url = f"{FILESTREAM_URL}?DocumentId={doc_id}"

    try:
        resp = session.get(url, headers=PAGE_HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    WARNING: Failed to download DocumentId={doc_id}: {e}")
        return None

    # Determine file extension from content type
    content_type = resp.headers.get("Content-Type", "")
    if "pdf" in content_type:
        ext = ".pdf"
    elif "word" in content_type or "docx" in content_type:
        ext = ".docx"
    elif "excel" in content_type or "xlsx" in content_type:
        ext = ".xlsx"
    else:
        ext = ".pdf"  # default to PDF

    # Build filename
    safe_prefix = re.sub(r'[^\w\-]', '_', filename_prefix)[:80] if filename_prefix else ""
    if safe_prefix:
        filename = f"{safe_prefix}_doc{doc_id}{ext}"
    else:
        filename = f"doc{doc_id}{ext}"

    output_path = output_dir / filename
    output_path.write_bytes(resp.content)

    return output_path


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF using PyMuPDF."""
    if fitz is None:
        return "[PyMuPDF not installed -- cannot extract text]"

    try:
        doc = fitz.open(str(pdf_path))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    except Exception as e:
        return f"[Error extracting text: {e}]"


# ── Full Pipeline ────────────────────────────────────────────────────────────

def scrape_meeting(
    session: requests.Session,
    meeting: dict,
    output_dir: Path | None = None,
    download_attachments: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Full pipeline: fetch meeting page, parse items, download attachments.

    Args:
        session: requests session with cookies
        meeting: dict from discover_meetings() with at least 'ID' key
        output_dir: directory for downloaded files (auto-created)
        download_attachments: if False, just parse structure without downloading PDFs
        dry_run: if True, don't download anything

    Returns:
        dict with full meeting structure including parsed items and attachment paths
    """
    guid = meeting["ID"]
    meeting_name = meeting.get("MeetingName", "Unknown")
    start_date = meeting.get("StartDate", "")

    # Parse date for directory naming
    date_str = start_date.split(" ")[0].replace("/", "-") if start_date else "unknown"

    print(f"Fetching meeting page: {meeting_name} ({date_str})")
    print(f"  GUID: {guid}")

    if dry_run:
        print("  [DRY RUN] Would fetch and parse meeting page")
        return {"guid": guid, "date": date_str, "name": meeting_name, "dry_run": True}

    # Set up output directory
    if output_dir is None:
        safe_name = re.sub(r'[^\w\-]', '_', f"{date_str}_{meeting_name}")
        output_dir = RAW_DIR / safe_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fetch and parse meeting page
    html = fetch_meeting_page(session, guid)

    # Save raw HTML for debugging/re-parsing
    html_path = output_dir / "meeting_page.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"  Saved HTML ({len(html):,} bytes)")

    parsed = parse_meeting_page(html)
    print(f"  Found {parsed['total_items']} agenda items with {parsed['total_attachments']} attachments")

    # Download attachments
    attachment_count = 0
    text_count = 0

    if download_attachments and parsed["total_attachments"] > 0:
        print(f"  Downloading attachments...")
        attachments_dir = output_dir / "attachments"
        attachments_dir.mkdir(exist_ok=True)

        for item in parsed["items"]:
            item_num = item.get("item_number", "misc")
            for att in item.get("attachments", []):
                doc_id = att["document_id"]
                prefix = f"{item_num}_{att['name'][:60]}"

                file_path = download_attachment(session, doc_id, attachments_dir, prefix)
                if file_path:
                    att["local_path"] = str(file_path)
                    att["file_size"] = file_path.stat().st_size
                    attachment_count += 1

                    # Extract text from PDFs
                    if file_path.suffix == ".pdf":
                        text = extract_text_from_pdf(file_path)
                        if text and not text.startswith("["):
                            txt_path = file_path.with_suffix(".txt")
                            txt_path.write_text(text, encoding="utf-8")
                            att["text_path"] = str(txt_path)
                            att["text_length"] = len(text)
                            text_count += 1

                    # Brief pause between downloads
                    time.sleep(0.3)

        print(f"  Downloaded {attachment_count} attachments, extracted text from {text_count}")

    # Build result
    result = {
        "city_fips": CITY_FIPS,
        "source": "escribemeetings",
        "guid": guid,
        "meeting_name": meeting_name,
        "meeting_date": date_str,
        "start_date": start_date,
        "portal_url": f"{MEETING_PAGE_URL}?Id={guid}&Agenda=Agenda&lang=English",
        "scraped_at": datetime.now().isoformat(),
        "items": parsed["items"],
        "stats": {
            "total_items": parsed["total_items"],
            "total_attachments": parsed["total_attachments"],
            "downloaded_attachments": attachment_count,
            "text_extracted": text_count,
        },
    }

    # Save structured result
    result_path = output_dir / "meeting_data.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Saved meeting data to {result_path}")

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project -- eSCRIBE Meeting Scraper"
    )
    parser.add_argument("--list", action="store_true",
                        help="List all available meetings")
    parser.add_argument("--date",
                        help="Download meeting by date (YYYY-MM-DD)")
    parser.add_argument("--guid",
                        help="Download meeting by GUID")
    parser.add_argument("--from", dest="from_date",
                        help="Start of date range (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date",
                        help="End of date range (YYYY-MM-DD)")
    parser.add_argument("--upcoming", action="store_true",
                        help="Show upcoming meetings (next 60 days)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be downloaded without downloading")
    parser.add_argument("--no-attachments", action="store_true",
                        help="Parse meeting structure without downloading PDFs")
    parser.add_argument("--output-dir",
                        help="Custom output directory")
    parser.add_argument("--meeting-type", default="City Council",
                        help="Filter by meeting type (default: 'City Council')")

    args = parser.parse_args()

    print("Richmond eSCRIBE Meeting Scraper")
    print("=" * 50)

    # Create session
    print("Establishing session...")
    session = create_session()

    # Determine date range for discovery
    if args.from_date:
        start = args.from_date
    else:
        start = "2020-01-01"

    if args.to_date:
        end = args.to_date
    elif args.upcoming:
        end = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        start = datetime.now().strftime("%Y-%m-%d")
    else:
        end = "2027-01-01"

    # Discover meetings
    print(f"Discovering meetings ({start} to {end})...")
    all_meetings = discover_meetings(session, start, end)
    print(f"Found {len(all_meetings)} meetings")

    # Filter by type if specified
    if args.meeting_type:
        filtered = [m for m in all_meetings if args.meeting_type in m.get("MeetingName", "")]
        print(f"  {len(filtered)} match type '{args.meeting_type}'")
    else:
        filtered = all_meetings

    # ── List mode ────────────────────────────────────────────────────────
    if args.list or args.upcoming:
        print()
        for m in filtered:
            start_dt = m.get("StartDate", "")
            date_str = start_dt.split(" ")[0].replace("/", "-") if start_dt else "?"
            name = m.get("MeetingName", "?")
            guid = m.get("ID", "?")
            cancelled = " [CANCELLED]" if m.get("IsCancelled") else ""
            print(f"  {date_str}  {name:<35}  {guid}{cancelled}")
        print(f"\nTotal: {len(filtered)} meetings")
        return

    # ── Single meeting by date ───────────────────────────────────────────
    if args.date:
        meeting = find_meeting_by_date(all_meetings, args.date)
        if not meeting:
            print(f"\nERROR: No meeting found for date {args.date}")
            # Show nearby meetings
            print("Available meetings around that date:")
            for m in all_meetings:
                start_dt = m.get("StartDate", "")
                d = start_dt.split(" ")[0].replace("/", "-") if start_dt else ""
                if d and abs((datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(args.date, "%Y-%m-%d")).days) <= 30:
                    print(f"  {d}  {m.get('MeetingName', '?')}")
            sys.exit(1)

        output_dir = Path(args.output_dir) if args.output_dir else None
        result = scrape_meeting(
            session, meeting,
            output_dir=output_dir,
            download_attachments=not args.no_attachments,
            dry_run=args.dry_run,
        )

        print(f"\nDone! Meeting: {result.get('meeting_name')} ({result.get('meeting_date')})")
        stats = result.get("stats", {})
        if stats:
            print(f"  Items: {stats.get('total_items', 0)}")
            print(f"  Attachments: {stats.get('downloaded_attachments', 0)}/{stats.get('total_attachments', 0)}")
            print(f"  Text extracted: {stats.get('text_extracted', 0)}")
        return

    # ── Single meeting by GUID ───────────────────────────────────────────
    if args.guid:
        # Build a minimal meeting dict
        meeting = {"ID": args.guid, "MeetingName": "Unknown", "StartDate": ""}
        # Try to find it in discovered meetings
        for m in all_meetings:
            if m.get("ID") == args.guid:
                meeting = m
                break

        output_dir = Path(args.output_dir) if args.output_dir else None
        result = scrape_meeting(
            session, meeting,
            output_dir=output_dir,
            download_attachments=not args.no_attachments,
            dry_run=args.dry_run,
        )

        print(f"\nDone!")
        return

    # ── Date range mode ──────────────────────────────────────────────────
    if args.from_date or args.to_date:
        meetings_to_scrape = filtered
        print(f"\nWill scrape {len(meetings_to_scrape)} meetings")

        if args.dry_run:
            for m in meetings_to_scrape:
                start_dt = m.get("StartDate", "")
                d = start_dt.split(" ")[0].replace("/", "-") if start_dt else "?"
                print(f"  [DRY RUN] Would scrape: {d} - {m.get('MeetingName', '?')}")
            return

        for i, meeting in enumerate(meetings_to_scrape, 1):
            print(f"\n[{i}/{len(meetings_to_scrape)}]")
            try:
                scrape_meeting(
                    session, meeting,
                    download_attachments=not args.no_attachments,
                    dry_run=args.dry_run,
                )
            except Exception as e:
                print(f"  ERROR: {e}")
                continue

            # Pause between meetings
            if i < len(meetings_to_scrape):
                time.sleep(2)

        print(f"\nBatch complete: scraped {len(meetings_to_scrape)} meetings")
        return

    # No action specified -- show help
    parser.print_help()
    print("\nExamples:")
    print("  python escribemeetings_scraper.py --list")
    print("  python escribemeetings_scraper.py --upcoming")
    print("  python escribemeetings_scraper.py --date 2026-02-17")
    print("  python escribemeetings_scraper.py --from 2026-01-01 --to 2026-03-01")


if __name__ == "__main__":
    main()
