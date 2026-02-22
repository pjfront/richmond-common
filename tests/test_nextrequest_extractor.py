"""Tests for NextRequest document extraction via Claude API.

Uses mocked Claude responses — no actual API calls.
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock


SAMPLE_CONTRACT_TEXT = """
PROFESSIONAL SERVICES AGREEMENT

This Agreement is entered into between the City of Richmond ("City")
and ABC Consulting LLC ("Consultant") for the provision of
environmental assessment services.

Contract Amount: $150,000
Term: January 1, 2026 through December 31, 2026
Department: Planning and Building Services

Scope of Work:
Phase 1 - Site Assessment ($50,000)
Phase 2 - Environmental Review ($75,000)
Phase 3 - Final Report ($25,000)
"""

SAMPLE_EXTRACTION_RESPONSE = {
    "document_type": "contract",
    "parties": ["City of Richmond", "ABC Consulting LLC"],
    "amount": 150000,
    "term_start": "2026-01-01",
    "term_end": "2026-12-31",
    "department": "Planning and Building Services",
    "summary": "Professional services agreement for environmental assessment.",
    "entities": ["City of Richmond", "ABC Consulting LLC"],
    "amounts": [150000, 50000, 75000, 25000],
}


class TestExtractDocument:
    """Test Claude API document extraction."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("nextrequest_extractor.anthropic")
    def test_extracts_contract(self, mock_anthropic):
        from nextrequest_extractor import extract_document

        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(SAMPLE_EXTRACTION_RESPONSE))]
        mock_client.messages.create.return_value = mock_response

        result = extract_document(
            text=SAMPLE_CONTRACT_TEXT,
            filename="contract.pdf",
            file_type="pdf",
        )

        assert result["document_type"] == "contract"
        assert result["amount"] == 150000
        assert "ABC Consulting" in str(result["parties"])

    @patch("nextrequest_extractor.anthropic")
    def test_returns_none_on_empty_text(self, mock_anthropic):
        from nextrequest_extractor import extract_document
        result = extract_document(text="", filename="empty.pdf", file_type="pdf")
        assert result is None

    @patch("nextrequest_extractor.anthropic")
    def test_returns_none_on_short_text(self, mock_anthropic):
        from nextrequest_extractor import extract_document
        result = extract_document(text="Too short", filename="tiny.pdf", file_type="pdf")
        assert result is None


class TestCrossReferenceAgenda:
    """Test cross-referencing extracted documents with agenda items."""

    def test_matches_by_entity_name(self):
        from nextrequest_extractor import cross_reference_agenda

        extracted = {
            "entities": ["ABC Consulting LLC", "City of Richmond"],
            "department": "Planning",
            "amount": 150000,
        }
        agenda_items = [
            {"item_number": "H-1", "title": "ABC Consulting contract amendment",
             "description": "Approve amendment to ABC Consulting agreement"},
            {"item_number": "I-1", "title": "Budget update",
             "description": "Quarterly budget review"},
        ]

        matches = cross_reference_agenda(extracted, agenda_items)
        assert len(matches) >= 1
        assert matches[0]["item_number"] == "H-1"

    def test_no_matches_returns_empty(self):
        from nextrequest_extractor import cross_reference_agenda

        extracted = {"entities": ["Unrelated Corp"], "department": "HR", "amount": 0}
        agenda_items = [
            {"item_number": "A-1", "title": "Zoning variance",
             "description": "Residential zoning change"},
        ]

        matches = cross_reference_agenda(extracted, agenda_items)
        assert matches == []
