"""Tests for the transcript-based meeting recap generator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from generate_transcript_recaps import (
    _build_transcript_context,
    _parse_recap,
    generate_transcript_recap,
)


# ── Sample Data ─────────────────────────────────────────────


SAMPLE_TRANSCRIPT = """
[0:00:00]
Good evening and welcome to the Richmond City Council meeting for April first
twenty twenty six. Roll call please.

[0:01:30]
We'll now move to consent calendar items. Any items pulled?

[0:05:00]
Moving on to item number one. This is regarding the storm drain repair contract.
We have a presentation from public works.

[0:10:00]
We'll now open public comment on this item.

[0:10:30]
Thank you council. I'm here to talk about the need for better drainage
on Cutting Boulevard. My street floods every winter.

[0:12:00]
I also want to speak about the drainage. We've been asking for this
for three years now.

[0:15:00]
Thank you to all the speakers. Moving on to item two.

[0:20:00]
This is regarding the surveillance technology policy. We have several
speakers signed up for public comment.

[0:25:00]
I'm concerned about privacy. These cameras collect data on everyone.

[0:26:30]
We need accountability measures before any surveillance expansion.

[0:28:00]
I support the cameras. Crime is a real problem in my neighborhood.

[0:35:00]
Let's move on to the next item.
"""


def _make_agenda_items() -> list[dict]:
    return [
        {
            "item_number": "C.1",
            "title": "Approve minutes of March 18 meeting",
            "summary_headline": "Minutes approval",
            "category": "administrative",
            "financial_amount": None,
            "is_consent_calendar": True,
        },
        {
            "item_number": "1",
            "title": "Approve contract with Ghilotti Construction for storm drain repairs",
            "summary_headline": "Storm drain repair contract",
            "category": "infrastructure",
            "financial_amount": "$400,000",
            "is_consent_calendar": False,
        },
        {
            "item_number": "2",
            "title": "Surveillance technology acquisition and use policy update",
            "summary_headline": "Surveillance technology policy",
            "category": "public safety",
            "financial_amount": None,
            "is_consent_calendar": False,
        },
    ]


def _make_meeting_meta(
    *,
    meeting_date: str = "2026-04-01",
    meeting_type: str = "Regular",
) -> dict:
    return {
        "meeting_date": meeting_date,
        "meeting_type": meeting_type,
    }


# ── Context Builder ─────────────────────────────────────────


class TestBuildTranscriptContext:
    def test_basic_structure(self):
        ctx = _build_transcript_context(
            SAMPLE_TRANSCRIPT, _make_agenda_items(), _make_meeting_meta(),
        )
        assert "MEETING: Date: 2026-04-01" in ctx
        assert "CONSENT CALENDAR (1 items)" in ctx
        assert "ACTION/DISCUSSION ITEMS (2 items)" in ctx
        assert "TRANSCRIPT" in ctx
        assert "storm drain" in ctx.lower()

    def test_agenda_items_included(self):
        ctx = _build_transcript_context(
            SAMPLE_TRANSCRIPT, _make_agenda_items(), _make_meeting_meta(),
        )
        assert "Storm drain repair contract" in ctx
        assert "$400,000" in ctx
        assert "Surveillance technology policy" in ctx

    def test_transcript_text_included(self):
        ctx = _build_transcript_context(
            SAMPLE_TRANSCRIPT, _make_agenda_items(), _make_meeting_meta(),
        )
        assert "drainage" in ctx
        assert "privacy" in ctx.lower()

    def test_empty_transcript(self):
        ctx = _build_transcript_context(
            "", _make_agenda_items(), _make_meeting_meta(),
        )
        assert "TRANSCRIPT (0 chars)" in ctx

    def test_truncation_note(self):
        long_text = "word " * 200_000  # ~1M chars
        ctx = _build_transcript_context(
            long_text, _make_agenda_items(), _make_meeting_meta(),
        )
        assert "truncated" in ctx

    def test_no_agenda_items(self):
        ctx = _build_transcript_context(
            SAMPLE_TRANSCRIPT, [], _make_meeting_meta(),
        )
        assert "CONSENT CALENDAR" not in ctx
        assert "ACTION/DISCUSSION" not in ctx
        assert "TRANSCRIPT" in ctx

    def test_meeting_type_included(self):
        ctx = _build_transcript_context(
            SAMPLE_TRANSCRIPT, [], _make_meeting_meta(meeting_type="Special"),
        )
        assert "Type: Special" in ctx


# ── JSON Parsing ────────────────────────────────────────────


class TestParseRecap:
    def test_valid_json(self):
        raw = '{"transcript_recap": "The council discussed storm drains."}'
        assert _parse_recap(raw) == "The council discussed storm drains."

    def test_code_fenced_json(self):
        raw = '```json\n{"transcript_recap": "The council discussed."}\n```'
        assert _parse_recap(raw) == "The council discussed."

    def test_empty_recap(self):
        raw = '{"transcript_recap": ""}'
        assert _parse_recap(raw) is None

    def test_raw_text_fallback(self):
        raw = "The council discussed storm drains and surveillance."
        result = _parse_recap(raw)
        assert result is not None
        assert "storm drains" in result

    def test_partial_json_regex(self):
        raw = '{"transcript_recap": "Paragraph one.\\n\\nParagraph two."'
        result = _parse_recap(raw)
        assert result is not None
        assert "Paragraph one" in result


# ── Single Recap Generation ─────────────────────────────────


class TestGenerateTranscriptRecap:
    def test_api_call_params(self):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"transcript_recap": "The council discussed storm drains."}'
            )
        ]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = generate_transcript_recap(
                SAMPLE_TRANSCRIPT,
                _make_agenda_items(),
                _make_meeting_meta(),
                source="youtube",
            )

        assert result["transcript_recap"] == "The council discussed storm drains."
        assert result["model"] == "claude-sonnet-4-20250514"
        assert result["source"] == "youtube"

        # Verify API was called with correct params
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs.kwargs["max_tokens"] == 1500
        assert "transcript_recap_system" not in call_kwargs.kwargs["system"]
        # System prompt should contain transcript-specific instructions
        assert "transcript" in call_kwargs.kwargs["system"].lower()

    def test_source_defaults_to_youtube(self):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"transcript_recap": "Recap."}')
        ]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = generate_transcript_recap(
                SAMPLE_TRANSCRIPT, _make_agenda_items(), _make_meeting_meta(),
            )
        assert result["source"] == "youtube"

    def test_source_passed_through(self):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"transcript_recap": "Recap."}')
        ]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = generate_transcript_recap(
                SAMPLE_TRANSCRIPT,
                _make_agenda_items(),
                _make_meeting_meta(),
                source="granicus",
            )
        assert result["source"] == "granicus"
