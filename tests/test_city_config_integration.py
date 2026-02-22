"""Integration tests for city config pipeline resolution.

Verifies that the city config registry contains all data source
configurations needed by the cloud pipeline and data sync tooling.
"""
import pytest
from city_config import get_city_config, list_configured_cities, CityNotConfiguredError


def test_full_pipeline_config_resolution():
    """Cloud pipeline should resolve all Richmond data sources from config."""
    cfg = get_city_config("0660620")

    # Verify all pipeline-required sources are present
    required = ["escribemeetings", "netfile", "calaccess", "archive_center"]
    for source in required:
        assert source in cfg["data_sources"], f"Missing required source: {source}"

    # Verify URLs are well-formed
    assert cfg["data_sources"]["escribemeetings"]["base_url"].startswith("https://")
    assert cfg["data_sources"]["netfile"]["agency_id"] > 0
    assert cfg["data_sources"]["archive_center"]["minutes_amid"] > 0


def test_config_default_fips_matches_richmond():
    """CLI defaults should still resolve to Richmond."""
    cfg = get_city_config("0660620")
    assert cfg["name"] == "Richmond"
    assert cfg["state"] == "CA"
    assert cfg["fips_code"] == "0660620"


def test_list_cities_includes_richmond():
    """list_configured_cities must include Richmond."""
    cities = list_configured_cities()
    fips_codes = [c["fips_code"] for c in cities]
    assert "0660620" in fips_codes


def test_list_cities_returns_required_fields():
    """Each city entry must have fips_code, name, and state."""
    for city in list_configured_cities():
        assert "fips_code" in city
        assert "name" in city
        assert "state" in city


def test_unknown_city_raises():
    """Unknown FIPS code should raise CityNotConfiguredError."""
    with pytest.raises(CityNotConfiguredError):
        get_city_config("9999999")


def test_socrata_config_present():
    """Richmond should have Socrata data source configured."""
    cfg = get_city_config("0660620")
    assert "socrata" in cfg["data_sources"]
    socrata = cfg["data_sources"]["socrata"]
    assert "domain" in socrata
    assert "datasets" in socrata
    assert isinstance(socrata["datasets"], dict)


def test_nextrequest_config_present():
    """Richmond should have NextRequest data source configured."""
    cfg = get_city_config("0660620")
    assert "nextrequest" in cfg["data_sources"]
    nr = cfg["data_sources"]["nextrequest"]
    assert "base_url" in nr


def test_council_members_present():
    """Richmond config should include council member lists."""
    cfg = get_city_config("0660620")
    assert "council_members" in cfg
    members = cfg["council_members"]
    assert "current" in members
    assert "former" in members
    assert len(members["current"]) >= 7
    assert len(members["former"]) >= 10
