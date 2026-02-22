# src/commission_roster_scraper.py
"""
Scrape commission roster pages from Richmond's city website.

Parses member names, roles (chair/vice_chair/member), and term dates.
Richmond uses simple HTML tables with columns: Name | Appointed | Term Expiration.
Roles are embedded as parentheticals in the name cell, e.g. "Jane Smith (Chair)".

NOTE: HTML selectors are Richmond-specific. When adding a new city,
the scraper needs city-specific selector profiles (similar to
ESCRIBEMEETINGS_PLATFORM_PROFILE in escribemeetings_enricher.py).

Usage:
    python commission_roster_scraper.py --all                          # Scrape all commissions
    python commission_roster_scraper.py --commission "Planning Commission"  # One commission
    python commission_roster_scraper.py --output FILE                  # Save JSON
    python commission_roster_scraper.py --load                         # Load to DB
    python commission_roster_scraper.py --inspect --url URL            # Debug: show parsed HTML
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

CITY_FIPS = "0660620"

# ── Vacant seat detection ────────────────────────────────────
_VACANT_PATTERNS = {"vacant", "vacancy", "tbd", "to be determined", "unfilled"}


def normalize_member_name(name: str | None) -> str:
    """Normalize a member name for matching. Returns '' for vacant/null."""
    if not name:
        return ""
    cleaned = " ".join(name.strip().split())
    if cleaned.lower() in _VACANT_PATTERNS:
        return ""
    return cleaned.lower()


def _parse_role(role_text: str) -> str:
    """Normalize role text to chair/vice_chair/member."""
    lower = role_text.lower().strip()
    if "vice" in lower and "chair" in lower:
        return "vice_chair"
    if "chair" in lower:
        return "chair"
    return "member"


def _extract_name_and_role(raw_name: str) -> tuple[str, str]:
    """Extract clean name and role from a cell like 'Jane Smith (Chair)'.

    Returns (clean_name, role) where role is chair/vice_chair/member.
    """
    # Match parenthetical at end of name
    match = re.search(r"\(([^)]+)\)\s*$", raw_name)
    if match:
        role_text = match.group(1)
        clean_name = raw_name[: match.start()].strip()
        role = _parse_role(role_text)
    else:
        clean_name = raw_name.strip()
        role = "member"
    # Collapse internal whitespace
    clean_name = " ".join(clean_name.split())
    return clean_name, role


def _parse_term_date(text: str) -> str | None:
    """Extract the last MM/DD/YYYY date from term text.

    When multiple dates are listed (e.g. "06/30/2025, 06/30/2027"),
    returns the last one as an ISO date string (YYYY-MM-DD).
    """
    if not text:
        return None
    matches = re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if not matches:
        return None
    # Take the last date (most recent / latest term expiration)
    month, day, year = matches[-1]
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _is_roster_table(headers: list[str]) -> bool:
    """Check if table headers indicate a commission roster table."""
    normalized = [h.strip().upper() for h in headers]
    return "NAME" in normalized


def parse_roster_page(html: str) -> list[dict]:
    """Parse a commission roster page into member dicts.

    Looks for HTML tables with a NAME column header. Extracts member
    name, role (from parenthetical), and term expiration date.

    Returns list of dicts with keys: name, role, term_end
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []

    for table in soup.find_all("table"):
        # Identify column positions from header row
        header_row = table.find("thead")
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all("th")]
        else:
            # Some tables use the first <tr> as header
            first_row = table.find("tr")
            if not first_row:
                continue
            headers = [cell.get_text(strip=True) for cell in first_row.find_all(["th", "td"])]

        if not _is_roster_table(headers):
            continue

        # Map column names to indices
        col_map = {}
        for i, h in enumerate(headers):
            upper = h.strip().upper()
            if "NAME" in upper:
                col_map["name"] = i
            elif "TERM" in upper and "EXPIR" in upper:
                col_map["term_end"] = i
            elif "APPOINTED" in upper:
                col_map["appointed"] = i

        if "name" not in col_map:
            continue

        # Parse data rows from tbody (or all tr after header)
        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for row in rows:
            cells = row.find_all("td")
            if len(cells) <= col_map["name"]:
                continue

            raw_name = cells[col_map["name"]].get_text(strip=True)
            normalized = normalize_member_name(raw_name)
            if not normalized:
                continue  # Skip vacant seats

            # Extract name and role from parenthetical
            clean_name, role = _extract_name_and_role(raw_name)

            # Extract term expiration date
            term_end = None
            if "term_end" in col_map and len(cells) > col_map["term_end"]:
                term_text = cells[col_map["term_end"]].get_text(strip=True)
                term_end = _parse_term_date(term_text)

            members.append({
                "name": clean_name,
                "role": role,
                "term_end": term_end,
            })

    return members


def build_member_record(
    raw: dict,
    *,
    commission_name: str,
    city_fips: str = CITY_FIPS,
) -> dict:
    """Build a full member record for DB insertion."""
    return {
        "city_fips": city_fips,
        "commission_name": commission_name,
        "name": raw["name"],
        "normalized_name": normalize_member_name(raw["name"]),
        "role": raw["role"],
        "term_end": raw.get("term_end"),
        "is_current": True,
        "source": "city_website",
    }


def fetch_roster(url: str) -> str:
    """Fetch a commission roster page HTML."""
    resp = requests.get(url, timeout=30, headers={
        "User-Agent": "RichmondTransparencyProject/1.0 (civic research)"
    })
    resp.raise_for_status()
    return resp.text


def _load_commissions_config() -> list[dict]:
    """Load commission seed data from officials.json."""
    gt_path = Path(__file__).parent / "ground_truth" / "officials.json"
    if not gt_path.exists():
        return []
    data = json.loads(gt_path.read_text())
    return data.get("commissions", [])


def scrape_commission(commission: dict, *, city_fips: str = CITY_FIPS) -> list[dict]:
    """Scrape a single commission's roster.

    Args:
        commission: dict with 'name' and 'website_roster_url' keys.

    Returns list of member records.
    """
    url = commission.get("website_roster_url")
    if not url:
        logger.warning("No roster URL for %s — skipping", commission["name"])
        return []

    logger.info("Scraping %s from %s", commission["name"], url)
    html = fetch_roster(url)
    raw_members = parse_roster_page(html)
    logger.info("  Found %d members", len(raw_members))

    return [
        build_member_record(m, commission_name=commission["name"], city_fips=city_fips)
        for m in raw_members
    ]


def scrape_all_commissions(*, city_fips: str = CITY_FIPS) -> dict[str, list[dict]]:
    """Scrape all commission rosters from ground truth config.

    Returns dict mapping commission name to list of member records.
    """
    commissions = _load_commissions_config()
    if not commissions:
        logger.error("No commissions found in officials.json")
        return {}

    results = {}
    for c in commissions:
        members = scrape_commission(c, city_fips=city_fips)
        results[c["name"]] = members

    total = sum(len(v) for v in results.values())
    logger.info("Scraped %d commissions, %d total members", len(results), total)
    return results


def load_to_db(all_members: dict[str, list[dict]], *, city_fips: str = CITY_FIPS) -> None:
    """Load scraped roster data to Supabase."""
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for commission_name, members in all_members.items():
                # Find or create commission
                cur.execute(
                    "SELECT id FROM commissions WHERE city_fips = %s AND name = %s",
                    (city_fips, commission_name),
                )
                row = cur.fetchone()
                if not row:
                    logger.warning("Commission '%s' not in DB — run migration + seed first", commission_name)
                    continue
                commission_id = row[0]

                for m in members:
                    cur.execute(
                        """INSERT INTO commission_members
                           (city_fips, commission_id, name, normalized_name, role,
                            term_end, is_current, source)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT ON CONSTRAINT uq_commission_member
                           DO UPDATE SET
                               role = EXCLUDED.role,
                               term_end = EXCLUDED.term_end,
                               is_current = EXCLUDED.is_current,
                               source = EXCLUDED.source,
                               updated_at = NOW()""",
                        (
                            m["city_fips"], commission_id, m["name"],
                            m["normalized_name"], m["role"],
                            m["term_end"], m["is_current"], m["source"],
                        ),
                    )

                # Update last_website_scrape timestamp
                cur.execute(
                    "UPDATE commissions SET last_website_scrape = NOW() WHERE id = %s",
                    (commission_id,),
                )

            conn.commit()
        total = sum(len(v) for v in all_members.values())
        logger.info("Loaded %d members across %d commissions", total, len(all_members))
    finally:
        conn.close()


# ── CLI ─────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape commission rosters from city website"
    )
    parser.add_argument("--all", action="store_true", help="Scrape all commissions")
    parser.add_argument("--commission", help="Scrape one commission by name")
    parser.add_argument("--output", type=Path, help="Save JSON to file")
    parser.add_argument("--load", action="store_true", help="Load to Supabase")
    parser.add_argument("--inspect", action="store_true", help="Debug: print parsed HTML")
    parser.add_argument("--url", help="URL to inspect (with --inspect)")
    parser.add_argument("--city-fips", default=None, help="City FIPS code")
    args = parser.parse_args()

    fips = args.city_fips or CITY_FIPS
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.inspect and args.url:
        html = fetch_roster(args.url)
        members = parse_roster_page(html)
        print(f"\nParsed {len(members)} members:")
        for m in members:
            print(f"  {m['name']:30s} {m['role']:12s} expires={m.get('term_end', 'N/A')}")
        return

    if args.commission:
        configs = _load_commissions_config()
        match = [c for c in configs if c["name"].lower() == args.commission.lower()]
        if not match:
            print(f"Commission '{args.commission}' not found in officials.json")
            print(f"Available: {[c['name'] for c in configs]}")
            sys.exit(1)
        results = {match[0]["name"]: scrape_commission(match[0], city_fips=fips)}
    elif args.all:
        results = scrape_all_commissions(city_fips=fips)
    else:
        parser.print_help()
        return

    # Print summary
    for name, members in results.items():
        print(f"\n{name} ({len(members)} members):")
        for m in members:
            print(f"  {m['name']:30s} {m['role']:12s}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2, default=str))
        logger.info("Saved to %s", args.output)

    if args.load:
        load_to_db(results, city_fips=fips)


if __name__ == "__main__":
    main()
