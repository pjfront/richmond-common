"""Tests for meeting-level summary generation."""
import json
import pytest
from generate_meeting_summaries import _build_meeting_context, _parse_meeting_summary


class TestBuildMeetingContext:
    def test_separates_consent_and_action(self):
        items = [
            {"title": "Approve minutes", "is_consent_calendar": True,
             "summary_headline": "Approve previous meeting minutes", "category": "procedural",
             "financial_amount": None, "vote_result": "Passed", "vote_detail": ""},
            {"title": "Award contract to ABC Corp", "is_consent_calendar": False,
             "summary_headline": "Award $2M contract to ABC Corp for street repairs",
             "category": "contracts", "financial_amount": "$2,000,000",
             "vote_result": "Passed", "vote_detail": "5-2"},
        ]
        context = _build_meeting_context(items)
        assert "CONSENT CALENDAR (1 items)" in context
        assert "ACTION ITEMS (1 items" in context
        assert "ABC Corp" in context
        assert "$2,000,000" in context
        assert "PASSED" in context

    def test_no_vote_recorded_shown_explicitly(self):
        items = [
            {"title": "Discuss budget", "is_consent_calendar": False,
             "summary_headline": "Discuss next year budget",
             "category": "budget", "financial_amount": None,
             "vote_result": "", "vote_detail": ""},
        ]
        context = _build_meeting_context(items)
        assert "NO VOTE RECORDED" in context

    def test_failed_items_show_failed(self):
        items = [
            {"title": "Deny rezoning", "is_consent_calendar": False,
             "summary_headline": "Deny rezoning of 123 Main St",
             "category": "land_use", "financial_amount": None,
             "vote_result": "Failed", "vote_detail": "3-4"},
        ]
        context = _build_meeting_context(items)
        assert "FAILED" in context

    def test_empty_items(self):
        context = _build_meeting_context([])
        assert context == ""

    def test_prefers_headline_over_title(self):
        items = [
            {"title": "H.1 Approve Contract", "is_consent_calendar": False,
             "summary_headline": "Approve road repair contract with Acme",
             "category": "contracts", "financial_amount": None,
             "vote_result": "", "vote_detail": ""},
        ]
        context = _build_meeting_context(items)
        assert "Approve road repair contract with Acme" in context

    def test_caps_consent_items(self):
        items = [
            {"title": f"Item {i}", "is_consent_calendar": True,
             "summary_headline": f"Routine item {i}", "category": "routine",
             "financial_amount": None, "vote_result": "", "vote_detail": ""}
            for i in range(20)
        ]
        context = _build_meeting_context(items)
        assert "... and 5 more routine items" in context


class TestParseMeetingSummary:
    def test_parses_json(self):
        text = '{"meeting_summary": "• First.\\n• Second."}'
        result = _parse_meeting_summary(text)
        assert result == "• First.\n• Second."

    def test_strips_code_fences(self):
        text = '```json\n{"meeting_summary": "• Test."}\n```'
        result = _parse_meeting_summary(text)
        assert result == "• Test."

    def test_fallback_to_raw_text(self):
        text = "Just a plain text summary."
        result = _parse_meeting_summary(text)
        assert result == "Just a plain text summary."

    def test_empty_string_returns_none(self):
        text = '{"meeting_summary": ""}'
        result = _parse_meeting_summary(text)
        assert result is None
