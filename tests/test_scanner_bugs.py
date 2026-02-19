"""Tests for scanner bug fixes."""
import pytest
from conflict_scanner import ConflictFlag, scan_meeting_json


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
