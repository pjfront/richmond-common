"""Tests for scanner bug fixes."""
import pytest
from conflict_scanner import (
    ConflictFlag, scan_meeting_json, get_levine_act_threshold,
    prefilter_contributions, signal_temporal_correlation,
    scan_temporal_correlations, _ScanContext, normalize_text,
)
from scan_audit import ScanAuditLogger


def _make_meeting(items):
    return {
        "meeting_date": "2026-02-17",
        "meeting_type": "regular",
        "city_fips": "0660620",
        "members_present": [],
        "consent_calendar": {"items": items},
        "action_items": [],
        "housing_authority_items": [],
    }


def _make_contribution(**kwargs):
    defaults = {
        "donor_name": "", "donor_employer": "", "council_member": "",
        "committee_name": "", "amount": 0, "date": "2024-01-01",
        "filing_id": "TEST-001", "source": "netfile",
    }
    defaults.update(kwargs)
    return defaults


class TestEmptyRecipientBug:
    """Bug: PAC contributions produce empty council_member field."""

    def test_pac_contribution_shows_pac_name(self):
        """When committee is a PAC (no candidate extractable),
        council_member should show the PAC/committee name."""
        meeting = _make_meeting([{
            "item_number": "V.5.a",
            "title": "Approve Contract with Rincon Consultants for Environmental Review",
            "description": "Professional services agreement with Rincon Consultants Inc.",
            "category": "contracts",
            "financial_amount": "$150,000",
        }])
        contributions = [
            _make_contribution(
                donor_name="Rincon Consultants",
                donor_employer="",
                committee_name="Independent PAC Local 188 International Association of Firefighters",
                amount=2500.00,
            ),
        ]
        result = scan_meeting_json(meeting, contributions)
        # The donor name matches the agenda item — should produce a flag
        flags_for_item = [f for f in result.flags if f.agenda_item_number == "V.5.a"]
        assert len(flags_for_item) >= 1, "Expected a flag for the PAC contribution matching agenda item"
        flag = flags_for_item[0]
        # council_member should NOT be empty
        assert flag.council_member != "", f"council_member was empty, description: {flag.description}"
        assert flag.council_member is not None
        # Should contain the PAC name since no candidate is extractable
        assert "PAC" in flag.council_member or "Local 188" in flag.council_member


class TestNoneEmployerBug:
    """Bug: employer displays as '(None)' or '(n/a)' in output."""

    def test_none_employer_not_displayed(self):
        """Employer field should be empty string when value is None/n/a."""
        meeting = _make_meeting([{
            "item_number": "V.6.a",
            "title": "Approve Contract with Cheryl Maier Consulting",
            "description": "Professional services with Cheryl Maier.",
            "category": "contracts",
            "financial_amount": "$100,000",
        }])
        contributions = [
            _make_contribution(
                donor_name="Cheryl Maier",
                donor_employer="n/a",
                committee_name="Sue Wilson for Richmond 2024",
                amount=500.00,
            ),
        ]
        result = scan_meeting_json(meeting, contributions)
        flags_for_item = [f for f in result.flags if f.agenda_item_number == "V.6.a"]
        if flags_for_item:
            flag = flags_for_item[0]
            # Description should NOT contain "(n/a)" or "(None)"
            assert "(n/a)" not in flag.description
            assert "(None)" not in flag.description
            assert "(none)" not in flag.description
            assert "(N/A)" not in flag.description


class TestSelfContributionFilter:
    """D27: Officials donating to their own campaigns should not be flagged."""

    def test_self_donation_filtered_in_prefilter(self):
        """Direct self-donation (donor name in committee name) is filtered."""
        contributions = [
            _make_contribution(
                donor_name="Eduardo Martinez",
                committee_name="Eduardo Martinez for Mayor 2022",
                amount=500,
            ),
        ]
        filtered = prefilter_contributions(contributions)
        assert len(filtered) == 0, "Self-donation should be filtered"

    def test_cross_cycle_self_donation_filtered(self):
        """Committee-to-committee transfer (same candidate, different cycles)."""
        contributions = [
            _make_contribution(
                donor_name="Claudia Jimenez for District 6 2020",
                committee_name="Claudia Jimenez for District 6 2024",
                amount=1000,
            ),
        ]
        filtered = prefilter_contributions(contributions)
        assert len(filtered) == 0, "Cross-cycle self-donation should be filtered"

    def test_legitimate_donor_not_filtered(self):
        """Unrelated donor to a committee should pass through."""
        contributions = [
            _make_contribution(
                donor_name="Chevron Corporation",
                donor_employer="",
                committee_name="Eduardo Martinez for Mayor 2022",
                amount=5000,
            ),
        ]
        filtered = prefilter_contributions(contributions)
        assert len(filtered) == 1, "Legitimate donor should not be filtered"

    def test_self_donation_in_temporal_scan_filtered(self):
        """Self-donations should also be filtered in retrospective temporal scan."""
        meeting = {
            "meeting_date": "2025-06-15",
            "meeting_type": "regular",
            "city_fips": "0660620",
            "members_present": [],
            "consent_calendar": {"items": []},
            "action_items": [{
                "item_number": "H.1",
                "title": "Approve contract with Acme Corp",
                "description": "Professional services agreement with Acme Corp Inc.",
                "motions": [{
                    "result": "Passed",
                    "votes": [{"council_member": "Eduardo Martinez", "vote": "Aye"}],
                }],
            }],
            "housing_authority_items": [],
        }
        # Martinez donates to their own committee after voting
        contributions = [
            _make_contribution(
                donor_name="Eduardo Martinez",
                committee_name="Eduardo Martinez for Mayor 2026",
                amount=500,
                date="2025-07-01",
            ),
        ]
        flags = scan_temporal_correlations(meeting, contributions)
        self_flags = [f for f in flags if "Eduardo Martinez" in f.description
                      and "Eduardo Martinez for Mayor" in f.description]
        assert len(self_flags) == 0, "Self-donations should be filtered in temporal scan"


class TestLevineActThreshold:
    """D23: Levine Act threshold is date-aware ($250 pre-2025, $500 post-2025)."""

    def test_pre_2025_threshold(self):
        assert get_levine_act_threshold("2024-12-31") == 250

    def test_2025_threshold(self):
        assert get_levine_act_threshold("2025-01-01") == 500

    def test_2026_threshold(self):
        assert get_levine_act_threshold("2026-03-25") == 500

    def test_invalid_date_defaults_to_current(self):
        assert get_levine_act_threshold("not-a-date") == 500

    def test_empty_date_defaults_to_current(self):
        assert get_levine_act_threshold("") == 500
