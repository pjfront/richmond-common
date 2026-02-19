"""Tests for conflict scanner matching logic.

Covers: normalize_text, names_match, extract_entity_names,
extract_candidate_from_committee, is_sitting_council_member,
and the filtering logic in scan_meeting_json (government employers,
council member name exclusion, self-donation exclusion, section
header skipping, contribution deduplication, materiality threshold).
"""
from __future__ import annotations

import pytest
from conflict_scanner import (
    normalize_text,
    names_match,
    extract_entity_names,
    extract_candidate_from_committee,
    is_sitting_council_member,
    scan_meeting_json,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_meeting(items, members_present=None):
    """Build minimal meeting JSON."""
    return {
        "meeting_date": "2026-03-04",
        "meeting_type": "regular",
        "city_fips": "0660620",
        "members_present": members_present or [],
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


# ── normalize_text ───────────────────────────────────────────

class TestNormalizeText:
    def test_lowercases(self):
        assert normalize_text("HELLO World") == "hello world"

    def test_strips_punctuation(self):
        # Comma and period replaced with spaces, then whitespace collapsed
        assert normalize_text("National Auto Fleet Group, Inc.") == "national auto fleet group inc"

    def test_collapses_whitespace(self):
        assert normalize_text("  lots   of   spaces  ") == "lots of spaces"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_preserves_hyphens_and_ampersands(self):
        # Hyphens and & are NOT in the strip set
        result = normalize_text("Garcia-Lopez & Associates")
        assert "garcia-lopez" in result
        assert "&" in result


# ── names_match ──────────────────────────────────────────────

class TestNamesMatch:
    def test_exact_match(self):
        matched, mtype = names_match("Cheryl Maier", "Cheryl Maier")
        assert matched is True
        assert mtype == "exact"

    def test_exact_match_case_insensitive(self):
        matched, mtype = names_match("CHERYL MAIER", "cheryl maier")
        assert matched is True
        assert mtype == "exact"

    def test_contains_match_long_strings(self):
        matched, mtype = names_match(
            "National Auto Fleet Group",
            "Purchase vehicles from National Auto Fleet Group for the city fleet"
        )
        assert matched is True
        assert mtype == "contains"

    def test_short_strings_no_substring_match(self):
        """Short names (<10 chars) should not trigger substring matches."""
        matched, _ = names_match("Martinez", "Eduardo Martinez voted aye")
        assert matched is False

    def test_empty_strings_no_match(self):
        matched, mtype = names_match("", "something")
        assert matched is False
        assert mtype == "no_match"

    def test_both_empty_no_match(self):
        matched, mtype = names_match("", "")
        assert matched is False

    def test_stop_words_filtered(self):
        """Common words like 'city', 'services' should not produce matches."""
        matched, _ = names_match(
            "City Services Group",
            "The city services department approved the item"
        )
        # "city" and "services" are stop words, "group" is too —
        # this should NOT match because meaningful words < threshold
        assert matched is False

    def test_word_overlap_sufficient_meaningful_words(self):
        """3+ meaningful words should produce a match against long text."""
        matched, mtype = names_match(
            "Gallagher Benefit Services Inc",
            "Annual benefits contract with Gallagher Benefit Services for employee health plans"
        )
        assert matched is True


# ── extract_entity_names ─────────────────────────────────────

class TestExtractEntityNames:
    def test_contract_with_pattern(self):
        entities = extract_entity_names(
            "Approve contract with National Auto Fleet Group for vehicle purchases"
        )
        assert any("National Auto Fleet" in e for e in entities)

    def test_corporate_suffix_pattern(self):
        entities = extract_entity_names(
            "Professional services agreement with Rincon Consultants Inc."
        )
        assert any("Rincon Consultants" in e for e in entities)

    def test_llc_pattern(self):
        entities = extract_entity_names(
            "Agreement with GreenBuild Solutions LLC for public facility"
        )
        assert any("GreenBuild Solutions" in e for e in entities)

    def test_no_entities_in_plain_text(self):
        entities = extract_entity_names(
            "approve the minutes of the regular council meeting"
        )
        assert entities == []

    def test_filters_out_generic_words(self):
        """Should not extract 'City', 'County', 'State', 'The' as entities."""
        entities = extract_entity_names(
            "contract with City for infrastructure improvements"
        )
        assert all(e not in ("City", "County", "State", "The") for e in entities)


# ── extract_candidate_from_committee ─────────────────────────

class TestExtractCandidate:
    def test_simple_for_pattern(self):
        name = extract_candidate_from_committee(
            "Claudia Jimenez for Richmond City Council 2024"
        )
        assert name == "Claudia Jimenez"

    def test_friends_of_pattern(self):
        name = extract_candidate_from_committee(
            "Friends of Tom Butt for Richmond City Council 2016"
        )
        assert name == "Tom Butt"

    def test_committee_to_elect(self):
        name = extract_candidate_from_committee(
            "Committee to Elect Doria Robinson for City Council"
        )
        assert name == "Doria Robinson"

    def test_pac_returns_none(self):
        name = extract_candidate_from_committee(
            "Independent PAC Local 188 International Association of Firefighters"
        )
        assert name is None

    def test_reelect_pattern(self):
        name = extract_candidate_from_committee(
            "Re-elect Eduardo Martinez for Mayor 2026"
        )
        assert name == "Eduardo Martinez"


# ── is_sitting_council_member ────────────────────────────────

class TestIsSittingCouncilMember:
    def test_exact_match_sitting(self):
        assert is_sitting_council_member("Eduardo Martinez") is True

    def test_exact_match_sitting_case_insensitive(self):
        assert is_sitting_council_member("eduardo martinez") is True

    def test_former_member_not_sitting(self):
        assert is_sitting_council_member("Tom Butt") is False

    def test_random_name_not_sitting(self):
        assert is_sitting_council_member("John Smith") is False

    def test_last_name_first_initial_match(self):
        """'C. Jimenez' should match 'Claudia Jimenez'."""
        assert is_sitting_council_member("C. Jimenez") is True

    def test_partial_name_too_short_no_match(self):
        """Very short names shouldn't match via substring."""
        assert is_sitting_council_member("Ed") is False


# ── scan_meeting_json: filter logic ──────────────────────────

class TestGovernmentEmployerFilter:
    """Donors with government employers should be filtered out."""

    def test_city_of_richmond_employer_filtered(self):
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Pacific Constructors for Road Repair",
            "description": "Road repair contract with Pacific Constructors.",
            "category": "contracts",
            "financial_amount": "$500,000",
        }])
        contributions = [_make_contribution(
            donor_name="Jane Smith",
            donor_employer="City of Richmond",
            committee_name="Claudia Jimenez for Richmond City Council 2024",
            amount=500.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        # Government employer should be filtered
        assert len(result.flags) == 0

    def test_county_employer_filtered(self):
        """When the donor name doesn't match the item, the employer path is
        tried.  A 'Contra Costa County' employer should be filtered."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Pacific Constructors for Infrastructure",
            "description": "Infrastructure work by Pacific Constructors.",
            "category": "contracts",
            "financial_amount": "$200,000",
        }])
        # Donor name does NOT match the agenda item — only employer might
        contributions = [_make_contribution(
            donor_name="John Q Taxpayer",
            donor_employer="Contra Costa County",
            committee_name="Sue Wilson for Richmond 2024",
            amount=1000.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        assert len(result.flags) == 0

    def test_school_district_employer_filtered(self):
        """Unified school district employer should be filtered from matching."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with ABC Education Corp for Tutoring",
            "description": "Education services from ABC Education Corp.",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        # Donor name does NOT match the agenda item — only employer might
        contributions = [_make_contribution(
            donor_name="Maria Johnson",
            donor_employer="West Contra Costa Unified School District",
            committee_name="Eduardo Martinez for Mayor 2026",
            amount=300.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        assert len(result.flags) == 0


class TestGovernmentDonorFilter:
    """Donors whose names look like government entities should be filtered."""

    def test_city_of_richmond_as_donor_filtered(self):
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Budget Allocation for Parks",
            "description": "Annual parks maintenance budget.",
            "category": "budget",
            "financial_amount": "$1,000,000",
        }])
        contributions = [_make_contribution(
            donor_name="City of Richmond Finance Department",
            committee_name="Eduardo Martinez for Mayor 2026",
            amount=5000.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        assert len(result.flags) == 0


class TestCouncilMemberNameExclusion:
    """Sitting council members' names as donors should be excluded."""

    def test_council_member_donor_excluded(self):
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Martinez Construction for Road Work",
            "description": "Road repair by Martinez Construction in the Hilltop district.",
            "category": "contracts",
            "financial_amount": "$300,000",
        }])
        # Eduardo Martinez as a donor — his name matches his own agenda items
        contributions = [_make_contribution(
            donor_name="Eduardo Martinez",
            committee_name="Claudia Jimenez for Richmond City Council 2024",
            amount=500.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        # Eduardo Martinez's donation should be excluded since he's a council member
        eduardo_flags = [f for f in result.flags
                         if "eduardo martinez" in f.description.lower()]
        assert len(eduardo_flags) == 0


class TestSelfDonationExclusion:
    """Candidates donating to their own campaigns should be excluded."""

    def test_self_donation_filtered(self):
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Jimenez Consulting for Planning",
            "description": "Planning services from Jimenez Consulting LLC.",
            "category": "contracts",
            "financial_amount": "$80,000",
        }])
        contributions = [_make_contribution(
            donor_name="Claudia Jimenez",
            committee_name="Claudia Jimenez for Richmond City Council District 6 in 2020",
            amount=10000.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        # Self-donation should be filtered (donor name appears in committee name)
        assert len(result.flags) == 0


class TestMaterialityThreshold:
    """Contributions below $100 total should be suppressed."""

    def test_below_100_not_flagged(self):
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Maier Consulting for Design Work",
            "description": "Professional design services from Cheryl Maier.",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [_make_contribution(
            donor_name="Cheryl Maier",
            committee_name="Sue Wilson for Richmond 2024",
            amount=50.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        assert len(result.flags) == 0

    def test_above_100_flagged(self):
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Maier Consulting for Design Work",
            "description": "Professional design services from Cheryl Maier.",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [_make_contribution(
            donor_name="Cheryl Maier",
            committee_name="Sue Wilson for Richmond 2024",
            amount=150.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        assert len(result.flags) >= 1


class TestContributionDeduplication:
    """Duplicate contribution records should produce only one flag."""

    def test_duplicate_contributions_produce_one_flag(self):
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Maier Consulting",
            "description": "Contract with Cheryl Maier for consulting.",
            "category": "contracts",
            "financial_amount": "$100,000",
        }])
        # Same donation appearing twice (amended filing in CAL-ACCESS)
        contrib = _make_contribution(
            donor_name="Cheryl Maier",
            committee_name="Sue Wilson for Richmond 2024",
            amount=500.00,
            date="2024-06-15",
        )
        result = scan_meeting_json(meeting, [contrib, contrib])
        # Should aggregate into one flag, not two
        flags_for_item = [f for f in result.flags if f.agenda_item_number == "V.1.a"]
        assert len(flags_for_item) == 1


class TestSectionHeaderSkip:
    """Section header items (e.g., 'V.5') should be skipped, not crash."""

    def test_section_header_item_skipped(self):
        """Items like 'V.5' with no description are department groupings.
        They should be cleanly skipped without errors."""
        meeting = _make_meeting([
            {
                "item_number": "V.5",
                "title": "Fire Department",
                "description": "",
                "category": "",
                "financial_amount": None,
            },
            {
                "item_number": "V.5.a",
                "title": "Approve Contract with Rincon Consultants for Fire Station Assessment",
                "description": "Professional services from Rincon Consultants Inc.",
                "category": "contracts",
                "financial_amount": "$150,000",
            },
        ])
        contributions = [_make_contribution(
            donor_name="Rincon Consultants",
            committee_name="Sue Wilson for Richmond 2024",
            amount=500.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        # V.5 should be clean (skipped), V.5.a may be flagged
        assert "V.5" in result.clean_items
        # Should not raise NameError


class TestForm700LandUse:
    """Form 700 property cross-reference for zoning/development items."""

    def test_land_use_item_flags_property_interest(self):
        meeting = _make_meeting([{
            "item_number": "H.1",
            "title": "Rezone parcel 510-123-001 for mixed-use development",
            "description": "Public hearing on rezone application for 1400 Marina Way.",
            "category": "planning",
            "financial_amount": None,
        }])
        form700 = [{
            "council_member": "Soheila Bana",
            "interest_type": "real_property",
            "description": "Residential property at 1500 Marina Way, Richmond CA",
            "location": "Richmond, CA",
            "filing_year": "2025",
            "source_url": "https://fppc.ca.gov",
        }]
        result = scan_meeting_json(meeting, [], form700_interests=form700)
        property_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(property_flags) >= 1
        assert property_flags[0].council_member == "Soheila Bana"

    def test_appointment_item_not_flagged_as_land_use(self):
        """Commission appointments with 'development' in name should not
        trigger Form 700 property cross-reference."""
        meeting = _make_meeting([{
            "item_number": "O.5.b",
            "title": "Appointment to the Economic Development Commission",
            "description": "Council consideration of appointment to the Economic Development Commission.",
            "category": "appointments",
            "financial_amount": None,
        }])
        form700 = [{
            "council_member": "Soheila Bana",
            "interest_type": "real_property",
            "description": "Residential property",
            "location": "Richmond, CA",
            "filing_year": "2025",
            "source_url": "https://fppc.ca.gov",
        }]
        result = scan_meeting_json(meeting, [], form700_interests=form700)
        property_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(property_flags) == 0


class TestConfidenceCalculation:
    """Test that confidence is correctly computed based on match type,
    sitting status, and contribution amount.

    Note: When a donor name like 'Cheryl Maier' appears inside a longer
    item text, names_match returns 'contains' (not 'exact') because the
    normalized donor name is a substring of the normalized item text.
    So sitting + contains = 0.5 base, non-sitting + contains = 0.3 base.
    """

    def test_sitting_contains_high_amount_confidence(self):
        """Sitting member + contains match + $5000 = 0.5 + 0.1 + 0.1 = 0.7."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Maier Consulting",
            "description": "Professional services agreement with Cheryl Maier.",
            "category": "contracts",
            "financial_amount": "$100,000",
        }])
        contributions = [_make_contribution(
            donor_name="Cheryl Maier",
            committee_name="Sue Wilson for Richmond 2024",
            amount=5000.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        assert len(result.flags) >= 1
        flag = result.flags[0]
        # Sitting (Wilson) + contains match = 0.5, + >=1000 = 0.1, + >=5000 = 0.1
        assert flag.confidence == 0.7

    def test_non_sitting_contains_low_amount_confidence(self):
        """Non-sitting candidate + contains match + $200 = 0.3."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Maier Consulting",
            "description": "Services from Cheryl Maier for consulting.",
            "category": "contracts",
            "financial_amount": "$50,000",
        }])
        contributions = [_make_contribution(
            donor_name="Cheryl Maier",
            committee_name="Oscar Garcia for Richmond City Council 2022",
            amount=200.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        assert len(result.flags) >= 1
        flag = result.flags[0]
        # Non-sitting + contains = 0.3, amount < 1000 = no bonus
        assert flag.confidence == 0.3

    def test_amount_bonus_at_1000(self):
        """Contributions >= $1000 get +0.1 confidence bonus."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve Contract with Maier Consulting",
            "description": "Professional services from Cheryl Maier.",
            "category": "contracts",
            "financial_amount": "$100,000",
        }])
        contributions = [_make_contribution(
            donor_name="Cheryl Maier",
            committee_name="Sue Wilson for Richmond 2024",
            amount=1000.00,
        )]
        result = scan_meeting_json(meeting, contributions)
        assert len(result.flags) >= 1
        flag = result.flags[0]
        # Sitting + contains = 0.5, + >=1000 = 0.1
        assert flag.confidence == 0.6
