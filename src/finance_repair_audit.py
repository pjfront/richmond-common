"""Read-only, source-linked repair packet for legacy campaign contribution rows.

No apply mode exists. DATABASE_URL is placed in a read-only transaction before
any query. The output omits personal donor names and street/contact information.
Public committee identities on Form 497 Part 2 are retained for exact direction
review. Near-date pairs are questions, never instructions to delete records.
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from finance_ledger import clean, normalized_name
from netfile_client import fetch_all_transactions, get_filing_info


def direction_status(tx: dict, rows: list[dict]) -> tuple[str, list[dict]]:
    """Match all source dimensions. Amount/date alone cannot identify a row."""
    relevant = [r for r in rows if str(r["filing_id"]) == str(tx["filingId"])
                and Decimal(str(r["amount"])) == Decimal(str(tx["amount"]))
                and str(r["contribution_date"])[:10] == tx["date"][:10]]
    reversed_rows = [r for r in relevant if normalized_name(r["donor_name"]) == normalized_name(tx.get("name"))
                     and str(r["recipient_fppc_id"]) == str(tx.get("filerFppcId"))]
    correct = [r for r in relevant if normalized_name(r["donor_name"]) == normalized_name(tx.get("filerName"))
               and ((clean(tx.get("transactionFppcId")) and str(r["recipient_fppc_id"]) == str(tx["transactionFppcId"]))
                    or normalized_name(r["recipient_name"]) == normalized_name(tx.get("name")))]
    if reversed_rows and correct:
        return "both_directions_present_review", reversed_rows + correct
    if reversed_rows:
        return "reversed_source_direction", reversed_rows
    if correct:
        return "already_correct", correct
    return "source_assertion_missing_from_legacy", []


def audit(conn, year: int, through: str, *, fetch=fetch_all_transactions, filing_info=get_filing_info) -> dict:
    from psycopg2.extras import RealDictCursor
    # Even accidentally supplied production credentials cannot turn this into a
    # writer. No functions that mutate the DB are imported or invoked.
    conn.set_session(readonly=True)
    txs = fetch(transaction_type=21, date_start=f"{year}-01-01", date_end=through, city_fips="0660620")
    lineage = {str(tx["filingId"]): filing_info(str(tx["filingId"])) for tx in txs}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT c.id::text,c.filing_id,c.amount,c.contribution_date,d.name donor_name,
                              m.filer_id recipient_fppc_id,m.name recipient_name
                       FROM contributions c JOIN donors d ON d.id=c.donor_id
                       JOIN committees m ON m.id=c.committee_id
                       WHERE c.contribution_date BETWEEN %s AND %s AND c.filing_id=ANY(%s)""",
                    (f"{year}-01-01", through, sorted(lineage)))
        rows = list(cur.fetchall())
        cur.execute("""SELECT a.id::text a_id,b.id::text b_id,a.filing_id a_filing_id,b.filing_id b_filing_id,
                              a.amount,a.contribution_date a_date,b.contribution_date b_date,
                              a.committee_id::text recipient_committee_id
                       FROM contributions a JOIN contributions b
                         ON a.donor_id=b.donor_id AND a.committee_id=b.committee_id AND a.amount=b.amount
                        AND a.id<b.id AND a.filing_id<>b.filing_id
                        AND abs(a.contribution_date-b.contribution_date)<=14
                       WHERE a.contribution_date BETWEEN %s AND %s AND b.contribution_date BETWEEN %s AND %s
                       ORDER BY a.contribution_date,a.id,b.id""",
                    (f"{year}-01-01", through, f"{year}-01-01", through))
        cohorts = list(cur.fetchall())
    packets = []
    for tx in txs:
        status, matched = direction_status(tx, rows)
        info = lineage[str(tx["filingId"])]
        packets.append(dict(
            status=status, source_filing_id=str(tx["filingId"]), source_transaction_id=tx["id"],
            source_url=f"https://netfile.com/Connect2/api/public/image/{tx['filingId']}",
            source_form="F497P2", source_amends=info.get("amends"), source_amended_by=info.get("amendedBy"),
            amount=tx["amount"], activity_date=tx["date"][:10],
            legacy_row_ids=[r["id"] for r in matched],
            before=[dict(row_id=r["id"], donor_name=r["donor_name"], recipient_name=r["recipient_name"],
                         recipient_fppc_id=r["recipient_fppc_id"]) for r in matched],
            source_verified_direction=dict(donor_name=tx.get("filerName"), donor_fppc_id=tx.get("filerFppcId"),
                                           recipient_name=tx.get("name"), recipient_fppc_id=tx.get("transactionFppcId")),
            proposed_action="retain_original_assertion_then_targeted_rebuild" if status == "reversed_source_direction" else "review_no_automatic_legacy_write",
        ))
    for row in cohorts:
        row["proposed_action"] = "retain_both_until_source_proves_relation"
        row["source_urls"] = [f"https://netfile.com/Connect2/api/public/image/{row[k]}" for k in ("a_filing_id", "b_filing_id")]
    return dict(mode="read_only", year=year, through=through, direction_packets=packets, near_date_cohorts=cohorts,
                limitations=["Rows deleted by earlier runs cannot be reconstructed from the current table; retained source transactions and explicit filing lineage are required.",
                             "Do not add corrected transfers to legacy reversed rows or delete near-date cohorts on amount/date similarity alone."])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--through", default=date.today().isoformat())
    parser.add_argument("--env-file", type=Path, help="Explicit credentials path; values are never printed")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
    from db import get_connection
    conn = get_connection()
    try:
        report = audit(conn, args.year, args.through)
    finally:
        conn.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, default=str, indent=2), encoding="utf-8")
    from collections import Counter
    print(json.dumps({"mode": "read_only", "direction_status_counts": dict(Counter(p["status"] for p in report["direction_packets"])),
                      "near_date_cohorts": len(report["near_date_cohorts"])}, indent=2))


if __name__ == "__main__":
    main()
