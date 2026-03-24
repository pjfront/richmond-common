"""
Richmond Common — Election Cycle Tracking Client (B.24)

Derives election cycle data from existing pipeline outputs (committees,
contributions, officials). Does NOT scrape external sources directly —
it assembles relationships from data already in the database.

Key operations:
  1. Extract election year and office from committee names
  2. Build election_candidates records from committee → official linkages
  3. Assign committees and contributions to election cycles
  4. Compute per-candidate fundraising summaries

Usage:
    # Build candidates from existing committee data
    python elections_client.py --build-candidates

    # Assign contributions to election cycles
    python elections_client.py --assign-contributions

    # Show fundraising summary for an election
    python elections_client.py --summary --election-date 2026-06-02

    # Full pipeline (all steps)
    python elections_client.py --full
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Reuse proven extraction and matching logic from wire_committees
from wire_committees import (
    extract_candidate_from_committee,
    match_candidate_to_official,
    normalize_name,
    _is_plausible_person_name,
)

RICHMOND_FIPS = "0660620"


# ── Extraction helpers ──────────────────────────────────────


def extract_election_year(committee_name: str) -> int | None:
    """Extract 4-digit election year from a committee name.

    Examples:
        "Eduardo Martinez for Richmond Mayor 2022" → 2022
        "Friends of Tom Butt for Richmond City Council 2016" → 2016
        "BECKLES FOR ASSEMBLY 2018, JOVANKA" → 2018
        "Richmond Progressive Alliance PAC" → None
    """
    # Look for 4-digit year (2000-2099) — take the LAST one if multiple
    matches = re.findall(r'\b(20\d{2})\b', committee_name)
    if matches:
        return int(matches[-1])
    return None


def extract_office_sought(committee_name: str) -> str | None:
    """Extract the office from a committee name.

    Focuses on Richmond city-level offices. Returns None for
    state/federal offices or unparseable names.

    Examples:
        "Eduardo Martinez for Richmond Mayor 2022" → "Mayor"
        "Andrew Butt for Richmond City Council District 2 2022" → "City Council District 2"
        "Sue Wilson for 2024 Richmond City Council District 5" → "City Council District 5"
        "BECKLES FOR ASSEMBLY 2018" → None (state-level)
        "Richmond Progressive Alliance PAC" → None
    """
    norm = committee_name.strip()

    # Pattern: "for [Richmond] [Office] [District N] [Year]"
    m = re.search(
        r'\bfor\b\s+(?:\d{4}\s+)?(?:richmond\s+)?'
        r'(mayor|city\s+council(?:\s+district\s+\d+)?|'
        r'city\s+treasurer|city\s+auditor|city\s+clerk)',
        norm,
        re.IGNORECASE,
    )
    if m:
        office = m.group(1).strip()
        # Normalize casing
        office = re.sub(r'\s+', ' ', office).title()
        return office

    # Also check "4" as alternate spelling of "for"
    m = re.search(
        r'\b4\b\s+(?:\d{4}\s+)?(?:richmond\s+)?'
        r'(mayor|city\s+council(?:\s+district\s+\d+)?)',
        norm,
        re.IGNORECASE,
    )
    if m:
        office = m.group(1).strip()
        office = re.sub(r'\s+', ' ', office).title()
        return office

    return None


# Richmond city-level offices — used to filter out state/federal candidates
_CITY_OFFICES = {
    'mayor', 'city council', 'city treasurer', 'city auditor', 'city clerk',
}


def _is_city_level_office(office: str | None) -> bool:
    """Check if an extracted office is a Richmond city-level position."""
    if not office:
        return False
    norm = office.lower().strip()
    return any(norm.startswith(o) for o in _CITY_OFFICES)


# ── Core pipeline functions ─────────────────────────────────


def build_candidates_from_committees(
    conn,
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Scan all committees, extract candidate info, populate election_candidates.

    Pipeline:
    1. Load all committees with their candidate_name/official_id (from wire_committees)
    2. Extract election year and office from committee name
    3. Match to election record by year + city_fips
    4. Upsert into election_candidates

    Returns stats dict.
    """
    cur = conn.cursor()

    # Load elections for this city (keyed by year for matching)
    cur.execute(
        """SELECT id, election_date, election_type
           FROM elections WHERE city_fips = %s
           ORDER BY election_date""",
        (city_fips,),
    )
    elections_by_year: dict[int, list[tuple]] = {}
    for eid, edate, etype in cur.fetchall():
        year = edate.year
        elections_by_year.setdefault(year, []).append((eid, edate, etype))

    if not elections_by_year:
        print("  No elections found — seed elections table first")
        return {"candidates_created": 0, "candidates_updated": 0, "skipped": 0}

    # Load all committees for this city
    cur.execute(
        """SELECT id, name, candidate_name, official_id, filer_id
           FROM committees WHERE city_fips = %s""",
        (city_fips,),
    )
    committees = cur.fetchall()

    # Load officials for matching (if wire_committees hasn't run yet)
    cur.execute(
        """SELECT id, name, normalized_name, role, is_current
           FROM officials WHERE city_fips = %s""",
        (city_fips,),
    )
    officials_raw = cur.fetchall()
    officials = []
    for row in officials_raw:
        officials.append({
            'id': row[0],
            'name': row[1],
            'normalized': normalize_name(row[1]),
            'role': row[3],
            'is_current': row[4],
        })

    stats = {"candidates_created": 0, "candidates_updated": 0, "skipped": 0}

    for comm_id, comm_name, existing_candidate, existing_official_id, filer_id in committees:
        # Extract candidate name (use wire_committees result if available)
        candidate = existing_candidate or extract_candidate_from_committee(comm_name)
        if not candidate or not _is_plausible_person_name(candidate):
            stats["skipped"] += 1
            continue

        # Extract election year and office
        year = extract_election_year(comm_name)
        office = extract_office_sought(comm_name)

        if not year:
            # Try to infer from contribution dates as fallback
            cur.execute(
                """SELECT EXTRACT(YEAR FROM MIN(contribution_date))::int,
                          EXTRACT(YEAR FROM MAX(contribution_date))::int
                   FROM contributions WHERE committee_id = %s""",
                (str(comm_id),),
            )
            row = cur.fetchone()
            if row and row[1]:
                # Use the max year (most recent contribution year = likely election year)
                # But only if it's an even year (elections are even years in CA)
                max_year = row[1]
                if max_year % 2 == 0:
                    year = max_year
                elif row[0] and row[0] % 2 == 0:
                    year = row[0]

        if not year or year not in elections_by_year:
            stats["skipped"] += 1
            continue

        # Skip state/federal offices
        if office and not _is_city_level_office(office):
            stats["skipped"] += 1
            continue

        # Default office if not extractable (most Richmond committees are for council)
        if not office:
            office = "City Council"

        # Find best matching election for this year
        # Prefer general election if no primary exists
        year_elections = elections_by_year[year]
        election_id = year_elections[0][0]  # Default to first
        for eid, edate, etype in year_elections:
            if etype == 'general':
                election_id = eid
                break

        # Match to official
        official_id = existing_official_id
        if not official_id:
            match = match_candidate_to_official(candidate, officials)
            if match:
                official_id = match['id']

        # Check incumbency
        is_incumbent = False
        if official_id:
            cur.execute(
                "SELECT is_current FROM officials WHERE id = %s",
                (str(official_id),),
            )
            row = cur.fetchone()
            if row:
                is_incumbent = bool(row[0])

        # Upsert election_candidates
        norm_candidate = normalize_name(candidate)
        cur.execute(
            """INSERT INTO election_candidates
               (city_fips, election_id, official_id, candidate_name, normalized_name,
                office_sought, fppc_id, committee_id, status, is_incumbent, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'filed', %s, 'netfile')
               ON CONFLICT (city_fips, election_id, normalized_name, office_sought)
               DO UPDATE SET
                 official_id = COALESCE(EXCLUDED.official_id, election_candidates.official_id),
                 fppc_id = COALESCE(EXCLUDED.fppc_id, election_candidates.fppc_id),
                 committee_id = COALESCE(EXCLUDED.committee_id, election_candidates.committee_id),
                 is_incumbent = EXCLUDED.is_incumbent,
                 updated_at = NOW()
               RETURNING (xmax = 0) AS is_insert""",
            (city_fips, str(election_id), str(official_id) if official_id else None,
             candidate, norm_candidate, office, filer_id or None, str(comm_id),
             is_incumbent),
        )
        row = cur.fetchone()
        if row and row[0]:
            stats["candidates_created"] += 1
        else:
            stats["candidates_updated"] += 1

    conn.commit()
    return stats


def assign_committees_to_elections(
    conn,
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Set election_id on committees by matching extracted year.

    Returns stats dict.
    """
    cur = conn.cursor()

    # Load elections keyed by year
    cur.execute(
        """SELECT id, EXTRACT(YEAR FROM election_date)::int AS year, election_type
           FROM elections WHERE city_fips = %s""",
        (city_fips,),
    )
    elections_by_year: dict[int, uuid.UUID] = {}
    for eid, year, etype in cur.fetchall():
        # Prefer general election for a given year
        if year not in elections_by_year or etype == 'general':
            elections_by_year[year] = eid

    # Load committees without election_id
    cur.execute(
        """SELECT id, name FROM committees
           WHERE city_fips = %s AND election_id IS NULL""",
        (city_fips,),
    )
    committees = cur.fetchall()

    stats = {"assigned": 0, "skipped": 0}

    for comm_id, comm_name in committees:
        year = extract_election_year(comm_name)
        if not year or year not in elections_by_year:
            # Fallback: infer from contribution dates
            cur.execute(
                """SELECT EXTRACT(YEAR FROM MAX(contribution_date))::int
                   FROM contributions WHERE committee_id = %s""",
                (str(comm_id),),
            )
            row = cur.fetchone()
            if row and row[0]:
                max_year = row[0]
                # Check even year (CA elections) and within known elections
                if max_year % 2 == 0 and max_year in elections_by_year:
                    year = max_year

        if not year or year not in elections_by_year:
            stats["skipped"] += 1
            continue

        cur.execute(
            "UPDATE committees SET election_id = %s WHERE id = %s",
            (str(elections_by_year[year]), str(comm_id)),
        )
        stats["assigned"] += 1

    conn.commit()
    return stats


def assign_contributions_to_elections(
    conn,
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Assign election_id to contributions.

    Strategy 1: Propagate election_id from committee.
    Strategy 2: Date-range heuristic — contributions within 24 months before
    an election are assigned to that cycle.

    Returns stats dict.
    """
    cur = conn.cursor()

    # Strategy 1: From committee election_id
    cur.execute(
        """UPDATE contributions c
           SET election_id = cm.election_id
           FROM committees cm
           WHERE c.committee_id = cm.id
             AND c.city_fips = %s
             AND c.election_id IS NULL
             AND cm.election_id IS NOT NULL""",
        (city_fips,),
    )
    from_committee = cur.rowcount
    print(f"  Contributions assigned from committee: {from_committee:,}")

    # Strategy 2: Date-range heuristic for remaining unlinked contributions
    # For each election, assign contributions dated within 24 months before election_date
    cur.execute(
        """SELECT id, election_date FROM elections
           WHERE city_fips = %s
           ORDER BY election_date DESC""",
        (city_fips,),
    )
    elections = cur.fetchall()

    from_date_range = 0
    for election_id, election_date in elections:
        cur.execute(
            """UPDATE contributions
               SET election_id = %s
               WHERE city_fips = %s
                 AND election_id IS NULL
                 AND contribution_date IS NOT NULL
                 AND contribution_date <= %s
                 AND contribution_date > %s - INTERVAL '24 months'""",
            (str(election_id), city_fips, election_date, election_date),
        )
        from_date_range += cur.rowcount

    print(f"  Contributions assigned from date range: {from_date_range:,}")

    conn.commit()
    return {
        "from_committee": from_committee,
        "from_date_range": from_date_range,
        "total_assigned": from_committee + from_date_range,
    }


def get_election_fundraising_summary(
    conn,
    election_id: str,
    city_fips: str = RICHMOND_FIPS,
) -> list[dict]:
    """Get per-candidate fundraising totals for an election.

    Returns list sorted by total_raised descending:
        [{candidate_name, office_sought, is_incumbent, status,
          total_raised, contribution_count, donor_count,
          avg_contribution, largest_contribution, smallest_contribution}]
    """
    cur = conn.cursor()

    cur.execute(
        """SELECT
             ec.candidate_name,
             ec.office_sought,
             ec.is_incumbent,
             ec.status,
             COALESCE(SUM(c.amount), 0) AS total_raised,
             COUNT(c.id) AS contribution_count,
             COUNT(DISTINCT c.donor_id) AS donor_count,
             COALESCE(AVG(c.amount), 0) AS avg_contribution,
             COALESCE(MAX(c.amount), 0) AS largest_contribution,
             COALESCE(MIN(c.amount), 0) AS smallest_contribution
           FROM election_candidates ec
           LEFT JOIN contributions c
             ON c.committee_id = ec.committee_id
             AND c.city_fips = ec.city_fips
           WHERE ec.election_id = %s
             AND ec.city_fips = %s
           GROUP BY ec.id, ec.candidate_name, ec.office_sought,
                    ec.is_incumbent, ec.status
           ORDER BY total_raised DESC""",
        (election_id, city_fips),
    )

    columns = [
        'candidate_name', 'office_sought', 'is_incumbent', 'status',
        'total_raised', 'contribution_count', 'donor_count',
        'avg_contribution', 'largest_contribution', 'smallest_contribution',
    ]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_candidate_top_donors(
    conn,
    election_candidate_id: str,
    limit: int = 10,
) -> list[dict]:
    """Get top donors for a specific candidate in an election."""
    cur = conn.cursor()

    cur.execute(
        """SELECT d.name, d.employer, SUM(c.amount) AS total,
                  COUNT(c.id) AS contribution_count
           FROM election_candidates ec
           JOIN contributions c ON c.committee_id = ec.committee_id
                                AND c.city_fips = ec.city_fips
           JOIN donors d ON d.id = c.donor_id
           WHERE ec.id = %s
           GROUP BY d.id, d.name, d.employer
           ORDER BY total DESC
           LIMIT %s""",
        (election_candidate_id, limit),
    )

    return [
        {
            'donor_name': row[0],
            'employer': row[1],
            'total_contributed': float(row[2]),
            'contribution_count': row[3],
        }
        for row in cur.fetchall()
    ]


# ── Full pipeline ───────────────────────────────────────────


def run_election_pipeline(
    conn,
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Run the full election cycle tracking pipeline.

    Steps:
    1. Build candidates from committee data
    2. Assign committees to elections
    3. Assign contributions to elections

    Returns combined stats.
    """
    print("Step 1: Building candidates from committees...")
    candidate_stats = build_candidates_from_committees(conn, city_fips)
    print(f"  Created: {candidate_stats['candidates_created']}, "
          f"Updated: {candidate_stats['candidates_updated']}, "
          f"Skipped: {candidate_stats['skipped']}")

    print("\nStep 2: Assigning committees to elections...")
    committee_stats = assign_committees_to_elections(conn, city_fips)
    print(f"  Assigned: {committee_stats['assigned']}, "
          f"Skipped: {committee_stats['skipped']}")

    print("\nStep 3: Assigning contributions to elections...")
    contribution_stats = assign_contributions_to_elections(conn, city_fips)
    print(f"  Total assigned: {contribution_stats['total_assigned']:,}")

    return {
        "candidates": candidate_stats,
        "committees": committee_stats,
        "contributions": contribution_stats,
    }


# ── CLI ─────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Richmond Common — Election Cycle Tracking"
    )
    parser.add_argument("--city-fips", default=RICHMOND_FIPS)
    parser.add_argument("--build-candidates", action="store_true",
                        help="Build election_candidates from committee data")
    parser.add_argument("--assign-contributions", action="store_true",
                        help="Assign contributions to election cycles")
    parser.add_argument("--summary", action="store_true",
                        help="Show fundraising summary")
    parser.add_argument("--election-date",
                        help="Election date for --summary (YYYY-MM-DD)")
    parser.add_argument("--full", action="store_true",
                        help="Run full election pipeline")

    args = parser.parse_args()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    if args.full:
        stats = run_election_pipeline(conn, args.city_fips)
        print(f"\n{'='*60}")
        print("Election pipeline complete.")
        print(f"{'='*60}")
        conn.close()
        return

    if args.build_candidates:
        stats = build_candidates_from_committees(conn, args.city_fips)
        print(f"Candidates — created: {stats['candidates_created']}, "
              f"updated: {stats['candidates_updated']}, "
              f"skipped: {stats['skipped']}")

    if args.assign_contributions:
        assign_committees_to_elections(conn, args.city_fips)
        stats = assign_contributions_to_elections(conn, args.city_fips)
        print(f"Contributions assigned: {stats['total_assigned']:,}")

    if args.summary:
        if not args.election_date:
            print("ERROR: --election-date required with --summary")
            sys.exit(1)

        cur = conn.cursor()
        cur.execute(
            """SELECT id, election_name FROM elections
               WHERE city_fips = %s AND election_date = %s""",
            (args.city_fips, args.election_date),
        )
        rows = cur.fetchall()
        if not rows:
            print(f"No election found for {args.election_date}")
            sys.exit(1)

        for election_id, election_name in rows:
            summary = get_election_fundraising_summary(conn, str(election_id), args.city_fips)
            print(f"\n{'='*60}")
            print(f"{election_name}")
            print(f"{'='*60}")
            if not summary:
                print("  No candidates linked yet.")
                continue
            for c in summary:
                inc = " (incumbent)" if c['is_incumbent'] else ""
                print(f"\n  {c['candidate_name']}{inc} — {c['office_sought']}")
                print(f"    Total raised:   ${c['total_raised']:>12,.2f}")
                print(f"    Contributions:  {c['contribution_count']:>8,}")
                print(f"    Unique donors:  {c['donor_count']:>8,}")
                print(f"    Avg donation:   ${c['avg_contribution']:>12,.2f}")
                print(f"    Largest:        ${c['largest_contribution']:>12,.2f}")

    conn.close()


if __name__ == "__main__":
    main()
