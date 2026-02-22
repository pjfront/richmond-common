"""Tests for city configuration registry."""
import pytest
from city_config import (
    get_city_config,
    list_configured_cities,
    get_data_source_config,
    get_council_member_names,
    CityNotConfiguredError,
)


def test_get_richmond_config():
    cfg = get_city_config("0660620")
    assert cfg["fips_code"] == "0660620"
    assert cfg["name"] == "Richmond"
    assert cfg["state"] == "CA"
    assert "escribemeetings" in cfg["data_sources"]


def test_get_richmond_escribemeetings_url():
    cfg = get_city_config("0660620")
    assert cfg["data_sources"]["escribemeetings"]["base_url"] == "https://pub-richmond.escribemeetings.com"


def test_get_richmond_netfile_agency_id():
    cfg = get_city_config("0660620")
    nf = cfg["data_sources"]["netfile"]
    assert nf["agency_id"] == 163
    assert nf["agency_shortcut"] == "RICH"


def test_get_richmond_nextrequest_url():
    cfg = get_city_config("0660620")
    assert "nextrequest" in cfg["data_sources"]
    assert "cityofrichmondca" in cfg["data_sources"]["nextrequest"]["base_url"]


def test_get_richmond_archive_center():
    cfg = get_city_config("0660620")
    ac = cfg["data_sources"]["archive_center"]
    assert ac["base_url"] == "https://www.ci.richmond.ca.us"
    assert 31 in [ac["minutes_amid"]]


def test_get_richmond_calaccess():
    cfg = get_city_config("0660620")
    assert "calaccess" in cfg["data_sources"]


def test_get_richmond_socrata():
    cfg = get_city_config("0660620")
    assert cfg["data_sources"]["socrata"]["domain"] == "www.transparentrichmond.org"


def test_get_richmond_council_members():
    cfg = get_city_config("0660620")
    assert "council_members" in cfg
    current = cfg["council_members"]["current"]
    assert len(current) >= 7
    # Spot check a known member
    names = {m["name"] for m in current}
    assert "Eduardo Martinez" in names


def test_unknown_city_raises():
    with pytest.raises(CityNotConfiguredError):
        get_city_config("9999999")


def test_list_configured_cities():
    cities = list_configured_cities()
    assert len(cities) >= 1
    assert any(c["fips_code"] == "0660620" for c in cities)


def test_config_is_deep_copy():
    """Ensure callers can't mutate the registry."""
    cfg1 = get_city_config("0660620")
    cfg1["name"] = "MUTATED"
    cfg2 = get_city_config("0660620")
    assert cfg2["name"] == "Richmond"


def test_get_data_source_config():
    nf = get_data_source_config("0660620", "netfile")
    assert nf["agency_id"] == 163


def test_get_data_source_config_missing_source():
    with pytest.raises(CityNotConfiguredError, match="no_such_source"):
        get_data_source_config("0660620", "no_such_source")


def test_get_council_member_names():
    current, former = get_council_member_names("0660620")
    assert "Eduardo Martinez" in current
    assert "Tom Butt" in former
    # Current and former should not overlap
    assert len(current & former) == 0
