"""Tests for NextRequest scraper city config integration."""
import pytest
from nextrequest_scraper import (
    _resolve_nextrequest_config,
)


def test_resolve_defaults_without_fips():
    """Without city_fips, should return module-level Richmond constants."""
    base_url, fips = _resolve_nextrequest_config()
    assert base_url == "https://cityofrichmondca.nextrequest.com"
    assert fips == "0660620"


def test_resolve_from_registry_with_fips():
    """With city_fips, should load config from city_config registry."""
    base_url, fips = _resolve_nextrequest_config("0660620")
    assert base_url == "https://cityofrichmondca.nextrequest.com"
    assert fips == "0660620"


def test_resolve_unknown_city_raises():
    """Unknown city should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError
    with pytest.raises(CityNotConfiguredError):
        _resolve_nextrequest_config("9999999")


def test_resolve_city_without_nextrequest_raises():
    """City with no NextRequest source should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError, CITY_REGISTRY

    fake_fips = "0000003"
    CITY_REGISTRY[fake_fips] = {
        "fips_code": fake_fips,
        "name": "TestCity",
        "state": "XX",
        "data_sources": {},
    }
    try:
        with pytest.raises(CityNotConfiguredError, match="no 'nextrequest'"):
            _resolve_nextrequest_config(fake_fips)
    finally:
        del CITY_REGISTRY[fake_fips]
