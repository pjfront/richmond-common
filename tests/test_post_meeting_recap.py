"""Tests for the post-meeting recap orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from post_meeting_recap import get_meeting_for_date, run_post_meeting_recap


# ── Meeting Detection ─────────────────────────────────────────


class TestGetMeetingForDate:
    def test_meeting_found(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (
            "abc-123",
            "2026-04-07",
            "regular",
            None,  # no transcript_recap yet
        )
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("post_meeting_recap.get_connection", return_value=mock_conn):
            result = get_meeting_for_date("2026-04-07")

        assert result is not None
        assert result["id"] == "abc-123"
        assert result["meeting_date"] == "2026-04-07"
        assert result["transcript_recap"] is None

    def test_no_meeting(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("post_meeting_recap.get_connection", return_value=mock_conn):
            result = get_meeting_for_date("2026-04-08")

        assert result is None


# ── Full Pipeline ─────────────────────────────────────────────


class TestRunPostMeetingRecap:
    def test_no_meeting_returns_status(self):
        with patch(
            "post_meeting_recap.get_meeting_for_date", return_value=None,
        ):
            result = run_post_meeting_recap("2026-04-08")
        assert result["status"] == "no_meeting"

    def test_already_generated_skips(self):
        with patch(
            "post_meeting_recap.get_meeting_for_date",
            return_value={
                "id": "abc-123",
                "meeting_date": "2026-04-07",
                "meeting_type": "regular",
                "transcript_recap": "Already exists.",
            },
        ):
            result = run_post_meeting_recap("2026-04-07")
        assert result["status"] == "already_generated"

    def test_dry_run_with_local_transcript(self):
        with (
            patch(
                "post_meeting_recap.get_meeting_for_date",
                return_value={
                    "id": "abc-123",
                    "meeting_date": "2026-04-07",
                    "meeting_type": "regular",
                    "transcript_recap": None,
                },
            ),
            patch(
                "transcript_utils.fetch_best_transcript",
                return_value=("Transcript text here...", "youtube"),
            ),
        ):
            result = run_post_meeting_recap("2026-04-07", dry_run=True)

        assert result["status"] == "dry_run"
        assert result["source"] == "youtube"

    def test_no_video_found(self):
        with (
            patch(
                "post_meeting_recap.get_meeting_for_date",
                return_value={
                    "id": "abc-123",
                    "meeting_date": "2026-04-07",
                    "meeting_type": "regular",
                    "transcript_recap": None,
                },
            ),
            patch(
                "transcript_utils.fetch_best_transcript",
                return_value=None,
            ),
            patch(
                "post_meeting_recap.poll_youtube_for_meeting",
                return_value=None,
            ),
        ):
            result = run_post_meeting_recap("2026-04-07")

        assert result["status"] == "no_video"
