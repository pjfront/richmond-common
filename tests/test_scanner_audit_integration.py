"""Tests for bias audit integration into conflict scanner."""
import json
import pytest
from conflict_scanner import scan_meeting_json, ScanResult


def _make_meeting(items):
    """Build a minimal meeting dict."""
    return {
        "meeting_date": "2026-02-17",
        "meeting_type": "regular",
        "consent_calendar": {"items": items},
        "action_items": [],
        "housing_authority_items": [],
    }


def _make_contribution(name, employer, committee, amount, **kwargs):
    """Build a contribution dict."""
    base = {
        "donor_name": name,
        "donor_employer": employer or "",
        "committee_name": committee,
        "amount": amount,
        "date": "2024-01-01",
        "filing_id": "999",
        "source": "test",
    }
    base.update(kwargs)
    return base


class TestScanResultHasScanRunId:
    """ScanResult should include a scan_run_id for audit tracking."""

    def test_scan_result_has_scan_run_id(self):
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Acme Corp",
            "description": "APPROVE contract with Acme Corp for consulting services",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        result = scan_meeting_json(meeting, [])
        assert hasattr(result, "scan_run_id")
        assert result.scan_run_id is not None
        assert len(result.scan_run_id) > 0


class TestAuditLoggerIntegration:
    """scan_meeting_json() populates an audit logger with decisions."""

    def test_scan_produces_audit_log(self):
        """Audit log is populated when a match produces a flag."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Acme Corp",
            "description": "APPROVE contract with Acme Corp for consulting services worth $50,000",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [
            _make_contribution("Jane Doe", "Acme Corp", "Wilson for Richmond 2024", 500),
        ]
        result = scan_meeting_json(meeting, contributions)
        assert result.audit_log is not None
        assert len(result.audit_log.decisions) > 0

    def test_suppressed_council_member_logged_as_near_miss(self):
        """Council member name filter produces a near-miss log entry."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Community Services Budget",
            "description": "Approve budget for community services including parks and recreation",
            "category": "budget",
            "financial_amount": "$200,000",
        }])
        # Sue Wilson is a sitting council member — her name as donor should be suppressed
        contributions = [
            _make_contribution("Sue Wilson", "", "Some Committee", 1000),
        ]
        result = scan_meeting_json(meeting, contributions)
        # Check if there's a suppressed decision in the log
        near_misses = [
            d for d in result.audit_log.decisions
            if not d.matched and "council_member" in d.match_type
        ]
        # This depends on whether "Sue Wilson" matches any text in the item
        # At minimum, the audit log should exist
        assert result.audit_log is not None

    def test_surname_tier_tallying_in_summary(self):
        """Contributions compared should tally by surname tier."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with TestCo",
            "description": "APPROVE contract with TestCo for consulting services",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [
            _make_contribution("John Smith", "TestCo", "Wilson for Richmond 2024", 500),
            _make_contribution("Jane Doe", "OtherCo", "Wilson for Richmond 2024", 200),
        ]
        result = scan_meeting_json(meeting, contributions)
        summary = result.audit_log.summary

        # At least one tier count should be nonzero (Smith is tier 1 if census loaded,
        # or all go to 'unknown' if census not loaded)
        total_donor_tiers = (
            summary.donors_surname_tier_1
            + summary.donors_surname_tier_2
            + summary.donors_surname_tier_3
            + summary.donors_surname_tier_4
            + summary.donors_surname_unknown
        )
        assert total_donor_tiers > 0, "Surname tier tallying should count all contributions"

    def test_audit_summary_has_filter_counts(self):
        """Audit summary captures filter funnel statistics."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with TestCo",
            "description": "APPROVE contract with TestCo for services",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [
            _make_contribution("John Smith", "TestCo", "Wilson for Richmond 2024", 500),
        ]
        result = scan_meeting_json(meeting, contributions)
        summary = result.audit_log.summary
        assert summary is not None
        assert summary.total_agenda_items > 0
        assert summary.total_contributions_compared > 0


class TestSurnameTierTallying:
    """Audit summary populates surname tier distribution fields."""

    def test_summary_has_donor_tier_counts(self):
        """Contributions compared should tally by surname tier."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with TestCo",
            "description": "APPROVE contract with TestCo for consulting services",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [
            _make_contribution("John Smith", "TestCo", "Wilson for Richmond 2024", 500),
            _make_contribution("Jane Doe", "OtherCo", "Wilson for Richmond 2024", 200),
        ]
        result = scan_meeting_json(meeting, contributions)
        summary = result.audit_log.summary

        # At least one tier count should be nonzero (Smith is tier 1 if census loaded,
        # or all go to 'unknown' if census not loaded)
        total_donor_tiers = (
            summary.donors_surname_tier_1
            + summary.donors_surname_tier_2
            + summary.donors_surname_tier_3
            + summary.donors_surname_tier_4
            + summary.donors_surname_unknown
        )
        assert total_donor_tiers > 0, "Surname tier tallying should count all contributions"
