"""Build a NEW local measurement DB from the allowlisted JSONL export.

Only loopback PostgreSQL is allowed. Existing databases are never reused,
overwritten, dropped or migrated. Credentials stay in libpq's private PGPASSFILE.
This is a physical database-size and read-contract check, not a cloud deploy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from export_core import COLUMNS, HELD_ITEM, HERE, file_hash


def validate_export(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("completed") or not manifest.get("source_read_only") or not manifest.get("source_local_only"):
        raise ValueError("Export is incomplete or outside the read-only local contract")
    if tuple(manifest["tables"]) != tuple(COLUMNS):
        raise ValueError("Export relation allowlist changed")
    if manifest["bootstrap_sha256"] != file_hash(HERE / "public-core.sql"):
        raise ValueError("Bootstrap changed since export; review and create a fresh export")
    if manifest["projection_sha256"] != file_hash(HERE / "projection.sql"):
        raise ValueError("Projection changed since export")
    for table, entry in manifest["tables"].items():
        if entry["file"] != f"{table}.jsonl" or tuple(entry["columns"]) != COLUMNS[table]:
            raise ValueError("Export file or field allowlist changed")
        path = directory / entry["file"]
        if path.stat().st_size != entry["bytes"] or file_hash(path) != entry["sha256"]:
            raise ValueError("Export bytes do not match manifest")
    return manifest


def import_export(connection: Any, directory: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    from psycopg2 import sql

    with connection.cursor() as cursor:
        cursor.execute((HERE / "public-core.sql").read_text(encoding="utf-8"))
    with connection.cursor() as cursor:
        for table, entry in manifest["tables"].items():
            statement = sql.SQL("INSERT INTO public.{} ({}) SELECT {} FROM jsonb_populate_recordset(NULL::public.{}, %s::jsonb)").format(
                sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, COLUMNS[table])),
                sql.SQL(",").join(map(sql.Identifier, COLUMNS[table])), sql.Identifier(table))
            count = 0
            batch: list[dict[str, Any]] = []
            with (directory / entry["file"]).open(encoding="utf-8") as stream:
                for line in stream:
                    row = json.loads(line)
                    if tuple(row) != COLUMNS[table]:
                        raise ValueError("Row fields differ from allowlist")
                    batch.append(row)
                    if len(batch) == 500:
                        cursor.execute(statement, (json.dumps(batch, ensure_ascii=False, allow_nan=False),))
                        count += len(batch)
                        batch.clear()
            if batch:
                cursor.execute(statement, (json.dumps(batch, ensure_ascii=False, allow_nan=False),))
                count += len(batch)
            if count != entry["rows"]:
                raise ValueError("Export row count differs from manifest")
        cursor.execute("UPDATE public.meetings m SET agenda_item_count=(SELECT count(*) FROM public.agenda_items a WHERE a.meeting_id=m.id AND a.agenda_source_retired_at IS NULL)")
        comments_from = manifest["policy"]["comments_from"]
        if comments_from:
            cursor.execute("UPDATE public.core_projection_status SET status='partial',detail=%s WHERE feature='public_comments'",
                           (manifest["policy"]["comments_limitation"] + f"; meetings on/after {comments_from}",))
        cursor.execute("INSERT INTO public.core_projection_status(feature,status,detail,checked_at) VALUES ('snapshot','local_export',%s,%s)",
                       (f"Read-only source snapshot; {manifest['total_rows']} public rows. This is not a freshness check against original websites.", manifest["source_snapshot_at"]))
    connection.commit()
    # Vacuum only the new measurement database; never the source restore DB.
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("VACUUM ANALYZE")
        counts: dict[str, int] = {}
        for table, entry in manifest["tables"].items():
            cursor.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table)))
            counts[table] = cursor.fetchone()[0]
            if counts[table] != entry["rows"]:
                raise ValueError("Imported count differs from the consistent source export")
        cursor.execute("SELECT pg_database_size(current_database())")
        database_bytes = cursor.fetchone()[0]
        cursor.execute("""SELECT relname, pg_table_size(c.oid), pg_indexes_size(c.oid), pg_total_relation_size(c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r' ORDER BY relname""")
        storage = {r[0]: {"table_bytes": r[1], "index_bytes": r[2], "total_bytes": r[3]} for r in cursor.fetchall()}
        cursor.execute("SELECT count(*) FROM public.motions WHERE agenda_item_id=%s::uuid", (HELD_ITEM,))
        held_motions = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM public.agenda_items WHERE id=%s::uuid", (HELD_ITEM,))
        held_items = cursor.fetchone()[0]
        searches: dict[str, dict[str, Any]] = {}
        for query, kind in (("housing", "agenda_item"), ("Point Molate", "agenda_item"), ("Point Molate", "vote_explainer")):
            cursor.execute("SELECT count(*) FROM public.search_site(%s,'0660620',%s,50,0)", (query, kind))
            searches[f"{kind}:{query}"] = {"bounded_match_count": cursor.fetchone()[0]}
        cursor.execute("SELECT count(*) FROM public.finance_public_events WHERE activity_date < DATE '2026-01-01' OR activity_date > DATE '2026-11-03' OR scope_key <> '0660620:calendar-2026' OR confidence_score < 0.90")
        invalid_finance = cursor.fetchone()[0]
        cursor.execute("SELECT status,count(*) FROM public.finance_public_coverage GROUP BY status ORDER BY status")
        coverage = dict(cursor.fetchall())
        cursor.execute("SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='public' AND c.contype='f' AND NOT c.convalidated")
        unvalidated_foreign_keys = cursor.fetchone()[0]
        # Verify the role actually receives RLS-filtered SELECT and cannot write.
        cursor.execute("SELECT exists(SELECT 1 FROM pg_roles WHERE rolname='anon')")
        has_anon = cursor.fetchone()[0]
        reader_checks: dict[str, Any] = {"role_exists": has_anon}
        if has_anon:
            cursor.execute("SET ROLE anon")
            try:
                cursor.execute("SELECT count(*) FROM public.agenda_items")
                reader_checks["agenda_count"] = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM public.search_site('housing','0660620','agenda_item',20,0)")
                reader_checks["search_match_count"] = cursor.fetchone()[0]
                cursor.execute("SELECT has_table_privilege(current_user,'public.agenda_items','INSERT'), has_table_privilege(current_user,'public.agenda_items','UPDATE'), has_table_privilege(current_user,'public.agenda_items','DELETE'), has_table_privilege(current_user,'public.agenda_items','TRUNCATE')")
                reader_checks["write_privileges"] = list(cursor.fetchone())
            finally:
                cursor.execute("RESET ROLE")
    return {"measured_at": datetime.now(timezone.utc).isoformat(), "local_only": True,
            "source_modified": False, "physical_database_bytes": database_bytes,
            "public_relation_bytes": sum(row["total_bytes"] for row in storage.values()),
            "tables": storage, "counts": counts, "held_agenda_items_retained": held_items,
            "held_motions_exported": held_motions, "finance_out_of_scope": invalid_finance,
            "finance_coverage_status_counts": coverage, "unvalidated_foreign_keys": unvalidated_foreign_keys,
            "fts_checks": searches, "reader_checks": reader_checks,
            "runtime_limits": "No PostgREST HTTP or managed-provider baseline tested. Missing/partial data is not zero activity."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--host", choices=("127.0.0.1", "::1", "localhost"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--database", default="basic_core_measure_20261004")
    args = parser.parse_args()
    if not re.fullmatch(r"basic_core_measure_\d{8}(?:_\d+)?", args.database):
        parser.error("A new basic_core_measure_YYYYMMDD[_N] database name is required")
    import psycopg2
    from psycopg2 import sql

    connection = None
    try:
        manifest = validate_export(args.export)
        admin = psycopg2.connect(host=args.host, hostaddr="127.0.0.1" if args.host == "localhost" else args.host,
                                port=args.port, dbname="postgres", user=args.user,
                                connect_timeout=10, application_name="richmond-basic-core-local-measure")
        try:
            admin.autocommit = True
            with admin.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s", (args.database,))
                if cursor.fetchone():
                    raise ValueError("Existing database will not be reused or overwritten")
                cursor.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(args.database)))
        finally:
            admin.close()
        connection = psycopg2.connect(host=args.host, hostaddr="127.0.0.1" if args.host == "localhost" else args.host,
                                     port=args.port, dbname=args.database,
                                     user=args.user, connect_timeout=10)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_database_size(current_database())")
            empty_bytes = cursor.fetchone()[0]
        connection.commit()
        report = import_export(connection, args.export, manifest)
        report["empty_database_bytes"] = empty_bytes
        report["added_database_bytes"] = report["physical_database_bytes"] - empty_bytes
        report["new_local_database"] = args.database
        (args.export / "measurement.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"completed": True, "new_local_database": args.database,
                          "database_bytes": report["physical_database_bytes"],
                          "public_relation_bytes": report["public_relation_bytes"]}))
        return 0
    except Exception as exc:
        print(json.dumps({"completed": False, "error_type": type(exc).__name__,
                          "detail": "Local core measurement failed; existing databases were not overwritten"}))
        return 1
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
