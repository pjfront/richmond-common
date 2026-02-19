"""
Richmond Transparency Project - Extraction Pipeline
Orchestrates scraping, extraction, and storage of city council meeting data.

Usage:
    python pipeline.py --url <meeting_minutes_url>
    python pipeline.py --file <path_to_pdf_or_html>
    python pipeline.py --scrape-recent  # scrape last N meetings from archive
"""
from __future__ import annotations

import json
import os
import re
import argparse
from datetime import datetime
from pathlib import Path

# You'll need: pip install anthropic requests beautifulsoup4 pymupdf
import anthropic
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF — handles government PDFs better than pdfplumber

from extraction import SYSTEM_PROMPT, EXTRACTION_PROMPT, EXTRACTION_SCHEMA


# --- Configuration ---

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATA_DIR = Path("./data")
RAW_DIR = DATA_DIR / "raw"          # Original downloaded documents
EXTRACTED_DIR = DATA_DIR / "extracted"  # Structured JSON output
ARCHIVE_BASE_URL = "https://www.ci.richmond.ca.us/Archive.aspx"
# Richmond uses ADID parameter for direct PDF download, not ViewFile/Item
ARCHIVE_DOCUMENT_URL = "https://www.ci.richmond.ca.us/Archive.aspx"

for d in [RAW_DIR, EXTRACTED_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# --- Scraping ---

def discover_meeting_minutes_urls(archive_id: int = 31, limit: int = 20) -> list[dict]:
    """
    Scrape the Richmond Archive Center index page to find meeting minutes URLs.

    Archive IDs:
      30 = City Council Agendas
      31 = City Council Minutes

    Links use the pattern: Archive.aspx?ADID={id}
    Each ADID URL serves a raw PDF directly.
    """
    url = f"{ARCHIVE_BASE_URL}?AMID={archive_id}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    minutes = []
    links = soup.find_all("a", href=re.compile(r"ADID=\d+", re.IGNORECASE))

    for link in links[:limit]:
        adid_match = re.search(r"ADID=(\d+)", link["href"], re.IGNORECASE)
        if adid_match:
            adid = adid_match.group(1)
            title = link.get_text(strip=True)
            minutes.append({
                "title": title,
                "adid": adid,
                "url": f"{ARCHIVE_DOCUMENT_URL}?ADID={adid}"
            })

    return minutes


def download_document(url: str, adid: str) -> Path:
    """Download a meeting document (PDF) and save locally."""
    response = requests.get(url)
    content_type = response.headers.get("content-type", "")

    if "pdf" in content_type or response.content[:5] == b"%PDF-":
        ext = ".pdf"
    else:
        ext = ".html"

    filepath = RAW_DIR / f"adid_{adid}{ext}"
    filepath.write_bytes(response.content)
    print(f"  Downloaded: {filepath} ({len(response.content)} bytes)")
    return filepath


def extract_text_from_document(filepath: Path) -> str:
    """Extract text content from a PDF or HTML file.

    Uses PyMuPDF (fitz) for PDFs — handles government PDFs with
    TrueType fonts reliably. Warns if Type3 fonts detected (image-based,
    may need OCR).
    """
    if filepath.suffix == ".pdf":
        doc = fitz.open(str(filepath))
        text_parts = []
        for page in doc:
            # Check for Type3 fonts (image-based, often garbled)
            fonts = page.get_fonts()
            has_type3 = any(f[2] == "Type3" for f in fonts)
            if has_type3:
                print(f"  WARNING: Page {page.number + 1} uses Type3 fonts — text may be garbled")
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    else:
        # HTML
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        for script in soup(["script", "style"]):
            script.decompose()
        return soup.get_text(separator="\n", strip=True)


# --- Extraction via Claude API ---

def extract_meeting_data(minutes_text: str) -> dict:
    """
    Send meeting minutes text to Claude for structured extraction.
    Uses tool_use for guaranteed JSON schema compliance.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    # Option 1: Simple prompt-based extraction
    prompt = EXTRACTION_PROMPT.format(
        schema=json.dumps(EXTRACTION_SCHEMA, indent=2),
        minutes_text=minutes_text[:100000]  # Claude can handle ~100K tokens
    )
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",  # Good balance of speed/quality for extraction
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Parse the JSON response
    response_text = response.content[0].text
    
    # Strip markdown code fences if present
    response_text = re.sub(r"^```json\s*", "", response_text)
    response_text = re.sub(r"\s*```$", "", response_text)
    
    return json.loads(response_text)


def extract_with_tool_use(minutes_text: str) -> dict:
    """
    Alternative: Use Claude's tool_use feature for guaranteed schema compliance.
    This is more reliable for production use.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    tool_definition = {
        "name": "save_meeting_data",
        "description": "Save the extracted structured meeting data",
        "input_schema": EXTRACTION_SCHEMA
    }
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=[tool_definition],
        tool_choice={"type": "tool", "name": "save_meeting_data"},
        messages=[{
            "role": "user",
            "content": f"Extract all structured data from these Richmond, CA City Council meeting minutes:\n\n{minutes_text[:100000]}"
        }]
    )
    
    # tool_use response gives us the structured data directly
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    
    raise ValueError("No tool_use block in response")


# --- Storage ---

def save_extracted_data(data: dict, meeting_date: str, source_url: str = None):
    """Save extracted meeting data as JSON."""
    data["_extraction_metadata"] = {
        "extracted_at": datetime.now().isoformat(),
        "source_url": source_url,
        "extraction_model": "claude-sonnet-4-20250514",
        "project": "Richmond Transparency Project"
    }
    
    filepath = EXTRACTED_DIR / f"{meeting_date}_council_meeting.json"
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"  Saved: {filepath}")
    return filepath


# --- Analysis helpers ---

def find_split_votes(data: dict) -> list[dict]:
    """Identify all non-unanimous votes - these are the interesting ones."""
    split_votes = []
    
    # Check action items
    for item in data.get("action_items", []):
        for motion in item.get("motions", []):
            ayes = sum(1 for v in motion.get("votes", []) if v["vote"] == "aye")
            nays = sum(1 for v in motion.get("votes", []) if v["vote"] == "nay")
            if nays > 0:
                split_votes.append({
                    "item_number": item["item_number"],
                    "item_title": item["title"],
                    "motion_type": motion["motion_type"],
                    "vote_tally": motion["vote_tally"],
                    "result": motion["result"],
                    "ayes": [v["council_member"] for v in motion["votes"] if v["vote"] == "aye"],
                    "nays": [v["council_member"] for v in motion["votes"] if v["vote"] == "nay"],
                    "motion_text": motion["motion_text"][:200]
                })
    
    return split_votes


def build_member_vote_record(data: dict) -> dict:
    """Build a voting record for each council member from one meeting."""
    records = {}
    
    # Consent calendar - everyone voted the same
    consent = data.get("consent_calendar", {})
    for vote in consent.get("votes", []):
        name = vote["council_member"]
        if name not in records:
            records[name] = {"aye": 0, "nay": 0, "abstain": 0, "absent": 0, "votes": []}
        records[name]["aye"] += len(consent.get("items", []))
    
    # Action items - individual votes
    for item in data.get("action_items", []):
        for motion in item.get("motions", []):
            for vote in motion.get("votes", []):
                name = vote["council_member"]
                if name not in records:
                    records[name] = {"aye": 0, "nay": 0, "abstain": 0, "absent": 0, "votes": []}
                records[name][vote["vote"]] += 1
                records[name]["votes"].append({
                    "item": item["item_number"],
                    "title": item["title"][:100],
                    "vote": vote["vote"],
                    "result": motion["result"]
                })
    
    return records


# --- Main pipeline ---

def process_single_meeting(url: str = None, filepath: str = None):
    """Process a single meeting from URL or local file."""

    if url:
        adid_match = re.search(r"ADID=(\d+)", url, re.IGNORECASE)
        adid = adid_match.group(1) if adid_match else "unknown"
        print(f"Downloading meeting document (ADID {adid})...")
        doc_path = download_document(url, adid)
    elif filepath:
        doc_path = Path(filepath)
    else:
        raise ValueError("Provide either url or filepath")
    
    print("Extracting text...")
    text = extract_text_from_document(doc_path)
    print(f"  Extracted {len(text)} characters")
    
    print("Sending to Claude for structured extraction...")
    data = extract_meeting_data(text)
    
    meeting_date = data.get("meeting_date", "unknown")
    print(f"  Meeting date: {meeting_date}")
    
    save_extracted_data(data, meeting_date, source_url=url)
    
    # Quick analysis
    split = find_split_votes(data)
    if split:
        print(f"\n  Found {len(split)} split votes:")
        for sv in split:
            print(f"    {sv['item_number']}: {sv['vote_tally']} ({sv['result']}) - {sv['item_title'][:60]}")
    
    records = build_member_vote_record(data)
    print(f"\n  Member vote summary:")
    for name, rec in sorted(records.items()):
        total = rec['aye'] + rec['nay'] + rec['abstain']
        print(f"    {name}: {rec['aye']} aye, {rec['nay']} nay, {rec['abstain']} abstain (of {total} votes)")
    
    return data


def scrape_recent_meetings(n: int = 5):
    """Discover and process the N most recent meeting minutes."""
    print(f"Discovering recent meeting minutes...")
    minutes = discover_meeting_minutes_urls(archive_id=31, limit=n)
    print(f"  Found {len(minutes)} documents")
    
    for meeting in minutes:
        print(f"\nProcessing: {meeting['title']} (ADID {meeting['adid']})")
        try:
            process_single_meeting(url=meeting["url"])
        except Exception as e:
            print(f"  ERROR processing ADID {meeting['adid']}: {e}")
            continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Richmond Transparency Project - Meeting Extraction Pipeline")
    parser.add_argument("--url", help="URL of a meeting minutes document")
    parser.add_argument("--file", help="Path to a local meeting minutes file")
    parser.add_argument("--scrape-recent", type=int, metavar="N", help="Scrape and process N recent meetings")
    
    args = parser.parse_args()
    
    if args.url:
        process_single_meeting(url=args.url)
    elif args.file:
        process_single_meeting(filepath=args.file)
    elif args.scrape_recent:
        scrape_recent_meetings(args.scrape_recent)
    else:
        parser.print_help()
