"""
Load paper-filed campaign contributions into the database.

Reads JSON files from src/data/paper_filings/ and loads them via
the same load_contributions_to_db() used for NetFile e-filed data.
Paper filings are tagged with source='fppc_paper' to distinguish
from electronic filings (source='netfile').

Usage:
    python load_paper_filings.py                     # load all JSON files
    python load_paper_filings.py anderson_mayor_2026 # load specific filing
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, load_contributions_to_db

PAPER_FILINGS_DIR = Path(__file__).parent / "data" / "paper_filings"


def load_paper_filing(filing_path: Path) -> dict:
    """Load a single paper filing JSON and insert contributions into the database."""
    with open(filing_path, encoding="utf-8") as f:
        data = json.load(f)

    committee = data["committee"]
    fppc_id = data.get("fppc_id", "")
    city_fips = data.get("city_fips", "0660620")

    # Tag each contribution with committee name and paper source
    records = []
    for c in data["contributions"]:
        records.append({
            "contributor_name": c["contributor_name"],
            "contributor_employer": c.get("contributor_employer", ""),
            "amount": c["amount"],
            "date": c["date"],
            "committee": committee,
            "occupation": c.get("occupation", ""),
            "source": "fppc_paper",
            "filing_id": c.get("filing_id", ""),
            "filer_fppc_id": fppc_id,
            "entity_code": c.get("entity_code", "IND"),
        })

    print(f"Loading {len(records)} contributions from {committee} ({filing_path.name})")

    conn = get_connection()
    try:
        stats = load_contributions_to_db(conn, records, city_fips=city_fips)
        conn.commit()
        print(f"  Donors created:        {stats['donors']}")
        print(f"  Committees created:    {stats['committees']}")
        print(f"  Contributions loaded:  {stats['contributions']}")
        print(f"  Skipped:               {stats['skipped']}")
        return stats
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Load paper-filed campaign contributions")
    parser.add_argument("filing", nargs="?", help="Filing JSON name (without .json extension)")
    args = parser.parse_args()

    if args.filing:
        path = PAPER_FILINGS_DIR / f"{args.filing}.json"
        if not path.exists():
            print(f"Filing not found: {path}")
            sys.exit(1)
        load_paper_filing(path)
    else:
        json_files = sorted(PAPER_FILINGS_DIR.glob("*.json"))
        if not json_files:
            print(f"No JSON files found in {PAPER_FILINGS_DIR}")
            sys.exit(1)
        for path in json_files:
            load_paper_filing(path)
            print()


if __name__ == "__main__":
    main()
