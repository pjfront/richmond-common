"""Tests for batch_scan.py — v3 scanner batch execution and validation."""
import json
import uuid
from collections import Counter
from datetime import date
from unittest.mock import MagicMock, patch, call

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from batch_scan import (
    resolve_official_id,
    resolve_agenda_item_id,
    run_batch_scan,
    run_validation,
    _tier_label,
    SCANNER_VERSION,
)
from conflict_scanner import ConflictFlag, ScanResult


# ── Helpers ──────────────────────────────────────────────────

def _make_conn():
    """Create a mock connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = lambda self: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


def _make_flag(**overrides) -> ConflictFlag:
    """Create a ConflictFlag with sensible defaults."""
    defaults = dict(
        agenda_item_number="H-1",
        agenda_item_title="Approve contract with Acme Corp",
        council_member="Jane Doe",
        flag_type="campaign_contribution",
        description="Test flag description",
        evidence=["Source: NetFile filing 12345"],
        confidence=0.75,
        legal_reference="FPPC §87100",
        publication_tier=2,
        confidence_factors={
            "match_strength": 0.90,
            "temporal_factor": 0.70,
            "financial_factor": 0.60,
            "anomaly_factor": 0.50,
            "signal_count": 1,
            "corroboration_boost": 1.0,
            "sitting_multiplier": 1.0,
        },
        scanner_version=3,
    )
    defaults.update(overrides)
    return ConflictFlag(**defaults)


def _make_scan_result(flags=None) -> ScanResult:
    """Create a ScanResult wrapping flags."""
    return ScanResult(
        meeting_date="2026-01-15",
        meeting_type="Regular",
        total_items_scanned=10,
        flags=flags or [],
        vendor_matches=[],
        clean_items=["A-1", "A-2"],
    )


# ── SCANNER_VERSION ──────────────────────────────────────────

class TestScannerVersion:
    """Verify v3 scanner version is set correctly."""

    def test_scanner_version_is_3(self):
        assert SCANNER_VERSION == 3


# ── _tier_label ──────────────────────────────────────────────

class TestTierLabel:
    """Human-readable tier labels."""

    def test_tier_1(self):
        assert _tier_label(1) == "High-Confidence Pattern"

    def test_tier_2(self):
        assert _tier_label(2) == "Medium-Confidence Pattern"

    def test_tier_3(self):
        assert _tier_label(3) == "Low-Confidence Pattern"

    def test_tier_4(self):
        assert _tier_label(4) == "Internal"

    def test_unknown_tier(self):
        assert "Tier" in _tier_label(99)


# ── resolve_official_id ──────────────────────────────────────

class TestResolveOfficialId:
    """Name-to-UUID resolution for officials."""

    def test_exact_match(self):
        conn, cur = _make_conn()
        official_uuid = uuid.uuid4()
        cur.fetchone.return_value = (official_uuid,)
        cache = {}
        result = resolve_official_id(conn, "Jane Doe", "0660620", cache)
        assert result == official_uuid
        assert cache["Jane Doe"] == official_uuid

    def test_cache_hit_skips_query(self):
        conn, cur = _make_conn()
        cached_uuid = uuid.uuid4()
        cache = {"Jane Doe": cached_uuid}
        result = resolve_official_id(conn, "Jane Doe", "0660620", cache)
        assert result == cached_uuid
        cur.execute.assert_not_called()

    def test_no_match_returns_none(self):
        conn, cur = _make_conn()
        cur.fetchone.return_value = None
        cache = {}
        result = resolve_official_id(conn, "Unknown Person", "0660620", cache)
        assert result is None
        assert cache["Unknown Person"] is None

    def test_strips_parenthetical_suffix(self):
        """Handles names like 'Jane Doe (sitting council member)'."""
        conn, cur = _make_conn()
        official_uuid = uuid.uuid4()
        # First two queries return None, third (stripped) matches
        cur.fetchone.side_effect = [None, None, (official_uuid,)]
        cache = {}
        result = resolve_official_id(conn, "Jane Doe (sitting council member)", "0660620", cache)
        assert result == official_uuid


# ── resolve_agenda_item_id ───────────────────────────────────

class TestResolveAgendaItemId:
    """Item number to UUID resolution."""

    def test_found(self):
        conn, cur = _make_conn()
        item_uuid = uuid.uuid4()
        cur.fetchone.return_value = (item_uuid,)
        cache = {}
        result = resolve_agenda_item_id(conn, "meeting-123", "H-1", cache)
        assert result == item_uuid

    def test_none_item_number(self):
        conn, cur = _make_conn()
        result = resolve_agenda_item_id(conn, "meeting-123", None, {})
        assert result is None
        cur.execute.assert_not_called()


# ── run_batch_scan (v3 integration) ──────────────────────────

class TestRunBatchScanV3:
    """Batch scan passes v3 metadata to save_conflict_flag."""

    @patch("batch_scan.complete_scan_run")
    @patch("batch_scan.save_conflict_flag")
    @patch("batch_scan.supersede_flags_for_meeting")
    @patch("batch_scan.create_scan_run")
    @patch("batch_scan.prefilter_contributions")
    @patch("batch_scan._fetch_independent_expenditures_from_db")
    @patch("batch_scan._fetch_form700_interests_from_db")
    @patch("batch_scan._fetch_contributions_from_db")
    @patch("batch_scan.scan_meeting_db")
    @patch("batch_scan._fresh_conn")
    def test_passes_confidence_factors_and_scanner_version(
        self, mock_conn, mock_scan, mock_contribs, mock_form700, mock_ie,
        mock_prefilter, mock_create_run, mock_supersede, mock_save_flag, mock_complete,
    ):
        """save_conflict_flag receives confidence_factors and scanner_version from ConflictFlag."""
        conn, cur = _make_conn()
        mock_conn.return_value = conn

        meeting_id = uuid.uuid4()
        official_id = uuid.uuid4()
        cur.fetchall.return_value = [(meeting_id, date(2026, 1, 15))]
        cur.fetchone.return_value = (official_id,)  # resolve_official_id

        mock_contribs.return_value = []
        mock_form700.return_value = []
        mock_ie.return_value = []
        mock_prefilter.return_value = []

        flag = _make_flag()
        mock_scan.return_value = _make_scan_result(flags=[flag])
        mock_create_run.return_value = uuid.uuid4()

        run_batch_scan(dry_run=False)

        # Verify save_conflict_flag was called with v3 params
        mock_save_flag.assert_called_once()
        call_kwargs = mock_save_flag.call_args[1]
        assert call_kwargs["confidence_factors"] == flag.confidence_factors
        assert call_kwargs["scanner_version"] == 3

    @patch("batch_scan.complete_scan_run")
    @patch("batch_scan.save_conflict_flag")
    @patch("batch_scan.supersede_flags_for_meeting")
    @patch("batch_scan.create_scan_run")
    @patch("batch_scan.prefilter_contributions")
    @patch("batch_scan._fetch_independent_expenditures_from_db")
    @patch("batch_scan._fetch_form700_interests_from_db")
    @patch("batch_scan._fetch_contributions_from_db")
    @patch("batch_scan.scan_meeting_db")
    @patch("batch_scan._fresh_conn")
    def test_create_scan_run_has_scanner_version_3(
        self, mock_conn, mock_scan, mock_contribs, mock_form700, mock_ie,
        mock_prefilter, mock_create_run, mock_supersede, mock_save_flag, mock_complete,
    ):
        """Scan run is created with scanner_version='3'."""
        conn, cur = _make_conn()
        mock_conn.return_value = conn

        # Need at least one meeting to trigger create_scan_run
        meeting_id = uuid.uuid4()
        cur.fetchall.return_value = [(meeting_id, date(2026, 1, 15))]
        cur.fetchone.return_value = None  # no official match

        mock_contribs.return_value = []
        mock_form700.return_value = []
        mock_ie.return_value = []
        mock_prefilter.return_value = []
        mock_scan.return_value = _make_scan_result(flags=[])
        mock_create_run.return_value = uuid.uuid4()

        run_batch_scan(dry_run=False)

        mock_create_run.assert_called_once()
        call_kwargs = mock_create_run.call_args[1]
        assert call_kwargs["scanner_version"] == "3"

    @patch("batch_scan.complete_scan_run")
    @patch("batch_scan.save_conflict_flag")
    @patch("batch_scan.supersede_flags_for_meeting")
    @patch("batch_scan.create_scan_run")
    @patch("batch_scan.prefilter_contributions")
    @patch("batch_scan._fetch_independent_expenditures_from_db")
    @patch("batch_scan._fetch_form700_interests_from_db")
    @patch("batch_scan._fetch_contributions_from_db")
    @patch("batch_scan.scan_meeting_db")
    @patch("batch_scan._fresh_conn")
    def test_complete_scan_run_metadata_includes_scanner_version(
        self, mock_conn, mock_scan, mock_contribs, mock_form700, mock_ie,
        mock_prefilter, mock_create_run, mock_supersede, mock_save_flag, mock_complete,
    ):
        """Scan run completion metadata records scanner version."""
        conn, cur = _make_conn()
        mock_conn.return_value = conn

        meeting_id = uuid.uuid4()
        official_id = uuid.uuid4()
        cur.fetchall.return_value = [(meeting_id, date(2026, 1, 15))]
        cur.fetchone.return_value = (official_id,)

        mock_contribs.return_value = []
        mock_form700.return_value = []
        mock_ie.return_value = []
        mock_prefilter.return_value = []
        mock_scan.return_value = _make_scan_result(flags=[_make_flag()])
        mock_create_run.return_value = uuid.uuid4()

        run_batch_scan(dry_run=False)

        mock_complete.assert_called_once()
        metadata = mock_complete.call_args[1]["metadata"]
        assert metadata["scanner_version"] == SCANNER_VERSION

    @patch("batch_scan.save_conflict_flag")
    @patch("batch_scan.supersede_flags_for_meeting")
    @patch("batch_scan.create_scan_run")
    @patch("batch_scan.prefilter_contributions")
    @patch("batch_scan._fetch_independent_expenditures_from_db")
    @patch("batch_scan._fetch_form700_interests_from_db")
    @patch("batch_scan._fetch_contributions_from_db")
    @patch("batch_scan.scan_meeting_db")
    @patch("batch_scan._fresh_conn")
    def test_dry_run_does_not_save(
        self, mock_conn, mock_scan, mock_contribs, mock_form700, mock_ie,
        mock_prefilter, mock_create_run, mock_supersede, mock_save_flag,
    ):
        """Dry run mode prints but does not write to database."""
        conn, cur = _make_conn()
        mock_conn.return_value = conn

        meeting_id = uuid.uuid4()
        official_id = uuid.uuid4()
        cur.fetchall.return_value = [(meeting_id, date(2026, 1, 15))]
        cur.fetchone.return_value = (official_id,)

        mock_contribs.return_value = []
        mock_form700.return_value = []
        mock_ie.return_value = []
        mock_prefilter.return_value = []
        mock_scan.return_value = _make_scan_result(flags=[_make_flag()])

        run_batch_scan(dry_run=True)

        mock_save_flag.assert_not_called()
        mock_create_run.assert_not_called()
        mock_supersede.assert_not_called()

    @patch("batch_scan.complete_scan_run")
    @patch("batch_scan.save_conflict_flag")
    @patch("batch_scan.supersede_flags_for_meeting")
    @patch("batch_scan.create_scan_run")
    @patch("batch_scan.prefilter_contributions")
    @patch("batch_scan._fetch_independent_expenditures_from_db")
    @patch("batch_scan._fetch_form700_interests_from_db")
    @patch("batch_scan._fetch_contributions_from_db")
    @patch("batch_scan.scan_meeting_db")
    @patch("batch_scan._fresh_conn")
    def test_unresolved_official_skips_flag(
        self, mock_conn, mock_scan, mock_contribs, mock_form700, mock_ie,
        mock_prefilter, mock_create_run, mock_supersede, mock_save_flag, mock_complete,
    ):
        """Flags for unresolvable officials are skipped, not saved."""
        conn, cur = _make_conn()
        mock_conn.return_value = conn

        meeting_id = uuid.uuid4()
        cur.fetchall.return_value = [(meeting_id, date(2026, 1, 15))]
        cur.fetchone.return_value = None  # official not found

        mock_contribs.return_value = []
        mock_form700.return_value = []
        mock_ie.return_value = []
        mock_prefilter.return_value = []
        mock_scan.return_value = _make_scan_result(flags=[_make_flag()])
        mock_create_run.return_value = uuid.uuid4()

        run_batch_scan(dry_run=False)

        mock_save_flag.assert_not_called()


# ── TIER_LABELS import ───────────────────────────────────────

class TestTierLabelsExport:
    """TIER_LABELS is importable from conflict_scanner."""

    def test_tier_labels_has_all_tiers(self):
        from conflict_scanner import TIER_LABELS
        assert 1 in TIER_LABELS
        assert 2 in TIER_LABELS
        assert 3 in TIER_LABELS
        assert 4 in TIER_LABELS

    def test_tier_labels_match_confidence_to_tier(self):
        from conflict_scanner import TIER_LABELS, _confidence_to_tier
        for tier_num, expected_label in TIER_LABELS.items():
            # Find a confidence that maps to this tier
            if tier_num == 1:
                conf = 0.90
            elif tier_num == 2:
                conf = 0.75
            elif tier_num == 3:
                conf = 0.55
            else:
                conf = 0.30
            actual_tier, actual_label = _confidence_to_tier(conf)
            assert actual_tier == tier_num
            assert actual_label == expected_label
