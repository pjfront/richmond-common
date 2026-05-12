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

# Meetings
from .meetings import load_meeting_to_db

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
)

# Elections
from .elections import (
    load_elections_to_db,
    load_election_candidates_to_db,
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

    load_cmd = sub.add_parser("load", help="Load extracted meeting JSON into database")
    load_cmd.add_argument("json_file", help="Path to extracted meeting JSON file")
    load_cmd.add_argument("--city-fips", default=RICHMOND_FIPS, help="City FIPS code (default: Richmond CA)")

    load_all_cmd = sub.add_parser("load-all", help="Load all meeting JSONs from a directory")
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
        conn = get_connection()
        with open(args.json_file) as f:
            data = json.load(f)
        meeting_id = load_meeting_to_db(conn, data, city_fips=args.city_fips)
        print(f"Loaded meeting {data.get('meeting_date')} -> {meeting_id}")
        conn.close()

    elif args.command == "load-all":
        conn = get_connection()
        json_files = sorted(globmod.glob(os.path.join(args.directory, "*.json")))
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
                meeting_id = load_meeting_to_db(conn, data, city_fips=args.city_fips)
                print(f"  Loaded {data['meeting_date']} ({os.path.basename(fpath)}) -> {meeting_id}")
                loaded += 1
            except Exception as e:
                print(f"  ERROR loading {os.path.basename(fpath)}: {e}")
                conn.rollback()
                skipped += 1
        print(f"\nDone: {loaded} meetings loaded, {skipped} skipped.")
        conn.close()

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
