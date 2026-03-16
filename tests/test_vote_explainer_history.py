"""Tests for H.16 vote explainer historical context.

Covers: get_member_voting_history, format_historical_context,
historical_context parameter in generate_vote_explainer,
and guard rails (min votes, no motive inference).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from generate_vote_explainers import (
    format_historical_context,
    get_member_voting_history,
)
from vote_explainer import generate_vote_explainer, _load_prompt


# ── format_historical_context ────────────────────────────────


class TestFormatHistoricalContext:
    """H.16: Formatting voting history for prompt inclusion."""

    def test_empty_history_returns_empty_string(self):
        assert format_historical_context({}, "housing") == ""

    def test_single_member_formatted(self):
        history = {
            "Sue Wilson": {
                "total": 5, "aye": 4, "nay": 1,
                "abstain": 0, "absent": 0,
                "aye_pct": 80.0, "category": "housing",
            },
        }
        result = format_historical_context(history, "housing")
        assert "Sue Wilson" in result
        assert "5 housing items" in result
        assert "80.0% aye" in result
        assert "1 nay" in result
        assert "Historical voting patterns" in result

    def test_multiple_members_sorted(self):
        history = {
            "Sue Wilson": {
                "total": 5, "aye": 5, "nay": 0,
                "abstain": 0, "absent": 0,
                "aye_pct": 100.0, "category": "housing",
            },
            "Eduardo Martinez": {
                "total": 4, "aye": 3, "nay": 1,
                "abstain": 0, "absent": 0,
                "aye_pct": 75.0, "category": "housing",
            },
        }
        result = format_historical_context(history, "housing")
        lines = result.strip().split("\n")
        # Header + 2 member lines
        assert len(lines) == 3
        # Alphabetical: Eduardo before Sue
        assert "Eduardo" in lines[1]
        assert "Sue" in lines[2]

    def test_category_in_header(self):
        history = {
            "Tom Butt": {
                "total": 10, "aye": 8, "nay": 2,
                "abstain": 0, "absent": 0,
                "aye_pct": 80.0, "category": "public safety",
            },
        }
        result = format_historical_context(history, "public safety")
        assert "'public safety'" in result


# ── get_member_voting_history ────────────────────────────────


class TestGetMemberVotingHistory:
    """H.16: Query layer for per-member voting patterns."""

    def _mock_conn(self, rows):
        """Create a mock connection returning given rows."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor
        return conn

    def test_sufficient_votes_returned(self):
        """Members with 3+ votes in category are included."""
        rows = [
            ("Sue Wilson", "aye", 4),
            ("Sue Wilson", "nay", 1),
        ]
        conn = self._mock_conn(rows)
        result = get_member_voting_history(
            conn, ["Sue Wilson"], "housing", "2026-03-04",
        )
        assert "Sue Wilson" in result
        assert result["Sue Wilson"]["total"] == 5
        assert result["Sue Wilson"]["aye"] == 4
        assert result["Sue Wilson"]["nay"] == 1
        assert result["Sue Wilson"]["aye_pct"] == 80.0

    def test_insufficient_votes_filtered(self):
        """Members with <3 votes in category are excluded."""
        rows = [
            ("Sue Wilson", "aye", 2),
        ]
        conn = self._mock_conn(rows)
        result = get_member_voting_history(
            conn, ["Sue Wilson"], "housing", "2026-03-04",
        )
        assert "Sue Wilson" not in result

    def test_custom_min_votes(self):
        """Custom min_votes threshold is respected."""
        rows = [
            ("Sue Wilson", "aye", 2),
        ]
        conn = self._mock_conn(rows)
        result = get_member_voting_history(
            conn, ["Sue Wilson"], "housing", "2026-03-04",
            min_votes=2,
        )
        assert "Sue Wilson" in result

    def test_empty_names_returns_empty(self):
        conn = self._mock_conn([])
        result = get_member_voting_history(
            conn, [], "housing", "2026-03-04",
        )
        assert result == {}

    def test_no_category_returns_empty(self):
        conn = self._mock_conn([])
        result = get_member_voting_history(
            conn, ["Sue Wilson"], "", "2026-03-04",
        )
        assert result == {}

    def test_none_category_returns_empty(self):
        conn = self._mock_conn([])
        result = get_member_voting_history(
            conn, ["Sue Wilson"], None, "2026-03-04",
        )
        assert result == {}

    def test_multiple_members_mixed_thresholds(self):
        """Only members meeting min_votes threshold included."""
        rows = [
            ("Sue Wilson", "aye", 5),
            ("Tom Butt", "aye", 1),
            ("Tom Butt", "nay", 1),
        ]
        conn = self._mock_conn(rows)
        result = get_member_voting_history(
            conn, ["Sue Wilson", "Tom Butt"], "housing", "2026-03-04",
        )
        assert "Sue Wilson" in result
        assert "Tom Butt" not in result  # only 2 total

    def test_query_uses_meeting_date_filter(self):
        """Verify the query passes meeting_date for historical-only filtering."""
        conn = self._mock_conn([])
        get_member_voting_history(
            conn, ["Sue Wilson"], "housing", "2026-03-04",
        )
        cursor = conn.cursor.return_value.__enter__.return_value
        call_args = cursor.execute.call_args
        # meeting_date should be the 4th parameter
        assert call_args[0][1][3] == "2026-03-04"


# ── Prompt template integration ──────────────────────────────


class TestPromptTemplateIntegration:
    """H.16: historical_context placeholder in prompt template."""

    def test_template_has_historical_context_placeholder(self):
        template = _load_prompt("vote_explainer_user.txt")
        assert "{historical_context}" in template

    def test_template_formats_with_empty_context(self):
        template = _load_prompt("vote_explainer_user.txt")
        result = template.format(
            item_title="Test",
            category="housing",
            department="Planning",
            financial_amount="$100",
            plain_language_summary="A test item",
            motion_text="Approve the item",
            motion_type="original",
            moved_by="Wilson",
            seconded_by="Martinez",
            result="passed",
            vote_tally="7-0",
            votes_list="Aye: All members",
            historical_context="",
        )
        assert "Test" in result
        assert "housing" in result

    def test_template_formats_with_context(self):
        context = (
            "Historical voting patterns in 'housing' category:\n"
            "- Sue Wilson: voted on 5 housing items (80.0% aye, 1 nay, 0 abstain)"
        )
        template = _load_prompt("vote_explainer_user.txt")
        result = template.format(
            item_title="Test",
            category="housing",
            department="Planning",
            financial_amount="$100",
            plain_language_summary="A test item",
            motion_text="Approve the item",
            motion_type="original",
            moved_by="Wilson",
            seconded_by="Martinez",
            result="passed",
            vote_tally="7-0",
            votes_list="Aye: All members",
            historical_context=context,
        )
        assert "Sue Wilson" in result
        assert "80.0% aye" in result


# ── System prompt guard rails ────────────────────────────────


class TestGuardRails:
    """H.16: Guard rails for historical context usage."""

    def test_system_prompt_has_historical_context_guidance(self):
        system = _load_prompt("vote_explainer_system.txt")
        assert "historical voting patterns" in system.lower()

    def test_system_prompt_prohibits_motive_inference(self):
        system = _load_prompt("vote_explainer_system.txt")
        assert "Do not infer motives from voting patterns" in system

    def test_min_votes_default_is_3(self):
        """Default min_votes parameter ensures 3+ vote minimum."""
        import inspect
        sig = inspect.signature(get_member_voting_history)
        assert sig.parameters["min_votes"].default == 3


# ── generate_vote_explainer accepts historical_context ───────


class TestGenerateVoteExplainerSignature:
    """H.16: generate_vote_explainer accepts historical_context param."""

    def test_accepts_historical_context_kwarg(self):
        """Function signature includes historical_context with default."""
        import inspect
        sig = inspect.signature(generate_vote_explainer)
        param = sig.parameters["historical_context"]
        assert param.default == ""
