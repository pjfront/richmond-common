"""Tests that scan_meeting_json assigns v3 publication_tier correctly.

v3 tier assignment is confidence-based:
  Tier 1: >= 0.85 (High-Confidence Pattern)
  Tier 2: >= 0.70 (Medium-Confidence Pattern)
  Tier 3: >= 0.50 (Low-Confidence Pattern)
  Tier 4: < 0.50 (Internal only)

Confidence depends on multi-factor scoring: match_strength, temporal_factor,
financial_factor, anomaly_factor, sitting_multiplier, corroboration_boost.
"""
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


def _make_contribution(donor_name, amount, committee, employer="", date="2026-01-15", source="netfile"):
    """Helper to build a contribution dict. Default date is recent (within 90 days)."""
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


def test_sitting_member_exact_match_high_amount_gets_tier2():
    """Exact donor name match + sitting member + high amount + recent = Tier 2.

    v3 composite: exact match_strength=1.0, temporal=1.0 (recent),
    financial=0.7 ($4900), anomaly=0.5 (stub).
    weighted_avg = 1.0*0.35 + 1.0*0.25 + 0.7*0.20 + 0.5*0.20 = 0.84
    sitting_multiplier=1.0 -> 0.84 (just under tier 1)
    """
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
    assert flag.publication_tier == 2  # 0.84 -> tier 2 (>= 0.70)
    assert flag.scanner_version == 3
    assert flag.confidence >= 0.70


def test_single_signal_max_is_tier2():
    """With anomaly_factor stub at 0.5, a single campaign contribution
    signal maxes out at tier 2. Tier 1 requires either corroboration
    from multiple signals (S9.3) or full anomaly_factor.

    B.52 proportional specificity: "National Auto Fleet Group" has
    {national, auto, fleet, group} — 2 of 4 distinctive (50%).
    Multiplier = 0.5 + 0.5*0.5 = 0.75 → match_strength = 0.85*0.75 = 0.6375
    weighted_avg = 0.6375*0.35 + 1.0*0.25 + 1.0*0.20 + 0.5*0.20 = 0.7731
    """
    meeting = _make_meeting([{
        "item_number": "V.1.a",
        "title": "Approve Contract with National Auto Fleet Group for Vehicle Purchases",
        "description": "Purchase 10 vehicles from National Auto Fleet Group.",
        "category": "contracts",
        "financial_amount": "$450,000",
    }])
    contributions = [
        _make_contribution(
            "National Auto Fleet Group", 5000.00,
            "Claudia Jimenez for Richmond City Council 2024",
        ),
    ]
    result = scan_meeting_json(meeting, contributions)
    assert len(result.flags) >= 1
    flag = result.flags[0]
    # Single signal + anomaly stub can't reach 0.85
    assert flag.publication_tier == 2
    assert 0.70 <= flag.confidence < 0.85


def test_non_sitting_candidate_gets_lower_tier():
    """Donation to a former/failed candidate = non-sitting multiplier.

    Non-sitting multiplier=0.6 pulls confidence below tier 2 threshold.
    """
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
        # Non-sitting: confidence * 0.6, should be tier 3 or 4
        assert flag.publication_tier >= 3


def test_sitting_member_employer_match_low_amount_gets_tier3():
    """Sitting member + employer match (weaker) + low amount = Tier 3.

    employer_match match_strength=0.6, financial=0.3 ($200), temporal=1.0
    weighted_avg = 0.6*0.35 + 1.0*0.25 + 0.3*0.20 + 0.5*0.20 = 0.57
    sitting_multiplier=1.0 -> 0.57 (tier 3: >= 0.50)
    """
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
    assert flag.publication_tier == 3  # employer match + low amount -> tier 3
    assert flag.confidence >= 0.50


def test_old_contribution_date_lowers_confidence():
    """Contribution from 2+ years ago should produce lower confidence.

    temporal_factor=0.2 for >730 days pulls everything down.
    """
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
            date="2023-01-01",  # 3+ years old
        ),
    ]
    result = scan_meeting_json(meeting, contributions)
    assert len(result.flags) >= 1
    flag = result.flags[0]
    # Old date makes temporal=0.2, pulling confidence below tier 2
    assert flag.confidence < 0.70
    assert flag.publication_tier >= 3


def test_confidence_factors_present_on_v3_flags():
    """v3 flags should have confidence_factors breakdown."""
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
    assert flag.confidence_factors is not None
    assert "match_strength" in flag.confidence_factors
    assert "temporal_factor" in flag.confidence_factors
    assert "financial_factor" in flag.confidence_factors
    assert "anomaly_factor" in flag.confidence_factors
