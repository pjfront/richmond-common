"""
db.entities — extracted from db.py (Phase 2.1).

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


# ── Entity Resolution (B.46) ─────────────────────────────────

def load_organizations_to_db(
    conn,
    records: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Load organization records into the organizations table.

    Upserts by (city_fips, source, entity_number). Returns summary stats.
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    with conn.cursor() as cur:
        for record in records:
            name = sanitize_text((record.get("name") or "").strip())
            entity_number = (record.get("entity_number") or "").strip()
            source = (record.get("source") or "").strip()

            if not name or not entity_number or not source:
                stats["skipped"] += 1
                continue

            normalized = _officials._normalize_name(name)
            org_id = uuid.uuid4()

            cur.execute(
                """INSERT INTO organizations
                   (id, city_fips, name, normalized_name, entity_number,
                    entity_type, jurisdiction, status, registered_agent,
                    formation_date, source, source_url, source_updated_at, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (city_fips, source, entity_number)
                   DO UPDATE SET
                     name = EXCLUDED.name,
                     normalized_name = EXCLUDED.normalized_name,
                     status = COALESCE(EXCLUDED.status, organizations.status),
                     registered_agent = COALESCE(EXCLUDED.registered_agent, organizations.registered_agent),
                     source_updated_at = EXCLUDED.source_updated_at,
                     metadata = organizations.metadata || EXCLUDED.metadata,
                     updated_at = NOW()
                   RETURNING (xmax = 0) AS inserted""",
                (
                    org_id, city_fips, name, normalized,
                    entity_number,
                    record.get("entity_type"),
                    record.get("jurisdiction"),
                    record.get("status"),
                    sanitize_text(record.get("registered_agent")),
                    record.get("formation_date"),
                    source,
                    record.get("source_url"),
                    record.get("source_updated_at"),
                    json.dumps(record.get("metadata", {})),
                ),
            )
            row = cur.fetchone()
            if row and row[0]:
                stats["inserted"] += 1
            else:
                stats["updated"] += 1

    conn.commit()
    return stats


def load_entity_links_to_db(
    conn,
    records: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Load entity link records (person→organization) into entity_links table.

    Upserts by (city_fips, normalized_person_name, organization_id, role, source).
    Returns summary stats.
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    with conn.cursor() as cur:
        for record in records:
            person_name = sanitize_text((record.get("person_name") or "").strip())
            org_id = record.get("organization_id")
            role = (record.get("role") or "").strip()
            source = (record.get("source") or "").strip()

            if not person_name or not org_id or not role or not source:
                stats["skipped"] += 1
                continue

            normalized_person = _officials._normalize_name(person_name)
            link_id = uuid.uuid4()

            cur.execute(
                """INSERT INTO entity_links
                   (id, city_fips, person_name, normalized_person_name,
                    organization_id, role, role_detail,
                    confidence, source, source_url, effective_date, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (city_fips, normalized_person_name, organization_id, role, source)
                   DO UPDATE SET
                     person_name = EXCLUDED.person_name,
                     role_detail = COALESCE(EXCLUDED.role_detail, entity_links.role_detail),
                     confidence = GREATEST(EXCLUDED.confidence, entity_links.confidence),
                     effective_date = COALESCE(EXCLUDED.effective_date, entity_links.effective_date),
                     metadata = entity_links.metadata || EXCLUDED.metadata
                   RETURNING (xmax = 0) AS inserted""",
                (
                    link_id, city_fips, person_name, normalized_person,
                    org_id, role,
                    sanitize_text(record.get("role_detail")),
                    record.get("confidence", 0.80),
                    source,
                    record.get("source_url"),
                    record.get("effective_date"),
                    json.dumps(record.get("metadata", {})),
                ),
            )
            row = cur.fetchone()
            if row and row[0]:
                stats["inserted"] += 1
            else:
                stats["updated"] += 1

    conn.commit()
    return stats


def resolve_entity_link_ids(
    conn,
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Post-ingestion job: resolve entity_links person names to donor_id and official_id.

    Matches entity_links.normalized_person_name against:
    - donors.normalized_name -> sets donor_id
    - officials.normalized_name -> sets official_id

    Returns stats on how many links were resolved.
    """
    stats = {"donor_resolved": 0, "official_resolved": 0}

    with conn.cursor() as cur:
        # Resolve donor_id
        cur.execute(
            """UPDATE entity_links el
               SET donor_id = d.id
               FROM donors d
               WHERE el.city_fips = %s
                 AND el.donor_id IS NULL
                 AND d.city_fips = el.city_fips
                 AND d.normalized_name = el.normalized_person_name""",
            (city_fips,),
        )
        stats["donor_resolved"] = cur.rowcount

        # Resolve official_id
        cur.execute(
            """UPDATE entity_links el
               SET official_id = o.id
               FROM officials o
               WHERE el.city_fips = %s
                 AND el.official_id IS NULL
                 AND o.city_fips = el.city_fips
                 AND o.normalized_name = el.normalized_person_name""",
            (city_fips,),
        )
        stats["official_resolved"] = cur.rowcount

    conn.commit()
    return stats


# ── Behested Payments (FPPC Form 803) ─────────────────────────


def load_behested_to_db(
    conn,
    payments: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Load behested payments into behested_payments table.

    Idempotent: ON CONFLICT (city_fips, source, source_identifier) DO UPDATE
    refreshes mutable fields. Counter Contract (Phase D-2/D-3, 2026-05-16):
    `inserted`/`updated` come from RETURNING (xmax = 0), not from "did
    execute succeed." Failures (e.g., FK violation) increment `skipped`.

    Args:
        conn: Database connection.
        payments: List of dicts from fppc_form803_client.fetch_behested_payments().
        city_fips: FIPS code.

    Returns:
        Dict with inserted/updated/skipped counts.
        Invariant: inserted + updated + skipped == len(payments).
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    with conn.cursor() as cur:
        for payment in payments:
            source_id = (payment.get("source_identifier") or "").strip()
            if not source_id:
                stats["skipped"] += 1
                continue

            official_name = (payment.get("official_name") or "").strip()
            if not official_name:
                stats["skipped"] += 1
                continue

            # Try to match official
            official_id = None
            try:
                official_id = _officials.ensure_official(conn, city_fips, official_name, "elected")
            except Exception:
                pass

            try:
                cur.execute(
                    """INSERT INTO behested_payments (
                        city_fips, official_name, official_id,
                        payor_name, payor_city, payor_state,
                        payee_name, payee_description,
                        amount, payment_date, filing_date, description,
                        source, source_url, source_identifier, filing_id,
                        metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (city_fips, source, source_identifier) DO UPDATE SET
                        official_id = COALESCE(EXCLUDED.official_id, behested_payments.official_id),
                        amount = EXCLUDED.amount,
                        description = EXCLUDED.description,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (
                        city_fips,
                        official_name,
                        official_id,
                        (payment.get("payor_name") or "").strip(),
                        payment.get("payor_city"),
                        payment.get("payor_state"),
                        (payment.get("payee_name") or "").strip(),
                        payment.get("payee_description"),
                        payment.get("amount"),
                        payment.get("payment_date"),
                        payment.get("filing_date"),
                        payment.get("description"),
                        payment.get("source", "fppc_form803"),
                        payment.get("source_url"),
                        source_id,
                        payment.get("filing_id"),
                        json.dumps(payment.get("metadata", {})),
                    ),
                )
                result = cur.fetchone()
                if result and result[0]:
                    stats["inserted"] += 1
                else:
                    stats["updated"] += 1
            except Exception as e:
                logger.warning("Failed to load behested payment %s: %s", source_id, e)
                stats["skipped"] += 1

    conn.commit()
    return stats


# ── Lobbyist Registrations ────────────────────────────────────


def load_lobbyists_to_db(
    conn,
    registrations: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Load lobbyist registrations into lobbyist_registrations table.

    Idempotent: ON CONFLICT (city_fips, source, source_identifier) DO UPDATE
    refreshes mutable fields. Counter Contract (Phase D-2/D-3, 2026-05-16):
    `inserted`/`updated` come from RETURNING (xmax = 0).

    Args:
        conn: Database connection.
        registrations: List of dicts from lobbyist_client.fetch_lobbyist_registrations().
        city_fips: FIPS code.

    Returns:
        Dict with inserted/updated/skipped counts.
        Invariant: inserted + updated + skipped == len(registrations).
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    with conn.cursor() as cur:
        for reg in registrations:
            source_id = (reg.get("source_identifier") or "").strip()
            if not source_id:
                stats["skipped"] += 1
                continue

            lobbyist_name = (reg.get("lobbyist_name") or "").strip()
            if not lobbyist_name:
                stats["skipped"] += 1
                continue

            try:
                cur.execute(
                    """INSERT INTO lobbyist_registrations (
                        city_fips, lobbyist_name, lobbyist_firm, client_name,
                        registration_date, expiration_date, topics, city_agencies,
                        lobbyist_address, lobbyist_phone, lobbyist_email,
                        status, source, source_url, source_identifier, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (city_fips, source, source_identifier) DO UPDATE SET
                        lobbyist_firm = EXCLUDED.lobbyist_firm,
                        client_name = EXCLUDED.client_name,
                        topics = EXCLUDED.topics,
                        status = EXCLUDED.status,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (
                        city_fips,
                        lobbyist_name,
                        reg.get("lobbyist_firm"),
                        (reg.get("client_name") or "").strip(),
                        reg.get("registration_date"),
                        reg.get("expiration_date"),
                        reg.get("topics"),
                        reg.get("city_agencies"),
                        reg.get("lobbyist_address"),
                        reg.get("lobbyist_phone"),
                        reg.get("lobbyist_email"),
                        reg.get("status", "active"),
                        reg.get("source", "city_clerk"),
                        reg.get("source_url"),
                        source_id,
                        json.dumps(reg.get("metadata", {})),
                    ),
                )
                result = cur.fetchone()
                if result and result[0]:
                    stats["inserted"] += 1
                else:
                    stats["updated"] += 1
            except Exception as e:
                logger.warning("Failed to load lobbyist %s: %s", source_id, e)
                stats["skipped"] += 1

    conn.commit()
    return stats


def load_entity_graph(
    conn,
    city_fips: str = RICHMOND_FIPS,
) -> dict[str, list[dict]]:
    """Load the entity graph for conflict scanner use.

    Returns a dict mapping normalized_person_name to a list of their
    organization connections:
      {
        "john smith": [
          {"org_name": "ABC Corp", "org_id": uuid, "org_normalized": "abc corp",
           "role": "officer", "source": "ca_sos", "confidence": 0.95},
          ...
        ]
      }

    Also includes a reverse map: org_normalized_name -> list of linked persons.
    """
    graph: dict[str, list[dict]] = {}

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT
                 el.normalized_person_name,
                 el.person_name,
                 el.role,
                 el.confidence,
                 el.source,
                 el.donor_id,
                 el.official_id,
                 o.id AS org_id,
                 o.name AS org_name,
                 o.normalized_name AS org_normalized,
                 o.entity_type,
                 o.entity_number,
                 o.status AS org_status
               FROM entity_links el
               JOIN organizations o ON o.id = el.organization_id
               WHERE el.city_fips = %s""",
            (city_fips,),
        )
        for row in cur:
            person_key = row["normalized_person_name"]
            if person_key not in graph:
                graph[person_key] = []
            graph[person_key].append({
                "org_name": row["org_name"],
                "org_id": row["org_id"],
                "org_normalized": row["org_normalized"],
                "entity_type": row["entity_type"],
                "entity_number": row["entity_number"],
                "role": row["role"],
                "source": row["source"],
                "confidence": float(row["confidence"]),
                "donor_id": row["donor_id"],
                "official_id": row["official_id"],
                "org_status": row["org_status"],
            })

    return graph


def load_org_reverse_map(
    conn,
    city_fips: str = RICHMOND_FIPS,
) -> dict[str, list[dict]]:
    """Load reverse entity graph: org_normalized_name -> list of linked persons.

    Used by LLC ownership chain detection: given an org name mentioned in an
    agenda item, find all people linked to that org.
    """
    reverse: dict[str, list[dict]] = {}

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT
                 o.normalized_name AS org_normalized,
                 o.name AS org_name,
                 o.entity_type,
                 el.person_name,
                 el.normalized_person_name,
                 el.role,
                 el.confidence,
                 el.donor_id,
                 el.official_id
               FROM entity_links el
               JOIN organizations o ON o.id = el.organization_id
               WHERE el.city_fips = %s""",
            (city_fips,),
        )
        for row in cur:
            org_key = row["org_normalized"]
            if org_key not in reverse:
                reverse[org_key] = []
            reverse[org_key].append({
                "person_name": row["person_name"],
                "normalized_person_name": row["normalized_person_name"],
                "role": row["role"],
                "confidence": float(row["confidence"]),
                "donor_id": row["donor_id"],
                "official_id": row["official_id"],
                "org_name": row["org_name"],
                "entity_type": row["entity_type"],
            })

    return reverse
