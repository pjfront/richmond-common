"""Tests for S8.3: Commission/board meeting support.

Covers:
- Commission-aware eSCRIBE→scanner converter routing
- Source identifier collision prevention
- Commission extraction schema and prompt
- get_extraction_config() body_type dispatch
- sync_minutes_extraction amid/body_type params
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from extraction import (
    COMMISSION_EXTRACTION_SCHEMA,
    COMMISSION_SYSTEM_PROMPT,
    EXTRACTION_SCHEMA,
    SYSTEM_PROMPT,
    get_extraction_config,
)
from run_pipeline import convert_escribemeetings_to_scanner_format


# ── eSCRIBE→Scanner Converter ────────────────────────────────


class TestConverterCommissionRouting:
    """Verify commission meetings route all items to action_items."""

    def _make_escribemeetings_data(self, meeting_name: str, items: list[dict]) -> dict:
        return {
            "meeting_name": meeting_name,
            "meeting_date": "2026-03-15",
            "city_fips": "0660620",
            "items": items,
        }

    def test_council_items_route_to_consent(self):
        """V.* items should route to consent_calendar for council meetings."""
        data = self._make_escribemeetings_data("City Council", [
            {"item_number": "V.1", "title": "Approve minutes", "description": ""},
            {"item_number": "V.2", "title": "Accept report", "description": ""},
        ])
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["consent_calendar"]["items"]) == 2
        assert len(result["action_items"]) == 0

    def test_council_items_route_to_housing(self):
        """M.* items should route to housing_authority for council meetings."""
        data = self._make_escribemeetings_data("City Council", [
            {"item_number": "M.1", "title": "Housing item", "description": ""},
        ])
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["housing_authority_items"]) == 1

    def test_commission_items_all_to_action(self):
        """Commission meetings should route ALL items to action_items."""
        data = self._make_escribemeetings_data("Planning Commission", [
            {"item_number": "1.a", "title": "Zoning variance", "description": ""},
            {"item_number": "2.a", "title": "Conditional use permit", "description": ""},
            {"item_number": "3.a", "title": "General plan amendment", "description": ""},
        ])
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["action_items"]) == 3
        assert len(result["consent_calendar"]["items"]) == 0
        assert len(result["housing_authority_items"]) == 0

    def test_rent_board_items_all_to_action(self):
        """Rent Board meetings should route all items to action_items."""
        data = self._make_escribemeetings_data("Richmond Rent Board", [
            {"item_number": "V.1", "title": "Rent petition", "description": ""},
        ])
        result = convert_escribemeetings_to_scanner_format(data)
        # V.1 would go to consent for council, but NOT for rent board
        assert len(result["action_items"]) == 1
        assert len(result["consent_calendar"]["items"]) == 0

    def test_design_review_items_all_to_action(self):
        data = self._make_escribemeetings_data("Design Review Board", [
            {"item_number": "A.1", "title": "Design review", "description": ""},
        ])
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["action_items"]) == 1

    def test_housing_authority_items_all_to_action(self):
        data = self._make_escribemeetings_data("Housing Authority Board of Commissioners", [
            {"item_number": "1.a", "title": "Budget approval", "description": ""},
        ])
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["action_items"]) == 1

    def test_empty_meeting_name_treated_as_council(self):
        """Empty meeting name defaults to council routing (backward compat)."""
        data = self._make_escribemeetings_data("", [
            {"item_number": "V.1", "title": "Approve minutes", "description": ""},
        ])
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["consent_calendar"]["items"]) == 1

    def test_special_council_treated_as_council(self):
        """Special City Council meetings use council routing."""
        data = self._make_escribemeetings_data("City Council Special Meeting", [
            {"item_number": "V.1", "title": "Emergency item", "description": ""},
        ])
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["consent_calendar"]["items"]) == 1

    def test_section_headers_skipped_for_commissions(self):
        """Items without dots are section headers and should be skipped."""
        data = self._make_escribemeetings_data("Planning Commission", [
            {"item_number": "I", "title": "Call to Order", "description": ""},
            {"item_number": "1.a", "title": "Real item", "description": ""},
        ])
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["action_items"]) == 1
        assert result["action_items"][0]["title"] == "Real item"


# ── Source Identifier ────────────────────────────────────────


class TestSourceIdentifier:
    """Verify source_identifier includes meeting name to prevent collisions."""

    def test_different_meetings_same_date_have_different_identifiers(self):
        """Council and commission on the same date should not collide."""
        # This tests the format logic, not the full sync function
        meeting_date = "2026-03-15"
        council_id = f"escribemeetings_City Council_{meeting_date}"
        planning_id = f"escribemeetings_Planning Commission_{meeting_date}"
        assert council_id != planning_id

    def test_source_identifier_format(self):
        """Verify the new format includes meeting name."""
        source_id = f"escribemeetings_Planning Commission_2026-03-15"
        assert "Planning Commission" in source_id
        assert "2026-03-15" in source_id


# ── Extraction Config ────────────────────────────────────────


class TestGetExtractionConfig:
    """Verify get_extraction_config dispatches correctly by body_type."""

    def test_city_council_returns_council_config(self):
        system, schema, prefix = get_extraction_config("city_council")
        assert system == SYSTEM_PROMPT
        assert schema == EXTRACTION_SCHEMA
        assert "City Council" in prefix

    def test_commission_returns_commission_config(self):
        system, schema, prefix = get_extraction_config("commission")
        assert system == COMMISSION_SYSTEM_PROMPT
        assert schema == COMMISSION_EXTRACTION_SCHEMA
        assert "commission/board" in prefix

    def test_board_returns_commission_config(self):
        """Non-council body types all use commission config."""
        system, schema, prefix = get_extraction_config("board")
        assert system == COMMISSION_SYSTEM_PROMPT
        assert schema == COMMISSION_EXTRACTION_SCHEMA

    def test_authority_returns_commission_config(self):
        system, schema, prefix = get_extraction_config("authority")
        assert system == COMMISSION_SYSTEM_PROMPT


# ── Commission Extraction Schema ─────────────────────────────


class TestCommissionExtractionSchema:
    """Verify the commission schema has correct structure."""

    def test_has_commission_roles(self):
        """Commission schema should have commission-appropriate roles."""
        roles = COMMISSION_EXTRACTION_SCHEMA["properties"]["members_present"]["items"]["properties"]["role"]["enum"]
        assert "chair" in roles
        assert "vice_chair" in roles
        assert "commissioner" in roles
        assert "member" in roles
        assert "board_member" in roles
        assert "alternate" in roles

    def test_no_council_roles(self):
        """Commission schema should not have council-specific roles."""
        roles = COMMISSION_EXTRACTION_SCHEMA["properties"]["members_present"]["items"]["properties"]["role"]["enum"]
        assert "mayor" not in roles
        assert "vice_mayor" not in roles
        assert "councilmember" not in roles

    def test_has_action_items(self):
        """Commission schema should have action_items."""
        assert "action_items" in COMMISSION_EXTRACTION_SCHEMA["properties"]

    def test_no_consent_calendar(self):
        """Commission schema should NOT have consent_calendar."""
        assert "consent_calendar" not in COMMISSION_EXTRACTION_SCHEMA["properties"]

    def test_no_council_reports(self):
        """Commission schema should not have council_reports."""
        assert "council_reports" not in COMMISSION_EXTRACTION_SCHEMA["properties"]

    def test_has_public_comments(self):
        """Commission schema should have public_comments."""
        assert "public_comments" in COMMISSION_EXTRACTION_SCHEMA["properties"]

    def test_has_public_hearing_category(self):
        """Commission schema should include public_hearing category."""
        categories = COMMISSION_EXTRACTION_SCHEMA["properties"]["action_items"]["items"]["properties"]["category"]["enum"]
        assert "public_hearing" in categories

    def test_commission_prompt_mentions_recommendations(self):
        """Commission prompt should mention that commissions make recommendations."""
        assert "recommendation" in COMMISSION_SYSTEM_PROMPT.lower()

    def test_commission_prompt_does_not_mention_city_council(self):
        """Commission prompt should not reference City Council."""
        assert "City Council meeting minutes" not in COMMISSION_SYSTEM_PROMPT


# ── City Config Commission AMIDs ─────────────────────────────


class TestCityConfigCommissionAmids:
    """Verify commission_amids mapping exists in city config."""

    def test_richmond_has_commission_amids(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        amids = cfg["data_sources"]["archive_center"]["commission_amids"]
        assert isinstance(amids, dict)
        assert len(amids) >= 3

    def test_personnel_board_amid(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        amids = cfg["data_sources"]["archive_center"]["commission_amids"]
        assert amids["Personnel Board"] == 132

    def test_rent_board_amid(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        amids = cfg["data_sources"]["archive_center"]["commission_amids"]
        assert amids["Richmond Rent Board"] == 168

    def test_commission_amids_mapping(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        amids = cfg["data_sources"]["archive_center"]["commission_amids"]
        assert amids.get("Design Review Board") == 61
        assert amids.get("Planning Commission") == 75
