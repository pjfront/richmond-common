"""Tests for the plain language summarizer module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Module under test
from plain_language_summarizer import (
    _load_prompt,
    generate_plain_language_summary,
    should_summarize,
)


# ── Prompt Loading ──────────────────────────────────────────


class TestLoadPrompt:
    def test_loads_system_prompt(self):
        prompt = _load_prompt("plain_language_system.txt")
        assert "plain English" in prompt
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


# ── Summary Generation ──────────────────────────────────────


class TestGenerateSummary:
    def test_returns_summary_and_model(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A plain language summary.")]
        mock_response.model = "claude-sonnet-4-20250514"

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

        assert result["summary"] == "A plain language summary."
        assert result["model"] == "claude-sonnet-4-20250514"

    def test_handles_missing_description(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary from title only.")]
        mock_response.model = "claude-sonnet-4-20250514"

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
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Minimal summary.")]
        mock_response.model = "claude-sonnet-4-20250514"

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
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test.")]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("plain_language_summarizer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            generate_plain_language_summary(title="Test item")

        call_kwargs = mock_client.messages.create.call_args
        assert "system" in call_kwargs.kwargs
        assert "plain English" in call_kwargs.kwargs["system"]

    def test_raises_without_anthropic(self):
        with patch("plain_language_summarizer.anthropic", None):
            with pytest.raises(ImportError, match="anthropic package required"):
                generate_plain_language_summary(title="Test")
