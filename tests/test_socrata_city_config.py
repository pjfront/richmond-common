"""Tests for Socrata client city config integration."""
import pytest
from socrata_client import (
    _resolve_socrata_config,
    SOCRATA_DOMAIN,
    DATASETS,
    CITY_FIPS,
)


def test_resolve_defaults_without_fips():
    """Without city_fips, should return module-level Richmond constants."""
    domain, datasets, fips = _resolve_socrata_config()
    assert domain == SOCRATA_DOMAIN
    assert datasets is DATASETS
    assert fips == CITY_FIPS


def test_resolve_from_registry_with_fips():
    """With city_fips, should load config from city_config registry."""
    domain, datasets, fips = _resolve_socrata_config("0660620")
    assert domain == "www.transparentrichmond.org"
    assert "expenditures" in datasets
    assert fips == "0660620"


def test_resolve_unknown_city_raises():
    """Unknown city should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError
    with pytest.raises(CityNotConfiguredError):
        _resolve_socrata_config("9999999")


def test_resolve_city_without_socrata_raises():
    """City with no socrata source should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError, CITY_REGISTRY

    fake_fips = "0000006"
    CITY_REGISTRY[fake_fips] = {
        "fips_code": fake_fips,
        "name": "TestCity",
        "state": "XX",
        "data_sources": {},
    }
    try:
        with pytest.raises(CityNotConfiguredError, match="no 'socrata'"):
            _resolve_socrata_config(fake_fips)
    finally:
        del CITY_REGISTRY[fake_fips]


def test_resolve_returns_datasets_dict():
    """Datasets from registry should be a dict mapping friendly names to IDs."""
    _domain, datasets, _fips = _resolve_socrata_config("0660620")
    assert isinstance(datasets, dict)
    assert len(datasets) >= 1
    # All values should be Socrata dataset IDs (xxxx-xxxx format)
    for key, val in datasets.items():
        assert isinstance(key, str)
        assert isinstance(val, str)
