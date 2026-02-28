"""Tests for the vote explainer generator CLI (S3.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from generate_vote_explainers import (
    generate_explainer_for_motion,
    save_explainer,
)


# ── Sample Data ─────────────────────────────────────────────


def _make_motion(
    *,
    category: str = "housing",
    is_consent_calendar: bool = False,
    vote_tally: str = "5-2",
    result: str = "passed",
    votes: list | None = None,
) -> dict:
    """Create a sample motion dict for testing."""
    return {
        "motion_id": "test-motion-id",
        "item_title": "Approve housing development at 123 Main St",
        "item_description": "Staff recommends approval.",
        "category": category,
        "department": "Planning",
        "financial_amount": "$15,000,000",
        "plain_language_summary": "A new housing project is proposed.",
        "is_consent_calendar": is_consent_calendar,
        "motion_text": "Approve the development permit",
        "motion_type": "original",
        "moved_by": "Martinez",
        "seconded_by": "Zepeda",
        "result": result,
        "vote_tally": vote_tally,
        "votes": votes or [
            {"official_name": "Martinez", "vote_choice": "aye"},
            {"official_name": "Zepeda", "vote_choice": "aye"},
            {"official_name": "Willis", "vote_choice": "aye"},
            {"official_name": "Bates", "vote_choice": "aye"},
            {"official_name": "Myrick", "vote_choice": "aye"},
            {"official_name": "Butt", "vote_choice": "nay"},
            {"official_name": "Johnson", "vote_choice": "nay"},
        ],
    }


# ── Generate Explainer for Motion ──────────────────────────


class TestGenerateExplainerForMotion:
    def test_generates_for_regular_item(self):
        motion = _make_motion()
        mock_conn = MagicMock()

        with patch("generate_vote_explainers.generate_vote_explainer") as mock_gen:
            mock_gen.return_value = {
                "explainer": "The council approved the housing project in a 5-2 vote.",
                "model": "claude-sonnet-4-20250514",
            }

            result = generate_explainer_for_motion(mock_conn, motion)

        assert result["skipped"] is False
        assert result["explainer"] == "The council approved the housing project in a 5-2 vote."
        assert result["model"] == "claude-sonnet-4-20250514"

    def test_skips_procedural(self):
        motion = _make_motion(category="procedural")
        mock_conn = MagicMock()

        result = generate_explainer_for_motion(mock_conn, motion)

        assert result["skipped"] is True
        assert result["reason"] == "procedural"

    def test_skips_unanimous_consent(self):
        motion = _make_motion(
            category="appointments",
            is_consent_calendar=True,
            vote_tally="7-0",
            votes=[
                {"official_name": "A", "vote_choice": "aye"},
                {"official_name": "B", "vote_choice": "aye"},
            ],
        )
        mock_conn = MagicMock()

        result = generate_explainer_for_motion(mock_conn, motion)

        assert result["skipped"] is True
        assert result["reason"] == "unanimous_consent"

    def test_generates_for_split_consent(self):
        motion = _make_motion(
            category="contracts",
            is_consent_calendar=True,
            vote_tally="5-2",
        )
        mock_conn = MagicMock()

        with patch("generate_vote_explainers.generate_vote_explainer") as mock_gen:
            mock_gen.return_value = {
                "explainer": "Split vote explanation.",
                "model": "claude-sonnet-4-20250514",
            }

            result = generate_explainer_for_motion(mock_conn, motion)

        assert result["skipped"] is False

    def test_dry_run_skips_api_call(self):
        motion = _make_motion()
        mock_conn = MagicMock()

        with patch("generate_vote_explainers.generate_vote_explainer") as mock_gen:
            result = generate_explainer_for_motion(mock_conn, motion, dry_run=True)

        mock_gen.assert_not_called()
        assert result["skipped"] is True
        assert result["reason"] == "dry_run"

    def test_saves_to_database(self):
        motion = _make_motion()
        mock_conn = MagicMock()

        with patch("generate_vote_explainers.generate_vote_explainer") as mock_gen:
            mock_gen.return_value = {
                "explainer": "Vote explanation.",
                "model": "claude-sonnet-4-20250514",
            }
            with patch("generate_vote_explainers.save_explainer") as mock_save:
                generate_explainer_for_motion(mock_conn, motion)

            mock_save.assert_called_once_with(
                mock_conn,
                "test-motion-id",
                "Vote explanation.",
                "claude-sonnet-4-20250514",
            )


# ── Save Explainer ─────────────────────────────────────────


class TestSaveExplainer:
    def test_updates_motions_table(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        save_explainer(mock_conn, "motion-123", "Test explainer.", "claude-sonnet-4-20250514")

        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "UPDATE motions" in sql
        assert "vote_explainer" in sql
        assert "vote_explainer_generated_at" in sql
        assert "vote_explainer_model" in sql

        params = mock_cursor.execute.call_args[0][1]
        assert params[0] == "Test explainer."
        assert params[2] == "claude-sonnet-4-20250514"
        assert params[3] == "motion-123"

        mock_conn.commit.assert_called_once()
