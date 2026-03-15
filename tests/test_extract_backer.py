"""Tests for extract_backer_from_committee() — extracting corporate/org backers from PAC names."""
import pytest
from conflict_scanner import extract_backer_from_committee


class TestExtractBackerFromCommittee:
    """Test PAC name -> corporate backer extraction."""

    def test_chevron_pac(self):
        result = extract_backer_from_committee("Chevron Richmond PAC")
        assert len(result) == 1
        assert "Chevron" in result[0]

    def test_seiu_pac(self):
        result = extract_backer_from_committee("SEIU Local 1021 PAC")
        assert len(result) == 1
        assert "SEIU" in result[0]
        assert "1021" in result[0]

    def test_police_officers_association(self):
        result = extract_backer_from_committee("Richmond Police Officers Association PAC")
        assert len(result) == 1
        assert "Police Officers Association" in result[0]

    def test_pac_for_good_government(self):
        result = extract_backer_from_committee("SEIU Local 1021 PAC for Good Government")
        assert len(result) == 1
        assert "SEIU" in result[0]

    def test_independent_expenditure_committee(self):
        result = extract_backer_from_committee("Chevron Independent Expenditure Committee")
        assert len(result) == 1
        assert "Chevron" in result[0]

    def test_generic_pac_returns_empty(self):
        """Generic PAC names with no identifiable backer return empty."""
        result = extract_backer_from_committee("Independent PAC for Good Government")
        assert result == []

    def test_empty_string(self):
        assert extract_backer_from_committee("") == []

    def test_whitespace_only(self):
        assert extract_backer_from_committee("   ") == []

    def test_just_pac(self):
        assert extract_backer_from_committee("PAC") == []

    def test_firefighters_union(self):
        result = extract_backer_from_committee(
            "Independent PAC Local 188 International Association of Firefighters"
        )
        assert len(result) == 1
        # Should have the firefighters org name
        assert "Firefighters" in result[0]

    def test_preserves_local_number(self):
        """Union local numbers are part of the org identity."""
        result = extract_backer_from_committee("SEIU Local 1021 PAC")
        assert len(result) == 1
        assert "1021" in result[0]

    def test_strips_geographic_qualifiers(self):
        result = extract_backer_from_committee("Chevron Richmond California PAC")
        assert len(result) == 1
        # Should strip Richmond and California
        assert "Richmond" not in result[0]
        assert "California" not in result[0]
        assert "Chevron" in result[0]

    def test_political_action_committee_suffix(self):
        result = extract_backer_from_committee(
            "Chevron Political Action Committee"
        )
        assert len(result) == 1
        assert "Chevron" in result[0]

    def test_committee_suffix_alone(self):
        result = extract_backer_from_committee("Chevron Committee")
        assert len(result) == 1
        assert "Chevron" in result[0]
