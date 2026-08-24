"""
db.meetings — extracted from db.py (Phase 2.1).

Re-exported from `db` package for backwards compatibility.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

from ._core import RICHMOND_FIPS, sanitize_text
from . import officials as _officials


def _active_agenda_revision_changed(
    active_source_states,
    incoming_revision: str,
) -> bool:
    """Compare an incoming revision with active, non-minutes source rows."""
    return any(
        authority != "agenda" or revision != incoming_revision
        for authority, revision in active_source_states
    )


def _agenda_reconciliation_invalidation_ids(
    attachment_changed_item_ids,
    newly_retired_item_ids,
    active_agenda_item_ids,
    *,
    agenda_revision_changed: bool,
) -> list:
    """Return the exact one-revision derivative invalidation set.

    Active agenda rows are invalidated when their source revision advances.
    Rows retired by *this* revision are unioned once. Older tombstones are
    deliberately absent from both inputs so a later verification cannot keep
    charging to regenerate derivatives that can never become current again.
    """
    ordered_ids = list(attachment_changed_item_ids)
    ordered_ids.extend(newly_retired_item_ids)
    if agenda_revision_changed:
        ordered_ids.extend(active_agenda_item_ids)
    return list(dict.fromkeys(ordered_ids))


def load_meeting_to_db(
    conn,
    data: dict,
    document_id: uuid.UUID = None,
    city_fips: str = RICHMOND_FIPS,
    body_id: uuid.UUID = None,
    agenda_url: str | None = None,
    authoritative_agenda_revision: str | None = None,
    official_minutes: bool = False,
    source_meeting_guid: str | None = None,
    source_observed_at: str | None = None,
    commit: bool = True,
) -> uuid.UUID:
    """Load extracted meeting JSON into Layer 2 structured tables.

    This is the main entry point for populating the structured schema
    from Claude's extraction output.

    Args:
        body_id: FK to bodies table. When provided, derives the default
            role for members (e.g., 'commissioner' for commissions)
            instead of defaulting to 'councilmember'.
        authoritative_agenda_revision: A complete eSCRIBE agenda revision.
            When present, agenda fields are exact source replacements (NULL
            clears stale values), current items are marked with this revision,
            and only previously managed items absent from this revision are
            soft-retired.  Leave NULL for minutes/transcript/LLM loads.
        official_minutes: This load is extracted from adopted official
            minutes. Minutes outrank agenda plans and revive/fence their
            confirmed items from later agenda reconciliation. The loader
            derives the public minutes link from the authoritative
            ``documents.source_url`` in the same transaction; callers must
            not supply a separately reconstructed URL.

    Returns the meeting UUID.
    """
    # ── Auto-resolve body_id to City Council when not provided ──
    if body_id is None:
        body_id = _officials.resolve_body_id(conn, city_fips, "City Council")

    # ── Resolve default role from body type ──
    body_type = _officials._resolve_body_type(conn, body_id)
    default_role = _officials._default_role_for_body_type(body_type)

    # ── Defensive type coercion ──
    # LLM extraction occasionally returns strings instead of dicts/lists
    # for fields with no data (e.g., "No consent calendar" instead of {}).
    # Coerce at the boundary so downstream code can assume correct types.
    _list_fields = [
        "members_present", "members_absent", "members_late",
        "closed_session_items", "action_items", "public_comments",
        "public_comments_open_forum", "written_public_comments",
        "council_reports", "conflict_of_interest_declared",
    ]
    for field in _list_fields:
        if field in data and not isinstance(data[field], list):
            data[field] = []

    _dict_fields = ["consent_calendar", "adjournment"]
    for field in _dict_fields:
        if field in data and not isinstance(data[field], dict):
            data[field] = {}

    # Sanitize sentinel strings — LLM extraction sometimes returns
    # "<UNKNOWN>", "N/A", "Unknown" instead of null for missing fields.
    # Convert these to None so the DB stores NULL, not a literal string.
    _sentinel_values = {"<UNKNOWN>", "<unknown>", "N/A", "n/a", "Unknown", "unknown", ""}
    _text_fields = [
        "call_to_order_time", "adjournment_time", "presiding_officer",
        "next_meeting_date", "adjourned_in_memory_of",
    ]
    for field in _text_fields:
        if field in data and data[field] in _sentinel_values:
            data[field] = None

    official_motion_replacement_numbers: list[str] = []
    if official_minutes:
        for item in (
            list(data.get("action_items") or [])
            + list(data.get("housing_authority_items") or [])
        ):
            motions = item.get("motions") or []
            has_validated_motion = any(
                isinstance(motion, dict)
                and bool(
                    str(motion.get("motion_text") or "").strip()
                    or str(motion.get("result") or "").strip()
                    or list(motion.get("votes") or [])
                )
                for motion in motions
            )
            item_number = str(item.get("item_number") or "").strip()
            if item_number and has_validated_motion:
                official_motion_replacement_numbers.append(item_number)
        consent = data.get("consent_calendar") or {}
        consent_votes = consent.get("votes") or []
        if consent_votes and str(consent.get("result") or "").strip():
            pulled_numbers = {
                str(pulled).split(" ")[0].split("(")[0].strip()
                for pulled in consent.get(
                    "items_pulled_for_separate_vote", []
                )
            }
            official_motion_replacement_numbers.extend(
                str(item.get("item_number") or "").strip()
                for item in consent.get("items") or []
                if str(item.get("item_number") or "").strip()
                and str(item.get("item_number") or "").strip()
                not in pulled_numbers
                and not re.match(
                    r"^[A-Z]+$",
                    str(item.get("item_number") or "").strip(),
                )
            )

    # Validate meeting_date — must be a valid ISO date for the DATE column.
    # LLM sometimes returns "<UNKNOWN>", "N/A", or descriptive text.
    raw_date = data.get("meeting_date")
    if raw_date:
        try:
            datetime.strptime(raw_date, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid meeting_date '{raw_date}' — cannot insert into DB. "
                "Document may not be parseable meeting minutes."
            )

    meeting_id = uuid.uuid4()

    with conn.cursor() as cur:
        authoritative_minutes_url = None
        if official_minutes:
            if document_id is None:
                raise ValueError(
                    "Official-minutes loads require an authoritative document_id"
                )
            cur.execute(
                """SELECT source_url
                   FROM documents
                   WHERE id = %s
                     AND city_fips = %s
                     AND source_type = 'archive_center'
                     AND credibility_tier = 1
                     AND source_url IS NOT NULL""",
                (document_id, city_fips),
            )
            source_row = cur.fetchone()
            authoritative_minutes_url = (
                str(source_row[0]).strip()
                if source_row and source_row[0]
                else None
            )
            if not authoritative_minutes_url:
                raise ValueError(
                    "Official-minutes document is missing its authoritative "
                    "Tier 1 source_url"
                )

        # Serialize writers for one logical meeting. This makes the
        # agenda<minutes precedence rule safe when detector and scheduled
        # workflows overlap.
        meeting_lock_key = "|".join((
            city_fips,
            str(data.get("meeting_date") or ""),
            str(data.get("meeting_type", "regular")),
            str(body_id or ""),
        ))
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (meeting_lock_key,),
        )
        if source_meeting_guid:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"escribe-guid|{city_fips}|{source_meeting_guid}",),
            )
            # A natural-key fallback may adopt one legacy row that has no
            # upstream identity. It must never merge two distinct eSCRIBE
            # sessions that happen on the same date for the same body/type.
            cur.execute(
                """SELECT m.source_meeting_guid
                   FROM meetings m
                   WHERE m.city_fips = %s
                     AND m.meeting_date = %s
                     AND m.meeting_type = %s
                     AND m.body_id IS NOT DISTINCT FROM %s
                     AND m.source_meeting_guid IS NOT NULL
                     AND m.source_meeting_guid <> %s
                   LIMIT 1""",
                (
                    city_fips,
                    data.get("meeting_date"),
                    data.get("meeting_type", "regular"),
                    str(body_id) if body_id else None,
                    source_meeting_guid,
                ),
            )
            collision = cur.fetchone()
            if collision:
                raise RuntimeError(
                    "Refusing to merge distinct eSCRIBE GUIDs through the "
                    "same-day meeting fallback"
                )

        # ── Meeting ──
        # body_id is NOT NULL after migration 037. All meetings belong to a body.
        cur.execute(
            """SELECT m.id,
                      (
                        d.source_type = 'archive_center'
                        OR EXISTS (
                          SELECT 1 FROM agenda_items ai
                          WHERE ai.meeting_id = m.id
                            AND ai.agenda_source_authority = 'minutes'
                        )
                        OR EXISTS (
                          SELECT 1 FROM agenda_items ai
                          JOIN motions mo ON mo.agenda_item_id = ai.id
                          WHERE ai.meeting_id = m.id
                            AND mo.source = 'minutes'
                        )
                      ) AS minutes_loaded
               FROM meetings m
               LEFT JOIN documents d ON d.id = m.document_id
               WHERE m.city_fips = %s
                 AND (
                   (%s IS NOT NULL AND m.source_meeting_guid = %s)
                    OR (
                      m.meeting_date = %s
                      AND m.meeting_type = %s
                      AND m.body_id IS NOT DISTINCT FROM %s
                      AND (
                        %s IS NULL OR m.source_meeting_guid IS NULL
                      )
                    )
                 )
               ORDER BY (
                 %s IS NOT NULL AND m.source_meeting_guid = %s
               ) DESC
               LIMIT 1""",
            (
                city_fips,
                source_meeting_guid,
                source_meeting_guid,
                data.get("meeting_date"),
                data.get("meeting_type", "regular"),
                str(body_id) if body_id else None,
                source_meeting_guid,
                source_meeting_guid,
                source_meeting_guid,
            ),
        )
        target_meeting = cur.fetchone()
        if target_meeting:
            # Date locks serialize ordinary agenda/minutes writers; this
            # persisted-ID lock also serializes a GUID-based reschedule with a
            # minutes writer still addressing the old date. Re-read authority
            # after acquiring it so meeting-level fields cannot be downgraded.
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"meeting-id|{target_meeting[0]}",),
            )
            cur.execute(
                """SELECT (
                         d.source_type = 'archive_center'
                         OR EXISTS (
                           SELECT 1 FROM agenda_items ai
                           WHERE ai.meeting_id = m.id
                             AND ai.agenda_source_authority = 'minutes'
                         )
                         OR EXISTS (
                           SELECT 1 FROM agenda_items ai
                           JOIN motions mo ON mo.agenda_item_id = ai.id
                           WHERE ai.meeting_id = m.id
                             AND mo.source = 'minutes'
                         )
                       ) AS minutes_loaded
                   FROM meetings m
                   LEFT JOIN documents d ON d.id = m.document_id
                   WHERE m.id = %s""",
                (target_meeting[0],),
            )
            refreshed_authority = cur.fetchone()
            target_meeting = (
                target_meeting[0],
                bool(refreshed_authority and refreshed_authority[0]),
            )
        if (
            authoritative_agenda_revision
            and source_meeting_guid
            and source_observed_at
        ):
            cur.execute(
                """SELECT EXISTS (
                     SELECT 1 FROM documents d
                     WHERE d.city_fips = %s
                       AND d.source_type = 'escribemeetings'
                       AND d.metadata->>'meeting_guid' = %s
                       AND d.metadata ? 'agenda_revision_applied_sha256'
                       AND d.metadata ? 'agenda_revision_observed_at'
                       AND (d.metadata->>'agenda_revision_observed_at')::timestamptz
                         > %s::timestamptz
                   )""",
                (city_fips, source_meeting_guid, source_observed_at),
            )
            stale_observation = cur.fetchone()
            if stale_observation and stale_observation[0]:
                raise RuntimeError(
                    "A newer eSCRIBE agenda observation already committed"
                )
        preserve_minutes_fields = bool(
            authoritative_agenda_revision
            and isinstance(target_meeting, (tuple, list))
            and len(target_meeting) > 1
            and target_meeting[1]
        )
        if target_meeting:
            cur.execute(
                """UPDATE meetings
                   SET document_id = CASE WHEN %s
                         THEN document_id ELSE %s END,
                       meeting_date = CASE WHEN %s
                         THEN meeting_date ELSE %s END,
                       meeting_type = CASE WHEN %s
                         THEN meeting_type ELSE %s END,
                       call_to_order_time = CASE WHEN %s
                         THEN call_to_order_time ELSE %s END,
                       adjournment_time = CASE WHEN %s
                         THEN adjournment_time ELSE %s END,
                       presiding_officer = CASE WHEN %s
                         THEN presiding_officer ELSE %s END,
                       agenda_url = COALESCE(%s, agenda_url),
                       minutes_url = COALESCE(
                         NULLIF(BTRIM(minutes_url), ''), %s
                       ),
                       body_id = CASE WHEN %s
                         THEN body_id ELSE %s END,
                       source_meeting_guid = COALESCE(
                         %s, source_meeting_guid
                       ),
                       source_cancelled_at = CASE WHEN %s
                         THEN NULL ELSE source_cancelled_at END
                   WHERE id = %s
                   RETURNING id""",
                (
                    preserve_minutes_fields,
                    document_id,
                    preserve_minutes_fields,
                    data.get("meeting_date"),
                    preserve_minutes_fields,
                    data.get("meeting_type", "regular"),
                    preserve_minutes_fields,
                    data.get("call_to_order_time"),
                    preserve_minutes_fields,
                    data.get("adjournment_time")
                    or (data.get("adjournment", {}) or {}).get("time"),
                    preserve_minutes_fields,
                    data.get("presiding_officer"),
                    agenda_url,
                    authoritative_minutes_url,
                    preserve_minutes_fields,
                    str(body_id) if body_id else None,
                    source_meeting_guid,
                    bool(authoritative_agenda_revision or official_minutes),
                    target_meeting[0],
                ),
            )
        else:
            cur.execute(
                """INSERT INTO meetings
                   (id, city_fips, document_id, meeting_date, meeting_type,
                    call_to_order_time, adjournment_time, presiding_officer,
                    adjourned_in_memory_of, next_meeting_date, metadata,
                    body_id, agenda_url, minutes_url, source_meeting_guid)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s)
                   ON CONFLICT (city_fips, meeting_date, meeting_type, body_id)
                   DO UPDATE SET
                     document_id = EXCLUDED.document_id,
                     call_to_order_time = EXCLUDED.call_to_order_time,
                     adjournment_time = EXCLUDED.adjournment_time,
                     presiding_officer = EXCLUDED.presiding_officer,
                     agenda_url = COALESCE(
                       EXCLUDED.agenda_url, meetings.agenda_url
                     ),
                     minutes_url = COALESCE(
                       NULLIF(BTRIM(meetings.minutes_url), ''),
                       EXCLUDED.minutes_url
                     ),
                     source_meeting_guid = COALESCE(
                       EXCLUDED.source_meeting_guid,
                       meetings.source_meeting_guid
                     ),
                      source_cancelled_at = CASE WHEN %s
                        THEN NULL ELSE meetings.source_cancelled_at END
                   WHERE EXCLUDED.source_meeting_guid IS NULL
                      OR meetings.source_meeting_guid IS NULL
                      OR meetings.source_meeting_guid
                         = EXCLUDED.source_meeting_guid
                   RETURNING id""",
                (
                    meeting_id, city_fips, document_id,
                    data.get("meeting_date"),
                    data.get("meeting_type", "regular"),
                    data.get("call_to_order_time"),
                    data.get("adjournment_time")
                    or (data.get("adjournment", {}) or {}).get("time"),
                    data.get("presiding_officer"),
                    (data.get("adjournment", {}) or {}).get("in_memory_of")
                    or (data.get("adjournment", {}) or {}).get("in_honor_of"),
                    (data.get("adjournment", {}) or {}).get("next_meeting"),
                    json.dumps(data.get("_metadata", {})),
                    str(body_id) if body_id else None,
                    agenda_url,
                    authoritative_minutes_url,
                    source_meeting_guid,
                    bool(authoritative_agenda_revision or official_minutes),
                ),
            )
        meeting_row = cur.fetchone()
        if not meeting_row:
            raise RuntimeError(
                "Refusing same-day meeting upsert because the existing row "
                "belongs to a different eSCRIBE GUID"
            )
        meeting_id = meeting_row[0]
        agenda_revision_changed = False
        if authoritative_agenda_revision:
            attachment_changed_item_ids: set = set()
            cur.execute(
                """SELECT ai.agenda_source_authority,
                          ai.agenda_source_revision_sha256
                   FROM agenda_items ai
                   WHERE ai.meeting_id = %s
                     AND ai.agenda_source_authority <> 'minutes'
                     AND ai.agenda_source_retired_at IS NULL""",
                (meeting_id,),
            )
            agenda_revision_changed = _active_agenda_revision_changed(
                cur.fetchall(), authoritative_agenda_revision
            )

        # ── Supersede transcript-sourced motions/votes ──
        # When official minutes arrive, they are ground truth — delete any
        # preliminary motions+votes that extract_transcript_votes.py wrote
        # earlier with source='transcript'. The minutes-derived rows that
        # follow will fill in correctly. (S24.23, 2026-04-26.)
        # Only official minutes supersede preliminary transcript votes.  An
        # eSCRIBE agenda amendment has no outcome evidence and must never erase
        # transcript-derived meeting history merely because its HTML changed.
        if official_minutes and official_motion_replacement_numbers:
            cur.execute(
                """DELETE FROM motions
                   WHERE source = 'transcript'
                     AND agenda_item_id IN (
                       SELECT id FROM agenda_items
                       WHERE meeting_id = %s
                         AND item_number = ANY(%s)
                     )
                """,
                (
                    meeting_id,
                    sorted(set(official_motion_replacement_numbers)),
                ),
            )

        # ── Attendance ──
        for member in data.get("members_present", []):
            official_id = _officials.ensure_official(conn, city_fips, member["name"], member.get("role", default_role), commit=False)
            # Check if this member was late
            late_info = next(
                (m for m in data.get("members_late", []) if _officials._normalize_name(m["name"]) == _officials._normalize_name(member["name"])),
                None,
            )
            status = "late" if late_info else "present"
            notes = late_info.get("notes") if late_info else None
            cur.execute(
                """INSERT INTO meeting_attendance (id, meeting_id, official_id, status, notes, body_id)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (meeting_id, official_id) DO NOTHING""",
                (uuid.uuid4(), meeting_id, official_id, status, notes, str(body_id) if body_id else None),
            )

        for member in data.get("members_absent", []):
            official_id = _officials.ensure_official(conn, city_fips, member["name"], member.get("role", default_role), commit=False)
            cur.execute(
                """INSERT INTO meeting_attendance (id, meeting_id, official_id, status, notes, body_id)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (meeting_id, official_id) DO NOTHING""",
                (uuid.uuid4(), meeting_id, official_id, "absent", member.get("notes"), str(body_id) if body_id else None),
            )

        # ── Closed Session Items ──
        for item in data.get("closed_session_items", []):
            cur.execute(
                """INSERT INTO closed_session_items
                   (id, meeting_id, item_number, legal_authority, description, parties, reportable_action)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (meeting_id, item_number) DO NOTHING""",
                (
                    uuid.uuid4(), meeting_id,
                    item.get("item_number", ""),
                    item.get("legal_authority", ""),
                    item.get("description", ""),
                    item.get("parties", []),
                    item.get("reportable_action"),
                ),
            )

        # ── Consent Calendar ──
        consent = data.get("consent_calendar", {})
        if consent and consent.get("items"):
            # Build set of item numbers pulled for separate vote
            pulled_numbers = set()
            for p in consent.get("items_pulled_for_separate_vote", []):
                # Extract item number (everything before first space or paren)
                # e.g., "W.3.a (Update on...)" → "W.3.a"
                num = p.split(" ")[0].split("(")[0].strip()
                if num:
                    pulled_numbers.add(num)

            for consent_item in consent["items"]:
                item_num = consent_item.get("item_number", "")
                # Skip section headers (bare letters like "V", "M")
                if item_num and re.match(r'^[A-Z]+$', item_num):
                    continue
                was_pulled = item_num in pulled_numbers
                ai_id = uuid.uuid4()
                consent_params = (
                    ai_id, meeting_id,
                    item_num,
                    sanitize_text(consent_item.get("title", "")),
                    sanitize_text(consent_item.get("description")),
                    consent_item.get("department"),
                    consent_item.get("staff_contact"),
                    consent_item.get("category"),
                    was_pulled,
                    consent_item.get("resolution_number"),
                    consent_item.get("financial_amount"),
                )
                if authoritative_agenda_revision:
                    cur.execute(
                        """INSERT INTO agenda_items
                           (id, meeting_id, item_number, title, description,
                            department, staff_contact, category,
                            is_consent_calendar, was_pulled_from_consent,
                            resolution_number, financial_amount,
                            continued_from, continued_to,
                            agenda_source_authority,
                            agenda_source_revision_sha256,
                            agenda_source_retired_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                                   TRUE, %s, %s, %s, NULL, NULL,
                                   'agenda', %s, NULL)
                           ON CONFLICT (meeting_id, item_number) DO UPDATE
                           SET title = EXCLUDED.title,
                               description = EXCLUDED.description,
                               department = EXCLUDED.department,
                               staff_contact = EXCLUDED.staff_contact,
                               category = EXCLUDED.category,
                               is_consent_calendar = TRUE,
                               was_pulled_from_consent =
                                 EXCLUDED.was_pulled_from_consent,
                               resolution_number = EXCLUDED.resolution_number,
                               financial_amount = EXCLUDED.financial_amount,
                               continued_from = NULL,
                               continued_to = NULL,
                               agenda_source_authority = 'agenda',
                               agenda_source_revision_sha256 =
                                 EXCLUDED.agenda_source_revision_sha256,
                               agenda_source_retired_at = NULL
                           WHERE agenda_items.agenda_source_authority
                             <> 'minutes'""",
                        consent_params + (authoritative_agenda_revision,),
                    )
                else:
                    cur.execute(
                        """INSERT INTO agenda_items
                           (id, meeting_id, item_number, title, description,
                            department, staff_contact, category,
                            is_consent_calendar, was_pulled_from_consent,
                            resolution_number, financial_amount)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                                   TRUE, %s, %s, %s)
                           ON CONFLICT (meeting_id, item_number) DO UPDATE
                           SET title = COALESCE(EXCLUDED.title, agenda_items.title),
                               description = COALESCE(
                                 EXCLUDED.description, agenda_items.description
                               ),
                               category = COALESCE(
                                 EXCLUDED.category, agenda_items.category
                               ),
                               was_pulled_from_consent =
                                 EXCLUDED.was_pulled_from_consent""",
                        consent_params,
                    )

            # Record the consent calendar block vote on ALL non-pulled items.
            # The block vote applies equally to every consent item that wasn't
            # pulled for separate consideration.
            if consent.get("votes") and str(
                consent.get("result") or ""
            ).strip():
                # Collect DB ids for all non-pulled consent items
                non_pulled_nums = [
                    ci.get("item_number", "")
                    for ci in consent["items"]
                    if ci.get("item_number", "") not in pulled_numbers
                    and not re.match(r'^[A-Z]+$', ci.get("item_number", ""))
                ]
                for item_num in non_pulled_nums:
                    cur.execute(
                        "SELECT id FROM agenda_items WHERE meeting_id = %s AND item_number = %s",
                        (meeting_id, item_num),
                    )
                    row = cur.fetchone()
                    if not row:
                        continue
                    motion_id = uuid.uuid4()
                    cur.execute(
                        """INSERT INTO motions
                           (id, agenda_item_id, motion_type, motion_text,
                            moved_by, seconded_by, result, vote_tally, sequence_number)
                           VALUES (%s, %s, 'original', %s, %s, %s, %s, %s, 1)
                           ON CONFLICT (agenda_item_id, motion_type,
                               (COALESCE(motion_text, '')), (COALESCE(result, '')))
                           DO UPDATE SET id = motions.id
                           RETURNING id""",
                        (
                            motion_id, row[0],
                            "Approve consent calendar",
                            consent.get("motion_by"),
                            consent.get("seconded_by"),
                            consent["result"],
                            consent.get("vote_tally"),
                        ),
                    )
                    motion_id = cur.fetchone()[0]
                    for vote in consent["votes"]:
                        off_id = _officials.ensure_official(conn, city_fips, vote["council_member"], vote.get("role", default_role), commit=False)
                        cur.execute(
                            """INSERT INTO votes (id, motion_id, official_id, official_name, official_role, vote_choice)
                               VALUES (%s, %s, %s, %s, %s, %s)
                               ON CONFLICT (motion_id, official_name) DO NOTHING""",
                            (uuid.uuid4(), motion_id, off_id, vote["council_member"], vote.get("role"), vote["vote"]),
                        )

        # ── Action Items + Housing Authority Items ──
        # Housing authority items (M.* prefix from eSCRIBE) use the same schema
        # as action items. Process them together so they appear in agenda_items.
        for item in data.get("action_items", []) + data.get("housing_authority_items", []):
            ai_id = uuid.uuid4()
            action_params = (
                ai_id, meeting_id,
                item.get("item_number", ""),
                sanitize_text(item.get("title", "")),
                sanitize_text(item.get("description")),
                item.get("department"),
                item.get("staff_contact"),
                item.get("category"),
                item.get("resolution_number"),
                item.get("financial_amount"),
                item.get("continued_from"),
                item.get("continued_to"),
            )
            if authoritative_agenda_revision:
                cur.execute(
                    """INSERT INTO agenda_items
                       (id, meeting_id, item_number, title, description,
                        department, staff_contact, category,
                        is_consent_calendar, was_pulled_from_consent,
                        resolution_number, financial_amount,
                        continued_from, continued_to,
                        agenda_source_authority,
                        agenda_source_revision_sha256,
                        agenda_source_retired_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                               FALSE, FALSE, %s, %s, %s, %s,
                               'agenda', %s, NULL)
                       ON CONFLICT (meeting_id, item_number) DO UPDATE
                       SET title = EXCLUDED.title,
                           description = EXCLUDED.description,
                           department = EXCLUDED.department,
                           staff_contact = EXCLUDED.staff_contact,
                           category = EXCLUDED.category,
                           is_consent_calendar = FALSE,
                           was_pulled_from_consent = FALSE,
                           resolution_number = EXCLUDED.resolution_number,
                           financial_amount = EXCLUDED.financial_amount,
                           continued_from = EXCLUDED.continued_from,
                           continued_to = EXCLUDED.continued_to,
                           agenda_source_authority = 'agenda',
                           agenda_source_revision_sha256 =
                             EXCLUDED.agenda_source_revision_sha256,
                           agenda_source_retired_at = NULL
                       WHERE agenda_items.agenda_source_authority <> 'minutes'
                       RETURNING id""",
                    action_params + (authoritative_agenda_revision,),
                )
            else:
                cur.execute(
                    """INSERT INTO agenda_items
                       (id, meeting_id, item_number, title, description,
                        department, staff_contact, category,
                        is_consent_calendar, resolution_number,
                        financial_amount, continued_from, continued_to)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                               FALSE, %s, %s, %s, %s)
                       ON CONFLICT (meeting_id, item_number) DO UPDATE
                       SET title = COALESCE(EXCLUDED.title, agenda_items.title),
                           description = COALESCE(
                             EXCLUDED.description, agenda_items.description
                           ),
                           category = COALESCE(
                             EXCLUDED.category, agenda_items.category
                           )
                       RETURNING id""",
                    action_params,
                )
            # Use actual row id (may differ from ai_id if row already existed)
            actual_row = cur.fetchone()
            if actual_row:
                actual_ai_id = actual_row[0]
            else:
                cur.execute(
                    """SELECT id FROM agenda_items
                       WHERE meeting_id = %s AND item_number = %s""",
                    (meeting_id, item.get("item_number", "")),
                )
                actual_ai_id = cur.fetchone()[0]

            for seq, motion in enumerate(item.get("motions", []), start=1):
                motion_id = uuid.uuid4()
                cur.execute(
                    """INSERT INTO motions
                       (id, agenda_item_id, motion_type, motion_text,
                        moved_by, seconded_by, result, vote_tally,
                        resolution_number, sequence_number)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (agenda_item_id, motion_type,
                           (COALESCE(motion_text, '')), (COALESCE(result, '')))
                       DO UPDATE SET id = motions.id
                       RETURNING id""",
                    (
                        motion_id, actual_ai_id,
                        motion.get("motion_type", "original"),
                        motion.get("motion_text", ""),
                        motion.get("motion_by"),
                        motion.get("seconded_by"),
                        motion.get("result"),
                        motion.get("vote_tally"),
                        motion.get("resolution_number"),
                        seq,
                    ),
                )
                motion_id = cur.fetchone()[0]

                for vote in motion.get("votes", []):
                    off_id = _officials.ensure_official(conn, city_fips, vote["council_member"], vote.get("role", default_role), commit=False)
                    cur.execute(
                        """INSERT INTO votes (id, motion_id, official_id, official_name, official_role, vote_choice)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON CONFLICT (motion_id, official_name) DO NOTHING""",
                        (uuid.uuid4(), motion_id, off_id, vote["council_member"], vote.get("role"), vote["vote"]),
                    )

                for amendment in motion.get("friendly_amendments", []):
                    cur.execute(
                        """INSERT INTO friendly_amendments (id, motion_id, proposed_by, description, accepted)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (uuid.uuid4(), motion_id, amendment.get("proposed_by", ""), amendment.get("description", ""), amendment.get("accepted", False)),
                    )

        # ── Public Comments ──
        for comment in data.get("public_comments_open_forum", []) + data.get("public_comments", []):
            related_items = comment.get("related_items", comment.get("related_agenda_items", []))
            # Try to link to an agenda item
            agenda_item_id = None
            if related_items:
                cur.execute(
                    "SELECT id FROM agenda_items WHERE meeting_id = %s AND item_number = %s",
                    (meeting_id, related_items[0]),
                )
                row = cur.fetchone()
                if row:
                    agenda_item_id = row[0]

            cur.execute(
                """INSERT INTO public_comments
                   (id, meeting_id, agenda_item_id, speaker_name, method, summary, comment_type)
                   VALUES (%s, %s, %s, %s, %s, %s, 'public')
                   ON CONFLICT (meeting_id,
                       (COALESCE(agenda_item_id::text, '')),
                       (COALESCE(speaker_name, '')),
                       (COALESCE(summary, '')))
                   DO NOTHING""",
                (
                    uuid.uuid4(), meeting_id, agenda_item_id,
                    comment.get("speaker_name", ""),
                    comment.get("method", "in_person"),
                    comment.get("summary"),
                ),
            )

        for comment in data.get("written_public_comments", []):
            related_items = comment.get("related_items", comment.get("related_agenda_items", []))
            agenda_item_id = None
            if related_items:
                cur.execute(
                    "SELECT id FROM agenda_items WHERE meeting_id = %s AND item_number = %s",
                    (meeting_id, related_items[0]),
                )
                row = cur.fetchone()
                if row:
                    agenda_item_id = row[0]

            cur.execute(
                """INSERT INTO public_comments
                   (id, meeting_id, agenda_item_id, speaker_name, method, summary, comment_type)
                   VALUES (%s, %s, %s, %s, %s, %s, 'written')
                   ON CONFLICT (meeting_id,
                       (COALESCE(agenda_item_id::text, '')),
                       (COALESCE(speaker_name, '')),
                       (COALESCE(summary, '')))
                   DO NOTHING""",
                (
                    uuid.uuid4(), meeting_id, agenda_item_id,
                    comment.get("speaker_name", ""),
                    comment.get("method", "email"),
                    comment.get("summary"),
                ),
            )

        if official_minutes:
            minute_numbers = sorted({
                str(item.get("item_number") or "").strip()
                for item in (
                    list((data.get("consent_calendar") or {}).get("items") or [])
                    + list(data.get("action_items") or [])
                    + list(data.get("housing_authority_items") or [])
                )
                if str(item.get("item_number") or "").strip()
                and not re.match(
                    r"^[A-Z]+$", str(item.get("item_number") or "").strip()
                )
            })
            if minute_numbers:
                cur.execute(
                    """UPDATE agenda_items
                       SET agenda_source_authority = 'minutes',
                           agenda_source_revision_sha256 = NULL,
                           agenda_source_retired_at = NULL
                       WHERE meeting_id = %s
                         AND item_number = ANY(%s)
                       RETURNING id""",
                    (meeting_id, minute_numbers),
                )
                minutes_item_ids = [row[0] for row in cur.fetchall()]
                # The minutes extraction may omit rows even when the source
                # PDF is official. Promote only exact matched item numbers;
                # absence is not mechanically proven withdrawal evidence.
                affected_item_ids = minutes_item_ids
                if affected_item_ids:
                    cur.execute(
                        """UPDATE agenda_items
                           SET plain_language_summary = NULL,
                               summary_headline = NULL,
                               plain_language_model = NULL,
                               plain_language_generated_at = NULL,
                               plain_language_summary_provenance = NULL,
                               topic_label = NULL,
                               proceeding_type = NULL,
                               proceeding_classification_attempts = 0,
                               proceeding_classification_last_error = NULL,
                               proceeding_classification_last_attempted_at = NULL,
                               proceeding_classification_dead_lettered_at = NULL,
                               proceeding_classification_claim_token = NULL,
                               proceeding_classification_claim_expires_at = NULL
                           WHERE id = ANY(%s)""",
                        (affected_item_ids,),
                    )
                    cur.execute(
                        "DELETE FROM agenda_items_embeddings WHERE id = ANY(%s)",
                        (affected_item_ids,),
                    )
                    cur.execute(
                        """DELETE FROM item_topics
                           WHERE agenda_item_id = ANY(%s)
                             AND source <> 'manual'""",
                        (affected_item_ids,),
                    )
                    cur.execute(
                        """DELETE FROM item_theme_narratives
                           WHERE agenda_item_id = ANY(%s)""",
                        (affected_item_ids,),
                    )
                    cur.execute(
                        """UPDATE conflict_flags
                           SET is_current = FALSE
                           WHERE agenda_item_id = ANY(%s)
                             AND is_current = TRUE""",
                        (affected_item_ids,),
                    )
                    cur.execute(
                        """UPDATE meetings
                           SET meeting_summary = NULL,
                               meeting_summary_provenance = NULL,
                               orientation_preview = NULL,
                               orientation_preview_provenance = NULL,
                               meeting_recap = NULL,
                               meeting_recap_provenance = NULL
                           WHERE id = %s""",
                        (meeting_id,),
                    )
                    cur.execute(
                        "DELETE FROM meetings_embeddings WHERE id = %s",
                        (meeting_id,),
                    )

        if authoritative_agenda_revision:
            # The incoming set is authoritative only because the caller proved
            # complete agenda publication and parsing before invoking this
            # boundary.  A NULL revision marks legacy/minutes/transcript rows;
            # those rows are deliberately outside eSCRIBE retirement scope.
            authoritative_numbers = sorted({
                str(item.get("item_number") or "").strip()
                for item in (
                    list((data.get("consent_calendar") or {}).get("items") or [])
                    + list(data.get("action_items") or [])
                    + list(data.get("housing_authority_items") or [])
                )
                if str(item.get("item_number") or "").strip()
                and not re.match(
                    r"^[A-Z]+$", str(item.get("item_number") or "").strip()
                )
            })
            if not authoritative_numbers:
                raise ValueError(
                    "authoritative eSCRIBE agenda has no structured item numbers"
                )

            cur.execute(
                """UPDATE agenda_items
                   SET agenda_source_retired_at = NOW(),
                       agenda_source_revision_sha256 = %s
                   WHERE meeting_id = %s
                     AND agenda_source_authority = 'agenda'
                     AND agenda_source_retired_at IS NULL
                     AND NOT (item_number = ANY(%s))
                   RETURNING id""",
                (
                    authoritative_agenda_revision,
                    meeting_id,
                    authoritative_numbers,
                ),
            )
            retired_item_ids = [row[0] for row in cur.fetchall()]
            if retired_item_ids:
                cur.execute(
                    """UPDATE agenda_item_attachments
                       SET source_retired_at = COALESCE(
                             source_retired_at, NOW()
                           ),
                           source_revision_sha256 = %s
                       WHERE agenda_item_id = ANY(%s)
                         AND source_revision_sha256 IS NOT NULL
                         AND source_retired_at IS NULL
                       RETURNING agenda_item_id""",
                    (authoritative_agenda_revision, retired_item_ids),
                )
                attachment_changed_item_ids.update(
                    row[0] for row in cur.fetchall()
                )
            cur.execute(
                """UPDATE agenda_item_attachments aia
                   SET source_retired_at = COALESCE(
                         aia.source_retired_at, NOW()
                       ),
                       source_revision_sha256 = %s
                   FROM agenda_items ai
                   WHERE ai.id = aia.agenda_item_id
                      AND ai.meeting_id = %s
                      AND ai.agenda_source_authority = 'agenda'
                      AND aia.source_retired_at IS NULL
                      AND aia.source_revision_sha256 IS NOT NULL
                      AND NOT (ai.item_number = ANY(%s))
                   RETURNING aia.agenda_item_id""",
                (
                    authoritative_agenda_revision,
                    meeting_id,
                    authoritative_numbers,
                ),
            )
            attachment_changed_item_ids.update(
                row[0] for row in cur.fetchall()
            )

            # The parsed HTML attachment list is complete per exact agenda
            # item. Reconcile by eSCRIBE DocumentId. Downloaded content hashes
            # prove publication; extractable text is optional and stored as
            # NULL when unavailable. Only rows carrying a prior source
            # revision are managed omission candidates; NULL-revision history
            # stays review-bound even at this exact item-number boundary.
            source_items = (
                list((data.get("consent_calendar") or {}).get("items") or [])
                + list(data.get("action_items") or [])
                + list(data.get("housing_authority_items") or [])
            )
            for source_item in source_items:
                item_number = str(
                    source_item.get("item_number") or ""
                ).strip()
                if not item_number or re.match(r"^[A-Z]+$", item_number):
                    continue
                cur.execute(
                    """SELECT id
                       FROM agenda_items
                       WHERE meeting_id = %s
                         AND item_number = %s
                         AND agenda_source_authority = 'agenda'
                         AND agenda_source_retired_at IS NULL""",
                    (meeting_id, item_number),
                )
                agenda_row = cur.fetchone()
                if not agenda_row:
                    continue
                agenda_item_id = agenda_row[0]
                active_document_ids: list[str] = []
                for attachment in source_item.get("attachments") or []:
                    source_document_id = str(
                        attachment.get("document_id") or ""
                    ).strip()
                    if not source_document_id:
                        raise ValueError(
                            f"eSCRIBE attachment on {item_number} has no "
                            "DocumentId"
                        )
                    active_document_ids.append(source_document_id)
                    extracted_text = attachment.get("extracted_text")
                    if (
                        not isinstance(extracted_text, str)
                        or not extracted_text.strip()
                    ):
                        # Downloaded bytes establish publication. Text is an
                        # optional derivative: DOCX/images and scanned PDFs
                        # legitimately have no locally extractable text. NULL
                        # keeps extraction errors/sentinels out of LLM inputs.
                        extracted_text = None
                    else:
                        extracted_text = extracted_text.strip()
                    source_content_sha256 = str(
                        attachment.get("source_content_sha256") or ""
                    ).strip().lower()
                    if not re.fullmatch(
                        r"[0-9a-f]{64}", source_content_sha256
                    ):
                        raise RuntimeError(
                            f"eSCRIBE attachment {source_document_id} on "
                            f"{item_number} lacks downloaded-byte proof"
                        )
                    char_count = (
                        len(extracted_text)
                        if extracted_text is not None
                        else None
                    )
                    cur.execute(
                        """SELECT source_content_sha256, source_retired_at,
                                  filename, source_url
                           FROM agenda_item_attachments
                           WHERE agenda_item_id = %s
                             AND document_id = %s
                             AND source_revision_sha256 IS NOT NULL""",
                        (agenda_item_id, source_document_id),
                    )
                    prior_attachment_rows = cur.fetchall()
                    if not prior_attachment_rows or any(
                        prior_hash != source_content_sha256
                        or prior_retired_at is not None
                        or prior_filename
                          != (attachment.get("filename") or "Unnamed")
                        or prior_url != attachment.get("source_url")
                        for (
                            prior_hash,
                            prior_retired_at,
                            prior_filename,
                            prior_url,
                        ) in prior_attachment_rows
                    ):
                        attachment_changed_item_ids.add(agenda_item_id)
                    cur.execute(
                        """UPDATE agenda_item_attachments
                           SET filename = %s,
                               source_url = %s,
                               extracted_text = %s,
                               char_count = %s,
                               source_content_sha256 = %s,
                               source_revision_sha256 = %s,
                               source_retired_at = NULL
                           WHERE agenda_item_id = %s
                             AND document_id = %s
                             AND source_revision_sha256 IS NOT NULL
                           RETURNING id""",
                        (
                            attachment.get("filename") or "Unnamed",
                            attachment.get("source_url"),
                            extracted_text,
                            char_count,
                            source_content_sha256,
                            authoritative_agenda_revision,
                            agenda_item_id,
                            source_document_id,
                        ),
                    )
                    existing_attachment_rows = cur.fetchall()
                    if not existing_attachment_rows:
                        cur.execute(
                            """INSERT INTO agenda_item_attachments
                               (agenda_item_id, document_id, filename,
                                source_url, extracted_text, char_count,
                                source_content_sha256,
                                source_revision_sha256, source_retired_at)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                                       NULL)""",
                            (
                                agenda_item_id,
                                source_document_id,
                                attachment.get("filename") or "Unnamed",
                                attachment.get("source_url"),
                                extracted_text,
                                char_count,
                                source_content_sha256,
                                authoritative_agenda_revision,
                            ),
                        )
                if active_document_ids:
                    cur.execute(
                        """UPDATE agenda_item_attachments
                           SET source_retired_at = COALESCE(
                                 source_retired_at, NOW()
                               ),
                               source_revision_sha256 = %s
                            WHERE agenda_item_id = %s
                              AND source_retired_at IS NULL
                              AND source_revision_sha256 IS NOT NULL
                              AND (
                                document_id IS NULL
                               OR NOT (document_id = ANY(%s))
                             )
                           RETURNING agenda_item_id""",
                        (
                            authoritative_agenda_revision,
                            agenda_item_id,
                            sorted(set(active_document_ids)),
                        ),
                    )
                    attachment_changed_item_ids.update(
                        row[0] for row in cur.fetchall()
                    )
                else:
                    cur.execute(
                        """UPDATE agenda_item_attachments
                           SET source_retired_at = COALESCE(
                                 source_retired_at, NOW()
                               ),
                               source_revision_sha256 = %s
                            WHERE agenda_item_id = %s
                              AND source_retired_at IS NULL
                              AND source_revision_sha256 IS NOT NULL
                            RETURNING agenda_item_id""",
                        (authoritative_agenda_revision, agenda_item_id),
                    )
                    attachment_changed_item_ids.update(
                        row[0] for row in cur.fetchall()
                    )

            # Any source amendment can invalidate text-derived artifacts even
            # when the item number is unchanged. Preserve raw meeting history
            # and human topic assignments, while clearing/retires derivatives
            # so automatic jobs regenerate from the new source-closest data.
            active_agenda_item_ids = []
            if agenda_revision_changed:
                cur.execute(
                    """SELECT id
                       FROM agenda_items
                       WHERE meeting_id = %s
                         AND agenda_source_authority = 'agenda'
                         AND agenda_source_retired_at IS NULL""",
                    (meeting_id,),
                )
                active_agenda_item_ids = [row[0] for row in cur.fetchall()]
            managed_item_ids = _agenda_reconciliation_invalidation_ids(
                attachment_changed_item_ids,
                retired_item_ids,
                active_agenda_item_ids,
                agenda_revision_changed=agenda_revision_changed,
            )
            if managed_item_ids:
                cur.execute(
                    """UPDATE agenda_items
                       SET plain_language_summary = NULL,
                           summary_headline = NULL,
                           plain_language_model = NULL,
                           plain_language_generated_at = NULL,
                           plain_language_summary_provenance = NULL,
                           topic_label = NULL,
                           proceeding_type = NULL,
                           proceeding_classification_attempts = 0,
                           proceeding_classification_last_error = NULL,
                           proceeding_classification_last_attempted_at = NULL,
                           proceeding_classification_dead_lettered_at = NULL,
                           proceeding_classification_claim_token = NULL,
                           proceeding_classification_claim_expires_at = NULL
                       WHERE id = ANY(%s)""",
                    (managed_item_ids,),
                )
                cur.execute(
                    "DELETE FROM agenda_items_embeddings WHERE id = ANY(%s)",
                    (managed_item_ids,),
                )
                cur.execute(
                    """DELETE FROM item_topics
                       WHERE agenda_item_id = ANY(%s)
                         AND source <> 'manual'""",
                    (managed_item_ids,),
                )
                cur.execute(
                    """DELETE FROM item_theme_narratives
                       WHERE agenda_item_id = ANY(%s)""",
                    (managed_item_ids,),
                )
                cur.execute(
                    """UPDATE conflict_flags
                       SET is_current = FALSE
                       WHERE agenda_item_id = ANY(%s)
                         AND is_current = TRUE""",
                    (managed_item_ids,),
                )

            if managed_item_ids:
                cur.execute(
                    """UPDATE meetings
                       SET meeting_summary = NULL,
                           meeting_summary_provenance = NULL,
                           orientation_preview = NULL,
                           orientation_preview_provenance = NULL,
                           meeting_recap = NULL,
                           meeting_recap_provenance = NULL
                       WHERE id = %s""",
                    (meeting_id,),
                )
                cur.execute(
                    "DELETE FROM meetings_embeddings WHERE id = %s",
                    (meeting_id,),
                )

    if commit:
        conn.commit()
    return meeting_id


def retire_escribe_agenda(
    conn,
    *,
    city_fips: str,
    meeting_date: str,
    meeting_type: str,
    body_id: uuid.UUID | str | None,
    agenda_revision_sha256: str,
    meeting_cancelled: bool = False,
    source_meeting_guid: str | None = None,
    source_observed_at: str | None = None,
    commit: bool = True,
) -> tuple[int, bool]:
    """Soft-retire agenda-owned rows after proven agenda withdrawal.

    Returns ``(retired_count, official_minutes_fenced)``. The same advisory
    lock and persisted minutes check used by the loader close the race with a
    concurrent official-minutes extraction. Legacy and minutes-owned rows are
    never inferred to be retractable agenda data.
    """
    lock_key = "|".join((
        city_fips,
        str(meeting_date or ""),
        str(meeting_type or "regular"),
        str(body_id or ""),
    ))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (lock_key,),
        )
        if source_meeting_guid:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"escribe-guid|{city_fips}|{source_meeting_guid}",),
            )
        if source_meeting_guid and source_observed_at:
            cur.execute(
                """SELECT EXISTS (
                     SELECT 1 FROM documents d
                     WHERE d.city_fips = %s
                       AND d.source_type = 'escribemeetings'
                       AND d.metadata->>'meeting_guid' = %s
                       AND d.metadata ? 'agenda_revision_applied_sha256'
                       AND d.metadata ? 'agenda_revision_observed_at'
                       AND (d.metadata->>'agenda_revision_observed_at')::timestamptz
                         > %s::timestamptz
                   )""",
                (city_fips, source_meeting_guid, source_observed_at),
            )
            stale_observation = cur.fetchone()
            if stale_observation and stale_observation[0]:
                raise RuntimeError(
                    "A newer eSCRIBE withdrawal observation already committed"
                )
        cur.execute(
            """SELECT m.id,
                      (
                        m.minutes_url IS NOT NULL
                        OR d.source_type = 'archive_center'
                        OR EXISTS (
                          SELECT 1 FROM agenda_items ai
                          WHERE ai.meeting_id = m.id
                            AND ai.agenda_source_authority = 'minutes'
                        )
                        OR EXISTS (
                          SELECT 1
                          FROM agenda_items ai
                          JOIN motions mo ON mo.agenda_item_id = ai.id
                          WHERE ai.meeting_id = m.id
                            AND mo.source = 'minutes'
                        )
                      ) AS official_minutes_loaded
               FROM meetings m
               LEFT JOIN documents d ON d.id = m.document_id
               WHERE m.city_fips = %s
                 AND (
                   (%s IS NOT NULL AND m.source_meeting_guid = %s)
                   OR (
                     m.meeting_date = %s
                     AND m.meeting_type = %s
                     AND m.body_id IS NOT DISTINCT FROM %s
                     AND (
                       %s IS NULL OR m.source_meeting_guid IS NULL
                     )
                   )
                 )
               LIMIT 1""",
            (
                city_fips,
                source_meeting_guid,
                source_meeting_guid,
                meeting_date,
                meeting_type,
                str(body_id) if body_id else None,
                source_meeting_guid,
            ),
        )
        row = cur.fetchone()
        if not isinstance(row, (tuple, list)) or not row:
            if commit:
                conn.commit()
            return 0, False
        meeting_id, official_minutes_loaded = row[0], bool(row[1])
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"meeting-id|{meeting_id}",),
        )
        # Re-check after the persisted-ID lock; minutes could have committed
        # while this withdrawal waited on a GUID/date race.
        cur.execute(
            """SELECT (
                     m.minutes_url IS NOT NULL
                     OR d.source_type = 'archive_center'
                     OR EXISTS (
                       SELECT 1 FROM agenda_items ai
                       WHERE ai.meeting_id = m.id
                         AND ai.agenda_source_authority = 'minutes'
                     )
                     OR EXISTS (
                       SELECT 1 FROM agenda_items ai
                       JOIN motions mo ON mo.agenda_item_id = ai.id
                       WHERE ai.meeting_id = m.id
                         AND mo.source = 'minutes'
                     )
                   )
               FROM meetings m
               LEFT JOIN documents d ON d.id = m.document_id
               WHERE m.id = %s""",
            (meeting_id,),
        )
        refreshed_minutes = cur.fetchone()
        official_minutes_loaded = bool(
            refreshed_minutes and refreshed_minutes[0]
        )

        # Only attachments already carrying a source revision are proven to be
        # managed by this reconciliation contract.  Migration-133 NULL rows
        # include legacy/minutes packets whose ownership has not been proven;
        # preserve them for bounded review rather than treating NULL as an
        # implicit tombstone candidate.
        cur.execute(
            """UPDATE agenda_item_attachments aia
               SET source_retired_at = COALESCE(
                     aia.source_retired_at, NOW()
                   ),
                   source_revision_sha256 = %s
               FROM agenda_items ai
                WHERE ai.id = aia.agenda_item_id
                  AND ai.meeting_id = %s
                  AND ai.agenda_source_authority = 'agenda'
                  AND aia.source_retired_at IS NULL
                  AND aia.source_revision_sha256 IS NOT NULL
                RETURNING aia.agenda_item_id""",
            (agenda_revision_sha256, meeting_id),
        )
        attachment_item_ids = [row[0] for row in cur.fetchall()]

        if meeting_cancelled and not official_minutes_loaded:
            cur.execute(
                "UPDATE meetings SET source_cancelled_at = NOW() WHERE id = %s",
                (meeting_id,),
            )

        cur.execute(
            """UPDATE agenda_items
               SET agenda_source_retired_at = NOW(),
                   agenda_source_revision_sha256 = %s
               WHERE meeting_id = %s
                 AND agenda_source_authority = 'agenda'
                 AND agenda_source_retired_at IS NULL
               RETURNING id""",
            (agenda_revision_sha256, meeting_id),
        )
        retired_ids = [retired[0] for retired in cur.fetchall()]
        affected_item_ids = list(dict.fromkeys(
            attachment_item_ids + retired_ids
        ))
        if affected_item_ids:
            cur.execute(
                """UPDATE agenda_items
                   SET plain_language_summary = NULL,
                       summary_headline = NULL,
                       plain_language_model = NULL,
                       plain_language_generated_at = NULL,
                       plain_language_summary_provenance = NULL,
                       topic_label = NULL,
                       proceeding_type = NULL,
                       proceeding_classification_attempts = 0,
                       proceeding_classification_last_error = NULL,
                       proceeding_classification_last_attempted_at = NULL,
                       proceeding_classification_dead_lettered_at = NULL,
                       proceeding_classification_claim_token = NULL,
                       proceeding_classification_claim_expires_at = NULL
                   WHERE id = ANY(%s)""",
                (affected_item_ids,),
            )
            cur.execute(
                "DELETE FROM agenda_items_embeddings WHERE id = ANY(%s)",
                (affected_item_ids,),
            )
            cur.execute(
                """DELETE FROM item_topics
                   WHERE agenda_item_id = ANY(%s)
                     AND source <> 'manual'""",
                (affected_item_ids,),
            )
            cur.execute(
                """DELETE FROM item_theme_narratives
                   WHERE agenda_item_id = ANY(%s)""",
                (affected_item_ids,),
            )
            cur.execute(
                """UPDATE conflict_flags SET is_current = FALSE
                   WHERE agenda_item_id = ANY(%s) AND is_current = TRUE""",
                (affected_item_ids,),
            )
            cur.execute(
                """UPDATE meetings
                   SET meeting_summary = NULL,
                       meeting_summary_provenance = NULL,
                       orientation_preview = NULL,
                       orientation_preview_provenance = NULL,
                       meeting_recap = NULL,
                       meeting_recap_provenance = NULL
                   WHERE id = %s""",
                (meeting_id,),
            )
            cur.execute(
                "DELETE FROM meetings_embeddings WHERE id = %s",
                (meeting_id,),
            )

    if commit:
        conn.commit()
    return len(retired_ids), official_minutes_loaded
