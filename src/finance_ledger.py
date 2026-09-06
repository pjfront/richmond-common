"""Deterministic finance evidence and conservative cross-report reconciliation.

Reports are assertions, not separate gifts. Never infer amendments from dates,
amounts, or filing-number order. Original payloads and explicit lineage remain
immutable; only the selected current projection changes. No model calls.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any

FORMS = {0: "F460A", 1: "F460C", 4: "F496P3", 12: "F460B1", 19: "S496", 20: "F497P1", 21: "F497P2"}
TYPES = tuple(FORMS)
RECEIPT_TYPES = {0, 4, 20, 21}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def clean(value: Any) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def normalized_name(value: str | None) -> str:
    # Formatting only. No fuzzy matching, punctuation removal, or entity guesses.
    return " ".join((value or "").casefold().split())


def fppc_id(value: Any) -> str | None:
    """Pending/unknown IDs must not identify unrelated committees as one party."""
    value = clean(value)
    return value if value and re.fullmatch(r"\d{6,7}", value) else None


def iso_date(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def assertion_from_netfile(tx: dict, info: dict, scope_key: str, pdf_context: dict | None = None) -> dict:
    """Explicit Connect2 enum (not the unrelated legacy upload enum)."""
    kind = int(tx["transactionType"])
    if kind not in FORMS or not clean(tx.get("id")) or not clean(tx.get("filingId")):
        raise ValueError("Unsupported transaction type or missing source identity")
    if str(info.get("filingId")) != str(tx["filingId"]):
        raise ValueError("Mismatched filing metadata")
    context = pdf_context or {}
    payload = {"transaction": tx, "filing_info": info, "pdf_context": context, "parser_version": 1}
    reporter, reporter_id = clean(tx.get("filerName")), fppc_id(tx.get("filerFppcId"))
    counterparty, counterparty_id = clean(tx.get("name")), fppc_id(tx.get("transactionFppcId"))
    try:
        amount = Decimal(str(tx.get("amount"))).quantize(Decimal("0.01"))
        if not amount.is_finite():
            amount = None
    except (InvalidOperation, TypeError):
        amount = None
    event_kind = {1: "noncash", 12: "loan", 19: "independent_expenditure", 21: "transfer"}.get(kind, "receipt")
    amount_kind = {1: "reported_noncash_value", 12: "reported_loan_amount"}.get(kind, "monetary")
    # A signed negative entry proves an adjustment, not necessarily a cash refund.
    if amount is not None and amount < 0:
        amount_kind = "negative_adjustment"
    donor, donor_id, recipient, recipient_id = counterparty, counterparty_id, reporter, reporter_id
    if kind == 21:
        donor, donor_id, recipient, recipient_id = reporter, reporter_id, counterparty, counterparty_id
    if kind == 19:
        # Expenditure API has no payee identity. A spender is not an original donor.
        donor = donor_id = recipient = recipient_id = None
    candidate = clean(tx.get("candidate")) if kind == 19 else None
    measure = clean(tx.get("ballotMeasureName")) if kind == 19 else None
    stance = context.get("support_oppose") if context.get("candidate_name") == candidate else None
    reasons = []
    if amount is None or not iso_date(tx.get("date")) or not reporter:
        reasons.append("missing_amount_date_or_reporting_filer")
    if kind in RECEIPT_TYPES and (not donor or not recipient):
        reasons.append("missing_reported_counterparty")
    if kind == 19 and (not (candidate or measure) or stance not in {"S", "O"}):
        reasons.append("independent_expenditure_target_or_stance_unverified")
    return {
        "source": "netfile", "scope_key": scope_key,
        "record_key": f"{tx['filingId']}:{tx['id']}", "content_hash": digest(payload),
        "filing_id": str(tx["filingId"]), "transaction_id": str(tx["id"]),
        "form_type": FORMS[kind], "transaction_type": kind,
        "reporting_filer_name": reporter or "", "reporting_filer_fppc_id": reporter_id,
        "donor_name": donor, "donor_fppc_id": donor_id, "recipient_name": recipient, "recipient_fppc_id": recipient_id,
        "event_kind": event_kind, "amount": amount, "amount_kind": amount_kind,
        "activity_date": iso_date(tx.get("date")), "support_oppose": stance,
        "candidate_name": candidate, "measure_name": measure,
        # Neither committee year nor transaction date proves the election.
        "election_date": None, "report_number": context.get("report_number"),
        "amends_filing_id": clean(info.get("amends")), "amended_by_filing_id": clean(info.get("amendedBy")),
        "amendment_sequence": int(info.get("amendmentSequenceNumber") or 0),
        "raw_payload": payload,
        "source_url": f"https://netfile.com/Connect2/api/public/image/{tx['filingId']}",
        "extracted_at": datetime.now(timezone.utc).isoformat(), "source_tier": 1,
        "confidence_score": Decimal("0.99") if not reasons else Decimal("0.50"),
        "is_current": not bool(info.get("amendedBy")),
        "reconciliation_status": "pending_review" if reasons else "source_reported",
        "canonical_event_key": None, "review_reason": ";".join(reasons) or None,
    }


def reconciliation_key(a: dict, name_ids: dict | None = None) -> tuple:
    # The receiving committee must have a reported identifier. Same-filer
    # receipts may match exact donor text when no donor identifier is disclosed.
    reported_name = normalized_name(a["donor_name"])
    ids = (name_ids or {}).get(reported_name, set())
    donor_id = a.get("donor_fppc_id") or (next(iter(ids)) if len(ids) == 1 else None)
    donor = ("id", donor_id) if donor_id else ("reported_name", reported_name)
    recipient = ("id", a["recipient_fppc_id"]) if a.get("recipient_fppc_id") else ("unidentified", a["record_key"])
    return donor, recipient, a["amount"], a["activity_date"], a["amount_kind"]


def reconcile(assertions: list[dict]) -> list[dict]:
    """Keep same-role repeated gifts; match unique exact cross-report claims.

    Conflicting multiplicity is reviewable, never destroyed. A source-reported
    event is evidence of what a source said, not completeness of economic activity.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    name_ids = defaultdict(set)
    for a in assertions:
        if a["is_current"] and a.get("donor_fppc_id"):
            name_ids[normalized_name(a.get("donor_name"))].add(a["donor_fppc_id"])
    # Timing proximity is an operator question, not proof of duplication. Keep
    # recipient periodic accounting visible; hold only the unmatched rapid or
    # outgoing claim that might repeat it, with both source assertions retained.
    periodic = defaultdict(list)
    for a in assertions:
        if a["is_current"] and not a["review_reason"] and a["transaction_type"] == 0:
            k = reconciliation_key(a, name_ids)
            periodic[k[:3] + k[4:]].append(a)
    for a in assertions:
        if a["is_current"] and not a["review_reason"] and a["transaction_type"] in {4, 20, 21}:
            k = reconciliation_key(a, name_ids)
            candidates = periodic.get(k[:3] + k[4:], [])
            if candidates and not any(p["activity_date"] == a["activity_date"] for p in candidates):
                if any(abs((date.fromisoformat(p["activity_date"]) - date.fromisoformat(a["activity_date"])).days) <= 14 for p in candidates):
                    a.update(reconciliation_status="pending_review", review_reason="cross_report_date_disagreement")
    for a in assertions:
        if not a["is_current"] or a["review_reason"]:
            continue
        key = reconciliation_key(a, name_ids) if a["transaction_type"] in RECEIPT_TYPES else ("single", a["record_key"])
        groups[key].append(a)
    events = []
    for group in groups.values():
        roles = defaultdict(list)
        for a in group:
            roles[a["transaction_type"]].append(a)
        if len(roles) > 1 and any(len(rows) != 1 for rows in roles.values()):
            for a in group:
                a.update(reconciliation_status="pending_review", review_reason="ambiguous_cross_report_multiplicity")
            continue
        # Different IDs with the same source role are separate reported events.
        bundles = [group] if len(roles) > 1 else [[a] for a in group]
        for bundle in bundles:
            representative = min(bundle, key=lambda a: ({0: 0, 20: 1, 4: 2, 21: 3}.get(a["transaction_type"], 0), a["record_key"]))
            event_key = "netfile:" + digest(sorted(a["record_key"] for a in bundle))
            status = "matched_exact" if len(bundle) > 1 else "source_reported"
            for a in bundle:
                a.update(canonical_event_key=event_key, reconciliation_status=status)
            keys = ("source", "scope_key", "event_kind", "reporting_filer_name", "reporting_filer_fppc_id",
                    "donor_name", "donor_fppc_id", "recipient_name", "recipient_fppc_id", "amount", "amount_kind",
                    "activity_date", "support_oppose", "candidate_name", "measure_name", "election_date",
                    "source_url", "extracted_at", "source_tier", "confidence_score")
            event = {key: representative[key] for key in keys}
            event.update(event_key=event_key, description=clean(representative["raw_payload"]["transaction"].get("description")),
                         filing_ids=sorted({a["filing_id"] for a in bundle}), source_urls=sorted({a["source_url"] for a in bundle}),
                         assertion_keys=[(a["record_key"], a["content_hash"]) for a in bundle], reconciliation_status=status)
            events.append(event)
    return sorted(events, key=lambda e: e["event_key"])


def parse_496_context(pdf: bytes, candidate: str | None) -> dict:
    """Verify a printed NetFile 496 candidate checkbox with PDF geometry.

    Only a recognized layout with exactly one mark below candidate SUPPORT or
    OPPOSE qualifies. Scans, ambiguous marks and measure layouts stay pending.
    The form has no election-date field, so no election is inferred here.
    """
    import pymupdf as fitz
    result = {"pdf_sha256": hashlib.sha256(pdf).hexdigest(), "parser": "netfile-496-layout-v1"}
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        page = doc[0]
        text = page.get_text()
        if not candidate or "496 Independent Expenditure Report" not in text or candidate not in text:
            return result
        words = [(fitz.Rect(w[:4]) * page.rotation_matrix, w[4]) for w in page.get_text("words")]
        headings = [(rect, word) for rect, word in words if word in {"SUPPORT", "OPPOSE"}]
        marks = [(rect, word) for rect, word in words if word == "X"]
        # Candidate columns occupy the left half of this published form. Marks
        # have to be beneath a label, within the same narrow column.
        matches = []
        for heading, word in headings:
            if heading.x1 > page.rect.width * 0.52:
                continue
            for mark, _ in marks:
                if heading.x0 - 2 <= (mark.x0 + mark.x1) / 2 <= heading.x1 + 2 and 0 <= mark.y0 - heading.y1 <= 16:
                    matches.append("S" if word == "SUPPORT" else "O")
        # Ensure the candidate text appears inside the candidate-name field,
        # rather than merely in a filer name or an expenditure description.
        candidate_rects = [r * page.rotation_matrix for r in page.search_for(candidate)]
        if len(matches) == 1 and any(r.x1 < page.rect.width * 0.52 and 195 < r.y0 < 237 for r in candidate_rects):
            result.update(candidate_name=candidate, support_oppose=matches[0], evidence_page=1)
    return result
