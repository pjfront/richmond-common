"""
Richmond Common — Database Access Layer (Phase 2.1 split).

This package re-exports all functions and constants previously defined in
src/db.py so existing callers (`from db import X`) continue to work
unchanged. Each domain lives in its own submodule:

    db._core         — connection management, sanitize_text, init/migration
    db.documents     — ingest_document, save_extraction_run
    db.officials     — official resolution, alias mapping, body type
    db.meetings      — load_meeting_to_db
    db.contributions — load_contributions_to_db (+ private helpers)
    db.expenditures  — load_expenditures_to_db
    db.form700       — load_form700_to_db
    db.scan_runs     — create_scan_run / complete_scan_run / fail_scan_run
    db.sync_logs     — sync log lifecycle
    db.journal       — pipeline journal helpers
    db.decisions     — decision queue helpers
    db.flags         — conflict flag helpers
    db.entities      — organizations, links, behested, lobbyists, graph
    db.elections     — election cycles + candidates

Tests that patch helper internals should now patch them at their
definition site, e.g. `patch("db.officials.ensure_official")` rather
than `patch("db.ensure_official")`. See Phase 2.1 commit notes.
"""
from __future__ import annotations

from datetime import datetime
import re

# Core & connection
from ._core import (
    RICHMOND_FIPS,
    sanitize_text,
    get_connection,
    is_connection_alive,
    init_schema,
    run_migration,
    logger,
)

# Documents
from .documents import (
    ingest_document,
    ingest_document_with_status,
    save_extraction_run,
)

# Officials & body resolution
from .officials import (
    FUZZY_MATCH_THRESHOLD,
    _normalize_name,
    _load_alias_map,
    _fuzzy_find_official,
    ensure_official,
    _default_role_for_body_type,
    _resolve_body_type,
    resolve_body_id,
)

# Meetings. Keep the generic loader export for minutes/transcript call sites;
# documented eSCRIBE agenda CLIs below must use the provenance-gated wrapper.
from .meetings import (
    load_meeting_to_db as _load_meeting_to_db,
    retire_escribe_agenda,
)

load_meeting_to_db = _load_meeting_to_db

# Contributions / expenditures / form700
from .contributions import (
    _parse_contribution_date,
    _contribution_type_from_record,
    load_contributions_to_db,
)
from .expenditures import load_expenditures_to_db
from .form700 import load_form700_to_db

# Scan runs / sync logs / journal / decisions / flags
from .scan_runs import (
    create_scan_run,
    complete_scan_run,
    fail_scan_run,
)
from .sync_logs import (
    cleanup_stale_sync_logs,
    create_sync_log,
    complete_sync_log,
)
from .source_change_jobs import (
    claim_source_change_job,
    get_source_change_job,
    mark_source_change_base_completed,
    retry_source_change_job,
    continue_source_change_job,
    complete_source_change_job,
    get_change_sync_log,
)
from .journal import (
    write_journal_entry,
    get_journal_entries,
    get_recent_step_metrics,
)
from .decisions import (
    insert_pending_decision,
    update_decision_status,
    query_pending_decisions,
    query_resolved_decisions,
    count_decisions_by_severity,
)
from .flags import (
    save_conflict_flag,
    supersede_flags_for_meeting,
)

# Entities
from .entities import (
    load_organizations_to_db,
    load_entity_links_to_db,
    resolve_entity_link_ids,
    load_behested_to_db,
    load_lobbyists_to_db,
    load_entity_graph,
    load_org_reverse_map,
    load_city_contracts_to_db,
    match_contract_entities,
    classify_influence_patterns,
)

# Elections
from .elections import (
    load_elections_to_db,
    load_election_candidates_to_db,
)


AUTHORITATIVE_ESCRIBE_IDENTITY_KEY = "_authoritative_escribe_source"


class AuthoritativeEscribeIdentityError(ValueError):
    """Raised when a legacy eSCRIBE load lacks source revision identity."""


def _one_identity_value(label: str, *candidates) -> str | None:
    values = {
        str(value).strip()
        for value in candidates
        if value is not None and str(value).strip()
    }
    if len(values) > 1:
        raise AuthoritativeEscribeIdentityError(
            f"Conflicting authoritative eSCRIBE {label} values"
        )
    return next(iter(values), None)


def require_authoritative_escribe_identity(
    data: dict,
    *,
    source_meeting_guid: str | None = None,
    agenda_revision_sha256: str | None = None,
    source_observed_at: str | None = None,
) -> dict[str, str]:
    """Validate the source identity required for an eSCRIBE agenda write.

    The pre-cutover loaders identified meetings by date/type and could create
    unowned legacy rows. A caller must now provide an exact meeting GUID, the
    normalized agenda revision SHA-256, and a timezone-aware observation time,
    either explicitly or in ``_authoritative_escribe_source``.
    """
    if not isinstance(data, dict):
        raise AuthoritativeEscribeIdentityError(
            "Authoritative eSCRIBE meeting payload must be an object"
        )
    embedded = data.get(AUTHORITATIVE_ESCRIBE_IDENTITY_KEY, {})
    if embedded is None:
        embedded = {}
    if not isinstance(embedded, dict):
        raise AuthoritativeEscribeIdentityError(
            f"{AUTHORITATIVE_ESCRIBE_IDENTITY_KEY} must be an object"
        )

    meeting_guid = _one_identity_value(
        "meeting GUID",
        source_meeting_guid,
        embedded.get("meeting_guid"),
    )
    revision = _one_identity_value(
        "agenda revision",
        (
            str(agenda_revision_sha256).lower()
            if agenda_revision_sha256 is not None
            else None
        ),
        (
            str(embedded.get("agenda_revision_sha256")).lower()
            if embedded.get("agenda_revision_sha256") is not None
            else None
        ),
    )
    observed_at = _one_identity_value(
        "observation time",
        source_observed_at,
        embedded.get("observed_at"),
    )

    missing = [
        label
        for label, value in (
            ("meeting_guid", meeting_guid),
            ("agenda_revision_sha256", revision),
            ("observed_at", observed_at),
        )
        if not value
    ]
    if missing:
        raise AuthoritativeEscribeIdentityError(
            "Legacy eSCRIBE database loading is disabled without authoritative "
            f"source identity: missing {', '.join(missing)}"
        )
    if len(meeting_guid) > 200:
        raise AuthoritativeEscribeIdentityError(
            "Authoritative eSCRIBE meeting GUID is malformed"
        )
    if re.fullmatch(r"[0-9a-fA-F]{64}", revision) is None:
        raise AuthoritativeEscribeIdentityError(
            "Authoritative eSCRIBE agenda revision must be a SHA-256 hex digest"
        )
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthoritativeEscribeIdentityError(
            "Authoritative eSCRIBE observation time is malformed"
        ) from exc
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise AuthoritativeEscribeIdentityError(
            "Authoritative eSCRIBE observation time must include a timezone"
        )

    return {
        "meeting_guid": meeting_guid,
        "agenda_revision_sha256": revision.lower(),
        "observed_at": observed_at,
    }


def load_authoritative_escribe_agenda(
    conn,
    data: dict,
    *,
    document_id=None,
    city_fips: str = RICHMOND_FIPS,
    body_id=None,
    agenda_url: str | None = None,
    source_meeting_guid: str | None = None,
    agenda_revision_sha256: str | None = None,
    source_observed_at: str | None = None,
    commit: bool = True,
):
    """Load an eSCRIBE agenda only through the post-cutover identity fence."""
    identity = require_authoritative_escribe_identity(
        data,
        source_meeting_guid=source_meeting_guid,
        agenda_revision_sha256=agenda_revision_sha256,
        source_observed_at=source_observed_at,
    )
    return _load_meeting_to_db(
        conn,
        data,
        document_id=document_id,
        city_fips=city_fips,
        body_id=body_id,
        agenda_url=agenda_url,
        authoritative_agenda_revision=identity["agenda_revision_sha256"],
        source_meeting_guid=identity["meeting_guid"],
        source_observed_at=identity["observed_at"],
        commit=commit,
    )


# ── CLI ──────────────────────────────────────────────────────

def main():
    """CLI for database operations."""
    import argparse
    import glob as globmod
    import json
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Richmond Common — Database Management")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize database schema")

    load_cmd = sub.add_parser(
        "load",
        help="Load an identity-fenced eSCRIBE agenda JSON into database",
    )
    load_cmd.add_argument("json_file", help="Path to extracted meeting JSON file")
    load_cmd.add_argument("--city-fips", default=RICHMOND_FIPS, help="City FIPS code (default: Richmond CA)")
    load_cmd.add_argument("--source-meeting-guid")
    load_cmd.add_argument("--agenda-revision-sha256")
    load_cmd.add_argument("--source-observed-at")
    load_cmd.add_argument("--agenda-url")

    load_all_cmd = sub.add_parser(
        "load-all",
        help=(
            "Load identity-fenced eSCRIBE agenda JSONs; every file must embed "
            f"{AUTHORITATIVE_ESCRIBE_IDENTITY_KEY}"
        ),
    )
    load_all_cmd.add_argument("directory", help="Directory containing extracted meeting JSON files")
    load_all_cmd.add_argument("--city-fips", default=RICHMOND_FIPS, help="City FIPS code (default: Richmond CA)")

    load_contribs_cmd = sub.add_parser("load-contributions", help="Load campaign contributions JSON")
    load_contribs_cmd.add_argument("json_file", help="Path to combined contributions JSON")
    load_contribs_cmd.add_argument("--city-fips", default=RICHMOND_FIPS, help="City FIPS code (default: Richmond CA)")

    migrate_cmd = sub.add_parser("migrate", help="Run database migrations")
    migrate_cmd.add_argument("migration_file", nargs="?", help="Specific migration file (default: run all in src/migrations/)")

    args = parser.parse_args()

    if args.command == "init":
        conn = get_connection()
        init_schema(conn)
        print("Schema initialized successfully.")
        conn.close()

    elif args.command == "load":
        with open(args.json_file) as f:
            data = json.load(f)
        identity = require_authoritative_escribe_identity(
            data,
            source_meeting_guid=args.source_meeting_guid,
            agenda_revision_sha256=args.agenda_revision_sha256,
            source_observed_at=args.source_observed_at,
        )
        conn = get_connection()
        try:
            meeting_id = load_authoritative_escribe_agenda(
                conn,
                data,
                city_fips=args.city_fips,
                agenda_url=args.agenda_url,
                source_meeting_guid=identity["meeting_guid"],
                agenda_revision_sha256=identity["agenda_revision_sha256"],
                source_observed_at=identity["observed_at"],
            )
            print(f"Loaded meeting {data.get('meeting_date')} -> {meeting_id}")
        finally:
            conn.close()

    elif args.command == "load-all":
        json_files = sorted(globmod.glob(os.path.join(args.directory, "*.json")))
        preflight = []
        loaded = 0
        skipped = 0
        for fpath in json_files:
            with open(fpath) as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    print(f"  SKIP (invalid JSON): {fpath}")
                    skipped += 1
                    continue
            if "meeting_date" not in data:
                print(f"  SKIP (no meeting_date): {os.path.basename(fpath)}")
                skipped += 1
                continue
            try:
                require_authoritative_escribe_identity(data)
            except AuthoritativeEscribeIdentityError as exc:
                raise AuthoritativeEscribeIdentityError(
                    f"Refusing load-all before any writes; "
                    f"{os.path.basename(fpath)}: {exc}"
                ) from exc
            preflight.append((fpath, data))

        conn = get_connection()
        try:
            for fpath, data in preflight:
                try:
                    meeting_id = load_authoritative_escribe_agenda(
                        conn,
                        data,
                        city_fips=args.city_fips,
                        agenda_url=data.get("agenda_url"),
                    )
                    print(f"  Loaded {data['meeting_date']} ({os.path.basename(fpath)}) -> {meeting_id}")
                    loaded += 1
                except Exception as e:
                    print(f"  ERROR loading {os.path.basename(fpath)}: {e}")
                    conn.rollback()
                    skipped += 1
        finally:
            conn.close()
        print(f"\nDone: {loaded} meetings loaded, {skipped} skipped.")

    elif args.command == "load-contributions":
        conn = get_connection()
        with open(args.json_file) as f:
            records = json.load(f)
        print(f"Loading {len(records)} contribution records...")
        stats = load_contributions_to_db(conn, records, city_fips=args.city_fips)
        print(f"\nDone:")
        print(f"  Donors created:        {stats['donors']}")
        print(f"  Committees created:     {stats['committees']}")
        print(f"  Contributions inserted: {stats['contributions']}")
        print(f"  Records skipped:        {stats['skipped']}")
        conn.close()

    elif args.command == "migrate":
        conn = get_connection()
        if args.migration_file:
            print(f"Running migration: {args.migration_file}")
            run_migration(conn, args.migration_file)
            print("Migration complete.")
        else:
            migrations_dir = Path(__file__).parent.parent / "migrations"
            if not migrations_dir.exists():
                print("No migrations directory found.")
            else:
                migration_files = sorted(migrations_dir.glob("*.sql"))
                if not migration_files:
                    print("No migration files found.")
                else:
                    for mf in migration_files:
                        print(f"Running: {mf.name}")
                        run_migration(conn, str(mf))
                    print(f"\n{len(migration_files)} migration(s) applied.")
        conn.close()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
