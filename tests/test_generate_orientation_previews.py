"""Tests for the pre-meeting orientation preview generator (S21.5.3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from generate_orientation_previews import (
    _build_orientation_context,
    _fetch_items,
    _parse_orientation,
    _select_candidate_meetings,
    generate_orientation,
    generate_previews,
)
from orientation_scope import (
    ORIENTATION_CANDIDATE_CAP,
    ORIENTATION_CONTEXT_MAX_CHARS,
    ORIENTATION_LOOKAHEAD_DAYS,
    ORIENTATION_SECTION_ITEM_CAP,
    ORIENTATION_SECTION_FETCH_CAP,
    RICHMOND_FIPS,
)


# â”€â”€ Sample Data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _make_item(
    *,
    item_number: str = "1",
    title: str = "Approve contract with Ghilotti Construction",
    description: str = (
        "Approve a $400,000 contract with Ghilotti Construction for storm "
        "drain repairs on Cutting Boulevard."
    ),
    is_consent_calendar: bool = False,
) -> dict:
    return {
        "item_number": item_number,
        "title": title,
        "description": description,
        "is_consent_calendar": is_consent_calendar,
    }


# â”€â”€ Context Builder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestBuildOrientationContext:
    def test_basic_action_item(self):
        items = [_make_item()]
        ctx = _build_orientation_context(items)
        assert "ACTION ITEMS (1 items shown)" in ctx
        assert "Approve contract with Ghilotti Construction" in ctx
        assert "$400,000" in ctx
        assert "Agenda description:" in ctx

    def test_consent_calendar_separated(self):
        items = [
            _make_item(is_consent_calendar=True, item_number="C1", title="Routine approval"),
            _make_item(item_number="2"),
        ]
        ctx = _build_orientation_context(items)
        assert "CONSENT CALENDAR (1 items shown)" in ctx
        assert "ACTION ITEMS (1 items shown)" in ctx

    def test_empty_items_returns_empty(self):
        ctx = _build_orientation_context([])
        assert ctx == ""

    def test_description_is_truncated(self):
        long_description = "A" * 1_000
        items = [_make_item(description=long_description)]
        ctx = _build_orientation_context(items)
        assert "..." in ctx
        assert "A" * 300 in ctx

    def test_derivative_fields_are_not_used(self):
        item = _make_item()
        item.update(
            summary_headline="DERIVATIVE HEADLINE",
            plain_language_summary="DERIVATIVE SUMMARY",
            topic_label="DERIVATIVE TOPIC",
        )
        ctx = _build_orientation_context([item])
        assert "DERIVATIVE" not in ctx

    def test_each_section_is_capped(self):
        items = [
            _make_item(is_consent_calendar=True, item_number=f"C{i}", title=f"Item {i}")
            for i in range(ORIENTATION_SECTION_ITEM_CAP + 5)
        ] + [
            _make_item(item_number=f"A{i}", title=f"Action {i}")
            for i in range(ORIENTATION_SECTION_ITEM_CAP + 4)
        ]
        ctx = _build_orientation_context(items)
        assert "additional consent items omitted by safety limit" in ctx
        assert "additional action items omitted by safety limit" in ctx

    def test_total_context_has_hard_character_cap(self):
        items = [
            _make_item(
                item_number="N" * 100,
                title="T" * 2_000,
                description="D" * 4_000,
                is_consent_calendar=bool(i % 2),
            )
            for i in range(100)
        ]
        ctx = _build_orientation_context(items)
        assert len(ctx) <= ORIENTATION_CONTEXT_MAX_CHARS


# â”€â”€ JSON Parser â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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


# â”€â”€ Generate Orientation (API Call) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestGenerateOrientation:
    def test_calls_api_and_returns_preview(self):
        items = [_make_item()]
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"orientation_preview": "A $400,000 contract is on the agenda."}')
        ]
        mock_response.model = "deepseek-v4-pro"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("generate_orientation_previews.LLMClient") as mock_llm:
            mock_llm.return_value = mock_client
            result = generate_orientation(items)

        assert result["orientation_preview"] == "A $400,000 contract is on the agenda."
        assert result["model"] == "deepseek-v4-pro"

        # Verify API call used correct model and system prompt
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "deepseek-v4-pro"
        assert "pre-meeting orientation" in call_kwargs["system"]

    def test_returns_none_for_empty_context(self):
        result = generate_orientation([])
        assert result["orientation_preview"] is None
        assert result["model"] is None


# â”€â”€ Generate Previews (Batch Runner) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestGeneratePreviews:
    def test_skips_meetings_with_no_items(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Meeting query returns 1 meeting
        mock_cur.fetchall.side_effect = [
            # Tuple shape: (id, meeting_date, meeting_type, agenda_url) â€”
            # agenda_url added by S24 provenance-pattern commit.
            [("meeting-1", "2026-04-01", "Regular", None)],  # meetings
            [],  # action items (empty)
            [],  # consent items (empty)
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
            # Tuple shape: (id, meeting_date, meeting_type, agenda_url) â€”
            # agenda_url added by S24 provenance-pattern commit.
            [("meeting-1", "2026-04-01", "Regular", None)],  # meetings
            [("1", "Contract", "Approve a $400K storm-drain contract", False)],  # items
            [],  # consent items
        ]
        mock_cur.rowcount = 1

        with patch("generate_orientation_previews.generate_orientation") as mock_gen:
            mock_gen.return_value = {
                "orientation_preview": "A $400K contract is up for discussion.",
                "model": "deepseek-v4-pro",
            }

            result = generate_previews(mock_conn, meeting_id="meeting-1", delay=0)

        assert result["generated"] == 1
        # Verify UPDATE was called
        update_call = mock_cur.execute.call_args_list[-1]
        assert "orientation_preview" in update_call.args[0]
        mock_conn.commit.assert_called()

    def test_concurrent_non_force_run_preserves_first_preview(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.side_effect = [
            [("meeting-1", "2026-04-01", "Regular", None)],
            [("1", "Contract", "Agenda description", False)],
            [],
        ]
        mock_cur.rowcount = 0

        with patch("generate_orientation_previews.generate_orientation") as mock_gen:
            mock_gen.return_value = {
                "orientation_preview": "Second generated value",
                "model": "deepseek-v4-pro",
            }
            result = generate_previews(mock_conn, meeting_id="meeting-1", delay=0)

        update_call = mock_cur.execute.call_args_list[-1]
        assert "orientation_preview IS NULL" in update_call.args[0]
        assert result["generated"] == 0
        assert result["skipped"] == 1
        mock_conn.commit.assert_not_called()
        mock_conn.rollback.assert_called_once()


class TestCandidateContainment:
    @staticmethod
    def _select(**overrides):
        cur = MagicMock()
        cur.fetchall.return_value = []
        kwargs = {
            "city_fips": RICHMOND_FIPS,
            "force": False,
            "meeting_id": None,
            "limit": None,
        }
        kwargs.update(overrides)
        _select_candidate_meetings(cur, **kwargs)
        return cur.execute.call_args.args

    def test_automatic_selector_is_upcoming_regular_richmond_council_only(self):
        sql, params = self._select()

        assert "JOIN bodies b ON b.id = m.body_id" in sql
        assert "b.body_type = 'city_council'" in sql
        assert "m.meeting_type = 'regular'" in sql
        assert "m.source_cancelled_at IS NULL" in sql
        assert "America/Los_Angeles" in sql
        assert "m.meeting_date >=" in sql
        assert "m.meeting_date <=" in sql
        assert "m.orientation_preview IS NULL" in sql
        assert params == (
            RICHMOND_FIPS,
            RICHMOND_FIPS,
            ORIENTATION_LOOKAHEAD_DAYS,
            ORIENTATION_CANDIDATE_CAP,
        )

    def test_city_council_filter_excludes_commissions_and_rent_board(self):
        sql, _params = self._select()

        # Commission rows use body_type='commission'; the Rent Board uses a
        # non-council body type. Equality to city_council excludes both.
        assert "b.body_type = 'city_council'" in sql
        assert "b.body_type <>" not in sql

    def test_force_run_still_has_hard_sql_cap(self):
        sql, params = self._select(force=True, limit=10_000)

        assert "LIMIT %s" in sql
        assert params[-1] == ORIENTATION_CANDIDATE_CAP
        assert "m.orientation_preview IS NULL" not in sql

    def test_exact_meeting_is_one_row_but_keeps_all_scope_filters(self):
        sql, params = self._select(
            force=True,
            meeting_id="meeting-exact",
            limit=10_000,
        )

        assert "m.id = %s" in sql
        assert "LIMIT %s" in sql
        assert "b.body_type = 'city_council'" in sql
        assert "m.meeting_type = 'regular'" in sql
        assert "m.source_cancelled_at IS NULL" in sql
        assert "America/Los_Angeles" in sql
        assert params[-2:] == ("meeting-exact", 1)

    def test_exact_meeting_does_not_overwrite_without_force(self):
        sql, _params = self._select(meeting_id="meeting-exact")
        assert "m.orientation_preview IS NULL" in sql

    def test_exact_meeting_can_overwrite_only_with_force(self):
        sql, _params = self._select(force=True, meeting_id="meeting-exact")
        assert "m.orientation_preview IS NULL" not in sql

    def test_non_richmond_city_fips_fails_closed(self):
        cur = MagicMock()

        with pytest.raises(ValueError, match="Richmond-only"):
            _select_candidate_meetings(
                cur,
                city_fips="0000000",
                force=False,
                meeting_id=None,
                limit=None,
            )

        cur.execute.assert_not_called()


def test_agenda_item_query_is_source_closest_and_bounded():
    cur = MagicMock()
    cur.fetchall.side_effect = [[], []]

    _fetch_items(cur, "meeting-1")

    assert cur.execute.call_count == 2
    calls = cur.execute.call_args_list
    for call in calls:
        sql, params = call.args
        assert "ai.title" in sql
        assert "ai.description" in sql
        assert "ai.summary_headline" not in sql
        assert "ai.plain_language_summary" not in sql
        assert "ai.topic_label" not in sql
        assert "ai.category" not in sql
        assert "ai.is_consent_calendar = %s" in sql
        assert "LIMIT %s" in sql
        assert params[-1] == ORIENTATION_SECTION_FETCH_CAP
    assert calls[0].args[1] == (
        "meeting-1", False, ORIENTATION_SECTION_FETCH_CAP,
    )
    assert calls[1].args[1] == (
        "meeting-1", True, ORIENTATION_SECTION_FETCH_CAP,
    )
