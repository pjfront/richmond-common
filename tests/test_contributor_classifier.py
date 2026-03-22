"""Tests for contributor type classification."""

import pytest
from contributor_classifier import (
    classify_contributor,
    _classify_by_name,
    CORPORATE,
    UNION,
    INDIVIDUAL,
    PAC_IE,
    OTHER,
)


# ── CAL-ACCESS ENTITY_CD mapping (authoritative path) ──


class TestEntityCdMapping:
    """Authoritative classification from CAL-ACCESS ENTITY_CD field."""

    def test_ind_maps_to_individual(self):
        result, source = classify_contributor("John Smith", entity_code="IND")
        assert result == INDIVIDUAL
        assert source == "entity_cd"

    def test_com_maps_to_pac_ie(self):
        result, source = classify_contributor("Some Committee", entity_code="COM")
        assert result == PAC_IE
        assert source == "entity_cd"

    def test_pty_maps_to_pac_ie(self):
        result, source = classify_contributor("Democratic Party", entity_code="PTY")
        assert result == PAC_IE
        assert source == "entity_cd"

    def test_scc_maps_to_pac_ie(self):
        result, source = classify_contributor("Small Contrib Committee", entity_code="SCC")
        assert result == PAC_IE
        assert source == "entity_cd"

    def test_oth_disambiguates_corporate(self):
        result, source = classify_contributor("Chevron Corp", entity_code="OTH")
        assert result == CORPORATE
        assert source == "entity_cd"

    def test_oth_disambiguates_union(self):
        result, source = classify_contributor("SEIU Local 1021", entity_code="OTH")
        assert result == UNION
        assert source == "entity_cd"

    def test_oth_individual_fallback(self):
        """OTH with a plain name falls back to individual."""
        result, source = classify_contributor("Jane Doe", entity_code="OTH")
        assert result == INDIVIDUAL
        assert source == "entity_cd"

    def test_case_insensitive_entity_code(self):
        result, _ = classify_contributor("John Smith", entity_code="ind")
        assert result == INDIVIDUAL

    def test_union_pac_detected_from_com(self):
        """COM entity with union name → union, not pac_ie."""
        result, source = classify_contributor(
            "SEIU Local 1021 PAC", entity_code="COM"
        )
        assert result == UNION
        assert source == "entity_cd"

    def test_whitespace_entity_code(self):
        result, _ = classify_contributor("John Smith", entity_code="  IND  ")
        assert result == INDIVIDUAL


# ── Name-pattern inference (NetFile path) ──


class TestNamePatternInference:
    """Inferred classification from contributor name patterns."""

    # Corporate patterns
    @pytest.mark.parametrize("name", [
        "ABC Construction Inc",
        "Richmond Properties LLC",
        "Bay Area Consulting Group",
        "Pacific Engineering Co.",
        "Smith & Associates",
        "RIN Investments Corp",
        "Delta Demolition Services",
        "Golden State Paving Ltd",
        "Sunrise Real Estate Holdings",
        "TechVentures Capital",
    ])
    def test_corporate_names(self, name):
        result, source = classify_contributor(name)
        assert result == CORPORATE
        assert source == "inferred"

    # Union patterns
    @pytest.mark.parametrize("name", [
        "SEIU Local 1021",
        "IBEW Local 302",
        "Richmond Police Officers Association",
        "Teamsters Joint Council 7",
        "Building Trades Council",
        "United Teachers of Richmond",
        "AFSCME Council 57",
        "Firefighters Local 188",
        "Plumbers and Pipefitters Union",
        "Laborers International Union",
    ])
    def test_union_names(self, name):
        result, source = classify_contributor(name)
        assert result == UNION
        assert source == "inferred"

    # PAC/IE Committee patterns
    @pytest.mark.parametrize("name", [
        "Doria Robinson for Richmond City Council 2026",
        "Richmond Progressive Alliance PAC",
        "Measure T Ballot Measure Committee",
        "Citizens for Mayor Smith",
        "Independent Expenditure Committee for Schools",
    ])
    def test_pac_ie_names(self, name):
        result, source = classify_contributor(name)
        assert result == PAC_IE
        assert source == "inferred"

    # Individual names (no pattern match → default)
    @pytest.mark.parametrize("name", [
        "John Smith",
        "Maria Garcia",
        "Tom Butt",
        "Najari Smith",
        "Diana Wear",
    ])
    def test_individual_names(self, name):
        result, source = classify_contributor(name)
        assert result == INDIVIDUAL
        assert source == "inferred"

    def test_empty_name_returns_other(self):
        result, _ = classify_contributor("")
        assert result == OTHER

    def test_none_name_returns_other(self):
        result, _ = classify_contributor(None)
        assert result == OTHER


# ── Priority ordering ──


class TestClassificationPriority:
    """Union > PAC > Corporate > Individual priority."""

    def test_union_beats_pac_in_name(self):
        """'SEIU Political Action Committee' → union, not pac_ie."""
        result, _ = classify_contributor("SEIU Political Action Committee")
        assert result == UNION

    def test_union_beats_corporate(self):
        """'Carpenters Union Inc' → union, not corporate."""
        result, _ = classify_contributor("Carpenters Union Inc")
        assert result == UNION

    def test_pac_beats_corporate(self):
        """'Richmond Corp PAC' → pac_ie (PAC takes priority)."""
        result, _ = classify_contributor("Richmond Corp PAC")
        assert result == PAC_IE


# ── Edge cases ──


class TestEdgeCases:
    def test_no_entity_code_uses_name(self):
        result, source = classify_contributor("SEIU Local 1021", entity_code=None)
        assert result == UNION
        assert source == "inferred"

    def test_empty_entity_code_uses_name(self):
        result, source = classify_contributor("Chevron Corp", entity_code="")
        assert result == CORPORATE
        assert source == "inferred"

    def test_unknown_entity_code_falls_through_to_name(self):
        result, source = classify_contributor("SEIU Local 1021", entity_code="XYZ")
        assert result == UNION
        assert source == "inferred"

    def test_source_param_does_not_affect_classification(self):
        """Source is informational, doesn't change logic."""
        r1, _ = classify_contributor("John Smith", source="netfile")
        r2, _ = classify_contributor("John Smith", source="calaccess")
        assert r1 == r2 == INDIVIDUAL


# ── Integration with load_contributions_to_db format ──


class TestRecordFormat:
    """Verify classify_contributor works with real record field names."""

    def test_calaccess_record_flow(self):
        """Simulates how calaccess_client produces entity_code."""
        record = {
            "contributor_name": "Chevron USA Inc",
            "entity_code": "OTH",
            "source": "calaccess",
        }
        result, source = classify_contributor(
            name=record["contributor_name"],
            entity_code=record.get("entity_code"),
            source=record.get("source", ""),
        )
        assert result == CORPORATE
        assert source == "entity_cd"

    def test_netfile_record_flow(self):
        """Simulates NetFile records which have no entity_code."""
        record = {
            "contributor_name": "SEIU Local 1021",
            "entity_code": None,
            "source": "netfile",
        }
        result, source = classify_contributor(
            name=record["contributor_name"],
            entity_code=record.get("entity_code"),
            source=record.get("source", ""),
        )
        assert result == UNION
        assert source == "inferred"
