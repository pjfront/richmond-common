"""
Richmond Transparency Project — Database Access Layer

Handles connection management and provides helpers for loading
extracted meeting data into the Layer 2 structured schema.

Usage:
    from db import get_connection, load_meeting_to_db

    conn = get_connection()
    load_meeting_to_db(conn, extracted_data, document_id, city_fips="0660620")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# Register UUID adapter for psycopg2
psycopg2.extras.register_uuid()

RICHMOND_FIPS = "0660620"

logger = logging.getLogger(__name__)


def get_connection():
    """Get a PostgreSQL connection from DATABASE_URL."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL not set. Add it to .env or environment.\n"
            "Example: postgresql://user:pass@localhost:5432/richmond_transparency"
        )
    return psycopg2.connect(database_url)


def init_schema(conn, schema_path: str = None):
    """Run schema.sql to initialize the database."""
    if schema_path is None:
        schema_path = Path(__file__).parent / "schema.sql"
    sql = Path(schema_path).read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


# ── Document Lake (Layer 1) ──────────────────────────────────

def ingest_document(
    conn,
    city_fips: str,
    source_type: str,
    raw_content: bytes,
    credibility_tier: int,
    source_url: str = None,
    source_identifier: str = None,
    mime_type: str = None,
    raw_text: str = None,
    metadata: dict = None,
) -> uuid.UUID:
    """Store a raw document in Layer 1. Returns the document ID.

    Deduplicates by content_hash — returns existing ID if duplicate.
    """
    content_hash = hashlib.sha256(raw_content).hexdigest()

    with conn.cursor() as cur:
        # Check for existing document
        cur.execute(
            "SELECT id FROM documents WHERE city_fips = %s AND content_hash = %s",
            (city_fips, content_hash),
        )
        existing = cur.fetchone()
        if existing:
            return existing[0]

        doc_id = uuid.uuid4()
        cur.execute(
            """INSERT INTO documents
               (id, city_fips, source_type, source_url, source_identifier,
                raw_content, raw_text, content_hash, mime_type,
                credibility_tier, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                doc_id, city_fips, source_type, source_url, source_identifier,
                psycopg2.Binary(raw_content), raw_text, content_hash, mime_type,
                credibility_tier, json.dumps(metadata or {}),
            ),
        )
    conn.commit()
    return doc_id


def save_extraction_run(
    conn,
    document_id: uuid.UUID,
    extracted_data: dict,
    model: str = "claude-sonnet-4-20250514",
    prompt_version: str = None,
    input_tokens: int = None,
    output_tokens: int = None,
    cost_usd: float = None,
) -> uuid.UUID:
    """Record an extraction run in Layer 1. Marks previous runs as non-current."""
    run_id = uuid.uuid4()
    with conn.cursor() as cur:
        # Mark previous runs as non-current
        cur.execute(
            "UPDATE extraction_runs SET is_current = FALSE WHERE document_id = %s",
            (document_id,),
        )
        cur.execute(
            """INSERT INTO extraction_runs
               (id, document_id, extraction_model, extraction_prompt_version,
                extracted_data, input_tokens, output_tokens, cost_usd)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                run_id, document_id, model, prompt_version,
                json.dumps(extracted_data), input_tokens, output_tokens, cost_usd,
            ),
        )
    conn.commit()
    return run_id


# ── Structured Core (Layer 2) ────────────────────────────────

def _normalize_name(name: str) -> str:
    """Lowercase and strip whitespace for matching."""
    return " ".join(name.lower().split())


# Fuzzy matching threshold: names with similarity >= this merge automatically.
# 0.85 catches single-character typos in typical council member names
# (e.g., "Jamelia Brown" vs "Jamalia Brown" = 0.846) while rejecting
# genuinely different names (e.g., "Eduardo Martinez" vs "Edward Martin" = 0.828,
# "Jamelia Brown" vs "James Brown" = 0.833).
FUZZY_MATCH_THRESHOLD = 0.85


def _load_alias_map(city_fips: str) -> dict[str, str]:
    """Build a normalized_alias -> canonical_name map from officials.json.

    Loads aliases from all official categories (council, leadership, etc.)
    for the given city. Returns a dict mapping each normalized alias to the
    canonical (preferred) name.
    """
    gt_path = Path(__file__).parent / "ground_truth" / "officials.json"
    if not gt_path.exists():
        return {}

    try:
        data = json.loads(gt_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    if data.get("city_fips") != city_fips:
        return {}

    alias_map: dict[str, str] = {}
    # Scan all list-of-official sections for aliases
    for section in ("current_council_members", "former_council_members", "city_leadership"):
        for official in data.get(section, []):
            canonical = official.get("name", "")
            for alias in official.get("aliases", []):
                alias_map[_normalize_name(alias)] = canonical
    return alias_map


def _fuzzy_find_official(
    cur,
    city_fips: str,
    normalized: str,
    threshold: float = FUZZY_MATCH_THRESHOLD,
) -> tuple[uuid.UUID | None, str | None, float]:
    """Search existing officials for a fuzzy name match.

    Returns (official_id, matched_name, similarity) or (None, None, 0.0).
    Only considers officials with is_current = TRUE.
    """
    cur.execute(
        """SELECT id, normalized_name FROM officials
           WHERE city_fips = %s AND is_current = TRUE""",
        (city_fips,),
    )
    best_id = None
    best_name = None
    best_score = 0.0

    for row in cur.fetchall():
        existing_id, existing_name = row
        score = SequenceMatcher(None, normalized, existing_name).ratio()
        if score >= threshold and score > best_score:
            best_id = existing_id
            best_name = existing_name
            best_score = score

    return best_id, best_name, best_score


def ensure_official(
    conn,
    city_fips: str,
    name: str,
    role: str,
) -> uuid.UUID:
    """Find or create an official. Returns the official ID.

    Matching strategy (in order):
    1. Exact match on normalized name
    2. Alias match from officials.json (e.g., "Kinshasa Curl" -> "Shasa Curl")
    3. Fuzzy match (SequenceMatcher ratio >= threshold) to catch typos
    4. Create new record if no match found
    """
    normalized = _normalize_name(name)
    with conn.cursor() as cur:
        # 1. Exact match
        cur.execute(
            """SELECT id FROM officials
               WHERE city_fips = %s AND normalized_name = %s AND is_current = TRUE""",
            (city_fips, normalized),
        )
        row = cur.fetchone()
        if row:
            return row[0]

        # 2. Alias match — check if this name is a known alias
        alias_map = _load_alias_map(city_fips)
        canonical = alias_map.get(normalized)
        if canonical:
            canonical_normalized = _normalize_name(canonical)
            cur.execute(
                """SELECT id FROM officials
                   WHERE city_fips = %s AND normalized_name = %s AND is_current = TRUE""",
                (city_fips, canonical_normalized),
            )
            row = cur.fetchone()
            if row:
                logger.info(
                    "Alias match: '%s' resolved to canonical '%s'",
                    name, canonical,
                )
                return row[0]

        # 3. Fuzzy match — catch typos like "Jamalia Brown" -> "Jamelia Brown"
        fuzzy_id, fuzzy_name, score = _fuzzy_find_official(cur, city_fips, normalized)
        if fuzzy_id is not None:
            logger.warning(
                "Fuzzy match: '%s' merged with existing '%s' (similarity=%.3f). "
                "If this is wrong, add both names to officials.json as separate entries.",
                name, fuzzy_name, score,
            )
            return fuzzy_id

        # 4. No match — create new record
        official_id = uuid.uuid4()
        cur.execute(
            """INSERT INTO officials (id, city_fips, name, normalized_name, role)
               VALUES (%s, %s, %s, %s, %s)""",
            (official_id, city_fips, name, normalized, role),
        )
        conn.commit()
        return official_id


def load_meeting_to_db(
    conn,
    data: dict,
    document_id: uuid.UUID = None,
    city_fips: str = RICHMOND_FIPS,
) -> uuid.UUID:
    """Load extracted meeting JSON into Layer 2 structured tables.

    This is the main entry point for populating the structured schema
    from Claude's extraction output.

    Returns the meeting UUID.
    """
    meeting_id = uuid.uuid4()

    with conn.cursor() as cur:
        # ── Meeting ──
        cur.execute(
            """INSERT INTO meetings
               (id, city_fips, document_id, meeting_date, meeting_type,
                call_to_order_time, adjournment_time, presiding_officer,
                adjourned_in_memory_of, next_meeting_date, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (city_fips, meeting_date, meeting_type) DO UPDATE
               SET document_id = EXCLUDED.document_id,
                   call_to_order_time = EXCLUDED.call_to_order_time,
                   adjournment_time = EXCLUDED.adjournment_time,
                   presiding_officer = EXCLUDED.presiding_officer
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
            ),
        )
        meeting_id = cur.fetchone()[0]

        # ── Attendance ──
        for member in data.get("members_present", []):
            official_id = ensure_official(conn, city_fips, member["name"], member.get("role", "councilmember"))
            # Check if this member was late
            late_info = next(
                (m for m in data.get("members_late", []) if _normalize_name(m["name"]) == _normalize_name(member["name"])),
                None,
            )
            status = "late" if late_info else "present"
            notes = late_info.get("notes") if late_info else None
            cur.execute(
                """INSERT INTO meeting_attendance (id, meeting_id, official_id, status, notes)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (meeting_id, official_id) DO NOTHING""",
                (uuid.uuid4(), meeting_id, official_id, status, notes),
            )

        for member in data.get("members_absent", []):
            official_id = ensure_official(conn, city_fips, member["name"], member.get("role", "councilmember"))
            cur.execute(
                """INSERT INTO meeting_attendance (id, meeting_id, official_id, status, notes)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (meeting_id, official_id) DO NOTHING""",
                (uuid.uuid4(), meeting_id, official_id, "absent", member.get("notes")),
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
            for consent_item in consent["items"]:
                ai_id = uuid.uuid4()
                cur.execute(
                    """INSERT INTO agenda_items
                       (id, meeting_id, item_number, title, description,
                        department, staff_contact, category, is_consent_calendar,
                        resolution_number, financial_amount)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
                       ON CONFLICT (meeting_id, item_number) DO UPDATE
                       SET title = COALESCE(EXCLUDED.title, agenda_items.title),
                           description = COALESCE(EXCLUDED.description, agenda_items.description),
                           category = COALESCE(EXCLUDED.category, agenda_items.category)""",
                    (
                        ai_id, meeting_id,
                        consent_item.get("item_number", ""),
                        consent_item.get("title", ""),
                        consent_item.get("description"),
                        consent_item.get("department"),
                        consent_item.get("staff_contact"),
                        consent_item.get("category"),
                        consent_item.get("resolution_number"),
                        consent_item.get("financial_amount"),
                    ),
                )

            # Record the consent calendar block vote as a motion on the first item
            if consent.get("votes"):
                # Find the first consent item's DB id
                first_item_num = consent["items"][0].get("item_number", "")
                cur.execute(
                    "SELECT id FROM agenda_items WHERE meeting_id = %s AND item_number = %s",
                    (meeting_id, first_item_num),
                )
                row = cur.fetchone()
                if row:
                    motion_id = uuid.uuid4()
                    cur.execute(
                        """INSERT INTO motions
                           (id, agenda_item_id, motion_type, motion_text,
                            moved_by, seconded_by, result, vote_tally, sequence_number)
                           VALUES (%s, %s, 'original', %s, %s, %s, %s, %s, 1)""",
                        (
                            motion_id, row[0],
                            "Approve consent calendar",
                            consent.get("motion_by"),
                            consent.get("seconded_by"),
                            consent.get("result", "passed"),
                            consent.get("vote_tally"),
                        ),
                    )
                    for vote in consent["votes"]:
                        off_id = ensure_official(conn, city_fips, vote["council_member"], vote.get("role", "councilmember"))
                        cur.execute(
                            """INSERT INTO votes (id, motion_id, official_id, official_name, official_role, vote_choice)
                               VALUES (%s, %s, %s, %s, %s, %s)
                               ON CONFLICT (motion_id, official_name) DO NOTHING""",
                            (uuid.uuid4(), motion_id, off_id, vote["council_member"], vote.get("role"), vote["vote"]),
                        )

        # ── Action Items ──
        for item in data.get("action_items", []):
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
                    item.get("title", ""),
                    item.get("description"),
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
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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

                for vote in motion.get("votes", []):
                    off_id = ensure_official(conn, city_fips, vote["council_member"], vote.get("role", "councilmember"))
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
                   VALUES (%s, %s, %s, %s, %s, %s, 'public')""",
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
                   VALUES (%s, %s, %s, %s, %s, %s, 'written')""",
                (
                    uuid.uuid4(), meeting_id, agenda_item_id,
                    comment.get("speaker_name", ""),
                    comment.get("method", "email"),
                    comment.get("summary"),
                ),
            )

    conn.commit()
    return meeting_id


# ── Contribution Loading ─────────────────────────────────────

def _parse_contribution_date(date_str: str) -> Optional[date]:
    """Parse contribution date from either NetFile (ISO) or CAL-ACCESS format."""
    if not date_str:
        return None
    # ISO format: "2025-12-29"
    if "-" in date_str and len(date_str) >= 10:
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    # CAL-ACCESS format: "4/11/2001 12:00:00 AM"
    try:
        return datetime.strptime(date_str.split()[0], "%m/%d/%Y").date()
    except (ValueError, IndexError):
        pass
    return None


def _contribution_type_from_record(record: dict) -> str:
    """Map transaction_type or form_type to our contribution_type enum."""
    tx_type = record.get("transaction_type", "")
    if tx_type in ("F460A", "F497P1"):
        return "monetary"
    if tx_type == "F460C":
        return "nonmonetary"
    # CAL-ACCESS records without transaction_type
    form_type = record.get("form_type", "")
    if form_type == "F460":
        return "monetary"
    return "monetary"


def load_contributions_to_db(
    conn,
    records: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Load combined contribution records into donors, committees, and contributions tables.

    Handles both CAL-ACCESS and NetFile record formats.
    Returns summary dict with counts.
    """
    donor_cache: dict[str, uuid.UUID] = {}   # (normalized_name, employer) -> id
    committee_cache: dict[str, uuid.UUID] = {}  # normalized committee name -> id
    stats = {"donors": 0, "committees": 0, "contributions": 0, "skipped": 0}

    with conn.cursor() as cur:
        for record in records:
            # ── Extract fields (handle both formats) ──
            donor_name = (record.get("contributor_name") or record.get("name") or "").strip()
            employer = (record.get("contributor_employer") or record.get("employer") or "").strip()
            occupation = (record.get("occupation") or record.get("contributor_occupation") or "").strip()
            amount = record.get("amount")
            date_str = record.get("date", "")
            committee_name = (record.get("committee") or record.get("filerName") or "").strip()
            source = record.get("source", "unknown")
            filing_id = record.get("filing_id", "")

            if not donor_name or amount is None or not committee_name:
                stats["skipped"] += 1
                continue

            contrib_date = _parse_contribution_date(date_str)
            if not contrib_date:
                stats["skipped"] += 1
                continue

            # ── Upsert donor ──
            norm_donor = _normalize_name(donor_name)
            donor_key = (norm_donor, employer.lower().strip())
            if donor_key not in donor_cache:
                norm_employer = _normalize_name(employer) if employer else None
                cur.execute(
                    """SELECT id FROM donors
                       WHERE city_fips = %s AND normalized_name = %s
                         AND COALESCE(employer, '') = %s""",
                    (city_fips, norm_donor, employer or ""),
                )
                row = cur.fetchone()
                if row:
                    donor_cache[donor_key] = row[0]
                else:
                    donor_id = uuid.uuid4()
                    cur.execute(
                        """INSERT INTO donors
                           (id, city_fips, name, normalized_name, employer, normalized_employer, occupation)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (city_fips, normalized_name, COALESCE(employer, ''))
                           DO UPDATE SET occupation = COALESCE(EXCLUDED.occupation, donors.occupation)
                           RETURNING id""",
                        (donor_id, city_fips, donor_name, norm_donor,
                         employer or None, norm_employer, occupation or None),
                    )
                    donor_cache[donor_key] = cur.fetchone()[0]
                    stats["donors"] += 1

            # ── Upsert committee ──
            norm_committee = _normalize_name(committee_name)
            if norm_committee not in committee_cache:
                cur.execute(
                    "SELECT id FROM committees WHERE city_fips = %s AND name = %s",
                    (city_fips, committee_name),
                )
                row = cur.fetchone()
                if row:
                    committee_cache[norm_committee] = row[0]
                else:
                    committee_id = uuid.uuid4()
                    filer_id = record.get("filer_id") or record.get("filer_fppc_id") or ""
                    cur.execute(
                        """INSERT INTO committees
                           (id, city_fips, name, filer_id, committee_type, status)
                           VALUES (%s, %s, %s, %s, %s, 'active')
                           ON CONFLICT DO NOTHING
                           RETURNING id""",
                        (committee_id, city_fips, committee_name,
                         filer_id or None, "candidate" if source == "netfile" else "pac"),
                    )
                    result = cur.fetchone()
                    committee_cache[norm_committee] = result[0] if result else committee_id
                    stats["committees"] += 1

            # ── Insert contribution ──
            contrib_type = _contribution_type_from_record(record)
            cur.execute(
                """INSERT INTO contributions
                   (id, city_fips, donor_id, committee_id, amount,
                    contribution_date, contribution_type, filing_id, source)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (uuid.uuid4(), city_fips,
                 donor_cache[donor_key], committee_cache[norm_committee],
                 amount, contrib_date, contrib_type,
                 str(filing_id) if filing_id else None,
                 "calaccess" if source == "calaccess" else "city_clerk"),
            )
            stats["contributions"] += 1

            # Commit in batches to avoid huge transactions
            if stats["contributions"] % 1000 == 0:
                conn.commit()

    conn.commit()
    return stats


# ── Form 700 Filings (Financial Intelligence) ─────────────────

def load_form700_to_db(
    conn,
    extraction: dict,
    filing_metadata: dict,
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Load a Form 700 extraction result into form700_filings and economic_interests.

    Creates a filing record (parent) and individual interest entries (children).
    Matches filer to existing official via ensure_official() if possible.

    Args:
        conn: Database connection.
        extraction: Dict from form700_extractor.extract_form700() matching
            FORM700_EXTRACTION_SCHEMA.
        filing_metadata: Scraper metadata dict with keys:
            filer_name, agency, statement_type, filing_year,
            source (str), source_url (str), document_id (UUID or None).
        city_fips: FIPS code.

    Returns:
        Dict with: filing_id, official_id, interests_count, matched_official (bool).
    """
    filer_name = extraction.get("filer_name") or filing_metadata.get("filer_name", "")
    agency = extraction.get("filer_agency") or filing_metadata.get("agency", "")
    position = extraction.get("filer_position") or ""
    statement_type = extraction.get("statement_type") or filing_metadata.get("statement_type", "annual")
    filing_year = filing_metadata.get("filing_year", 0)
    period_start = extraction.get("period_start")
    period_end = extraction.get("period_end")
    source = filing_metadata.get("source", "netfile_sei")
    source_url = filing_metadata.get("source_url", "")
    document_id = filing_metadata.get("document_id")
    no_interests = extraction.get("no_interests_declared", False)

    if not filer_name:
        raise ValueError("Cannot load filing without filer_name")

    # Match filer to official (nullable — unmatched filers still get stored)
    official_id = None
    matched = False
    try:
        official_id = ensure_official(conn, city_fips, filer_name, position or "filer")
        matched = True
    except Exception as e:
        logger.warning("Could not match filer '%s' to official: %s", filer_name, e)

    # Build metadata JSONB
    metadata = {
        "extraction_confidence": extraction.get("extraction_confidence", 0),
        "extraction_notes": extraction.get("extraction_notes", ""),
    }
    if extraction.get("_extraction_metadata"):
        metadata["api_usage"] = extraction["_extraction_metadata"]

    filing_id = uuid.uuid4()

    with conn.cursor() as cur:
        # Upsert filing (deduplicate on filer + year + type + source)
        cur.execute(
            """INSERT INTO form700_filings
               (id, city_fips, official_id, filer_name, filer_agency,
                filer_position, statement_type, period_start, period_end,
                filing_year, source, source_url, document_id,
                no_interests_declared, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (city_fips, filer_name, filing_year, statement_type, source)
               DO UPDATE SET
                   official_id = COALESCE(EXCLUDED.official_id, form700_filings.official_id),
                   filer_agency = EXCLUDED.filer_agency,
                   filer_position = EXCLUDED.filer_position,
                   period_start = EXCLUDED.period_start,
                   period_end = EXCLUDED.period_end,
                   source_url = EXCLUDED.source_url,
                   document_id = COALESCE(EXCLUDED.document_id, form700_filings.document_id),
                   no_interests_declared = EXCLUDED.no_interests_declared,
                   metadata = EXCLUDED.metadata
               RETURNING id""",
            (
                filing_id, city_fips, official_id, filer_name, agency,
                position, statement_type,
                period_start, period_end,
                filing_year, source, source_url, document_id,
                no_interests, json.dumps(metadata),
            ),
        )
        row = cur.fetchone()
        filing_id = row[0] if row else filing_id

        # Delete existing interests for this filing (re-extraction replaces)
        cur.execute(
            "DELETE FROM economic_interests WHERE filing_id = %s",
            (filing_id,),
        )

        # Insert interests
        interests = extraction.get("interests", [])
        for item in interests:
            schedule = item.get("schedule", "")
            interest_type = item.get("interest_type", "")
            description = item.get("description", "")

            if not description:
                continue

            # Map extractor interest_type to schema's interest_type
            type_map = {
                "investment": "investment",
                "business_entity": "business_position",
                "real_property": "real_property",
                "income": "income",
                "business_position": "business_position",
                "gift": "gift",
                "travel": "travel",
            }
            db_interest_type = type_map.get(interest_type, interest_type)

            cur.execute(
                """INSERT INTO economic_interests
                   (id, city_fips, official_id, filing_id, filing_year,
                    schedule, interest_type, description, value_range,
                    location, source_url, document_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    uuid.uuid4(), city_fips, official_id, filing_id,
                    filing_year, schedule, db_interest_type,
                    description,
                    item.get("value_range"),
                    item.get("location"),
                    source_url or None,
                    document_id,
                ),
            )

    conn.commit()
    return {
        "filing_id": filing_id,
        "official_id": official_id,
        "interests_count": len(interests),
        "matched_official": matched,
        "filer_name": filer_name,
    }


# ── Scan Runs (Cloud Pipeline) ───────────────────────────────

def create_scan_run(
    conn,
    city_fips: str,
    meeting_id: uuid.UUID = None,
    scan_mode: str = "prospective",
    data_cutoff_date: date = None,
    contributions_count: int = None,
    contributions_sources: dict = None,
    form700_count: int = None,
    triggered_by: str = "manual",
    pipeline_run_id: str = None,
    scanner_version: str = None,
) -> uuid.UUID:
    """Create a scan_runs row at the start of a pipeline execution.

    Returns the scan_run UUID. Update with complete_scan_run() when done.
    """
    run_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO scan_runs
               (id, city_fips, meeting_id, scan_mode, data_cutoff_date,
                contributions_count, contributions_sources, form700_count,
                triggered_by, pipeline_run_id, scanner_version, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'running')""",
            (
                run_id, city_fips, meeting_id, scan_mode, data_cutoff_date,
                contributions_count, json.dumps(contributions_sources or {}),
                form700_count, triggered_by, pipeline_run_id, scanner_version,
            ),
        )
    conn.commit()
    return run_id


def complete_scan_run(
    conn,
    scan_run_id: uuid.UUID,
    flags_found: int,
    flags_by_tier: dict,
    clean_items_count: int,
    enriched_items_count: int = None,
    execution_time_seconds: float = None,
    metadata: dict = None,
    error_message: str = None,
) -> None:
    """Mark a scan_run as completed (or failed) with results."""
    status = "failed" if error_message else "completed"
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE scan_runs
               SET flags_found = %s, flags_by_tier = %s,
                   clean_items_count = %s, enriched_items_count = %s,
                   execution_time_seconds = %s, metadata = %s,
                   status = %s, error_message = %s,
                   completed_at = NOW()
               WHERE id = %s""",
            (
                flags_found, json.dumps(flags_by_tier or {}),
                clean_items_count, enriched_items_count,
                execution_time_seconds, json.dumps(metadata or {}),
                status, error_message,
                scan_run_id,
            ),
        )
    conn.commit()


def fail_scan_run(conn, scan_run_id: uuid.UUID, error_message: str) -> None:
    """Mark a scan_run as failed."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE scan_runs
               SET status = 'failed', error_message = %s, completed_at = NOW()
               WHERE id = %s""",
            (error_message, scan_run_id),
        )
    conn.commit()


# ── Data Sync Log ───────────────────────────────────────────

def create_sync_log(
    conn,
    city_fips: str,
    source: str,
    sync_type: str = "incremental",
    triggered_by: str = "manual",
    pipeline_run_id: str = None,
) -> uuid.UUID:
    """Create a data_sync_log row at the start of a sync.

    Returns the log UUID. Update with complete_sync_log() when done.
    """
    log_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO data_sync_log
               (id, city_fips, source, sync_type, triggered_by, pipeline_run_id, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'running')""",
            (log_id, city_fips, source, sync_type, triggered_by, pipeline_run_id),
        )
    conn.commit()
    return log_id


def complete_sync_log(
    conn,
    sync_log_id: uuid.UUID,
    records_fetched: int = None,
    records_new: int = None,
    records_updated: int = None,
    error_message: str = None,
    metadata: dict = None,
) -> None:
    """Mark a sync log entry as completed (or failed)."""
    status = "failed" if error_message else "completed"
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE data_sync_log
               SET records_fetched = %s, records_new = %s, records_updated = %s,
                   status = %s, error_message = %s, metadata = %s,
                   completed_at = NOW()
               WHERE id = %s""",
            (
                records_fetched, records_new, records_updated,
                status, error_message, json.dumps(metadata or {}),
                sync_log_id,
            ),
        )
    conn.commit()


# ── Pipeline Journal (Autonomy Zones Phase A) ────────────────


def write_journal_entry(
    conn,
    city_fips: str,
    session_id: uuid.UUID,
    entry_type: str,
    description: str,
    zone: str = "observation",
    target_artifact: str = None,
    metrics: dict = None,
) -> uuid.UUID:
    """Write one row to pipeline_journal. Returns entry UUID.

    This is the low-level writer. Prefer PipelineJournal class for
    instrumentation (handles non-fatal behavior and session grouping).
    """
    entry_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO pipeline_journal
               (id, city_fips, session_id, entry_type, zone,
                target_artifact, description, metrics)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                entry_id, city_fips, session_id, entry_type, zone,
                target_artifact, description, json.dumps(metrics or {}),
            ),
        )
    conn.commit()
    return entry_id


def get_journal_entries(
    conn,
    city_fips: str,
    days: int = 7,
    entry_types: list[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Read recent journal entries, newest first.

    Used by the self-assessment module to gather pipeline telemetry.
    """
    query = """
        SELECT id, city_fips, session_id, entry_type, zone,
               target_artifact, description, metrics, created_at
        FROM pipeline_journal
        WHERE city_fips = %s
          AND created_at >= NOW() - INTERVAL '%s days'
    """
    params: list = [city_fips, days]

    if entry_types:
        placeholders = ", ".join(["%s"] * len(entry_types))
        query += f" AND entry_type IN ({placeholders})"
        params.extend(entry_types)

    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    return [
        {col: (str(val) if isinstance(val, uuid.UUID) else val)
         for col, val in zip(columns, row)}
        for row in rows
    ]


def get_recent_step_metrics(
    conn,
    city_fips: str,
    step_name: str,
    metric_key: str = None,
    limit: int = 10,
) -> list[dict]:
    """Get metrics from recent step_completed entries for anomaly detection.

    If metric_key is provided, returns only that key's values from each
    entry's metrics JSONB. Otherwise returns full metrics dicts.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT metrics, created_at
               FROM pipeline_journal
               WHERE city_fips = %s
                 AND target_artifact = %s
                 AND entry_type = 'step_completed'
               ORDER BY created_at DESC
               LIMIT %s""",
            (city_fips, step_name, limit),
        )
        rows = cur.fetchall()

    results = []
    for metrics_json, created_at in rows:
        m = metrics_json if isinstance(metrics_json, dict) else {}
        if metric_key:
            results.append({"value": m.get(metric_key), "created_at": created_at})
        else:
            results.append({"metrics": m, "created_at": created_at})
    return results


# ── Decision Queue (S7) ─────────────────────────────────────


def insert_pending_decision(
    conn,
    city_fips: str,
    decision_type: str,
    severity: str,
    title: str,
    description: str,
    source: str,
    evidence: dict = None,
    entity_type: str = None,
    entity_id: str = None,
    link: str = None,
    dedup_key: str = None,
) -> Optional[uuid.UUID]:
    """Insert a pending decision. Returns UUID, or None if deduplicated.

    If dedup_key is set and a pending decision with that key already exists,
    the partial unique index prevents insertion and this returns None.
    """
    decision_id = uuid.uuid4()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO pending_decisions
                   (id, city_fips, decision_type, severity, title, description,
                    evidence, source, entity_type, entity_id, link, dedup_key)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    decision_id, city_fips, decision_type, severity,
                    title, description, json.dumps(evidence or {}),
                    source, entity_type, entity_id, link, dedup_key,
                ),
            )
        conn.commit()
        return decision_id
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return None


def update_decision_status(
    conn,
    decision_id: uuid.UUID,
    status: str,
    resolved_by: str = "operator",
    resolution_note: str = None,
) -> bool:
    """Update a decision's status. Returns True if a row was updated."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE pending_decisions
               SET status = %s, resolved_by = %s, resolution_note = %s,
                   resolved_at = NOW(), updated_at = NOW()
               WHERE id = %s AND status = 'pending'""",
            (status, resolved_by, resolution_note, decision_id),
        )
        updated = cur.rowcount > 0
    conn.commit()
    return updated


def query_pending_decisions(
    conn,
    city_fips: str,
    decision_type: str = None,
    severity: str = None,
) -> list[dict]:
    """Query pending decisions, ordered by severity rank then age.

    Severity order: critical > high > medium > low > info.
    Within each severity, oldest first (so nothing gets buried).
    """
    query = """
        SELECT id, city_fips, decision_type, severity, title, description,
               evidence, source, entity_type, entity_id, link, dedup_key,
               status, created_at, updated_at
        FROM pending_decisions
        WHERE city_fips = %s AND status = 'pending'
    """
    params: list = [city_fips]

    if decision_type:
        query += " AND decision_type = %s"
        params.append(decision_type)

    if severity:
        query += " AND severity = %s"
        params.append(severity)

    query += """
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                WHEN 'info' THEN 5
                ELSE 6
            END,
            created_at ASC
    """

    with conn.cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    return [
        {col: (str(val) if isinstance(val, uuid.UUID) else val)
         for col, val in zip(columns, row)}
        for row in rows
    ]


def query_resolved_decisions(
    conn,
    city_fips: str,
    days: int = 7,
    limit: int = 20,
) -> list[dict]:
    """Query recently resolved decisions, newest first."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, city_fips, decision_type, severity, title, description,
                      evidence, source, entity_type, entity_id, link, dedup_key,
                      status, resolved_at, resolved_by, resolution_note,
                      created_at, updated_at
               FROM pending_decisions
               WHERE city_fips = %s AND status != 'pending'
                 AND resolved_at >= NOW() - INTERVAL '%s days'
               ORDER BY resolved_at DESC
               LIMIT %s""",
            (city_fips, days, limit),
        )
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    return [
        {col: (str(val) if isinstance(val, uuid.UUID) else val)
         for col, val in zip(columns, row)}
        for row in rows
    ]


def count_decisions_by_severity(
    conn,
    city_fips: str,
) -> dict[str, int]:
    """Count pending decisions grouped by severity."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT severity, COUNT(*) as cnt
               FROM pending_decisions
               WHERE city_fips = %s AND status = 'pending'
               GROUP BY severity""",
            (city_fips,),
        )
        rows = cur.fetchall()

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for severity, cnt in rows:
        counts[severity] = cnt
    return counts


# ── Conflict Flag Helpers (Cloud Pipeline) ──────────────────

def save_conflict_flag(
    conn,
    city_fips: str,
    meeting_id: uuid.UUID,
    scan_run_id: uuid.UUID,
    flag_type: str,
    description: str,
    evidence: list,
    confidence: float,
    scan_mode: str = None,
    data_cutoff_date: date = None,
    agenda_item_id: uuid.UUID = None,
    official_id: uuid.UUID = None,
    legal_reference: str = None,
) -> uuid.UUID:
    """Insert a conflict_flag linked to a scan_run."""
    flag_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO conflict_flags
               (id, city_fips, meeting_id, agenda_item_id, official_id,
                flag_type, description, evidence, confidence, legal_reference,
                scan_run_id, scan_mode, data_cutoff_date, is_current)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)""",
            (
                flag_id, city_fips, meeting_id, agenda_item_id, official_id,
                flag_type, description, json.dumps(evidence),
                confidence, legal_reference,
                scan_run_id, scan_mode, data_cutoff_date,
            ),
        )
    conn.commit()
    return flag_id


def supersede_flags_for_meeting(
    conn,
    meeting_id: uuid.UUID,
    new_scan_run_id: uuid.UUID,
    scan_mode: str = "prospective",
) -> int:
    """Mark existing prospective flags as superseded by a new scan.

    Returns the number of flags superseded.
    """
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE conflict_flags
               SET is_current = FALSE
               WHERE meeting_id = %s AND scan_mode = %s AND is_current = TRUE
                 AND scan_run_id != %s""",
            (meeting_id, scan_mode, new_scan_run_id),
        )
        count = cur.rowcount
    conn.commit()
    return count


def run_migration(conn, migration_path: str) -> None:
    """Run a SQL migration file."""
    sql = Path(migration_path).read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


# ── CLI ──────────────────────────────────────────────────────

def main():
    """CLI for database operations."""
    import argparse
    import glob as globmod

    parser = argparse.ArgumentParser(description="Richmond Transparency Project — Database Management")
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
            migrations_dir = Path(__file__).parent / "migrations"
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
