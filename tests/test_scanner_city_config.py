"""Tests for conflict scanner city config integration."""
import pytest
from conflict_scanner import (
    _get_council_members,
    _DEFAULT_CURRENT_COUNCIL,
    _DEFAULT_FORMER_COUNCIL,
    is_sitting_council_member,
)


def test_get_council_members_defaults_without_fips():
    """Without city_fips, should return hardcoded Richmond defaults."""
    current, former = _get_council_members()
    assert current is _DEFAULT_CURRENT_COUNCIL
    assert former is _DEFAULT_FORMER_COUNCIL


def test_get_council_members_from_registry():
    """With Richmond FIPS, should load from city_config registry."""
    current, former = _get_council_members("0660620")
    assert "Eduardo Martinez" in current
    assert "Tom Butt" in former
    assert len(current) >= 7
    assert len(former) >= 10


def test_get_council_members_unknown_city_falls_back():
    """Unknown city should fall back to defaults, not raise."""
    current, former = _get_council_members("9999999")
    assert current is _DEFAULT_CURRENT_COUNCIL
    assert former is _DEFAULT_FORMER_COUNCIL


def test_is_sitting_council_member_with_custom_set():
    """is_sitting_council_member should use the provided set."""
    custom_members = {"Alice Smith", "Bob Jones"}
    assert is_sitting_council_member("Alice Smith", custom_members) is True
    assert is_sitting_council_member("Charlie Brown", custom_members) is False


def test_is_sitting_council_member_default_set():
    """Without explicit set, should use _DEFAULT_CURRENT_COUNCIL."""
    assert is_sitting_council_member("Eduardo Martinez") is True
    assert is_sitting_council_member("Some Random Person") is False
