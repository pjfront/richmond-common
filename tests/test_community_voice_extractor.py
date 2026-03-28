"""Tests for community_voice_extractor.py — S21 Phase A."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from community_voice_extractor import (
    _normalize_item_number,
    _resolve_item_id,
    extract_speakers,
    import_speakers,
)


# -- Unit tests: item number normalization ----------------------


class TestNormalizeItemNumber:
    def test_already_dotted(self):
        assert _normalize_item_number("W.1") == "w.1"

    def test_no_dot(self):
        assert _normalize_item_number("P5") == "p.5"

    def test_multi_segment(self):
        assert _normalize_item_number("N3D") == "n.3.d"

    def test_lowercase_letter_suffix(self):
        assert _normalize_item_number("V6a") == "v.6.a"

    def test_with_spaces(self):
        assert _normalize_item_number(" W.1 ") == "w.1"

    def test_complex_number(self):
        assert _normalize_item_number("U.2.a") == "u.2.a"


class TestResolveItemId:
    def test_exact_match(self):
        item_map = {"W.1": "uuid-1", "W.2": "uuid-2"}
        assert _resolve_item_id("W.1", item_map) == "uuid-1"

    def test_fuzzy_match_no_dot(self):
        item_map = {"W.1": "uuid-1", "P.5": "uuid-5"}
        assert _resolve_item_id("P5", item_map) == "uuid-5"

    def test_fuzzy_match_case(self):
        item_map = {"V.6.a": "uuid-6a"}
        assert _resolve_item_id("V6A", item_map) == "uuid-6a"

    def test_no_match(self):
        item_map = {"W.1": "uuid-1"}
        assert _resolve_item_id("Z.99", item_map) is None

    def test_empty_map(self):
        assert _resolve_item_id("W.1", {}) is None


# -- Unit tests: import_speakers --------------------------------


SAMPLE_EXTRACTION = {
    "speakers": [
        {
            "speaker_name": "Ahmad Anderson",
            "name_confidence": "high",
            "method": "in_person",
            "item_number": "W.1",
            "summary": "Argued that public safety is important.",
        },
        {
            "speaker_name": "Jane Doe",
            "name_confidence": "medium",
            "method": "zoom",
            "item_number": "W.1",
            "summary": "Raised privacy concerns about camera data retention.",
        },
        {
            "speaker_name": "Cordell Hindler",
            "name_confidence": "high",
            "method": "in_person",
            "item_number": "open_forum",
            "summary": "Praised the city clerk's work.",
        },
        {
            "speaker_name": "Unknown Speaker",
            "name_confidence": "high",
            "method": "in_person",
            "item_number": "Z.99",
            "summary": "Spoke on an item not in the database.",
        },
    ],
    "extraction_notes": "Test extraction",
}


class TestImportSpeakers:
    """Test import logic without actual DB (dry run mode)."""

    def test_dry_run_counts_all(self):
        with patch("community_voice_extractor._get_agenda_item_ids") as mock_ids:
            mock_ids.return_value = {"W.1": "uuid-w1"}

            stats = import_speakers(
                SAMPLE_EXTRACTION,
                meeting_id="meeting-uuid",
                meeting_date="2026-03-03",
                dry_run=True,
            )

            # Dry run reports total count in inserted
            assert stats["inserted"] == 4

    def test_empty_speakers(self):
        with patch("community_voice_extractor._get_agenda_item_ids") as mock_ids:
            mock_ids.return_value = {}

            stats = import_speakers(
                {"speakers": []},
                meeting_id="meeting-uuid",
                meeting_date="2026-03-03",
                dry_run=True,
            )

            assert stats["inserted"] == 0

    def test_import_writes_to_db(self):
        """Test that non-dry-run mode calls DB correctly."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1

        with (
            patch("community_voice_extractor._get_agenda_item_ids") as mock_ids,
            patch("community_voice_extractor.get_connection") as mock_get_conn,
        ):
            mock_ids.return_value = {"W.1": "uuid-w1"}
            mock_get_conn.return_value = mock_conn

            result = {
                "speakers": [
                    {
                        "speaker_name": "Test Speaker",
                        "name_confidence": "high",
                        "method": "in_person",
                        "item_number": "W.1",
                        "summary": "Test summary.",
                    }
                ]
            }

            stats = import_speakers(
                result,
                meeting_id="meeting-uuid",
                meeting_date="2026-03-03",
                dry_run=False,
            )

            assert stats["inserted"] == 1
            mock_conn.commit.assert_called_once()
            mock_cursor.execute.assert_called_once()

            # Verify the SQL includes source='youtube_transcript'
            call_args = mock_cursor.execute.call_args
            sql = call_args[0][0]
            assert "source" in sql
            assert "youtube_transcript" in str(call_args[0][1])

    def test_skips_empty_speaker_name(self):
        """Speakers with no name should be silently skipped."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch("community_voice_extractor._get_agenda_item_ids") as mock_ids,
            patch("community_voice_extractor.get_connection") as mock_get_conn,
        ):
            mock_ids.return_value = {"W.1": "uuid-w1"}
            mock_get_conn.return_value = mock_conn

            result = {
                "speakers": [
                    {
                        "speaker_name": "",
                        "name_confidence": "low",
                        "method": "in_person",
                        "item_number": "W.1",
                        "summary": "Something.",
                    }
                ]
            }

            stats = import_speakers(
                result,
                meeting_id="meeting-uuid",
                meeting_date="2026-03-03",
                dry_run=False,
            )

            assert stats["inserted"] == 0
            mock_cursor.execute.assert_not_called()

    def test_normalizes_invalid_method(self):
        """Unknown methods should be normalized to 'in_person'."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1

        with (
            patch("community_voice_extractor._get_agenda_item_ids") as mock_ids,
            patch("community_voice_extractor.get_connection") as mock_get_conn,
        ):
            mock_ids.return_value = {"W.1": "uuid-w1"}
            mock_get_conn.return_value = mock_conn

            result = {
                "speakers": [
                    {
                        "speaker_name": "Test",
                        "method": "webex",  # Invalid method
                        "item_number": "W.1",
                        "summary": "Test.",
                    }
                ]
            }

            import_speakers(
                result,
                meeting_id="meeting-uuid",
                meeting_date="2026-03-03",
                dry_run=False,
            )

            call_args = mock_cursor.execute.call_args
            params = call_args[0][1]
            # Method should be normalized to in_person (4th param)
            assert params[3] == "in_person"


# -- Integration-style tests: extract_speakers ------------------


class TestExtractSpeakers:
    """Test the Claude API call (mocked)."""

    def test_successful_extraction(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(SAMPLE_EXTRACTION))]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 500

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with (
            patch("community_voice_extractor.anthropic") as mock_anthropic,
            patch("community_voice_extractor._get_agenda_items_text") as mock_items,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_items.return_value = "W.1 - Flock Safety Camera Program"

            transcript_path = Path(__file__).parent / "fixtures" / "fake_transcript.txt"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("Fake transcript content")

            try:
                result = extract_speakers(
                    transcript_path, "meeting-uuid", "2026-03-03"
                )
            finally:
                transcript_path.unlink(missing_ok=True)

            assert result is not None
            assert len(result["speakers"]) == 4
            assert result["speakers"][0]["speaker_name"] == "Ahmad Anderson"

    def test_json_parse_failure_returns_none(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with (
            patch("community_voice_extractor.anthropic") as mock_anthropic,
            patch("community_voice_extractor._get_agenda_items_text") as mock_items,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_items.return_value = "W.1 - Test"

            transcript_path = Path(__file__).parent / "fixtures" / "fake_transcript.txt"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("Fake content")

            try:
                result = extract_speakers(
                    transcript_path, "meeting-uuid", "2026-03-03"
                )
            finally:
                transcript_path.unlink(missing_ok=True)

            assert result is None

    def test_strips_markdown_fences(self):
        """API sometimes wraps JSON in markdown code blocks."""
        raw_json = json.dumps({"speakers": [], "extraction_notes": ""})
        fenced = f"```json\n{raw_json}\n```"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fenced)]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with (
            patch("community_voice_extractor.anthropic") as mock_anthropic,
            patch("community_voice_extractor._get_agenda_items_text") as mock_items,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_items.return_value = "W.1 - Test"

            transcript_path = Path(__file__).parent / "fixtures" / "fake_transcript.txt"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("Fake content")

            try:
                result = extract_speakers(
                    transcript_path, "meeting-uuid", "2026-03-03"
                )
            finally:
                transcript_path.unlink(missing_ok=True)

            assert result is not None
            assert result["speakers"] == []
