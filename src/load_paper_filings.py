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


FORM_SUMMARY_CACHE = Path(__file__).parent / "data" / "form_summaries.json"


def _load_form_summary_cache() -> dict:
    """Load the persistent {filing_id: form_summary} cache."""
    if not FORM_SUMMARY_CACHE.exists():
        return {}
    try:
        with open(FORM_SUMMARY_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_form_summary_cache(cache: dict) -> None:
    """Atomically write the form-summary cache."""
    import tempfile
    FORM_SUMMARY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=FORM_SUMMARY_CACHE.parent,
        suffix=".tmp", delete=False,
    ) as tmp:
        json.dump(cache, tmp, indent=2, ensure_ascii=False, sort_keys=True)
        tmp_path = Path(tmp.name)
    tmp_path.replace(FORM_SUMMARY_CACHE)


def discover_and_extract_all_form460_summaries(client=None) -> dict:
    """Walk the NetFile RSS, extract Form 460 cover summaries for any
    filings not yet in the persistent cache, and return the full cache.

    The cache (src/data/form_summaries.json) maps filing_id ->
    form_summary. Once extracted, the same filing_id never re-extracts
    (Form 460s don't change after filing). New filings get added
    incrementally.

    This generalizes the form-summary extraction beyond just paper
    filers — every candidate, paper or electronic, has their Form 460
    summary in the cache after one cron pass through.

    Returns the full {filing_id: summary, "_committees": {filing_id: name}}
    cache. The "_committees" sidecar lets reconciliation map filing_id
    back to a committee name without a second RSS round-trip.
    """
    if client is None:
        from anthropic import Anthropic
        client = Anthropic()

    from netfile_client import fetch_filing_rss
    from netfile_paper_extractor import (
        download_paper_filing, parse_form460_summary_with_vision,
        PDF_CACHE_DIR, classify_form,
    )

    cache = _load_form_summary_cache()
    cache.setdefault("_committees", {})

    rss = fetch_filing_rss()
    new_count = 0
    for filing in rss:
        if classify_form(filing.get("form_type", "")) != "460":
            continue
        filing_id = str(filing.get("filing_id", ""))
        if not filing_id or filing_id in cache:
            cache["_committees"][filing_id] = filing.get("committee", "")
            continue

        committee = filing.get("committee", "")
        print(f"  [extract] {committee} filing {filing_id}")
        try:
            pdf_path = download_paper_filing(filing_id, output_dir=PDF_CACHE_DIR)
            summary = parse_form460_summary_with_vision(
                pdf_path, filing_id, committee, client
            )
        except Exception as exc:
            print(f"    failed: {exc}")
            continue
        if summary:
            cache[filing_id] = summary
            cache["_committees"][filing_id] = committee
            new_count += 1
            print(
                f"    monetary=${float(summary.get('monetary_this_period', 0)):,.2f}, "
                f"loans=${float(summary.get('loans_this_period', 0)):,.2f}, "
                f"unitemized=${float(summary.get('unitemized_this_period', 0)):,.2f}"
            )

    if new_count:
        _save_form_summary_cache(cache)
        print(f"  cached {new_count} new Form 460 summary/summaries")
    return cache


def reconcile_paper_filings_to_forms(conn, city_fips: str = "0660620") -> dict:
    """Synthesize Form 460 reconciliation rows for ALL candidates with a
    Form 460 in the persistent summary cache. Reconciles against
    MONETARY (Line 1) — excludes loans (Schedule B/F) and non-monetary
    (Schedule C) which are tracked separately.

    For each Form 460 in the cache:
      * Compute gap = form.monetary_this_period - DB monetary in period
      * If gap > $1: insert/update one synthetic row with that amount,
        contributor_name=UNITEMIZED_DONOR_NAME, entity_code='UNI',
        date=period_end. Represents unitemized small-donor contributions
        FPPC rules let candidates aggregate rather than itemize.
      * If gap < -$1: DB EXCEEDS form — flagged in the return stats so
        the operator can investigate. NO negative synthesis.
      * If |gap| <= $1: extraction already matches.

    Idempotent: drops all UNI rows for the city before re-inserting,
    so the resulting state reflects the latest summary cache + DB
    state regardless of run history.

    Designed to run AFTER donor_employer_merge and donor_dedup so the
    DB period totals reflect the post-cleanup state. The caller (e.g.,
    sync_paper_filing_reconciliation) typically also calls
    discover_and_extract_all_form460_summaries first to ensure the
    cache is fresh.
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

    cache = _load_form_summary_cache()
    committees_map = cache.get("_committees", {})
    over_filings: list[dict] = []

    for filing_id, summary in cache.items():
        if filing_id == "_committees":
            continue
        committee = committees_map.get(filing_id, "")
        if not committee:
            continue
        stats["filings_examined"] += 1

        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM committees WHERE city_fips = %s AND name = %s",
                (city_fips, committee),
            )
            row = cur.fetchone()
        if not row:
            continue  # committee not yet synced — skip silently
        committee_id = row[0]

        # Reconcile against MONETARY (Schedule A, Line 1) — excludes
        # loans (Schedule B, separate financial instrument) and
        # nonmonetary (Schedule C, in-kind goods/services). Loans and
        # nonmonetary are tracked in `contributions.contribution_type`
        # so they show up in DB sums; we filter them here.
        monetary_form = float(summary.get("monetary_this_period") or 0)
        period_start = (summary.get("period_start") or "").strip() or "2000-01-01"
        period_end = (summary.get("period_end") or "").strip()
        if not period_end:
            continue
        # Defensive: Vision OCR occasionally extracts a 497 PDF as a "460"
        # and returns sentinel strings like "<UNKNOWN>" or empty values for
        # period_start. Reject malformed dates to avoid SQL crashes and
        # bogus reconciliation. Caller should re-classify these filings.
        import re as _re
        date_re = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if not date_re.match(period_start) or not date_re.match(period_end):
            print(f"  ⚠ {committee} filing {filing_id}: malformed period "
                  f"({period_start}..{period_end}) — skipping reconciliation")
            continue

        with conn.cursor() as cur:
            cur.execute(
                """SELECT COALESCE(SUM(amount), 0)
                     FROM contributions
                    WHERE committee_id = %s
                      AND contribution_date >= %s
                      AND contribution_date <= %s
                      AND entity_code IS DISTINCT FROM 'UNI'
                      AND (contribution_type IS NULL
                           OR contribution_type = 'monetary')""",
                (committee_id, period_start, period_end),
            )
            db_monetary = float(cur.fetchone()[0])

        gap = round(monetary_form - db_monetary, 2)
        if gap < -1.0:
            stats["filings_over"] += 1
            over_record = {
                "filing_id": filing_id,
                "committee": committee,
                "form_monetary": monetary_form,
                "db_monetary": db_monetary,
                "excess": -gap,
                "period_start": period_start,
                "period_end": period_end,
            }
            over_filings.append(over_record)
            print(
                f"  ⚠ {committee} filing {filing_id}: "
                f"DB monetary ${db_monetary:,.2f} EXCEEDS form Line 1 "
                f"${monetary_form:,.2f} by ${-gap:,.2f} — "
                f"flagged for operator review (data quality)"
            )
            continue
        if gap < 1.0:
            stats["filings_already_matched"] += 1
            continue

        synth_record = {
            "contributor_name": UNITEMIZED_DONOR_NAME,
            "contributor_employer": "",
            "amount": gap,
            "date": period_end,
            "committee": committee,
            "occupation": "",
            "source": "fppc_paper",
            "filing_id": filing_id,
            "filer_fppc_id": "",
            "entity_code": "UNI",
        }
        print(f"  {committee} filing {filing_id}: synthesizing ${gap:,.2f} unitemized")
        load_contributions_to_db(conn, [synth_record], city_fips=city_fips)
        stats["rows_synthesized"] += 1
        stats["dollars_synthesized"] += gap

    stats["over_filings"] = over_filings
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
