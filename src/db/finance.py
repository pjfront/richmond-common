"""Atomic, append-only finance evidence snapshots and public projections."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import uuid

from psycopg2 import Binary, sql
from psycopg2.extras import Json, execute_values

from finance_ledger import FORMS

BATCH_SIZE = 250


def persist_finance_documents(conn, assertions: list[dict], pdfs: dict[str, bytes]) -> dict:
    """Batch content-addressed evidence storage; caller owns the transaction.

    Lookup all hashes once. New evidence uses bounded VALUES batches and keeps
    document-lake uniqueness, including a concurrent non-finance document writer.
    """
    documents, links = {}, {}
    for filing, content in pdfs.items():
        content_hash = hashlib.sha256(content).hexdigest()
        links[("pdf", filing)] = content_hash
        documents[content_hash] = dict(id=str(uuid.uuid4()), city_fips="0660620", source_type="netfile_496",
            source_url=f"https://netfile.com/Connect2/api/public/image/{filing}", source_identifier=filing,
            raw_content=content, content_hash=content_hash, mime_type="application/pdf", credibility_tier=1,
            metadata={"parser":"netfile-496-layout-v1"})
    for a in assertions:
        content = json.dumps(a["raw_payload"], sort_keys=True).encode()
        content_hash = hashlib.sha256(content).hexdigest()
        links[("json", a["record_key"], a["content_hash"])] = content_hash
        documents[content_hash] = dict(id=str(uuid.uuid4()), city_fips="0660620", source_type="netfile_transaction",
            source_url=a["source_url"], source_identifier=a["record_key"], raw_content=content,
            content_hash=content_hash, mime_type="application/json", credibility_tier=1, metadata={})
    ids, inserted = {}, []
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('finance:netfile'))")
        if documents:
            cur.execute("SELECT content_hash,id FROM documents WHERE city_fips='0660620' AND content_hash=ANY(%s)", (list(documents),))
            ids.update((content_hash,str(document_id)) for content_hash,document_id in cur.fetchall())
            columns = list(next(iter(documents.values())))
            missing = []
            for content_hash, document in documents.items():
                if content_hash in ids:
                    continue
                values = dict(document, raw_content=Binary(document["raw_content"]), metadata=Json(document["metadata"]))
                missing.append([values[c] for c in columns])
            if missing:
                query = sql.SQL("INSERT INTO documents ({}) VALUES %s ON CONFLICT(city_fips,content_hash) DO NOTHING RETURNING content_hash,id").format(sql.SQL(",").join(map(sql.Identifier, columns)))
                inserted = execute_values(cur, query, missing, page_size=BATCH_SIZE, fetch=True)
                ids.update((content_hash,str(document_id)) for content_hash,document_id in inserted)
            unresolved = set(documents) - ids.keys()
            if unresolved:
                # A different source writer may have stored identical bytes
                # between the lookup and INSERT. Read that immutable document.
                cur.execute("SELECT content_hash,id FROM documents WHERE city_fips='0660620' AND content_hash=ANY(%s)", (sorted(unresolved),))
                ids.update((content_hash,str(document_id)) for content_hash,document_id in cur.fetchall())
            if set(documents) - ids.keys():
                raise RuntimeError("Evidence insert did not return or resolve every content hash")
    for a in assertions:
        content_hash = links.get(("pdf", a["filing_id"]), links[("json", a["record_key"], a["content_hash"])])
        a["document_id"] = ids[content_hash]
    return dict(documents_inserted=len(inserted), documents_retained=len(documents)-len(inserted),
                document_bytes_inserted=sum(len(documents[key]["raw_content"]) for key,_ in inserted))


def _upsert_projection(cur, table: str, rows: list[dict], conflict_columns: tuple[str, ...]) -> None:
    if not rows:
        return
    columns = list(rows[0])
    query = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT({}) DO UPDATE SET {}").format(
        sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns)),
        sql.SQL(",").join(map(sql.Identifier, conflict_columns)),
        sql.SQL(",").join(sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c)) for c in columns if c not in conflict_columns))
    template = "(" + ",".join("%s::uuid[]" if c == "assertion_ids" else "%s" for c in columns) + ")"
    execute_values(cur, query, [[row[c] for c in columns] for row in rows], template=template, page_size=BATCH_SIZE)


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
    if len(forms) != len(FORMS) or set(forms) != set(FORMS.values()):
        raise ValueError("A calendar projection requires all supported forms; a partial form set cannot replace it")
    stats = {"assertions_inserted": 0, "assertions_retained": 0, "events_current": len(events)}
    identities = {}
    with conn.cursor() as cur:
        # Serializes projection rebuilds for a source. Transaction-level lock.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('finance:netfile'))")
        cur.execute("SELECT max(activity_through) FROM finance_source_coverage WHERE source='netfile' AND scope_key=%s", (scope,))
        previous_through = cur.fetchone()[0]
        incoming_through = min(date.fromisoformat(str(c["activity_through"])[:10]) for c in coverage)
        if previous_through and previous_through > incoming_through:
            raise ValueError("Refusing to shrink a current calendar snapshot to an earlier cutoff")
        cur.execute("""SELECT id,record_key,content_hash,is_current,reconciliation_status,canonical_event_key,review_reason
                       FROM finance_assertions WHERE source='netfile' AND scope_key=%s""", (scope,))
        existing = {(row[1],row[2]):row for row in cur.fetchall()}
        touched = []
        for a in assertions:
            key = a["record_key"], a["content_hash"]
            old = existing.get(key)
            identities[key] = str(old[0]) if old else str(uuid.uuid4())
            desired = (a["is_current"], a["reconciliation_status"], a["canonical_event_key"], a["review_reason"])
            if old and tuple(old[3:]) == desired:
                # No INSERT/conflict lock and no toggle-false-then-true write
                # for unchanged immutable evidence on a daily replay.
                continue
            values = dict(a, id=identities[key])
            values["raw_payload"] = Json(values["raw_payload"])
            touched.append(values)
        if touched:
            columns = list(touched[0])
            query = sql.SQL("INSERT INTO finance_assertions ({}) VALUES %s ON CONFLICT(source,record_key,content_hash) DO UPDATE SET is_current=EXCLUDED.is_current,reconciliation_status=EXCLUDED.reconciliation_status,canonical_event_key=EXCLUDED.canonical_event_key,review_reason=EXCLUDED.review_reason RETURNING id,record_key,content_hash,(xmax=0)").format(sql.SQL(",").join(map(sql.Identifier, columns)))
            returned = execute_values(cur, query, [[row[c] for c in columns] for row in touched], page_size=BATCH_SIZE, fetch=True)
            for assertion_id,record_key,content_hash,inserted in returned:
                identities[(record_key,content_hash)] = str(assertion_id)
                stats["assertions_inserted"] += int(inserted)
        stats["assertions_retained"] = len(assertions) - stats["assertions_inserted"]
        stats["assertion_versions_updated"] = len(touched) - stats["assertions_inserted"]
        current_ids = [identities[(a["record_key"],a["content_hash"])] for a in assertions if a["is_current"]]
        cur.execute("""UPDATE finance_assertions SET is_current=false
                       WHERE source='netfile' AND scope_key=%s AND is_current AND NOT(id=ANY(%s::uuid[]))""", (scope,current_ids))
        event_rows = []
        for event in events:
            values = {key: value for key, value in event.items() if key != "assertion_keys"}
            values["assertion_ids"] = [identities[key] for key in event["assertion_keys"]]
            values["is_current"] = True
            event_rows.append(values)
        _upsert_projection(cur, "finance_events", event_rows, ("event_key",))
        cur.execute("UPDATE finance_events SET is_current=false WHERE source='netfile' AND scope_key=%s AND is_current AND NOT(event_key=ANY(%s))", (scope,[e["event_key"] for e in events]))
        _upsert_projection(cur, "finance_source_coverage", [{k:v for k,v in c.items() if k != "snapshot_complete"} for c in coverage], ("source","form_type","scope_key"))
    return stats
