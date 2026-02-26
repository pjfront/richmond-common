"""Tests for extraction schema category consistency."""
import json
from src.extraction import EXTRACTION_SCHEMA


def _get_consent_category_schema():
    """Navigate to consent_calendar > items > items > properties > category."""
    return (
        EXTRACTION_SCHEMA["properties"]["consent_calendar"]
        ["properties"]["items"]["items"]["properties"]["category"]
    )


def _get_action_category_schema():
    """Navigate to action_items > items > properties > category."""
    return (
        EXTRACTION_SCHEMA["properties"]["action_items"]
        ["items"]["properties"]["category"]
    )


def test_consent_calendar_has_appointments_category():
    schema = _get_consent_category_schema()
    assert "appointments" in schema["enum"]


def test_action_items_has_enum_constraint():
    """Action items category should have an enum constraint, not just type: string."""
    schema = _get_action_category_schema()
    assert "enum" in schema, "action_items category should have an enum constraint"


def test_action_items_has_appointments_category():
    schema = _get_action_category_schema()
    assert "appointments" in schema["enum"]


def test_both_schemas_have_same_categories():
    """Both consent_calendar and action_items should use identical category enums."""
    consent = set(_get_consent_category_schema()["enum"])
    action = set(_get_action_category_schema()["enum"])
    assert consent == action


def test_category_enum_has_14_values():
    """The extraction schema should list all 14 categories."""
    schema = _get_consent_category_schema()
    assert len(schema["enum"]) == 14
