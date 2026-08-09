"""Capture and diff partial evidence for bounded eSCRIBE clone exercises.

Reads from the ``documents``, ``meetings``, ``agenda_items``, and
``agenda_item_attachments`` tables for an explicit set of eSCRIBE meeting
GUIDs. Does NOT read date/title fallbacks and does NOT mutate the database.

This is a delta recorder, not a rollback generator. The four queries capture
only selected columns and omit relations that the authoritative loader can
mutate or invalidate. Reports therefore declare the mutation surface
incomplete and no executable restoration SQL can be emitted.

Typical use::

    # The dedicated variable must point at a non-production Supabase clone.
    python src/escribe_reconciliation_rollback.py before \
      --project-ref <clone-ref> --guid <meeting-guid> --output before.json

    # Run the bounded reconciliation separately, then capture its result.
    python src/escribe_reconciliation_rollback.py after \
      --project-ref <clone-ref> --before before.json --output after.json \
      --report report.json --review-manifest review.json

The database URL is read only from ``ESCRIBE_CLONE_DATABASE_URL`` by default,
so credentials do not appear in the process list.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit


PRODUCTION_PROJECT_REF = "ahrwvmizzykyyfavdvfv"
DEFAULT_CITY_FIPS = "0660620"
DEFAULT_DATABASE_URL_ENV = "ESCRIBE_CLONE_DATABASE_URL"
MAX_COHORT_GUIDS = 25
SNAPSHOT_SCHEMA_VERSION = 1
MUTATION_SURFACE_COMPLETE = False
MUTATION_SURFACE_INCOMPLETE_REASON = (
    "The snapshot records selected identity and reconciliation fields from "
    "four core tables only. The authoritative eSCRIBE loader can mutate "
    "additional content fields and related/derivative relations, so these "
    "artifacts support exact scoped delta review but not restoration."
)
OMITTED_MUTATION_SURFACE = (
    "documents: raw_content, raw_text, source_url, mime_type, credibility_tier",
    "meetings: mutable descriptive, timing, attendance, summary, and source fields",
    "agenda_items: title, description, department, staff contact, category, "
    "consent, continuation, resolution, financial, summary, and confidence fields",
    "agenda_item_attachments: filename, URL, title, local path, text content, "
    "extraction status, MIME type, and source document identity fields",
    "meeting_attendance, closed_session_items, motions, votes, "
    "friendly_amendments, and public_comments",
    "agenda_items_embeddings, meetings_embeddings, item_topics, "
    "item_theme_narratives, conflict_flags, and other derived content",
    "data_sync_log, pipeline_journal, and other orchestration audit relations",
)


class RollbackSafetyError(RuntimeError):
    """Raised when clone evidence cannot satisfy its fail-closed contract."""


@dataclass(frozen=True)
class CloneTarget:
    project_ref: str
    host: str
    port: int | None
    database_name: str
    fingerprint: str


TABLE_ORDER = (
    "documents",
    "meetings",
    "agenda_items",
    "agenda_item_attachments",
)

TABLE_CONFIG: dict[str, dict[str, Any]] = {
    "documents": {"created_field": "ingested_at"},
    "meetings": {"created_field": "created_at"},
    "agenda_items": {"created_field": "created_at"},
    "agenda_item_attachments": {"created_field": "created_at"},
}


_DOCUMENT_COHORT = """
    d.city_fips = %s
    AND d.source_type = 'escribemeetings'
    AND (
      d.metadata->>'meeting_guid' = ANY(%s)
      OR d.source_identifier = ANY(%s)
    )
"""

DOCUMENTS_QUERY = f"""
SELECT d.id, d.city_fips, d.source_type, d.source_identifier,
       d.content_hash, d.metadata, d.source_retired_at, d.ingested_at
FROM documents d
WHERE {_DOCUMENT_COHORT}
ORDER BY d.id
"""

_COHORT_MEETINGS_CTE = f"""
WITH cohort_meetings AS (
  SELECT m.id
  FROM meetings m
  WHERE m.city_fips = %s
    AND (
      m.source_meeting_guid = ANY(%s)
      OR m.document_id IN (
        SELECT d.id
        FROM documents d
        WHERE {_DOCUMENT_COHORT}
      )
    )
)
"""

MEETINGS_QUERY = _COHORT_MEETINGS_CTE + """
SELECT m.id, m.city_fips, m.document_id, m.meeting_date, m.meeting_type,
       m.body_id, m.source_meeting_guid, m.source_cancelled_at, m.metadata,
       m.agenda_item_count, m.created_at
FROM meetings m
JOIN cohort_meetings cohort ON cohort.id = m.id
ORDER BY m.id
"""

AGENDA_ITEMS_QUERY = _COHORT_MEETINGS_CTE + """
SELECT ai.id, ai.meeting_id, ai.item_number,
       ai.agenda_source_authority, ai.agenda_source_revision_sha256,
       ai.agenda_source_retired_at, ai.created_at
FROM agenda_items ai
JOIN cohort_meetings cohort ON cohort.id = ai.meeting_id
ORDER BY ai.id
"""

ATTACHMENTS_QUERY = _COHORT_MEETINGS_CTE + """
SELECT aia.id, aia.agenda_item_id, aia.document_id,
       aia.source_revision_sha256, aia.source_content_sha256,
       aia.source_retired_at, aia.created_at
FROM agenda_item_attachments aia
JOIN agenda_items ai ON ai.id = aia.agenda_item_id
JOIN cohort_meetings cohort ON cohort.id = ai.meeting_id
ORDER BY aia.id
"""


def validate_clone_target(project_ref: str, database_url: str) -> CloneTarget:
    """Prove that a URL names the requested non-production Supabase project."""
    ref = (project_ref or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9]{20}", ref):
        raise RollbackSafetyError(
            "Supabase project ref must be exactly 20 lowercase letters/digits"
        )
    if ref == PRODUCTION_PROJECT_REF:
        raise RollbackSafetyError("Production project ref is a hard no-go")

    raw_url = (database_url or "").strip()
    if not raw_url:
        raise RollbackSafetyError("Clone database URL is missing")
    if PRODUCTION_PROJECT_REF in unquote(raw_url).lower():
        raise RollbackSafetyError("Database URL identifies the production project")

    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RollbackSafetyError("Clone URL must use postgres:// or postgresql://")
    host = (parsed.hostname or "").lower()
    username = unquote(parsed.username or "").lower()
    if not (
        host.endswith(".supabase.co")
        or host.endswith(".supabase.com")
    ):
        raise RollbackSafetyError("Target is not a Supabase database host")

    direct_host_match = host.startswith(f"db.{ref}.")
    pooler_user_match = username == f"postgres.{ref}"
    if not (direct_host_match or pooler_user_match):
        raise RollbackSafetyError(
            "Clone URL does not prove the requested project ref in its "
            "direct host or pooler username"
        )

    database_name = (parsed.path or "/postgres").lstrip("/") or "postgres"
    safe_target = f"{ref}|{host}|{parsed.port or ''}|{database_name}"
    return CloneTarget(
        project_ref=ref,
        host=host,
        port=parsed.port,
        database_name=database_name,
        fingerprint=hashlib.sha256(safe_target.encode("utf-8")).hexdigest(),
    )


def normalize_guids(guids: Iterable[str]) -> list[str]:
    """Validate a non-empty, duplicate-free, bounded GUID cohort."""
    raw = [str(value or "").strip().lower() for value in guids]
    if not raw:
        raise RollbackSafetyError("At least one explicit eSCRIBE GUID is required")
    if len(raw) > MAX_COHORT_GUIDS:
        raise RollbackSafetyError(
            f"Cohort has {len(raw)} GUIDs; maximum is {MAX_COHORT_GUIDS}"
        )
    if any(not value for value in raw):
        raise RollbackSafetyError("Empty GUIDs are not allowed")
    if len(set(raw)) != len(raw):
        raise RollbackSafetyError("Duplicate GUIDs are not allowed")
    try:
        normalized = [str(uuid.UUID(value)) for value in raw]
    except ValueError as exc:
        raise RollbackSafetyError(f"Invalid eSCRIBE GUID: {exc}") from exc
    return sorted(normalized)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RollbackSafetyError("Non-finite numeric value in snapshot")
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _fetch_rows(cur, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _query_params(city_fips: str, guids: list[str]) -> tuple[Any, ...]:
    source_ids = [f"escribemeetings_{guid}" for guid in guids]
    return city_fips, guids, city_fips, guids, source_ids


def _validate_unique_ids(table: str, rows: list[dict[str, Any]]) -> None:
    ids = [str(row.get("id") or "") for row in rows]
    if any(not row_id for row_id in ids):
        raise RollbackSafetyError(f"{table} snapshot contains a row without id")
    try:
        canonical_ids = [str(uuid.UUID(row_id)) for row_id in ids]
    except ValueError as exc:
        raise RollbackSafetyError(
            f"{table} snapshot contains a non-UUID id"
        ) from exc
    if canonical_ids != ids:
        raise RollbackSafetyError(f"{table} snapshot ids are not canonical UUIDs")
    if len(ids) != len(set(ids)):
        raise RollbackSafetyError(f"{table} snapshot contains duplicate ids")


def capture_snapshot(
    conn,
    target: CloneTarget,
    guids: Iterable[str],
    *,
    phase: str,
    city_fips: str = DEFAULT_CITY_FIPS,
) -> dict[str, Any]:
    """Take one repeatable-read, read-only snapshot for an exact GUID cohort."""
    if phase not in {"before", "after"}:
        raise RollbackSafetyError("Snapshot phase must be 'before' or 'after'")
    if city_fips != DEFAULT_CITY_FIPS:
        raise RollbackSafetyError(
            f"Richmond clone captures require city_fips={DEFAULT_CITY_FIPS}"
        )
    cohort = normalize_guids(guids)
    source_ids = [f"escribemeetings_{guid}" for guid in cohort]
    tables: dict[str, list[dict[str, Any]]] = {}

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            clock_rows = _fetch_rows(
                cur,
                "SELECT clock_timestamp() AS captured_at, "
                "current_database() AS database_name",
                (),
            )
            if len(clock_rows) != 1:
                raise RollbackSafetyError("Could not capture clone database clock")

            documents = _fetch_rows(
                cur,
                DOCUMENTS_QUERY,
                (city_fips, cohort, source_ids),
            )
            cohort_params = _query_params(city_fips, cohort)
            meetings = _fetch_rows(cur, MEETINGS_QUERY, cohort_params)
            agenda_items = _fetch_rows(cur, AGENDA_ITEMS_QUERY, cohort_params)
            attachments = _fetch_rows(cur, ATTACHMENTS_QUERY, cohort_params)
            raw_tables = {
                "documents": documents,
                "meetings": meetings,
                "agenda_items": agenda_items,
                "agenda_item_attachments": attachments,
            }
            for table in TABLE_ORDER:
                safe_rows = [_json_safe(row) for row in raw_tables[table]]
                _validate_unique_ids(table, safe_rows)
                tables[table] = sorted(safe_rows, key=lambda row: str(row["id"]))
            captured_at = _json_safe(clock_rows[0]["captured_at"])
            database_name = str(clock_rows[0]["database_name"])
    finally:
        # Capture is evidence collection only. End the read-only transaction
        # even if a query or serialization check fails.
        conn.rollback()

    snapshot: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "phase": phase,
        "snapshot_id": str(uuid.uuid4()),
        "captured_at": captured_at,
        "city_fips": city_fips,
        "target": {
            "project_ref": target.project_ref,
            "host": target.host,
            "port": target.port,
            "database_name": database_name,
            "target_fingerprint": target.fingerprint,
        },
        "cohort": {
            "guids": cohort,
            "guid_count": len(cohort),
            "guid_sha256": _sha256_json(cohort),
        },
        "tables": tables,
    }
    snapshot["snapshot_sha256"] = _sha256_json(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise RollbackSafetyError("Unsupported rollback snapshot schema version")
    stored_hash = snapshot.get("snapshot_sha256")
    unhashed = {key: value for key, value in snapshot.items()
                if key != "snapshot_sha256"}
    if not stored_hash or stored_hash != _sha256_json(unhashed):
        raise RollbackSafetyError("Snapshot integrity hash does not match")
    ref = str((snapshot.get("target") or {}).get("project_ref") or "")
    if ref == PRODUCTION_PROJECT_REF:
        raise RollbackSafetyError("Production snapshots are forbidden")
    if snapshot.get("city_fips") != DEFAULT_CITY_FIPS:
        raise RollbackSafetyError("Snapshot is not scoped to Richmond city_fips")
    cohort = normalize_guids((snapshot.get("cohort") or {}).get("guids") or [])
    if cohort != (snapshot.get("cohort") or {}).get("guids"):
        raise RollbackSafetyError("Snapshot cohort is not canonical")
    tables = snapshot.get("tables") or {}
    if set(tables) != set(TABLE_ORDER):
        raise RollbackSafetyError("Snapshot table set is incomplete or unexpected")
    for table in TABLE_ORDER:
        if not isinstance(tables[table], list):
            raise RollbackSafetyError(f"Snapshot {table} rows are not a list")
        _validate_unique_ids(table, tables[table])


def _parse_timestamp(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise RollbackSafetyError(f"Invalid timestamp for {label}: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def compare_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Return exact per-table counts, IDs, field deltas, and unsafe gaps."""
    validate_snapshot(before)
    validate_snapshot(after)
    if before.get("phase") != "before" or after.get("phase") != "after":
        raise RollbackSafetyError("Expected before/after snapshot phases")
    for field in ("project_ref", "target_fingerprint"):
        if before["target"].get(field) != after["target"].get(field):
            raise RollbackSafetyError(f"Snapshot target mismatch: {field}")
    if before.get("city_fips") != after.get("city_fips"):
        raise RollbackSafetyError("Snapshot city_fips values differ")
    if before.get("cohort") != after.get("cohort"):
        raise RollbackSafetyError("Snapshot GUID cohorts differ")

    before_time = _parse_timestamp(before["captured_at"], "before.captured_at")
    after_time = _parse_timestamp(after["captured_at"], "after.captured_at")
    if after_time < before_time:
        raise RollbackSafetyError("After snapshot predates before snapshot")

    table_reports: dict[str, Any] = {}
    captured_surface_has_identity_gaps = False
    totals = {
        "before_count": 0,
        "after_count": 0,
        "created_count": 0,
        "missing_count": 0,
        "changed_count": 0,
        "unsafe_after_only_count": 0,
    }
    for table in TABLE_ORDER:
        before_rows = {str(row["id"]): row for row in before["tables"][table]}
        after_rows = {str(row["id"]): row for row in after["tables"][table]}
        before_ids = sorted(before_rows)
        after_ids = sorted(after_rows)
        missing_ids = sorted(set(before_ids) - set(after_ids))
        after_only_ids = sorted(set(after_ids) - set(before_ids))
        created_ids: list[str] = []
        unsafe_after_only_ids: list[str] = []
        created_field = TABLE_CONFIG[table]["created_field"]
        for row_id in after_only_ids:
            created_value = after_rows[row_id].get(created_field)
            try:
                created_at = _parse_timestamp(
                    created_value, f"{table}.{row_id}.{created_field}"
                )
            except RollbackSafetyError:
                unsafe_after_only_ids.append(row_id)
                continue
            if created_at >= before_time:
                created_ids.append(row_id)
            else:
                # The row predates capture and only became cohort-visible
                # during the run. Its prior values were not captured, so an
                # automatic rollback would risk destroying legacy/minutes data.
                unsafe_after_only_ids.append(row_id)

        changed: list[dict[str, Any]] = []
        for row_id in sorted(set(before_ids) & set(after_ids)):
            old = before_rows[row_id]
            new = after_rows[row_id]
            fields = sorted(
                field for field in set(old) | set(new)
                if old.get(field) != new.get(field)
            )
            if fields:
                changed.append({"id": row_id, "fields": fields})

        report = {
            "before_count": len(before_ids),
            "before_ids": before_ids,
            "after_count": len(after_ids),
            "after_ids": after_ids,
            "created_count": len(created_ids),
            "created_ids": created_ids,
            "missing_count": len(missing_ids),
            "missing_ids": missing_ids,
            "changed_count": len(changed),
            "changed": changed,
            "unsafe_after_only_count": len(unsafe_after_only_ids),
            "unsafe_after_only_ids": unsafe_after_only_ids,
        }
        table_reports[table] = report
        for total_field in totals:
            totals[total_field] += report[total_field]
        if missing_ids or unsafe_after_only_ids:
            captured_surface_has_identity_gaps = True

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "project_ref": before["target"]["project_ref"],
        "target_fingerprint": before["target"]["target_fingerprint"],
        "city_fips": before["city_fips"],
        "cohort": before["cohort"],
        "before_snapshot_id": before["snapshot_id"],
        "before_snapshot_sha256": before["snapshot_sha256"],
        "before_captured_at": before["captured_at"],
        "after_snapshot_id": after["snapshot_id"],
        "after_snapshot_sha256": after["snapshot_sha256"],
        "after_captured_at": after["captured_at"],
        "totals": totals,
        "tables": table_reports,
        "mutation_surface_complete": MUTATION_SURFACE_COMPLETE,
        "restoration_supported": False,
        "evidence_use": "partial_scoped_delta_review_only",
        "captured_surface_has_identity_gaps": (
            captured_surface_has_identity_gaps
        ),
        "partial_capture_reason": MUTATION_SURFACE_INCOMPLETE_REASON,
        "omitted_mutation_surface": list(OMITTED_MUTATION_SURFACE),
    }


def render_review_manifest(
    before: dict[str, Any],
    after: dict[str, Any],
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a hashed, non-executable manifest for human delta review."""
    report = report or compare_snapshots(before, after)
    if report.get("mutation_surface_complete") is not False:
        raise RollbackSafetyError(
            "Partial capture must never be represented as a complete surface"
        )
    if report.get("restoration_supported") is not False:
        raise RollbackSafetyError(
            "Partial capture must never be represented as restorable"
        )
    manifest: dict[str, Any] = {
        "artifact_type": "escribe_reconciliation_partial_review_manifest",
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "executable": False,
        "mutation_surface_complete": False,
        "restoration_supported": False,
        "evidence_use": "partial_scoped_delta_review_only",
        "captured_surface_has_identity_gaps": report[
            "captured_surface_has_identity_gaps"
        ],
        "partial_capture_reason": MUTATION_SURFACE_INCOMPLETE_REASON,
        "omitted_mutation_surface": list(OMITTED_MUTATION_SURFACE),
        "project_ref": report["project_ref"],
        "target_fingerprint": report["target_fingerprint"],
        "cohort": report["cohort"],
        "before_snapshot_sha256": before["snapshot_sha256"],
        "after_snapshot_sha256": after["snapshot_sha256"],
        "report_sha256": _sha256_json(report),
        "totals": report["totals"],
        "tables": report["tables"],
        "instruction": (
            "Review exact deltas only. Do not execute this JSON and do not "
            "infer rollback safety from it."
        ),
    }
    manifest["manifest_sha256"] = _sha256_json(manifest)
    return manifest


def read_snapshot(path: Path) -> dict[str, Any]:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    validate_snapshot(snapshot)
    return snapshot


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _connect(database_url: str):
    import psycopg2

    return psycopg2.connect(
        database_url,
        connect_timeout=10,
        application_name="richmond_escribe_delta_capture",
        sslmode="require",
    )


def _resolve_target(args) -> tuple[CloneTarget, str]:
    database_url = os.environ.get(args.database_url_env, "")
    target = validate_clone_target(args.project_ref, database_url)
    return target, database_url


def _print_snapshot_counts(snapshot: dict[str, Any]) -> None:
    print(
        f"{snapshot['phase']} snapshot {snapshot['snapshot_id']} "
        f"for {snapshot['cohort']['guid_count']} GUID(s)"
    )
    for table in TABLE_ORDER:
        ids = [str(row["id"]) for row in snapshot["tables"][table]]
        print(f"  {table}: count={len(ids)} ids={','.join(ids) or '(none)'}")


def _print_report(report: dict[str, Any]) -> None:
    print(
        "reconciliation delta: "
        f"before={report['totals']['before_count']} "
        f"after={report['totals']['after_count']} "
        f"created={report['totals']['created_count']} "
        f"missing={report['totals']['missing_count']} "
        f"changed={report['totals']['changed_count']}"
    )
    for table in TABLE_ORDER:
        row = report["tables"][table]
        print(
            f"  {table}: before={row['before_count']} after={row['after_count']} "
            f"created={row['created_ids']} missing={row['missing_ids']} "
            f"changed={[change['id'] for change in row['changed']]} "
            f"unsafe_after_only={row['unsafe_after_only_ids']}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bounded eSCRIBE partial delta capture (clones only)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    before = subparsers.add_parser("before", help="capture the pre-run snapshot")
    before.add_argument("--project-ref", required=True)
    before.add_argument("--guid", action="append", required=True,
                        help=f"eSCRIBE meeting GUID; repeat up to {MAX_COHORT_GUIDS}")
    before.add_argument("--output", type=Path, required=True)
    before.add_argument("--database-url-env", default=DEFAULT_DATABASE_URL_ENV,
                        help="environment variable containing the clone URL")

    after = subparsers.add_parser(
        "after", help="capture post-run state and emit partial delta evidence"
    )
    after.add_argument("--project-ref", required=True)
    after.add_argument("--before", type=Path, required=True)
    after.add_argument("--output", type=Path, required=True)
    after.add_argument("--report", type=Path, required=True)
    after.add_argument("--review-manifest", type=Path, required=True)
    after.add_argument("--database-url-env", default=DEFAULT_DATABASE_URL_ENV,
                       help="environment variable containing the clone URL")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        target, database_url = _resolve_target(args)
        if args.command == "before":
            guids = normalize_guids(args.guid)
            with _connect(database_url) as conn:
                snapshot = capture_snapshot(
                    conn,
                    target,
                    guids,
                    phase="before",
                    city_fips=DEFAULT_CITY_FIPS,
                )
            write_json(args.output, snapshot)
            _print_snapshot_counts(snapshot)
            print(f"wrote {args.output}")
            return 0

        before = read_snapshot(args.before)
        if before["target"]["project_ref"] != target.project_ref:
            raise RollbackSafetyError(
                "--project-ref does not match the before snapshot"
            )
        if before["target"]["target_fingerprint"] != target.fingerprint:
            raise RollbackSafetyError(
                "Clone connection target does not match the before snapshot"
            )
        with _connect(database_url) as conn:
            after = capture_snapshot(
                conn,
                target,
                before["cohort"]["guids"],
                phase="after",
                city_fips=before["city_fips"],
            )
        write_json(args.output, after)
        report = compare_snapshots(before, after)
        write_json(args.report, report)
        review_manifest = render_review_manifest(before, after, report)
        write_json(args.review_manifest, review_manifest)
        _print_snapshot_counts(after)
        _print_report(report)
        print(
            "partial capture only: mutation_surface_complete=false; "
            "restoration_supported=false"
        )
        print(f"wrote {args.output}, {args.report}, {args.review_manifest}")
        return 0
    except (RollbackSafetyError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
