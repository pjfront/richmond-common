"""Export the basic public projection from an already restored LOCAL database.

Reads explicit structured civic rows and finance_public_* source projections.
Does NOT read documents/raw payloads, generated narratives, embeddings, donors,
private operator/subscriber/auth tables, configuration or provider credentials.
One repeatable-read, read-only source transaction; no target database connection.
Credentials use libpq's private PGPASSFILE, never a command-line connection URL.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from uuid import UUID

HERE = Path(__file__).resolve().parent
HELD_ITEM = "9cf375c8-edc1-413c-8ee0-6485348fbc6f"
HELD_MEETING = "5f560013-daea-499a-8ecd-ca1a089c8a0c"

# This separate field allowlist makes a future source-column addition fail closed.
# Names on public meeting/filing records are retained; direct contact/address
# fields and private submissions/payloads are not part of the export.
COLUMNS: dict[str, tuple[str, ...]] = {
    "bodies": tuple("id city_fips name body_type short_name parent_body_id is_elected num_seats meeting_schedule is_active created_at".split()),
    "officials": tuple("id city_fips name normalized_name role seat party_affiliation term_start term_end is_current created_at".split()),
    "meetings": tuple("id city_fips document_id body_id meeting_date meeting_type call_to_order_time adjournment_time presiding_officer minutes_url agenda_url video_url adjourned_in_memory_of next_meeting_date source_cancelled_at source_meeting_guid created_at".split()),
    "agenda_items": tuple("id meeting_id item_number title description department category is_consent_calendar was_pulled_from_consent resolution_number financial_amount continued_from continued_to topic_label proceeding_type agenda_source_authority agenda_source_revision_sha256 agenda_source_retired_at created_at".split()),
    "motions": tuple("id agenda_item_id motion_type motion_text moved_by seconded_by result vote_tally resolution_number sequence_number source created_at".split()),
    "votes": tuple("id motion_id official_id official_name official_role vote_choice source".split()),
    "meeting_attendance": tuple("id meeting_id official_id body_id status notes".split()),
    "topics": tuple("id city_fips slug name description primary_category status merged_into_id color_classes keywords created_at updated_at".split()),
    "item_topics": tuple("id agenda_item_id topic_id confidence source created_at".split()),
    "closed_session_items": tuple("id meeting_id item_number legal_authority description parties reportable_action".split()),
    "public_comments": tuple("id meeting_id agenda_item_id speaker_name method comment_type source confidence name_confidence extracted_at created_at city_fips".split()),
    "finance_public_events": tuple("event_key scope_key event_kind donor_name donor_fppc_id recipient_name recipient_fppc_id reporting_filer_name reporting_filer_fppc_id amount amount_kind activity_date support_oppose candidate_name measure_name election_date filing_ids source_urls source_url extracted_at source_tier confidence_score reconciliation_status".split()),
    "finance_public_coverage": tuple("source form_type scope_key status checked_at activity_from activity_through filing_count assertion_count pending_count limitations source_url extracted_at source_tier confidence_score".split()),
}


def projection_queries() -> dict[str, str]:
    contents = (HERE / "projection.sql").read_text(encoding="utf-8")
    sections = re.split(r"^-- relation: ([a-z_]+)\s*$", contents, flags=re.MULTILINE)
    result = dict(zip(sections[1::2], sections[2::2]))
    if tuple(result) != tuple(COLUMNS):
        raise ValueError("Projection relation order or allowlist changed")
    # Execution is protected by READ ONLY too; this catches an unintended edit
    # before any source SQL executes. No SQL file or query override is accepted.
    for query in result.values():
        without_comments = re.sub(r"--[^\n]*", "", query).strip()
        if not without_comments.startswith("SELECT ") or without_comments.count(";") != 1:
            raise ValueError("Only one explicit SELECT per relation is allowed")
        if re.search(r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|COPY|TRUNCATE|CALL)\b", without_comments, re.I):
            raise ValueError("Mutating SQL is outside the export contract")
    return result


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        # Numeric amounts retain exact decimal text; the importer casts using
        # PostgreSQL's numeric type rather than converting through binary float.
        return str(value)
    raise TypeError(f"Unsupported public projection value type: {type(value).__name__}")


def encode_row(columns: tuple[str, ...], values: tuple[Any, ...]) -> bytes:
    if len(columns) != len(values):
        raise ValueError("Column count differs from allowlist")
    return (json.dumps(dict(zip(columns, values)), ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False, default=json_default) + "\n").encode("utf-8")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export(connection: Any, destination: Path, comments_from: str | None = None,
           page_size: int = 1000) -> dict[str, Any]:
    if not 1 <= page_size <= 5000:
        raise ValueError("Page size must be 1–5000")
    if comments_from is not None and date.fromisoformat(comments_from) < date(2026, 1, 1):
        raise ValueError("Basic comments must be limited to 2026 or later")
    queries = projection_queries()
    destination.mkdir(parents=True, exist_ok=False)
    connection.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
    manifest: dict[str, Any] = {
        "format_version": 1, "completed": False, "city_fips": "0660620",
        "source_read_only": True, "source_local_only": True,
        "source_snapshot_at": None, "tables": {},
        "projection_sha256": file_hash(HERE / "projection.sql"),
        "bootstrap_sha256": file_hash(HERE / "public-core.sql"),
        "policy": {
            "active_sources_only": True, "generated_content": "withheld",
            "comments_from": comments_from,
            "comments_limitation": "Not indexed" if comments_from is None else "Recent minutes-sourced >=90% confidence records only; summaries omitted; coverage is incomplete",
            "finance_scope": "0660620:calendar-2026", "finance_from": "2026-01-01",
            "finance_through": "2026-11-03", "finance_coverage": "Source statuses and limitations preserved; no claim of completeness",
            "held_agenda_item_id": HELD_ITEM, "held_meeting_id": HELD_MEETING,
            "held_item_number": "j-2", "held_checked_at": "2026-10-03",
            "held_source_url": "https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809",
            "held_records": "Motions, votes and generated claims withheld; original item remains",
        },
        "private_tables_exported": False, "raw_documents_exported": False,
        "embeddings_exported": False, "provider_connections": False,
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT transaction_timestamp(), current_setting('server_version')")
            snapshot_time, version = cursor.fetchone()
            manifest["source_snapshot_at"] = snapshot_time.isoformat()
            manifest["postgres_version"] = version
            cursor.execute("SELECT meeting_id::text, lower(item_number) FROM public.agenda_items WHERE id=%s::uuid", (HELD_ITEM,))
            held = cursor.fetchone()
            if held and held != (HELD_MEETING, "j-2"):
                raise ValueError("Held source identity changed; export is blocked")
        for table, query in queries.items():
            path = destination / f"{table}.jsonl"
            digest = hashlib.sha256()
            rows = byte_count = 0
            # A named cursor streams a consistent transaction snapshot, instead
            # of buffering the full result or opening changing HTTP pages.
            with connection.cursor(name=f"basic_core_{table}") as cursor, path.open("xb") as stream:
                cursor.itersize = page_size
                cursor.execute(query, {"comments_from": comments_from})
                while batch := cursor.fetchmany(page_size):
                    actual = tuple(column.name for column in cursor.description)
                    if actual != COLUMNS[table]:
                        raise ValueError("Source projection fields differ from allowlist")
                    for values in batch:
                        encoded = encode_row(COLUMNS[table], values)
                        stream.write(encoded)
                        digest.update(encoded)
                        byte_count += len(encoded)
                        rows += 1
                # Even empty relations must have the reviewed field projection.
                if tuple(column.name for column in cursor.description) != COLUMNS[table]:
                    raise ValueError("Empty source projection fields differ from allowlist")
            manifest["tables"][table] = {"file": path.name, "columns": list(COLUMNS[table]),
                                         "rows": rows, "bytes": byte_count, "sha256": digest.hexdigest()}
        connection.rollback()  # Source transaction is intentionally never committed.
        manifest["completed"] = True
        manifest["total_rows"] = sum(t["rows"] for t in manifest["tables"].values())
        manifest["total_jsonl_bytes"] = sum(t["bytes"] for t in manifest["tables"].values())
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest
    except BaseException:
        connection.rollback()
        (destination / "incomplete-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("127.0.0.1", "::1", "localhost"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="richmond_restore")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--output", type=Path, default=HERE / "exports" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--comments-from", help="Opt-in recent public minutes comments, YYYY-MM-DD; default omits all comments")
    args = parser.parse_args()
    import psycopg2

    connection = None
    try:
        connection = psycopg2.connect(host=args.host, hostaddr="127.0.0.1" if args.host == "localhost" else args.host,
                                     port=args.port, dbname=args.database,
                                     user=args.user, connect_timeout=10, application_name="richmond-basic-core-read-export")
        report = export(connection, args.output, args.comments_from)
        # No rows, credentials or source configuration enter stdout.
        print(json.dumps({"completed": True, "output": str(args.output), "rows": report["total_rows"],
                          "jsonl_bytes": report["total_jsonl_bytes"]}))
        return 0
    except Exception as exc:
        print(json.dumps({"completed": False, "error_type": type(exc).__name__, "detail": "Export failed; source changes were not committed"}))
        return 1
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
