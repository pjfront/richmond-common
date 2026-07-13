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


# ── City Contracts (S26.2) ──────────────────────────────────────


def load_city_contracts_to_db(
    conn,
    records: list[dict],
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Load aggregated city contract records into city_contracts table.

    Each record is an aggregated vendor-department-year contract derived
    from Socrata expenditures data. Idempotent: ON CONFLICT on the
    (vendor_name, contract_number, approval_date) partial unique index
    — contract_number IS NOT NULL rows use the unique constraint; rows
    without a contract_number get a synthetic key.

    Args:
        conn: Database connection.
        records: List of dicts with keys matching city_contracts columns:
            vendor_name, description, annual_cost, total_cost, contract_type,
            department, approval_date, expiration_date, contract_number,
            awarding_body, approval_action, source_url, source_tier,
            confidence_score.
        city_fips: FIPS code.

    Returns:
        Dict with inserted/updated/skipped counts.
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    with conn.cursor() as cur:
        for rec in records:
            vendor = sanitize_text((rec.get("vendor_name") or "").strip())
            if not vendor:
                stats["skipped"] += 1
                continue

            # Generate synthetic contract_number if none provided — the
            # unique index only fires when contract_number IS NOT NULL.
            # ponytail: hash of vendor+department+fiscal_year avoids a
            # second unique index; add a real city contract_number column
            # when the city provides a contract register.
            contract_number = (rec.get("contract_number") or "").strip() or None
            if not contract_number:
                raw = f"{vendor}|{rec.get('department','')}|{rec.get('approval_date','')}"
                contract_number = f"SYN-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
            approval_date = rec.get("approval_date")

            cur.execute(
                """INSERT INTO city_contracts
                   (city_fips, vendor_name, description, annual_cost, total_cost,
                    contract_type, department, approval_date, expiration_date,
                    contract_number, awarding_body, approval_action,
                    source_url, source_tier, confidence_score)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (vendor_name, contract_number, approval_date)
                       WHERE contract_number IS NOT NULL
                   DO UPDATE SET
                       description = EXCLUDED.description,
                       annual_cost = EXCLUDED.annual_cost,
                       total_cost = EXCLUDED.total_cost,
                       expiration_date = EXCLUDED.expiration_date,
                       updated_at = NOW()
                   RETURNING (xmax = 0) AS inserted""",
                (
                    city_fips,
                    vendor,
                    sanitize_text(rec.get("description")) or None,
                    rec.get("annual_cost"),
                    rec.get("total_cost"),
                    rec.get("contract_type"),
                    rec.get("department"),
                    approval_date,
                    rec.get("expiration_date"),
                    contract_number,
                    rec.get("awarding_body"),
                    rec.get("approval_action"),
                    rec.get("source_url", ""),
                    rec.get("source_tier", 2),
                    rec.get("confidence_score"),
                ),
            )
            result = cur.fetchone()
            if result and result[0]:
                stats["inserted"] += 1
            else:
                stats["updated"] += 1

            if (stats["inserted"] + stats["updated"]) % 500 == 0:
                conn.commit()

    conn.commit()
    return stats


def match_contract_entities(
    conn,
    city_fips: str = RICHMOND_FIPS,
    match_threshold: float = 0.80,
) -> dict:
    """Match city_contracts vendors against business_entities via normalized name.

    Inserts rows into entity_name_matches (source_table='contracts') for
    vendors whose normalized name matches a business_entity. Idempotent:
    skips contracts that already have an entity_name_matches row.

    Matching uses exact normalized match — the same _normalize_name used
    for donors and officials. For fuzzy matches below threshold, the
    operator can review via the entity_name_matches review queue.

    Args:
        conn: Database connection.
        city_fips: FIPS code.
        match_threshold: Confidence threshold for auto-match (default 0.80).

    Returns:
        Dict with matched, skipped (already matched), unmatched counts.
    """
    stats = {"matched": 0, "already_matched": 0, "unmatched": 0}

    with conn.cursor() as cur:
        # Count already-matched contracts
        cur.execute(
            """SELECT COUNT(*)
               FROM entity_name_matches enm
               JOIN city_contracts cc ON cc.id = enm.source_record_id
              WHERE enm.source_table = 'contracts'
                AND cc.city_fips = %s""",
            (city_fips,),
        )
        stats["already_matched"] = cur.fetchone()[0]

        # Find contracts not yet matched
        cur.execute(
            """SELECT cc.id, cc.vendor_name
               FROM city_contracts cc
              WHERE cc.city_fips = %s
                AND NOT EXISTS (
                    SELECT 1 FROM entity_name_matches enm
                     WHERE enm.source_table = 'contracts'
                       AND enm.source_record_id = cc.id
                )""",
            (city_fips,),
        )
        unmatched_contracts = cur.fetchall()

        if not unmatched_contracts:
            return stats

        # Load all business_entities into memory — Richmond-scale data
        # fits easily; ponytail: switch to pg_trgm SIMILARITY() index scan
        # if business_entities grows past 10K rows.
        cur.execute(
            """SELECT be.id, be.entity_name
               FROM business_entities be
              WHERE be.city_fips = %s
                AND be.entity_name IS NOT NULL""",
            (city_fips,),
        )
        entities = [(row[0], row[1], _officials._normalize_name(row[1]).lower())
                    for row in cur.fetchall()]

        for contract_id, vendor_name in unmatched_contracts:
            normalized = _officials._normalize_name(vendor_name).lower()
            if not normalized:
                stats["unmatched"] += 1
                continue

            # Best match by SequenceMatcher ratio
            best = None
            best_ratio = 0.0
            for be_id, be_name, be_normalized in entities:
                ratio = SequenceMatcher(None, normalized, be_normalized).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best = (be_id, be_name)

            if best and best_ratio >= match_threshold:
                be_id, be_name = best
                method = "exact" if best_ratio >= 0.95 else (
                    "normalized" if best_ratio >= 0.85 else "fuzzy"
                )
                cur.execute(
                    """INSERT INTO entity_name_matches
                       (source_name, source_table, source_record_id,
                        business_entity_id, match_confidence, match_method)
                       VALUES (%s, 'contracts', %s, %s, %s, %s)""",
                    (vendor_name, contract_id, be_id, best_ratio, method),
                )
                stats["matched"] += 1
            else:
                stats["unmatched"] += 1

            if stats["matched"] % 100 == 0 and stats["matched"] > 0:
                conn.commit()

    conn.commit()
    return stats


# ── Influence Pattern Taxonomy (S26.3) ─────────────────────────


def classify_influence_patterns(
    conn,
    city_fips: str = RICHMOND_FIPS,
) -> dict:
    """Classify conflict_flags into influence pattern taxonomy.

    Assigns each unclassified conflict_flag to an influence_pattern based
    on its flag_type and cross-signal relationships. Idempotent: skips
    flags that already have an influence_pattern_id.

    Classification rules (order matters — first match wins):
    1. form700_investment → Conflicts of interest
    2. llc_ownership_chain → Revolving door
    3. donor_vendor_expenditure + related campaign_contribution
       on same item → Pay-to-play
    4. donor_vendor_expenditure (no related contribution) → Contract steering
    5. campaign_contribution + related donor_vendor_expenditure → Pay-to-play
    6. campaign_contribution (no related expenditure) → Pay-to-play
    7. Remaining flags → Quid pro quo permit approvals

    Args:
        conn: Database connection.
        city_fips: FIPS code.

    Returns:
        Dict with pattern counts and total classified.
    """
    stats: dict = {"total_classified": 0}

    with conn.cursor() as cur:
        # Load pattern ID map
        cur.execute(
            "SELECT id, pattern_name, signal_types FROM influence_patterns ORDER BY sort_order"
        )
        patterns = {
            row[1]: {"id": row[0], "signal_types": row[2]}
            for row in cur.fetchall()
        }

        # 1. Form700 → Conflicts of interest (direct rule)
        cur.execute(
            """UPDATE conflict_flags
               SET influence_pattern_id = %s
               WHERE city_fips = %s
                 AND influence_pattern_id IS NULL
                 AND flag_type = 'form700_investment'""",
            (patterns["Conflicts of interest (planning/zoning)"]["id"], city_fips),
        )
        stats["conflicts_of_interest"] = cur.rowcount

        # 2. LLC ownership → Revolving door (direct rule)
        cur.execute(
            """UPDATE conflict_flags
               SET influence_pattern_id = %s
               WHERE city_fips = %s
                 AND influence_pattern_id IS NULL
                 AND flag_type = 'llc_ownership_chain'""",
            (patterns["Revolving door"]["id"], city_fips),
        )
        stats["revolving_door"] = cur.rowcount

        # 3. donor_vendor_expenditure + campaign_contribution on same
        #    (official, agenda_item) pair → Pay-to-play
        cur.execute(
            """UPDATE conflict_flags cf
               SET influence_pattern_id = %s
               WHERE cf.city_fips = %s
                 AND cf.influence_pattern_id IS NULL
                 AND cf.flag_type = 'donor_vendor_expenditure'
                 AND EXISTS (
                     SELECT 1 FROM conflict_flags cf2
                     WHERE cf2.city_fips = cf.city_fips
                       AND cf2.agenda_item_id = cf.agenda_item_id
                       AND cf2.flag_type = 'campaign_contribution'
                 )""",
            (patterns["Pay-to-play"]["id"], city_fips),
        )
        stats["pay_to_play_from_expenditure"] = cur.rowcount

        # 4. Remaining donor_vendor_expenditure → Contract steering
        cur.execute(
            """UPDATE conflict_flags
               SET influence_pattern_id = %s
               WHERE city_fips = %s
                 AND influence_pattern_id IS NULL
                 AND flag_type = 'donor_vendor_expenditure'""",
            (patterns["Contract steering"]["id"], city_fips),
        )
        stats["contract_steering"] = cur.rowcount

        # 5. campaign_contribution + related donor_vendor_expenditure → Pay-to-play
        cur.execute(
            """UPDATE conflict_flags cf
               SET influence_pattern_id = %s
               WHERE cf.city_fips = %s
                 AND cf.influence_pattern_id IS NULL
                 AND cf.flag_type = 'campaign_contribution'
                 AND EXISTS (
                     SELECT 1 FROM conflict_flags cf2
                     WHERE cf2.city_fips = cf.city_fips
                       AND cf2.agenda_item_id = cf.agenda_item_id
                       AND cf2.flag_type = 'donor_vendor_expenditure'
                 )""",
            (patterns["Pay-to-play"]["id"], city_fips),
        )
        stats["pay_to_play_from_contribution"] = cur.rowcount

        # 6. Remaining campaign_contribution → Pay-to-play (default)
        cur.execute(
            """UPDATE conflict_flags
               SET influence_pattern_id = %s
               WHERE city_fips = %s
                 AND influence_pattern_id IS NULL
                 AND flag_type = 'campaign_contribution'""",
            (patterns["Pay-to-play"]["id"], city_fips),
        )
        stats["pay_to_play_remaining"] = cur.rowcount

        # 7. Remaining flags → Quid pro quo permit approvals
        #    (independent_expenditure, any future types)
        cur.execute(
            """UPDATE conflict_flags
               SET influence_pattern_id = %s
               WHERE city_fips = %s
                 AND influence_pattern_id IS NULL""",
            (patterns["Quid pro quo permit approvals"]["id"], city_fips),
        )
        stats["quid_pro_quo"] = cur.rowcount

        stats["total_classified"] = sum(
            v for k, v in stats.items() if k != "total_classified"
        )

    conn.commit()
    return stats
