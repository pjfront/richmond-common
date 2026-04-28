"""Cross-filing contribution deduplication.

California campaign finance reporting double-counts contributions when
both parties file: a $2,500 PAC donation appears once on the donor PAC's
Form 497 Part 2 (outgoing) and again on the recipient candidate's Form
497 Part 1 (incoming). Both filings carry slightly different transaction
dates (the date the donor sent vs the date the recipient cleared) and
get extracted into our `contributions` table as two separate rows that
slip past the standard `(donor_id, amount, contribution_date,
committee_id)` ON CONFLICT key.

This module finds those near-date cross-filing duplicates and collapses
them, preferring the row from the higher filing_id (typically the
recipient's later filing — the canonical one from the receiving
committee's own accounting view).

Match rule:
  same donor_id
  AND same committee_id (recipient)
  AND same amount
  AND filing_id differs
  AND contribution_date within ±14 days

This is conservative on purpose. A donor genuinely giving the same
amount twice within a single 460 filing won't have different filing_ids
(they're rows in the same form), so they're safe. Two $50 monthly
gifts from the same person across separate filings of the same form
also won't trigger because they share the form's filing_id.

Reads from `contributions` directly. Writes only the rows being deleted.
Source-closest: `contributions` is the source of truth here — paper-
filing JSONs feed into it via load_paper_filings, and after that the DB
is canonical.

Usage::

    python src/dedup_contributions.py            # dry run
    python src/dedup_contributions.py --apply    # write changes
    python src/dedup_contributions.py --committee-id <uuid>  # one committee only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=True)
sys.path.insert(0, str(_ROOT / "src"))

import psycopg2  # noqa: E402

CITY_FIPS = "0660620"
DAY_WINDOW = 14  # ± window for cross-filing match


def _choose_keeper(
    a_id, a_date, a_filing,
    b_id, b_date, b_filing,
) -> tuple:
    """Decide which side of a duplicate-pair becomes the keeper.

    Pure function — extracted from find_cross_filing_duplicates so the
    tie-break rules are testable without a DB. Returns
    (keep_id, drop_id, keep_date, drop_date, keep_fid, drop_fid).

    Rules (in order):
      1. Prefer the higher filing_id — typically the receiving
         committee's later filing, the canonical row from the
         recipient's own accounting view.
      2. On filing_id tie (or both NULL), prefer the later
         contribution_date — the date the recipient cleared the gift.
    """
    keep_filing = a_filing or ""
    drop_filing = b_filing or ""
    if keep_filing < drop_filing:
        return (b_id, a_id, b_date, a_date, b_filing, a_filing)
    if keep_filing > drop_filing:
        return (a_id, b_id, a_date, b_date, a_filing, b_filing)
    # filing_id tie
    if a_date >= b_date:
        return (a_id, b_id, a_date, b_date, a_filing, b_filing)
    return (b_id, a_id, b_date, a_date, b_filing, a_filing)


def _deoverlap_pairs(pairs: list[dict]) -> list[dict]:
    """Drop pairs that would conflict with each other in 3-way duplicates.

    Pure function — same row can appear in multiple raw pairs (e.g. A=B,
    B=C, A=C). We greedy-select pairs in input order, skipping any pair
    whose keep_id was previously dropped or whose drop_id was previously
    kept. This guarantees each row is in the keep_set or drop_set, never
    both — so the apply pass can DELETE drop_ids without orphaning a
    surviving row.
    """
    drop_set: set[str] = set()
    keep_set: set[str] = set()
    final: list[dict] = []
    for p in pairs:
        if p["keep_id"] in drop_set or p["drop_id"] in keep_set:
            continue
        keep_set.add(p["keep_id"])
        drop_set.add(p["drop_id"])
        final.append(p)
    return final


def find_cross_filing_duplicates(
    conn,
    city_fips: str = CITY_FIPS,
    committee_id: str | None = None,
) -> list[dict]:
    """Return contribution row pairs that look like cross-filing dupes.

    Each pair: {keep_id, drop_id, donor_name, amount, keep_date, drop_date,
    keep_filing_id, drop_filing_id, day_gap}. Caller can preview or apply.
    """
    where_clauses = ["c.city_fips = %s", "c.contribution_date IS NOT NULL"]
    params: list = [city_fips]
    if committee_id:
        where_clauses.append("c.committee_id = %s")
        params.append(committee_id)

    sql = f"""
    WITH candidates AS (
      SELECT c.id, c.donor_id, c.amount, c.contribution_date,
             c.filing_id, c.committee_id,
             d.name AS donor_name
        FROM contributions c
        JOIN donors d ON d.id = c.donor_id
       WHERE {" AND ".join(where_clauses)}
    )
    SELECT a.id   AS a_id,
           b.id   AS b_id,
           a.donor_name, a.amount,
           a.contribution_date AS a_date,
           b.contribution_date AS b_date,
           a.filing_id AS a_filing,
           b.filing_id AS b_filing,
           ABS((b.contribution_date - a.contribution_date)) AS day_gap
      FROM candidates a
      JOIN candidates b
        ON a.donor_id    = b.donor_id
       AND a.amount      = b.amount
       AND a.committee_id IS NOT DISTINCT FROM b.committee_id
       AND a.id         <  b.id
       AND a.filing_id  IS DISTINCT FROM b.filing_id
       AND ABS((b.contribution_date - a.contribution_date)) <= %s
    ORDER BY a.donor_name, a.contribution_date
    """
    params.append(DAY_WINDOW)

    pairs: list[dict] = []
    with conn.cursor() as cur:
        cur.execute(sql, params)
        for row in cur.fetchall():
            (a_id, b_id, donor_name, amount,
             a_date, b_date, a_filing, b_filing, day_gap) = row

            keep_id, drop_id, keep_date, drop_date, keep_fid, drop_fid = (
                _choose_keeper(a_id, a_date, a_filing, b_id, b_date, b_filing)
            )

            pairs.append({
                "keep_id": str(keep_id),
                "drop_id": str(drop_id),
                "donor_name": donor_name,
                "amount": float(amount),
                "keep_date": keep_date,
                "drop_date": drop_date,
                "keep_filing_id": keep_fid,
                "drop_filing_id": drop_fid,
                "day_gap": int(day_gap),
            })

    return _deoverlap_pairs(pairs)


def apply_cross_filing_dedup(
    conn,
    city_fips: str = CITY_FIPS,
    committee_id: str | None = None,
) -> dict:
    """Delete the duplicate (drop) row from each pair found.

    Returns counts. Idempotent — re-running on a deduped DB is a no-op.
    """
    pairs = find_cross_filing_duplicates(conn, city_fips, committee_id)
    if not pairs:
        return {"dropped": 0, "pairs_seen": 0}

    drop_ids = [p["drop_id"] for p in pairs]
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM contributions WHERE id::text = ANY(%s)",
            (drop_ids,),
        )
        dropped = cur.rowcount
    conn.commit()
    return {"dropped": dropped, "pairs_seen": len(pairs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true",
                        help="Write changes (default is dry-run preview)")
    parser.add_argument("--committee-id", default=None,
                        help="Limit to one recipient committee (UUID)")
    parser.add_argument("--city-fips", default=CITY_FIPS)
    args = parser.parse_args()

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = False

    pairs = find_cross_filing_duplicates(conn, args.city_fips, args.committee_id)
    if not pairs:
        print("No cross-filing duplicates found.")
        conn.close()
        return

    print(f"Found {len(pairs)} cross-filing duplicate pair(s):\n")
    total_drop_amount = 0.0
    for p in pairs:
        total_drop_amount += p["amount"]
        print(
            f"  {p['donor_name'][:45]:45s} ${p['amount']:>10,.2f}\n"
            f"    keep: {p['keep_date']} fid={p['keep_filing_id']}\n"
            f"    drop: {p['drop_date']} fid={p['drop_filing_id']} "
            f"(gap {p['day_gap']}d)"
        )
    print(f"\nTotal duplicate dollars to drop: ${total_drop_amount:,.2f}")

    if not args.apply:
        print("\n(Dry run — pass --apply to execute.)")
        conn.close()
        return

    stats = apply_cross_filing_dedup(conn, args.city_fips, args.committee_id)
    print(f"\nDone. Dropped {stats['dropped']} row(s).")
    conn.close()


if __name__ == "__main__":
    main()
