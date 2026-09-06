"""Retired near-date contribution heuristic, retained for read-only diagnosis.

Equal amounts on different dates/filings do not prove a duplicate. The prior
heuristic erased a distinct May 18, 2026 $30,000 RPOA-to-Safe-Richmond gift.
No write path is allowed here. Use finance_repair_audit.py for a source-linked
read-only packet, and finance_ledger.py for explicit amendment reconciliation.
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
      1. Prefer the EARLIER contribution_date — closer to when the
         money actually moved. The donor's 497 Part 2 (filed within
         24 hours of sending) and the recipient's 497 Part 1 (filed
         within 24 hours of clearing) carry slightly different dates
         even though it's the same legal gift; the earlier date is
         what matters for temporal-window comparisons (e.g. an article
         reporting "through April 18" needs to see a gift sent on
         April 10 even when the recipient cleared it on April 20).
      2. On date tie, prefer the LOWER filing_id — the donor's filing
         is typically logged first in the FPPC system since the donor
         knows about the gift before the recipient. This is a tiebreak
         and rarely matters; date dominates.

    History: this rule originally preferred the HIGHER filing_id on
    the theory that the recipient's filing was canonical from their
    accounting view. That was wrong — higher filing_id correlates
    with later FILING date, not later TRANSACTION date, and the
    article-as-oracle test for Jimenez (IAFF Local 188, 4/10 vs 4/20)
    revealed the bug: keeping the recipient's 4/20 filing put the
    contribution AFTER the article's 4/18 cutoff, making it look
    like our DB didn't have the gift at all.
    """
    if a_date < b_date:
        return (a_id, b_id, a_date, b_date, a_filing, b_filing)
    if a_date > b_date:
        return (b_id, a_id, b_date, a_date, b_filing, a_filing)
    # date tie — fall back to filing_id (lower wins)
    a_fid = a_filing or ""
    b_fid = b_filing or ""
    if a_fid <= b_fid:
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
    """Reject the retired destructive heuristic, including legacy callers."""
    raise RuntimeError(
        "Near-date equality does not prove duplicate contributions. "
        "Use the read-only finance repair audit and retained source assertions."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Retired; always rejected")
    parser.add_argument("--committee-id", default=None)
    parser.add_argument("--city-fips", default=CITY_FIPS)
    args = parser.parse_args()
    if args.apply:
        parser.error("Destructive near-date dedup is retired; use finance_repair_audit.py")
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.set_session(readonly=True)
    try:
        pairs = find_cross_filing_duplicates(conn, args.city_fips, args.committee_id)
        print(f"{len(pairs)} near-date candidate pairs. Similarity does not prove duplication.")
        print("Use finance_repair_audit.py for all cohorts and source evidence; no rows changed.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
