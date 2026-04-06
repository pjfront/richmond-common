"""Tests for the pre-meeting orientation preview generator (S21.5.3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from generate_orientation_previews import (
    _build_orientation_context,
    _parse_orientation,
    generate_orientation,
    generate_previews,
)


# ── Sample Data ─────────────────────────────────────────────


def _make_item(
    *,
    item_number: str = "1",
    title: str = "Approve contract with Ghilotti Construction",
    summary_headline: str = "Storm drain repair contract",
    plain_language_summary: str = "The city wants to fix storm drains on Cutting Blvd.",
    category: str = "infrastructure",
    financial_amount: str | None = "$400,000",
    is_consent_calendar: bool = False,
    department: str = "Public Works",
    topic_label: str | None = "storm drain repairs",
    continued_from: str | None = None,
) -> dict:
    return {
        "item_number": item_number,
        "title": title,
        "summary_headline": summary_headline,
        "plain_language_summary": plain_language_summary,
        "category": category,
        "financial_amount": financial_amount,
        "is_consent_calendar": is_consent_calendar,
        "department": department,
        "topic_label": topic_label,
        "continued_from": continued_from,
    }


# ── Context Builder ─────────────────────────────────────────


class TestBuildOrientationContext:
    def test_basic_action_item(self):
        items = [_make_item()]
        ctx = _build_orientation_context(items, {}, {})
        assert "ACTION ITEMS (1 items)" in ctx
        assert "Storm drain repair contract" in ctx
        assert "$400,000" in ctx
        assert "[infrastructure]" in ctx
        assert "Public Works" in ctx

    def test_consent_calendar_separated(self):
        items = [
            _make_item(is_consent_calendar=True, item_number="C1", title="Routine approval"),
            _make_item(item_number="2"),
        ]
        ctx = _build_orientation_context(items, {}, {})
        assert "CONSENT CALENDAR (1 items)" in ctx
        assert "ACTION ITEMS (1 items)" in ctx

    def test_history_injected(self):
        items = [_make_item(topic_label="Point Molate")]
        history = {
            "Point Molate": {"meeting_count": 4, "most_recent": "2026-01-14"},
        }
        ctx = _build_orientation_context(items, history, {})
        assert 'HISTORY: "Point Molate"' in ctx
        assert "4 agendas" in ctx
        assert "January 14, 2026" in ctx

    def test_continuation_injected(self):
        items = [_make_item(item_number="5", continued_from="Item 5")]
        continuations = {"5": "2026-03-04"}
        ctx = _build_orientation_context(items, {}, continuations)
        assert "CONTINUATION: Item 5" in ctx
        assert "March 04, 2026" in ctx

    def test_empty_items_returns_empty(self):
        ctx = _build_orientation_context([], {}, {})
        assert ctx == ""

    def test_financial_amount_omitted_when_null(self):
        items = [_make_item(financial_amount=None)]
        ctx = _build_orientation_context(items, {}, {})
        assert "($" not in ctx

    def test_plain_language_summary_truncated(self):
        long_summary = "A" * 300
        items = [_make_item(plain_language_summary=long_summary)]
        ctx = _build_orientation_context(items, {}, {})
        assert "..." in ctx
        # Should be truncated to 200 chars + "..."
        assert "A" * 200 in ctx

    def test_consent_calendar_recurring_topic_annotated(self):
        items = [
            _make_item(
                is_consent_calendar=True,
                topic_label="street lighting",
                summary_headline="Street light maintenance contract",
            ),
        ]
        history = {"street lighting": {"meeting_count": 3, "most_recent": "2026-02-01"}}
        ctx = _build_orientation_context(items, history, {})
        assert "recurring topic: 3 past meetings" in ctx

    def test_consent_calendar_capped_at_15(self):
        items = [
            _make_item(is_consent_calendar=True, item_number=f"C{i}", title=f"Item {i}")
            for i in range(20)
        ]
        ctx = _build_orientation_context(items, {}, {})
        assert "... and 5 more routine items" in ctx


# ── JSON Parser ──────────────────────────────────────────────


class TestParseOrientation:
    def test_parses_valid_json(self):
        raw = '{"orientation_preview": "First paragraph.\\n\\nSecond paragraph."}'
        result = _parse_orientation(raw)
        assert result == "First paragraph.\n\nSecond paragraph."

    def test_parses_json_in_code_block(self):
        raw = '```json\n{"orientation_preview": "Hello world."}\n```'
        result = _parse_orientation(raw)
        assert result == "Hello world."

    def test_returns_none_for_empty_preview(self):
        raw = '{"orientation_preview": ""}'
        result = _parse_orientation(raw)
        assert result is None

    def test_falls_back_to_raw_text(self):
        raw = "Just some plain text orientation."
        result = _parse_orientation(raw)
        assert result == "Just some plain text orientation."

    def test_strips_whitespace(self):
        raw = '  {"orientation_preview": "  Trimmed.  "}  '
        result = _parse_orientation(raw)
        assert result == "Trimmed."


# ── Generate Orientation (API Call) ──────────────────────────


class TestGenerateOrientation:
    def test_calls_api_and_returns_preview(self):
        items = [_make_item()]
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"orientation_preview": "A $400,000 contract is on the agenda."}')
        ]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = generate_orientation(items, {}, {})

        assert result["orientation_preview"] == "A $400,000 contract is on the agenda."
        assert result["model"] == "claude-sonnet-4-20250514"

        # Verify API call used correct model and system prompt
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert "pre-meeting orientation" in call_kwargs["system"]

    def test_returns_none_for_empty_context(self):
        result = generate_orientation([], {}, {})
        assert result["orientation_preview"] is None
        assert result["model"] is None


# ── Generate Previews (Batch Runner) ─────────────────────────


class TestGeneratePreviews:
    def test_skips_meetings_with_no_items(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Meeting query returns 1 meeting
        mock_cur.fetchall.side_effect = [
            [("meeting-1", "2026-04-01", "Regular")],  # meetings
            [],  # items (empty)
        ]

        result = generate_previews(mock_conn, meeting_id="meeting-1", delay=0)
        assert result["skipped"] == 1
        assert result["generated"] == 0

    def test_generates_and_saves_orientation(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Meeting query returns 1 meeting
        # Items query returns 1 item
        # Topic history returns empty
        mock_cur.fetchall.side_effect = [
            [("meeting-1", "2026-04-01", "Regular")],  # meetings
            [("1", "Contract", "Storm drains", "Fix drains", "infrastructure",
              "$400K", False, "Public Works", "storm drains", None)],  # items
            [],  # topic history
        ]
        mock_cur.fetchone.return_value = None  # no continuations

        with patch("generate_orientation_previews.generate_orientation") as mock_gen:
            mock_gen.return_value = {
                "orientation_preview": "A $400K contract is up for discussion.",
                "model": "claude-sonnet-4-20250514",
            }

            result = generate_previews(mock_conn, meeting_id="meeting-1", delay=0)

        assert result["generated"] == 1
        # Verify UPDATE was called
        update_call = mock_cur.execute.call_args_list[-1]
        assert "orientation_preview" in update_call.args[0]
        mock_conn.commit.assert_called()
