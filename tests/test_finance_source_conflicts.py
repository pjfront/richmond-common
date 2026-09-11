"""Regressions from original Richmond, California filings checked September 10."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest

from civic_review_packets import prepare_finance_packets, possible_counterpart
from finance_ledger import (
    FORMS, assertion_from_netfile, independent_expenditure_counterpart,
    receipt_loan_counterpart, reconcile,
)
from finance_sync import acquire_snapshot


SOURCE = json.loads((Path(__file__).parent / "fixtures/finance-source-conflicts.json").read_text())


def source_rows(section):
    return [assertion_from_netfile(row["transaction"], row["metadata"], SOURCE["scope_key"], row.get("pdf_context"))
            for row in SOURCE[section]]


def test_actual_rpoa_loan_keeps_lender_borrower_direction_and_does_not_certify_another_gift():
    rows = source_rows("loan_conflict")
    originals = [(row["content_hash"], deepcopy(row["raw_payload"])) for row in rows]
    events = reconcile(rows)
    assert len(events) == 1
    loan = events[0]
    assert (loan["donor_fppc_id"], loan["recipient_fppc_id"]) == ("951606", "1490887")
    assert loan["reporting_filer_fppc_id"] == "951606"
    assert loan["event_kind"] == "loan" and loan["amount_kind"] == "reported_loan_amount"
    assert loan["filing_ids"] == ["217081719"] and loan["amount"] == Decimal("30000")
    assert loan["activity_date"] == "2026-05-29" and loan["election_date"] is None
    held = [row for row in rows if row["reconciliation_status"] == "pending_review"]
    assert {row["form_type"] for row in held} == {"F460A", "F497P1", "F497P2", "F496P3"}
    assert all(row["review_reason"] == "receipt_loan_classification_conflict" and row["canonical_event_key"] is None for row in held)
    assert [(row["content_hash"], row["raw_payload"]) for row in rows] == originals


@pytest.mark.parametrize("which,updates", [
    (0, {"is_current": False}), (0, {"review_reason": "unverified_source"}),
    (0, {"donor_fppc_id": "1111111"}), (0, {"recipient_fppc_id": "2222222"}),
    (0, {"reporting_filer_fppc_id": "1490887"}), (0, {"amount_kind": "monetary"}),
    (0, {"activity_date": "2026-05-30"}), (0, {"scope_key": "other-scope"}),
    (0, {"amount": Decimal("29999.99")}), (0, {"source": "another-source"}),
    (1, {"donor_fppc_id": None}), (1, {"recipient_fppc_id": None}),
    (1, {"reporting_filer_fppc_id": "951606"}), (1, {"is_current": False}),
    (1, {"amount": Decimal("NaN")}), (1, {"amount": None}), (1, {"activity_date": None}),
])
def test_loan_comparison_requires_current_exact_ids_date_amount_and_source(which, updates):
    loan, receipt, *_ = source_rows("loan_conflict")
    [loan, receipt][which].update(updates)
    assert not receipt_loan_counterpart(receipt, loan)


def test_received_loan_preserves_the_same_party_direction_and_negative_entries_remain_adjustments():
    loan, receipt, *_ = source_rows("loan_conflict")
    tx = deepcopy(receipt["raw_payload"]["transaction"])
    tx.update(transactionType=12)
    received = assertion_from_netfile(tx, {"filingId": tx["filingId"]}, SOURCE["scope_key"])
    assert receipt_loan_counterpart(receipt, received)
    tx["amount"] = -30000
    adjusted = assertion_from_netfile(tx, {"filingId": tx["filingId"]}, SOURCE["scope_key"])
    assert adjusted["amount_kind"] == "negative_adjustment"
    assert not receipt_loan_counterpart(receipt, adjusted)


def test_loan_conflict_builds_one_resolve_only_packet_with_all_five_originals():
    rows = source_rows("loan_conflict")
    reconcile(rows)
    packets = prepare_finance_packets(rows, date(2026, 9, 10))
    assert len(packets) == 1 and packets[0].kind is None
    packet = packets[0]
    assert packet.evidence["reason_codes"] == ["receipt_loan_classification_conflict"]
    assert {row["filing_id"] for row in packet.evidence["reported_entries"]} == {"217081719", "217288271", "216840276", "216841017", "216896453"}
    assert "does not merge, delete, or change" in packet.evidence["recommendation"]
    assert packet.input_fingerprint == prepare_finance_packets(list(reversed(rows)), date(2026, 9, 10))[0].input_fingerprint


def test_loan_packet_does_not_mix_in_nearby_separate_reported_transfers():
    rows = source_rows("loan_conflict")
    nearby = deepcopy(rows[1])
    nearby.update(record_key="217249948:earlier-transfer", filing_id="217249948", activity_date="2026-05-18")
    rows.append(nearby)
    reconcile(rows)
    packets = prepare_finance_packets(rows, date(2026, 9, 10))
    assert len(packets) == 1
    assert len(packets[0].evidence["reported_entries"]) == 5
    assert nearby["record_key"] not in {key for key, _ in packets[0].evidence["source_versions"]}
    assert not possible_counterpart(rows[1], nearby) and not possible_counterpart(nearby, rows[1])


def test_actual_cross_report_mailer_repetition_is_held_without_choosing_or_deleting_a_source():
    rows = source_rows("ie_repetition")
    originals = [(row["content_hash"], deepcopy(row["raw_payload"])) for row in rows]
    assert independent_expenditure_counterpart(*rows)
    assert reconcile(rows) == []
    assert all(row["reconciliation_status"] == "pending_review" and row["canonical_event_key"] is None for row in rows)
    assert {row["review_reason"] for row in rows} == {"independent_expenditure_cross_report_repetition"}
    assert [(row["content_hash"], row["raw_payload"]) for row in rows] == originals
    packets = prepare_finance_packets(rows, date(2026, 9, 10))
    assert len(packets) == 1 and packets[0].kind is None
    assert {entry["filing_id"] for entry in packets[0].evidence["reported_entries"]} == {"216728089", "216772061"}
    assert all(entry["description"] == "Mailer" for entry in packets[0].evidence["reported_entries"])
    assert "no duplicate has been assumed or deleted" in packets[0].evidence["reason"][0]
    assert possible_counterpart(*rows)


@pytest.mark.parametrize("updates", [
    {"activity_date": "2026-05-05"}, {"amount": Decimal("12682.31")},
    {"reporting_filer_fppc_id": "1111111"}, {"reporting_filer_fppc_id": None},
    {"candidate_name": "Another candidate"}, {"support_oppose": "O"}, {"support_oppose": None},
    {"scope_key": "other-scope"}, {"source": "other-source"}, {"is_current": False},
    {"review_reason": "independent_expenditure_target_or_stance_unverified"},
    {"amount": Decimal("NaN")}, {"amount_kind": "negative_adjustment"}, {"election_date": "2026-11-03"},
    {"raw_payload": {"transaction": {"description": "Video production"}}},
    {"raw_payload": {"transaction": {"description": ""}}},
])
def test_independent_spending_comparison_never_uses_near_dates_or_fuzzy_identity(updates):
    left, right = source_rows("ie_repetition")
    right.update(updates)
    assert not independent_expenditure_counterpart(left, right)


def test_same_filing_distinct_expenditures_survive_and_explicit_supersession_is_respected():
    rows = source_rows("ie_repetition")
    rows[1]["filing_id"] = rows[0]["filing_id"]
    assert len(reconcile(rows)) == 2
    rows = source_rows("ie_repetition")
    rows[0].update(is_current=False, amended_by_filing_id=rows[1]["filing_id"])
    events = reconcile(rows)
    assert len(events) == 1 and events[0]["filing_ids"] == ["216772061"]


def test_acquisition_requires_loan_schedule_and_preserves_partial_coverage():
    source = SOURCE["loan_conflict"]
    calls = []
    def fetch(**kwargs):
        calls.append(kwargs)
        return [row["transaction"] for row in source if row["transaction"]["transactionType"] == kwargs["transaction_type"]]
    metadata = {row["metadata"]["filingId"]: row["metadata"] for row in source}
    snapshot = acquire_snapshot(2026, "2026-09-10", fetch=fetch, filing_info=metadata.__getitem__)
    assert {call["transaction_type"] for call in calls} == set(FORMS)
    assert all(call["city_fips"] == "0660620" and call["date_start"] == "2026-01-01" for call in calls)
    loan = next(row for row in snapshot["coverage"] if row["form_type"] == "F460H")
    assert loan["assertion_count"] == 1 and loan["status"] == "partial"
    assert any("not cash gifts or net-new borrowing totals" in limitation for limitation in loan["limitations"])
    assert sum(row["pending_count"] for row in snapshot["coverage"]) == 4
    assert snapshot["acquisition_metrics"]["model_calls"] == 0


def test_failed_loan_source_cannot_produce_a_replacement_snapshot():
    def fetch(**kwargs):
        if kwargs["transaction_type"] == 14:
            raise RuntimeError("Source unavailable")
        return []
    with pytest.raises(RuntimeError, match="Source unavailable"):
        acquire_snapshot(2026, "2026-09-10", fetch=fetch)
