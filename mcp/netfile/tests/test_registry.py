"""Tests for the agency registry lookup logic."""
import json
from pathlib import Path

import pytest

from netfile_mcp.registry import (
    load_bundled_agencies,
    resolve_agency,
    resolve_agency_id,
    search_agencies,
)

# Sample agencies for testing (avoid hitting the real bundled file in unit tests)
SAMPLE_AGENCIES = [
    {"id": 116, "shortcut": "SUPER", "name": "( All Agencies )"},
    {"id": 163, "shortcut": "RICH", "name": "City of Richmond"},
    {"id": 175, "shortcut": "SFO", "name": "City and County of San Francisco"},
    {"id": 44, "shortcut": "OAK", "name": "City of Oakland"},
    {"id": 999, "shortcut": "RSIDE", "name": "City of Riverside"},
    {"id": 500, "shortcut": "RCITY", "name": "Richmond County"},
]


class TestSearchAgencies:
    def test_exact_shortcut_match(self):
        results = search_agencies("RICH", SAMPLE_AGENCIES)
        assert len(results) >= 1
        assert results[0]["shortcut"] == "RICH"

    def test_name_substring_match(self):
        results = search_agencies("Oakland", SAMPLE_AGENCIES)
        assert len(results) == 1
        assert results[0]["id"] == 44

    def test_case_insensitive(self):
        results = search_agencies("richmond", SAMPLE_AGENCIES)
        assert len(results) >= 1
        assert any(a["id"] == 163 for a in results)

    def test_multiple_matches(self):
        results = search_agencies("Richmond", SAMPLE_AGENCIES)
        # Should match "City of Richmond" and "Richmond County"
        assert len(results) == 2

    def test_exact_shortcut_comes_first(self):
        results = search_agencies("RICH", SAMPLE_AGENCIES)
        # Exact shortcut match should be first
        assert results[0]["id"] == 163

    def test_no_match(self):
        results = search_agencies("Nonexistent City", SAMPLE_AGENCIES)
        assert len(results) == 0

    def test_empty_query_returns_all(self):
        results = search_agencies("", SAMPLE_AGENCIES)
        # Empty query returns full list unfiltered
        assert len(results) == len(SAMPLE_AGENCIES)

    def test_filters_super_agency(self):
        results = search_agencies("All Agencies", SAMPLE_AGENCIES)
        assert not any(a["shortcut"] == "SUPER" for a in results)


class TestResolveAgency:
    def test_single_match_resolves(self):
        result = resolve_agency("Oakland", SAMPLE_AGENCIES)
        assert result is not None
        assert result["id"] == 44

    def test_multiple_matches_returns_none(self):
        result = resolve_agency("Richmond", SAMPLE_AGENCIES)
        assert result is None  # Ambiguous

    def test_no_match_returns_none(self):
        result = resolve_agency("Nonexistent", SAMPLE_AGENCIES)
        assert result is None


class TestResolveAgencyId:
    def test_direct_agency_id(self):
        aid, name = resolve_agency_id(agency_id=163)
        assert aid == 163

    def test_city_name_unique(self):
        # This uses the bundled registry, so depends on agencies.json
        # Just test error handling for missing inputs
        with pytest.raises(ValueError, match="Provide either"):
            resolve_agency_id()

    def test_no_inputs_raises(self):
        with pytest.raises(ValueError, match="Provide either"):
            resolve_agency_id(city=None, agency_id=None)


class TestBundledAgencies:
    def test_bundled_file_exists(self):
        path = Path(__file__).parent.parent / "netfile_mcp" / "agencies.json"
        assert path.exists(), "agencies.json must be bundled with the package"

    def test_bundled_file_has_agencies(self):
        agencies = load_bundled_agencies()
        assert len(agencies) > 100  # Should have ~220

    def test_richmond_in_bundled(self):
        agencies = load_bundled_agencies()
        richmond = [a for a in agencies if a.get("id") == 163]
        assert len(richmond) == 1
        assert "Richmond" in richmond[0]["name"]
