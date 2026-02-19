"""Tests for periodic bias audit analysis."""
import json
import pytest
from pathlib import Path

from bias_audit import load_all_verdicts, compute_bias_statistics


class TestLoadAllVerdicts:
    """load_all_verdicts() reads ground truth from all sidecars."""

    def test_loads_verdicts_from_multiple_sidecars(self, tmp_path):
        for i in range(3):
            sidecar = {
                "scan_run_id": f"run-{i}",
                "decisions": [
                    {
                        "donor_name": f"Donor {i}",
                        "matched": True,
                        "ground_truth": True if i < 2 else False,
                        "bias_signals": {"surname_frequency_tier": 1, "has_compound_surname": False},
                    }
                ],
            }
            (tmp_path / f"run-{i}.json").write_text(json.dumps(sidecar))

        verdicts = load_all_verdicts(tmp_path)
        assert len(verdicts) == 3

    def test_skips_unreviewed_decisions(self, tmp_path):
        sidecar = {
            "scan_run_id": "run-1",
            "decisions": [
                {"donor_name": "A", "matched": True, "ground_truth": True, "bias_signals": {}},
                {"donor_name": "B", "matched": True, "ground_truth": None, "bias_signals": {}},
            ],
        }
        (tmp_path / "run-1.json").write_text(json.dumps(sidecar))
        verdicts = load_all_verdicts(tmp_path)
        assert len(verdicts) == 1

    def test_skips_suppressed_decisions(self, tmp_path):
        sidecar = {
            "scan_run_id": "run-1",
            "decisions": [
                {"donor_name": "A", "matched": True, "ground_truth": True, "bias_signals": {}},
                {"donor_name": "B", "matched": False, "ground_truth": None, "bias_signals": {}},
            ],
        }
        (tmp_path / "run-1.json").write_text(json.dumps(sidecar))
        verdicts = load_all_verdicts(tmp_path)
        assert len(verdicts) == 1

    def test_skips_bias_audit_report_files(self, tmp_path):
        """bias_audit_report_*.json files should not be loaded as sidecars."""
        sidecar = {
            "scan_run_id": "run-1",
            "decisions": [
                {"donor_name": "A", "matched": True, "ground_truth": True, "bias_signals": {}},
            ],
        }
        (tmp_path / "run-1.json").write_text(json.dumps(sidecar))
        # This should be skipped
        (tmp_path / "bias_audit_report_20260219.json").write_text(json.dumps({"overall": {}}))
        verdicts = load_all_verdicts(tmp_path)
        assert len(verdicts) == 1


class TestComputeBiasStatistics:
    """compute_bias_statistics() computes per-tier false positive rates."""

    def test_computes_fp_rate_by_tier(self):
        verdicts = [
            {"ground_truth": True, "bias_signals": {"surname_frequency_tier": 1}},
            {"ground_truth": True, "bias_signals": {"surname_frequency_tier": 1}},
            {"ground_truth": False, "bias_signals": {"surname_frequency_tier": 4}},
            {"ground_truth": False, "bias_signals": {"surname_frequency_tier": 4}},
            {"ground_truth": True, "bias_signals": {"surname_frequency_tier": 4}},
        ]
        stats = compute_bias_statistics(verdicts)
        assert stats["overall"]["total"] == 5
        assert stats["overall"]["true_positives"] == 3
        assert stats["overall"]["false_positives"] == 2
        # Tier 1: 2 TP, 0 FP => FP rate 0.0
        assert stats["by_surname_tier"][1]["false_positive_rate"] == 0.0
        # Tier 4: 1 TP, 2 FP => FP rate ~0.667
        assert abs(stats["by_surname_tier"][4]["false_positive_rate"] - 2/3) < 0.01

    def test_handles_empty_verdicts(self):
        stats = compute_bias_statistics([])
        assert stats["overall"]["total"] == 0

    def test_computes_name_property_stats(self):
        verdicts = [
            {"ground_truth": True, "bias_signals": {"has_compound_surname": True, "has_diacritics": False}},
            {"ground_truth": False, "bias_signals": {"has_compound_surname": True, "has_diacritics": False}},
            {"ground_truth": True, "bias_signals": {"has_compound_surname": False, "has_diacritics": False}},
        ]
        stats = compute_bias_statistics(verdicts)
        # Compound surnames: 1 TP + 1 FP => 50% FP rate
        assert stats["by_name_property"]["has_compound_surname"]["with"]["total"] == 2
        assert stats["by_name_property"]["has_compound_surname"]["with"]["false_positive_rate"] == 0.5
        # Non-compound: 1 TP => 0% FP rate
        assert stats["by_name_property"]["has_compound_surname"]["without"]["false_positive_rate"] == 0.0
