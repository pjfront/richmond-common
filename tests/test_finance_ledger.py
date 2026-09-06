"""Real-case regressions: source direction, repeated gifts, amendments and IE."""
from copy import deepcopy
from decimal import Decimal

import fitz
import pytest

from finance_ledger import assertion_from_netfile, reconcile, parse_496_context
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


def test_legacy_direction_repair_requires_full_source_match():
    tx = transaction()
    row = dict(id="legacy", filing_id=tx["filingId"], amount=30000, contribution_date="2026-05-12",
               donor_name=SAFE, recipient_fppc_id="951606", recipient_name=RPOA)
    assert direction_status(tx, [row])[0] == "reversed_source_direction"
    assert direction_status(tx, [dict(row, donor_name="Different committee")])[0] == "source_assertion_missing_from_legacy"
