# Commissions & Board Members — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the data foundation for commission transparency: schema, seed data, website roster scraping, appointment extraction from council minutes, and eSCRIBE commission meeting discovery.

**Architecture:** Three sub-phases. B1 builds the schema and website scraper (zero LLM cost). B2 uses Claude API (~$0.50 total) to mine 21 already-extracted council meeting JSONs for appointment actions, then compares against the website roster for staleness detection. B3 extends the eSCRIBE scraper to discover and catalog commission meeting types. Every module follows the city-config resolution pattern (`_resolve_*_config(city_fips)`) for multi-city scaling.

**Tech Stack:** Python, BeautifulSoup (roster scraping), Claude API (appointment extraction), eSCRIBE calendar API (meeting discovery), PostgreSQL (Supabase), pytest

**Design doc:** `docs/plans/2026-02-22-commissions-design.md`

**Migration number:** 005 (city employees is 004)

**Branch:** `feature/commissions`

---

## Sub-Phase B1: Schema + Seed Data + Website Roster Scraping

### Task 1: Migration — `commissions` and `commission_members` Tables

**Files:**
- Create: `src/migrations/005_commissions.sql`
- Create: `tests/test_migration_005.py`

**Step 1: Write the migration file**

```sql
-- Migration 005: Commissions & board members
-- Schema for commission rosters, appointments, and staleness tracking.
-- Idempotent: safe to re-run (uses IF NOT EXISTS / OR REPLACE).

-- ============================================================
-- New Table: commissions
-- Registry of city commissions, boards, and committees.
-- ============================================================

CREATE TABLE IF NOT EXISTS commissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    name VARCHAR(300) NOT NULL,
    commission_type VARCHAR(50) NOT NULL DEFAULT 'advisory',
    num_seats SMALLINT,
    appointment_authority VARCHAR(100),
    form700_required BOOLEAN NOT NULL DEFAULT FALSE,
    term_length_years SMALLINT,
    meeting_schedule VARCHAR(200),
    escribemeetings_type VARCHAR(200),
    archive_center_amid INTEGER,
    website_roster_url VARCHAR(500),
    last_website_scrape TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_commission UNIQUE (city_fips, name)
);

CREATE INDEX IF NOT EXISTS idx_commissions_fips ON commissions(city_fips);
CREATE INDEX IF NOT EXISTS idx_commissions_type ON commissions(commission_type);
CREATE INDEX IF NOT EXISTS idx_commissions_form700 ON commissions(form700_required, city_fips);

-- ============================================================
-- New Table: commission_members
-- People serving on commissions with appointment provenance.
-- ============================================================

CREATE TABLE IF NOT EXISTS commission_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    commission_id UUID NOT NULL REFERENCES commissions(id) ON DELETE CASCADE,
    name VARCHAR(300) NOT NULL,
    normalized_name VARCHAR(300) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'member',
    appointed_by VARCHAR(300),
    appointed_by_official_id UUID REFERENCES officials(id),
    term_start DATE,
    term_end DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    source VARCHAR(50) NOT NULL DEFAULT 'city_website',
    source_meeting_id UUID REFERENCES meetings(id),
    website_stale_since DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_commission_member UNIQUE (city_fips, commission_id, normalized_name)
);

CREATE INDEX IF NOT EXISTS idx_commission_members_fips ON commission_members(city_fips);
CREATE INDEX IF NOT EXISTS idx_commission_members_commission ON commission_members(commission_id);
CREATE INDEX IF NOT EXISTS idx_commission_members_current ON commission_members(is_current, city_fips);
CREATE INDEX IF NOT EXISTS idx_commission_members_name ON commission_members(normalized_name);
CREATE INDEX IF NOT EXISTS idx_commission_members_source ON commission_members(source);
CREATE INDEX IF NOT EXISTS idx_commission_members_stale ON commission_members(website_stale_since)
    WHERE website_stale_since IS NOT NULL;

-- ============================================================
-- View: v_commission_staleness
-- Commissions with website roster out-of-date vs. minutes record.
-- ============================================================

CREATE OR REPLACE VIEW v_commission_staleness AS
SELECT
    c.id AS commission_id,
    c.city_fips,
    c.name AS commission_name,
    c.last_website_scrape,
    COUNT(cm.id) FILTER (WHERE cm.website_stale_since IS NOT NULL) AS stale_members,
    COUNT(cm.id) FILTER (WHERE cm.is_current = TRUE) AS total_current_members,
    MIN(cm.website_stale_since) AS oldest_stale_since,
    CURRENT_DATE - MIN(cm.website_stale_since) AS max_days_stale,
    ARRAY_AGG(cm.name ORDER BY cm.name)
        FILTER (WHERE cm.website_stale_since IS NOT NULL) AS stale_member_names
FROM commissions c
LEFT JOIN commission_members cm ON c.id = cm.commission_id
GROUP BY c.id, c.city_fips, c.name, c.last_website_scrape
HAVING COUNT(cm.id) FILTER (WHERE cm.website_stale_since IS NOT NULL) > 0;

-- ============================================================
-- View: v_appointment_network
-- Maps which council members appointed which commissioners.
-- ============================================================

CREATE OR REPLACE VIEW v_appointment_network AS
SELECT
    cm.city_fips,
    cm.appointed_by,
    o.id AS appointing_official_id,
    o.name AS appointing_official_name,
    c.name AS commission_name,
    c.commission_type,
    cm.name AS commissioner_name,
    cm.role,
    cm.term_start,
    cm.term_end,
    cm.is_current,
    cm.source
FROM commission_members cm
JOIN commissions c ON cm.commission_id = c.id
LEFT JOIN officials o ON cm.appointed_by_official_id = o.id
WHERE cm.appointed_by IS NOT NULL;
```

**Step 2: Write the migration test**

```python
# tests/test_migration_005.py
"""Verify migration 005 SQL is syntactically valid and idempotent."""
from pathlib import Path


MIGRATION_PATH = Path(__file__).parent.parent / "src" / "migrations" / "005_commissions.sql"


def test_migration_file_exists():
    assert MIGRATION_PATH.exists(), f"Migration not found: {MIGRATION_PATH}"


def test_migration_is_idempotent_keywords():
    """All CREATE statements use IF NOT EXISTS / OR REPLACE."""
    sql = MIGRATION_PATH.read_text()
    for line in sql.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("CREATE TABLE"):
            assert "IF NOT EXISTS" in stripped, f"Non-idempotent: {line.strip()}"
        if stripped.startswith("CREATE INDEX"):
            assert "IF NOT EXISTS" in stripped, f"Non-idempotent: {line.strip()}"
        if stripped.startswith("CREATE VIEW") or stripped.startswith("CREATE OR REPLACE VIEW"):
            assert "OR REPLACE" in stripped, f"Non-idempotent: {line.strip()}"


def test_migration_has_city_fips():
    """city_fips column present in both tables."""
    sql = MIGRATION_PATH.read_text()
    assert sql.count("city_fips") >= 4  # at minimum: 2 columns + 2 FK refs
    assert "REFERENCES cities(fips_code)" in sql


def test_migration_has_unique_constraints():
    sql = MIGRATION_PATH.read_text()
    assert "uq_commission" in sql
    assert "uq_commission_member" in sql


def test_migration_has_both_views():
    sql = MIGRATION_PATH.read_text()
    assert "v_commission_staleness" in sql
    assert "v_appointment_network" in sql
```

**Step 3: Run tests to verify they pass**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_migration_005.py -v
```

Expected: 5 PASSED

**Step 4: Commit**

```bash
git add src/migrations/005_commissions.sql tests/test_migration_005.py
git commit -m "feat: add migration 005 for commissions and commission_members tables"
```

---

### Task 2: Commission Seed Data in `officials.json` (Human Checkpoint)

**Files:**
- Modify: `src/ground_truth/officials.json`

**This is a human task.** The system pre-generates context to minimize decision time.

**Step 1: Research Richmond's commissions**

Open the city's boards/commissions page: `https://www.ci.richmond.ca.us/Boards`

Identify each commission's:
- Name (exact as listed on website)
- Type: `quasi_judicial` or `advisory`
- Number of seats
- Appointment authority (`mayor`, `council`, `mayor_council`)
- Whether Form 700 is required
- Meeting schedule
- Website roster URL

**Step 2: Add `commissions` section to `officials.json`**

The human adds entries in this format (template below — edit with actual data):

```json
{
  "city_fips": "0660620",
  "city_name": "Richmond, California",
  "updated": "2026-02-22",
  "current_council_members": [ ... ],
  "former_council_members": [ ... ],
  "commissions": [
    {
      "name": "Planning Commission",
      "type": "quasi_judicial",
      "num_seats": 7,
      "appointment_authority": "mayor_council",
      "form700_required": true,
      "term_length_years": 4,
      "meeting_schedule": "1st and 3rd Thursday monthly",
      "website_roster_url": "https://www.ci.richmond.ca.us/..."
    },
    {
      "name": "Rent Board",
      "type": "quasi_judicial",
      "num_seats": 5,
      "appointment_authority": "council",
      "form700_required": true,
      "term_length_years": 4,
      "meeting_schedule": "3rd Wednesday monthly",
      "website_roster_url": "https://www.ci.richmond.ca.us/..."
    },
    {
      "name": "Personnel Board",
      "type": "quasi_judicial",
      "num_seats": 5,
      "appointment_authority": "mayor_council",
      "form700_required": true,
      "term_length_years": 4,
      "meeting_schedule": "as needed",
      "website_roster_url": "https://www.ci.richmond.ca.us/..."
    },
    {
      "name": "Design Review Board",
      "type": "quasi_judicial",
      "num_seats": 5,
      "appointment_authority": "mayor_council",
      "form700_required": true,
      "term_length_years": 4,
      "meeting_schedule": "2nd and 4th Wednesday monthly",
      "website_roster_url": "https://www.ci.richmond.ca.us/..."
    },
    {
      "name": "Housing Authority",
      "type": "quasi_judicial",
      "num_seats": 7,
      "appointment_authority": "mayor",
      "form700_required": true,
      "term_length_years": 4,
      "meeting_schedule": "monthly",
      "website_roster_url": "https://www.ci.richmond.ca.us/..."
    },
    {
      "name": "Police Commission",
      "type": "quasi_judicial",
      "num_seats": 7,
      "appointment_authority": "council",
      "form700_required": true,
      "term_length_years": 4,
      "meeting_schedule": "1st Wednesday monthly",
      "website_roster_url": "https://www.ci.richmond.ca.us/..."
    }
  ]
}
```

**Priority:** Get the 6 quasi-judicial commissions right. Advisory commissions can be cataloged with just `name` and `type: "advisory"` — member data comes from the website scraper.

**Step 3: Verify JSON is valid**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -c "import json; json.loads(open('src/ground_truth/officials.json').read()); print('Valid JSON')"
```

**Step 4: Commit**

```bash
git add src/ground_truth/officials.json
git commit -m "feat: seed commission ground truth in officials.json"
```

---

### Task 3: Commission Roster Scraper — Core Parsing

**Files:**
- Create: `src/commission_roster_scraper.py`
- Create: `tests/test_commission_roster_scraper.py`

**Step 1: Write failing tests**

```python
# tests/test_commission_roster_scraper.py
"""Tests for city website commission roster scraping."""
from commission_roster_scraper import (
    parse_roster_page,
    normalize_member_name,
    build_member_record,
)


# ── Inline HTML fixture ──────────────────────────────────────
# Mimics Richmond's commission roster page structure.
# The actual selectors may need adjustment after inspecting the real page.
# Run `python commission_roster_scraper.py --inspect --url <URL>` to verify.

SAMPLE_ROSTER_HTML = """
<div class="boardMemberContainer">
  <div class="boardMember">
    <span class="memberName">Jane Smith</span>
    <span class="memberTitle">Chair</span>
    <span class="memberTerm">Term Expires: 06/30/2027</span>
  </div>
  <div class="boardMember">
    <span class="memberName">Bob Johnson</span>
    <span class="memberTitle">Vice Chair</span>
    <span class="memberTerm">Term Expires: 06/30/2028</span>
  </div>
  <div class="boardMember">
    <span class="memberName">Alice Williams</span>
    <span class="memberTitle">Member</span>
  </div>
  <div class="boardMember">
    <span class="memberName">VACANT</span>
    <span class="memberTitle">Member</span>
  </div>
</div>
"""

# NOTE: The HTML selectors above are PLACEHOLDERS. Before implementing,
# inspect the actual roster page at https://www.ci.richmond.ca.us/Boards
# and update the selectors in BOTH the test fixture and the scraper.
# Richmond uses CivicPlus/CivicEngage — class names vary by commission.


class TestNormalizeMemberName:
    def test_basic_name(self):
        assert normalize_member_name("Jane Smith") == "jane smith"

    def test_strips_extra_whitespace(self):
        assert normalize_member_name("  Jane   Smith  ") == "jane smith"

    def test_vacant_returns_empty(self):
        assert normalize_member_name("VACANT") == ""

    def test_vacancy_returns_empty(self):
        assert normalize_member_name("Vacancy") == ""

    def test_tbd_returns_empty(self):
        assert normalize_member_name("TBD") == ""

    def test_none_returns_empty(self):
        assert normalize_member_name(None) == ""


class TestParseRosterPage:
    def test_parses_members(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        # VACANT should be excluded
        assert len(members) == 3

    def test_extracts_name(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        names = [m["name"] for m in members]
        assert "Jane Smith" in names

    def test_extracts_role(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        chair = [m for m in members if m["name"] == "Jane Smith"][0]
        assert chair["role"] == "chair"

    def test_vice_chair_role(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        vc = [m for m in members if m["name"] == "Bob Johnson"][0]
        assert vc["role"] == "vice_chair"

    def test_member_role(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        member = [m for m in members if m["name"] == "Alice Williams"][0]
        assert member["role"] == "member"

    def test_extracts_term_end(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        chair = [m for m in members if m["name"] == "Jane Smith"][0]
        assert chair["term_end"] == "2027-06-30"

    def test_missing_term_is_none(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        member = [m for m in members if m["name"] == "Alice Williams"][0]
        assert member["term_end"] is None


class TestBuildMemberRecord:
    def test_includes_city_fips(self):
        raw = {"name": "Jane Smith", "role": "chair", "term_end": "2027-06-30"}
        rec = build_member_record(raw, commission_name="Planning Commission", city_fips="0660620")
        assert rec["city_fips"] == "0660620"
        assert rec["source"] == "city_website"

    def test_normalized_name(self):
        raw = {"name": "Jane Smith", "role": "member", "term_end": None}
        rec = build_member_record(raw, commission_name="Rent Board", city_fips="0660620")
        assert rec["normalized_name"] == "jane smith"

    def test_is_current_true_by_default(self):
        raw = {"name": "Jane Smith", "role": "member", "term_end": None}
        rec = build_member_record(raw, commission_name="Rent Board", city_fips="0660620")
        assert rec["is_current"] is True
```

**Step 2: Run tests — expect FAIL**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_commission_roster_scraper.py -v
```

Expected: ModuleNotFoundError for `commission_roster_scraper`

**Step 3: Implement the scraper core**

```python
# src/commission_roster_scraper.py
"""
Scrape commission roster pages from Richmond's city website.

Parses member names, roles (chair/vice_chair/member), and term dates.
Uses CivicPlus/CivicEngage HTML structure.

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


def _parse_term_date(text: str) -> str | None:
    """Extract a date from term text like 'Term Expires: 06/30/2027'.

    Returns ISO date string (YYYY-MM-DD) or None.
    """
    if not text:
        return None
    # Look for MM/DD/YYYY pattern
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:
        month, day, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


def parse_roster_page(html: str) -> list[dict]:
    """Parse a commission roster page into member dicts.

    NOTE: Selectors below are PLACEHOLDERS for Richmond's CivicPlus site.
    Before first use, inspect actual pages and update selectors.

    Returns list of dicts with keys: name, role, term_end
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []

    for el in soup.select(".boardMember"):
        name_el = el.select_one(".memberName")
        role_el = el.select_one(".memberTitle")
        term_el = el.select_one(".memberTerm")

        name_raw = name_el.get_text(strip=True) if name_el else ""
        normalized = normalize_member_name(name_raw)
        if not normalized:
            continue  # Skip vacant seats

        role = _parse_role(role_el.get_text(strip=True) if role_el else "member")
        term_end = _parse_term_date(term_el.get_text(strip=True) if term_el else "")

        members.append({
            "name": " ".join(name_raw.strip().split()),
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
```

**Step 4: Run tests — expect PASS**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_commission_roster_scraper.py -v
```

Expected: All PASSED

**Step 5: Commit**

```bash
git add src/commission_roster_scraper.py tests/test_commission_roster_scraper.py
git commit -m "feat: add commission roster scraper with HTML parsing and DB loading"
```

---

### Task 4: Pre-flight — Inspect Real Roster Pages (Human Checkpoint)

**This is a human-assisted step.** The scraper has placeholder selectors that must be verified against the actual website before use.

**Step 1: Inspect a real roster page**

Pick one commission URL from the seed data in `officials.json` and run:

```bash
cd src && python commission_roster_scraper.py --inspect --url "https://www.ci.richmond.ca.us/BOARD_URL_HERE"
```

**Step 2: If selectors don't match, update**

The CivicPlus HTML structure varies. Common patterns:
- `.boardMember` container might be `.widget-board-member` or `.board-member-item`
- Name might be in `h3`, `h4`, or a `<strong>` tag instead of `.memberName`
- Term dates might be in a different format

Update the selectors in `parse_roster_page()` AND the test fixture HTML to match reality.

**Step 3: Verify with --inspect**

```bash
cd src && python commission_roster_scraper.py --inspect --url "URL"
```

Should show parsed members matching the website.

**Step 4: Run tests again after any selector changes**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_commission_roster_scraper.py -v
```

**Step 5: Commit selector updates if needed**

```bash
git add src/commission_roster_scraper.py tests/test_commission_roster_scraper.py
git commit -m "fix: update commission roster selectors for actual CivicPlus HTML"
```

---

## Sub-Phase B2: Appointment Extraction from Council Minutes

### Task 5: Appointment Extractor — Claude API Extraction

**Files:**
- Create: `src/appointment_extractor.py`
- Create: `tests/test_appointment_extractor.py`

**Step 1: Write failing tests**

```python
# tests/test_appointment_extractor.py
"""Tests for commission appointment extraction from council minutes."""
import json
from unittest.mock import patch, MagicMock

from appointment_extractor import (
    extract_appointments_from_meeting,
    parse_claude_response,
    build_appointment_record,
    normalize_commission_name,
    APPOINTMENT_SCHEMA,
)


# ── Sample extracted meeting JSON (subset) ────────────────────
SAMPLE_MEETING = {
    "meeting_date": "2025-09-23",
    "consent_calendar": {
        "items": [
            {
                "item_number": "I.1",
                "title": "APPROVE the reappointment of Jane Doe to the Planning Commission for a term ending June 30, 2029",
                "description": "Reappointment by Mayor Martinez. Jane Doe has served since 2025.",
                "department": "City Clerk",
                "category": "personnel",
            },
            {
                "item_number": "I.2",
                "title": "APPROVE a contract with ABC Corp for $50,000",
                "description": "Maintenance contract renewal.",
                "department": "Public Works",
                "category": "contracts",
            },
        ]
    },
    "action_items": [
        {
            "item_number": "J.1",
            "title": "CONFIRM the appointment of Bob Smith to the Police Commission",
            "description": "Appointment by Councilmember Brown, District 1.",
            "department": "City Clerk",
            "category": "personnel",
        }
    ],
}

# ── Sample Claude API response ────────────────────────────────
SAMPLE_CLAUDE_RESPONSE = [
    {
        "person_name": "Jane Doe",
        "commission_name": "Planning Commission",
        "action": "reappoint",
        "appointed_by": "Mayor Martinez",
        "term_end": "2029-06-30",
        "item_number": "I.1",
        "confidence": 0.95,
    },
    {
        "person_name": "Bob Smith",
        "commission_name": "Police Commission",
        "action": "appoint",
        "appointed_by": "Councilmember Brown",
        "term_end": None,
        "item_number": "J.1",
        "confidence": 0.90,
    },
]


class TestNormalizeCommissionName:
    def test_exact_match(self):
        assert normalize_commission_name("Planning Commission") == "planning commission"

    def test_strips_prefix(self):
        assert normalize_commission_name("City of Richmond Planning Commission") == "planning commission"

    def test_strips_whitespace(self):
        assert normalize_commission_name("  Rent  Board  ") == "rent board"


class TestParseClaude Response:
    def test_valid_json(self):
        result = parse_claude_response(json.dumps(SAMPLE_CLAUDE_RESPONSE))
        assert len(result) == 2

    def test_strips_markdown_fences(self):
        wrapped = f"```json\n{json.dumps(SAMPLE_CLAUDE_RESPONSE)}\n```"
        result = parse_claude_response(wrapped)
        assert len(result) == 2

    def test_invalid_json_returns_empty(self):
        result = parse_claude_response("not json at all")
        assert result == []


class TestBuildAppointmentRecord:
    def test_basic_record(self):
        raw = SAMPLE_CLAUDE_RESPONSE[0]
        rec = build_appointment_record(raw, meeting_date="2025-09-23", city_fips="0660620")
        assert rec["name"] == "Jane Doe"
        assert rec["normalized_name"] == "jane doe"
        assert rec["commission_name"] == "Planning Commission"
        assert rec["action"] == "reappoint"
        assert rec["source"] == "council_minutes"
        assert rec["city_fips"] == "0660620"

    def test_appointment_record(self):
        raw = SAMPLE_CLAUDE_RESPONSE[1]
        rec = build_appointment_record(raw, meeting_date="2025-09-23", city_fips="0660620")
        assert rec["action"] == "appoint"
        assert rec["appointed_by"] == "Councilmember Brown"


class TestExtractAppointments:
    @patch("appointment_extractor.anthropic")
    def test_calls_claude_api(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(SAMPLE_CLAUDE_RESPONSE))]
        mock_msg.usage.input_tokens = 1000
        mock_msg.usage.output_tokens = 200
        mock_client.messages.create.return_value = mock_msg

        result = extract_appointments_from_meeting(SAMPLE_MEETING)
        assert len(result) == 2
        mock_client.messages.create.assert_called_once()

    @patch("appointment_extractor.anthropic")
    def test_skips_non_appointment_items(self, mock_anthropic):
        """Claude should only return appointment actions, not contracts."""
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        # Claude returns only the 2 appointments, not the contract
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(SAMPLE_CLAUDE_RESPONSE))]
        mock_msg.usage.input_tokens = 1000
        mock_msg.usage.output_tokens = 200
        mock_client.messages.create.return_value = mock_msg

        result = extract_appointments_from_meeting(SAMPLE_MEETING)
        actions = [r["action"] for r in result]
        assert "contract" not in actions
```

**Step 2: Run tests — expect FAIL**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_appointment_extractor.py -v
```

Expected: ModuleNotFoundError for `appointment_extractor`

**Step 3: Implement the extractor**

```python
# src/appointment_extractor.py
"""
Extract commission/board appointment actions from council meeting minutes.

Uses Claude API to identify appointment, reappointment, resignation, and
removal actions from already-extracted council meeting JSONs. These become
the authoritative (Tier 1) record of who sits on which commission.

Cost: ~$0.02 per meeting, ~$0.50 total for 21 meetings.

Usage:
    python appointment_extractor.py --meetings-dir src/data/extracted/   # All meetings
    python appointment_extractor.py --meeting src/data/extracted/FILE    # One meeting
    python appointment_extractor.py --output FILE                       # Save JSON
    python appointment_extractor.py --compare-website                   # Run staleness check
    python appointment_extractor.py --load                              # Load to DB
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import anthropic

logger = logging.getLogger(__name__)

CITY_FIPS = "0660620"

APPOINTMENT_SCHEMA = [
    {
        "person_name": "Full name of person being appointed/reappointed/resigned/removed",
        "commission_name": "Name of the commission or board",
        "action": "appoint | reappoint | resign | remove | confirm",
        "appointed_by": "Name of appointing official (e.g., 'Mayor Martinez', 'Councilmember Brown')",
        "term_end": "YYYY-MM-DD or null if not mentioned",
        "item_number": "Agenda item number where this action appears",
        "confidence": "0.0-1.0 confidence in extraction accuracy",
    }
]

SYSTEM_PROMPT = """You are a precise data extraction system for the Richmond Transparency Project.
Your job is to extract commission and board APPOINTMENT ACTIONS from city council meeting data.

Look for these action types:
- APPOINT: New appointment to a commission/board
- REAPPOINT: Renewal of existing appointment
- RESIGN: Resignation from a commission/board
- REMOVE: Removal from a commission/board
- CONFIRM: Council confirmation of an appointment

Only extract actions related to commissions, boards, and committees.
Do NOT extract employment actions (hiring, promotions) or contract approvals.
Do NOT extract council member elections or swearing-in ceremonies.

Return valid JSON array. If no appointment actions are found, return [].
"""


def normalize_commission_name(name: str) -> str:
    """Normalize a commission name for matching."""
    lower = " ".join(name.lower().strip().split())
    # Strip common prefixes
    for prefix in ["city of richmond ", "richmond ", "city of "]:
        if lower.startswith(prefix):
            lower = lower[len(prefix):]
    return lower


def _normalize_name(name: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return " ".join(name.lower().split())


def parse_claude_response(text: str) -> list[dict]:
    """Parse Claude's JSON response, handling markdown fences."""
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines)
    try:
        data = json.loads(clean)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        logger.error("Failed to parse Claude response as JSON")
        return []


def build_appointment_record(
    raw: dict,
    *,
    meeting_date: str,
    city_fips: str = CITY_FIPS,
) -> dict:
    """Build a full appointment record from Claude extraction output."""
    return {
        "city_fips": city_fips,
        "name": raw.get("person_name", ""),
        "normalized_name": _normalize_name(raw.get("person_name", "")),
        "commission_name": raw.get("commission_name", ""),
        "action": raw.get("action", ""),
        "appointed_by": raw.get("appointed_by"),
        "term_end": raw.get("term_end"),
        "item_number": raw.get("item_number"),
        "confidence": raw.get("confidence", 0.0),
        "meeting_date": meeting_date,
        "source": "council_minutes",
    }


def extract_appointments_from_meeting(meeting_data: dict) -> list[dict]:
    """Extract appointment actions from one meeting's JSON.

    Sends the meeting data to Claude API with a focused prompt.
    Returns list of appointment records.
    """
    meeting_date = meeting_data.get("meeting_date", "unknown")

    # Build a text representation of all agenda items
    items_text = []
    for section in ["consent_calendar", "action_items", "housing_authority_items"]:
        section_data = meeting_data.get(section, {})
        if isinstance(section_data, dict):
            section_items = section_data.get("items", [])
        elif isinstance(section_data, list):
            section_items = section_data
        else:
            continue

        for item in section_items:
            num = item.get("item_number", "?")
            title = item.get("title", "")
            desc = item.get("description", "")
            items_text.append(f"[{num}] {title}\n{desc}")

    if not items_text:
        return []

    prompt = f"""Extract all commission/board APPOINTMENT ACTIONS from the following council meeting agenda items.
Meeting date: {meeting_date}

Return a JSON array matching this schema:
{json.dumps(APPOINTMENT_SCHEMA, indent=2)}

If no appointment actions are found, return an empty array [].

Agenda items:
---
{chr(10).join(items_text)}
---

Return ONLY valid JSON. No explanation."""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text
    cost = (message.usage.input_tokens * 3 + message.usage.output_tokens * 15) / 1_000_000
    logger.info(
        "  Meeting %s: %d input + %d output tokens (~$%.4f)",
        meeting_date, message.usage.input_tokens, message.usage.output_tokens, cost,
    )

    raw_appointments = parse_claude_response(response_text)
    return [
        build_appointment_record(a, meeting_date=meeting_date)
        for a in raw_appointments
    ]


def extract_from_directory(
    meetings_dir: Path, *, city_fips: str = CITY_FIPS
) -> list[dict]:
    """Extract appointments from all meeting JSONs in a directory."""
    all_appointments = []
    json_files = sorted(meetings_dir.glob("*.json"))
    logger.info("Processing %d meeting files...", len(json_files))

    for f in json_files:
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError:
            logger.warning("Skipping invalid JSON: %s", f.name)
            continue

        appointments = extract_appointments_from_meeting(data)
        all_appointments.extend(appointments)
        if appointments:
            logger.info("  %s: %d appointments found", f.name, len(appointments))

    logger.info("Total: %d appointments from %d meetings", len(all_appointments), len(json_files))
    return all_appointments


def compare_with_website(
    appointments: list[dict],
    website_members: dict[str, list[dict]],
) -> list[dict]:
    """Compare minutes-derived appointments against website roster.

    Returns list of staleness findings.
    """
    findings = []
    for appt in appointments:
        if appt["action"] not in ("appoint", "reappoint", "confirm"):
            continue

        commission = appt["commission_name"]
        norm_commission = normalize_commission_name(commission)

        # Find matching commission in website data
        website_roster = None
        for wc_name, wc_members in website_members.items():
            if normalize_commission_name(wc_name) == norm_commission:
                website_roster = wc_members
                break

        if website_roster is None:
            continue  # Commission not scraped

        # Check if this person is on the website roster
        website_names = {m["normalized_name"] for m in website_roster}
        if appt["normalized_name"] not in website_names:
            findings.append({
                "type": "member_not_on_website",
                "commission": commission,
                "member": appt["name"],
                "appointed_date": appt["meeting_date"],
                "action": appt["action"],
            })

    return findings


def load_to_db(appointments: list[dict], *, city_fips: str = CITY_FIPS) -> None:
    """Load extracted appointments to Supabase commission_members table."""
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            loaded = 0
            for appt in appointments:
                if appt["action"] in ("resign", "remove"):
                    # Mark member as no longer current
                    cur.execute(
                        """UPDATE commission_members
                           SET is_current = FALSE, updated_at = NOW()
                           WHERE city_fips = %s
                             AND normalized_name = %s
                             AND commission_id IN (
                                 SELECT id FROM commissions
                                 WHERE city_fips = %s AND LOWER(name) = LOWER(%s)
                             )""",
                        (city_fips, appt["normalized_name"], city_fips, appt["commission_name"]),
                    )
                else:
                    # Find the commission
                    cur.execute(
                        "SELECT id FROM commissions WHERE city_fips = %s AND LOWER(name) = LOWER(%s)",
                        (city_fips, appt["commission_name"]),
                    )
                    row = cur.fetchone()
                    if not row:
                        logger.warning("Commission '%s' not in DB", appt["commission_name"])
                        continue
                    commission_id = row[0]

                    cur.execute(
                        """INSERT INTO commission_members
                           (city_fips, commission_id, name, normalized_name, role,
                            appointed_by, term_end, is_current, source)
                           VALUES (%s, %s, %s, %s, 'member', %s, %s, TRUE, 'council_minutes')
                           ON CONFLICT ON CONSTRAINT uq_commission_member
                           DO UPDATE SET
                               appointed_by = EXCLUDED.appointed_by,
                               term_end = EXCLUDED.term_end,
                               is_current = TRUE,
                               source = 'council_minutes',
                               updated_at = NOW()""",
                        (
                            city_fips, commission_id, appt["name"],
                            appt["normalized_name"], appt["appointed_by"],
                            appt["term_end"],
                        ),
                    )
                loaded += 1

            conn.commit()
        logger.info("Loaded %d appointment records to database", loaded)
    finally:
        conn.close()


# ── CLI ─────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract commission appointments from council meeting minutes"
    )
    parser.add_argument("--meetings-dir", type=Path, help="Directory of extracted meeting JSONs")
    parser.add_argument("--meeting", type=Path, help="Single meeting JSON file")
    parser.add_argument("--output", type=Path, help="Save extracted appointments JSON")
    parser.add_argument("--compare-website", type=Path, help="Website roster JSON for staleness check")
    parser.add_argument("--load", action="store_true", help="Load to Supabase")
    parser.add_argument("--city-fips", default=None, help="City FIPS code")
    args = parser.parse_args()

    fips = args.city_fips or CITY_FIPS
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.meeting:
        data = json.loads(args.meeting.read_text())
        appointments = extract_appointments_from_meeting(data)
    elif args.meetings_dir:
        appointments = extract_from_directory(args.meetings_dir, city_fips=fips)
    else:
        parser.print_help()
        return

    # Print summary
    print(f"\nExtracted {len(appointments)} appointment actions:")
    for a in appointments:
        print(f"  [{a['action']:10s}] {a['name']:25s} → {a['commission_name']:30s} (by {a.get('appointed_by', 'N/A')})")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(appointments, indent=2, default=str))
        logger.info("Saved to %s", args.output)

    if args.compare_website:
        website_data = json.loads(args.compare_website.read_text())
        findings = compare_with_website(appointments, website_data)
        if findings:
            print(f"\nStaleness findings ({len(findings)}):")
            for f in findings:
                print(f"  {f['commission']:30s} — {f['member']} ({f['action']} on {f['appointed_date']}) NOT on website")
        else:
            print("\nNo staleness findings — website roster matches minutes.")

    if args.load:
        load_to_db(appointments, city_fips=fips)


if __name__ == "__main__":
    main()
```

**Step 4: Run tests — expect PASS**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_appointment_extractor.py -v
```

Expected: All PASSED

**Step 5: Commit**

```bash
git add src/appointment_extractor.py tests/test_appointment_extractor.py
git commit -m "feat: add appointment extractor with Claude API for commission membership mining"
```

---

### Task 6: Appointment Extractor — Staleness Comparison Tests

**Files:**
- Modify: `tests/test_appointment_extractor.py`

**Step 1: Add staleness comparison tests**

Append to the test file:

```python
class TestCompareWithWebsite:
    def test_finds_missing_member(self):
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "Planning Commission",
                "action": "appoint",
                "meeting_date": "2025-09-23",
            }
        ]
        website = {
            "Planning Commission": [
                {"name": "Bob Jones", "normalized_name": "bob jones", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 1
        assert findings[0]["member"] == "Jane Doe"
        assert findings[0]["type"] == "member_not_on_website"

    def test_no_finding_when_present(self):
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "Planning Commission",
                "action": "appoint",
                "meeting_date": "2025-09-23",
            }
        ]
        website = {
            "Planning Commission": [
                {"name": "Jane Doe", "normalized_name": "jane doe", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 0

    def test_ignores_resignation_actions(self):
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "Planning Commission",
                "action": "resign",
                "meeting_date": "2025-09-23",
            }
        ]
        website = {
            "Planning Commission": [
                {"name": "Jane Doe", "normalized_name": "jane doe", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 0  # Resignations don't generate staleness flags

    def test_handles_commission_name_normalization(self):
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "City of Richmond Planning Commission",
                "action": "appoint",
                "meeting_date": "2025-09-23",
            }
        ]
        website = {
            "Planning Commission": [
                {"name": "Bob Jones", "normalized_name": "bob jones", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 1  # Should match despite "City of Richmond" prefix
```

**Step 2: Run tests — expect PASS**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_appointment_extractor.py -v
```

Expected: All PASSED (previous + new tests)

**Step 3: Commit**

```bash
git add tests/test_appointment_extractor.py
git commit -m "test: add staleness comparison tests for appointment extractor"
```

---

## Sub-Phase B3: eSCRIBE Commission Meeting Discovery

### Task 7: Extend eSCRIBE Scraper with `--discover-types`

**Files:**
- Modify: `src/escribemeetings_scraper.py`
- Create: `tests/test_escribemeetings_discover_types.py`

**Step 1: Write failing tests**

```python
# tests/test_escribemeetings_discover_types.py
"""Tests for eSCRIBE meeting type discovery."""
from escribemeetings_scraper import discover_meeting_types


# ── Sample meeting data (from discover_meetings) ─────────────
SAMPLE_MEETINGS = [
    {"ID": "guid1", "MeetingName": "City Council", "StartDate": "2025/01/07 18:30:00"},
    {"ID": "guid2", "MeetingName": "City Council", "StartDate": "2025/01/21 18:30:00"},
    {"ID": "guid3", "MeetingName": "Planning Commission", "StartDate": "2025/01/16 18:00:00"},
    {"ID": "guid4", "MeetingName": "Planning Commission", "StartDate": "2025/02/06 18:00:00"},
    {"ID": "guid5", "MeetingName": "Planning Commission", "StartDate": "2025/03/06 18:00:00"},
    {"ID": "guid6", "MeetingName": "Richmond Rent Board", "StartDate": "2025/01/15 17:00:00"},
    {"ID": "guid7", "MeetingName": "Special City Council", "StartDate": "2025/02/03 17:00:00"},
    {"ID": "guid8", "MeetingName": "Design Review Board", "StartDate": "2025/01/22 17:30:00"},
]


class TestDiscoverMeetingTypes:
    def test_counts_by_type(self):
        result = discover_meeting_types(SAMPLE_MEETINGS)
        assert result["City Council"]["count"] == 2
        assert result["Planning Commission"]["count"] == 3

    def test_includes_date_range(self):
        result = discover_meeting_types(SAMPLE_MEETINGS)
        pc = result["Planning Commission"]
        assert pc["first_date"] == "2025-01-16"
        assert pc["last_date"] == "2025-03-06"

    def test_all_types_present(self):
        result = discover_meeting_types(SAMPLE_MEETINGS)
        assert len(result) == 5
        assert "Richmond Rent Board" in result
        assert "Design Review Board" in result

    def test_empty_input(self):
        result = discover_meeting_types([])
        assert result == {}

    def test_single_meeting_type(self):
        result = discover_meeting_types([SAMPLE_MEETINGS[0]])
        assert result["City Council"]["count"] == 1
        assert result["City Council"]["first_date"] == result["City Council"]["last_date"]
```

**Step 2: Run tests — expect FAIL**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_escribemeetings_discover_types.py -v
```

Expected: ImportError for `discover_meeting_types`

**Step 3: Add `discover_meeting_types` function to `escribemeetings_scraper.py`**

Add this function after the existing `find_meeting_by_date` function (~line 213):

```python
def discover_meeting_types(meetings: list[dict]) -> dict[str, dict]:
    """Catalog all unique meeting types with counts and date ranges.

    Useful for discovering which commissions have eSCRIBE agendas.

    Args:
        meetings: List of meeting dicts from discover_meetings().

    Returns:
        Dict mapping meeting type name to {count, first_date, last_date, sample_ids}.
    """
    types: dict[str, dict] = {}

    for m in meetings:
        name = m.get("MeetingName", "Unknown")
        start = m.get("StartDate", "")
        meeting_date = start.split(" ")[0].replace("/", "-") if start else ""
        guid = m.get("ID", "")

        if name not in types:
            types[name] = {
                "count": 0,
                "first_date": meeting_date,
                "last_date": meeting_date,
                "sample_ids": [],
            }

        types[name]["count"] += 1
        if meeting_date and meeting_date < types[name]["first_date"]:
            types[name]["first_date"] = meeting_date
        if meeting_date and meeting_date > types[name]["last_date"]:
            types[name]["last_date"] = meeting_date
        if len(types[name]["sample_ids"]) < 3:
            types[name]["sample_ids"].append(guid)

    return types
```

Also add `--discover-types` to the existing CLI in `main()`. Find the argparse section and add:

```python
parser.add_argument("--discover-types", action="store_true",
                    help="List all unique meeting types with counts and date ranges")
```

And add the handler in the CLI logic:

```python
if args.discover_types:
    session = create_session(city_fips=args.city_fips)
    meetings = discover_meetings(session, city_fips=args.city_fips)
    types = discover_meeting_types(meetings)
    print(f"\nMeeting Types ({len(types)}):")
    print(f"{'Type':40s} {'Count':>6s}  {'First':>12s}  {'Last':>12s}")
    print("-" * 76)
    for name, info in sorted(types.items(), key=lambda x: -x[1]["count"]):
        print(f"{name:40s} {info['count']:>6d}  {info['first_date']:>12s}  {info['last_date']:>12s}")
    return
```

**Step 4: Run tests — expect PASS**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_escribemeetings_discover_types.py -v
```

Expected: All PASSED

**Step 5: Commit**

```bash
git add src/escribemeetings_scraper.py tests/test_escribemeetings_discover_types.py
git commit -m "feat: add --discover-types to eSCRIBE scraper for commission meeting cataloging"
```

---

### Task 8: Commission Type Registry in City Config

**Files:**
- Modify: `src/city_config.py`
- Modify: `tests/test_commission_roster_scraper.py` (add config resolution test)

**Step 1: Add `commissions_escribemeetings` to Richmond's city config**

In `src/city_config.py`, inside the `"0660620"` entry's `"data_sources"` dict, add:

```python
"commissions_escribemeetings": {
    "Planning Commission": "Planning Commission",
    "Rent Board": "Richmond Rent Board",
    "Design Review Board": "Design Review Board",
    "Police Commission": "Police Commission",
    "Housing Authority": "Housing Authority Board of Commissioners",
    # Map: canonical name → eSCRIBE MeetingName value
    # Run: python escribemeetings_scraper.py --discover-types
    # to find the exact MeetingName strings for each commission.
},
```

**Step 2: Add a test for config resolution**

Append to `tests/test_commission_roster_scraper.py`:

```python
class TestCityConfigIntegration:
    def test_commissions_escribemeetings_config_exists(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        sources = cfg["data_sources"]
        assert "commissions_escribemeetings" in sources

    def test_mapping_has_planning_commission(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        mapping = cfg["data_sources"]["commissions_escribemeetings"]
        assert "Planning Commission" in mapping
```

**Step 3: Run tests — expect PASS**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_commission_roster_scraper.py::TestCityConfigIntegration -v
```

Expected: 2 PASSED

**Step 4: Commit**

```bash
git add src/city_config.py tests/test_commission_roster_scraper.py
git commit -m "feat: add commissions_escribemeetings registry to city config"
```

---

### Task 9: Update Migration Health Check

**Files:**
- Modify: `web/src/app/api/health/route.ts`
- Modify: `src/staleness_monitor.py`

**Step 1: Add migration group to health endpoint**

In `web/src/app/api/health/route.ts`, add after the `003_nextrequest` entry in `MIGRATION_GROUPS`:

```typescript
{
  name: '005_commissions',
  tables: ['commissions', 'commission_members'],
},
```

**Step 2: Add to `staleness_monitor.py`'s `EXPECTED_TABLES`**

In `src/staleness_monitor.py`, add to the `EXPECTED_TABLES` dict:

```python
"005_commissions": ["commissions", "commission_members"],
```

**Step 3: Run existing health check tests**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/ -k "health" -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add web/src/app/api/health/route.ts src/staleness_monitor.py
git commit -m "feat: add commissions to migration health check"
```

---

### Task 10: End-to-End Integration Test + Summary

**Step 1: Run eSCRIBE discovery to map meeting types**

```bash
cd src && python escribemeetings_scraper.py --discover-types
```

This prints all meeting types found in eSCRIBE. Verify that the `commissions_escribemeetings` mapping in `city_config.py` uses the exact `MeetingName` values from this output. Update if needed.

**Step 2: Run the roster scraper against one real commission**

```bash
cd src && python commission_roster_scraper.py --inspect --url "URL_FROM_OFFICIALS_JSON"
```

Verify members are parsed correctly.

**Step 3: Test appointment extraction on one meeting**

```bash
cd src && python appointment_extractor.py --meeting data/extracted/SAMPLE_MEETING.json --output ../data/test_appointments.json
```

Verify appointments are extracted correctly. Cost: ~$0.02.

**Step 4: Run full test suite**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/ -v --tb=short
```

Expected: All tests PASS

**Step 5: Clean up test artifacts**

```bash
rm -f data/test_appointments.json
```

**New files created:**
- `src/migrations/005_commissions.sql`
- `src/commission_roster_scraper.py`
- `src/appointment_extractor.py`
- `tests/test_migration_005.py`
- `tests/test_commission_roster_scraper.py`
- `tests/test_appointment_extractor.py`
- `tests/test_escribemeetings_discover_types.py`

**Modified files:**
- `src/ground_truth/officials.json` (commissions section)
- `src/escribemeetings_scraper.py` (discover_meeting_types + CLI flag)
- `src/city_config.py` (commissions_escribemeetings mapping)
- `web/src/app/api/health/route.ts` (migration group)
- `src/staleness_monitor.py` (schema health)

**Cost:** ~$0.50 (Claude API for appointment extraction of 21 meetings). Website scraping and eSCRIBE discovery are $0.
