"""Pure compact projection of a completed finance_sync.acquire_snapshot result.

Reads reconciled electronic events and all-eight-form acquisition coverage.
Does NOT read aggregate campaign totals, legacy donor tables or AI narratives.
No fetching, database writes, credentials, raw documents or model calls occur
here. Raw assertion/address payloads never enter the returned public rows.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from urllib.parse import urlsplit

from finance_ledger import FORMS

PUBLIC_SCOPE = "0660620:calendar-2026"
PUBLIC_FROM = "2026-01-01"
PUBLIC_THROUGH = "2026-11-03"
EVENT_COLUMNS = tuple("event_key scope_key event_kind donor_name donor_fppc_id recipient_name recipient_fppc_id reporting_filer_name reporting_filer_fppc_id amount amount_kind activity_date support_oppose candidate_name measure_name election_date filing_ids source_urls source_url extracted_at source_tier confidence_score reconciliation_status".split())
COVERAGE_COLUMNS = tuple("source form_type scope_key status checked_at activity_from activity_through filing_count assertion_count pending_count limitations source_url extracted_at source_tier confidence_score".split())
EVENT_KINDS = frozenset({"receipt", "transfer", "independent_expenditure", "refund", "loan", "noncash"})
PUBLIC_STATUSES = frozenset({"source_reported", "matched_exact"})


class FinanceProjectionError(ValueError):
    """Aggregate-only errors: never include rows, donor names or source payloads."""


def _date(value: Any) -> str:
    try:
        parsed = date.fromisoformat(str(value))
        if parsed.isoformat() != str(value):
            raise ValueError
        return parsed.isoformat()
    except (ValueError, TypeError) as exc:
        raise FinanceProjectionError("Invalid calendar date in finance projection") from exc


def _timestamp(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return str(value)
    except (ValueError, TypeError) as exc:
        raise FinanceProjectionError("Missing or invalid finance provenance timestamp") from exc


def _decimal(value: Any) -> Decimal:
    try:
        if value is None or isinstance(value, bool):
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError
        return result
    except (ValueError, InvalidOperation) as exc:
        raise FinanceProjectionError("Invalid finite finance numeric value") from exc


def _text(value: Any, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise FinanceProjectionError("Missing or invalid public finance text field")
    return value


def _source_url(value: Any) -> str:
    text = _text(value)
    parsed = urlsplit(text)
    try:
        valid = (parsed.scheme == "https" and parsed.hostname in {"netfile.com", "public.netfile.com"}
                 and not parsed.username and not parsed.password and parsed.port in {None, 443})
    except ValueError as exc:
        raise FinanceProjectionError("Invalid original finance source link") from exc
    if not valid:
        raise FinanceProjectionError("Invalid original finance source link")
    return text


def _strings(value: Any, *, nonempty: bool = False, links: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple)) or (nonempty and not value):
        raise FinanceProjectionError("Missing public finance evidence list")
    result = [_source_url(entry) if links else _text(entry) for entry in value]
    if len(set(result)) != len(result):
        raise FinanceProjectionError("Repeated public finance evidence identity")
    return result


def project_public_finance_snapshot(snapshot: Mapping[str, Any], *,
                                    previous_through: str | date | None = None) -> dict[str, Any]:
    """Return exact compact-table rows after verifying acquisition completeness.

    Public coverage stays partial even when electronic acquisition succeeded:
    paper and other-agency coverage is incomplete. All forms/cutoffs are checked
    before returning anything. The caller must recheck the existing cutoff and
    atomically replace this WHOLE scope under a transaction-level lock; never
    append events or delete from a failed/partial form acquisition.
    """
    metrics = snapshot.get("acquisition_metrics")
    if not isinstance(metrics, Mapping) or type(metrics.get("model_calls")) is not int or metrics["model_calls"] != 0:
        raise FinanceProjectionError("A completed zero-model acquisition is required")
    raw_coverage = snapshot.get("coverage")
    raw_events = snapshot.get("events")
    if not isinstance(raw_coverage, (list, tuple)) or not isinstance(raw_events, (list, tuple)):
        raise FinanceProjectionError("A complete events-and-coverage snapshot is required")
    if len(raw_coverage) != len(FORMS):
        raise FinanceProjectionError("All eight electronic finance forms are required")
    coverage: list[dict[str, Any]] = []
    forms: set[str] = set()
    cutoffs: set[str] = set()
    for row in raw_coverage:
        if not isinstance(row, Mapping) or row.get("snapshot_complete") is not True:
            raise FinanceProjectionError("Incomplete acquisition cannot replace a finance snapshot")
        if row.get("source") != "netfile" or row.get("scope_key") != PUBLIC_SCOPE:
            raise FinanceProjectionError("Only the exact Richmond 2026 electronic scope can be replaced")
        form = row.get("form_type")
        if form not in FORMS.values() or form in forms:
            raise FinanceProjectionError("Electronic finance forms are missing or repeated")
        forms.add(form)
        start, cutoff = _date(row.get("activity_from")), _date(row.get("activity_through"))
        if start != PUBLIC_FROM or not PUBLIC_FROM <= cutoff <= PUBLIC_THROUGH:
            raise FinanceProjectionError("Finance acquisition window is outside the published scope")
        cutoffs.add(cutoff)
        # acquire_snapshot always describes limited electronic coverage. Do not
        # silently promote a manipulated/unknown 'complete' public status.
        if row.get("status") != "partial":
            raise FinanceProjectionError("Electronic-only public coverage must remain partial")
        try:
            projected = {column: row[column] for column in COVERAGE_COLUMNS}
        except KeyError as exc:
            raise FinanceProjectionError("Finance coverage provenance is incomplete") from exc
        projected.update(checked_at=_timestamp(row["checked_at"]), extracted_at=_timestamp(row["extracted_at"]),
                         source_url=_source_url(row["source_url"]),
                         limitations=_strings(row["limitations"], nonempty=True),
                         confidence_score=_decimal(row["confidence_score"]))
        if not 0 <= projected["confidence_score"] <= 1 or type(row["source_tier"]) is not int or not 1 <= row["source_tier"] <= 4:
            raise FinanceProjectionError("Finance coverage provenance is outside valid bounds")
        for field in ("filing_count", "assertion_count", "pending_count"):
            if type(row[field]) is not int or row[field] < 0:
                raise FinanceProjectionError("Finance coverage counts must be nonnegative integers")
        if row["pending_count"] > row["assertion_count"]:
            raise FinanceProjectionError("Pending finance count exceeds source assertions")
        coverage.append(projected)
    if forms != set(FORMS.values()) or len(cutoffs) != 1:
        raise FinanceProjectionError("All finance forms must share one complete calendar cutoff")
    cutoff = next(iter(cutoffs))
    if previous_through is not None and cutoff < _date(previous_through):
        raise FinanceProjectionError("A finance snapshot cannot shrink to an earlier cutoff")

    events: list[dict[str, Any]] = []
    event_keys: set[str] = set()
    filtered = 0
    for row in raw_events:
        if not isinstance(row, Mapping) or row.get("source") != "netfile" or row.get("scope_key") != PUBLIC_SCOPE:
            raise FinanceProjectionError("Finance event source/scope differs from its acquisition")
        score = _decimal(row.get("confidence_score"))
        if not 0 <= score <= 1:
            raise FinanceProjectionError("Finance event confidence is outside valid bounds")
        # acquire_snapshot.reconcile emits only current events. A persisted
        # input that explicitly marks an old event is conservatively withheld.
        if row.get("is_current", True) is not True or score < Decimal("0.90") or row.get("reconciliation_status") not in PUBLIC_STATUSES:
            filtered += 1
            continue
        day = _date(row.get("activity_date"))
        if not PUBLIC_FROM <= day <= PUBLIC_THROUGH:
            filtered += 1
            continue
        if day > cutoff:
            raise FinanceProjectionError("An event is newer than its acquired calendar cutoff")
        try:
            projected = {column: row[column] for column in EVENT_COLUMNS}
        except KeyError as exc:
            raise FinanceProjectionError("Public event provenance/fields are incomplete") from exc
        key = _text(row["event_key"])
        if not key.startswith("netfile:") or len(key) == len("netfile:") or key in event_keys:
            raise FinanceProjectionError("Finance event identity is invalid or repeated")
        event_keys.add(key)
        if row["event_kind"] not in EVENT_KINDS or row["support_oppose"] not in {None, "S", "O"}:
            raise FinanceProjectionError("Unknown source-reported finance event kind or stance")
        for field in ("donor_name", "donor_fppc_id", "recipient_name", "recipient_fppc_id",
                      "reporting_filer_name", "reporting_filer_fppc_id", "candidate_name", "measure_name"):
            projected[field] = _text(row[field], nullable=True)
        projected.update(amount=_decimal(row["amount"]), amount_kind=_text(row["amount_kind"]),
                         activity_date=day, confidence_score=score,
                         extracted_at=_timestamp(row["extracted_at"]), source_url=_source_url(row["source_url"]),
                         filing_ids=_strings(row["filing_ids"], nonempty=True),
                         source_urls=_strings(row["source_urls"], nonempty=True, links=True))
        if projected["source_url"] not in projected["source_urls"]:
            raise FinanceProjectionError("Primary finance source is absent from the evidence list")
        if type(row["source_tier"]) is not int or not 1 <= row["source_tier"] <= 4:
            raise FinanceProjectionError("Invalid public finance source tier")
        projected["election_date"] = _date(row["election_date"]) if row["election_date"] is not None else None
        events.append(projected)
    return {"events": sorted(events, key=lambda row: row["event_key"]),
            "coverage": sorted(coverage, key=lambda row: row["form_type"]),
            "scope_key": PUBLIC_SCOPE, "activity_from": PUBLIC_FROM,
            "activity_through": cutoff, "model_calls": 0,
            "filtered_event_count": filtered, "complete_electronic_acquisition": True,
            "public_coverage": "partial"}
