"""
Load paper-filed campaign contributions into the database.

Reads JSON files from src/data/paper_filings/ and loads them via
the same load_contributions_to_db() used for NetFile e-filed data.
Paper filings are tagged with source='fppc_paper' to distinguish
from electronic filings (source='netfile').

Reconciliation to Form 460 cover totals: each Form 460 carries a
``form_summary`` block (extracted by parse_form460_summary_with_vision)
with the candidate's own legal claim of total monetary contributions
this period and cycle-to-date. After itemized rows are loaded and the
dedup/merge enrichments have run, ``reconcile_paper_filings_to_forms``
inserts one synthetic row per Form 460 with amount = (form total -
itemized rows in that period). The synthetic row covers unitemized
small donations (< $100, FPPC reports as a summary line) plus any
extraction noise. This makes DB cycle totals match the form exactly,
without falsely implying we have donor identity for the small-dollar
gifts that FPPC rules let candidates report aggregated.

Run order (handled automatically via SYNC_SOURCES enrichment cascade):
  1. load_paper_filings.py        — itemized rows from JSON
  2. donor_employer_merge          — collapse same-name donors
  3. donor_dedup                   — drop cross-filing 497 dups
  4. paper_filing_reconciliation   — synthesize Form 460 deficit rows

Usage:
    python load_paper_filings.py                     # load all JSON files
    python load_paper_filings.py anderson_mayor_2026 # load specific filing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, load_contributions_to_db

PAPER_FILINGS_DIR = Path(__file__).parent / "data" / "paper_filings"

# Sentinel donor name for the synthetic unitemized aggregate row.
# Stored as a real donors row so the contributions FK + uniqueness
# constraints stay valid; rendered separately by the frontend with a
# "small donations under $100, count not disclosed by FPPC" treatment.
UNITEMIZED_DONOR_NAME = "Unitemized contributions (under $100)"


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

    # NOTE: Form 460 unitemized synthesis happens in the
    # paper_filing_reconciliation enrichment AFTER dedup/merge run.
    # See sync_paper_filing_reconciliation in data_sync.py — synthesis
    # at this layer would synthesize against pre-dedup totals and
    # over-count.

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


def reconcile_paper_filings_to_forms(conn, city_fips: str = "0660620") -> dict:
    """Synthesize one row per Form 460 filing whose form_summary indicates
    extracted itemized rows fall short of the candidate's own reported total.

    For each paper_filings/*.json with form_summary blocks:
      * For each Form 460 filing: compute reconciliation gap as
          gap = form_summary.total_this_period - sum(DB contribs in
                  [period_start, period_end] for this committee)
      * If gap > $1: insert/update one synthetic row with amount=gap,
        contributor_name=UNITEMIZED_DONOR_NAME, entity_code='UNI',
        date=period_end, filing_id=this filing.
      * If gap <= $1: no synthesis (extraction already matches).
      * If gap < 0: log a warning (DB has MORE than the form claims —
        likely OCR over-extraction or stale dedup).

    Idempotent: re-running uses the same upsert key
    (contributor_name=UNITEMIZED_DONOR_NAME, committee_id, date, amount).
    Existing UNI rows for the same filing get refreshed to the new amount.

    Designed to run AFTER donor_employer_merge and donor_dedup so that
    the DB period totals reflect the post-cleanup state.
    """
    from db import load_contributions_to_db

    stats = {
        "filings_examined": 0,
        "rows_synthesized": 0,
        "dollars_synthesized": 0.0,
        "filings_already_matched": 0,
        "filings_over": 0,  # DB exceeds form (data quality issue)
    }

    # Drop any prior UNI rows so this is fully idempotent — we'll
    # re-insert with current correct amounts.
    with conn.cursor() as cur:
        cur.execute(
            """DELETE FROM contributions
                WHERE city_fips = %s AND entity_code = 'UNI'""",
            (city_fips,),
        )
        prior_uni_count = cur.rowcount
        if prior_uni_count:
            print(f"  cleared {prior_uni_count} prior UNI rows")

    json_files = sorted(PAPER_FILINGS_DIR.glob("*.json"))
    for json_path in json_files:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("city_fips", "0660620") != city_fips:
            continue
        committee = data["committee"]
        fppc_id = data.get("fppc_id", "")

        # Find the committee_id
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM committees WHERE city_fips = %s AND name = %s",
                (city_fips, committee),
            )
            row = cur.fetchone()
        if not row:
            print(f"  skip {committee}: no committee row in DB")
            continue
        committee_id = row[0]

        synth_records: list[dict] = []
        for filing in data.get("filings", []):
            if filing.get("form") != "460":
                continue
            summary = filing.get("form_summary")
            if not summary:
                continue
            stats["filings_examined"] += 1

            total_this_period = float(summary.get("total_this_period") or 0)
            period_start = (summary.get("period_start") or "").strip() or "2000-01-01"
            period_end = (summary.get("period_end") or "").strip()
            if not period_end:
                continue

            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(amount), 0)
                         FROM contributions
                        WHERE committee_id = %s
                          AND contribution_date >= %s
                          AND contribution_date <= %s
                          AND entity_code IS DISTINCT FROM 'UNI'""",
                    (committee_id, period_start, period_end),
                )
                db_in_period = float(cur.fetchone()[0])

            gap = round(total_this_period - db_in_period, 2)
            if gap < -1.0:
                stats["filings_over"] += 1
                print(
                    f"  ⚠ {committee} filing {filing['filing_id']}: "
                    f"DB total ${db_in_period:,.2f} EXCEEDS form total "
                    f"${total_this_period:,.2f} by ${-gap:,.2f} — "
                    f"check OCR over-extraction or dedup gaps"
                )
                continue
            if gap < 1.0:
                stats["filings_already_matched"] += 1
                continue

            synth_records.append({
                "contributor_name": UNITEMIZED_DONOR_NAME,
                "contributor_employer": "",
                "amount": gap,
                "date": period_end,
                "committee": committee,
                "occupation": "",
                "source": "fppc_paper",
                "filing_id": str(filing.get("filing_id", "")),
                "filer_fppc_id": fppc_id,
                "entity_code": "UNI",
            })

        if synth_records:
            print(f"  {committee}: synthesizing {len(synth_records)} reconciliation row(s) "
                  f"totaling ${sum(r['amount'] for r in synth_records):,.2f}")
            load_contributions_to_db(conn, synth_records, city_fips=city_fips)
            stats["rows_synthesized"] += len(synth_records)
            stats["dollars_synthesized"] += sum(r["amount"] for r in synth_records)

    conn.commit()
    return stats


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
