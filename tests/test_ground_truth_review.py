"""Tests for ground truth review CLI."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from io import StringIO

from conflict_scanner import load_audit_sidecar, apply_verdict


class TestLoadAuditSidecar:
    """load_audit_sidecar() reads and parses a JSON sidecar file."""

    def test_loads_valid_sidecar(self, tmp_path):
        sidecar = {
            "scan_run_id": "test-123",
            "created_at": "2026-02-19T00:00:00Z",
            "decisions": [
                {
                    "donor_name": "John Smith",
                    "donor_employer": "Acme",
                    "agenda_item_number": "V.1",
                    "agenda_text_preview": "Contract text",
                    "match_type": "exact",
                    "confidence": 0.7,
                    "matched": True,
                    "bias_signals": {"has_compound_surname": False},
                    "ground_truth": None,
                    "ground_truth_source": None,
                    "audit_notes": None,
                }
            ],
            "summary": {"scan_run_id": "test-123", "meeting_date": "2026-02-17"},
        }
        path = tmp_path / "test-123.json"
        path.write_text(json.dumps(sidecar))
        data = load_audit_sidecar(path)
        assert data["scan_run_id"] == "test-123"
        assert len(data["decisions"]) == 1

    def test_returns_none_for_missing_file(self, tmp_path):
        data = load_audit_sidecar(tmp_path / "nonexistent.json")
        assert data is None


class TestApplyVerdict:
    """apply_verdict() updates a decision with ground truth."""

    def test_true_positive(self):
        decision = {
            "donor_name": "John Smith",
            "ground_truth": None,
            "ground_truth_source": None,
            "audit_notes": None,
        }
        apply_verdict(decision, verdict="T", notes=None)
        assert decision["ground_truth"] is True
        assert "manual_review" in decision["ground_truth_source"]

    def test_false_positive(self):
        decision = {
            "donor_name": "John Smith",
            "ground_truth": None,
            "ground_truth_source": None,
            "audit_notes": None,
        }
        apply_verdict(decision, verdict="F", notes="Not the same entity")
        assert decision["ground_truth"] is False
        assert decision["audit_notes"] == "Not the same entity"
