"""
Spot-check donor data for an official against NetFile, the upstream truth.

Background (2026-04-26): The first organic public reader of the site
(Leisa Johnson) flagged Claudia Jimenez's 2024 contributions as
"inaccurate." We've hidden donations from public view (S24.25) until
we verify ingestion accuracy. This script makes the spot-check fast.

For a given official (or all current council), it prints:
  - Every committee linked to them
  - Per-committee: contribution count, total raised, date range, top 5 donors
  - Direct NetFile portal URL for each committee, so the operator can
    pull the same view and compare line by line
  - A diff-friendly summary at the bottom

The operator opens each NetFile URL, eyeballs the totals, and either
marks the data verified or flags discrepancies for a deeper look.

Usage:
  python verify_donor_data.py --name "Claudia Jimenez"
  python verify_donor_data.py --all-current     # all 7 council members
  python verify_donor_data.py --slug claudia-jimenez

Output goes to stdout; pipe through `tee` to save a record of what
was checked when.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

RICHMOND_FIPS = "0660620"
NETFILE_FILER_URL = "https://public.netfile.com/pub2/?aid=RICH#/filer/"


def _fmt_money(amount: float | None) -> str:
    if amount is None:
        return "$0"
    return f"${amount:,.0f}"


def _print_committee_card(cur, comm_id, comm_name, filer_id, comm_status, election_name):
    """Print a structured per-committee report card."""
    cur.execute(
        """SELECT COUNT(*),
                  SUM(amount),
                  MIN(contribution_date),
                  MAX(contribution_date)
           FROM contributions WHERE committee_id = %s
        """,
        (comm_id,),
    )
    n_contribs, total, first_d, last_d = cur.fetchone()

    cur.execute(
        """SELECT d.name, SUM(c.amount) AS total, COUNT(*) AS n
           FROM contributions c
           JOIN donors d ON d.id = c.donor_id
           WHERE c.committee_id = %s
           GROUP BY d.name
           ORDER BY total DESC
           LIMIT 5
        """,
        (comm_id,),
    )
    top_donors = cur.fetchall()

    cur.execute(
        """SELECT d.name, c.contribution_date, c.amount, c.schedule
           FROM contributions c
           JOIN donors d ON d.id = c.donor_id
           WHERE c.committee_id = %s
           ORDER BY c.contribution_date DESC
           LIMIT 3
        """,
        (comm_id,),
    )
    most_recent = cur.fetchall()

    print(f"\n  ── {comm_name} ──")
    print(f"     committee_id: {comm_id}")
    print(f"     filer_id:     {filer_id}")
    print(f"     status:       {comm_status}")
    print(f"     election:     {election_name or '(unlinked)'}")
    print(f"     NetFile portal: {NETFILE_FILER_URL}{filer_id}")
    print()
    print(f"     Our DB summary (what the site shows when un-hidden):")
    print(f"       contributions:     {n_contribs}")
    print(f"       total raised:      {_fmt_money(total)}")
    print(f"       date range:        {first_d} to {last_d}")
    print()
    if top_donors:
        print(f"     Top 5 donors (by total):")
        for name, donor_total, donor_n in top_donors:
            print(f"       {_fmt_money(donor_total):>10}  ({donor_n}x)  {name}")
        print()
    if most_recent:
        print(f"     Most recent 3 contributions (sanity check the latest filing):")
        for name, date, amt, form in most_recent:
            print(f"       {date}  {_fmt_money(amt):>8}  {form or '?':<8}  {name}")

    print()
    print(f"     >>> COMPARE: open the NetFile URL above. On NetFile,")
    print(f"     >>> click 'Transactions' tab. Confirm:")
    print(f"     >>>   1. Total dollar amount matches our {_fmt_money(total)}")
    print(f"     >>>   2. Contribution count is close to our {n_contribs} (small")
    print(f"     >>>      differences from amended forms are normal)")
    print(f"     >>>   3. Top donor names look right")
    print(f"     >>>   4. Most recent contributions appear (no big lag)")


def verify_official(name: str | None = None, slug: str | None = None) -> None:
    """Print donor verification card for one official."""
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if slug:
                cur.execute(
                    """SELECT id, name FROM officials
                       WHERE city_fips = %s AND LOWER(REPLACE(name, ' ', '-')) = %s
                       LIMIT 1
                    """,
                    (RICHMOND_FIPS, slug.lower()),
                )
            else:
                cur.execute(
                    """SELECT id, name FROM officials
                       WHERE city_fips = %s AND name ILIKE %s
                       LIMIT 1
                    """,
                    (RICHMOND_FIPS, f"%{name}%"),
                )
            row = cur.fetchone()
            if not row:
                print(f"No official found matching: {name or slug}")
                return
            off_id, full_name = row

            print(f"\n========================================")
            print(f"DONOR DATA VERIFICATION — {full_name}")
            print(f"========================================")

            # Find all committees linked to this official, either via
            # election_candidates or directly via committees.official_id
            cur.execute(
                """SELECT c.id, c.name, c.filer_id, c.status, e.election_name,
                          e.election_date
                   FROM committees c
                   LEFT JOIN elections e ON e.id = c.election_id
                   WHERE c.city_fips = %s AND (
                     c.official_id = %s
                     OR c.id IN (
                       SELECT committee_id FROM election_candidates
                       WHERE official_id = %s AND committee_id IS NOT NULL
                     )
                   )
                   ORDER BY e.election_date DESC NULLS LAST, c.name
                """,
                (RICHMOND_FIPS, str(off_id), str(off_id)),
            )
            committees = cur.fetchall()
            if not committees:
                print(f"\n  No committees linked to {full_name}.")
                print(f"  (If they have NetFile filings, they're not in our DB yet.)")
                return

            print(f"\n  {len(committees)} committee(s) linked:")
            for c in committees:
                _print_committee_card(cur, c[0], c[1], c[2], c[3], c[4])

            # Final summary
            cur.execute(
                """SELECT COUNT(*), SUM(amount)
                   FROM contributions
                   WHERE committee_id IN (
                     SELECT DISTINCT id FROM committees c
                     WHERE c.city_fips = %s AND (
                       c.official_id = %s
                       OR c.id IN (
                         SELECT committee_id FROM election_candidates
                         WHERE official_id = %s AND committee_id IS NOT NULL
                       )
                     )
                   )
                """,
                (RICHMOND_FIPS, str(off_id), str(off_id)),
            )
            grand_n, grand_total = cur.fetchone()
            print(f"\n  ── ALL-COMMITTEES TOTAL FOR {full_name} ──")
            print(f"     {grand_n} contributions, {_fmt_money(grand_total)} lifetime")
            print()
    finally:
        conn.close()


def verify_all_current() -> None:
    """Run verify_official for every current council member."""
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT name FROM officials
                   WHERE city_fips = %s AND is_current = TRUE
                   ORDER BY role DESC, name
                """,
                (RICHMOND_FIPS,),
            )
            names = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    for n in names:
        verify_official(name=n)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--name", help='Official name (e.g., "Claudia Jimenez")')
    g.add_argument("--slug", help="Slug form (e.g., claudia-jimenez)")
    g.add_argument("--all-current", action="store_true",
                   help="Run for all 7 current council members")
    args = parser.parse_args()

    if args.all_current:
        verify_all_current()
    else:
        verify_official(name=args.name, slug=args.slug)


if __name__ == "__main__":
    main()
