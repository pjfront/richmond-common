"""Atomic, append-only finance evidence snapshots and public projections."""
from __future__ import annotations

from psycopg2 import sql
from psycopg2.extras import Json


def persist_finance_snapshot(conn, assertions: list[dict], events: list[dict], coverage: list[dict]) -> dict:
    """Caller owns commit. Only a complete fetched snapshot can replace state.

    A partial public coverage status is expected (paper source gaps); failed
    pagination/metadata acquisition must never reach this function. All form
    scopes supplied here were completely fetched, even when zero rows match.
    """
    if not coverage or any(not c.get("snapshot_complete") for c in coverage):
        raise ValueError("Refusing to replace evidence with an incomplete acquisition")
    scopes = {c["scope_key"] for c in coverage}
    if len(scopes) != 1 or any(a["scope_key"] not in scopes for a in assertions):
        raise ValueError("A snapshot must have exactly one consistent scope")
    scope = next(iter(scopes))
    forms = [c["form_type"] for c in coverage]
    stats = {"assertions_inserted": 0, "assertions_retained": 0, "events_current": len(events)}
    identities = {}
    with conn.cursor() as cur:
        # Serializes projection rebuilds for a source. Transaction-level lock.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('finance:netfile'))")
        cur.execute("UPDATE finance_assertions SET is_current=false WHERE source='netfile' AND scope_key=%s AND form_type=ANY(%s)", (scope, forms))
        cur.execute("UPDATE finance_events SET is_current=false WHERE source='netfile' AND scope_key=%s", (scope,))
        for a in assertions:
            values = dict(a)
            values["raw_payload"] = Json(values["raw_payload"])
            columns = list(values)
            query = sql.SQL("INSERT INTO finance_assertions ({}) VALUES ({}) ON CONFLICT(source,record_key,content_hash) DO UPDATE SET is_current=EXCLUDED.is_current,reconciliation_status=EXCLUDED.reconciliation_status,canonical_event_key=EXCLUDED.canonical_event_key,review_reason=EXCLUDED.review_reason RETURNING id,(xmax=0)").format(
                sql.SQL(",").join(map(sql.Identifier, columns)), sql.SQL(",").join(sql.Placeholder() for _ in columns))
            cur.execute(query, [values[c] for c in columns])
            assertion_id, inserted = cur.fetchone()
            identities[(a["record_key"], a["content_hash"])] = str(assertion_id)
            stats["assertions_inserted" if inserted else "assertions_retained"] += 1
        for event in events:
            values = {key: value for key, value in event.items() if key != "assertion_keys"}
            values["assertion_ids"] = [identities[key] for key in event["assertion_keys"]]
            values["is_current"] = True
            columns = list(values)
            placeholders = [sql.SQL("%s::uuid[]") if c == "assertion_ids" else sql.Placeholder() for c in columns]
            query = sql.SQL("INSERT INTO finance_events ({}) VALUES ({}) ON CONFLICT(event_key) DO UPDATE SET {}").format(
                sql.SQL(",").join(map(sql.Identifier, columns)), sql.SQL(",").join(placeholders),
                sql.SQL(",").join(sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c)) for c in columns if c != "event_key"))
            cur.execute(query, [values[c] for c in columns])
        for item in coverage:
            values = {key: value for key, value in item.items() if key != "snapshot_complete"}
            columns = list(values)
            query = sql.SQL("INSERT INTO finance_source_coverage ({}) VALUES ({}) ON CONFLICT(source,form_type,scope_key) DO UPDATE SET {}").format(
                sql.SQL(",").join(map(sql.Identifier, columns)), sql.SQL(",").join(sql.Placeholder() for _ in columns),
                sql.SQL(",").join(sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c)) for c in columns if c not in {"source", "form_type", "scope_key"}))
            cur.execute(query, [values[c] for c in columns])
    return stats
