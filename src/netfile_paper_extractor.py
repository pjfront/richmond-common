"""
NetFile paper-filing PDF extractor.

Reads paper-filed campaign finance PDFs (FPPC forms 460 and 497) downloaded
from the NetFile public portal, extracts contribution rows via PyMuPDF +
Claude tool_use, and writes JSON in the schema consumed by
src/load_paper_filings.py and the sync_netfile paper-filing loop in
src/data_sync.py.

Reads from: NetFile public portal PDFs at /public/image/{filing_id} (raw).
Does NOT read from: any derivative summary or pre-extracted text — every
filing is re-parsed from the source PDF on demand.

Why: paper filers (e.g., Anderson for Mayor 2026) don't appear in the
NetFile Connect2 transaction API. Without this extractor, their
contributions reach Richmond Commons only via hand-curated JSON, which
goes stale between filing periods (Q1 2026: Anderson page understated
by ~$14k as of 2026-04-27).

Usage:
  python netfile_paper_extractor.py                   # all paper filers
  python netfile_paper_extractor.py --committee "Anderson for Mayor 2026"
  python netfile_paper_extractor.py --filing-id 215523926 --committee "..."
  python netfile_paper_extractor.py --dry-run         # extract but don't write JSON
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import fitz  # PyMuPDF
from anthropic import Anthropic

from netfile_client import (
    download_paper_filing,
    extract_filers,
    fetch_all_transactions,
    fetch_filing_rss,
    identify_paper_filers,
)

PAPER_FILINGS_DIR = Path(__file__).parent / "data" / "paper_filings"
PDF_CACHE_DIR = PAPER_FILINGS_DIR / "_pdf_cache"
DEFAULT_FIPS = "0660620"
MODEL = "claude-sonnet-4-5"

# Forms that carry contribution rows. Form 410 = Statement of Organization
# (no contributions). Form 460 Schedule A = itemized monetary contributions.
# Form 497 = late-contribution report (Part 1 = received by this committee,
# Part 2 = contribution made to another committee — only relevant when a
# different committee's 497 names this candidate as recipient).
EXTRACTABLE_FORMS = {"460", "497", "497_received"}

CONTRIBUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "contributions": {
            "type": "array",
            "description": "All itemized monetary contributions in this filing. Skip non-monetary, loans, and refunds.",
            "items": {
                "type": "object",
                "properties": {
                    "contributor_name": {"type": "string"},
                    "amount": {"type": "number", "description": "Dollars (e.g., 250.00). Positive = contribution received."},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "city": {"type": "string"},
                    "state": {"type": "string", "description": "Two-letter US state abbreviation."},
                    "zip": {"type": "string"},
                    "entity_code": {
                        "type": "string",
                        "enum": ["IND", "COM", "OTH", "SCC", "PTY"],
                        "description": "IND=individual, COM=committee/PAC, OTH=business, SCC=small contributor committee, PTY=political party.",
                    },
                    "occupation": {"type": "string"},
                    "contributor_employer": {"type": "string"},
                },
                "required": ["contributor_name", "amount", "date"],
            },
        }
    },
    "required": ["contributions"],
}


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all text from a PDF using PyMuPDF. Strips NUL bytes."""
    doc = fitz.open(str(pdf_path))
    try:
        parts = [page.get_text() for page in doc]
    finally:
        doc.close()
    return "\n".join(parts).replace("\x00", "").strip()


def parse_filing_with_claude(
    pdf_text: str,
    form_type: str,
    filing_id: str,
    committee: str,
    client: Anthropic,
) -> list[dict]:
    """Parse a paper filing's text into structured contribution dicts.

    Uses Claude tool_use with temperature=0 for reproducible extraction.
    Returns [] if no contributions found (e.g., Form 410, or 497 Part 2
    naming a different recipient).
    """
    system = (
        "You extract itemized monetary contributions from California FPPC "
        "campaign finance forms. You are conservative and precise: only "
        "include rows you can see clearly in the input. Skip non-monetary "
        "contributions, loans, and refunds. If a column is blank, leave the "
        "corresponding field as an empty string. Dates must be YYYY-MM-DD. "
        "Amounts must be in dollars (e.g., 250.00 not 25000)."
    )
    user = (
        f"Filing ID: {filing_id}\n"
        f"Committee: {committee}\n"
        f"Form type: {form_type}\n\n"
        f"PDF TEXT:\n{pdf_text}"
    )

    tool_def = {
        "name": "save_contributions",
        "description": "Save the extracted itemized contribution rows.",
        "input_schema": CONTRIBUTION_SCHEMA,
    }

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        temperature=0,
        system=system,
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "save_contributions"},
        messages=[{"role": "user", "content": user}],
    )

    for block in response.content:
        if block.type == "tool_use":
            rows = block.input.get("contributions", [])
            for r in rows:
                r["filing_id"] = filing_id
                r.setdefault("entity_code", "IND")
                r.setdefault("city", "")
                r.setdefault("state", "")
                r.setdefault("zip", "")
                r.setdefault("occupation", "")
                r.setdefault("contributor_employer", "")
            return rows

    return []


def filing_already_extracted(json_data: dict, filing_id: str) -> bool:
    """Idempotency check: True if filing_id is already in the JSON's filings list."""
    for f in json_data.get("filings", []):
        if str(f.get("filing_id")) == str(filing_id):
            return True
    return False


def find_committee_json(committee: str) -> Path | None:
    """Locate the existing JSON for this committee, if any."""
    needle = committee.lower().strip()
    for p in PAPER_FILINGS_DIR.glob("*.json"):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if (data.get("committee", "").lower().strip()) == needle:
            return p
    return None


def slugify(name: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")
    while "__" in out:
        out = out.replace("__", "_")
    return out


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def classify_form(form_type_text: str) -> str:
    """Map an RSS form_type string ('Form 460 - Pre-Election Statement') to '460'/'497'/'410'/'other'."""
    s = (form_type_text or "").lower()
    if "460" in s:
        return "460"
    if "497" in s:
        return "497"
    if "410" in s:
        return "410"
    return "other"


def extract_committee(
    committee: str,
    filings: list[dict],
    client: Anthropic,
    dry_run: bool = False,
    only_filing_id: str | None = None,
) -> dict:
    """Extract all unprocessed filings for one committee.

    Returns the updated JSON dict (whether or not it was written to disk).
    """
    json_path = find_committee_json(committee)
    if json_path:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        json_path = PAPER_FILINGS_DIR / f"{slugify(committee)}.json"
        data = {
            "committee": committee,
            "fppc_id": "",
            "candidate_name": "",
            "office_sought": "",
            "city_fips": DEFAULT_FIPS,
            "source": "fppc_paper",
            "filings": [],
            "contributions": [],
        }

    new_filings = 0
    new_contribs = 0
    for filing in filings:
        filing_id = str(filing.get("filing_id", ""))
        if not filing_id:
            continue
        if only_filing_id and filing_id != only_filing_id:
            continue
        if filing_already_extracted(data, filing_id):
            continue

        form = classify_form(filing.get("form_type", ""))
        if form not in EXTRACTABLE_FORMS and form != "410":
            print(f"  [skip] {committee} filing {filing_id}: unknown form ({filing.get('form_type')!r})")
            continue

        print(f"  [download] {committee} filing {filing_id} (form {form})")
        try:
            pdf_path = download_paper_filing(filing_id, output_dir=PDF_CACHE_DIR)
        except Exception as exc:
            print(f"    download failed: {exc}")
            continue

        filing_entry = {"filing_id": filing_id, "form": form, "date": str(date.today())}

        if form == "410":
            data["filings"].append(filing_entry)
            new_filings += 1
            continue

        try:
            text = extract_text_from_pdf(pdf_path)
        except Exception as exc:
            print(f"    PDF text extraction failed: {exc}")
            continue
        if not text:
            print("    PDF appears empty after extraction (possibly Type3 image fonts)")
            data["filings"].append(filing_entry)
            new_filings += 1
            continue

        rows = parse_filing_with_claude(text, form, filing_id, committee, client)
        print(f"    extracted {len(rows)} contribution row(s)")

        data["filings"].append(filing_entry)
        data["contributions"].extend(rows)
        new_filings += 1
        new_contribs += len(rows)

    print(f"  [{committee}] +{new_filings} filing(s), +{new_contribs} contribution(s)")

    if not dry_run and (new_filings or new_contribs):
        write_json_atomic(json_path, data)
        print(f"  wrote {json_path}")

    return data


def discover_paper_filers(
    transactions: list[dict] | None = None,
) -> dict[str, list[dict]]:
    """Return {committee_name: [filing_dict, ...]} for every paper filer in the RSS feed.

    Builds the API committee list from the monetary-contributions transaction
    feed (type 0). Any committee that appears in the RSS filing feed but not
    in the API transaction feed is a paper filer whose contribution data is
    only available via downloaded PDFs.

    *transactions* lets a caller (e.g., sync_netfile) reuse a transaction set
    it already fetched, avoiding a duplicate ~18-minute API pull.
    """
    rss = fetch_filing_rss()
    if transactions is None:
        transactions = fetch_all_transactions(transaction_type=0)
    api_committees = extract_filers(transactions)
    filers = identify_paper_filers(rss, api_committees)
    return {f["committee"]: f["filings"] for f in filers}


def auto_extract_paper_filings(
    transactions: list[dict] | None = None,
    dry_run: bool = False,
) -> dict:
    """Refresh every paper filer's JSON from the latest PDFs.

    Designed to be called from sync_netfile. Soft-fail: missing API key,
    network errors, or per-committee parse failures are logged but never
    raise — paper filings are a best-effort enrichment, not a sync gate.

    Returns {committees_seen, committees_extracted, filings_added, contributions_added}.
    """
    summary = {
        "committees_seen": 0,
        "committees_extracted": 0,
        "filings_added": 0,
        "contributions_added": 0,
    }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  paper-extractor: ANTHROPIC_API_KEY not set — skipping PDF extraction")
        return summary

    try:
        by_committee = discover_paper_filers(transactions=transactions)
    except Exception as exc:
        print(f"  paper-extractor: discovery failed ({exc}) — continuing with cached JSONs")
        return summary

    summary["committees_seen"] = len(by_committee)
    if not by_committee:
        return summary

    client = Anthropic(api_key=api_key)
    for committee, filings in by_committee.items():
        try:
            before = _count_contribs(committee)
            extract_committee(committee, filings, client=client, dry_run=dry_run)
            after = _count_contribs(committee)
            added_contribs = max(0, after - before)
            if added_contribs:
                summary["committees_extracted"] += 1
                summary["contributions_added"] += added_contribs
        except Exception as exc:
            print(f"  paper-extractor: {committee} failed ({exc}) — continuing")

    return summary


def _count_contribs(committee: str) -> int:
    p = find_committee_json(committee)
    if not p:
        return 0
    try:
        with open(p, encoding="utf-8") as f:
            return len(json.load(f).get("contributions", []))
    except (json.JSONDecodeError, OSError):
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract paper-filed contributions from NetFile PDFs")
    parser.add_argument("--committee", help="Restrict to one committee name (exact match)")
    parser.add_argument("--filing-id", help="Restrict to a single filing ID (requires --committee)")
    parser.add_argument("--dry-run", action="store_true", help="Extract but do not write JSON output")
    args = parser.parse_args()

    if args.filing_id and not args.committee:
        parser.error("--filing-id requires --committee")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    client = Anthropic(api_key=api_key)

    print("Discovering paper filers from NetFile RSS...")
    by_committee = discover_paper_filers()
    print(f"Found {len(by_committee)} committees with paper filings")

    if args.committee:
        if args.committee not in by_committee:
            available = "\n  ".join(sorted(by_committee.keys()))
            print(f"Committee not found in RSS: {args.committee!r}\nAvailable:\n  {available}")
            sys.exit(1)
        targets: Iterable[str] = [args.committee]
    else:
        targets = sorted(by_committee.keys())

    for committee in targets:
        print(f"\n→ {committee}")
        extract_committee(
            committee,
            by_committee[committee],
            client=client,
            dry_run=args.dry_run,
            only_filing_id=args.filing_id,
        )


if __name__ == "__main__":
    main()
