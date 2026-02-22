"""Tests for NetFile client city config integration."""
import pytest
from netfile_client import (
    _resolve_netfile_config,
    normalize_transaction,
    extract_filers,
)


def test_resolve_defaults_without_fips():
    """Without city_fips, should return module-level Richmond constants."""
    api_base, agency_id, shortcut, fips = _resolve_netfile_config()
    assert api_base == "https://netfile.com/Connect2/api"
    assert agency_id == 163
    assert shortcut == "RICH"
    assert fips == "0660620"


def test_resolve_from_registry_with_fips():
    """With city_fips, should load config from city_config registry."""
    api_base, agency_id, shortcut, fips = _resolve_netfile_config("0660620")
    assert api_base == "https://netfile.com/Connect2/api"
    assert agency_id == 163
    assert shortcut == "RICH"
    assert fips == "0660620"


def test_resolve_unknown_city_raises():
    """Unknown city should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError
    with pytest.raises(CityNotConfiguredError):
        _resolve_netfile_config("9999999")


def test_resolve_city_without_netfile_raises():
    """City with no NetFile source should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError, CITY_REGISTRY

    fake_fips = "0000002"
    CITY_REGISTRY[fake_fips] = {
        "fips_code": fake_fips,
        "name": "TestCity",
        "state": "XX",
        "data_sources": {},
    }
    try:
        with pytest.raises(CityNotConfiguredError, match="no 'netfile'"):
            _resolve_netfile_config(fake_fips)
    finally:
        del CITY_REGISTRY[fake_fips]


def test_normalize_transaction_default_fips():
    """normalize_transaction without city_fips uses Richmond default."""
    tx = {
        "name": "Jane Donor",
        "employer": "Acme Inc",
        "amount": 500.0,
        "date": "2025-06-15T00:00:00",
        "filerName": "Friends of Richmond",
        "occupation": "Engineer",
        "city": "Richmond",
        "state": "CA",
        "zip": "94801",
        "transactionType": 0,
        "filerFppcId": "123456",
        "filerLocalId": "LOC-1",
        "filingId": "FIL-1",
        "id": "guid-1",
    }
    result = normalize_transaction(tx)
    assert result["city_fips"] == "0660620"
    assert result["contributor_name"] == "Jane Donor"
    assert result["source"] == "netfile"


def test_normalize_transaction_with_city_fips():
    """normalize_transaction with explicit city_fips should use it."""
    tx = {
        "name": "Bob Smith",
        "amount": 100.0,
        "date": "2025-01-01T00:00:00",
        "filerName": "Some Committee",
    }
    result = normalize_transaction(tx, city_fips="0600001")
    assert result["city_fips"] == "0600001"


def test_extract_filers_default_fips():
    """extract_filers without city_fips uses Richmond default."""
    transactions = [
        {
            "filer_fppc_id": "FP-1",
            "filer_local_id": "LOC-1",
            "committee": "Test Committee",
        }
    ]
    filers = extract_filers(transactions)
    assert len(filers) == 1
    assert filers[0]["city_fips"] == "0660620"


def test_extract_filers_with_city_fips():
    """extract_filers with explicit city_fips should use it."""
    transactions = [
        {
            "filer_fppc_id": "FP-2",
            "filer_local_id": "LOC-2",
            "committee": "Another Committee",
        }
    ]
    filers = extract_filers(transactions, city_fips="0600001")
    assert len(filers) == 1
    assert filers[0]["city_fips"] == "0600001"
