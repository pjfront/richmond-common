"""Tests for audit sidecar persistence in pipeline and scanner CLI."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from conflict_scanner import scan_meeting_json


def _make_meeting(items):
    return {
        "meeting_date": "2026-02-17",
        "meeting_type": "regular",
        "consent_calendar": {"items": items},
        "action_items": [],
        "housing_authority_items": [],
    }


class TestAuditSidecarPersistence:
    """run_pipeline saves audit sidecar to src/data/audit_runs/."""

    def test_scan_result_audit_log_saveable(self, tmp_path):
        """ScanResult.audit_log.save() produces valid JSON."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with TestCo",
            "description": "APPROVE contract with TestCo for services",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [{
            "donor_name": "Jane Doe",
            "donor_employer": "TestCo",
            "committee_name": "Wilson for Richmond 2024",
            "amount": 500,
            "date": "2024-01-01",
            "filing_id": "999",
            "source": "test",
        }]
        result = scan_meeting_json(meeting, contributions)
        audit_path = tmp_path / "audit_runs" / f"{result.scan_run_id}.json"
        result.audit_log.save(audit_path)

        assert audit_path.exists()
        data = json.loads(audit_path.read_text())
        assert data["scan_run_id"] == result.scan_run_id
        assert "decisions" in data
        assert "summary" in data
