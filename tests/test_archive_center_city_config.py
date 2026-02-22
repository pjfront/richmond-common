"""Tests for Archive Center discovery city config integration."""
import pytest
from archive_center_discovery import (
    _resolve_archive_config,
    get_download_tier,
    save_to_documents,
)


def test_resolve_defaults_without_fips():
    """Without city_fips, should return module-level Richmond constants."""
    base_url, t1, t2, fips = _resolve_archive_config()
    assert base_url == "https://www.ci.richmond.ca.us"
    assert 67 in t1   # Resolutions
    assert 168 in t2   # Rent Board
    assert fips == "0660620"


def test_resolve_from_registry_with_fips():
    """With city_fips, should load config from city_config registry."""
    base_url, t1, t2, fips = _resolve_archive_config("0660620")
    assert base_url == "https://www.ci.richmond.ca.us"
    assert 67 in t1
    assert fips == "0660620"


def test_resolve_unknown_city_raises():
    """Unknown city should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError
    with pytest.raises(CityNotConfiguredError):
        _resolve_archive_config("9999999")


def test_resolve_city_without_archive_center_raises():
    """City with no archive_center source should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError, CITY_REGISTRY

    fake_fips = "0000004"
    CITY_REGISTRY[fake_fips] = {
        "fips_code": fake_fips,
        "name": "TestCity",
        "state": "XX",
        "data_sources": {},
    }
    try:
        with pytest.raises(CityNotConfiguredError, match="no 'archive_center'"):
            _resolve_archive_config(fake_fips)
    finally:
        del CITY_REGISTRY[fake_fips]


def test_get_download_tier_with_custom_sets():
    """get_download_tier should respect custom tier sets."""
    assert get_download_tier(999, tier_1={999}, tier_2=set()) == 1
    assert get_download_tier(888, tier_1=set(), tier_2={888}) == 2
    assert get_download_tier(777, tier_1=set(), tier_2=set()) == 3


def test_get_download_tier_default_sets():
    """get_download_tier without custom sets uses module defaults."""
    assert get_download_tier(67) == 1   # Richmond default TIER_1
    assert get_download_tier(168) == 2  # Richmond default TIER_2
    assert get_download_tier(1) == 3    # Not in either tier
