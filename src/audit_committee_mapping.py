"""
Audit committee↔candidate wiring for an upcoming election.

When the candidate-page totals are wrong, the cause is almost always one
of three structural gaps:

  A. Committee has contributions in `contributions` but no candidate row
     points at it via `election_candidates.committee_id` (orphan committee
     — the candidate page can never find this money).
  B. A `filed`/`qualified` candidate row has no `committee_id`, so the
     candidate-page query (`election_candidates JOIN contributions ON
     committee_id`) silently returns zero rows for that candidate.
  C. The candidate's `committee_id` points at a committee that has no
     contributions in the same `city_fips` — usually a wrong-jurisdiction
     wiring or a stale id.

This script reports all three and (with --create-decisions) pushes one
decision-queue entry per orphan so the operator sees them in the standard
session-start briefing.

Reads from: live DB (committees, election_candidates, contributions, elections).
Does NOT read from: any cached audit artifact — every run is fresh.

Usage:
  python audit_committee_mapping.py                      # text report
  python audit_committee_mapping.py --json               # JSON output
  python audit_committee_mapping.py --create-decisions   # also push to decision_queue
  python audit_committee_mapping.py --election-id <UUID> # restrict to one election
"""
from __future__ import annotations

import argparse
import json as _json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection
from decision_queue import create_decision

DEFAULT_FIPS = "0660620"
ACTIVE_STATUSES = ("filed", "qualified")


def find_orphan_committees(cur, city_fips: str, election_id: str | None = None) -> list[dict]:
    """Report A: committees with contributions but no election_candidates row."""
    where = ["c.city_fips = %s"]
    params: list = [city_fips]
    if election_id:
        # If restricted to one election, only flag committees that *should*
        # belong to it (have contributions inside that election's cycle window).
        where.append("c.election_id = %s")
        params.append(election_id)

    cur.execute(
        f"""
        SELECT c.id, c.name, c.filer_id,
               COUNT(con.id) AS contrib_count,
               COALESCE(SUM(con.amount), 0) AS total_amount,
               MIN(con.contribution_date) AS first_contrib,
               MAX(con.contribution_date) AS last_contrib
        FROM committees c
        JOIN contributions con ON con.committee_id = c.id
        LEFT JOIN election_candidates ec ON ec.committee_id = c.id
        WHERE {' AND '.join(where)}
          AND ec.id IS NULL
        GROUP BY c.id, c.name, c.filer_id
        ORDER BY total_amount DESC
        """,
        params,
    )
    return [
        {
            "committee_id": str(row[0]),
            "committee_name": row[1],
            "filer_id": row[2],
            "contribution_count": row[3],
            "total_amount": float(row[4] or 0),
            "first_contribution": row[5].isoformat() if row[5] else None,
            "last_contribution": row[6].isoformat() if row[6] else None,
        }
        for row in cur.fetchall()
    ]


def find_candidates_without_committee(
    cur, city_fips: str, election_id: str | None = None
) -> list[dict]:
    """Report B: active candidates with no committee_id."""
    where = ["ec.city_fips = %s", "ec.committee_id IS NULL", f"ec.status IN {ACTIVE_STATUSES}"]
    params: list = [city_fips]
    if election_id:
        where.append("ec.election_id = %s")
        params.append(election_id)

    cur.execute(
        f"""
        SELECT ec.id, ec.candidate_name, ec.office_sought, ec.status,
               e.id, e.election_name, e.election_date
        FROM election_candidates ec
        JOIN elections e ON e.id = ec.election_id
        WHERE {' AND '.join(where)}
        ORDER BY e.election_date, ec.candidate_name
        """,
        params,
    )
    return [
        {
            "candidate_id": str(row[0]),
            "candidate_name": row[1],
            "office_sought": row[2],
            "status": row[3],
            "election_id": str(row[4]),
            "election_name": row[5],
            "election_date": row[6].isoformat() if row[6] else None,
        }
        for row in cur.fetchall()
    ]


def find_candidates_with_unwired_committee(
    cur, city_fips: str, election_id: str | None = None
) -> list[dict]:
    """Report C: candidate.committee_id points at a committee with zero contributions in city_fips."""
    where = ["ec.city_fips = %s", "ec.committee_id IS NOT NULL"]
    params: list = [city_fips]
    if election_id:
        where.append("ec.election_id = %s")
        params.append(election_id)

    cur.execute(
        f"""
        SELECT ec.id, ec.candidate_name, ec.office_sought, ec.status,
               ec.committee_id, c.name AS committee_name,
               (
                 SELECT COUNT(*)
                 FROM contributions con
                 WHERE con.committee_id = ec.committee_id
                   AND con.city_fips = ec.city_fips
               ) AS contrib_count
        FROM election_candidates ec
        LEFT JOIN committees c ON c.id = ec.committee_id
        WHERE {' AND '.join(where)}
        ORDER BY ec.candidate_name
        """,
        params,
    )
    return [
        {
            "candidate_id": str(row[0]),
            "candidate_name": row[1],
            "office_sought": row[2],
            "status": row[3],
            "committee_id": str(row[4]) if row[4] else None,
            "committee_name": row[5],
            "contribution_count": row[6],
        }
        for row in cur.fetchall()
        if row[6] == 0
    ]


def run_audit(city_fips: str = DEFAULT_FIPS, election_id: str | None = None) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            return {
                "city_fips": city_fips,
                "election_id": election_id,
                "orphan_committees": find_orphan_committees(cur, city_fips, election_id),
                "candidates_without_committee": find_candidates_without_committee(
                    cur, city_fips, election_id
                ),
                "candidates_with_unwired_committee": find_candidates_with_unwired_committee(
                    cur, city_fips, election_id
                ),
            }
    finally:
        conn.close()


def push_decisions(report: dict) -> int:
    """Push one decision_queue entry per orphan. Returns count created."""
    conn = get_connection()
    created = 0
    try:
        for orphan in report["orphan_committees"]:
            decision = create_decision(
                conn,
                city_fips=report["city_fips"],
                decision_type="data_quality",
                severity="medium",
                title=f"Orphan committee: {orphan['committee_name']}",
                description=(
                    f"Committee {orphan['committee_name']!r} has "
                    f"{orphan['contribution_count']:,} contribution(s) "
                    f"totaling ${orphan['total_amount']:,.2f} but no "
                    f"election_candidates row links to it. The candidate "
                    f"page query can't find this money. Wire this committee "
                    f"to a candidate via election_candidates.committee_id."
                ),
                source="audit_committee_mapping",
                evidence=orphan,
                entity_type="committee",
                entity_id=orphan["committee_id"],
                dedup_key=f"audit_committee_mapping:orphan:{orphan['committee_id']}",
            )
            if decision:
                created += 1

        for missing in report["candidates_without_committee"]:
            decision = create_decision(
                conn,
                city_fips=report["city_fips"],
                decision_type="data_quality",
                severity="medium",
                title=f"Candidate missing committee: {missing['candidate_name']}",
                description=(
                    f"Candidate {missing['candidate_name']!r} ({missing['office_sought']}) "
                    f"in election {missing['election_name']!r} has no committee_id. "
                    f"Their candidate page will show $0 raised. Look up their FPPC "
                    f"committee in NetFile and set election_candidates.committee_id."
                ),
                source="audit_committee_mapping",
                evidence=missing,
                entity_type="election_candidate",
                entity_id=missing["candidate_id"],
                dedup_key=f"audit_committee_mapping:no_committee:{missing['candidate_id']}",
            )
            if decision:
                created += 1

        for unwired in report["candidates_with_unwired_committee"]:
            decision = create_decision(
                conn,
                city_fips=report["city_fips"],
                decision_type="data_quality",
                severity="high",
                title=f"Unwired committee: {unwired['candidate_name']}",
                description=(
                    f"Candidate {unwired['candidate_name']!r} points at "
                    f"committee_id {unwired['committee_id']} "
                    f"({unwired['committee_name']!r}) but that committee has zero "
                    f"contributions in city_fips={report['city_fips']!r}. Likely a "
                    f"wrong-jurisdiction or stale committee_id."
                ),
                source="audit_committee_mapping",
                evidence=unwired,
                entity_type="election_candidate",
                entity_id=unwired["candidate_id"],
                dedup_key=f"audit_committee_mapping:unwired:{unwired['candidate_id']}",
            )
            if decision:
                created += 1

        conn.commit()
    finally:
        conn.close()
    return created


def print_text(report: dict) -> None:
    print(f"\nCommittee mapping audit — city_fips={report['city_fips']}")
    if report["election_id"]:
        print(f"  scoped to election {report['election_id']}")
    print()

    orphans = report["orphan_committees"]
    print(f"A. Orphan committees (contributions present, no candidate link): {len(orphans)}")
    for o in orphans[:20]:
        print(
            f"   ${o['total_amount']:>12,.2f}  "
            f"{o['contribution_count']:>4}x  {o['committee_name']}  "
            f"(filer_id={o['filer_id']!r})"
        )
    if len(orphans) > 20:
        print(f"   ...and {len(orphans) - 20} more")
    print()

    missing = report["candidates_without_committee"]
    print(f"B. Candidates without committee_id (status filed/qualified): {len(missing)}")
    for m in missing:
        print(
            f"   {m['candidate_name']:<40} {m['office_sought']:<30} "
            f"{m['election_name']}  ({m['status']})"
        )
    print()

    unwired = report["candidates_with_unwired_committee"]
    print(f"C. Candidates with unwired committee (committee has zero contributions in this city): {len(unwired)}")
    for u in unwired:
        print(
            f"   {u['candidate_name']:<40} {u['office_sought']:<30} "
            f"committee_id={u['committee_id']}  ({u['committee_name']!r})"
        )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit committee↔candidate wiring")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS)
    parser.add_argument("--election-id", help="Restrict to one election UUID")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--create-decisions",
        action="store_true",
        help="Push orphans to decision_queue (deduplicated by dedup_key)",
    )
    args = parser.parse_args()

    report = run_audit(city_fips=args.city_fips, election_id=args.election_id)

    if args.json:
        print(_json.dumps(report, indent=2, default=str))
    else:
        print_text(report)

    if args.create_decisions:
        n = push_decisions(report)
        print(f"  Pushed {n} new decision(s) to operator decision_queue")

    total_issues = (
        len(report["orphan_committees"])
        + len(report["candidates_without_committee"])
        + len(report["candidates_with_unwired_committee"])
    )
    return 1 if total_issues else 0


if __name__ == "__main__":
    sys.exit(main())
