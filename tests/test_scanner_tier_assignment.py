"""Tests that scan_meeting_json assigns publication_tier correctly."""
import pytest
from conflict_scanner import scan_meeting_json


def _make_meeting(items):
    """Helper to build minimal meeting JSON."""
    return {
        "meeting_date": "2026-02-17",
        "meeting_type": "regular",
        "city_fips": "0660620",
        "members_present": [],
        "consent_calendar": {"items": items},
        "action_items": [],
        "housing_authority_items": [],
    }


def _make_contribution(donor_name, amount, committee, employer="", date="2024-01-01", source="netfile"):
    """Helper to build a contribution dict."""
    return {
        "donor_name": donor_name,
        "donor_employer": employer,
        "council_member": "",
        "committee_name": committee,
        "amount": amount,
        "date": date,
        "filing_id": "TEST-001",
        "source": source,
    }


def test_sitting_member_exact_match_gets_tier1():
    """Exact donor name match + sitting member + high confidence = Tier 1."""
    meeting = _make_meeting([{
        "item_number": "V.1.a",
        "title": "Approve Contract with National Auto Fleet Group for Vehicle Purchases",
        "description": "Purchase 10 vehicles from National Auto Fleet Group.",
        "category": "contracts",
        "financial_amount": "$450,000",
    }])
    contributions = [
        _make_contribution(
            "National Auto Fleet Group", 4900.00,
            "Claudia Jimenez for Richmond City Council 2024",
        ),
    ]
    result = scan_meeting_json(meeting, contributions)
    assert len(result.flags) >= 1
    flag = result.flags[0]
    assert flag.publication_tier == 1  # sitting member, exact, high amount


def test_non_sitting_candidate_gets_tier3():
    """Donation to a former/failed candidate = Tier 3."""
    meeting = _make_meeting([{
        "item_number": "V.6.a",
        "title": "Approve Contract with Maier Consulting for Library Design",
        "description": "Professional services agreement with Cheryl Maier.",
        "category": "contracts",
        "financial_amount": "$100,000",
    }])
    contributions = [
        _make_contribution(
            "Cheryl Maier", 100.00,
            "Oscar Garcia for Richmond City Council 2022",
        ),
    ]
    result = scan_meeting_json(meeting, contributions)
    assert len(result.flags) >= 1
    for flag in result.flags:
        assert flag.publication_tier == 3  # non-sitting candidate


def test_sitting_member_employer_match_low_amount_gets_tier2():
    """Sitting member + employer match + low amount = Tier 2."""
    meeting = _make_meeting([{
        "item_number": "V.3.a",
        "title": "Approve Contract with Gallagher Benefit Services for Employee Benefits",
        "description": "Annual benefits administration contract with Gallagher Benefit Services.",
        "category": "contracts",
        "financial_amount": "$200,000",
    }])
    contributions = [
        _make_contribution(
            "Sarah Whitfield", 200.00,
            "Sue Wilson for Richmond 2024",
            employer="Gallagher Benefit Services",
        ),
    ]
    result = scan_meeting_json(meeting, contributions)
    assert len(result.flags) >= 1
    flag = result.flags[0]
    assert flag.publication_tier == 2  # sitting member, but employer match + low amount
