"""Public-core precision, source-scope and no-private-payload regressions."""
from copy import deepcopy
from decimal import Decimal
import json

import pytest

from finance_ledger import FORMS
from finance_public_projection import (
    COVERAGE_COLUMNS, EVENT_COLUMNS, FinanceProjectionError,
    project_public_finance_snapshot,
)
from finance_sync import acquire_snapshot


def snapshot() -> dict:
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        if kwargs["transaction_type"] != 0:
            return []
        return [dict(transactionType=0, filingId="12345", id="fixture-receipt",
                     date="2026-05-12", amount="12.34", filerName="Public Committee",
                     filerFppcId="1490887", name="Reported Public Donor", transactionFppcId="951606",
                     address="PRIVATE_ADDRESS_DO_NOT_EXPORT", description="PRIVATE_PAYLOAD_DO_NOT_EXPORT")]

    result = acquire_snapshot(2026, "2026-10-04", fetch=fetch,
                              filing_info=lambda filing: {"filingId": filing})
    assert len(calls) == 8
    assert {call["transaction_type"] for call in calls} == set(FORMS)
    assert all(call["city_fips"] == "0660620" and call["date_start"] == "2026-01-01"
               and call["date_end"] == "2026-10-04" for call in calls)
    assert result["acquisition_metrics"]["model_calls"] == 0
    return result


def test_real_acquisition_contract_has_all_forms_and_no_private_public_payload() -> None:
    source = snapshot()
    unchanged = deepcopy(source)
    result = project_public_finance_snapshot(source)
    assert source == unchanged
    assert result["model_calls"] == 0 and result["complete_electronic_acquisition"] is True
    assert len(result["events"]) == 1 and len(result["coverage"]) == 8
    assert tuple(result["events"][0]) == EVENT_COLUMNS
    assert all(tuple(row) == COVERAGE_COLUMNS for row in result["coverage"])
    serialized = json.dumps(result, default=str)
    assert "PRIVATE_ADDRESS_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_PAYLOAD_DO_NOT_EXPORT" not in serialized
    assert "raw_payload" not in serialized and "assertion_keys" not in serialized
    assert all(row["status"] == "partial" and row["limitations"] for row in result["coverage"])
    assert result["events"][0]["amount"] == Decimal("12.34")


@pytest.mark.parametrize("mutation", [
    lambda s: s["coverage"].pop(),
    lambda s: s["coverage"].__setitem__(1, deepcopy(s["coverage"][0])),
    lambda s: s["coverage"][0].update(snapshot_complete=False),
    lambda s: s["coverage"][0].update(scope_key="0660620:calendar-2025"),
    lambda s: s["coverage"][0].update(source="other-agency"),
    lambda s: s["coverage"][0].update(activity_through="2026-10-03"),
    lambda s: s["coverage"][0].update(activity_through="2026-11-04"),
    lambda s: s["coverage"][0].update(activity_from="2026-02-01"),
    lambda s: s["coverage"][0].update(status="complete"),
    lambda s: s["coverage"][0].update(limitations=[]),
    lambda s: s["coverage"][0].update(pending_count=100),
    lambda s: s["acquisition_metrics"].update(model_calls=1),
    lambda s: s.pop("acquisition_metrics"),
])
def test_incomplete_or_misleading_snapshot_is_blocked_before_replacement(mutation) -> None:
    source = snapshot()
    mutation(source)
    with pytest.raises(FinanceProjectionError):
        project_public_finance_snapshot(source)


def test_stale_cutoff_and_mixed_event_scope_are_blocked() -> None:
    source = snapshot()
    with pytest.raises(FinanceProjectionError, match="earlier cutoff"):
        project_public_finance_snapshot(source, previous_through="2026-10-05")
    source["events"][0]["scope_key"] = "0660620:calendar-2025"
    with pytest.raises(FinanceProjectionError, match="source/scope"):
        project_public_finance_snapshot(source)


def test_sql_publication_filters_and_exact_date_window() -> None:
    source = snapshot()
    prototype = source["events"][0]
    variants = [dict(prototype, event_key=f"netfile:{index}", **changes) for index, changes in enumerate([
        {"confidence_score": Decimal("0.89")}, {"reconciliation_status": "pending_review"},
        {"is_current": False}, {"activity_date": "2025-12-31"}, {"activity_date": "2026-11-04"},
    ])]
    source["events"].extend(variants)
    result = project_public_finance_snapshot(source)
    assert len(result["events"]) == 1 and result["filtered_event_count"] == 5
    source["events"][0]["activity_date"] = "2026-10-05"
    with pytest.raises(FinanceProjectionError, match="newer"):
        project_public_finance_snapshot(source)


def test_signed_adjustments_loans_noncash_and_spender_roles_remain_separate() -> None:
    source = snapshot()
    prototype = source["events"][0]
    source["events"] = [dict(prototype, event_key="netfile:adjustment", amount=Decimal("-12.34"), amount_kind="negative_adjustment"),
                        dict(prototype, event_key="netfile:loan", event_kind="loan", amount_kind="reported_loan_amount"),
                        dict(prototype, event_key="netfile:noncash", event_kind="noncash", amount_kind="reported_noncash_value"),
                        dict(prototype, event_key="netfile:ie", event_kind="independent_expenditure",
                             donor_name=None, donor_fppc_id=None, recipient_name=None, recipient_fppc_id=None,
                             support_oppose="S", candidate_name="Reported Candidate")]
    rows = {row["event_key"]: row for row in project_public_finance_snapshot(source)["events"]}
    assert rows["netfile:adjustment"]["amount"] == Decimal("-12.34")
    assert rows["netfile:loan"]["event_kind"] == "loan"
    assert rows["netfile:noncash"]["event_kind"] == "noncash"
    assert rows["netfile:ie"]["donor_name"] is None
    assert rows["netfile:ie"]["reporting_filer_name"] == prototype["reporting_filer_name"]
    assert rows["netfile:ie"]["election_date"] is None


@pytest.mark.parametrize("changes", [
    {"amount": "NaN"}, {"confidence_score": "Infinity"}, {"source_url": "https://example.org/private"},
    {"source_url": "https://user:secret@netfile.com/Connect2/api/public/image/12345"},
    {"source_urls": []}, {"source_tier": 0}, {"extracted_at": None},
    {"support_oppose": "maybe"}, {"event_kind": "inferred_influence"},
])
def test_unpublishable_public_event_provenance_is_blocked(changes) -> None:
    source = snapshot()
    source["events"][0].update(changes)
    with pytest.raises(FinanceProjectionError):
        project_public_finance_snapshot(source)


def test_repeated_identity_and_empty_complete_acquisition() -> None:
    source = snapshot()
    source["events"].append(deepcopy(source["events"][0]))
    with pytest.raises(FinanceProjectionError, match="repeated"):
        project_public_finance_snapshot(source)
    source["events"] = []
    result = project_public_finance_snapshot(source)
    assert result["events"] == [] and len(result["coverage"]) == 8
