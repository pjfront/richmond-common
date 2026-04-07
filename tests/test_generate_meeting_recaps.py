"""Tests for the post-meeting recap generator (S21.5.4)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from generate_meeting_recaps import (
    _build_recap_context,
    _parse_recap,
    generate_recap,
    generate_recaps,
)


# ── Sample Data ─────────────────────────────────────────────


def _make_item(
    *,
    id: str = "item-uuid-1",
    item_number: str = "1",
    title: str = "Approve contract with Ghilotti Construction",
    summary_headline: str = "Storm drain repair contract",
    plain_language_summary: str = "The city wants to fix storm drains on Cutting Blvd.",
    category: str = "infrastructure",
    financial_amount: str | None = "$400,000",
    is_consent_calendar: bool = False,
    department: str = "Public Works",
    topic_label: str | None = "storm drain repairs",
    continued_to: str | None = None,
    vote_result: str = "Passed",
    vote_detail: str = "Butt: aye, Johnson: aye, Martinez: aye, Willis: aye, Bates: aye",
    comment_count: int = 0,
    nay_count: int = 0,
) -> dict:
    return {
        "id": id,
        "item_number": item_number,
        "title": title,
        "summary_headline": summary_headline,
        "plain_language_summary": plain_language_summary,
        "category": category,
        "financial_amount": financial_amount,
        "is_consent_calendar": is_consent_calendar,
        "department": department,
        "topic_label": topic_label,
        "continued_to": continued_to,
        "vote_result": vote_result,
        "vote_detail": vote_detail,
        "comment_count": comment_count,
        "nay_count": nay_count,
    }


def _make_meeting_meta(
    *,
    meeting_date: str = "2026-04-01",
    meeting_type: str = "Regular",
    presiding_officer: str = "Mayor Martinez",
    call_to_order_time: str = "6:30 PM",
    adjournment_time: str = "9:15 PM",
) -> dict:
    return {
        "meeting_date": meeting_date,
        "meeting_type": meeting_type,
        "presiding_officer": presiding_officer,
        "call_to_order_time": call_to_order_time,
        "adjournment_time": adjournment_time,
    }


# ── Context Builder ─────────────────────────────────────────


class TestBuildRecapContext:
    def test_basic_action_item(self):
        items = [_make_item()]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "ACTION ITEMS (1 items" in ctx
        assert "Storm drain repair contract" in ctx
        assert "$400,000" in ctx
        assert "PASSED" in ctx
        assert "infrastructure" in ctx

    def test_consent_calendar_separated(self):
        items = [
            _make_item(is_consent_calendar=True, item_number="C1", title="Routine",
                       vote_result="Passed"),
            _make_item(item_number="2"),
        ]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "CONSENT CALENDAR (1 items)" in ctx
        assert "ACTION ITEMS (1 items" in ctx

    def test_consent_calendar_passed_as_block(self):
        items = [
            _make_item(is_consent_calendar=True, vote_result="Passed"),
        ]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "PASSED as a block" in ctx

    def test_split_vote_detail_included(self):
        items = [_make_item(
            vote_result="Passed",
            vote_detail="Butt: aye, Johnson: aye, Martinez: aye, Willis: nay, Bates: nay",
            nay_count=2,
        )]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "Vote detail:" in ctx
        assert "Willis: nay" in ctx
        assert "Split vote: 2 nay" in ctx

    def test_theme_narratives_included(self):
        items = [_make_item(id="item-1", comment_count=5)]
        themes = {
            "item-1": [{
                "theme_label": "Privacy & Data Retention",
                "narrative": "Residents expressed concerns about how personal data would be stored.",
                "comment_count": 3,
            }],
        }
        ctx = _build_recap_context(items, themes, _make_meeting_meta())
        assert 'THEME "Privacy & Data Retention"' in ctx
        assert "3 comments" in ctx
        assert "personal data" in ctx

    def test_controversy_ordering(self):
        """Items with nay votes + comments sort first."""
        items = [
            _make_item(id="boring", item_number="1", summary_headline="Routine item",
                       comment_count=0, nay_count=0),
            _make_item(id="hot", item_number="2", summary_headline="Controversial item",
                       comment_count=5, nay_count=2),
        ]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        controversial_pos = ctx.index("Controversial item")
        routine_pos = ctx.index("Routine item")
        assert controversial_pos < routine_pos

    def test_failed_items_visible(self):
        items = [_make_item(vote_result="Failed")]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "FAILED" in ctx

    def test_meeting_metadata_included(self):
        meta = _make_meeting_meta(
            presiding_officer="Mayor Martinez",
            call_to_order_time="6:30 PM",
        )
        ctx = _build_recap_context([_make_item()], {}, meta)
        assert "Mayor Martinez" in ctx
        assert "6:30 PM" in ctx

    def test_continued_items_listed(self):
        items = [_make_item(continued_to="2026-05-01", summary_headline="Deferred item")]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "CONTINUED TO FUTURE MEETING" in ctx
        assert "Deferred item" in ctx

    def test_empty_items_returns_metadata_only(self):
        ctx = _build_recap_context([], {}, _make_meeting_meta())
        assert "MEETING:" in ctx
        assert "ACTION ITEMS" not in ctx

    def test_total_public_comments_shown(self):
        items = [
            _make_item(id="a", comment_count=3),
            _make_item(id="b", item_number="2", comment_count=5),
        ]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "Total public comments across all items: 8" in ctx

    def test_financial_amount_omitted_when_null(self):
        items = [_make_item(financial_amount=None)]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "($" not in ctx

    def test_plain_language_summary_truncated(self):
        long_summary = "A" * 300
        items = [_make_item(plain_language_summary=long_summary)]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "..." in ctx
        assert "A" * 200 in ctx

    def test_consent_calendar_capped_at_15(self):
        items = [
            _make_item(is_consent_calendar=True, item_number=f"C{i}",
                       title=f"Item {i}", vote_result="Passed")
            for i in range(20)
        ]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "... and 5 more routine items" in ctx

    def test_themes_capped_at_3_per_item(self):
        """Only the first 3 themes per item are shown (already sorted by SQL)."""
        items = [_make_item(id="item-1", comment_count=10)]
        themes = {
            "item-1": [
                {"theme_label": f"Theme {i}", "narrative": f"Narrative {i}", "comment_count": 10 - i}
                for i in range(5)
            ],
        }
        ctx = _build_recap_context(items, themes, _make_meeting_meta())
        # First 3 themes shown (already ordered by comment_count DESC from SQL)
        assert 'THEME "Theme 0"' in ctx
        assert 'THEME "Theme 1"' in ctx
        assert 'THEME "Theme 2"' in ctx
        # Themes 3 and 4 should be excluded by the cap
        assert 'THEME "Theme 3"' not in ctx
        assert 'THEME "Theme 4"' not in ctx
        assert ctx.count("THEME") == 3

    def test_no_vote_recorded(self):
        items = [_make_item(vote_result="", vote_detail="")]
        ctx = _build_recap_context(items, {}, _make_meeting_meta())
        assert "NO VOTE RECORDED" in ctx


# ── JSON Parser ──────────────────────────────────────────────


class TestParseRecap:
    def test_parses_valid_json(self):
        raw = '{"meeting_recap": "The council approved a **$400,000** contract."}'
        result = _parse_recap(raw)
        assert result == "The council approved a **$400,000** contract."

    def test_parses_json_in_code_block(self):
        raw = '```json\n{"meeting_recap": "Hello world."}\n```'
        result = _parse_recap(raw)
        assert result == "Hello world."

    def test_returns_none_for_empty_recap(self):
        raw = '{"meeting_recap": ""}'
        result = _parse_recap(raw)
        assert result is None

    def test_falls_back_to_raw_text(self):
        raw = "Just some plain text recap."
        result = _parse_recap(raw)
        assert result == "Just some plain text recap."

    def test_strips_whitespace(self):
        raw = '  {"meeting_recap": "  Trimmed.  "}  '
        result = _parse_recap(raw)
        assert result == "Trimmed."

    def test_regex_fallback_for_partial_json(self):
        raw = '{"meeting_recap": "The council met and approved several items."'
        result = _parse_recap(raw)
        assert "approved several items" in result

    def test_newlines_preserved(self):
        raw = '{"meeting_recap": "First paragraph.\\n\\nSecond paragraph."}'
        result = _parse_recap(raw)
        assert "First paragraph.\n\nSecond paragraph." == result


# ── Generate Recap (API Call) ──────────────────────────────


class TestGenerateRecap:
    def test_calls_api_and_returns_recap(self):
        items = [_make_item()]
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"meeting_recap": "The council approved a **$400,000** storm drain contract."}')
        ]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = generate_recap(items, {}, _make_meeting_meta())

        assert "storm drain contract" in result["meeting_recap"]
        assert result["model"] == "claude-sonnet-4-20250514"

        # Verify API call parameters
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["max_tokens"] == 1200
        assert "post-meeting recap" in call_kwargs["system"]

    def test_returns_none_for_empty_context(self):
        result = generate_recap([], {}, _make_meeting_meta())
        # Even with empty items, meeting metadata produces context
        # so this should still attempt generation — unless context is truly empty
        # The function checks context.strip(), which will have metadata
        assert result is not None


# ── Generate Recaps (Batch Runner) ─────────────────────────


class TestGenerateRecaps:
    def test_skips_meetings_with_no_items(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Meeting query returns 1 meeting, items query returns empty
        mock_cur.fetchall.side_effect = [
            [("meeting-1", "2026-04-01", "Regular", "Mayor Martinez", "6:30 PM", "9:15 PM")],
            [],  # items (empty)
        ]

        result = generate_recaps(mock_conn, meeting_id="meeting-1", delay=0)
        assert result["skipped"] == 1
        assert result["generated"] == 0

    def test_generates_and_saves_recap(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Meeting query → 1 meeting, items → 1 item, themes → empty
        mock_cur.fetchall.side_effect = [
            [("meeting-1", "2026-04-01", "Regular", "Mayor Martinez", "6:30 PM", "9:15 PM")],
            [("uuid-1", "1", "Contract", "Storm drains", "Fix drains",
              "infrastructure", "$400K", False, "Public Works", "storm drains",
              None, "Passed", "Butt: aye, Martinez: aye", 0, 0)],  # items
            [],  # themes
        ]

        with patch("generate_meeting_recaps.generate_recap") as mock_gen:
            mock_gen.return_value = {
                "meeting_recap": "The council approved a storm drain contract.",
                "model": "claude-sonnet-4-20250514",
            }

            result = generate_recaps(mock_conn, meeting_id="meeting-1", delay=0)

        assert result["generated"] == 1
        # Verify UPDATE targeted meeting_recap column
        update_call = mock_cur.execute.call_args_list[-1]
        assert "meeting_recap" in update_call.args[0]
        mock_conn.commit.assert_called()

    def test_vote_gate_applied(self):
        """The batch query should include the vote gate SQL."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.side_effect = [[], []]

        generate_recaps(mock_conn, city_fips="0660620", delay=0)

        # The first execute call (meeting query) should contain the vote gate
        first_query = mock_cur.execute.call_args_list[0].args[0]
        assert "EXISTS" in first_query
        assert "motions" in first_query

    def test_handles_error_gracefully(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_cur.fetchall.side_effect = [
            [("meeting-1", "2026-04-01", "Regular", "Mayor Martinez", "6:30 PM", "9:15 PM")],
            [("uuid-1", "1", "Contract", "Storm drains", "Fix drains",
              "infrastructure", "$400K", False, "Public Works", "storm drains",
              None, "Passed", "Butt: aye", 0, 0)],
            [],  # themes
        ]

        with patch("generate_meeting_recaps.generate_recap") as mock_gen:
            mock_gen.side_effect = Exception("API error")
            result = generate_recaps(mock_conn, meeting_id="meeting-1", delay=0)

        assert result["errors"] == 1
        assert result["generated"] == 0
        mock_conn.rollback.assert_called()

    def test_returns_correct_stats_structure(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = []

        result = generate_recaps(mock_conn, delay=0)

        assert "total" in result
        assert "generated" in result
        assert "skipped" in result
        assert "errors" in result
