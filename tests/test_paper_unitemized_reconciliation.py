"""A missing donor extraction is not evidence of an unitemized donation."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import load_paper_filings as loader


def summary(itemized=1000, unitemized=200, **changes):
    return {"period_start": "2026-01-01", "period_end": "2026-06-30",
            "monetary_this_period": itemized + unitemized,
            "itemized_this_period": itemized, "unitemized_this_period": unitemized, **changes}


def database(monkeypatch, cache, itemized, prior=()):
    """Exercise SQL intent without a database or any external calls."""
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    state = SimpleNamespace(prior=list(prior), inserted=[], statements=[], selected=None)
    committees = set(cache.get("_committees", {}).values())

    def execute(sql, params):
        normalized = " ".join(sql.split())
        state.statements.append(normalized)
        if normalized.startswith("SELECT id FROM committees"):
            state.selected = (params[1],) if params[1] in committees else None
        elif normalized.startswith("SELECT filing_id, committee_id, contribution_date, amount"):
            state.selected = list(state.prior)
        elif normalized.startswith("SELECT COALESCE(SUM(amount), 0)"):
            assert "entity_code IS DISTINCT FROM 'UNI'" in normalized
            assert "contribution_type = 'monetary'" in normalized
            state.selected = (itemized.get(params[0], 0),)
        else:
            raise AssertionError(f"Unexpected SQL or attempted legacy mutation: {normalized}")

    def insert(_conn, records, *, city_fips, commit):
        assert _conn is conn and city_fips == "0660620" and commit is False
        state.inserted.extend(deepcopy(records))
        state.prior.extend((row["filing_id"], row["committee"], row["date"], row["amount"]) for row in records)

    cursor.execute.side_effect = execute
    cursor.fetchone.side_effect = lambda: state.selected
    cursor.fetchall.side_effect = lambda: state.selected
    monkeypatch.setattr(loader, "load_contributions_to_db", insert)
    return conn, state


@pytest.mark.parametrize("existing", [False, True])
def test_anderson_missing_itemized_7993_never_becomes_unitemized_9140(monkeypatch, existing):
    cache = {"217094857": summary(7993, 1147), "_committees": {"217094857": "Anderson"}}
    prior = [("217094857", "Anderson", "2026-06-30", 9140)] if existing else []
    conn, state = database(monkeypatch, cache, {}, prior)
    result = loader.reconcile_paper_filings_to_forms(conn, form_summary_cache=cache)
    assert state.prior == prior and state.inserted == []
    assert result["rows_synthesized"] == 0 and result["incomplete_count"] == 1
    issue = result["reconciliation_issues"][0]
    assert issue["itemized_form"] == 7993 and issue["unitemized_form"] == 1147
    assert issue["monetary_gap"] == 9140
    assert "not an unitemized donation" in issue["reason"]


def test_mixed_committee_run_preserves_real_and_legacy_uni_and_inserts_only_proven_amount(monkeypatch):
    cache = {"real": summary(), "bad": summary(7993, 1147), "fresh": summary(),
             "_committees": {"real": "Real", "bad": "Bad", "fresh": "Fresh"}}
    prior = [("real", "Real", "2026-06-30", 200), ("bad", "Bad", "2026-06-30", 9140),
             ("uncached", "Unrelated", "2025-12-31", 80)]
    conn, state = database(monkeypatch, cache, {"Real": 1000, "Fresh": 1000}, prior)
    result = loader.reconcile_paper_filings_to_forms(conn, form_summary_cache=cache)
    assert state.prior[:3] == prior
    assert [(row["filing_id"], row["amount"], row["entity_code"]) for row in state.inserted] == [("fresh", 200, "UNI")]
    assert result["rows_synthesized"] == 1 and result["dollars_synthesized"] == 200
    assert result["filings_already_matched"] == 1 and result["incomplete_count"] == 2
    assert {issue["filing_id"] for issue in result["reconciliation_issues"]} == {"bad", "uncached"}
    second = loader.reconcile_paper_filings_to_forms(conn, form_summary_cache=cache)
    assert second["rows_synthesized"] == 0 and len(state.inserted) == 1
    assert second["filings_already_matched"] == 2 and second["incomplete_count"] == 2
    assert state.prior[:3] == prior


@pytest.mark.parametrize("changes", [
    {"itemized_this_period": None}, {"unitemized_this_period": None},
    {"unitemized_this_period": True}, {"itemized_this_period": float("nan")},
    {"unitemized_this_period": float("inf")}, {"unitemized_this_period": -200},
    {"monetary_this_period": 1201}, {"monetary_this_period": 1200.01},
])
def test_missing_or_inconsistent_source_cannot_create_uni(monkeypatch, changes):
    cache = {"f": summary(**changes), "_committees": {"f": "Committee"}}
    prior = [("f", "Committee", "2026-06-30", 200)]
    conn, state = database(monkeypatch, cache, {"Committee": 1000}, prior)
    result = loader.reconcile_paper_filings_to_forms(conn, form_summary_cache=cache)
    assert result["incomplete_count"] == 1 and result["rows_synthesized"] == 0
    assert state.prior == prior and state.inserted == []


@pytest.mark.parametrize("retained_itemized", [0, 100, 999.99, 1000.01, 1100, 1200, float("nan")])
def test_explicit_unitemized_is_insufficient_without_matching_itemized_extraction(monkeypatch, retained_itemized):
    cache = {"f": summary(), "_committees": {"f": "Committee"}}
    conn, state = database(monkeypatch, cache, {"Committee": retained_itemized})
    result = loader.reconcile_paper_filings_to_forms(conn, form_summary_cache=cache)
    assert result["incomplete_count"] == 1 and state.inserted == []


@pytest.mark.parametrize("prior", [
    [("f", "Committee", "2026-06-30", 1100)],
    [("superseded", "Committee", "2026-06-30", 200)],
    [("f", "Committee", "2026-06-30", 100), ("f", "Committee", "2026-06-30", 100)],
])
def test_existing_amount_or_source_ambiguity_requires_explicit_repair(monkeypatch, prior):
    cache = {"f": summary(), "_committees": {"f": "Committee"}}
    conn, state = database(monkeypatch, cache, {"Committee": 1000}, prior)
    result = loader.reconcile_paper_filings_to_forms(conn, form_summary_cache=cache)
    assert result["incomplete_count"] == 1 and state.inserted == [] and state.prior == prior
    assert "separate source-backed repair" in result["incomplete_reasons"][0]


@pytest.mark.parametrize("cache", [
    {"_committees": {}},
    {"f": summary(period_end="bad-date"), "_committees": {"f": "Committee"}},
    {"f": summary(7993, 1147), "_committees": {"f": "Committee"}},
])
def test_job_reports_empty_malformed_or_missing_extraction_as_incomplete(monkeypatch, cache):
    from pipelines.netfile import sync_paper_filing_reconciliation

    conn, state = database(monkeypatch, cache, {})
    with patch.object(loader, "discover_and_extract_all_form460_summaries", return_value=cache), patch(
        "netfile_paper_extractor.get_form460_summary_run_failures", return_value={},
    ):
        result = sync_paper_filing_reconciliation(conn, "0660620")
    assert result["retryable_incomplete"] is True
    assert result["cache_complete_for_reconciliation"] is False
    assert result["incomplete_count"] == 1 and result["incomplete_reasons"]
    assert result["records_new"] == 0 and state.inserted == []
