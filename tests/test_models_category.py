"""Tests for AgendaCategory enum completeness."""
from src.models import AgendaCategory


def test_appointments_category_exists():
    """The appointments category must exist in the enum."""
    assert AgendaCategory.APPOINTMENTS == "appointments"


def test_all_expected_categories_present():
    """All 14 categories must be present."""
    expected = {
        "zoning", "budget", "housing", "public_safety",
        "environment", "infrastructure", "personnel",
        "contracts", "governance", "proclamation",
        "litigation", "other", "appointments", "procedural",
    }
    actual = {c.value for c in AgendaCategory}
    assert actual == expected
