"""Tests for CAL-ACCESS client city config integration."""
import pytest
from calaccess_client import (
    _resolve_calaccess_config,
    RICHMOND_KEYWORDS,
    CITY_FIPS,
)


def test_resolve_defaults_without_fips():
    """Without city_fips, should return module-level Richmond constants."""
    keywords, fips = _resolve_calaccess_config()
    assert keywords == RICHMOND_KEYWORDS
    assert fips == CITY_FIPS


def test_resolve_from_registry_with_fips():
    """With city_fips, should load config from city_config registry."""
    keywords, fips = _resolve_calaccess_config("0660620")
    assert "richmond" in keywords
    assert fips == "0660620"


def test_resolve_unknown_city_raises():
    """Unknown city should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError
    with pytest.raises(CityNotConfiguredError):
        _resolve_calaccess_config("9999999")


def test_resolve_city_without_calaccess_raises():
    """City with no calaccess source should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError, CITY_REGISTRY

    fake_fips = "0000005"
    CITY_REGISTRY[fake_fips] = {
        "fips_code": fake_fips,
        "name": "TestCity",
        "state": "XX",
        "data_sources": {},
    }
    try:
        with pytest.raises(CityNotConfiguredError, match="no 'calaccess'"):
            _resolve_calaccess_config(fake_fips)
    finally:
        del CITY_REGISTRY[fake_fips]


def test_resolve_returns_search_keywords():
    """Keywords from registry should be a list of strings."""
    keywords, _fips = _resolve_calaccess_config("0660620")
    assert isinstance(keywords, list)
    assert all(isinstance(k, str) for k in keywords)
    assert len(keywords) >= 1
