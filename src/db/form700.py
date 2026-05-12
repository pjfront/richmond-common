"""
db.form700 — extracted from db.py (Phase 2.1).

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
        official_id = _officials.ensure_official(conn, city_fips, filer_name, position or "filer")
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
