"""Read-only representative civic/search/finance checks on the compact LOCAL DB.

Prints aggregate verification outcomes only, never source rows or credentials.
Does not start/stop servers or modify any data. HTTP/PostgREST checks are separate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from export_core import HELD_ITEM, HELD_MEETING


def verify(connection: Any) -> dict[str, Any]:
    connection.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
    checks: dict[str, Any] = {}
    with connection.cursor() as cursor:
        # Same parent/child relationships used by getMeeting/getAgendaItemDetail.
        cursor.execute("""SELECT m.id FROM public.meetings m JOIN public.bodies b ON b.id=m.body_id
            WHERE m.meeting_date BETWEEN DATE '2026-01-01' AND DATE '2026-11-03'
            AND EXISTS (SELECT 1 FROM public.agenda_items a WHERE a.meeting_id=m.id)
            ORDER BY m.meeting_date DESC,m.id LIMIT 1""")
        meeting = cursor.fetchone()
        if not meeting:
            raise ValueError("No representative 2026 meeting with original items")
        meeting_id = meeting[0]
        cursor.execute("SELECT count(*) FROM public.agenda_items WHERE meeting_id=%s", (meeting_id,))
        checks["recent_meeting_agenda_items"] = cursor.fetchone()[0]
        cursor.execute("""SELECT count(*) FROM public.meeting_attendance ma
            JOIN public.officials o ON o.id=ma.official_id WHERE ma.meeting_id=%s""", (meeting_id,))
        checks["recent_meeting_attendance_embeds"] = cursor.fetchone()[0]
        cursor.execute("""SELECT a.id FROM public.agenda_items a JOIN public.meetings m ON m.id=a.meeting_id
            WHERE m.city_fips='0660620' AND m.source_cancelled_at IS NULL
              AND a.agenda_source_retired_at IS NULL AND EXISTS
              (SELECT 1 FROM public.motions mo JOIN public.votes v ON v.motion_id=mo.id WHERE mo.agenda_item_id=a.id)
            ORDER BY m.meeting_date DESC,a.id LIMIT 1""")
        item = cursor.fetchone()
        if not item:
            raise ValueError("No representative source-backed vote item")
        cursor.execute("SELECT count(*) FROM public.motions WHERE agenda_item_id=%s", (item[0],))
        checks["item_motion_count"] = cursor.fetchone()[0]
        cursor.execute("""SELECT count(*) FROM public.votes v JOIN public.motions mo ON mo.id=v.motion_id
            LEFT JOIN public.officials o ON o.id=v.official_id WHERE mo.agenda_item_id=%s""", (item[0],))
        checks["item_vote_rows"] = cursor.fetchone()[0]
        cursor.execute("""SELECT count(*) FROM public.agenda_items a JOIN public.meetings m ON m.id=a.meeting_id
            WHERE a.id=%s::uuid AND m.id=%s::uuid AND lower(a.item_number)='j-2'""", (HELD_ITEM, HELD_MEETING))
        checks["exact_j2_identity_retained"] = cursor.fetchone()[0] == 1
        cursor.execute("SELECT count(*) FROM public.motions WHERE agenda_item_id=%s::uuid", (HELD_ITEM,))
        checks["exact_j2_disputed_motions_absent"] = cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM public.item_topics it JOIN public.topics t ON t.id=it.topic_id JOIN public.agenda_items a ON a.id=it.agenda_item_id")
        checks["valid_item_topic_embeds"] = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM public.finance_public_events WHERE source_url<>'' AND extracted_at IS NOT NULL AND cardinality(source_urls)>0")
        checks["source_linked_finance_events"] = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM public.finance_public_coverage WHERE status='partial' AND cardinality(limitations)>0")
        checks["partial_finance_sources_with_limits"] = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM public.search_site('housing','0000000','agenda_item',1000,0)")
        checks["other_city_search_empty"] = cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM public.search_site('housing','0660620','agenda_item',1000,0)")
        checks["search_limit_clamped"] = cursor.fetchone()[0] <= 50
        cursor.execute("SELECT count(*) FROM public.search_site('','0660620',NULL,20,0)")
        checks["empty_search_empty"] = cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM public.search_site('housing','0660620','operator',20,0)")
        checks["unsupported_search_kind_empty"] = cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename IN ('documents','donors','contributions','operator_config','email_subscribers','search_queries','llm_cost_reservations','pipeline_journal')")
        checks["excluded_relations_absent"] = cursor.fetchone()[0] == 0
    connection.rollback()
    if any(value is False for value in checks.values()):
        raise ValueError("A compact public read check failed")
    return {"passed": True, "read_only": True, "local_only": True,
            "checks": checks, "http_postgrest_verified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("127.0.0.1", "::1", "localhost"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="basic_core_measure_20261004")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    import psycopg2

    connection = None
    try:
        connection = psycopg2.connect(host=args.host, hostaddr="127.0.0.1" if args.host == "localhost" else args.host,
                                     port=args.port, dbname=args.database,
                                     user=args.user, connect_timeout=10)
        report = verify(connection)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
        return 0
    except Exception as exc:
        print(json.dumps({"passed": False, "error_type": type(exc).__name__, "detail": "Local read verification failed"}))
        return 1
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
