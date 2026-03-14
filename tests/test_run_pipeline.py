"""Tests for the end-to-end pipeline automation command."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from run_pipeline import (
    convert_escribemeetings_to_scanner_format,
    extract_financial_amount,
    categorize_item,
    run_pipeline,
)


# ── eSCRIBE → Scanner Format Conversion ─────────────────────


class TestConvertEscribemeetingsToScannerFormat:
    """Convert eSCRIBE meeting_data.json to conflict scanner schema."""

    def test_basic_structure(self):
        """Converted data has required top-level keys."""
        escribemeetings_data = {
            "meeting_date": "2026-02-17",
            "meeting_name": "City Council",
            "city_fips": "0660620",
            "items": [],
        }
        result = convert_escribemeetings_to_scanner_format(escribemeetings_data)
        assert result["meeting_date"] == "2026-02-17"
        assert result["meeting_type"] == "regular"
        assert result["city_fips"] == "0660620"
        assert "consent_calendar" in result
        assert "action_items" in result
        assert "housing_authority_items" in result

    def test_consent_item_routed_to_consent_calendar(self):
        """Items with V.x numbering go to consent calendar."""
        data = {
            "meeting_date": "2026-02-17",
            "meeting_name": "City Council",
            "city_fips": "0660620",
            "items": [
                {
                    "item_number": "V.1.a",
                    "title": "Approve Contract with Acme Corp",
                    "description": "APPROVE a contract with Acme Corp for $50,000",
                    "attachments": [],
                }
            ],
        }
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["consent_calendar"]["items"]) == 1
        item = result["consent_calendar"]["items"][0]
        assert item["item_number"] == "V.1.a"
        assert item["title"] == "Approve Contract with Acme Corp"
        assert "$50,000" in item["description"]

    def test_action_item_routed_correctly(self):
        """Items outside consent calendar (VI, VII, etc.) go to action_items."""
        data = {
            "meeting_date": "2026-02-17",
            "meeting_name": "City Council",
            "city_fips": "0660620",
            "items": [
                {
                    "item_number": "VI.1",
                    "title": "Public Hearing on Rezoning",
                    "description": "Conduct public hearing on proposed rezoning",
                    "attachments": [],
                }
            ],
        }
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["action_items"]) == 1

    def test_housing_authority_item_routed(self):
        """Items with M.x numbering go to housing_authority_items."""
        data = {
            "meeting_date": "2026-02-17",
            "meeting_name": "City Council",
            "city_fips": "0660620",
            "items": [
                {
                    "item_number": "M.1",
                    "title": "Housing Authority Contract Amendment",
                    "description": "Approve amendment for housing services",
                    "attachments": [],
                }
            ],
        }
        result = convert_escribemeetings_to_scanner_format(data)
        assert len(result["housing_authority_items"]) == 1

    def test_special_meeting_type_detected(self):
        """Meeting name containing 'special' sets meeting_type."""
        data = {
            "meeting_date": "2026-02-17",
            "meeting_name": "Special City Council",
            "city_fips": "0660620",
            "items": [],
        }
        result = convert_escribemeetings_to_scanner_format(data)
        assert result["meeting_type"] == "special"

    def test_section_headers_skipped(self):
        """Section headers (V, M, C) without dots are skipped.

        B.49: Bare-letter items like "V" (CONSENT CALENDAR) and "C"
        (CLOSED SESSION) are parent containers, not actionable items.
        They caused uninformative scanner flags when included.
        """
        data = {
            "meeting_date": "2026-02-17",
            "meeting_name": "City Council",
            "city_fips": "0660620",
            "items": [
                {
                    "item_number": "V",
                    "title": "CONSENT CALENDAR",
                    "description": "",
                    "attachments": [],
                },
                {
                    "item_number": "V.1.a",
                    "title": "Contract with Acme",
                    "description": "Approve contract",
                    "attachments": [],
                },
                {
                    "item_number": "C",
                    "title": "CLOSED SESSION",
                    "description": "",
                    "attachments": [],
                },
            ],
        }
        result = convert_escribemeetings_to_scanner_format(data)
        consent_nums = [i["item_number"] for i in result["consent_calendar"]["items"]]
        action_nums = [i["item_number"] for i in result["action_items"]]
        all_nums = consent_nums + action_nums
        # Headers should NOT appear anywhere
        assert "V" not in all_nums
        assert "C" not in all_nums
        # Sub-items should still be present
        assert "V.1.a" in consent_nums

    def test_procedural_bare_letter_items_skipped(self):
        """Procedural items (A, B, I, II, III) are also skipped as bare letters."""
        data = {
            "meeting_date": "2026-02-17",
            "meeting_name": "City Council",
            "city_fips": "0660620",
            "items": [
                {"item_number": "A", "title": "CALL TO ORDER", "description": "", "attachments": []},
                {"item_number": "B", "title": "ROLL CALL", "description": "", "attachments": []},
                {"item_number": "I", "title": "OPEN SESSION", "description": "", "attachments": []},
                {"item_number": "A.1", "title": "Pledge of Allegiance", "description": "", "attachments": []},
            ],
        }
        result = convert_escribemeetings_to_scanner_format(data)
        all_nums = (
            [i["item_number"] for i in result["consent_calendar"]["items"]]
            + [i["item_number"] for i in result["action_items"]]
            + [i["item_number"] for i in result["housing_authority_items"]]
        )
        assert "A" not in all_nums
        assert "B" not in all_nums
        assert "I" not in all_nums
        # Sub-item A.1 should be preserved
        assert "A.1" in all_nums

    def test_empty_items_produce_empty_output(self):
        """No items = empty lists everywhere."""
        data = {
            "meeting_date": "2026-02-17",
            "meeting_name": "City Council",
            "city_fips": "0660620",
            "items": [],
        }
        result = convert_escribemeetings_to_scanner_format(data)
        assert result["consent_calendar"]["items"] == []
        assert result["action_items"] == []
        assert result["housing_authority_items"] == []


class TestExtractFinancialAmount:
    """Parse dollar amounts from description text."""

    def test_simple_dollar_amount(self):
        assert extract_financial_amount("Approve $50,000 for repairs") == "$50,000"

    def test_million_dollar_amount(self):
        assert extract_financial_amount("Budget of $1.2 million") == "$1,200,000"

    def test_not_to_exceed(self):
        assert extract_financial_amount(
            "not to exceed $175,000 with term"
        ) == "$175,000"

    def test_no_amount(self):
        assert extract_financial_amount("Approve the minutes") is None

    def test_multiple_amounts_returns_largest(self):
        result = extract_financial_amount(
            "increase by $300,000 for total not to exceed $1,159,990"
        )
        assert result == "$1,159,990"


class TestCategorizeItem:
    """Assign category based on title/description keywords."""

    def test_housing_keyword(self):
        assert categorize_item("Affordable Housing Project", "housing development") == "housing"

    def test_contract_keyword(self):
        assert categorize_item("Contract with Vendor", "approve contract") == "contracts"

    def test_zoning_keyword(self):
        assert categorize_item("Rezoning Request", "zoning amendment") == "zoning"

    def test_budget_keyword(self):
        assert categorize_item("Budget Amendment", "appropriation increase") == "budget"

    def test_personnel_keyword(self):
        assert categorize_item("Appointment of Commissioner", "personnel action") == "personnel"

    def test_default_to_other(self):
        assert categorize_item("Regular Business", "some normal item") == "other"


# ── Full Pipeline Integration ────────────────────────────────


class TestRunPipeline:
    """Test the full pipeline orchestration (mocked external calls)."""

    @patch("run_pipeline.create_session")
    @patch("run_pipeline.discover_meetings")
    @patch("run_pipeline.find_meeting_by_date")
    @patch("run_pipeline.scrape_meeting")
    def test_pipeline_returns_comment_string(
        self, mock_scrape, mock_find, mock_discover, mock_session
    ):
        """Pipeline produces a non-empty comment string."""
        # Minimal eSCRIBE mock
        mock_session.return_value = MagicMock()
        mock_discover.return_value = [{"ID": "abc123"}]
        mock_find.return_value = {"ID": "abc123", "StartDate": "2026/02/17"}
        mock_scrape.return_value = {
            "city_fips": "0660620",
            "meeting_date": "2026-02-17",
            "meeting_name": "City Council",
            "items": [
                {
                    "item_number": "V.1.a",
                    "title": "Approve Contract with Acme Corp",
                    "description": "APPROVE contract with Acme Corp for $50,000",
                    "attachments": [],
                }
            ],
            "stats": {"total_items": 1},
        }

        result = run_pipeline(
            date="2026-02-17",
            contributions_path=None,
            dry_run=True,
            skip_escribemeetings=False,
        )
        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain the methodology section
        assert "Richmond Common" in result

    @patch("run_pipeline.create_session")
    @patch("run_pipeline.discover_meetings")
    @patch("run_pipeline.find_meeting_by_date")
    def test_pipeline_no_meeting_found_raises(
        self, mock_find, mock_discover, mock_session
    ):
        """Pipeline raises when no meeting found for given date."""
        mock_session.return_value = MagicMock()
        mock_discover.return_value = []
        mock_find.return_value = None

        with pytest.raises(SystemExit):
            run_pipeline(date="2026-12-25", contributions_path=None, dry_run=True)

    def test_pipeline_with_cached_data(self, tmp_path):
        """Pipeline can use pre-scraped eSCRIBE data via --escribemeetings flag."""
        # Create a minimal meeting JSON file
        meeting_data = {
            "meeting_date": "2026-02-17",
            "meeting_type": "regular",
            "city_fips": "0660620",
            "consent_calendar": {
                "items": [
                    {
                        "item_number": "V.1.a",
                        "title": "Approve Contract with TestCo",
                        "description": "APPROVE contract with TestCo for $25,000",
                        "category": "contracts",
                        "financial_amount": "$25,000",
                    }
                ]
            },
            "action_items": [],
            "housing_authority_items": [],
        }
        meeting_json = tmp_path / "meeting.json"
        meeting_json.write_text(json.dumps(meeting_data))

        result = run_pipeline(
            date="2026-02-17",
            contributions_path=None,
            dry_run=True,
            skip_escribemeetings=True,
            meeting_json_path=str(meeting_json),
        )
        assert isinstance(result, str)
        assert "Richmond Common" in result
