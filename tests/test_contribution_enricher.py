"""Tests for contribution_enricher.py — donor pattern classification."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from contribution_enricher import (
    DonorContext,
    PatternThresholds,
    classify_donor_pattern,
    enrich_donors,
    is_pac_name,
)


# ── PAC name detection ────────────────────────────────────────────


class TestIsPacName:
    """Tests for PAC/committee name detection."""

    @pytest.mark.parametrize(
        "name",
        [
            "Richmond Police Officers Association PAC",
            "SEIU Local 1021 Candidate PAC",
            "Committee for Quality Government",
            "California Workers' Justice Coalition Sponsored by SEIU",
            "International Federation of Professional and Technical Engineers PAC Fund",
            "Independent PAC Local 188 IAFF",
            "East Bay Working Families Political Action Committee",
            "AFL-CIO Local 123",
        ],
    )
    def test_pac_names_detected(self, name):
        assert is_pac_name(name), f"Should detect PAC: {name}"

    @pytest.mark.parametrize(
        "name",
        [
            "John Smith",
            "CHEVRON",
            "M. Quinn Delaney",
            "Richmond Community Foundation",
            "Tom Butt",
            "East Bay Express",
        ],
    )
    def test_non_pac_names_not_detected(self, name):
        assert not is_pac_name(name), f"Should NOT detect PAC: {name}"


# ── Pattern classification ────────────────────────────────────────


class TestClassifyDonorPattern:
    """Tests for classify_donor_pattern with default thresholds."""

    def _make_ctx(self, **kwargs) -> DonorContext:
        """Helper to create a DonorContext with defaults."""
        defaults = dict(
            donor_id=str(uuid.uuid4()),
            donor_name="Test Donor",
            contribution_count=5,
            total_contributed=1000.0,
            avg_contribution=200.0,
            distinct_recipients=2,
            contribution_span_days=365,
        )
        defaults.update(kwargs)
        return DonorContext(**defaults)

    # ── PAC (priority 1) ──

    def test_pac_classification(self):
        """PAC name pattern overrides all other signals."""
        ctx = self._make_ctx(
            donor_name="SEIU Local 1021 Candidate PAC",
            total_contributed=500_000.0,  # Also mega-level
        )
        assert classify_donor_pattern(ctx) == "pac"

    def test_pac_with_small_donations(self):
        """PAC classification even with grassroots-level amounts."""
        ctx = self._make_ctx(
            donor_name="Neighborhood Coalition for Better Parks",
            total_contributed=500.0,
            avg_contribution=50.0,
        )
        assert classify_donor_pattern(ctx) == "pac"

    # ── Mega (priority 2) ──

    def test_mega_classification(self):
        ctx = self._make_ctx(
            total_contributed=100_000.0,
            avg_contribution=50_000.0,
            distinct_recipients=1,
        )
        assert classify_donor_pattern(ctx) == "mega"

    def test_mega_threshold_boundary(self):
        """Exactly at threshold = mega."""
        ctx = self._make_ctx(total_contributed=75_000.0)
        assert classify_donor_pattern(ctx) == "mega"

    def test_below_mega_threshold(self):
        """Just below threshold = not mega."""
        ctx = self._make_ctx(total_contributed=74_999.99)
        assert classify_donor_pattern(ctx) != "mega"

    # ── Grassroots (priority 3) ──

    def test_grassroots_classification(self):
        ctx = self._make_ctx(
            contribution_count=10,
            total_contributed=1_500.0,
            avg_contribution=150.0,
            distinct_recipients=3,
        )
        assert classify_donor_pattern(ctx) == "grassroots"

    def test_grassroots_requires_multiple_recipients(self):
        """Small average but only 1 recipient = not grassroots."""
        ctx = self._make_ctx(
            contribution_count=5,
            total_contributed=500.0,
            avg_contribution=100.0,
            distinct_recipients=1,
        )
        assert classify_donor_pattern(ctx) != "grassroots"

    def test_grassroots_requires_minimum_contributions(self):
        """Too few contributions = not grassroots even with small avg."""
        ctx = self._make_ctx(
            contribution_count=2,
            total_contributed=200.0,
            avg_contribution=100.0,
            distinct_recipients=2,
        )
        assert classify_donor_pattern(ctx) != "grassroots"

    def test_grassroots_avg_boundary(self):
        """Exactly at avg threshold = grassroots."""
        ctx = self._make_ctx(
            contribution_count=4,
            avg_contribution=250.0,
            distinct_recipients=2,
        )
        assert classify_donor_pattern(ctx) == "grassroots"

    # ── Targeted (priority 4) ──

    def test_targeted_classification(self):
        ctx = self._make_ctx(
            contribution_count=3,
            total_contributed=10_000.0,
            avg_contribution=3_333.33,
            distinct_recipients=1,
        )
        assert classify_donor_pattern(ctx) == "targeted"

    def test_targeted_two_recipients(self):
        """Up to 2 recipients still counts as targeted."""
        ctx = self._make_ctx(
            contribution_count=4,
            total_contributed=8_000.0,
            avg_contribution=2_000.0,
            distinct_recipients=2,
        )
        assert classify_donor_pattern(ctx) == "targeted"

    def test_targeted_requires_min_total(self):
        """High average but low total = not targeted."""
        ctx = self._make_ctx(
            contribution_count=2,
            total_contributed=3_000.0,
            avg_contribution=1_500.0,
            distinct_recipients=1,
        )
        assert classify_donor_pattern(ctx) != "targeted"

    def test_targeted_too_many_recipients(self):
        """3+ recipients = not targeted."""
        ctx = self._make_ctx(
            contribution_count=5,
            total_contributed=10_000.0,
            avg_contribution=2_000.0,
            distinct_recipients=3,
        )
        assert classify_donor_pattern(ctx) != "targeted"

    # ── Regular (default) ──

    def test_regular_default(self):
        """Moderate donor that doesn't match any pattern."""
        ctx = self._make_ctx(
            contribution_count=3,
            total_contributed=1_500.0,
            avg_contribution=500.0,
            distinct_recipients=1,
        )
        assert classify_donor_pattern(ctx) == "regular"

    def test_no_contributions(self):
        """Donor with zero contributions = regular."""
        ctx = self._make_ctx(
            contribution_count=0,
            total_contributed=0.0,
            avg_contribution=None,
            distinct_recipients=0,
        )
        assert classify_donor_pattern(ctx) == "regular"

    def test_null_avg_contribution(self):
        """None avg_contribution handled gracefully."""
        ctx = self._make_ctx(
            contribution_count=1,
            total_contributed=100.0,
            avg_contribution=None,
            distinct_recipients=1,
        )
        assert classify_donor_pattern(ctx) == "regular"

    # ── Priority ordering ──

    def test_pac_beats_mega(self):
        """PAC classification has highest priority."""
        ctx = self._make_ctx(
            donor_name="Richmond Police Officers Association PAC",
            total_contributed=1_000_000.0,
        )
        assert classify_donor_pattern(ctx) == "pac"

    def test_mega_beats_targeted(self):
        """Mega beats targeted for high-dollar concentrated donors."""
        ctx = self._make_ctx(
            total_contributed=100_000.0,
            avg_contribution=50_000.0,
            distinct_recipients=1,
        )
        assert classify_donor_pattern(ctx) == "mega"


# ── Custom thresholds ─────────────────────────────────────────────


class TestCustomThresholds:
    """Test that thresholds are configurable (multi-city scaling)."""

    def test_lower_mega_threshold(self):
        thresholds = PatternThresholds(mega_total_min=10_000.0)
        ctx = DonorContext(
            donor_id=str(uuid.uuid4()),
            donor_name="Test Donor",
            contribution_count=5,
            total_contributed=15_000.0,
            avg_contribution=3_000.0,
            distinct_recipients=2,
            contribution_span_days=100,
        )
        assert classify_donor_pattern(ctx, thresholds) == "mega"

    def test_higher_grassroots_avg(self):
        thresholds = PatternThresholds(grassroots_avg_max=500.0)
        ctx = DonorContext(
            donor_id=str(uuid.uuid4()),
            donor_name="Test Donor",
            contribution_count=10,
            total_contributed=3_500.0,
            avg_contribution=350.0,
            distinct_recipients=3,
            contribution_span_days=500,
        )
        assert classify_donor_pattern(ctx, thresholds) == "grassroots"


# ── DonorContext.from_row ─────────────────────────────────────────


class TestDonorContextFromRow:
    """Tests for parsing database rows into DonorContext."""

    def test_normal_row(self):
        row = (
            uuid.uuid4(),
            "John Smith",
            10,
            5000.0,
            500.0,
            3,
            730,
        )
        ctx = DonorContext.from_row(row)
        assert ctx.donor_name == "John Smith"
        assert ctx.contribution_count == 10
        assert ctx.total_contributed == 5000.0
        assert ctx.avg_contribution == 500.0
        assert ctx.distinct_recipients == 3
        assert ctx.contribution_span_days == 730

    def test_null_values(self):
        row = (uuid.uuid4(), None, None, None, None, None, None)
        ctx = DonorContext.from_row(row)
        assert ctx.donor_name == ""
        assert ctx.contribution_count == 0
        assert ctx.total_contributed == 0.0
        assert ctx.avg_contribution is None
        assert ctx.distinct_recipients == 0
        assert ctx.contribution_span_days is None


# ── enrich_donors (integration-style with mocked DB) ──────────────


class TestEnrichDonors:
    """Test the batch enrichment function with mocked database."""

    def _make_mock_conn(self, rows):
        """Create a mock connection returning given rows."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return mock_conn, mock_cursor

    def test_dry_run_no_updates(self):
        rows = [
            (uuid.uuid4(), "Test PAC", 5, 10000.0, 2000.0, 2, 100),
            (uuid.uuid4(), "Jane Doe", 3, 500.0, 166.67, 1, 30),
        ]
        conn, cursor = self._make_mock_conn(rows)

        stats = enrich_donors(conn, city_fips="0660620", dry_run=True)

        assert stats["pac"] == 1
        assert stats["regular"] == 1
        assert stats["total"] == 2
        # Dry run should not commit
        conn.commit.assert_not_called()

    def test_live_run_commits(self):
        rows = [
            (uuid.uuid4(), "M. Quinn Delaney", 6, 300000.0, 50000.0, 1, 0),
            (uuid.uuid4(), "SEIU PAC", 10, 50000.0, 5000.0, 3, 500),
        ]
        conn, cursor = self._make_mock_conn(rows)

        stats = enrich_donors(conn, city_fips="0660620", dry_run=False)

        assert stats["mega"] == 1
        assert stats["pac"] == 1
        assert stats["total"] == 2
        conn.commit.assert_called_once()

    def test_empty_city(self):
        conn, cursor = self._make_mock_conn([])

        stats = enrich_donors(conn, city_fips="9999999")

        assert stats["total"] == 0
        assert stats["updated"] == 0


# ── Real-world Richmond donor archetypes ──────────────────────────


class TestRichmondArchetypes:
    """Test classification against known Richmond donor archetypes."""

    def _make_ctx(self, **kwargs) -> DonorContext:
        defaults = dict(
            donor_id=str(uuid.uuid4()),
            donor_name="Test",
            contribution_count=1,
            total_contributed=100.0,
            avg_contribution=100.0,
            distinct_recipients=1,
            contribution_span_days=0,
        )
        defaults.update(kwargs)
        return DonorContext(**defaults)

    def test_chevron_mega(self):
        """Chevron: massive spending to single committee."""
        ctx = self._make_ctx(
            donor_name="CHEVRON",
            contribution_count=18,
            total_contributed=1_887_103.65,
            avg_contribution=104_839.09,
            distinct_recipients=1,
            contribution_span_days=47,
        )
        assert classify_donor_pattern(ctx) == "mega"

    def test_seiu_pac(self):
        """SEIU Local 1021 Candidate PAC: PAC name overrides mega."""
        ctx = self._make_ctx(
            donor_name="Service Employees International Union Local 1021 Candidate PAC",
            contribution_count=55,
            total_contributed=1_952_000.0,
            avg_contribution=35_490.91,
            distinct_recipients=4,
            contribution_span_days=2401,
        )
        assert classify_donor_pattern(ctx) == "pac"

    def test_rpoa_pac(self):
        """Richmond Police Officers Association PAC."""
        ctx = self._make_ctx(
            donor_name="Richmond Police Officers Association PAC",
            contribution_count=87,
            total_contributed=1_704_082.67,
            avg_contribution=19_587.16,
            distinct_recipients=11,
            contribution_span_days=6953,
        )
        assert classify_donor_pattern(ctx) == "pac"

    def test_quinn_delaney_mega(self):
        """M. Quinn Delaney: individual mega donor."""
        ctx = self._make_ctx(
            donor_name="M. Quinn Delaney",
            contribution_count=6,
            total_contributed=300_000.0,
            avg_contribution=50_000.0,
            distinct_recipients=1,
            contribution_span_days=0,
        )
        assert classify_donor_pattern(ctx) == "mega"

    def test_small_grassroots_donor(self):
        """Typical grassroots: many small donations, multiple candidates."""
        ctx = self._make_ctx(
            donor_name="Maria Garcia",
            contribution_count=8,
            total_contributed=800.0,
            avg_contribution=100.0,
            distinct_recipients=3,
            contribution_span_days=1200,
        )
        assert classify_donor_pattern(ctx) == "grassroots"

    def test_single_donation_regular(self):
        """One-time $500 donor: regular."""
        ctx = self._make_ctx(
            donor_name="Robert Johnson",
            contribution_count=1,
            total_contributed=500.0,
            avg_contribution=500.0,
            distinct_recipients=1,
            contribution_span_days=0,
        )
        assert classify_donor_pattern(ctx) == "regular"

    def test_moderate_targeted_donor(self):
        """Higher-dollar donor focused on one candidate."""
        ctx = self._make_ctx(
            donor_name="Bay Area Developer LLC",
            contribution_count=4,
            total_contributed=8_000.0,
            avg_contribution=2_000.0,
            distinct_recipients=1,
            contribution_span_days=90,
        )
        assert classify_donor_pattern(ctx) == "targeted"
