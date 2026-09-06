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
may insert the form's explicit unitemized amount only after the extracted
itemized rows match its itemized summary. Missing extraction is reported as
incomplete; it is never classified as small donations. Existing UNI rows are
preserved for a separately reviewed repair, including historical rows that
incorrectly combined missing itemized extraction with unitemized receipts.

Run order (handled automatically via SYNC_SOURCES enrichment cascade):
  1. load_paper_filings.py        — itemized rows from JSON
  2. donor_employer_merge          — collapse same-name donors
  3. donor_dedup                   — drop cross-filing 497 dups
  4. paper_filing_reconciliation   — verify explicit Form 460 unitemized totals

Usage:
    python load_paper_filings.py                     # load all JSON files
    python load_paper_filings.py anderson_mayor_2026 # load specific filing
"""
from __future__ import annotations


import argparse
import json
import math
import sys
from datetime import date
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
# Legacy file path. Kept as an explicit standalone/dev fallback and debugging
# mirror. Automatic reconciliation never treats it as authoritative: cloud
# runs require a complete DB-backed cache read/write before replacing UNI rows.


class FormSummaryCacheDurabilityError(RuntimeError):
    """Raised when automatic reconciliation cannot prove durable cache state."""


def _load_form_summary_cache(*, require_durable_db: bool = False) -> dict:
    """Load the {filing_id: form_summary, "_committees": {...}} cache.

    Source of truth is the DB-backed `form_summary_cache` table (added
    in migration 114). Explicit standalone/dev callers may fall back to the
    legacy file when the DB is unavailable. Automatic reconciliation passes
    ``require_durable_db=True`` and fails closed instead: a local/empty cache
    cannot prove it is complete enough for destructive UNI replacement.

    Why this matters (T0.3, 2026-05-16): the file alone was lost on
    ephemeral GitHub Actions runners and could not be rebuilt from
    the NetFile RSS feed, which only carries a rolling 15-day window.
    All Form 460 reconciliations went silently dead after the April
    semi-annual filings aged out of RSS. DB persistence is the fix.
    """
    cache: dict = {"_committees": {}}

    # Try DB first.
    try:
        from db import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT filing_id, committee, summary "
                    "FROM form_summary_cache"
                )
                for filing_id, committee, summary in cur.fetchall():
                    cache[filing_id] = summary
                    cache["_committees"][filing_id] = committee
            return cache
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as exc:
        if require_durable_db:
            raise FormSummaryCacheDurabilityError(
                f"durable form_summary_cache read failed: {exc}"
            ) from exc
        # DB unreachable or table missing — fall back to file.
        print(f"  (form_summary_cache DB unavailable: {exc} — falling back to file)")

    if not FORM_SUMMARY_CACHE.exists():
        return cache
    try:
        with open(FORM_SUMMARY_CACHE, encoding="utf-8") as f:
            file_cache = json.load(f)
        file_cache.setdefault("_committees", {})
        return file_cache
    except (json.JSONDecodeError, OSError):
        return cache


def _upsert_form_summary_row(
    cur,
    *,
    filing_id: str,
    committee: str,
    summary: dict,
) -> None:
    """Write one exact current-run summary with amendment replacement."""
    period_start = summary.get("period_start")
    period_end = summary.get("period_end")
    cur.execute(
        """DELETE FROM form_summary_cache
            WHERE filing_id = %s
               OR (committee = %s
                   AND summary->>'period_start' = %s
                   AND summary->>'period_end' = %s)""",
        (filing_id, committee, period_start, period_end),
    )
    cur.execute(
        """INSERT INTO form_summary_cache
              (filing_id, committee, summary, updated_at)
           VALUES (%s, %s, %s::jsonb, NOW())""",
        (filing_id, committee, json.dumps(summary)),
    )


def _put_form_summary_in_cache(
    cache: dict,
    *,
    filing_id: str,
    committee: str,
    summary: dict,
) -> None:
    """Replace this filing or a superseded amendment in an in-memory cache."""
    committees = cache.setdefault("_committees", {})
    period_key = (summary.get("period_start"), summary.get("period_end"))
    for existing_id, existing_summary in list(cache.items()):
        if existing_id in {"_committees", filing_id}:
            continue
        if committees.get(existing_id) != committee:
            continue
        existing_period = (
            existing_summary.get("period_start"),
            existing_summary.get("period_end"),
        )
        if existing_period == period_key:
            cache.pop(existing_id, None)
            committees.pop(existing_id, None)
    cache[filing_id] = dict(summary)
    committees[filing_id] = committee


def persist_form460_summary(
    *,
    filing_id: str,
    committee: str,
    summary: dict,
) -> bool:
    """Durably cache one newly validated Form 460 summary.

    This only persists the exact current-run extraction. It never infers a
    terminal-zero result and never scans historical committee artifacts.
    The caller retains the summary in process memory if this soft-fails.
    """
    try:
        from db import get_connection

        conn = get_connection()
    except Exception as exc:
        print(f"  form-summary cache connection unavailable: {exc}")
        return False
    try:
        with conn.cursor() as cur:
            _upsert_form_summary_row(
                cur,
                filing_id=str(filing_id),
                committee=str(committee),
                summary=dict(summary),
            )
        conn.commit()
        return True
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"  form-summary cache persistence failed: {exc}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _save_form_summary_cache(
    cache: dict,
    *,
    require_durable_db: bool = False,
) -> bool:
    """Persist cache to DB (primary) + file (fallback / debugging).

    Writes to the `form_summary_cache` table via DELETE-then-INSERT keyed
    on either `filing_id` (same filing re-extracted) OR
    `(committee, period_start, period_end)` (amendment filing for the
    same underlying Form 460). The schema has a unique expression index
    on `(committee, period_start, period_end)` enforcing the invariant
    (migration 115). Without the DELETE step, an amendment with a new
    filing_id would violate the unique index — see D56.

    After a successful required DB write (or in standalone fallback mode),
    atomically mirrors the cache to FORM_SUMMARY_CACHE for local debugging.
    Automatic mode raises before the file write when DB persistence fails,
    preventing an ephemeral artifact from masquerading as durable authority.
    """
    # Try DB persistence first.
    db_ok = False
    db_error: Exception | None = None
    try:
        from db import get_connection
        conn = get_connection()
        try:
            committees = cache.get("_committees", {})
            with conn.cursor() as cur:
                for filing_id, summary in cache.items():
                    if filing_id == "_committees":
                        continue
                    committee = committees.get(filing_id, "")
                    if not committee:
                        continue
                    _upsert_form_summary_row(
                        cur,
                        filing_id=filing_id,
                        committee=committee,
                        summary=summary,
                    )
            conn.commit()
            db_ok = True
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as exc:
        db_error = exc
        print(f"  ⚠ form_summary_cache DB persistence failed: {exc}")

    if require_durable_db and not db_ok:
        # Do not create an ephemeral fallback artifact for an automatic run
        # and then accidentally treat it as authoritative. The coordinator
        # must retry before any destructive reconciliation occurs.
        raise FormSummaryCacheDurabilityError(
            f"durable form_summary_cache write failed: {db_error}"
        ) from db_error

    # Always write the file too — cheap insurance for local debugging.
    # If DB also failed, this is the only persistence path.
    import tempfile
    try:
        FORM_SUMMARY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=FORM_SUMMARY_CACHE.parent,
            suffix=".tmp", delete=False,
        ) as tmp:
            json.dump(cache, tmp, indent=2, ensure_ascii=False, sort_keys=True)
            tmp_path = Path(tmp.name)
        tmp_path.replace(FORM_SUMMARY_CACHE)
    except OSError as exc:
        if not db_ok:
            # Both paths failed — surface loudly. Reconciliation will be
            # stale next run.
            print(f"  ⚠⚠ form_summary_cache could not be persisted "
                  f"(DB and file both failed): {exc}")
    return db_ok


def discover_and_extract_all_form460_summaries(
    client=None,
    *,
    require_durable_cache: bool = False,
) -> dict:
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
    back to a committee name without a second RSS round-trip. With
    ``require_durable_cache=True``, both the initial full-cache read and any
    current-run additions must succeed against Postgres or the function
    raises before reconciliation can delete existing UNI rows.
    """
    from netfile_client import fetch_filing_rss
    from netfile_paper_extractor import (
        download_paper_filing, parse_form460_summary_with_vision,
        PDF_CACHE_DIR, classify_form,
        form460_summary_attempted_this_run,
        get_form460_summary_run_cache,
        record_form460_summary_run_failure,
    )

    cache = _load_form_summary_cache(
        require_durable_db=require_durable_cache,
    )
    cache.setdefault("_committees", {})

    new_count = 0
    # The NetFile source phase may have extracted this same Form 460 moments
    # ago. Merge that exact validated output before reading RSS so DB-cache
    # lag/failure cannot trigger a duplicate paid summary call.
    for filing_id, entry in get_form460_summary_run_cache().items():
        if (
            filing_id not in cache
            or cache[filing_id] != entry["summary"]
        ):
            new_count += 1
        _put_form_summary_in_cache(
            cache,
            filing_id=filing_id,
            committee=entry["committee"],
            summary=entry["summary"],
        )

    rss = fetch_filing_rss()
    for filing in rss:
        if classify_form(filing.get("form_type", "")) != "460":
            continue
        filing_id = str(filing.get("filing_id", ""))
        if not filing_id or filing_id in cache:
            cache["_committees"][filing_id] = filing.get("committee", "")
            continue

        committee = filing.get("committee", "")
        if form460_summary_attempted_this_run(filing_id):
            # A failed source-phase attempt remains retryable next run, but a
            # second paid attempt in this same sync would only amplify cost.
            print(f"  [defer] {committee} filing {filing_id}: already attempted this run")
            continue
        print(f"  [extract] {committee} filing {filing_id}")
        try:
            if client is None:
                from llm_client import LLMClient

                client = LLMClient()
            pdf_path = download_paper_filing(filing_id, output_dir=PDF_CACHE_DIR)
            summary = parse_form460_summary_with_vision(
                pdf_path, filing_id, committee, client
            )
        except Exception as exc:
            print(f"    failed: {exc}")
            record_form460_summary_run_failure(filing_id, str(exc))
            continue
        if summary:
            _put_form_summary_in_cache(
                cache,
                filing_id=filing_id,
                committee=committee,
                summary=summary,
            )
            new_count += 1
            print(
                f"    monetary=${float(summary.get('monetary_this_period', 0)):,.2f}, "
                f"loans=${float(summary.get('loans_this_period', 0)):,.2f}, "
                f"unitemized=${float(summary.get('unitemized_this_period', 0)):,.2f}"
            )

    if new_count:
        _save_form_summary_cache(
            cache,
            require_durable_db=require_durable_cache,
        )
        print(f"  cached {new_count} new Form 460 summary/summaries")
    return cache


def _preflight_form_summary_cache(
    conn,
    cache: dict,
    city_fips: str,
) -> list[dict]:
    """Validate reporting periods and committee identity before any insert.

    A successful DB read is not enough: historical cache rows predate the
    strict extraction contract. A malformed or unmapped row cannot establish
    a source-backed reconciliation obligation; preserve it for review.
    """
    if not isinstance(cache, dict):
        raise FormSummaryCacheDurabilityError(
            "form_summary_cache payload must be an object"
        )
    committees_map = cache.get("_committees")
    if not isinstance(committees_map, dict):
        raise FormSummaryCacheDurabilityError(
            "form_summary_cache is missing its committee mapping"
        )

    validated: list[dict] = []
    seen_periods: set[tuple[str, str, str]] = set()
    for raw_filing_id, summary in cache.items():
        if raw_filing_id == "_committees":
            continue
        filing_id = str(raw_filing_id).strip()
        if not filing_id or not isinstance(summary, dict):
            raise FormSummaryCacheDurabilityError(
                f"invalid Form 460 cache row for filing {raw_filing_id!r}"
            )

        committee = committees_map.get(raw_filing_id)
        if not isinstance(committee, str) or not committee.strip():
            raise FormSummaryCacheDurabilityError(
                f"filing {filing_id} has no committee mapping"
            )
        committee = committee.strip()

        period_start = summary.get("period_start")
        period_end = summary.get("period_end")
        if not isinstance(period_start, str) or not isinstance(period_end, str):
            raise FormSummaryCacheDurabilityError(
                f"filing {filing_id} is missing a reporting-period date"
            )
        period_start = period_start.strip()
        period_end = period_end.strip()
        try:
            start_date = date.fromisoformat(period_start)
            end_date = date.fromisoformat(period_end)
        except ValueError as exc:
            raise FormSummaryCacheDurabilityError(
                f"filing {filing_id} has malformed reporting period "
                f"{period_start!r}..{period_end!r}"
            ) from exc
        if (
            start_date.isoformat() != period_start
            or end_date.isoformat() != period_end
            or start_date > end_date
        ):
            raise FormSummaryCacheDurabilityError(
                f"filing {filing_id} has invalid reporting period "
                f"{period_start!r}..{period_end!r}"
            )

        raw_monetary = summary.get("monetary_this_period")
        if isinstance(raw_monetary, bool):
            raise FormSummaryCacheDurabilityError(
                f"filing {filing_id} has a non-numeric monetary total"
            )
        try:
            monetary_form = float(raw_monetary)
        except (TypeError, ValueError) as exc:
            raise FormSummaryCacheDurabilityError(
                f"filing {filing_id} has a non-numeric monetary total"
            ) from exc
        # Form 460 period totals can legitimately be negative when returned
        # contributions or other corrections exceed new receipts. Filing
        # 216805176, for example, reports -$1,000 + $600 + $300 = -$100.
        # Reconciliation never synthesizes a negative UNI row: a negative gap
        # follows the existing DB-over review path. Reject only non-finite data.
        if not math.isfinite(monetary_form):
            raise FormSummaryCacheDurabilityError(
                f"filing {filing_id} has an invalid monetary total"
            )

        period_key = (committee, period_start, period_end)
        if period_key in seen_periods:
            raise FormSummaryCacheDurabilityError(
                f"duplicate Form 460 cache period for {committee}: "
                f"{period_start}..{period_end}"
            )
        seen_periods.add(period_key)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM committees WHERE city_fips = %s AND name = %s",
                (city_fips, committee),
            )
            row = cur.fetchone()
        if not row:
            # A zero-dollar filing cannot produce a reconciliation row and
            # therefore does not require us to invent a committee identity.
            # This is common for newly formed committees whose first filing
            # predates the committee registry (for example FPPC 1490877).
            # The later prior-UNI coverage proof still fails closed if a row
            # for this skipped filing was ever published.
            if abs(monetary_form) < 1.0:
                continue
            raise FormSummaryCacheDurabilityError(
                f"filing {filing_id} references unknown committee {committee!r}"
            )

        validated.append({
            "filing_id": filing_id,
            "committee": committee,
            "committee_id": row[0],
            "period_start": period_start,
            "period_end": period_end,
            "monetary_form": monetary_form,
            "itemized_form": summary.get("itemized_this_period"),
            "unitemized_form": summary.get("unitemized_this_period"),
        })
    return validated


def reconcile_paper_filings_to_forms(
    conn,
    city_fips: str = "0660620",
    form_summary_cache: dict | None = None,
) -> dict:
    """Insert only an explicit, reconciled Form 460 unitemized aggregate.

    Both itemized and unitemized source amounts must be finite, their sum
    must match monetary receipts, and retained non-UNI monetary rows must
    match the itemized amount. A deficit alone proves no donor category.
    Existing UNI rows are never deleted or rewritten: mismatches, uncovered
    rows and amendment ambiguity require a separate source-backed repair.
    The wrapper propagates these issues as incomplete work to monitoring.
    """
    stats = {
        "filings_examined": 0,
        "rows_synthesized": 0,
        "dollars_synthesized": 0.0,
        "filings_already_matched": 0,
        "filings_over": 0,  # DB exceeds form (data quality issue)
    }

    # The orchestrated sync passes the exact cache returned by discovery so
    # reconciliation cannot discard current-run in-memory summaries by
    # immediately reloading a lagging durable cache. Standalone callers keep
    # the historical load behavior.
    cache = (
        form_summary_cache
        if form_summary_cache is not None
        else _load_form_summary_cache()
    )
    validated_filings = _preflight_form_summary_cache(conn, cache, city_fips)
    over_filings: list[dict] = []
    issues: list[dict] = []
    if not any(key != "_committees" for key in cache):
        issues.append({"filing_id": "<cache>",
                       "reason": "Empty summary cache cannot establish reconciliation coverage"})
    synth_records: list[dict] = []
    with conn.cursor() as cur:
        cur.execute(
            """SELECT filing_id, committee_id, contribution_date, amount
                 FROM contributions
                WHERE city_fips = %s AND entity_code = 'UNI'""",
            (city_fips,),
        )
        prior_uni_rows = cur.fetchall()
    prior_by_period: dict[tuple[str, str], list[tuple]] = {}
    for prior_filing, prior_committee, prior_date, prior_amount in prior_uni_rows:
        period_end = prior_date.isoformat() if hasattr(prior_date, "isoformat") else str(prior_date)
        prior_by_period.setdefault((str(prior_committee), period_end), []).append(
            (str(prior_filing or ""), float(prior_amount))
        )

    # Validate and inspect the complete input before performing any inserts.
    for filing in validated_filings:
        filing_id = filing["filing_id"]
        committee = filing["committee"]
        committee_id = filing["committee_id"]
        period_start = filing["period_start"]
        period_end = filing["period_end"]
        monetary_form = filing["monetary_form"]
        stats["filings_examined"] += 1

        def unresolved(reason: str, **detail) -> None:
            issues.append({"filing_id": filing_id, "committee": committee,
                           "period_start": period_start, "period_end": period_end,
                           "reason": reason, **detail})

        raw_itemized = filing["itemized_form"]
        raw_unitemized = filing["unitemized_form"]
        try:
            if isinstance(raw_itemized, bool) or isinstance(raw_unitemized, bool):
                raise ValueError("Boolean source amount")
            itemized_form = float(raw_itemized)
            unitemized_form = float(raw_unitemized)
        except (TypeError, ValueError):
            unresolved("Explicit itemized and unitemized source amounts are missing or invalid")
            continue
        if (not math.isfinite(itemized_form) or not math.isfinite(unitemized_form)
                or unitemized_form < 0
                or round(itemized_form + unitemized_form - monetary_form, 2) != 0):
            unresolved("Explicit source amounts do not reconcile to monetary receipts")
            continue

        # Reconcile against MONETARY (Schedule A, Line 1) — excludes
        # loans (Schedule B, separate financial instrument) and
        # nonmonetary (Schedule C, in-kind goods/services). Loans and
        # nonmonetary are tracked in `contributions.contribution_type`
        # so they show up in DB sums; we filter them here.
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
        if not math.isfinite(db_monetary):
            unresolved("Retained monetary amount is invalid; preserved unchanged")
            continue

        gap = round(monetary_form - db_monetary, 2)
        if gap < 0:
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
        if round(itemized_form - db_monetary, 2) != 0 or round(gap - unitemized_form, 2) != 0:
            unresolved("Itemized extraction does not match the source; the deficit is not an unitemized donation",
                       itemized_form=itemized_form, db_itemized=db_monetary,
                       unitemized_form=unitemized_form, monetary_gap=gap)
            continue

        existing = prior_by_period.get((str(committee_id), period_end), [])
        if existing:
            if len(existing) == 1 and existing[0][0] == filing_id and round(existing[0][1] - unitemized_form, 2) == 0:
                stats["filings_already_matched"] += 1
            else:
                unresolved("Existing UNI rows need a separate source-backed repair; preserved unchanged",
                           retained_rows=len(existing), retained_total=sum(row[1] for row in existing),
                           unitemized_form=unitemized_form)
            continue
        if unitemized_form == 0:
            stats["filings_already_matched"] += 1
            continue

        synth_records.append({
            "contributor_name": UNITEMIZED_DONOR_NAME,
            "contributor_employer": "",
            "amount": unitemized_form,
            "date": period_end,
            "committee": committee,
            "occupation": "",
            "source": "fppc_paper",
            "filing_id": filing_id,
            "filer_fppc_id": "",
            "entity_code": "UNI",
        })
        print(f"  {committee} filing {filing_id}: recording ${unitemized_form:,.2f} source-reported unitemized")
        stats["rows_synthesized"] += 1
        stats["dollars_synthesized"] += unitemized_form

    # Uncovered historical rows also remain intact. A partial cache cannot
    # quietly claim that those source obligations were reconciled.
    validated_ids = {filing["filing_id"] for filing in validated_filings}
    validated_periods = {
        (str(filing["committee_id"]), filing["period_end"])
        for filing in validated_filings
    }
    for prior_filing_id, prior_committee_id, prior_date, _prior_amount in prior_uni_rows:
        rendered_id = str(prior_filing_id or "").strip()
        rendered_date = (
            prior_date.isoformat()
            if hasattr(prior_date, "isoformat")
            else str(prior_date or "").strip()
        )
        if rendered_id and rendered_id in validated_ids:
            continue
        if (str(prior_committee_id), rendered_date) in validated_periods:
            continue
        issues.append({"filing_id": rendered_id or "<missing filing_id>",
                       "reason": "Summary cache does not cover prior UNI filing; preserved unchanged"})

    # Only new, proven aggregates are written. No global UNI deletion and no
    # implicit repair of existing rows during a routine observation.
    try:
        if synth_records:
            load_contributions_to_db(
                conn,
                synth_records,
                city_fips=city_fips,
                commit=False,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    stats["over_filings"] = over_filings
    stats["reconciliation_issues"] = issues
    stats["incomplete_count"] = len(issues)
    stats["incomplete_reasons"] = [f"Form 460 {issue['filing_id']}: {issue['reason']}" for issue in issues]
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
