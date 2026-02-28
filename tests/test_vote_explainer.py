"""Tests for the vote explainer module (S3.2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Module under test
from vote_explainer import (
    _format_votes_list,
    _is_unanimous,
    generate_vote_explainer,
    should_explain,
)


# ── Prompt Loading ──────────────────────────────────────────


class TestPromptLoading:
    def test_loads_system_prompt(self):
        from vote_explainer import _load_prompt

        prompt = _load_prompt("vote_explainer_system.txt")
        assert "plain English" in prompt
        assert "factual" in prompt.lower()
        assert len(prompt) > 50

    def test_loads_user_prompt(self):
        from vote_explainer import _load_prompt

        prompt = _load_prompt("vote_explainer_user.txt")
        assert "{item_title}" in prompt
        assert "{motion_text}" in prompt
        assert "{votes_list}" in prompt

    def test_missing_prompt_raises(self):
        from vote_explainer import _load_prompt

        with pytest.raises(FileNotFoundError, match="Prompt template not found"):
            _load_prompt("nonexistent_prompt.txt")


# ── Vote Formatting ────────────────────────────────────────


class TestFormatVotesList:
    def test_empty_votes(self):
        result = _format_votes_list([])
        assert "No individual votes recorded" in result

    def test_groups_by_choice(self):
        votes = [
            {"official_name": "Martinez", "vote_choice": "aye"},
            {"official_name": "Butt", "vote_choice": "aye"},
            {"official_name": "Zepeda", "vote_choice": "nay"},
        ]
        result = _format_votes_list(votes)
        assert "Aye: Martinez, Butt" in result
        assert "Nay: Zepeda" in result

    def test_all_four_choices(self):
        votes = [
            {"official_name": "A", "vote_choice": "aye"},
            {"official_name": "B", "vote_choice": "nay"},
            {"official_name": "C", "vote_choice": "abstain"},
            {"official_name": "D", "vote_choice": "absent"},
        ]
        result = _format_votes_list(votes)
        assert "Aye: A" in result
        assert "Nay: B" in result
        assert "Abstain: C" in result
        assert "Absent: D" in result

    def test_ordering_is_consistent(self):
        votes = [
            {"official_name": "B", "vote_choice": "nay"},
            {"official_name": "A", "vote_choice": "aye"},
        ]
        result = _format_votes_list(votes)
        lines = result.strip().split("\n")
        # Aye comes before Nay regardless of input order
        assert lines[0].startswith("Aye")
        assert lines[1].startswith("Nay")


# ── Unanimity Detection ────────────────────────────────────


class TestIsUnanimous:
    def test_tally_7_0_is_unanimous(self):
        assert _is_unanimous(vote_tally="7-0") is True

    def test_tally_6_0_is_unanimous(self):
        assert _is_unanimous(vote_tally="6-0") is True

    def test_tally_5_2_is_not_unanimous(self):
        assert _is_unanimous(vote_tally="5-2") is False

    def test_tally_4_3_is_not_unanimous(self):
        assert _is_unanimous(vote_tally="4-3") is False

    def test_votes_all_aye_is_unanimous(self):
        votes = [
            {"official_name": "A", "vote_choice": "aye"},
            {"official_name": "B", "vote_choice": "aye"},
            {"official_name": "C", "vote_choice": "aye"},
        ]
        assert _is_unanimous(votes=votes) is True

    def test_votes_with_absent_still_unanimous(self):
        votes = [
            {"official_name": "A", "vote_choice": "aye"},
            {"official_name": "B", "vote_choice": "aye"},
            {"official_name": "C", "vote_choice": "absent"},
        ]
        assert _is_unanimous(votes=votes) is True

    def test_votes_with_nay_not_unanimous(self):
        votes = [
            {"official_name": "A", "vote_choice": "aye"},
            {"official_name": "B", "vote_choice": "nay"},
        ]
        assert _is_unanimous(votes=votes) is False

    def test_votes_with_abstain_not_unanimous(self):
        votes = [
            {"official_name": "A", "vote_choice": "aye"},
            {"official_name": "B", "vote_choice": "abstain"},
        ]
        assert _is_unanimous(votes=votes) is False

    def test_no_data_defaults_to_not_unanimous(self):
        assert _is_unanimous() is False

    def test_malformed_tally_falls_through(self):
        assert _is_unanimous(vote_tally="passed") is False


# ── Should Explain ─────────────────────────────────────────


class TestShouldExplain:
    def test_procedural_items_skipped(self):
        assert should_explain(category="procedural") is False

    def test_regular_categories_explained(self):
        for cat in ["budget", "housing", "contracts", "zoning", "personnel"]:
            assert should_explain(category=cat) is True

    def test_none_category_explained(self):
        assert should_explain(category=None) is True

    def test_consent_unanimous_skipped(self):
        assert should_explain(
            category="appointments",
            is_consent_calendar=True,
            vote_tally="7-0",
        ) is False

    def test_consent_split_vote_explained(self):
        assert should_explain(
            category="appointments",
            is_consent_calendar=True,
            vote_tally="5-2",
        ) is True

    def test_consent_with_nay_votes_explained(self):
        votes = [
            {"official_name": "A", "vote_choice": "aye"},
            {"official_name": "B", "vote_choice": "nay"},
        ]
        assert should_explain(
            category="contracts",
            is_consent_calendar=True,
            votes=votes,
        ) is True

    def test_non_consent_unanimous_still_explained(self):
        """Non-consent items always get explanations, even if unanimous."""
        assert should_explain(
            category="budget",
            is_consent_calendar=False,
            vote_tally="7-0",
        ) is True


# ── Explainer Generation ───────────────────────────────────


class TestGenerateVoteExplainer:
    def test_returns_explainer_and_model(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="A contextual vote explanation.")]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("vote_explainer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            result = generate_vote_explainer(
                item_title="Approve housing development at 123 Main St",
                category="housing",
                department="Planning",
                financial_amount="$15,000,000",
                plain_language_summary="A new 200-unit housing project is being proposed.",
                motion_text="Approve the development permit for 123 Main St",
                motion_type="original",
                moved_by="Martinez",
                seconded_by="Zepeda",
                result="passed",
                vote_tally="5-2",
                votes=[
                    {"official_name": "Martinez", "vote_choice": "aye"},
                    {"official_name": "Zepeda", "vote_choice": "aye"},
                    {"official_name": "Butt", "vote_choice": "nay"},
                ],
            )

        assert result["explainer"] == "A contextual vote explanation."
        assert result["model"] == "claude-sonnet-4-20250514"

    def test_handles_missing_optional_fields(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Minimal explainer.")]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("vote_explainer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            result = generate_vote_explainer(
                item_title="Some motion",
                motion_text="Approve the item",
                result="passed",
            )

        call_kwargs = mock_client.messages.create.call_args
        user_message = call_kwargs.kwargs["messages"][0]["content"]
        assert "unknown" in user_message  # category fallback
        assert "Not specified" in user_message  # department fallback
        assert "Not recorded" in user_message  # moved_by fallback
        assert result["explainer"] == "Minimal explainer."

    def test_includes_votes_in_prompt(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test.")]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("vote_explainer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            generate_vote_explainer(
                item_title="Test",
                motion_text="Test motion",
                result="passed",
                votes=[
                    {"official_name": "Martinez", "vote_choice": "aye"},
                    {"official_name": "Butt", "vote_choice": "nay"},
                ],
            )

        call_kwargs = mock_client.messages.create.call_args
        user_message = call_kwargs.kwargs["messages"][0]["content"]
        assert "Aye: Martinez" in user_message
        assert "Nay: Butt" in user_message

    def test_uses_system_prompt(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test.")]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("vote_explainer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            generate_vote_explainer(
                item_title="Test",
                motion_text="Test motion",
                result="passed",
            )

        call_kwargs = mock_client.messages.create.call_args
        assert "system" in call_kwargs.kwargs
        assert "plain English" in call_kwargs.kwargs["system"]

    def test_raises_without_anthropic(self):
        with patch("vote_explainer.anthropic", None):
            with pytest.raises(ImportError, match="anthropic package required"):
                generate_vote_explainer(
                    item_title="Test",
                    motion_text="Test motion",
                    result="passed",
                )

    def test_max_tokens_allows_longer_output(self):
        """Vote explainers get 300 tokens (vs 200 for summaries) for richer context."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test.")]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("vote_explainer.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = mock_client

            generate_vote_explainer(
                item_title="Test",
                motion_text="Test motion",
                result="passed",
            )

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 300
