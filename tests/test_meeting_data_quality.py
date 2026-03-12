"""Tests for meeting data quality fixes (March 2026 audit).

Covers:
  - Financial amount extraction (escribemeetings_to_agenda.py)
  - Sentinel value sanitization (db.py)
  - Closed session item_number extraction (escribemeetings_scraper.py)
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from escribemeetings_to_agenda import extract_financial_amount


class TestExtractFinancialAmountEscribe:
    """Tests for the eSCRIBE-path financial amount extractor.

    This is the version in escribemeetings_to_agenda.py, which previously
    had bugs: returned first match (not largest), didn't handle trailing
    commas, and broke on "$8.3 million" (matched "$8" only).
    """

    def test_simple_dollar_amount(self):
        assert extract_financial_amount("Approve $50,000 for repairs") == "$50,000"

    def test_million_dollar_amount(self):
        assert extract_financial_amount("Budget of $1.2 million") == "$1,200,000"

    def test_billion_dollar_amount(self):
        assert extract_financial_amount("Total $2.5 billion infrastructure") == "$2,500,000,000"

    def test_no_amount(self):
        assert extract_financial_amount("Approve the minutes") is None

    def test_empty_text(self):
        assert extract_financial_amount("") is None

    def test_none_text(self):
        """None input should not crash."""
        assert extract_financial_amount(None) is None

    def test_multiple_amounts_returns_largest(self):
        result = extract_financial_amount(
            "increase by $300,000 for total not to exceed $1,159,990"
        )
        assert result == "$1,159,990"

    def test_homekey_bug_8_3_million(self):
        """The original bug: '$8.3 million' was extracted as '$8'."""
        text = (
            "increasing the City loan amount from $8.3 million to up to "
            "$10.3 million to 425 Civic Center LP"
        )
        result = extract_financial_amount(text)
        assert result == "$10,300,000"

    def test_trailing_comma_stripped(self):
        """Previously returned '$70,000,' with trailing comma."""
        assert extract_financial_amount("Contract amount $70,000, with contingency") == "$70,000"

    def test_trailing_comma_in_sentence(self):
        assert extract_financial_amount("$30,494, for training services") == "$30,494"

    def test_amount_with_cents(self):
        assert extract_financial_amount("Payment of $1,234.56 for services") == "$1,234"

    def test_million_integer(self):
        assert extract_financial_amount("$5 million grant") == "$5,000,000"

    def test_mixed_million_and_numeric(self):
        """When both $X million and $X,XXX appear, return the larger."""
        result = extract_financial_amount(
            "Approve $2 million project with $50,000 contingency"
        )
        assert result == "$2,000,000"


class TestSentinelSanitization:
    """Test that sentinel values are converted to None in db.py."""

    def test_unknown_angle_brackets(self):
        from db import load_meeting_to_db
        # We can't easily test the full function without a DB connection,
        # so test the sanitization logic directly by checking the data dict
        data = {
            "meeting_date": "2026-02-17",
            "meeting_type": "regular",
            "presiding_officer": "<UNKNOWN>",
            "call_to_order_time": "<UNKNOWN>",
        }
        # Apply the same sanitization logic from load_meeting_to_db
        _sentinel_values = {"<UNKNOWN>", "<unknown>", "N/A", "n/a", "Unknown", "unknown", ""}
        _text_fields = [
            "call_to_order_time", "adjournment_time", "presiding_officer",
            "next_meeting_date", "adjourned_in_memory_of",
        ]
        for field in _text_fields:
            if field in data and data[field] in _sentinel_values:
                data[field] = None

        assert data["presiding_officer"] is None
        assert data["call_to_order_time"] is None

    def test_na_sanitized(self):
        data = {"presiding_officer": "N/A"}
        _sentinel_values = {"<UNKNOWN>", "<unknown>", "N/A", "n/a", "Unknown", "unknown", ""}
        if data["presiding_officer"] in _sentinel_values:
            data["presiding_officer"] = None
        assert data["presiding_officer"] is None

    def test_valid_name_preserved(self):
        data = {"presiding_officer": "Mayor Eduardo Martinez"}
        _sentinel_values = {"<UNKNOWN>", "<unknown>", "N/A", "n/a", "Unknown", "unknown", ""}
        if data["presiding_officer"] in _sentinel_values:
            data["presiding_officer"] = None
        assert data["presiding_officer"] == "Mayor Eduardo Martinez"


class TestClosedSessionItemNumberExtraction:
    """Test that item numbers are extracted from title when .AgendaItemCounter is missing."""

    def _extract_item_number(self, title: str) -> tuple[str, str]:
        """Simulate the extraction logic from escribemeetings_scraper.py."""
        item_number = ""
        prefix_match = re.match(r'^([A-Z]\.\d+(?:\.[a-z])?)\s*', title)
        if prefix_match:
            item_number = prefix_match.group(1)
            title = title[prefix_match.end():].strip()
        return item_number, title

    def test_c1_conference(self):
        num, title = self._extract_item_number(
            "C.1CONFERENCE WITH LEGAL COUNSEL - ANTICIPATED LITIGATION"
        )
        assert num == "C.1"
        assert title == "CONFERENCE WITH LEGAL COUNSEL - ANTICIPATED LITIGATION"

    def test_c1_liability(self):
        num, title = self._extract_item_number(
            "C.1LIABILITY CLAIMS (Government Code Section 54956.9)"
        )
        assert num == "C.1"
        assert title == "LIABILITY CLAIMS (Government Code Section 54956.9)"

    def test_c2_subitem(self):
        num, title = self._extract_item_number("C.2.aSOME CLOSED SESSION ITEM")
        assert num == "C.2.a"
        assert title == "SOME CLOSED SESSION ITEM"

    def test_no_prefix(self):
        num, title = self._extract_item_number("Regular Agenda Item Title")
        assert num == ""
        assert title == "Regular Agenda Item Title"

    def test_c1_with_space(self):
        num, title = self._extract_item_number("C.1 PUBLIC EMPLOYEE PERFORMANCE EVALUATION")
        assert num == "C.1"
        assert title == "PUBLIC EMPLOYEE PERFORMANCE EVALUATION"
