"""Safety-contract tests for the one-off reviewed July recap repair."""
from __future__ import annotations

import hashlib
import inspect
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import reviewed_july_recap_repair as repair
import post_meeting_recap as legacy_recap


def _null_rows() -> list[dict]:
    return [
        {
            "meeting_id": target.meeting_id,
            "meeting_date": target.meeting_date,
            "city_fips": repair.CITY_FIPS,
            "meeting_type": repair.MEETING_TYPE,
            "body_id": repair.BODY_ID,
            "body_name": repair.BODY_NAME,
            **{field: None for field in repair.RECAP_FIELDS},
        }
        for target in repair.TARGETS.values()
    ]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _install_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact_dir = tmp_path / "reviewed"
    source_dir = artifact_dir / "sources"
    monkeypatch.setattr(repair, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(repair, "SOURCE_DIR", source_dir)
    generated_at = "2026-08-29T12:00:00+00:00"

    for target in repair.TARGETS.values():
        pdf_path, transcript_path, identity_path = repair._source_paths(
            target.meeting_date
        )
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.7\nreview source")
        transcript_path.write_text(
            "[0:00:00]\nOfficial meeting transcript evidence.",
            encoding="utf-8",
            newline="\n",
        )
        transcript_text = transcript_path.read_bytes().decode("utf-8")
        source = {
            "schema_version": repair.SCHEMA_VERSION,
            "approval_id": repair.APPROVAL_ID,
            "meeting_date": target.meeting_date,
            "meeting_id": target.meeting_id,
            "clip_id": target.clip_id,
            "doc_id": target.doc_id,
            "source": "granicus",
            "source_url": target.source_url,
            "resolved_pdf_url": "https://richmond.granicus.com/DocumentViewer.php?file=x.pdf",
            "fetched_at": generated_at,
            "pdf_path": str(pdf_path),
            "pdf_sha256": repair._sha256_file(pdf_path),
            "transcript_path": str(transcript_path),
            "transcript_sha256": repair._sha256_file(transcript_path),
            "transcript_char_count": len(transcript_text),
        }
        _write_json(identity_path, source)

        recap = f"Reviewed candidate recap for {target.meeting_date}."
        candidate = {
            "schema_version": repair.SCHEMA_VERSION,
            "approval_id": repair.APPROVAL_ID,
            "generation_status": "candidate",
            "target": {
                "meeting_date": target.meeting_date,
                "meeting_id": target.meeting_id,
                "clip_id": target.clip_id,
                "doc_id": target.doc_id,
            },
            "source": source,
            "model_requested": repair.MODEL,
            "prompt_sha256": "a" * 64,
            "generated_at": generated_at,
            "usage": {"input_tokens": 100, "output_tokens": 10},
            "cost": {
                "reservation_id": f"00000000-0000-0000-0000-00000000{target.clip_id}",
                "journal_id": f"10000000-0000-0000-0000-00000000{target.clip_id}",
                "model": repair.MODEL,
                "caller": repair.CALLER,
                "event_type": repair._event_type(target.meeting_date),
                "projected_cost": 0.05,
                "actual_cost": 0.02,
                "status": "settled",
            },
            "recap_sha256": repair._sha256_text(recap),
            "recap_fields": {
                "transcript_recap": recap,
                "transcript_recap_source": "granicus",
                "transcript_recap_provenance": {
                    "kind": "meeting_recording",
                    "channel": "granicus",
                    "as_of": generated_at,
                    "generator": repair.GENERATOR,
                },
                "transcript_recap_generated_at": generated_at,
            },
        }
        candidate_path = repair._candidate_path(target.meeting_date)
        _write_json(candidate_path, candidate)
        candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        review = {
            "schema_version": repair.SCHEMA_VERSION,
            "approval_id": repair.APPROVAL_ID,
            "meeting_date": target.meeting_date,
            "meeting_id": target.meeting_id,
            "candidate_sha256": candidate_sha,
            "recap_sha256": candidate["recap_sha256"],
            "transcript_sha256": source["transcript_sha256"],
            "pdf_sha256": source["pdf_sha256"],
            "decision": "pass",
            "reviewer": "independent-source-reviewer",
            "reviewed_at": generated_at,
            "checks": {name: True for name in repair.REVIEW_CHECKS},
            "claims": [{
                "claim": recap,
                "supported": True,
                "evidence": [{"timestamp": "[0:00:00]", "note": "Source support."}],
            }],
        }
        _write_json(repair._review_path(target.meeting_date), review)


def test_allowlist_is_exact() -> None:
    assert set(repair.TARGETS) == {"2026-07-07", "2026-07-21", "2026-07-28"}
    assert {target.meeting_id for target in repair.TARGETS.values()} == {
        "c11d635f-b74f-4208-8fad-376a3791905b",
        "a166af80-e456-4db2-9b74-215a378956a4",
        "3de0bb26-8f30-4836-a5bd-a01b6640b676",
    }
    assert {target.clip_id for target in repair.TARGETS.values()} == {
        "6020", "6025", "6028"
    }
    assert legacy_recap.REVIEWED_JULY_RECAP_QUARANTINE == {
        date: target.meeting_id for date, target in repair.TARGETS.items()
    }


def test_cohort_gate_requires_every_field_null() -> None:
    rows = _null_rows()
    rows[1]["transcript_recap_source"] = "granicus"
    with pytest.raises(repair.RepairBlocked, match="all-null review gate"):
        repair._validate_cohort_null(rows)


def test_budget_guards_never_widen_approved_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "4.50")
    monkeypatch.setenv("RICHMOND_EVENT_BUDGET_USD", "1.00")
    repair._configure_cost_guards("2026-07-07")
    assert repair.os.environ["RICHMOND_API_MONTHLY_CAP_USD"] == "4.50"
    assert repair.os.environ["RICHMOND_EVENT_BUDGET_USD"] == "0.15"
    assert repair.os.environ["RICHMOND_EVENT_TYPE"] == (
        "reviewed-july-recap-repair-v2:2026-07-07"
    )


def test_budget_lock_blocks_before_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RICHMOND_API_BUDGET_LOCK", "true")
    with pytest.raises(repair.RepairBlocked, match="BUDGET_LOCK is active"):
        repair._configure_cost_guards("2026-07-07")


def test_generation_creates_candidate_without_meeting_update_or_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_dir = tmp_path / "reviewed"
    monkeypatch.setattr(repair, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(repair, "SOURCE_DIR", artifact_dir / "sources")
    monkeypatch.setattr(repair, "_configure_cost_guards", lambda _date: None)
    monkeypatch.setattr(repair, "_acquire_generation_lock", lambda _conn, _date: None)
    monkeypatch.setattr(repair, "_assert_no_paid_attempt", lambda _conn, _date: None)
    monkeypatch.setattr(repair, "_load_cohort_rows", lambda _conn: _null_rows())

    connection = MagicMock()
    monkeypatch.setattr(repair, "get_connection", lambda: connection)
    target = repair.TARGETS["2026-07-07"]
    _, transcript_path, _ = repair._source_paths(target.meeting_date)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        "official transcript", encoding="utf-8", newline="\n"
    )
    source = {
        "meeting_date": target.meeting_date,
        "meeting_id": target.meeting_id,
        "clip_id": target.clip_id,
        "doc_id": target.doc_id,
        "source": "granicus",
        "transcript_path": str(transcript_path),
        "transcript_sha256": repair._sha256_file(transcript_path),
        "pdf_sha256": "b" * 64,
    }
    monkeypatch.setattr(repair, "_fetch_or_validate_source", lambda _target: source)
    monkeypatch.setattr(repair, "_build_system_prompt", lambda: "strict prompt")
    run = MagicMock(return_value=(
        json.dumps({"transcript_recap": "A supported recap."}),
        {"input_tokens": 1},
    ))
    monkeypatch.setattr(repair, "_run_deepseek_candidate", run)
    monkeypatch.setattr(
        repair,
        "_load_cost_receipt",
        lambda _conn, _date: {
            "reservation_id": "one",
            "model": repair.MODEL,
            "caller": repair.CALLER,
            "event_type": repair._event_type(target.meeting_date),
            "projected_cost": 0.05,
            "actual_cost": 0.02,
            "status": "settled",
        },
    )

    path = repair.generate_candidate(target.meeting_date)

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["recap_fields"][
        "transcript_recap"
    ] == "A supported recap."
    run.assert_called_once()
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
    assert "UPDATE meetings" not in inspect.getsource(repair.generate_candidate)


def test_existing_v2_reservation_blocks_replay() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [("reservation", "settled", 0.05, 0.02)]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    with pytest.raises(repair.RepairBlocked, match="paid V2 attempt already exists"):
        repair._assert_no_paid_attempt(conn, "2026-07-07")


def test_generation_lock_blocks_a_concurrent_process() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = (False,)
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    with pytest.raises(repair.RepairBlocked, match="holds the lock"):
        repair._acquire_generation_lock(conn, "2026-07-07")
    sql, params = cursor.execute.call_args.args
    assert "pg_try_advisory_xact_lock" in sql
    assert params == ("reviewed-july-recap-repair-v2:generate:2026-07-07",)


def test_tampered_candidate_hash_cannot_be_approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_artifacts(tmp_path, monkeypatch)
    target = repair.TARGETS["2026-07-07"]
    candidate_path = repair._candidate_path(target.meeting_date)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["recap_fields"]["transcript_recap"] += " Tampered."
    _write_json(candidate_path, candidate)

    with pytest.raises(repair.RepairBlocked, match="integrity failed"):
        repair._validate_candidate(target, candidate_path)


def test_failed_review_blocks_entire_cohort_before_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_artifacts(tmp_path, monkeypatch)
    review_path = repair._review_path("2026-07-21")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["decision"] = "fail"
    _write_json(review_path, review)
    connect = MagicMock()
    monkeypatch.setattr(repair, "get_connection", connect)

    with pytest.raises(repair.RepairBlocked, match="did not approve"):
        repair.apply_reviewed()
    connect.assert_not_called()


def test_malformed_candidate_cost_blocks_before_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_artifacts(tmp_path, monkeypatch)
    candidate_path = repair._candidate_path("2026-07-07")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["cost"]["reservation_id"] = {"not": "a scalar UUID"}
    _write_json(candidate_path, candidate)
    connect = MagicMock()
    monkeypatch.setattr(repair, "get_connection", connect)

    with pytest.raises(repair.RepairBlocked, match="cost evidence is malformed"):
        repair.apply_reviewed()
    connect.assert_not_called()


def test_apply_is_one_atomic_three_row_four_field_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_artifacts(tmp_path, monkeypatch)
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [
        (target.meeting_id,) for target in repair.TARGETS.values()
    ]
    monkeypatch.setattr(repair, "get_connection", lambda: conn)
    locks: list[bool] = []

    def fake_rows(_conn: object, *, for_update: bool = False) -> list[dict]:
        locks.append(for_update)
        return _null_rows()

    monkeypatch.setattr(repair, "_load_cohort_rows", fake_rows)
    monkeypatch.setattr(
        repair, "_validate_cost_receipt_against_db", lambda _conn, _candidate: None
    )
    llm = MagicMock(side_effect=AssertionError("apply must not call an LLM"))
    monkeypatch.setattr(repair, "LLMClient", llm)

    updated = repair.apply_reviewed()

    assert locks == [True]
    assert set(updated) == {target.meeting_id for target in repair.TARGETS.values()}
    update_calls = [
        call for call in cursor.execute.call_args_list if "UPDATE meetings" in call.args[0]
    ]
    assert len(update_calls) == 3
    for call in update_calls:
        sql = call.args[0]
        set_clause = sql.split("SET", 1)[1].split("WHERE", 1)[0]
        assert set(re.findall(r"(transcript_recap(?:_source|_provenance|_generated_at)?)\s*=", set_clause)) == set(repair.RECAP_FIELDS)
        assert all(f"{field} IS NULL" in sql for field in repair.RECAP_FIELDS)
        assert "RETURNING id" in sql
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()
    llm.assert_not_called()


def test_apply_rolls_back_if_any_compare_and_swap_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_artifacts(tmp_path, monkeypatch)
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [
        (repair.TARGETS["2026-07-07"].meeting_id,),
        None,
    ]
    monkeypatch.setattr(repair, "get_connection", lambda: conn)
    monkeypatch.setattr(repair, "_load_cohort_rows", lambda *_args, **_kwargs: _null_rows())
    monkeypatch.setattr(
        repair, "_validate_cost_receipt_against_db", lambda _conn, _candidate: None
    )

    with pytest.raises(repair.RepairBlocked, match="compare-and-swap failed"):
        repair.apply_reviewed()
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_source_url_must_remain_on_official_richmond_granicus_host() -> None:
    repair._validate_source_url(
        "https://richmond.granicus.com/DocumentViewer.php?file=official.pdf"
    )
    with pytest.raises(repair.RepairBlocked, match="unexpected transcript URL"):
        repair._validate_source_url("https://example.com/DocumentViewer.php?file=x")


def test_fresh_source_bundle_appears_atomically_after_all_files_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(repair, "SOURCE_DIR", tmp_path / "sources")
    target = repair.TARGETS["2026-07-07"]
    monkeypatch.setattr(
        repair,
        "discover_granicus_meetings",
        lambda: [{
            "meeting_date": target.meeting_date,
            "clip_id": target.clip_id,
            "doc_id": target.doc_id,
        }],
    )
    resolved = "https://richmond.granicus.com/DocumentViewer.php?file=official.pdf"
    monkeypatch.setattr(repair, "_resolve_pdf_url", lambda *_args: resolved)
    response = SimpleNamespace(
        content=b"%PDF-1.7\nsource",
        raise_for_status=lambda: None,
    )
    monkeypatch.setattr(repair.requests, "get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(
        repair,
        "_pdf_to_clean_text",
        lambda _path: "[0:00:00]\n" + ("official transcript evidence " * 50),
    )

    source = repair._fetch_or_validate_source(target)

    pdf_path, transcript_path, identity_path = repair._source_paths(
        target.meeting_date
    )
    assert pdf_path.exists() and transcript_path.exists() and identity_path.exists()
    assert source["pdf_path"] == str(pdf_path)
    assert source["transcript_path"] == str(transcript_path)
    assert not list(repair.SOURCE_DIR.glob(f".{target.meeting_date}.staging-*"))
    assert repair._validate_existing_source(target) == source


@pytest.mark.parametrize("meeting_date", tuple(repair.TARGETS))
@pytest.mark.parametrize("force", [False, True])
def test_legacy_immediate_writer_cannot_bypass_review_gate(
    meeting_date: str,
    force: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup = MagicMock(side_effect=AssertionError("gate must precede date lookup"))
    llm = MagicMock(side_effect=AssertionError("gate must precede paid call"))
    monkeypatch.setattr(legacy_recap, "_get_meeting_id", lookup)
    monkeypatch.setattr(legacy_recap, "LLMClient", llm)
    gate_state = MagicMock(return_value=False)
    monkeypatch.setattr(
        legacy_recap, "_reviewed_july_recap_is_complete", gate_state
    )

    with pytest.raises(legacy_recap.RecapReviewGateError, match="ACTION:"):
        legacy_recap.generate_transcript_recap(meeting_date, force=force)
    lookup.assert_not_called()
    llm.assert_not_called()
    if force:
        gate_state.assert_not_called()
    else:
        gate_state.assert_called_once_with(meeting_date)


def test_legacy_writer_is_idempotent_after_reviewed_cohort_is_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meeting_date = "2026-07-07"
    monkeypatch.setattr(
        legacy_recap, "_reviewed_july_recap_is_complete", lambda _date: True
    )
    lookup = MagicMock(side_effect=AssertionError("complete gate returns first"))
    llm = MagicMock(side_effect=AssertionError("complete gate returns first"))
    monkeypatch.setattr(legacy_recap, "_get_meeting_id", lookup)
    monkeypatch.setattr(legacy_recap, "LLMClient", llm)

    assert legacy_recap.generate_transcript_recap(meeting_date) is None
    lookup.assert_not_called()
    llm.assert_not_called()


@pytest.mark.parametrize(
    ("field_values", "expected"),
    [
        ((None, None, None, None), False),
        (("recap", "granicus", {"kind": "meeting_recording"}, "now"), True),
    ],
)
def test_legacy_gate_reads_exact_row_and_all_four_fields(
    field_values: tuple[object, object, object, object],
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db

    target = repair.TARGETS["2026-07-07"]
    cursor = MagicMock()
    cursor.fetchall.return_value = [(target.meeting_id, *field_values)]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(db, "get_connection", lambda: conn)

    assert legacy_recap._reviewed_july_recap_is_complete(target.meeting_date) is expected
    sql, params = cursor.execute.call_args.args
    assert "WHERE id = %s" in sql
    assert params == (target.meeting_id, repair.CITY_FIPS, target.meeting_date)
    conn.close.assert_called_once()


def test_legacy_gate_rejects_partial_reviewed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db

    target = repair.TARGETS["2026-07-07"]
    cursor = MagicMock()
    cursor.fetchall.return_value = [(target.meeting_id, "recap", None, None, None)]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(db, "get_connection", lambda: conn)

    with pytest.raises(legacy_recap.RecapReviewGateError, match="partially populated"):
        legacy_recap._reviewed_july_recap_is_complete(target.meeting_date)


def test_cost_receipt_must_be_settled_and_under_per_call_cap() -> None:
    cursor = MagicMock()
    now = datetime.now(timezone.utc)
    cursor.fetchall.side_effect = [
        [
            (
                "reservation",
                repair.MODEL,
                repair.CALLER,
                repair._event_type("2026-07-07"),
                0.14,
                0.151,
                "settled",
                now,
                now,
                {},
            )
        ],
    ]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    with pytest.raises(repair.RepairBlocked, match=r"under \$0.15"):
        repair._load_cost_receipt(conn, "2026-07-07")
