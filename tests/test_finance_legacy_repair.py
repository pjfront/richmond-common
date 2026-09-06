from copy import deepcopy
from decimal import Decimal

import pytest

from finance_ledger import assertion_from_netfile, reconcile
from repair_2026_part2 import EXPECTED, make_plan, apply_plan, validate_sources


def fixture_state():
    rows = []
    for index, (key, (day, amount, donor, recipient)) in enumerate(EXPECTED.items()):
        filing, transaction = key.split(":")
        tx = dict(filingId=filing,id=transaction,transactionType=21,date=day,amount=amount,
                  filerName=f"PAC {donor}",filerFppcId=donor,name=f"Committee {recipient}",transactionFppcId=recipient)
        a = assertion_from_netfile(tx,dict(filingId=filing,agency="RICH"),"0660620:calendar-2026")
        a["id"] = f"source-{index}"
        rows.append(a)
    incoming = []
    for a in rows[:3]:
        tx = dict(a["raw_payload"]["transaction"],transactionType=0,filingId="periodic"+a["filing_id"],
                  filerName=a["recipient_name"],filerFppcId=a["recipient_fppc_id"],name=a["donor_name"],transactionFppcId=a["donor_fppc_id"])
        p = assertion_from_netfile(tx,dict(filingId=tx["filingId"],agency="RICH"),"0660620:calendar-2026")
        p["id"] = "receipt-"+a["id"]
        incoming.append(p)
    reconcile(rows+incoming)
    committees = [dict(id=identifier,name=f"Committee {identifier}",filer_id=identifier,committee_type=None,status=None)
                  for identifier in sorted({a["recipient_fppc_id"] for a in rows}|{a["donor_fppc_id"] for a in rows})]
    next(m for m in committees if m["id"] == "1490887")["filer_id"] = "Pending"
    legacy = []
    for i,a in enumerate(rows):
        if i == 1:  # Real-case middle May18 outgoing record was deleted earlier.
            continue
        legacy.append(dict(before_row=dict(id=f"wrong-{i}",committee_id=a["donor_fppc_id"],amount=a["amount"],
                          contribution_date=a["activity_date"],filing_id=a["filing_id"]),donor_name=a["recipient_name"],
                          recipient_fppc_id=a["donor_fppc_id"],recipient_name=a["donor_name"]))
    for p in (incoming[0], incoming[2]):
        legacy.append(dict(before_row=dict(id=p["id"],committee_id="1490887",amount=p["amount"],
                          contribution_date=p["activity_date"],filing_id=p["filing_id"]),donor_name=p["donor_name"],
                          recipient_fppc_id="Pending",recipient_name=p["recipient_name"]))
    return dict(assertions=rows,recipient_reports=incoming,committees=committees,legacy=legacy)


def test_exact_repair_retires_11_reversed_restores_one_missing_gift_and_links_filer():
    state = fixture_state()
    plan = make_plan(state)
    assert sum(len(a["reverse_row_ids"]) for a in plan["actions"]) == 11
    restores = [a for a in plan["actions"] if a["disposition"] == "restore_missing_receipt"]
    assert len(restores) == 1 and restores[0]["activity_date"] == "2026-05-18"
    assert len(plan["committee_identity_updates"]) == 1
    safe = next(m for m in plan["committee_balance_changes"] if m["filer_id"] == "1490887")
    assert (safe["before"], safe["change"], safe["after"]) == (Decimal(60000),Decimal(30000),Decimal(90000))
    assert sum(a["disposition"] == "ledger_only_outgoing_or_pending" for a in plan["actions"]) == 9
    assert make_plan(state) == plan


def test_missing_or_changed_original_assertion_stops_bounded_repair():
    state = fixture_state()
    with pytest.raises(ValueError, match="twelve"):
        validate_sources(state["assertions"][:-1])
    state["assertions"][0]["amount"] = Decimal(60000)
    with pytest.raises(ValueError, match="changed"):
        validate_sources(state["assertions"])


def test_stale_or_tampered_preview_cannot_write():
    class NeverWrite:
        def cursor(self):
            raise AssertionError("No writes allowed")
    state = fixture_state()
    plan = make_plan(state)
    with pytest.raises(ValueError, match="state changed"):
        apply_plan(NeverWrite(), state, plan, "0"*64)
    altered = deepcopy(plan)
    altered["actions"][0]["reverse_row_ids"] = ["unrelated-row"]
    with pytest.raises(ValueError, match="state changed"):
        apply_plan(NeverWrite(), state, altered, plan["state_hash"])
    state["legacy"][0]["before_row"]["amount"] = Decimal(29999)
    with pytest.raises(ValueError, match="state changed"):
        apply_plan(NeverWrite(), state, plan, plan["state_hash"])


def test_conflicting_committee_identity_is_not_silently_reassigned():
    state = fixture_state()
    next(m for m in state["committees"] if m["id"] == "1490887")["filer_id"] = "1234567"
    with pytest.raises(ValueError, match="Conflicting committee identity"):
        make_plan(state)


def test_existing_equal_receipts_are_not_deleted_or_merged_when_ambiguous():
    state = fixture_state()
    state["legacy"].append(dict(state["legacy"][-1],before_row=dict(state["legacy"][-1]["before_row"],id="another-real-gift")))
    with pytest.raises(ValueError, match="Ambiguous existing recipient"):
        make_plan(state)
