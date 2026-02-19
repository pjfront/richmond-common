"""
Richmond Transparency Project -- Census Surname Data Preprocessor

Downloads Census 2010 surname frequency data and pre-processes it into
a {normalized_surname: tier} JSON lookup used by bias_signals.py.

Source: https://www2.census.gov/topics/genealogy/2010surnames/names.zip
Output: src/data/census/surname_freq.json

Tiers (per docs/specs/bias-audit-spec.md):
  Tier 1: rank 1-100 (most common)
  Tier 2: rank 101-1000
  Tier 3: rank 1001-10000
  Tier 4: rank 10001+ (rare)

Usage:
  python prepare_census_data.py
  python prepare_census_data.py --skip-download  # if CSV already exists
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "census"
CSV_FILENAME = "Names_2010Census.csv"
OUTPUT_FILENAME = "surname_freq.json"
CENSUS_URL = "https://www2.census.gov/topics/genealogy/2010surnames/names.zip"


def assign_tier(rank: int) -> int:
    """Map Census surname rank to frequency tier."""
    if rank <= 100:
        return 1
    elif rank <= 1000:
        return 2
    elif rank <= 10000:
        return 3
    else:
        return 4


def process_census_csv(csv_text: str) -> dict[str, int]:
    """Convert Census CSV text to {lowercase_surname: tier} dict.

    Args:
        csv_text: Raw CSV content with header row.

    Returns:
        Dict mapping lowercase surname to tier (1-4).
    """
    result = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        name = row.get("name", "").strip()
        rank_str = row.get("rank", "").strip()
        if not name or not rank_str:
            continue
        try:
            rank = int(rank_str)
        except ValueError:
            continue
        result[name.lower()] = assign_tier(rank)
    return result


def download_census_data() -> Path:
    """Download Census 2010 surname ZIP and extract CSV."""
    import requests

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_DIR / CSV_FILENAME

    if csv_path.exists():
        print(f"  CSV already exists at {csv_path}")
        return csv_path

    print(f"  Downloading {CENSUS_URL} ...")
    resp = requests.get(CENSUS_URL, timeout=120)
    resp.raise_for_status()

    zip_path = DATA_DIR / "names.zip"
    zip_path.write_bytes(resp.content)
    print(f"  Saved ZIP to {zip_path} ({len(resp.content):,} bytes)")

    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError(f"No CSV found in ZIP. Contents: {zf.namelist()}")
        csv_name = csv_names[0]
        zf.extract(csv_name, DATA_DIR)
        extracted = DATA_DIR / csv_name
        if extracted.name != CSV_FILENAME:
            extracted.rename(csv_path)
        print(f"  Extracted {csv_name} to {csv_path}")

    return csv_path


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Download and preprocess Census 2010 surname frequency data",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download (use existing CSV)",
    )
    args = parser.parse_args()

    print("Census 2010 Surname Data Preprocessor")
    print("=" * 50)

    csv_path = DATA_DIR / CSV_FILENAME
    if not args.skip_download:
        csv_path = download_census_data()

    if not csv_path.exists():
        print(f"ERROR: CSV not found at {csv_path}")
        print("Run without --skip-download to fetch the data.")
        return

    print(f"  Processing {csv_path} ...")
    csv_text = csv_path.read_text(encoding="utf-8", errors="replace")
    surname_freq = process_census_csv(csv_text)

    output_path = DATA_DIR / OUTPUT_FILENAME
    with open(output_path, "w") as f:
        json.dump(surname_freq, f)
    print(f"  Wrote {len(surname_freq):,} surnames to {output_path}")

    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for tier in surname_freq.values():
        tier_counts[tier] += 1
    print(f"  Tier 1 (rank 1-100):     {tier_counts[1]:,}")
    print(f"  Tier 2 (rank 101-1000):  {tier_counts[2]:,}")
    print(f"  Tier 3 (rank 1001-10k):  {tier_counts[3]:,}")
    print(f"  Tier 4 (rank 10001+):    {tier_counts[4]:,}")
    print("Done.")


if __name__ == "__main__":
    main()
