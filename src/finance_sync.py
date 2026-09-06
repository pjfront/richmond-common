"""Acquire Richmond, California electronic finance evidence without model calls.

Default is read-only dry run. --apply stores raw JSON, local 496 PDFs, assertions
and coverage in one transaction. It never rewrites legacy contributions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path

import requests

from finance_ledger import TYPES, FORMS, assertion_from_netfile, clean, parse_496_context, reconcile
from netfile_client import API_BASE, fetch_all_transactions, get_filing_info


def acquire_snapshot(year: int, through: str, *, fetch=fetch_all_transactions, filing_info=get_filing_info, download=None) -> dict:
    """Acquire all supported electronic forms atomically; failures raise.

    Calendar scope is stable across poll dates. Never mix arbitrary overlapping
    windows or filer subsets in the same source projection.
    """
    if date.fromisoformat(through).year != year:
        raise ValueError("Through date must be in the selected calendar year")
    since = f"{year}-01-01"
    scope = f"0660620:calendar-{year}"
    raw, metadata, documents, contexts = [], {}, {}, {}
    for kind in TYPES:
        raw.extend(fetch(transaction_type=kind, date_start=since, date_end=through, city_fips="0660620"))
    for filing in sorted({str(tx["filingId"]) for tx in raw}):
        metadata[filing] = filing_info(filing)
    for tx in raw:
        if tx["transactionType"] != 19:
            continue
        filing = str(tx["filingId"])
        if filing not in documents:
            url = f"{API_BASE}/public/image/{filing}"
            if download:
                pdf = download(url)
            else:
                response = requests.get(url, timeout=45)
                response.raise_for_status()
                pdf = response.content
            if not pdf.startswith(b"%PDF-"):
                raise ValueError("496 source did not return a PDF")
            documents[filing] = pdf
        key = filing, clean(tx.get("candidate"))
        if key not in contexts:
            contexts[key] = parse_496_context(documents[filing], key[1])
    assertions = [assertion_from_netfile(tx, metadata[str(tx["filingId"])], scope,
                  contexts.get((str(tx["filingId"]), clean(tx.get("candidate"))))) for tx in raw]
    events = reconcile(assertions)
    now = datetime.now(timezone.utc).isoformat()
    coverage = []
    for kind, form in FORMS.items():
        rows = [a for a in assertions if a["transaction_type"] == kind]
        pending = sum(a["is_current"] and a["reconciliation_status"] == "pending_review" for a in rows)
        limitations = [
            "Richmond, California NetFile electronic records only; paper filings and disclosures filed solely with other agencies are not included.",
            "Activity dates define this calendar window; this is not an election-specific or campaign-to-date total.",
            "Latest non-superseded source records were requested. Signed adjustments, loans and noncash values remain separate.",
        ]
        if kind == 19:
            limitations.append("Form 496 rapid reports only; periodic 460/461 independent spending is not yet included. The form has no election-date field.")
        if kind == 4:
            limitations.append("Form 496 Part 3 reports newly received funding; it is not independent spending and is reconciled with other receipt reports when exact and unique.")
        if kind == 12:
            limitations.append("Schedule B1 records may include loan balances and activity; these values are not treated as cash contributions or net new borrowing.")
        coverage.append(dict(source="netfile", form_type=form, scope_key=scope,
                             status="partial", checked_at=now, activity_from=since, activity_through=through,
                             filing_count=len({a["filing_id"] for a in rows}), assertion_count=len(rows), pending_count=pending,
                             limitations=limitations, source_url="https://public.netfile.com/pub2/?AID=RICH",
                             extracted_at=now, source_tier=1, confidence_score=1, snapshot_complete=True))
    return dict(assertions=assertions, events=events, coverage=coverage, documents=documents,
                acquisition_metrics={"filing_metadata_requests": len(metadata), "pdf_downloads": len(documents),
                                     "pdf_bytes": sum(len(pdf) for pdf in documents.values()), "model_calls": 0})


def save_snapshot(conn, snapshot: dict) -> dict:
    from db.documents import ingest_document
    from db.finance import persist_finance_snapshot
    # Raw JSON includes full original IDs/direction and source amendment metadata.
    document_ids = {}
    for filing, pdf in snapshot["documents"].items():
        document_ids[filing] = ingest_document(conn, "0660620", "netfile_496", pdf, 1,
            source_url=f"{API_BASE}/public/image/{filing}", source_identifier=filing,
            mime_type="application/pdf", metadata={"parser": "netfile-496-layout-v1"}, commit=False)
    for a in snapshot["assertions"]:
        raw_id = ingest_document(conn, "0660620", "netfile_transaction",
            json.dumps(a["raw_payload"], sort_keys=True).encode(), 1, source_url=a["source_url"],
            source_identifier=a["record_key"], mime_type="application/json", commit=False)
        a["document_id"] = str(document_ids.get(a["filing_id"], raw_id))
    return persist_finance_snapshot(conn, snapshot["assertions"], snapshot["events"], snapshot["coverage"])


def public_summary(snapshot: dict) -> dict:
    """Aggregate diagnostics; never print personal donor names or addresses."""
    return {"assertions": len(snapshot["assertions"]), "events": len(snapshot["events"]),
            "pdfs": len(snapshot["documents"]),
            "acquisition_metrics": snapshot.get("acquisition_metrics", {}),
            "pending": dict(Counter(a["review_reason"] for a in snapshot["assertions"] if a["review_reason"])),
            "forms": {c["form_type"]: {k: c[k] for k in ("assertion_count", "filing_count", "pending_count", "status")} for c in snapshot["coverage"]}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--through", default=date.today().isoformat())
    parser.add_argument("--apply", action="store_true", help="Persist new evidence/projection; no legacy repair")
    parser.add_argument("--dry-run", action="store_true", help="Explicit read-only acquisition (default)")
    parser.add_argument("--report", type=Path, help="Write aggregate-only JSON diagnostics")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("Choose --apply or --dry-run")
    snapshot = acquire_snapshot(args.year, args.through)
    summary = public_summary(snapshot)
    if args.apply:
        from db import get_connection
        conn = get_connection()
        try:
            with conn:
                summary["persistence"] = save_snapshot(conn, snapshot)
        finally:
            conn.close()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
