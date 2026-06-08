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


def _run_sync_netfile_with_stats(loader_stats: dict) -> dict:
    """Invoke sync_netfile with all external I/O mocked, returning its
    result dict. load_contributions_to_db is patched to return loader_stats
    so we exercise only the counter-mapping logic."""
    import netfile_client
    import netfile_paper_extractor
    import pipelines.netfile as nf

    with patch.object(netfile_client, "fetch_all_transactions", return_value=[]), \
         patch.object(netfile_client, "deduplicate_contributions", side_effect=lambda c: c), \
         patch.object(netfile_client, "normalize_transaction", side_effect=lambda t: t), \
         patch.object(netfile_paper_extractor, "auto_extract_paper_filings",
                      return_value={"committees_extracted": 0, "contributions_added": 0}), \
         patch.object(nf, "load_contributions_to_db", return_value=loader_stats):
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
