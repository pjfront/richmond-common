"""Tests for the plain language summarizer module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Module under test
from plain_language_summarizer import (
    _load_prompt,
    _parse_response,
    generate_plain_language_summary,
    should_summarize,
)


# ── Prompt Loading ──────────────────────────────────────────


class TestLoadPrompt:
    def test_loads_system_prompt(self):
        prompt = _load_prompt("plain_language_system.txt")
        assert "civic information translator" in prompt
        assert len(prompt) > 50

    def test_loads_user_prompt(self):
        prompt = _load_prompt("plain_language_user.txt")
        assert "{title}" in prompt
        assert "{description}" in prompt

    def test_missing_prompt_raises(self):
        with pytest.raises(FileNotFoundError, match="Prompt template not found"):
            _load_prompt("nonexistent_prompt.txt")


# ── Should Summarize ────────────────────────────────────────


class TestShouldSummarize:
    def test_procedural_items_skipped(self):
        assert should_summarize("procedural") is False

    def test_regular_categories_summarized(self):
        for cat in ["budget", "housing", "contracts", "zoning", "personnel"]:
            assert should_summarize(cat) is True

    def test_none_category_summarized(self):
        assert should_summarize(None) is True

    def test_unknown_category_summarized(self):
        assert should_summarize("other") is True


# ── Response Parsing ────────────────────────────────────────


class TestParseResponse:
    def test_parses_valid_json(self):
        text = '{"summary": "Council approves new park.", "headline": "New park approved."}'
        result = _parse_response(text)
        assert result["summary"] == "Council approves new park."
        assert result["headline"] == "New park approved."

    def test_parses_json_with_code_fences(self):
        text = '```json\n{"summary": "A summary.", "headline": "A headline."}\n```'
        result = _parse_response(text)
        assert result["summary"] == "A summary."
        assert result["headline"] == "A headline."

    def test_parses_json_with_bare_code_fences(self):
        text = '```\n{"summary": "A summary.", "headline": "A headline."}\n```'
        result = _parse_response(text)
        assert result["summary"] == "A summary."
        assert result["headline"] == "A headline."

    def test_falls_back_to_plain_text(self):
        text = "Just a plain text summary without JSON."
        result = _parse_response(text)
        assert result["summary"] == text
        assert result["headline"] is None

    def test_handles_empty_fields(self):
        text = '{"summary": "", "headline": ""}'
        result = _parse_response(text)
        assert result["summary"] is None
        assert result["headline"] is None

    def test_handles_missing_headline_key(self):
        text = '{"summary": "Only a summary."}'
        result = _parse_response(text)
        assert result["summary"] == "Only a summary."
        assert result["headline"] is None

    def test_handles_whitespace_only(self):
        text = '{"summary": "  A summary.  ", "headline": "  A headline.  "}'
        result = _parse_response(text)
        assert result["summary"] == "A summary."
        assert result["headline"] == "A headline."

    def test_handles_empty_string(self):
        result = _parse_response("")
        assert result["summary"] is None
        assert result["headline"] is None


# ── Summary Generation ──────────────────────────────────────


def _mock_json_response(summary: str, headline: str | None = None) -> MagicMock:
    """Create a mock API response with JSON content."""
    payload = {"summary": summary}
    if headline is not None:
        payload["headline"] = headline
    mock_response = MagicMock()
    import json
    mock_response.content = [MagicMock(text=json.dumps(payload))]
    mock_response.model = "claude-sonnet-4-20250514"
    return mock_response


class TestGenerateSummary:
    def test_returns_summary_headline_and_model(self):
        mock_response = _mock_json_response(
            "Council will approve a $2.5 million street paving contract.",
            "Street paving contract approved for $2.5 million.",
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("plain_language_summarizer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            result = generate_plain_language_summary(
                title="Approve contract for street paving",
                description="Staff recommends approval of a $2.5M contract.",
                category="contracts",
                department="Public Works",
                financial_amount="$2,500,000",
            )

        assert result["summary"] == "Council will approve a $2.5 million street paving contract."
        assert result["headline"] == "Street paving contract approved for $2.5 million."
        assert result["model"] == "claude-sonnet-4-20250514"

    def test_handles_plain_text_fallback(self):
        """If the model returns plain text instead of JSON, summary still works."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A plain language summary.")]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("plain_language_summarizer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            result = generate_plain_language_summary(
                title="Approve contract for street paving",
            )

        assert result["summary"] == "A plain language summary."
        assert result["headline"] is None  # Fallback: no headline from plain text
        assert result["model"] == "claude-sonnet-4-20250514"

    def test_handles_missing_description(self):
        mock_response = _mock_json_response("Summary from title only.", "Title-based headline.")

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("plain_language_summarizer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            result = generate_plain_language_summary(
                title="Proclamation honoring local volunteers",
            )

        # Verify the user prompt used the fallback text
        call_kwargs = mock_client.messages.create.call_args
        user_message = call_kwargs.kwargs["messages"][0]["content"]
        assert "(No description provided)" in user_message
        assert result["summary"] == "Summary from title only."

    def test_handles_missing_optional_fields(self):
        mock_response = _mock_json_response("Minimal summary.", "Minimal headline.")

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("plain_language_summarizer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            result = generate_plain_language_summary(
                title="Roll call",
                description=None,
                category=None,
                department=None,
                financial_amount=None,
            )

        call_kwargs = mock_client.messages.create.call_args
        user_message = call_kwargs.kwargs["messages"][0]["content"]
        assert "unknown" in user_message  # category fallback
        assert "Not specified" in user_message  # department fallback
        assert "None" in user_message  # financial_amount fallback

    def test_uses_system_prompt(self):
        mock_response = _mock_json_response("Test.", "Test headline.")

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("plain_language_summarizer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            generate_plain_language_summary(title="Test item")

        call_kwargs = mock_client.messages.create.call_args
        assert "system" in call_kwargs.kwargs
        assert "civic information translator" in call_kwargs.kwargs["system"]

    def test_includes_staff_report_in_prompt(self):
        mock_response = _mock_json_response("Context-rich summary.", "Context headline.")

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("plain_language_summarizer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            generate_plain_language_summary(
                title="Contract renewal",
                staff_report="FINANCIAL IMPACT: $50,000 from General Fund. BACKGROUND: Current contract expires March 31.",
            )

        call_kwargs = mock_client.messages.create.call_args
        user_message = call_kwargs.kwargs["messages"][0]["content"]
        assert "FINANCIAL IMPACT" in user_message
        assert "$50,000" in user_message

    def test_truncates_long_staff_report(self):
        mock_response = _mock_json_response("Summary.", "Headline.")

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        long_report = "A" * 10000

        with patch("plain_language_summarizer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            generate_plain_language_summary(
                title="Test",
                staff_report=long_report,
            )

        call_kwargs = mock_client.messages.create.call_args
        user_message = call_kwargs.kwargs["messages"][0]["content"]
        # Should be truncated to 4000 chars, not the full 10000
        assert "A" * 4000 in user_message
        assert "A" * 4001 not in user_message

    def test_no_staff_report_uses_fallback(self):
        mock_response = _mock_json_response("Summary.", "Headline.")

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("plain_language_summarizer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            generate_plain_language_summary(title="Test", staff_report=None)

        call_kwargs = mock_client.messages.create.call_args
        user_message = call_kwargs.kwargs["messages"][0]["content"]
        assert "(No staff report available)" in user_message

    def test_raises_without_anthropic(self):
        with patch("plain_language_summarizer.anthropic", None):
            with pytest.raises(ImportError, match="anthropic package required"):
                generate_plain_language_summary(title="Test")
