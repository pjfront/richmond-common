"""Tests for scan audit logging — matching decisions and scan summary."""
import json
import uuid
import pytest
from pathlib import Path

from scan_audit import (
    MatchingDecision,
    ScanAuditSummary,
    ScanAuditLogger,
)


class TestMatchingDecision:
    """MatchingDecision captures one match or near-miss."""

    def test_creates_with_required_fields(self):
        d = MatchingDecision(
            donor_name="Cheryl Maier",
            donor_employer="Acme Environmental",
            agenda_item_number="V.3.a",
            agenda_text_preview="Approve contract with Acme",
            match_type="contains",
            confidence=0.5,
            matched=True,
        )
        assert d.donor_name == "Cheryl Maier"
        assert d.matched is True

    def test_bias_signals_computed(self):
        """Bias risk signals auto-computed from donor name."""
        d = MatchingDecision(
            donor_name="Maria Garcia-Lopez",
            donor_employer="",
            agenda_item_number="V.1",
            agenda_text_preview="Some item text",
            match_type="exact",
            confidence=0.7,
            matched=True,
        )
        assert d.bias_signals["has_compound_surname"] is True

    def test_to_dict_serializable(self):
        """to_dict() produces JSON-serializable output."""
        d = MatchingDecision(
            donor_name="John Smith",
            donor_employer="Acme Corp",
            agenda_item_number="V.1.a",
            agenda_text_preview="Contract text",
            match_type="exact",
            confidence=0.7,
            matched=True,
        )
        result = d.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(result)
        assert "John Smith" in json_str
        assert "bias_signals" in result


class TestScanAuditSummary:
    """ScanAuditSummary captures per-scan filter funnel statistics."""

    def test_creates_with_defaults(self):
        s = ScanAuditSummary(
            scan_run_id="test-123",
            city_fips="0660620",
            meeting_date="2026-02-17",
            total_agenda_items=27,
            total_contributions_compared=1000,
        )
        assert s.filtered_short_name == 0
        assert s.passed_to_flag == 0

    def test_increment_filter_counts(self):
        s = ScanAuditSummary(
            scan_run_id="test-123",
            city_fips="0660620",
            meeting_date="2026-02-17",
            total_agenda_items=27,
            total_contributions_compared=1000,
        )
        s.filtered_short_name += 5
        s.filtered_govt_employer += 3
        s.passed_to_flag += 2
        assert s.filtered_short_name == 5
        assert s.total_comparisons == 27 * 1000

    def test_to_dict_serializable(self):
        s = ScanAuditSummary(
            scan_run_id="test-123",
            city_fips="0660620",
            meeting_date="2026-02-17",
            total_agenda_items=10,
            total_contributions_compared=100,
        )
        result = s.to_dict()
        json_str = json.dumps(result)
        assert "total_comparisons" in json_str


class TestScanAuditLogger:
    """ScanAuditLogger writes JSON sidecar files."""

    def test_log_decision(self):
        logger = ScanAuditLogger(scan_run_id="test-abc")
        logger.log_decision(MatchingDecision(
            donor_name="John Smith",
            donor_employer="Acme",
            agenda_item_number="V.1",
            agenda_text_preview="Contract text",
            match_type="exact",
            confidence=0.7,
            matched=True,
        ))
        assert len(logger.decisions) == 1

    def test_log_near_miss(self):
        """Near-misses (suppressed matches) are logged with matched=False."""
        logger = ScanAuditLogger(scan_run_id="test-abc")
        logger.log_decision(MatchingDecision(
            donor_name="Eduardo Martinez",
            donor_employer="",
            agenda_item_number="V.1",
            agenda_text_preview="Some item",
            match_type="suppressed_council_member",
            confidence=0.0,
            matched=False,
        ))
        assert len(logger.decisions) == 1
        assert logger.decisions[0].matched is False

    def test_save_to_json(self, tmp_path):
        """save() writes decisions + summary to JSON file."""
        logger = ScanAuditLogger(scan_run_id="test-xyz")
        logger.log_decision(MatchingDecision(
            donor_name="Test Donor",
            donor_employer="Test Employer",
            agenda_item_number="V.1",
            agenda_text_preview="Contract text",
            match_type="contains",
            confidence=0.5,
            matched=True,
        ))
        logger.summary = ScanAuditSummary(
            scan_run_id="test-xyz",
            city_fips="0660620",
            meeting_date="2026-02-17",
            total_agenda_items=10,
            total_contributions_compared=100,
        )
        logger.summary.passed_to_flag = 1

        output_path = tmp_path / "audit.json"
        logger.save(output_path)

        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert data["scan_run_id"] == "test-xyz"
        assert len(data["decisions"]) == 1
        assert data["summary"]["passed_to_flag"] == 1

    def test_generate_scan_run_id(self):
        """Each logger generates a unique scan_run_id if not provided."""
        logger1 = ScanAuditLogger()
        logger2 = ScanAuditLogger()
        assert logger1.scan_run_id != logger2.scan_run_id
        # Should be valid UUID
        uuid.UUID(logger1.scan_run_id)
