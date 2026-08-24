"""Tests for enrichment source-eligibility gates.

The generators and database are mocked; no LLM or live Supabase calls occur.
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipelines import enrichments


def _conn_returning_exists(value: bool):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (value,)
    return conn, cur


@pytest.mark.parametrize(
    ("wrapper_name", "module_name", "generator_name", "gate_name"),
    [
        (
            "sync_meeting_summaries",
            "generate_meeting_summaries",
            "generate_summaries",
            "meeting_summary",
        ),
        (
            "sync_orientation_previews",
            "generate_orientation_previews",
            "generate_previews",
            "orientation_preview",
        ),
        (
            "sync_meeting_recaps",
            "generate_meeting_recaps",
            "generate_recaps",
            "meeting_recap",
        ),
        (
            "sync_comment_summaries",
            "generate_comment_summaries",
            "generate_comment_summaries",
            "comment_summary",
        ),
    ],
)
def test_incremental_wrapper_skips_generator_without_eligible_source(
    monkeypatch,
    wrapper_name,
    module_name,
    generator_name,
    gate_name,
):
    conn, cur = _conn_returning_exists(False)
    generator = MagicMock()
    monkeypatch.setitem(
        sys.modules,
        module_name,
        SimpleNamespace(**{generator_name: generator}),
    )

    result = getattr(enrichments, wrapper_name)(conn, "0660620")

    assert result == {
        "records_fetched": 0,
        "records_new": 0,
        "records_updated": 0,
    }
    generator.assert_not_called()
    cur.execute.assert_called_once_with(
        enrichments._PENDING_ENRICHMENT_SQL[gate_name],
        ("0660620",),
    )


def test_full_sync_explicitly_bypasses_incremental_gate(monkeypatch):
    conn, cur = _conn_returning_exists(False)
    generator = MagicMock(
        return_value={"total": 1, "generated": 1, "skipped": 0, "errors": 0},
    )
    monkeypatch.setitem(
        sys.modules,
        "generate_meeting_summaries",
        SimpleNamespace(generate_summaries=generator),
    )

    result = enrichments.sync_meeting_summaries(
        conn, "0660620", sync_type="full",
    )

    assert result["records_new"] == 1
    generator.assert_called_once_with(conn, "0660620", force=True)
    cur.execute.assert_not_called()


def test_topic_label_backfill_skips_when_no_curated_match_is_eligible(monkeypatch):
    conn, _cur = _conn_returning_exists(False)
    get_items = MagicMock(return_value=[])
    backfill = MagicMock()
    monkeypatch.setitem(
        sys.modules,
        "generate_summaries",
        SimpleNamespace(
            get_items_needing_summaries=get_items,
            generate_summary_for_item=MagicMock(),
            should_summarize=MagicMock(),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "topic_tagger",
        SimpleNamespace(
            get_topic_label_seeds=MagicMock(),
            format_topic_seed_prompt=MagicMock(),
            backfill_topic_labels=backfill,
        ),
    )

    result = enrichments.sync_item_summaries(conn, "0660620")

    assert result == {
        "records_fetched": 0,
        "records_new": 0,
        "records_updated": 0,
    }
    backfill.assert_not_called()
    get_items.assert_called_once_with(conn, "0660620", force=False)


def test_topic_label_backfill_runs_only_for_an_active_curated_match(monkeypatch):
    conn, _cur = _conn_returning_exists(True)
    get_items = MagicMock(return_value=[])
    backfill = MagicMock(return_value={"items_updated": 1})
    monkeypatch.setitem(
        sys.modules,
        "generate_summaries",
        SimpleNamespace(
            get_items_needing_summaries=get_items,
            generate_summary_for_item=MagicMock(),
            should_summarize=MagicMock(),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "topic_tagger",
        SimpleNamespace(
            get_topic_label_seeds=MagicMock(),
            format_topic_seed_prompt=MagicMock(),
            backfill_topic_labels=backfill,
        ),
    )

    enrichments.sync_item_summaries(conn, "0660620")

    backfill.assert_called_once_with(conn, "0660620")
    conn.commit.assert_called_once()


def test_each_gate_requires_source_material_not_only_a_null_output():
    summary_sql = enrichments._PENDING_ENRICHMENT_SQL["meeting_summary"]
    orientation_sql = enrichments._PENDING_ENRICHMENT_SQL["orientation_preview"]
    recap_sql = enrichments._PENDING_ENRICHMENT_SQL["meeting_recap"]
    comments_sql = enrichments._PENDING_ENRICHMENT_SQL["comment_summary"]
    topic_sql = enrichments._PENDING_ENRICHMENT_SQL["topic_label"]

    assert "JOIN motions" in summary_sql
    assert "category <> 'procedural'" in summary_sql
    assert "FROM agenda_items" in orientation_sql
    assert "CONCAT_WS" in orientation_sql
    assert "ai.title, ai.description" in orientation_sql
    assert "ai.summary_headline" not in orientation_sql
    assert "ai.plain_language_summary" not in orientation_sql
    assert "ai.topic_label" not in orientation_sql
    assert "ai.category" not in orientation_sql
    assert "JOIN bodies b ON b.id = m.body_id" in orientation_sql
    assert "b.body_type = 'city_council'" in orientation_sql
    assert "m.meeting_type = 'regular'" in orientation_sql
    assert "m.source_cancelled_at IS NULL" in orientation_sql
    assert "America/Los_Angeles" in orientation_sql
    assert "m.meeting_date >=" in orientation_sql
    assert "m.meeting_date <=" in orientation_sql
    assert "mo.source = 'minutes'" in recap_sql
    assert "public_comments" in comments_sql
    assert "item_theme_narratives" in comments_sql
    assert "FROM item_topics" in topic_sql
    assert "t.status = 'active'" in topic_sql


def test_unknown_eligibility_gate_fails_closed():
    conn, _cur = _conn_returning_exists(True)

    with pytest.raises(ValueError, match="Unknown enrichment eligibility gate"):
        enrichments._has_pending_enrichment(conn, "not-real", "0660620")


def test_orientation_wrapper_rejects_non_richmond_before_pending_query():
    conn, cur = _conn_returning_exists(True)

    with pytest.raises(ValueError, match="Richmond-only"):
        enrichments.sync_orientation_previews(conn, "0000000")

    cur.execute.assert_not_called()
