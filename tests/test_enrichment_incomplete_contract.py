"""Regression tests for explicit retryable downstream enrichment results."""
from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import db as db_module
from pipelines import enrichments


def _assert_retryable_partial(result: dict, reason_fragment: str) -> None:
    assert result["retryable_incomplete"] is True
    assert result["incomplete_count"] == 1
    assert result["incomplete_reasons"]
    assert any(
        reason_fragment in reason
        for reason in result["incomplete_reasons"]
    )


@pytest.mark.parametrize(
    ("wrapper_name", "module_name", "generator_name", "reason_fragment"),
    [
        (
            "sync_meeting_summaries",
            "generate_meeting_summaries",
            "generate_summaries",
            "meeting summary",
        ),
        (
            "sync_orientation_previews",
            "generate_orientation_previews",
            "generate_previews",
            "orientation preview",
        ),
        (
            "sync_meeting_recaps",
            "generate_meeting_recaps",
            "generate_recaps",
            "meeting recap",
        ),
        (
            "sync_comment_summaries",
            "generate_comment_summaries",
            "generate_comment_summaries",
            "public comment summary",
        ),
    ],
)
def test_bulk_generator_error_count_uses_explicit_incomplete_contract(
    monkeypatch,
    wrapper_name,
    module_name,
    generator_name,
    reason_fragment,
):
    monkeypatch.setattr(enrichments, "_has_pending_enrichment", lambda *_: True)
    generator = MagicMock(return_value={
        "total": 2,
        "generated": 1,
        "skipped": 0,
        "errors": 1,
    })
    monkeypatch.setitem(
        sys.modules,
        module_name,
        SimpleNamespace(**{generator_name: generator}),
    )

    result = getattr(enrichments, wrapper_name)(MagicMock(), "0660620")

    assert result["errors"] == 1
    _assert_retryable_partial(result, reason_fragment)


def test_successful_processed_work_is_explicitly_complete():
    assert enrichments._retryable_incomplete_fields(0, "unused") == {
        "retryable_incomplete": False,
        "incomplete_count": 0,
        "incomplete_reasons": [],
    }


def test_transcript_window_failure_is_retryable_incomplete(monkeypatch, tmp_path):
    for meeting_date in ("2026-01-01", "2026-01-02"):
        (tmp_path / f"{meeting_date}_clean.txt").write_text(
            "source transcript",
            encoding="utf-8",
        )
    window_meeting = MagicMock(side_effect=[
        {"meeting_date": "2026-01-01", "error": "parse_failure"},
        {"meeting_date": "2026-01-02", "windows": []},
    ])
    monkeypatch.setitem(
        sys.modules,
        "window_meeting_transcript",
        SimpleNamespace(
            window_meeting=window_meeting,
            TRANSCRIPTS_DIR=tmp_path,
        ),
    )

    result = enrichments.sync_transcript_windowing(MagicMock(), "0660620")

    assert result["records_new"] == 1
    assert result["errors"] == 1
    _assert_retryable_partial(result, "2026-01-01")


def test_transcript_vote_parse_failure_is_retryable_incomplete(monkeypatch):
    extract_all = MagicMock(return_value=[
        {
            "status": "extracted",
            "meeting_date": "2026-01-01",
            "motion_count": 2,
        },
        {"status": "parse_failed", "meeting_date": "2026-01-02"},
    ])
    monkeypatch.setitem(
        sys.modules,
        "extract_transcript_votes",
        SimpleNamespace(extract_all=extract_all),
    )

    result = enrichments.sync_transcript_votes(MagicMock(), "0660620")

    assert result["records_new"] == 2
    assert result["errors"] == 1
    _assert_retryable_partial(result, "2026-01-02")


def test_item_summary_row_failure_is_retryable_incomplete(monkeypatch):
    items = [{"id": "item-ok"}, {"id": "item-failed"}]

    def generate(_conn, item, **_kwargs):
        if item["id"] == "item-failed":
            raise RuntimeError("provider timeout")
        return {"skipped": False}

    monkeypatch.setattr(enrichments, "_has_pending_enrichment", lambda *_: False)
    monkeypatch.setattr(enrichments.time, "sleep", lambda *_: None)
    monkeypatch.setitem(
        sys.modules,
        "generate_summaries",
        SimpleNamespace(
            get_items_needing_summaries=MagicMock(return_value=items),
            generate_summary_for_item=generate,
            should_summarize=MagicMock(),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "topic_tagger",
        SimpleNamespace(
            get_topic_label_seeds=MagicMock(return_value=[]),
            format_topic_seed_prompt=MagicMock(return_value=""),
            backfill_topic_labels=MagicMock(),
        ),
    )

    result = enrichments.sync_item_summaries(MagicMock(), "0660620")

    assert result["records_new"] == 1
    assert result["errors"] == 1
    _assert_retryable_partial(result, "item-failed")


def test_vote_explainer_row_failure_is_retryable_incomplete(monkeypatch):
    motions = [{"motion_id": "motion-ok"}, {"motion_id": "motion-failed"}]

    def generate(_conn, motion):
        if motion["motion_id"] == "motion-failed":
            raise RuntimeError("invalid provider output")
        return {"skipped": False}

    monkeypatch.setattr(enrichments.time, "sleep", lambda *_: None)
    monkeypatch.setitem(
        sys.modules,
        "generate_vote_explainers",
        SimpleNamespace(
            get_motions_needing_explainers=MagicMock(return_value=motions),
            generate_explainer_for_motion=generate,
        ),
    )

    result = enrichments.sync_vote_explainers(MagicMock(), "0660620")

    assert result["records_new"] == 1
    assert result["errors"] == 1
    _assert_retryable_partial(result, "motion-failed")


def test_theme_extraction_row_failure_is_retryable_incomplete(monkeypatch):
    items = [
        {"item_id": "theme-ok"},
        {"item_id": "theme-failed"},
    ]

    def extract(item, _comments, _seeds):
        if item["item_id"] == "theme-failed":
            return None
        return {"themes": [{"label": "Housing"}]}

    monkeypatch.setitem(
        sys.modules,
        "theme_extractor",
        SimpleNamespace(
            MIN_COMMENTS=3,
            get_items_needing_themes=MagicMock(return_value=items),
            get_comments_for_item=MagicMock(return_value=[{}, {}, {}]),
            get_existing_theme_seeds=MagicMock(return_value=[]),
            extract_themes_for_item=extract,
            import_themes=MagicMock(return_value={"themes_created": 1}),
        ),
    )

    result = enrichments.sync_theme_extraction(MagicMock(), "0660620")

    assert result["records_new"] == 1
    assert result["errors"] == 1
    _assert_retryable_partial(result, "theme-failed")


def test_conflict_scan_counts_failed_meeting_and_continues(monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [
        ("meeting-failed", date(2026, 1, 1)),
        ("meeting-ok", date(2026, 1, 2)),
    ]

    scan_meeting = MagicMock(side_effect=[
        RuntimeError("scanner failure"),
        SimpleNamespace(flags=[]),
    ])
    fetch_form700 = MagicMock(return_value=[])
    conflict_module = SimpleNamespace(
        scan_meeting_db=scan_meeting,
        _fetch_contributions_from_db=MagicMock(return_value=[]),
        _fetch_form700_interests_from_db=fetch_form700,
        _fetch_expenditures_from_db=MagicMock(return_value=[]),
        _fetch_independent_expenditures_from_db=MagicMock(return_value=[]),
        _fetch_permits_from_db=MagicMock(return_value=[]),
        _fetch_licenses_from_db=MagicMock(return_value=[]),
        _fetch_behested_from_db=MagicMock(return_value=[]),
        _fetch_lobbyists_from_db=MagicMock(return_value=[]),
    )
    monkeypatch.setitem(sys.modules, "conflict_scanner", conflict_module)
    monkeypatch.setattr(db_module, "load_entity_graph", MagicMock(return_value={}))
    monkeypatch.setattr(db_module, "load_org_reverse_map", MagicMock(return_value={}))
    monkeypatch.setattr(db_module, "create_scan_run", MagicMock(return_value="run-id"))
    monkeypatch.setattr(db_module, "save_conflict_flag", MagicMock())
    monkeypatch.setattr(db_module, "supersede_flags_for_meeting", MagicMock())

    result = enrichments.sync_conflict_scanning(conn, "0660620")

    assert result["meetings_scanned"] == 1
    assert result["failed"] == 1
    assert result["errors"] == 1
    assert conn.rollback.call_count == 1
    assert scan_meeting.call_count == 2
    _assert_retryable_partial(result, "meeting-failed")


def test_conflict_flag_replacement_rolls_back_as_one_transaction(monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [("meeting-1", date(2026, 1, 1))]
    flags = [
        SimpleNamespace(
            evidence=["evidence"],
            flag_type="campaign_contribution",
            description=f"flag {index}",
            confidence=0.95,
            legal_reference=None,
            publication_tier=1,
            confidence_factors={},
            scanner_version=3,
            match_details={},
        )
        for index in range(2)
    ]
    conflict_module = SimpleNamespace(
        scan_meeting_db=MagicMock(return_value=SimpleNamespace(flags=flags)),
        _fetch_contributions_from_db=MagicMock(return_value=[]),
        _fetch_form700_interests_from_db=MagicMock(return_value=[]),
        _fetch_expenditures_from_db=MagicMock(return_value=[]),
        _fetch_independent_expenditures_from_db=MagicMock(return_value=[]),
        _fetch_permits_from_db=MagicMock(return_value=[]),
        _fetch_licenses_from_db=MagicMock(return_value=[]),
        _fetch_behested_from_db=MagicMock(return_value=[]),
        _fetch_lobbyists_from_db=MagicMock(return_value=[]),
    )
    monkeypatch.setitem(sys.modules, "conflict_scanner", conflict_module)
    monkeypatch.setattr(db_module, "load_entity_graph", MagicMock(return_value={}))
    monkeypatch.setattr(db_module, "load_org_reverse_map", MagicMock(return_value={}))
    create_run = MagicMock(return_value="run-id")
    supersede = MagicMock(return_value=1)
    save_flag = MagicMock(side_effect=["flag-1", RuntimeError("insert failed")])
    monkeypatch.setattr(db_module, "create_scan_run", create_run)
    monkeypatch.setattr(db_module, "supersede_flags_for_meeting", supersede)
    monkeypatch.setattr(db_module, "save_conflict_flag", save_flag)

    result = enrichments.sync_conflict_scanning(conn, "0660620")

    assert result["meetings_scanned"] == 0
    _assert_retryable_partial(result, "meeting-1")
    assert create_run.call_args.kwargs["commit"] is False
    assert supersede.call_args.kwargs["commit"] is False
    assert all(call.kwargs["commit"] is False for call in save_flag.call_args_list)
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()


@pytest.mark.parametrize(
    "failed_reference",
    ["behested", "lobbyists", "entity_graph"],
)
def test_conflict_reference_failure_cannot_complete_a_scan_run(
    monkeypatch,
    failed_reference,
):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [("meeting-1", date(2026, 1, 1))]
    scan_meeting = MagicMock()
    create_scan_run = MagicMock()

    def reference(name):
        if name == failed_reference:
            return MagicMock(side_effect=RuntimeError(f"{name} read failed"))
        return MagicMock(return_value=[])

    conflict_module = SimpleNamespace(
        scan_meeting_db=scan_meeting,
        _fetch_contributions_from_db=MagicMock(return_value=[]),
        _fetch_form700_interests_from_db=MagicMock(return_value=[]),
        _fetch_expenditures_from_db=MagicMock(return_value=[]),
        _fetch_independent_expenditures_from_db=MagicMock(return_value=[]),
        _fetch_permits_from_db=MagicMock(return_value=[]),
        _fetch_licenses_from_db=MagicMock(return_value=[]),
        _fetch_behested_from_db=reference("behested"),
        _fetch_lobbyists_from_db=reference("lobbyists"),
    )
    monkeypatch.setitem(sys.modules, "conflict_scanner", conflict_module)
    monkeypatch.setattr(
        db_module,
        "load_entity_graph",
        reference("entity_graph"),
    )
    monkeypatch.setattr(
        db_module,
        "load_org_reverse_map",
        MagicMock(return_value={}),
    )
    monkeypatch.setattr(db_module, "create_scan_run", create_scan_run)
    monkeypatch.setattr(db_module, "save_conflict_flag", MagicMock())
    monkeypatch.setattr(db_module, "supersede_flags_for_meeting", MagicMock())

    with pytest.raises(RuntimeError, match="read failed"):
        enrichments.sync_conflict_scanning(conn, "0660620")

    scan_meeting.assert_not_called()
    create_scan_run.assert_not_called()
    conn.rollback.assert_called_once()
    assert not any(
        "UPDATE scan_runs SET status = 'completed'" in call.args[0]
        for call in cursor.execute.call_args_list
    )


def test_behested_conversion_failure_is_not_treated_as_empty():
    import conflict_scanner

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [
        ("Official", "Payor", "Payee", "not-a-number", None, None, "", ""),
    ]

    with pytest.raises(ValueError):
        conflict_scanner._fetch_behested_from_db(conn, "0660620")


def test_filing_period_failure_is_explicit_and_incremental_forces_refresh(
    monkeypatch,
):
    from pipelines import elections

    generate = MagicMock(side_effect=[
        {"briefing_id": "brief-1", "candidates": 2, "contributions": 4},
        RuntimeError("briefing provider failed"),
    ])
    monkeypatch.setitem(
        sys.modules,
        "filing_period_briefing",
        SimpleNamespace(
            current_period_labels=lambda: ["2026-H1", "2026-497"],
            generate_briefing=generate,
        ),
    )

    result = elections.sync_filing_period_briefings(
        MagicMock(), "0660620", sync_type="incremental",
    )

    assert [call.kwargs["force"] for call in generate.call_args_list] == [True, True]
    assert result["records_new"] == 1
    assert result["errors"] == 1
    _assert_retryable_partial(result, "2026-497")


def test_donor_row_failure_uses_explicit_incomplete_contract(monkeypatch):
    import donor_classifier

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [
        ("donor-ok", "Acme Corp", "acme corp"),
        ("donor-failed", "Broken Corp", "broken corp"),
    ]
    monkeypatch.setattr(
        donor_classifier,
        "classify_contributor",
        MagicMock(side_effect=[
            (donor_classifier.CORPORATE, "pattern"),
            RuntimeError("classification failed"),
        ]),
    )
    monkeypatch.setattr(
        donor_classifier,
        "_resolve_slug",
        MagicMock(return_value="acme-corp"),
    )

    result = donor_classifier.sync_donor_classification(conn, "0660620")

    assert result["records_classified"] == 1
    assert result["errors"] == 1
    _assert_retryable_partial(result, "donor-failed")
