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


def load_meeting_to_db(
    conn,
    data: dict,
    document_id: uuid.UUID = None,
    city_fips: str = RICHMOND_FIPS,
    body_id: uuid.UUID = None,
    agenda_url: str | None = None,
) -> uuid.UUID:
    """Load extracted meeting JSON into Layer 2 structured tables.

    This is the main entry point for populating the structured schema
    from Claude's extraction output.

    Args:
        body_id: FK to bodies table. When provided, derives the default
            role for members (e.g., 'commissioner' for commissions)
            instead of defaulting to 'councilmember'.

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
        # ── Meeting ──
        # body_id is NOT NULL after migration 037. All meetings belong to a body.
        cur.execute(
            """INSERT INTO meetings
               (id, city_fips, document_id, meeting_date, meeting_type,
                call_to_order_time, adjournment_time, presiding_officer,
                adjourned_in_memory_of, next_meeting_date, metadata, body_id,
                agenda_url)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (city_fips, meeting_date, meeting_type, body_id)
               DO UPDATE
               SET document_id = EXCLUDED.document_id,
                   call_to_order_time = EXCLUDED.call_to_order_time,
                   adjournment_time = EXCLUDED.adjournment_time,
                   presiding_officer = EXCLUDED.presiding_officer,
                   agenda_url = COALESCE(EXCLUDED.agenda_url, meetings.agenda_url)
               RETURNING id""",
            (
                meeting_id, city_fips, document_id,
                data.get("meeting_date"),
                data.get("meeting_type", "regular"),
                data.get("call_to_order_time"),
                data.get("adjournment_time") or (data.get("adjournment", {}) or {}).get("time"),
                data.get("presiding_officer"),
                (data.get("adjournment", {}) or {}).get("in_memory_of")
                or (data.get("adjournment", {}) or {}).get("in_honor_of"),
                (data.get("adjournment", {}) or {}).get("next_meeting"),
                json.dumps(data.get("_metadata", {})),
                str(body_id) if body_id else None,
                agenda_url,
            ),
        )
        meeting_id = cur.fetchone()[0]

        # ── Supersede transcript-sourced motions/votes ──
        # When official minutes arrive, they are ground truth — delete any
        # preliminary motions+votes that extract_transcript_votes.py wrote
        # earlier with source='transcript'. The minutes-derived rows that
        # follow will fill in correctly. (S24.23, 2026-04-26.)
        cur.execute(
            """DELETE FROM motions
               WHERE source = 'transcript'
                 AND agenda_item_id IN (
                   SELECT id FROM agenda_items WHERE meeting_id = %s
                 )
            """,
            (meeting_id,),
        )

        # ── Attendance ──
        for member in data.get("members_present", []):
            official_id = _officials.ensure_official(conn, city_fips, member["name"], member.get("role", default_role))
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
            official_id = _officials.ensure_official(conn, city_fips, member["name"], member.get("role", default_role))
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
                cur.execute(
                    """INSERT INTO agenda_items
                       (id, meeting_id, item_number, title, description,
                        department, staff_contact, category, is_consent_calendar,
                        was_pulled_from_consent,
                        resolution_number, financial_amount)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s)
                       ON CONFLICT (meeting_id, item_number) DO UPDATE
                       SET title = COALESCE(EXCLUDED.title, agenda_items.title),
                           description = COALESCE(EXCLUDED.description, agenda_items.description),
                           category = COALESCE(EXCLUDED.category, agenda_items.category),
                           was_pulled_from_consent = EXCLUDED.was_pulled_from_consent""",
                    (
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
                    ),
                )

            # Record the consent calendar block vote on ALL non-pulled items.
            # The block vote applies equally to every consent item that wasn't
            # pulled for separate consideration.
            if consent.get("votes"):
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
                            consent.get("result", "passed"),
                            consent.get("vote_tally"),
                        ),
                    )
                    motion_id = cur.fetchone()[0]
                    for vote in consent["votes"]:
                        off_id = _officials.ensure_official(conn, city_fips, vote["council_member"], vote.get("role", default_role))
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
            cur.execute(
                """INSERT INTO agenda_items
                   (id, meeting_id, item_number, title, description,
                    department, category, is_consent_calendar,
                    continued_from, continued_to)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s)
                   ON CONFLICT (meeting_id, item_number) DO UPDATE
                   SET title = COALESCE(EXCLUDED.title, agenda_items.title),
                       description = COALESCE(EXCLUDED.description, agenda_items.description),
                       category = COALESCE(EXCLUDED.category, agenda_items.category)
                   RETURNING id""",
                (
                    ai_id, meeting_id,
                    item.get("item_number", ""),
                    sanitize_text(item.get("title", "")),
                    sanitize_text(item.get("description")),
                    item.get("department"),
                    item.get("category"),
                    item.get("continued_from"),
                    item.get("continued_to"),
                ),
            )
            # Use actual row id (may differ from ai_id if row already existed)
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
                    off_id = _officials.ensure_official(conn, city_fips, vote["council_member"], vote.get("role", default_role))
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

    conn.commit()
    return meeting_id
