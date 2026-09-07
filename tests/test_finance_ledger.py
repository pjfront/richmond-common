"""Real-case regressions: source direction, repeated gifts, amendments and IE."""
from copy import deepcopy
from decimal import Decimal

import pymupdf as fitz
import pytest

from finance_ledger import assertion_from_netfile, reconcile, parse_496_context, rapid_noncash_counterpart
from finance_repair_audit import direction_status
from netfile_client import deduplicate_contributions, NetFileAPIError
from db.finance import persist_finance_snapshot

RPOA = "Richmond Police Officers Association PAC, Sponsored by Richmond Police Officers Association"
SAFE = "Safe Richmond Neighborhoods supporting Ahmad Anderson for Mayor 2026 sponsored by the Richmond Police Officers Association"


def transaction(kind=21, filing="216765092", tx_id="gift-one", day="2026-05-12", amount=30000):
    outgoing = kind == 21
    return dict(transactionType=kind, filingId=filing, id=tx_id, date=day, amount=amount,
                filerName=RPOA if outgoing else SAFE, filerFppcId="951606" if outgoing else "1490887",
                name=SAFE if outgoing else RPOA, transactionFppcId="1490887" if outgoing else "951606",
                candidate="Ahmad Anderson" if kind == 19 else "", description="Mailer" if kind == 19 else "")


def assertion(tx, **metadata):
    return assertion_from_netfile(tx, dict(filingId=tx["filingId"], **metadata), "0660620:calendar-2026")


def test_three_actual_unamended_rpoa_gifts_survive_near_dates():
    # Published PDFs 216765092,216787856,216841017 each have an unchecked
    # amendment box. Production previously lost the May18 middle gift.
    rows = [assertion(transaction(filing=f, tx_id=f, day=d)) for f, d in
            [("216765092", "2026-05-12"), ("216787856", "2026-05-18"), ("216841017", "2026-05-29")]]
    events = reconcile(rows)
    assert len(events) == 3
    assert sum(e["amount"] for e in events) == Decimal("90000")
    assert {(e["donor_fppc_id"], e["recipient_fppc_id"]) for e in events} == {("951606", "1490887")}


def test_source_dedup_preserves_distinct_same_day_equal_gifts():
    first = dict(transaction_id="one", filing_id="460", amount=50, date="2026-05-12")
    second = dict(first, transaction_id="two")
    assert deduplicate_contributions([first, first.copy(), second]) == [first, second]
    with pytest.raises(NetFileAPIError):
        deduplicate_contributions([first, dict(first, amount=60)])


def test_exact_incoming_outgoing_and_rapid_claims_become_one_receipt():
    rows = [assertion(transaction(kind=k, filing=str(k), tx_id=str(k))) for k in (0, 20, 21, 4)]
    # Receiving filer sometimes omits a donor ID; its identical reported
    # committee name links to one source-provided identifier, never fuzzy text.
    rows[0]["donor_fppc_id"] = None
    events = reconcile(rows)
    assert len(events) == 1
    assert events[0]["event_kind"] == "receipt"
    assert events[0]["reconciliation_status"] == "matched_exact"
    assert len(events[0]["filing_ids"]) == 4
    assert len(rows) == 4


def test_equal_gifts_with_ambiguous_cross_report_multiplicity_wait_for_review():
    rows = [assertion(transaction(kind=0, tx_id="a")), assertion(transaction(kind=0, tx_id="b")),
            assertion(transaction(kind=20, tx_id="late"))]
    assert reconcile(rows) == []
    assert all(a["review_reason"] == "ambiguous_cross_report_multiplicity" for a in rows)


def test_different_dates_never_merge_keep_periodic_hold_rapid_for_review():
    rows = [assertion(transaction(kind=0, day="2026-05-18")), assertion(transaction(day="2026-05-12"))]
    events = reconcile(rows)
    assert len(events) == 1 and events[0]["activity_date"] == "2026-05-18"
    assert rows[1]["review_reason"] == "cross_report_date_disagreement"
    assert rows[1]["amount"] == Decimal("30000")  # evidence is not removed


def test_explicit_amendment_amount_change_excludes_old_and_retains_payload():
    old = assertion(transaction(kind=0, filing="old", amount=30000), amendedBy="new")
    new = assertion(transaction(kind=0, filing="new", amount=25000), amends="old", amendmentSequenceNumber=1)
    assert old["raw_payload"]["transaction"]["amount"] == 30000
    events = reconcile([old, new])
    assert len(events) == 1 and events[0]["amount"] == Decimal("25000")
    assert new["amends_filing_id"] == "old"


def test_negative_adjustment_noncash_and_loan_not_cash_gifts():
    rows = [assertion(transaction(kind=k, tx_id=str(k), amount=a)) for k, a in ((0, -100), (1, 100), (12, 100))]
    events = reconcile(rows)
    assert {e["event_kind"] for e in events} == {"receipt", "noncash", "loan"}
    assert next(e for e in events if e["event_kind"] == "receipt")["amount_kind"] == "negative_adjustment"
    assert sum(e["amount"] for e in events if e["event_kind"] == "receipt") == -100


def noncash_conflict_fixture():
    def reported(kind, filing):
        return dict(transactionType=kind, filingId=filing, id=f"source-{kind}", date="2026-04-08", amount=2000,
                    filerName="Claudia Jimenez for Mayor of Richmond 2026", filerFppcId="1488504",
                    name="Diana Wear", transactionFppcId=None, description="Payment for speech coaching" if kind == 1 else "")
    return [assertion(reported(1, "216815171"), amends="216686471", amendmentSequenceNumber=2), assertion(reported(20, "216668328"))]


def test_actual_rapid_noncash_conflict_withholds_cash_but_preserves_both_original_assertions():
    rows = noncash_conflict_fixture()
    before = [(row["content_hash"], deepcopy(row["raw_payload"])) for row in rows]
    events = reconcile(rows)
    assert len(events) == 1 and events[0]["event_kind"] == "noncash"
    assert events[0]["amount"] == Decimal("2000") and events[0]["filing_ids"] == ["216815171"]
    assert rows[1]["review_reason"] == "rapid_report_noncash_conflict"
    assert rows[1]["reconciliation_status"] == "pending_review" and rows[1]["canonical_event_key"] is None
    assert [(row["content_hash"], row["raw_payload"]) for row in rows] == before


@pytest.mark.parametrize("which,updates", [
    (0, {"is_current": False}), (0, {"review_reason": "unverified_source"}),
    (0, {"recipient_fppc_id": "1490887"}), (0, {"reporting_filer_fppc_id": "1490887"}),
    (0, {"activity_date": "2026-04-09"}), (0, {"amount": Decimal("2000.01")}),
    (0, {"donor_name": "Diana Wear LLC"}), (0, {"scope_key": "another-scope"}),
    (0, {"amount_kind": "negative_adjustment"}), (0, {"amount": Decimal("-2000")}),
    (1, {"transaction_type": 21}), (1, {"recipient_fppc_id": None}), (1, {"donor_name": None}),
    (1, {"activity_date": None}), (1, {"amount": None}), (1, {"amount": Decimal("NaN")}),
])
def test_noncash_guard_requires_exact_current_source_identity_and_positive_value(which, updates):
    periodic, rapid = noncash_conflict_fixture()
    [periodic, rapid][which].update(updates)
    assert not rapid_noncash_counterpart(rapid, periodic)


def test_noncash_guard_uses_reported_ids_without_fuzzy_names_or_conflicting_ids():
    periodic, rapid = noncash_conflict_fixture()
    periodic["donor_name"] = " DIANA  WEAR "
    assert rapid_noncash_counterpart(rapid, periodic)
    periodic["donor_fppc_id"], rapid["donor_fppc_id"] = "1111111", "2222222"
    assert not rapid_noncash_counterpart(rapid, periodic)
    rapid["donor_fppc_id"] = "1111111"
    rapid["donor_name"] = "Different reported spelling"
    assert rapid_noncash_counterpart(rapid, periodic)


def test_noncash_collision_with_multiple_possible_sources_never_auto_merges():
    periodic, rapid = noncash_conflict_fixture()
    second = deepcopy(periodic)
    second.update(record_key="another-periodic-row", transaction_id="another")
    extra_rapid = deepcopy(rapid)
    extra_rapid.update(record_key="another-rapid-row", transaction_id="another")
    events = reconcile([periodic, second, rapid, extra_rapid])
    assert len(events) == 2 and all(event["event_kind"] == "noncash" for event in events)
    assert all(row["review_reason"] == "rapid_report_noncash_conflict" for row in [rapid, extra_rapid])
    assert all(len(event["assertion_keys"]) == 1 for event in events)


def test_noncash_guard_preserves_a_separate_periodic_cash_receipt_with_identical_parties_and_value():
    periodic, rapid = noncash_conflict_fixture()
    cash = assertion({**rapid["raw_payload"]["transaction"], "transactionType": 0, "id": "cash", "filingId": "216815171"})
    events = reconcile([periodic, rapid, cash])
    assert len(events) == 2 and {event["event_kind"] for event in events} == {"receipt", "noncash"}
    assert rapid["review_reason"] == "rapid_report_noncash_conflict"
    assert all(len(event["assertion_keys"]) == 1 for event in events)


def test_ie_does_not_infer_donor_support_or_election_from_committee_title():
    row = assertion(transaction(kind=19))
    assert row["donor_name"] is None and row["recipient_name"] is None
    assert row["support_oppose"] is None and row["election_date"] is None
    assert reconcile([row]) == []


def pdf_fixture(mark="X", candidate_in_field=True):
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    page.insert_text((36, 40), "496 Independent Expenditure Report")
    page.insert_text((40, 82), SAFE, fontsize=6)
    if candidate_in_field:
        page.insert_text((53, 230), "Ahmad Anderson", fontsize=8)
    page.insert_text((302, 243), "SUPPORT", fontsize=7)
    page.insert_text((350, 243), "OPPOSE", fontsize=7)
    page.insert_text((318, 260), mark, fontsize=10)
    return doc.tobytes()


def test_pdf_checkbox_requires_candidate_field_not_just_filer_name():
    context = parse_496_context(pdf_fixture(), "Ahmad Anderson")
    assert context["support_oppose"] == "S"
    assert "support_oppose" not in parse_496_context(pdf_fixture(candidate_in_field=False), "Ahmad Anderson")
    assert "support_oppose" not in parse_496_context(pdf_fixture(mark=""), "Ahmad Anderson")


def test_incomplete_acquisition_cannot_change_database():
    class NeverWrite:
        def cursor(self):
            raise AssertionError("No database operation is allowed")
    with pytest.raises(ValueError, match="incomplete"):
        persist_finance_snapshot(NeverWrite(), [], [], [{"snapshot_complete": False}])
    with pytest.raises(ValueError, match="all supported forms"):
        persist_finance_snapshot(NeverWrite(), [], [], [{"snapshot_complete": True, "form_type": "F497P2", "scope_key": "0660620:calendar-2026"}])


def test_legacy_direction_repair_requires_full_source_match():
    tx = transaction()
    row = dict(id="legacy", filing_id=tx["filingId"], amount=30000, contribution_date="2026-05-12",
               donor_name=SAFE, recipient_fppc_id="951606", recipient_name=RPOA)
    assert direction_status(tx, [row])[0] == "reversed_source_direction"
    assert direction_status(tx, [dict(row, donor_name="Different committee")])[0] == "source_assertion_missing_from_legacy"


@pytest.mark.parametrize("payload", [{}, {"error": "upstream unavailable"},
    {"totalMatchingCount": 1, "totalMatchingPages": 0, "results": []},
    {"totalMatchingCount": 0, "totalMatchingPages": 0, "results": [], "searchParameters": {"showSuperceded": True}}])
def test_malformed_api_success_is_not_an_empty_finance_snapshot(monkeypatch, payload):
    import netfile_client
    monkeypatch.setattr(netfile_client, "search_transactions", lambda **kwargs: payload)
    with pytest.raises(NetFileAPIError):
        netfile_client.fetch_all_transactions(transaction_type=19)


def test_an_earlier_cutoff_cannot_remove_current_source_rows():
    from datetime import date
    from unittest.mock import MagicMock
    from finance_ledger import FORMS
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (date(2026,9,7),)
    coverage = [dict(snapshot_complete=True,form_type=form,scope_key="0660620:calendar-2026",activity_through="2026-09-06") for form in FORMS.values()]
    with pytest.raises(ValueError, match="earlier cutoff"):
        persist_finance_snapshot(conn, [], [], coverage)
    assert all(str(call.args[0]).startswith("SELECT") for call in cur.execute.call_args_list)
