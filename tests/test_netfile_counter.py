"""Tests for sync_netfile's counter accuracy — net-new vs cross-filing churn.

Background (2026-06-08): every netfile sync inserts ~1,700 cross-filing
variant rows (same gift filed on both Form 497 and Form 460) which the
dedup pass then deletes, producing ~0 net new rows. The old `records_new`
reported the raw INSERT count (~1,700), making a no-op sync look like a big
import and hiding the insert-then-delete churn. These tests pin the corrected
mapping: records_new is NET of dedup, and records_churned surfaces the waste.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))


def _run_sync_netfile_with_stats(
    loader_stats: dict,
    *,
    paper_summary: dict | None = None,
    fetch_side_effect=None,
) -> dict:
    """Invoke sync_netfile with all external I/O mocked, returning its
    result dict. load_contributions_to_db is patched to return loader_stats
    so we exercise only the counter-mapping logic."""
    import netfile_client
    import netfile_paper_extractor
    import pipelines.netfile as nf

    if paper_summary is None:
        paper_summary = {
            "committees_extracted": 0,
            "contributions_added": 0,
            "paper_pending_count": 0,
            "retryable_incomplete": False,
            "incomplete_count": 0,
            "incomplete_reasons": [],
        }
    fetcher = MagicMock(
        side_effect=fetch_side_effect,
        return_value=[] if fetch_side_effect is None else None,
    )

    with patch.object(netfile_client, "fetch_all_transactions", fetcher), \
         patch.object(netfile_client, "deduplicate_contributions", side_effect=lambda c: c), \
         patch.object(netfile_client, "normalize_transaction", side_effect=lambda t: t), \
         patch.object(netfile_paper_extractor, "auto_extract_paper_filings",
                      return_value=paper_summary), \
         patch.object(nf, "load_contributions_to_db", return_value=loader_stats), \
         patch.object(nf.time, "sleep"):
        return nf.sync_netfile(MagicMock(), "0660620", sync_type="incremental")


BASE_STATS = {
    "contributions": 0, "updated": 0, "conflict_noop": 0,
    "unchanged": 0, "donors": 0, "committees": 0, "skipped": 0,
}


class TestNetfileCounter:
    def test_records_new_is_net_of_churn(self):
        stats = {**BASE_STATS, "contributions": 1706, "unchanged": 22496,
                 "dedup_dropped": 1701, "donors": 657}
        result = _run_sync_netfile_with_stats(stats)
        # 1706 raw inserts - 1701 dedup-dropped = 5 genuinely new
        assert result["records_new"] == 5
        assert result["records_churned"] == 1701
        assert result["raw_inserts"] == 1706

    def test_no_churn_means_records_new_equals_inserts(self):
        stats = {**BASE_STATS, "contributions": 8, "unchanged": 100}
        result = _run_sync_netfile_with_stats(stats)
        assert result["records_new"] == 8        # dedup_dropped absent → 0
        assert result["records_churned"] == 0
        assert result["raw_inserts"] == 8

    def test_full_churn_means_zero_net_new(self):
        # The pathological steady state: every insert is an ephemeral
        # cross-filing variant that dedup immediately drops.
        stats = {**BASE_STATS, "contributions": 1706, "dedup_dropped": 1706,
                 "unchanged": 22496}
        result = _run_sync_netfile_with_stats(stats)
        assert result["records_new"] == 0
        assert result["records_churned"] == 1706

    def test_net_new_never_negative(self):
        # Defensive: dedup_dropped should not exceed this run's inserts, but
        # if a stale count ever did, records_new must not go negative.
        stats = {**BASE_STATS, "contributions": 3, "dedup_dropped": 10}
        result = _run_sync_netfile_with_stats(stats)
        assert result["records_new"] == 0

    def test_unchanged_includes_conflict_noop(self):
        stats = {**BASE_STATS, "contributions": 1, "unchanged": 50, "conflict_noop": 7}
        result = _run_sync_netfile_with_stats(stats)
        assert result["records_unchanged"] == 57

    def test_failed_transaction_type_is_explicitly_retryable(self):
        def fetch(*, transaction_type):
            if transaction_type == 20:
                raise RuntimeError("NetFile 500")
            return []

        result = _run_sync_netfile_with_stats(
            BASE_STATS,
            fetch_side_effect=fetch,
        )

        assert result["retryable_incomplete"] is True
        assert result["failed_transaction_types"] == [20]
        assert result["incomplete_count"] == 1
        assert "type 20" in result["incomplete_reasons"][0]

    def test_paper_pending_propagates_to_netfile_result(self):
        result = _run_sync_netfile_with_stats(
            BASE_STATS,
            paper_summary={
                "committees_extracted": 0,
                "contributions_added": 0,
                "paper_pending_count": 2,
                "retryable_incomplete": True,
                "incomplete_count": 2,
                "incomplete_reasons": ["2 paper filings remain pending"],
            },
        )

        assert result["retryable_incomplete"] is True
        assert result["paper_pending_count"] == 2
        assert result["incomplete_count"] == 2
        assert "paper filings" in result["incomplete_reasons"][0]


def test_terminal_netfile_500_raises_typed_failure_after_all_retries():
    import netfile_client

    response = MagicMock(status_code=500)
    with patch.object(
        netfile_client.requests,
        "post",
        return_value=response,
    ) as post, patch.object(netfile_client.time, "sleep"):
        with pytest.raises(netfile_client.NetFileAPIError) as exc:
            netfile_client.api_post(
                "/public/campaign/search/transaction/query",
                {"TransactionType": 20, "CurrentPageIndex": 0},
                retries=3,
            )

    assert exc.value.status_code == 500
    assert exc.value.transaction_type == 20
    assert exc.value.page == 0
    assert post.call_count == 3


def test_netfile_true_empty_200_response_remains_a_success():
    import netfile_client

    empty = {
        "totalMatchingCount": 0,
        "totalMatchingPages": 0,
        "results": [],
    }
    response = MagicMock(status_code=200)
    response.json.return_value = empty
    with patch.object(netfile_client.requests, "post", return_value=response):
        result = netfile_client.api_post(
            "/public/campaign/search/transaction/query",
            {"TransactionType": 20, "CurrentPageIndex": 0},
        )

    assert result == empty


def test_paper_extractor_reports_pending_when_model_key_is_missing():
    import netfile_paper_extractor as extractor

    filings = [{"filing_id": "paper-1", "form_type": "Form 460"}]
    with patch.object(
        extractor,
        "discover_paper_filers",
        return_value={"Richmond Neighbors": filings},
    ), patch.object(
        extractor,
        "db_filing_ids_extracted",
        return_value=set(),
    ), patch.object(
        extractor,
        "_read_committee_extraction_state",
        return_value={"filings": [], "contributions": []},
    ), patch.dict(
        extractor.os.environ,
        {"DEEPSEEK_API_KEY": ""},
    ):
        result = extractor.auto_extract_paper_filings(transactions=[])

    assert result["retryable_incomplete"] is True
    assert result["paper_pending_count"] == 1
    assert result["paper_pending_filing_ids"] == ["paper-1"]
