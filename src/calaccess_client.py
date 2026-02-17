"""
CAL-ACCESS campaign finance data client for Richmond, California.

Downloads the statewide bulk data from the Secretary of State,
extracts the RCPT_CD (contributions) and FILER_CD (committees) tables,
and filters for Richmond-area committees and contributors.

Data source: https://www.sos.ca.gov/campaign-lobbying/cal-access-resources/raw-data-campaign-finance-and-lobbying-activity
Bulk download: https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip

Key tables:
  RCPT_CD    — Itemized contributions (Schedule A/C of Form 460)
  EXPN_CD    — Itemized expenditures
  FILER_CD   — Committee/filer registration info
  CVR_SO_CD  — Slate mailer cover page (links to filer)

For Richmond, we care about:
  - Contributions TO Richmond council candidates/committees
  - Contributions FROM Richmond-area donors to any local committee
  - Independent expenditure committees active in Richmond elections

Note: The bulk ZIP is ~1.5GB and expands to ~10GB. We download once,
extract only what we need, and cache locally.
"""

import os
import csv
import json
import zipfile
import io
from pathlib import Path
from typing import Optional

import requests

BULK_DATA_URL = "https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip"
DATA_DIR = Path(__file__).parent.parent / "data" / "calaccess"
CITY_FIPS = "0660620"

# Richmond council member names (for matching against filer records)
# Update this list as council composition changes
RICHMOND_OFFICIALS = [
    "Eduardo Martinez",
    "Cesar Zepeda",
    "Soheila Bana",
    "Jamelia Brown",
    "Claudia Jimenez",
    "Doria Robinson",
    "Sue Wilson",
    # Historical — extend as needed
    "Tom Butt",
    "Nat Bates",
    "Gayle McLaughlin",
]

# Richmond-area keywords for filtering committees
RICHMOND_KEYWORDS = [
    "richmond",
    "contra costa",
    "west contra costa",
]


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


def extract_table_from_zip(zip_path: Path, table_name: str) -> Path:
    """
    Extract a single TSV file from the bulk ZIP.

    Tables are stored as CalAccess/DATA/{TABLE_NAME}.TSV inside the ZIP.
    """
    tsv_path = DATA_DIR / f"{table_name}.TSV"

    if tsv_path.exists():
        print(f"Already extracted: {tsv_path}")
        return tsv_path

    target = f"CalAccess/DATA/{table_name}.TSV"
    print(f"Extracting {target} from ZIP...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        # List matching files (case-insensitive)
        matching = [n for n in zf.namelist() if n.upper().endswith(f"{table_name}.TSV")]
        if not matching:
            raise FileNotFoundError(
                f"Table {table_name} not found in ZIP. "
                f"Available: {[n for n in zf.namelist() if n.endswith('.TSV')][:10]}"
            )

        with zf.open(matching[0]) as src, open(tsv_path, "wb") as dst:
            dst.write(src.read())

    print(f"  Extracted: {tsv_path} ({tsv_path.stat().st_size / 1e6:.1f} MB)")
    return tsv_path


def find_richmond_filers(zip_path: Path) -> list[dict]:
    """
    Search the FILER_CD table for Richmond-related committees.

    Returns list of filer records matching Richmond keywords.
    """
    tsv_path = extract_table_from_zip(zip_path, "FILER_CD")

    richmond_filers = []
    with open(tsv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            # Check if any Richmond keyword appears in filer name or city
            filer_name = (row.get("NAML", "") + " " + row.get("NAMF", "")).lower()
            city = row.get("CITY", "").lower()

            if any(kw in filer_name or kw in city for kw in RICHMOND_KEYWORDS):
                richmond_filers.append(row)

    print(f"Found {len(richmond_filers)} Richmond-area filers")
    return richmond_filers


def get_contributions_for_filer(
    zip_path: Path,
    filer_id: str,
    min_amount: float = 0,
) -> list[dict]:
    """
    Get all contributions received by a specific filer/committee.

    Searches the RCPT_CD table for records matching the filer_id.
    """
    tsv_path = extract_table_from_zip(zip_path, "RCPT_CD")

    contributions = []
    with open(tsv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("FILER_ID") == filer_id:
                amount = float(row.get("AMOUNT", "0") or "0")
                if amount >= min_amount:
                    contributions.append({
                        "filer_id": row.get("FILER_ID"),
                        "filing_id": row.get("FILING_ID"),
                        "amendment_id": row.get("AMEND_ID"),
                        "contributor_name": f"{row.get('CTRIB_NAMF', '')} {row.get('CTRIB_NAML', '')}".strip(),
                        "contributor_city": row.get("CTRIB_CITY", ""),
                        "contributor_state": row.get("CTRIB_ST", ""),
                        "contributor_zip": row.get("CTRIB_ZIP4", ""),
                        "contributor_employer": row.get("CTRIB_EMP", ""),
                        "contributor_occupation": row.get("CTRIB_OCC", ""),
                        "amount": amount,
                        "cumulative_amount": row.get("CUM_OTH", ""),
                        "date": row.get("RCPT_DATE", ""),
                        "form_type": row.get("FORM_TYPE", ""),
                        "entity_type": row.get("ENTITY_CD", ""),
                        "city_fips": CITY_FIPS,
                    })

    print(f"Found {len(contributions)} contributions for filer {filer_id}")
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
                "employer": c["contributor_employer"],
                "occupation": c["contributor_occupation"],
                "total_amount": 0,
                "contribution_count": 0,
                "recipients": set(),
            }

        donors[name]["total_amount"] += c["amount"]
        donors[name]["contribution_count"] += 1
        donors[name]["recipients"].add(c["filer_id"])

    # Convert sets to lists for JSON serialization
    for d in donors.values():
        d["recipients"] = list(d["recipients"])

    return donors


# ---- CLI ----

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CAL-ACCESS Richmond data")
    parser.add_argument("action", choices=["download", "filers", "contributions"])
    parser.add_argument("--filer-id", help="Filer ID for contribution lookup")
    parser.add_argument("--min-amount", type=float, default=100)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    if args.action == "download":
        download_bulk_data()

    elif args.action == "filers":
        zip_path = DATA_DIR / "dbwebexport.zip"
        if not zip_path.exists():
            print("Run 'download' first")
        else:
            filers = find_richmond_filers(zip_path)
            for f in filers[:args.limit]:
                name = f"{f.get('NAMF', '')} {f.get('NAML', '')}".strip()
                fid = f.get("FILER_ID", "?")
                city = f.get("CITY", "?")
                print(f"  [{fid:>8s}] {name:40s} ({city})")

    elif args.action == "contributions":
        if not args.filer_id:
            print("--filer-id required for contributions lookup")
        else:
            zip_path = DATA_DIR / "dbwebexport.zip"
            contribs = get_contributions_for_filer(
                zip_path, args.filer_id, min_amount=args.min_amount
            )
            for c in contribs[:args.limit]:
                print(
                    f"  ${c['amount']:>10,.2f}  {c['date']:10s}  "
                    f"{c['contributor_name']:30s}  {c['contributor_employer']}"
                )
