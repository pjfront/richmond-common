"""
CAL-ACCESS campaign finance data client for Richmond, California.

Downloads the statewide bulk data from the Secretary of State,
searches for Richmond-related committees and contributions.

IMPORTANT FINDING: Individual Richmond city council candidate committees
file locally with the City Clerk, NOT with CAL-ACCESS at the state level.
CAL-ACCESS contains:
  - PACs and independent expenditure committees active in Richmond elections
  - Statewide candidates from Richmond (e.g., Beckles for Assembly/Senate)
  - Major donor committees (Chevron, SEIU, Police Officers Association)
  - Ballot measure committees

For direct council candidate contributions, see the City Clerk's
e-filing system (future data source).

Data source: https://www.sos.ca.gov/campaign-lobbying/cal-access-resources/raw-data-campaign-finance-and-lobbying-activity
Bulk download: https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip

Key tables:
  FILERNAME_CD                 — Committee/filer registration (name, city, status)
  FILER_FILINGS_CD             — Maps FILER_ID -> FILING_ID
  CVR_CAMPAIGN_DISCLOSURE_CD   — Campaign disclosure cover pages (also links FILER_ID -> FILING_ID)
  RCPT_CD                      — Itemized contributions (linked by FILING_ID, NOT FILER_ID)
  EXPN_CD                      — Itemized expenditures
  S497_CD                      — Late contribution reports

Note: The bulk ZIP is ~1.5GB. We download once, read directly from ZIP,
and cache extracted results as JSON.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

import requests

BULK_DATA_URL = "https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip"
DATA_DIR = Path(__file__).parent.parent / "data" / "calaccess"
CITY_FIPS = "0660620"

# Richmond-area keywords for filtering (module-level defaults)
RICHMOND_KEYWORDS = [
    "richmond",
    "contra costa",
    "west contra costa",
]


# ── City-config resolution ───────────────────────────────────

def _resolve_calaccess_config(
    city_fips: str | None = None,
) -> tuple[list[str], str]:
    """Resolve CAL-ACCESS settings from city config registry or defaults.

    Returns (search_keywords, resolved_fips).
    """
    if city_fips is not None:
        from city_config import get_data_source_config

        cfg = get_data_source_config(city_fips, "calaccess")
        keywords = cfg.get("search_keywords") or []
        return keywords, city_fips
    return RICHMOND_KEYWORDS, CITY_FIPS


def download_bulk_data(force: bool = False) -> Path:
    """
    Download the CAL-ACCESS bulk ZIP file.

    This is a ~1.5GB download. Only downloads if not already cached.
    Returns path to the ZIP file.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DATA_DIR / "dbwebexport.zip"

    if zip_path.exists() and not force:
        print(f"Bulk data already cached: {zip_path} ({zip_path.stat().st_size / 1e9:.1f} GB)")
        return zip_path

    print(f"Downloading CAL-ACCESS bulk data (~1.5 GB)...")
    print(f"URL: {BULK_DATA_URL}")
    response = requests.get(BULK_DATA_URL, stream=True)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    downloaded = 0

    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192 * 128):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                print(f"\r  {downloaded / 1e6:.0f} / {total / 1e6:.0f} MB ({pct:.0f}%)", end="")

    print(f"\n  Saved to {zip_path}")
    return zip_path


def find_richmond_filers(
    zip_path: Path,
    *,
    city_fips: str | None = None,
) -> list[dict]:
    """
    Search FILERNAME_CD for city-related committees.

    Returns list of unique filer records matching search keywords,
    de-duplicated by FILER_ID (preferring ACTIVE records).
    """
    keywords, _fips = _resolve_calaccess_config(city_fips)
    richmond_filers = []
    print("Searching FILERNAME_CD for Richmond filers...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        with zf.open("CalAccess/DATA/FILERNAME_CD.TSV") as f:
            text_stream = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            clean_lines = (line.replace("\x00", "") for line in text_stream)
            reader = csv.DictReader(clean_lines, delimiter="\t")
            for row in reader:
                naml = (row.get("NAML") or "").strip()
                namf = (row.get("NAMF") or "").strip()
                filer_name = f"{namf} {naml}".strip()
                city = (row.get("CITY") or "").strip()
                filer_name_lower = filer_name.lower()
                city_lower = city.lower()

                if any(kw in filer_name_lower or kw in city_lower for kw in keywords):
                    richmond_filers.append({
                        "filer_id": (row.get("FILER_ID") or "").strip(),
                        "xref_filer_id": (row.get("XREF_FILER_ID") or "").strip(),
                        "name": filer_name,
                        "city": city,
                        "state": (row.get("ST") or "").strip(),
                        "status": (row.get("STATUS") or "").strip(),
                        "filer_type": (row.get("FILER_TYPE") or "").strip(),
                        "effect_date": (row.get("EFFECT_DT") or "").strip(),
                    })

    # De-duplicate by filer_id, preferring ACTIVE records
    unique = {}
    for f in richmond_filers:
        fid = f["filer_id"]
        if fid not in unique or f["status"] == "ACTIVE":
            unique[fid] = f

    result = list(unique.values())
    print(f"Found {len(result)} unique Richmond-area filers")
    return result


def find_richmond_filing_ids(zip_path: Path) -> dict[str, dict]:
    """
    Get all FILING_IDs for Richmond-related committees.

    Uses CVR_CAMPAIGN_DISCLOSURE_CD to find filings where the filer
    is based in Richmond or the jurisdiction mentions Richmond.

    Returns: {filing_id: {filer_id, name, form_type}}
    """
    filing_map = {}
    print("Searching CVR_CAMPAIGN_DISCLOSURE_CD for Richmond filings...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        with zf.open("CalAccess/DATA/CVR_CAMPAIGN_DISCLOSURE_CD.TSV") as f:
            # CAL-ACCESS TSVs contain NUL bytes from database padding — strip them
            text_stream = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            clean_lines = (line.replace("\x00", "") for line in text_stream)
            reader = csv.DictReader(clean_lines, delimiter="\t")
            for row in reader:
                naml = (row.get("FILER_NAML") or "").lower()
                city = (row.get("FILER_CITY") or "").lower()
                state = (row.get("FILER_ST") or "").lower()
                juris = (row.get("JURIS_DSCR") or "").lower()

                is_richmond = (
                    ("richmond" in city and "ca" in state)
                    or "richmond" in juris
                    or "richmond" in naml
                )

                if is_richmond:
                    filing_id = (row.get("FILING_ID") or "").strip()
                    filer_id = (row.get("FILER_ID") or "").strip()
                    name = (
                        (row.get("FILER_NAMF") or "") + " " +
                        (row.get("FILER_NAML") or "")
                    ).strip()
                    form_type = (row.get("FORM_TYPE") or "").strip()
                    filing_map[filing_id] = {
                        "filer_id": filer_id,
                        "name": name,
                        "form_type": form_type,
                    }

    print(f"Found {len(filing_map)} Richmond-related filing IDs")
    return filing_map


def get_richmond_contributions(
    zip_path: Path,
    min_amount: float = 100,
    filing_map: Optional[dict] = None,
    *,
    city_fips: str | None = None,
) -> list[dict]:
    """
    Get all contributions to city-related committees.

    Two-step process:
    1. Find city committee FILING_IDs via CVR_CAMPAIGN_DISCLOSURE_CD
    2. Match those FILING_IDs against RCPT_CD contributions

    Note: RCPT_CD uses FILING_ID (not FILER_ID) as the join key.
    """
    _keywords, resolved_fips = _resolve_calaccess_config(city_fips)
    if filing_map is None:
        filing_map = find_richmond_filing_ids(zip_path)

    print(f"Extracting contributions from RCPT_CD (min ${min_amount:.0f})...")
    contributions = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        with zf.open("CalAccess/DATA/RCPT_CD.TSV") as f:
            text_stream = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            clean_lines = (line.replace("\x00", "") for line in text_stream)
            reader = csv.DictReader(clean_lines, delimiter="\t")
            for row in reader:
                filing_id = (row.get("FILING_ID") or "").strip()
                if filing_id not in filing_map:
                    continue

                amount_str = (row.get("AMOUNT") or "0").strip()
                try:
                    amount = float(amount_str) if amount_str else 0
                except ValueError:
                    continue

                if amount < min_amount:
                    continue

                info = filing_map[filing_id]
                contributions.append({
                    "filer_id": info["filer_id"],
                    "committee": info["name"],
                    "filing_id": filing_id,
                    "form_type": info["form_type"],
                    "contributor_name": (
                        (row.get("CTRIB_NAMF") or "") + " " +
                        (row.get("CTRIB_NAML") or "")
                    ).strip(),
                    "contributor_city": (row.get("CTRIB_CITY") or "").strip(),
                    "contributor_state": (row.get("CTRIB_ST") or "").strip(),
                    "contributor_employer": (row.get("CTRIB_EMP") or "").strip(),
                    "contributor_occupation": (row.get("CTRIB_OCC") or "").strip(),
                    "amount": amount,
                    "date": (row.get("RCPT_DATE") or "").strip(),
                    "entity_code": (row.get("ENTITY_CD") or "").strip(),
                    "city_fips": resolved_fips,
                })

    print(f"Found {len(contributions)} contributions >= ${min_amount:.0f}")
    return contributions


def build_donor_index(contributions: list[dict]) -> dict:
    """
    Build an index of donors and their total contributions.

    Useful for the conflict scanner: cross-reference donors against
    vendors, property owners, or parties with business before council.
    """
    donors = {}
    for c in contributions:
        name = c["contributor_name"].upper().strip()
        if not name:
            continue

        if name not in donors:
            donors[name] = {
                "name": c["contributor_name"],
                "employer": c.get("contributor_employer", ""),
                "occupation": c.get("contributor_occupation", ""),
                "total_amount": 0,
                "contribution_count": 0,
                "recipients": set(),
            }

        donors[name]["total_amount"] += c["amount"]
        donors[name]["contribution_count"] += 1
        donors[name]["recipients"].add(c.get("committee", c.get("filer_id", "")))

    # Convert sets to lists for JSON serialization
    for d in donors.values():
        d["recipients"] = list(d["recipients"])

    return donors


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CAL-ACCESS Richmond campaign finance data")
    parser.add_argument("action", choices=["download", "filers", "contributions", "donors"])
    parser.add_argument("--min-amount", type=float, default=100,
                        help="Minimum contribution amount (default: $100)")
    parser.add_argument("--limit", type=int, default=30,
                        help="Max results to display (default: 30)")
    parser.add_argument("--save", action="store_true",
                        help="Save results to JSON")
    args = parser.parse_args()

    zip_path = DATA_DIR / "dbwebexport.zip"

    if args.action == "download":
        download_bulk_data()

    elif args.action == "filers":
        if not zip_path.exists():
            print("Run 'download' first")
        else:
            filers = find_richmond_filers(zip_path)
            richmond_named = [f for f in filers if "richmond" in f["name"].lower()]
            print(f"\nFilers with 'richmond' in name ({len(richmond_named)}):")
            for f in sorted(richmond_named, key=lambda x: x["name"])[:args.limit]:
                status = "ACTIVE" if f["status"] == "ACTIVE" else "inactive"
                print(f"  [{f['filer_id']:>8s}] {f['name'][:55]:55s} ({f['city']}, {status})")

            if args.save:
                output = DATA_DIR / "richmond_filers.json"
                with open(output, "w") as fp:
                    json.dump(filers, fp, indent=2)
                print(f"\nSaved {len(filers)} filers to {output}")

    elif args.action == "contributions":
        if not zip_path.exists():
            print("Run 'download' first")
        else:
            contributions = get_richmond_contributions(zip_path, min_amount=args.min_amount)

            # Summary by committee
            by_committee = defaultdict(list)
            for c in contributions:
                by_committee[c["committee"]].append(c)

            print(f"\nContributions by committee:")
            for comm, contribs in sorted(by_committee.items(), key=lambda x: -sum(c["amount"] for c in x[1]))[:args.limit]:
                total = sum(c["amount"] for c in contribs)
                print(f"  {comm[:55]:55s}: {len(contribs):4d} contribs, ${total:>12,.2f}")

            if args.save:
                output = DATA_DIR / "richmond_contributions.json"
                with open(output, "w") as fp:
                    json.dump(contributions, fp, indent=2)
                print(f"\nSaved {len(contributions)} contributions to {output}")

    elif args.action == "donors":
        if not zip_path.exists():
            print("Run 'download' first")
        else:
            contributions = get_richmond_contributions(zip_path, min_amount=args.min_amount)
            donors = build_donor_index(contributions)

            print(f"\nTop {args.limit} donors (all Richmond committees):")
            for name, info in sorted(donors.items(), key=lambda x: -x[1]["total_amount"])[:args.limit]:
                print(f"  ${info['total_amount']:>10,.2f}  {info['name']}")

            if args.save:
                output = DATA_DIR / "richmond_donors.json"
                with open(output, "w") as fp:
                    json.dump(donors, fp, indent=2, default=list)
                print(f"\nSaved {len(donors)} donors to {output}")
