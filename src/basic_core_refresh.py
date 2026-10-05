"""Small, source-link-only refresh for the reviewed basic-core schema.

No raw document lake, PDF storage, transcripts, vectors or generated content.
Caller owns the explicit target/configuration guards and transaction commit.
Original ledger and source originals remain in the separately retained archive.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any
from uuid import UUID, NAMESPACE_URL, uuid5

CITY_FIPS = "0660620"
BASE_URL = "https://pub-richmond.escribemeetings.com"
CALENDAR_URL = BASE_URL + "/MeetingsCalendarView.aspx/GetCalendarMeetings"
MAX_MEETINGS = 20
MAX_HTML_BYTES = 2_000_000
MAX_CALENDAR_BYTES = 4_000_000
MAX_ITEMS = 250
MAX_BATCH_BYTES = 8_000_000
MAX_PUBLIC_DATABASE_BYTES = 500_000_000
MIN_HEADROOM_BYTES = 50_000_000
SOURCE_NAMESPACE = "richmond-basic-core-v1"


class CompactRefreshError(ValueError):
    """Constant, credential-free rejection reason."""


def _bounded_response(response, maximum: int) -> bytes:
    try:
        response.raise_for_status()
        # Do not accept an upstream redirect to another host or an error page.
        if response.status_code != 200:
            raise CompactRefreshError("Official source did not return an accepted response")
        total = 0
        parts = []
        for chunk in response.iter_content(chunk_size=64_000):
            total += len(chunk)
            if total > maximum:
                raise CompactRefreshError("Official source exceeded the bounded response size")
            parts.append(chunk)
        return b"".join(parts)
    finally:
        response.close()


def _normal_guid(value: Any) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise CompactRefreshError("Official calendar contains an invalid meeting identity") from exc


def normalize_observation(raw: dict, html: str | None) -> dict:
    """Use the existing pure portal parser; never download an attachment."""
    from escribemeetings_scraper import get_meeting_date, parse_meeting_page, parse_agenda_item

    guid = _normal_guid(raw.get("ID"))
    try:
        meeting_date = date.fromisoformat(get_meeting_date(raw)).isoformat()
    except ValueError as exc:
        raise CompactRefreshError("Official calendar contains an invalid meeting date") from exc
    name = str(raw.get("MeetingName") or "").strip()
    if not name or len(name) > 250:
        raise CompactRefreshError("Official calendar contains an invalid meeting name")
    cancelled = raw.get("IsCancelled") is True
    withdrawn = raw.get("HasAgenda") is False
    items = []
    state = "withdrawn" if cancelled or withdrawn else "awaiting_agenda"
    if html is not None and not cancelled and not withdrawn:
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(html,"html.parser")
        containers=soup.select("[class*='AgendaItemContainer']")
        if not containers:
            containers=soup.select("[id*='AgendaItem'], .agenda-item, .meetingItem")
        if len(containers)>MAX_ITEMS+100:
            raise CompactRefreshError("Portal layout exceeded the bounded item/container inventory")
        for container in containers:
            if parse_agenda_item(container) is None:
                # The parser deliberately drops unknown structures. That is
                # useful for extraction, but absence cannot authorize retiring
                # retained records when an unsupported container has content.
                if container.get_text(strip=True) or container.select_one("a[href]"):
                    raise CompactRefreshError("Unsupported portal content prevents complete agenda reconciliation")
        parsed = parse_meeting_page(html)
        seen = set()
        for item in parsed["items"]:
            number = str(item.get("item_number") or "").strip()
            # Section wrappers are not independently actionable records.
            if not number:
                raise CompactRefreshError("Unnumbered portal content cannot prove a complete agenda revision")
            if re.fullmatch(r"[A-Z]+", number):
                continue
            title = str(item.get("title") or "").strip()
            description = str(item.get("description") or "").strip()
            if (number.casefold() in seen or len(number) > 50 or not title
                    or len(title) > 5_000 or len(description) > 100_000):
                raise CompactRefreshError("Agenda has ambiguous or oversized numbered records")
            seen.add(number.casefold())
            items.append({"item_number": number, "title": title, "description": description})
        if len(items) > MAX_ITEMS:
            raise CompactRefreshError("Agenda exceeded the bounded item count")
        state = "complete_agenda" if items else "legacy_portal_stub"
    # Hash the exact normalized record projection, not volatile ASP.NET HTML
    # state or unrelated calendar fields. Repeated checks of unchanged agenda
    # records must not churn every tuple/index toward the Free storage ceiling.
    revision = hashlib.sha256(json.dumps({"guid":guid,"date":meeting_date,"name":name,
                                         "cancelled":cancelled,"state":state,"items":items},
                                         sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    return {"guid": guid, "meeting_date": meeting_date, "meeting_name": name,
            "meeting_type": "special" if "special" in name.lower() else "regular",
            "agenda_url": f"{BASE_URL}/Meeting.aspx?Id={guid}&Agenda=Agenda&lang=English",
            "cancelled": cancelled, "state": state, "items": items, "revision": revision}


def acquire_agendas(*, today: date | None = None, session=None, limit: int = MAX_MEETINGS) -> list[dict]:
    """Fetch one bounded past-60/next-14 window, with TLS and host redirects closed."""
    if type(limit) is not int or not 1 <= limit <= MAX_MEETINGS:
        raise CompactRefreshError("Agenda refresh limit must be between 1 and 20")
    import requests
    from escribemeetings_scraper import AJAX_HEADERS, PAGE_HEADERS, get_meeting_date

    current = today or date.today()
    start, end = current - timedelta(days=60), current + timedelta(days=14)
    owned = session is None
    session = session or requests.Session()
    if owned:
        session.trust_env = False
    try:
        calendar = _bounded_response(session.post(
            CALENDAR_URL, json={"calendarStartDate": start.isoformat(), "calendarEndDate": end.isoformat()},
            headers=AJAX_HEADERS, timeout=(10, 45), allow_redirects=False, stream=True), MAX_CALENDAR_BYTES)
        try:
            raw_rows = json.loads(calendar).get("d")
        except (ValueError, AttributeError) as exc:
            raise CompactRefreshError("Official calendar response is not accepted JSON") from exc
        if not isinstance(raw_rows, list):
            raise CompactRefreshError("Official calendar response has no meeting inventory")
        rows = []
        identities = set()
        for raw in raw_rows:
            if not isinstance(raw, dict):
                raise CompactRefreshError("Official calendar contains an invalid meeting row")
            guid = _normal_guid(raw.get("ID"))
            if guid in identities:
                raise CompactRefreshError("Official calendar contains duplicate meeting identities")
            identities.add(guid)
            try:
                when = date.fromisoformat(get_meeting_date(raw))
            except ValueError as exc:
                raise CompactRefreshError("Official calendar contains an invalid meeting date") from exc
            if start <= when <= end:
                rows.append(raw)
        # Refuse truncation disguised as a successful complete refresh.
        if len(rows) > limit:
            raise CompactRefreshError("Agenda window exceeds its bounded cohort; raise explicit limit within 20 or review source coverage")
        observations = []
        for raw in sorted(rows, key=lambda row: (get_meeting_date(row), str(row["ID"]))):
            html = None
            has_link = any(isinstance(link, dict) and str(link.get("Type") or "").lower() in {"agenda", "agendacover"}
                           for link in (raw.get("MeetingDocumentLink") or []))
            if raw.get("IsCancelled") is not True and raw.get("HasAgenda") is not False and (raw.get("HasAgenda") is True or has_link):
                response = session.get(BASE_URL + "/Meeting.aspx", params={"Id": _normal_guid(raw["ID"]), "Agenda": "Agenda", "lang": "English"},
                                       headers=PAGE_HEADERS, timeout=(10, 45), allow_redirects=False, stream=True)
                html = _bounded_response(response, MAX_HTML_BYTES).decode("utf-8", errors="replace")
            observations.append(normalize_observation(raw, html))
        _validate_batch_size(observations)
        return observations
    finally:
        if owned:
            session.close()


def _validate_batch_size(value: Any) -> int:
    size = len(json.dumps(value, default=str, ensure_ascii=True).encode())
    if size > MAX_BATCH_BYTES:
        raise CompactRefreshError("Compact source batch exceeds its memory/write ceiling")
    return size


def check_storage(cur, payload_bytes: int = 0, ceiling: int = MAX_PUBLIC_DATABASE_BYTES) -> int:
    if type(ceiling) is not int or not 0 < ceiling <= MAX_PUBLIC_DATABASE_BYTES:
        raise CompactRefreshError("Compact database ceiling must not exceed 500 MB")
    cur.execute("SELECT pg_database_size(current_database())")
    current = int(cur.fetchone()[0])
    # Index and tuple overhead are reserved before writing; a post-write check
    # also rolls back unexpected growth. Frequent tombstones need owner vacuum.
    required = max(MIN_HEADROOM_BYTES, payload_bytes * 8)
    if current + required >= ceiling:
        raise CompactRefreshError("Compact database has insufficient reserved storage headroom")
    return current


def preflight_compact(conn, steps: list[str], *, ceiling: int = MAX_PUBLIC_DATABASE_BYTES) -> None:
    tables = {"bodies", "meetings", "agenda_items", "topics", "item_topics", "core_projection_status"}
    if "finance" in steps:
        tables.update({"finance_public_events", "finance_public_coverage"})
    with conn.cursor() as cur:
        # The compact schema must not be the restored paid/source document DB.
        cur.execute("SELECT to_regclass('public.documents')")
        if cur.fetchone()[0] is not None:
            raise CompactRefreshError("Compact refresh refuses a full document-lake database")
        for table in sorted(tables):
            cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
            if cur.fetchone()[0] is None:
                raise CompactRefreshError("Compact public schema is incomplete")
        check_storage(cur, ceiling=ceiling)
    conn.commit()


def _identity(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{SOURCE_NAMESPACE}:{kind}:{value}"))


def write_agendas(cur, observations: list[dict], *, tag: bool = True) -> dict:
    """Preserve UUIDs and minutes authority; tombstone only proven agenda rows."""
    from city_config import get_city_config
    from topic_tagger import tag_topics

    mapping = {v: k for k, v in get_city_config(CITY_FIPS)["data_sources"].get("commissions_escribemeetings", {}).items()}
    stats = {"meetings_observed": len(observations), "meetings_written": 0, "items_written": 0,
             "items_retired": 0, "tags_written": 0, "minutes_preserved": 0, "unmapped_bodies": 0, "awaiting_agenda": 0}
    cur.execute("SELECT name, id FROM bodies WHERE city_fips = %s", (CITY_FIPS,))
    bodies = {name: str(identity) for name, identity in cur.fetchall()}
    cur.execute("SELECT slug, id, name FROM topics WHERE city_fips = %s AND status = 'active'", (CITY_FIPS,))
    topics = {slug: (str(identity), name) for slug, identity, name in cur.fetchall()}
    for observation in observations:
        name = observation["meeting_name"]
        body_name = "City Council" if "city council" in name.lower() else mapping.get(name, name)
        body_id = bodies.get(body_name)
        if not body_id:
            stats["unmapped_bodies"] += 1
            continue
        guid, when, kind = observation["guid"], observation["meeting_date"], observation["meeting_type"]
        cur.execute("""SELECT id, source_meeting_guid, minutes_url,meeting_date,body_id,meeting_type FROM meetings
                       WHERE city_fips = %s AND (source_meeting_guid = %s OR
                         (meeting_date = %s AND body_id = %s AND meeting_type = %s)) FOR UPDATE""",
                    (CITY_FIPS, guid, when, body_id, kind))
        existing = cur.fetchall()
        if len(existing) > 1 or existing and existing[0][1] not in {None, guid}:
            raise CompactRefreshError("Source meeting identity conflicts with retained records")
        if existing and (str(existing[0][3]),str(existing[0][4]),existing[0][5]) != (when,body_id,kind):
            # A reschedule/body/type move needs source-aware reconciliation;
            # retain the last successful identity, records, and vote context.
            raise CompactRefreshError("Source meeting reschedule/body/type requires explicit identity review")
        meeting_id = str(existing[0][0]) if existing else _identity("meeting", guid)
        cur.execute("SELECT id, item_number, agenda_source_authority FROM agenda_items WHERE meeting_id = %s FOR UPDATE", (meeting_id,))
        retained = {}
        for identity, number, authority in cur.fetchall():
            key = number.casefold()
            if key in retained:
                raise CompactRefreshError("Retained meeting has ambiguous item identities")
            retained[key] = (str(identity), authority)
        has_minutes = bool(existing and existing[0][2]) or any(authority == "minutes" for _, authority in retained.values())
        cur.execute("""INSERT INTO meetings (id, city_fips, body_id, meeting_date, meeting_type, agenda_url,
                          source_meeting_guid, source_cancelled_at, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN now() END,now())
                       ON CONFLICT (id) DO UPDATE SET agenda_url=EXCLUDED.agenda_url,
                         source_meeting_guid=EXCLUDED.source_meeting_guid,
                         source_cancelled_at=EXCLUDED.source_cancelled_at
                       WHERE meetings.agenda_url IS DISTINCT FROM EXCLUDED.agenda_url
                          OR meetings.source_meeting_guid IS DISTINCT FROM EXCLUDED.source_meeting_guid
                          OR (meetings.source_cancelled_at IS NULL) IS DISTINCT FROM (EXCLUDED.source_cancelled_at IS NULL)""",
                    (meeting_id, CITY_FIPS, body_id, when, kind, observation["agenda_url"], guid, observation["cancelled"] and not has_minutes))
        stats["meetings_written"] += max(cur.rowcount, 0)
        state = observation["state"]
        if state in {"awaiting_agenda", "legacy_portal_stub"}:
            stats["awaiting_agenda"] += 1
            continue  # Unknown or placeholder source is never a withdrawal.
        numbers = []
        for item in observation["items"]:
            number = item["item_number"]
            numbers.append(number.casefold())
            retained_item = retained.get(number.casefold())
            if retained_item and retained_item[1] != "agenda":
                stats["minutes_preserved"] += 1
                continue
            item_id = retained_item[0] if retained_item else _identity("item", f"{meeting_id}:{number.casefold()}")
            cur.execute("""INSERT INTO agenda_items (id,meeting_id,item_number,title,description,
                              is_consent_calendar,was_pulled_from_consent,agenda_source_authority,
                              agenda_source_revision_sha256,created_at)
                           VALUES (%s,%s,%s,%s,%s,false,false,'agenda',%s,now())
                           ON CONFLICT(id) DO UPDATE SET title=EXCLUDED.title,description=EXCLUDED.description,
                             agenda_source_revision_sha256=EXCLUDED.agenda_source_revision_sha256,
                             agenda_source_retired_at=NULL
                           WHERE agenda_items.agenda_source_authority='agenda' AND
                             (agenda_items.title IS DISTINCT FROM EXCLUDED.title OR
                              agenda_items.description IS DISTINCT FROM EXCLUDED.description OR
                              agenda_items.agenda_source_revision_sha256 IS DISTINCT FROM EXCLUDED.agenda_source_revision_sha256 OR
                              agenda_items.agenda_source_retired_at IS NOT NULL)""",
                        (item_id, meeting_id, number, item["title"], item["description"], observation["revision"]))
            stats["items_written"] += max(cur.rowcount, 0)
            if tag:
                stats["tags_written"] += reconcile_keyword_tags(cur, item_id, item["title"] + " " + item["description"], topics)

        cur.execute("""UPDATE agenda_items SET agenda_source_retired_at=now(),agenda_source_revision_sha256=%s
                       WHERE meeting_id=%s AND agenda_source_authority='agenda'
                         AND agenda_source_retired_at IS NULL AND NOT (lower(item_number)=ANY(%s))""",
                    (observation["revision"], meeting_id, numbers))
        stats["items_retired"] += max(cur.rowcount, 0)
        cur.execute("""UPDATE meetings SET agenda_item_count=(SELECT count(*) FROM agenda_items
                       WHERE meeting_id=%s AND agenda_source_retired_at IS NULL) WHERE id=%s""", (meeting_id, meeting_id))
    status = "partial" if stats["unmapped_bodies"] or stats["awaiting_agenda"] else "checked"
    cur.execute("""INSERT INTO core_projection_status(feature,status,detail,checked_at,source_url,source_scope)
                   VALUES('agenda_refresh',%s,%s,now(),%s,'past-60/next-14-day window')
                   ON CONFLICT(feature) DO UPDATE SET status=EXCLUDED.status,detail=EXCLUDED.detail,
                     checked_at=EXCLUDED.checked_at,source_url=EXCLUDED.source_url,
                     source_scope=EXCLUDED.source_scope,updated_at=now()""",
                (status, "Official portal window checked; existing votes retained, no new vote extraction. Attachments remain official source links, not stored binaries.", CALENDAR_URL))
    return stats


def reconcile_keyword_tags(cur, item_id: str, text: str, topics: dict) -> int:
    """Refresh derived keywords, preserving manual tags and un-attributed labels."""
    from topic_tagger import tag_topics
    stats = {"tags_written": 0}
    matches = [match for match in tag_topics(text) if match.slug in topics]
    current_topics = [topics[match.slug][0] for match in matches]
    # Derived keyword assignments are a projection, not original
    # record evidence. Reconcile only this proven keyword subset;
    # archive source records and manual/generated tags stay intact.
    cur.execute("""DELETE FROM item_topics WHERE agenda_item_id=%s AND source='keyword'
                   AND NOT (topic_id=ANY(%s::uuid[]))""", (item_id,current_topics))
    for match in matches:
        topic_id, _ = topics[match.slug]
        cur.execute("SELECT id, source FROM item_topics WHERE agenda_item_id=%s AND topic_id=%s", (item_id, topic_id))
        old = cur.fetchall()
        if len(old) > 1:
            raise CompactRefreshError("Retained topic assignments have ambiguous identities")
        if old and old[0][1] != "keyword":
            continue  # Preserve reviewed/manual/generated provenance.
        assignment_id = str(old[0][0]) if old else _identity("tag", f"{item_id}:{topic_id}")
        cur.execute("""INSERT INTO item_topics(id,agenda_item_id,topic_id,confidence,source,created_at)
                       VALUES(%s,%s,%s,%s,'keyword',now()) ON CONFLICT(id) DO UPDATE
                       SET confidence=EXCLUDED.confidence WHERE item_topics.source='keyword'
                       AND item_topics.confidence IS DISTINCT FROM EXCLUDED.confidence""",
                    (assignment_id, item_id, topic_id, match.confidence))
        stats["tags_written"] += max(cur.rowcount, 0)
    label = None
    if matches:
        best = sorted(matches, key=lambda match: (-match.confidence, topics[match.slug][1]))[0]
        label = topics[best.slug][1]
    # Preserve un-attributed imported/manual/generated labels.
    # Subsequent refreshes can change labels this writer proved it
    # owns. Metadata is not copied into generated content fields.
    label_key = f"keyword_label:{item_id}"
    cur.execute("SELECT detail FROM core_projection_status WHERE feature=%s AND status='keyword_label'", (label_key,))
    owned_label = cur.fetchone()
    previous_label = owned_label[0] if owned_label else None
    cur.execute("""UPDATE agenda_items SET topic_label=%s WHERE id=%s
                   AND (topic_label IS NULL OR topic_label=%s)
                   AND topic_label IS DISTINCT FROM %s""", (label,item_id,previous_label,label))
    if cur.rowcount > 0:
        cur.execute("""INSERT INTO core_projection_status(feature,status,detail,checked_at)
                       VALUES(%s,'keyword_label',%s,now()) ON CONFLICT(feature)
                       DO UPDATE SET detail=EXCLUDED.detail,checked_at=EXCLUDED.checked_at,updated_at=now()""", (label_key,label or ""))
    return stats["tags_written"]


def replace_finance(cur, projection: dict) -> dict:
    """Replace only a proven complete scope; archive originals stay untouched."""
    from finance_public_projection import EVENT_COLUMNS, COVERAGE_COLUMNS

    scope = projection["scope_key"]
    cur.execute("DELETE FROM finance_public_events WHERE scope_key=%s", (scope,))
    cur.execute("DELETE FROM finance_public_coverage WHERE scope_key=%s", (scope,))
    for table, columns, rows in (
        ("finance_public_events", EVENT_COLUMNS, projection["events"]),
        ("finance_public_coverage", COVERAGE_COLUMNS, projection["coverage"]),
    ):
        # Tables and columns are code constants, never supplied by source data.
        query = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(['%s'] * len(columns))})"
        for row in rows:
            cur.execute(query, tuple(row[column] for column in columns))
    pending_cycle = date.today() > date(2026, 11, 3)
    cur.execute("""INSERT INTO core_projection_status(feature,status,detail,checked_at,source_url,source_scope)
                   VALUES('finance',%s,%s,now(),%s,%s) ON CONFLICT(feature) DO UPDATE
                   SET status=EXCLUDED.status,detail=EXCLUDED.detail,checked_at=EXCLUDED.checked_at,
                     source_url=EXCLUDED.source_url,source_scope=EXCLUDED.source_scope,updated_at=now()""",
                ("pending_review" if pending_cycle else "partial", "Reviewed 2026 electronic snapshot checked atomically. Paper filings and coverage limitations remain explicit; cycle expansion requires review, no complete campaign total is inferred.",
                 "https://public.netfile.com/pub2/?AID=RICH", scope))
    return {"events": len(projection["events"]), "coverage_rows": len(projection["coverage"])}


def refresh_compact(conn, steps: list[str], *, year: int, through: str, ceiling: int,
                    agenda_limit: int = MAX_MEETINGS, agenda_acquire=None, finance_acquire=None,
                    finance_project=None) -> dict:
    """Acquire before one transaction, validate before any replacement, no PDFs kept."""
    if any(step not in {"agenda", "tags", "finance"} for step in steps) or "tags" in steps and "agenda" not in steps:
        raise CompactRefreshError("Compact tags require an agenda refresh in the same bounded pass")
    if "finance" in steps and (year != 2026 or not "2026-01-01" <= through <= "2026-11-03"):
        raise CompactRefreshError("Compact finance is limited to the reviewed 2026 publication window")
    preflight_compact(conn, steps, ceiling=ceiling)
    observations = (agenda_acquire or acquire_agendas)(limit=agenda_limit) if "agenda" in steps else []
    projection = None
    if "finance" in steps:
        from basic_finance_acquisition import acquire_bounded_finance_snapshot
        from finance_public_projection import project_public_finance_snapshot
        snapshot = (finance_acquire or acquire_bounded_finance_snapshot)(year, through)
        with conn.cursor() as cur:
            cur.execute("SELECT max(activity_through) FROM finance_public_coverage WHERE scope_key='0660620:calendar-2026'")
            previous_through = cur.fetchone()[0]
        conn.commit()
        projection = (finance_project or project_public_finance_snapshot)(snapshot, previous_through=previous_through)
        # Public storage contains no raw assertion JSON, PDF or donor addresses.
        del snapshot
    payload_size = _validate_batch_size({"agenda": observations, "finance": projection})
    results = []
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('richmond-basic-refresh',0))")
            cur.execute("SET LOCAL statement_timeout='30s'")
            check_storage(cur, payload_size, ceiling)
            if "agenda" in steps:
                results.append({"step": "agenda_tags", **write_agendas(cur, observations, tag="tags" in steps)})
            if projection is not None:
                cur.execute("SELECT max(activity_through) FROM finance_public_coverage WHERE scope_key=%s", (projection["scope_key"],))
                latest = cur.fetchone()[0]
                if latest is not None and str(latest) > projection["activity_through"]:
                    raise CompactRefreshError("Finance source cutoff would regress the retained snapshot")
                results.append({"step": "finance", **replace_finance(cur, projection)})
            cur.execute("SELECT pg_database_size(current_database())")
            if int(cur.fetchone()[0]) >= ceiling - MIN_HEADROOM_BYTES:
                raise CompactRefreshError("Compact write exceeded its reserved storage ceiling")
    return {"status": "completed", "modelCalls": 0, "results": results}
