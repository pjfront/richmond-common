"""Tests for B.51 anomaly factor implementation.

Covers: build_contribution_baselines, compute_anomaly_factor,
integration with composite confidence and scan_meeting_json.
"""
from __future__ import annotations

import pytest
from conflict_scanner import (
    build_contribution_baselines,
    compute_anomaly_factor,
    compute_composite_confidence,
    ContributionBaselines,
    DEFAULT_ANOMALY_FACTOR,
    MIN_CONTRIBUTIONS_FOR_BASELINES,
    RawSignal,
    scan_meeting_json,
)


# ── build_contribution_baselines ──────────────────────────────

class TestBuildContributionBaselines:
    """B.51: Statistical baselines from contribution data."""

    def test_sufficient_data_has_baselines(self):
        """50+ contributions produce valid baselines."""
        contribs = [{"amount": i * 100} for i in range(1, 101)]
        baselines = build_contribution_baselines(contribs)
        assert baselines.has_baselines is True
        assert baselines.count == 100
        assert baselines.mean > 0
        assert baselines.stddev > 0
        assert baselines.median > 0

    def test_insufficient_data_no_baselines(self):
        """Fewer than 50 contributions fall back."""
        contribs = [{"amount": 100} for _ in range(49)]
        baselines = build_contribution_baselines(contribs)
        assert baselines.has_baselines is False
        assert baselines.count == 49

    def test_empty_contributions(self):
        baselines = build_contribution_baselines([])
        assert baselines.has_baselines is False
        assert baselines.count == 0

    def test_zero_amounts_excluded(self):
        """Zero and negative amounts are excluded from baselines."""
        contribs = [{"amount": 0}] * 30 + [{"amount": 100}] * 50
        baselines = build_contribution_baselines(contribs)
        assert baselines.has_baselines is True
        assert baselines.count == 50  # zeros excluded

    def test_percentiles_ordered(self):
        """Percentiles are monotonically increasing."""
        contribs = [{"amount": i * 10} for i in range(1, 201)]
        baselines = build_contribution_baselines(contribs)
        assert baselines.median <= baselines.p75
        assert baselines.p75 <= baselines.p90
        assert baselines.p90 <= baselines.p95
        assert baselines.p95 <= baselines.p99

    def test_uniform_distribution(self):
        """All same amounts produce zero stddev."""
        contribs = [{"amount": 500}] * 100
        baselines = build_contribution_baselines(contribs)
        assert baselines.mean == 500
        assert baselines.stddev == 0.0


# ── compute_anomaly_factor ────────────────────────────────────

class TestComputeAnomalyFactor:
    """B.51: Anomaly scoring based on statistical baselines."""

    @pytest.fixture
    def baselines(self):
        """Baselines from a typical distribution."""
        contribs = [{"amount": i * 50} for i in range(1, 201)]
        return build_contribution_baselines(contribs)

    def test_no_baselines_returns_default(self):
        """Without baselines, return the neutral default."""
        no_baselines = ContributionBaselines(
            mean=0, median=0, stddev=0,
            p75=0, p90=0, p95=0, p99=0,
            count=10, has_baselines=False,
        )
        result = compute_anomaly_factor(1000, no_baselines)
        assert result == DEFAULT_ANOMALY_FACTOR

    def test_typical_amount_low_anomaly(self, baselines):
        """Amount near the mean scores low anomaly (0.3)."""
        result = compute_anomaly_factor(baselines.mean, baselines)
        assert result <= 0.4  # within 1 stddev

    def test_high_amount_high_anomaly(self, baselines):
        """Amount far above mean scores high anomaly."""
        extreme = baselines.mean + 4 * baselines.stddev
        result = compute_anomaly_factor(extreme, baselines)
        assert result >= 0.9

    def test_moderately_high_amount(self, baselines):
        """Amount 1.5 stddev above mean scores moderate anomaly."""
        moderate = baselines.mean + 1.5 * baselines.stddev
        result = compute_anomaly_factor(moderate, baselines)
        assert 0.4 <= result <= 0.6

    def test_above_p99_is_high_anomaly(self, baselines):
        """Amount above 99th percentile always gets high anomaly."""
        result = compute_anomaly_factor(baselines.p99 + 1000, baselines)
        assert result >= 0.9

    def test_above_p95_moderate_minimum(self, baselines):
        """Amount above 95th percentile gets at least 0.7."""
        result = compute_anomaly_factor(baselines.p95 + 1, baselines)
        assert result >= 0.7

    def test_temporal_boost_within_30_days(self, baselines):
        """Contribution within 30 days of meeting gets +0.1 boost."""
        base = compute_anomaly_factor(
            baselines.mean, baselines,
            contribution_date="", meeting_date="",
        )
        boosted = compute_anomaly_factor(
            baselines.mean, baselines,
            contribution_date="2026-02-01", meeting_date="2026-02-15",
        )
        assert boosted == pytest.approx(base + 0.1, abs=0.01)

    def test_temporal_no_boost_beyond_30_days(self, baselines):
        """Contribution 60 days from meeting gets no temporal boost."""
        base = compute_anomaly_factor(
            baselines.mean, baselines,
            contribution_date="", meeting_date="",
        )
        no_boost = compute_anomaly_factor(
            baselines.mean, baselines,
            contribution_date="2025-12-01", meeting_date="2026-02-15",
        )
        assert no_boost == pytest.approx(base, abs=0.01)

    def test_zero_stddev_different_amount(self):
        """When all contributions are the same, different amount is anomalous."""
        uniform_baselines = ContributionBaselines(
            mean=500, median=500, stddev=0,
            p75=500, p90=500, p95=500, p99=500,
            count=100, has_baselines=True,
        )
        result = compute_anomaly_factor(5000, uniform_baselines)
        assert result >= 0.9  # treated as >3 stddev

    def test_result_always_between_0_and_1(self, baselines):
        """Anomaly factor is always in [0.0, 1.0]."""
        for amount in [0.01, 1, 100, 1000, 10000, 100000, 1000000]:
            result = compute_anomaly_factor(amount, baselines)
            assert 0.0 <= result <= 1.0


# ── Integration with composite confidence ─────────────────────

class TestAnomalyInCompositeConfidence:
    """B.51: Per-signal anomaly factors in composite confidence."""

    def _make_signal(self, anomaly_factor=DEFAULT_ANOMALY_FACTOR):
        return RawSignal(
            signal_type="campaign_contribution",
            council_member="Sue Wilson (sitting council member)",
            agenda_item_number="V.6.a",
            match_strength=0.85,
            temporal_factor=0.8,
            financial_factor=0.7,
            description="Test signal",
            evidence=["test"],
            legal_reference="Gov. Code SS 87100",
            anomaly_factor=anomaly_factor,
            match_details={"is_sitting": True},
        )

    def test_high_anomaly_increases_confidence(self):
        """Signal with high anomaly scores higher than one with default."""
        default_signal = self._make_signal(anomaly_factor=0.5)
        high_signal = self._make_signal(anomaly_factor=0.9)

        default_result = compute_composite_confidence([default_signal])
        high_result = compute_composite_confidence([high_signal])

        assert high_result["confidence"] > default_result["confidence"]

    def test_anomaly_factor_in_factors_dict(self):
        """Anomaly factor value appears in the factors breakdown."""
        signal = self._make_signal(anomaly_factor=0.8)
        result = compute_composite_confidence([signal])
        assert result["factors"]["anomaly_factor"] == 0.8

    def test_max_anomaly_across_signals(self):
        """When multiple signals, max anomaly_factor is used."""
        signals = [
            self._make_signal(anomaly_factor=0.3),
            self._make_signal(anomaly_factor=0.9),
        ]
        # Different signal types for these to be truly independent
        signals[1].signal_type = "donor_vendor_expenditure"
        result = compute_composite_confidence(signals)
        assert result["factors"]["anomaly_factor"] == 0.9

    def test_explicit_override_still_works(self):
        """Passing anomaly_factor explicitly overrides per-signal values."""
        signal = self._make_signal(anomaly_factor=0.9)
        result = compute_composite_confidence([signal], anomaly_factor=0.3)
        assert result["factors"]["anomaly_factor"] == 0.3


# ── Integration with scan_meeting_json ────────────────────────

class TestAnomalyInScan:
    """B.51: Full scan uses baselines when sufficient data exists."""

    def test_scan_with_many_contributions_uses_baselines(self):
        """With 50+ contributions, anomaly_factor varies from default."""
        meeting = {
            "meeting_date": "2026-03-04",
            "meeting_type": "regular",
            "members_present": [{"name": "Sue Wilson"}],
            "consent_calendar": {
                "items": [{
                    "item_number": "V.6.a",
                    "title": "Approve Contract with Maier Consulting",
                    "description": "Contract with Maier Consulting for environmental review.",
                    "financial_amount": "$50,000",
                }]
            },
            "action_items": [],
            "housing_authority_items": [],
        }
        # 60 small contributions + 1 large one to match
        contributions = [
            {
                "donor_name": f"Donor {i}",
                "donor_employer": "",
                "council_member": "",
                "committee_name": "Wilson for Richmond 2024",
                "amount": 100 + i,
                "date": "2025-06-01",
                "filing_id": f"TEST-{i:03d}",
                "source": "netfile",
            }
            for i in range(60)
        ]
        # Add the matching contribution with an anomalous amount
        contributions.append({
            "donor_name": "Maier Consulting",
            "donor_employer": "",
            "council_member": "",
            "committee_name": "Wilson for Richmond 2024",
            "amount": 50000,  # Way above baseline
            "date": "2026-02-15",
            "filing_id": "TEST-MATCH",
            "source": "netfile",
        })
        result = scan_meeting_json(meeting, contributions)
        assert len(result.flags) >= 1
        flag = result.flags[0]
        # With baselines, anomaly_factor should be high (>0.5) for this outlier
        assert flag.confidence_factors["anomaly_factor"] > 0.5

    def test_scan_with_few_contributions_uses_default(self):
        """With <50 contributions, falls back to default 0.5."""
        meeting = {
            "meeting_date": "2026-03-04",
            "meeting_type": "regular",
            "members_present": [{"name": "Sue Wilson"}],
            "consent_calendar": {
                "items": [{
                    "item_number": "V.6.a",
                    "title": "Approve Contract with Maier Consulting",
                    "description": "Contract with Maier Consulting for environmental review.",
                    "financial_amount": "$50,000",
                }]
            },
            "action_items": [],
            "housing_authority_items": [],
        }
        contributions = [{
            "donor_name": "Maier Consulting",
            "donor_employer": "",
            "council_member": "",
            "committee_name": "Wilson for Richmond 2024",
            "amount": 5000,
            "date": "2026-02-15",
            "filing_id": "TEST-001",
            "source": "netfile",
        }]
        result = scan_meeting_json(meeting, contributions)
        if result.flags:
            # Should use default 0.5 since <50 contributions
            assert result.flags[0].confidence_factors["anomaly_factor"] == 0.5
