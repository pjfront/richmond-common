"""
db.documents — extracted from db.py (Phase 2.1).

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

from ._core import sanitize_text


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
    commit: bool = True,
) -> uuid.UUID:
    """Store a raw document in Layer 1. Returns the document ID.

    Deduplicates by content_hash — returns existing ID if duplicate.

    Counter-aware callers (those that need to distinguish new inserts
    from dedup hits — e.g., `archive_center.save_to_documents`) should
    use `ingest_document_with_status` instead, which returns (uuid, bool).
    """
    doc_id, _ = ingest_document_with_status(
        conn, city_fips=city_fips, source_type=source_type,
        raw_content=raw_content, credibility_tier=credibility_tier,
        source_url=source_url, source_identifier=source_identifier,
        mime_type=mime_type, raw_text=raw_text, metadata=metadata,
        commit=commit,
    )
    return doc_id


def ingest_document_with_status(
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
    commit: bool = True,
) -> tuple[uuid.UUID, bool]:
    """Same as ingest_document but returns (doc_id, was_inserted).

    `was_inserted=False` means the content_hash already existed; the
    returned UUID is the EXISTING row's UUID, not a freshly minted one.

    This is the Counter Contract surface for the documents table:
    audit B9 found `save_to_documents` reporting "saved" for every call
    regardless of dedup, inflating its counter by the dedup rate. Phase
    D-3b adds this function so callers can report accurate counts.
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
            return existing[0], False

        doc_id = uuid.uuid4()
        cur.execute(
            """INSERT INTO documents
               (id, city_fips, source_type, source_url, source_identifier,
                raw_content, raw_text, content_hash, mime_type,
                credibility_tier, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                doc_id, city_fips, source_type, source_url, source_identifier,
                psycopg2.Binary(raw_content), sanitize_text(raw_text), content_hash, mime_type,
                credibility_tier, json.dumps(metadata or {}),
            ),
        )
    if commit:
        conn.commit()
    return doc_id, True


def save_extraction_run(
    conn,
    document_id: uuid.UUID,
    extracted_data: dict,
    model: str = "deepseek-v4-pro",
    prompt_version: str = None,
    input_tokens: int = None,
    output_tokens: int = None,
    cost_usd: float = None,
    *,
    commit: bool = True,
) -> uuid.UUID:
    """Record an extraction run in Layer 1. Updates existing run if re-extracting."""
    run_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO extraction_runs
               (id, document_id, extraction_model, extraction_prompt_version,
                extracted_data, input_tokens, output_tokens, cost_usd)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (document_id) DO UPDATE
               SET extraction_model = EXCLUDED.extraction_model,
                   extraction_prompt_version = EXCLUDED.extraction_prompt_version,
                   extracted_data = EXCLUDED.extracted_data,
                   input_tokens = EXCLUDED.input_tokens,
                   output_tokens = EXCLUDED.output_tokens,
                   cost_usd = EXCLUDED.cost_usd,
                   extracted_at = NOW(),
                   is_current = TRUE
               RETURNING id""",
            (
                run_id, document_id, model, prompt_version,
                json.dumps(extracted_data), input_tokens, output_tokens, cost_usd,
            ),
        )
        run_id = cur.fetchone()[0]
    if commit:
        conn.commit()
    return run_id
