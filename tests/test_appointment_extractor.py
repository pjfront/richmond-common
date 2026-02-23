# tests/test_appointment_extractor.py
"""Tests for commission appointment extraction from council minutes."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from appointment_extractor import (
    APPOINTMENT_SCHEMA,
    build_appointment_record,
    compare_with_website,
    extract_appointments_from_meeting,
    normalize_commission_name,
    parse_claude_response,
)


# ── Sample extracted meeting JSON (subset) ────────────────────
SAMPLE_MEETING = {
    "meeting_date": "2025-09-23",
    "consent_calendar": {
        "items": [
            {
                "item_number": "I.1",
                "title": "APPROVE the reappointment of Jane Doe to the Planning Commission for a term ending June 30, 2029",
                "description": "Reappointment by Mayor Martinez. Jane Doe has served since 2025.",
                "department": "City Clerk",
                "category": "personnel",
            },
            {
                "item_number": "I.2",
                "title": "APPROVE a contract with ABC Corp for $50,000",
                "description": "Maintenance contract renewal.",
                "department": "Public Works",
                "category": "contracts",
            },
        ]
    },
    "action_items": [
        {
            "item_number": "J.1",
            "title": "CONFIRM the appointment of Bob Smith to the Police Commission",
            "description": "Appointment by Councilmember Brown, District 1.",
            "department": "City Clerk",
            "category": "personnel",
        }
    ],
}

# ── Sample Claude API response ────────────────────────────────
SAMPLE_CLAUDE_RESPONSE = [
    {
        "person_name": "Jane Doe",
        "commission_name": "Planning Commission",
        "action": "reappoint",
        "appointed_by": "Mayor Martinez",
        "term_end": "2029-06-30",
        "item_number": "I.1",
        "confidence": 0.95,
    },
    {
        "person_name": "Bob Smith",
        "commission_name": "Police Commission",
        "action": "appoint",
        "appointed_by": "Councilmember Brown",
        "term_end": None,
        "item_number": "J.1",
        "confidence": 0.90,
    },
]


class TestNormalizeCommissionName:
    def test_exact_match(self):
        assert normalize_commission_name("Planning Commission") == "planning commission"

    def test_strips_prefix(self):
        assert normalize_commission_name("City of Richmond Planning Commission") == "planning commission"

    def test_strips_whitespace(self):
        assert normalize_commission_name("  Rent  Board  ") == "rent board"

    def test_strips_richmond_prefix(self):
        assert normalize_commission_name("Richmond Rent Board") == "rent board"

    def test_strips_city_of_prefix(self):
        assert normalize_commission_name("City of Planning Commission") == "planning commission"


class TestParseClaudeResponse:
    def test_valid_json(self):
        result = parse_claude_response(json.dumps(SAMPLE_CLAUDE_RESPONSE))
        assert len(result) == 2

    def test_strips_markdown_fences(self):
        wrapped = f"```json\n{json.dumps(SAMPLE_CLAUDE_RESPONSE)}\n```"
        result = parse_claude_response(wrapped)
        assert len(result) == 2

    def test_invalid_json_returns_empty(self):
        result = parse_claude_response("not json at all")
        assert result == []

    def test_non_array_returns_empty(self):
        result = parse_claude_response('{"key": "value"}')
        assert result == []


class TestBuildAppointmentRecord:
    def test_basic_record(self):
        raw = SAMPLE_CLAUDE_RESPONSE[0]
        rec = build_appointment_record(raw, meeting_date="2025-09-23", city_fips="0660620")
        assert rec["name"] == "Jane Doe"
        assert rec["normalized_name"] == "jane doe"
        assert rec["commission_name"] == "Planning Commission"
        assert rec["action"] == "reappoint"
        assert rec["source"] == "council_minutes"
        assert rec["city_fips"] == "0660620"

    def test_appointment_record(self):
        raw = SAMPLE_CLAUDE_RESPONSE[1]
        rec = build_appointment_record(raw, meeting_date="2025-09-23", city_fips="0660620")
        assert rec["action"] == "appoint"
        assert rec["appointed_by"] == "Councilmember Brown"

    def test_meeting_date_included(self):
        raw = SAMPLE_CLAUDE_RESPONSE[0]
        rec = build_appointment_record(raw, meeting_date="2025-09-23", city_fips="0660620")
        assert rec["meeting_date"] == "2025-09-23"


class TestExtractAppointments:
    @patch("appointment_extractor.anthropic")
    def test_calls_claude_api(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(SAMPLE_CLAUDE_RESPONSE))]
        mock_msg.usage.input_tokens = 1000
        mock_msg.usage.output_tokens = 200
        mock_client.messages.create.return_value = mock_msg

        result = extract_appointments_from_meeting(SAMPLE_MEETING)
        assert len(result) == 2
        mock_client.messages.create.assert_called_once()

    @patch("appointment_extractor.anthropic")
    def test_skips_non_appointment_items(self, mock_anthropic):
        """Claude should only return appointment actions, not contracts."""
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        # Claude returns only the 2 appointments, not the contract
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(SAMPLE_CLAUDE_RESPONSE))]
        mock_msg.usage.input_tokens = 1000
        mock_msg.usage.output_tokens = 200
        mock_client.messages.create.return_value = mock_msg

        result = extract_appointments_from_meeting(SAMPLE_MEETING)
        actions = [r["action"] for r in result]
        assert "contract" not in actions

    @patch("appointment_extractor.anthropic")
    def test_returns_empty_for_no_items(self, mock_anthropic):
        """Meetings with no agenda items should return empty without calling API."""
        result = extract_appointments_from_meeting({"meeting_date": "2025-01-01"})
        assert result == []
        mock_anthropic.Anthropic.assert_not_called()

    @patch("appointment_extractor.anthropic")
    def test_handles_list_format_sections(self, mock_anthropic):
        """Some meeting JSONs have sections as lists instead of dicts."""
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="[]")]
        mock_msg.usage.input_tokens = 500
        mock_msg.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_msg

        meeting = {
            "meeting_date": "2025-10-01",
            "action_items": [
                {"item_number": "A.1", "title": "Test item", "description": ""}
            ],
        }
        result = extract_appointments_from_meeting(meeting)
        assert result == []
        mock_client.messages.create.assert_called_once()


# ── Task 6: Staleness comparison tests ──────────────────────

class TestCompareWithWebsite:
    def test_finds_missing_member(self):
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "Planning Commission",
                "action": "appoint",
                "meeting_date": "2025-09-23",
            }
        ]
        website = {
            "Planning Commission": [
                {"name": "Bob Jones", "normalized_name": "bob jones", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 1
        assert findings[0]["member"] == "Jane Doe"
        assert findings[0]["type"] == "member_not_on_website"

    def test_no_finding_when_present(self):
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "Planning Commission",
                "action": "appoint",
                "meeting_date": "2025-09-23",
            }
        ]
        website = {
            "Planning Commission": [
                {"name": "Jane Doe", "normalized_name": "jane doe", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 0

    def test_ignores_resignation_actions(self):
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "Planning Commission",
                "action": "resign",
                "meeting_date": "2025-09-23",
            }
        ]
        website = {
            "Planning Commission": [
                {"name": "Jane Doe", "normalized_name": "jane doe", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 0  # Resignations don't generate staleness flags

    def test_handles_commission_name_normalization(self):
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "City of Richmond Planning Commission",
                "action": "appoint",
                "meeting_date": "2025-09-23",
            }
        ]
        website = {
            "Planning Commission": [
                {"name": "Bob Jones", "normalized_name": "bob jones", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 1  # Should match despite "City of Richmond" prefix

    def test_skips_unscraped_commissions(self):
        """If the commission hasn't been scraped, no finding is generated."""
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "Unknown Commission",
                "action": "appoint",
                "meeting_date": "2025-09-23",
            }
        ]
        website = {
            "Planning Commission": [
                {"name": "Bob Jones", "normalized_name": "bob jones", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 0

    def test_multiple_appointments_mixed_results(self):
        """Mix of present and missing members."""
        appointments = [
            {
                "name": "Jane Doe",
                "normalized_name": "jane doe",
                "commission_name": "Planning Commission",
                "action": "appoint",
                "meeting_date": "2025-09-23",
            },
            {
                "name": "Bob Jones",
                "normalized_name": "bob jones",
                "commission_name": "Planning Commission",
                "action": "reappoint",
                "meeting_date": "2025-09-23",
            },
        ]
        website = {
            "Planning Commission": [
                {"name": "Bob Jones", "normalized_name": "bob jones", "role": "member"},
            ]
        }
        findings = compare_with_website(appointments, website)
        assert len(findings) == 1
        assert findings[0]["member"] == "Jane Doe"
