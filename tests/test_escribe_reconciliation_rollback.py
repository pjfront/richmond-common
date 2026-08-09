"""Safety and artifact tests for bounded eSCRIBE clone delta capture."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import escribe_reconciliation_rollback as rollback  # noqa: E402


CLONE_REF = "bbbbbbbbbbbbbbbbbbbb"
GUID = "11111111-1111-4111-8111-111111111111"


def _target() -> rollback.CloneTarget:
    return rollback.validate_clone_target(
        CLONE_REF,
        f"postgresql://postgres:secret@db.{CLONE_REF}.supabase.co/postgres",
    )


def _rehash(snapshot):
    snapshot = copy.deepcopy(snapshot)
    snapshot.pop("snapshot_sha256", None)
    snapshot["snapshot_sha256"] = hashlib.sha256(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return snapshot


def _snapshot(phase="before", captured_at="2026-08-08T10:00:00+00:00"):
    value = {
        "schema_version": rollback.SNAPSHOT_SCHEMA_VERSION,
        "phase": phase,
        "snapshot_id": f"{phase}-snapshot",
        "captured_at": captured_at,
        "city_fips": "0660620",
        "target": {
            "project_ref": CLONE_REF,
            "host": f"db.{CLONE_REF}.supabase.co",
            "port": None,
            "database_name": "postgres",
            "target_fingerprint": _target().fingerprint,
        },
        "cohort": {
            "guids": [GUID],
            "guid_count": 1,
            "guid_sha256": rollback._sha256_json([GUID]),
        },
        "tables": {table: [] for table in rollback.TABLE_ORDER},
    }
    return _rehash(value)


class TestTargetSafety:
    def test_rejects_production_project_ref(self):
        with pytest.raises(rollback.RollbackSafetyError, match="hard no-go"):
            rollback.validate_clone_target(
                rollback.PRODUCTION_PROJECT_REF,
                "postgresql://unused@example.supabase.co/postgres",
            )

    def test_rejects_production_ref_hidden_in_url(self):
        with pytest.raises(rollback.RollbackSafetyError, match="production"):
            rollback.validate_clone_target(
                CLONE_REF,
                "postgresql://postgres."
                f"{CLONE_REF}:pw@pooler.supabase.com/postgres?x="
                + rollback.PRODUCTION_PROJECT_REF,
            )

    def test_rejects_unproven_or_non_supabase_target(self):
        with pytest.raises(rollback.RollbackSafetyError, match="not a Supabase"):
            rollback.validate_clone_target(
                CLONE_REF,
                f"postgresql://postgres.{CLONE_REF}:pw@localhost/postgres",
            )
        with pytest.raises(rollback.RollbackSafetyError, match="does not prove"):
            rollback.validate_clone_target(
                CLONE_REF,
                "postgresql://postgres:pw@db.cccccccccccccccccccc.supabase.co/postgres",
            )

    def test_accepts_direct_and_pooler_clone_urls_without_retaining_secret(self):
        direct = rollback.validate_clone_target(
            CLONE_REF,
            f"postgresql://postgres:top-secret@db.{CLONE_REF}.supabase.co/postgres",
        )
        pooler = rollback.validate_clone_target(
            CLONE_REF,
            f"postgresql://postgres.{CLONE_REF}:top-secret@aws-0-us-west-1."
            "pooler.supabase.com:6543/postgres",
        )
        assert direct.project_ref == pooler.project_ref == CLONE_REF
        assert "secret" not in repr(direct)
        assert "secret" not in repr(pooler)


class TestCohortSafety:
    def test_requires_valid_unique_bounded_guids(self):
        assert rollback.normalize_guids([GUID.upper()]) == [GUID]
        with pytest.raises(rollback.RollbackSafetyError, match="At least one"):
            rollback.normalize_guids([])
        with pytest.raises(rollback.RollbackSafetyError, match="Duplicate"):
            rollback.normalize_guids([GUID, GUID])
        with pytest.raises(rollback.RollbackSafetyError, match="Invalid"):
            rollback.normalize_guids(["Richmond"])
        too_many = [str(__import__("uuid").uuid4())
                    for _ in range(rollback.MAX_COHORT_GUIDS + 1)]
        with pytest.raises(rollback.RollbackSafetyError, match="maximum"):
            rollback.normalize_guids(too_many)

    def test_queries_are_guid_scoped_and_never_use_date_fallback_identity(self):
        all_sql = "\n".join((
            rollback.DOCUMENTS_QUERY,
            rollback.MEETINGS_QUERY,
            rollback.AGENDA_ITEMS_QUERY,
            rollback.ATTACHMENTS_QUERY,
        )).lower()
        assert "source_meeting_guid = any" in all_sql
        assert "metadata->>'meeting_guid' = any" in all_sql
        assert "source_identifier = any" in all_sql
        assert "meeting_date =" not in all_sql
        assert "limit" not in all_sql


def test_capture_is_repeatable_read_only_and_records_exact_rows():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    document_id = "00000000-0000-4000-8000-000000000001"
    meeting_id = "00000000-0000-4000-8000-000000000002"
    agenda_id = "00000000-0000-4000-8000-000000000003"
    attachment_id = "00000000-0000-4000-8000-000000000004"
    rows = [
        [{"captured_at": datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
          "database_name": "postgres"}],
        [{"id": document_id, "metadata": {"meeting_guid": GUID},
          "ingested_at": datetime(2026, 8, 1, tzinfo=timezone.utc)}],
        [{"id": meeting_id, "source_meeting_guid": GUID,
          "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc)}],
        [{"id": agenda_id, "meeting_id": meeting_id,
          "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc)}],
        [{"id": attachment_id, "agenda_item_id": agenda_id,
          "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc)}],
    ]
    with patch.object(rollback, "_fetch_rows", side_effect=rows):
        snapshot = rollback.capture_snapshot(
            conn, _target(), [GUID], phase="before"
        )

    first_sql = cur.execute.call_args_list[0].args[0]
    assert "REPEATABLE READ" in first_sql
    assert "READ ONLY" in first_sql
    conn.rollback.assert_called_once_with()
    assert snapshot["tables"]["documents"][0]["id"] == document_id
    assert snapshot["tables"]["documents"][0]["metadata"] == {
        "meeting_guid": GUID
    }
    assert snapshot["snapshot_sha256"]
    rollback.validate_snapshot(snapshot)


def test_snapshot_integrity_fails_closed_on_tampering():
    snapshot = _snapshot()
    snapshot["cohort"]["guids"][0] = "22222222-2222-4222-8222-222222222222"
    with pytest.raises(rollback.RollbackSafetyError, match="integrity"):
        rollback.validate_snapshot(snapshot)


def test_report_contains_exact_counts_ids_and_field_changes():
    before = _snapshot()
    before["tables"]["documents"] = [{
        "id": "00000000-0000-4000-8000-000000000001",
        "source_identifier": f"escribemeetings_{GUID}",
        "content_hash": "a" * 64,
        "metadata": {"meeting_guid": GUID, "revision": "old"},
        "source_retired_at": None,
        "ingested_at": "2026-08-01T00:00:00+00:00",
    }]
    before = _rehash(before)

    after = copy.deepcopy(before)
    after["phase"] = "after"
    after["snapshot_id"] = "after-snapshot"
    after["captured_at"] = "2026-08-08T10:10:00+00:00"
    after["tables"]["documents"][0]["metadata"]["revision"] = "new"
    after["tables"]["documents"].append({
        "id": "00000000-0000-4000-8000-000000000002",
        "source_identifier": f"escribemeetings_{GUID}",
        "content_hash": "b" * 64,
        "metadata": {"meeting_guid": GUID},
        "source_retired_at": None,
        "ingested_at": "2026-08-08T10:05:00+00:00",
    })
    after = _rehash(after)

    report = rollback.compare_snapshots(before, after)
    documents = report["tables"]["documents"]
    assert documents["before_count"] == 1
    assert documents["after_count"] == 2
    assert documents["before_ids"] == [
        "00000000-0000-4000-8000-000000000001"
    ]
    assert documents["created_ids"] == [
        "00000000-0000-4000-8000-000000000002"
    ]
    assert documents["changed"] == [{
        "id": "00000000-0000-4000-8000-000000000001",
        "fields": ["metadata"],
    }]
    assert report["totals"]["before_count"] == 1
    assert report["totals"]["after_count"] == 2
    assert report["mutation_surface_complete"] is False
    assert report["restoration_supported"] is False
    assert report["evidence_use"] == "partial_scoped_delta_review_only"
    assert report["omitted_mutation_surface"]


def test_review_manifest_is_hashed_partial_and_non_executable():
    before = _snapshot()
    existing_doc = "00000000-0000-4000-8000-000000000001"
    new_doc = "00000000-0000-4000-8000-000000000002"
    before["tables"]["documents"] = [{
        "id": existing_doc,
        "source_identifier": "old-id",
        "content_hash": "a" * 64,
        "metadata": {"revision": "old", "quote": "O'Hare"},
        "source_retired_at": None,
        "ingested_at": "2026-08-01T00:00:00+00:00",
    }]
    before = _rehash(before)
    after = copy.deepcopy(before)
    after["phase"] = "after"
    after["snapshot_id"] = "after-snapshot"
    after["captured_at"] = "2026-08-08T10:10:00+00:00"
    after["tables"]["documents"][0].update({
        "source_identifier": "new-id",
        "content_hash": "c" * 64,
        "metadata": {"revision": "new"},
        "source_retired_at": "2026-08-08T10:05:00+00:00",
    })
    after["tables"]["documents"].append({
        "id": new_doc,
        "source_identifier": "created-id",
        "content_hash": "b" * 64,
        "metadata": {"meeting_guid": GUID},
        "source_retired_at": None,
        "ingested_at": "2026-08-08T10:05:00+00:00",
    })
    after = _rehash(after)

    report = rollback.compare_snapshots(before, after)
    manifest = rollback.render_review_manifest(before, after, report)
    assert manifest["artifact_type"] == (
        "escribe_reconciliation_partial_review_manifest"
    )
    assert manifest["executable"] is False
    assert manifest["mutation_surface_complete"] is False
    assert manifest["restoration_supported"] is False
    assert manifest["omitted_mutation_surface"]
    assert manifest["totals"] == report["totals"]
    assert manifest["tables"] == report["tables"]
    assert manifest["manifest_sha256"]
    unhashed = {
        key: value for key, value in manifest.items()
        if key != "manifest_sha256"
    }
    assert manifest["manifest_sha256"] == rollback._sha256_json(unhashed)
    serialized = json.dumps(manifest).upper()
    assert "COMMIT;" not in serialized
    assert "UPDATE DOCUMENTS" not in serialized
    assert "DELETE FROM" not in serialized


@pytest.mark.parametrize("failure_kind", ["missing", "newly_linked_old_row"])
def test_identity_gaps_remain_partial_non_restorable_evidence(failure_kind):
    before = _snapshot()
    old_id = "00000000-0000-4000-8000-000000000001"
    before["tables"]["meetings"] = [{
        "id": old_id,
        "document_id": None,
        "metadata": {},
        "source_meeting_guid": GUID,
        "source_cancelled_at": None,
        "agenda_item_count": 0,
        "created_at": "2026-08-01T00:00:00+00:00",
    }]
    before = _rehash(before)
    after = copy.deepcopy(before)
    after["phase"] = "after"
    after["snapshot_id"] = "after-snapshot"
    after["captured_at"] = "2026-08-08T10:10:00+00:00"
    if failure_kind == "missing":
        after["tables"]["meetings"] = []
    else:
        after["tables"]["meetings"] = list(before["tables"]["meetings"])
        before["tables"]["meetings"] = []
        before = _rehash(before)
    after = _rehash(after)

    report = rollback.compare_snapshots(before, after)
    assert report["captured_surface_has_identity_gaps"] is True
    assert report["mutation_surface_complete"] is False
    assert report["restoration_supported"] is False
    assert "safe_to_generate_restoration_sql" not in report

    manifest = rollback.render_review_manifest(before, after, report)
    assert manifest["executable"] is False
    assert manifest["captured_surface_has_identity_gaps"] is True
    assert manifest["restoration_supported"] is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mutation_surface_complete", True, "complete surface"),
        ("restoration_supported", True, "restorable"),
    ],
)
def test_review_manifest_rejects_forged_safety_claims(field, value, message):
    before = _snapshot()
    after = _snapshot("after", "2026-08-08T10:10:00+00:00")
    report = rollback.compare_snapshots(before, after)
    report[field] = value

    with pytest.raises(rollback.RollbackSafetyError, match=message):
        rollback.render_review_manifest(before, after, report)


def test_module_has_no_executable_restoration_surface():
    assert not hasattr(rollback, "render_restoration_sql")
    assert not hasattr(rollback, "_restore_row_block")
    assert not hasattr(rollback, "_soft_retire_block")

    source = Path(rollback.__file__).read_text(encoding="utf-8").upper()
    assert "COMMIT;" not in source
    assert "UPDATE DOCUMENTS" not in source
    assert "UPDATE MEETINGS" not in source
    assert "UPDATE AGENDA_ITEMS" not in source
    assert "UPDATE AGENDA_ITEM_ATTACHMENTS" not in source
    assert "DELETE FROM" not in source


def test_after_cli_rejects_removed_restoration_sql_option(tmp_path):
    parser = rollback.build_parser()
    common = [
        "after",
        "--project-ref", CLONE_REF,
        "--before", str(tmp_path / "before.json"),
        "--output", str(tmp_path / "after.json"),
        "--report", str(tmp_path / "report.json"),
        "--review-manifest", str(tmp_path / "review.json"),
    ]

    args = parser.parse_args(common)
    assert args.review_manifest == tmp_path / "review.json"
    assert not hasattr(args, "restoration_sql")
    with pytest.raises(SystemExit):
        parser.parse_args(common + ["--restoration-sql", "rollback.sql"])
