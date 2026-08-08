"""
db.officials — extracted from db.py (Phase 2.1).

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

from ._core import RICHMOND_FIPS


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
    Searches all officials (current and former). Prefers current officials
    when scores are tied.
    """
    cur.execute(
        """SELECT id, normalized_name, is_current FROM officials
           WHERE city_fips = %s
           ORDER BY is_current DESC""",
        (city_fips,),
    )
    best_id = None
    best_name = None
    best_score = 0.0

    for row in cur.fetchall():
        existing_id, existing_name, _is_current = row
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
    *,
    commit: bool = True,
) -> uuid.UUID:
    """Find or create an official. Returns the official ID.

    Matching strategy (in order):
    1. Exact match on normalized name (all officials, not just current)
    2. Alias match from officials.json (e.g., "Kinshasa Curl" -> "Shasa Curl")
    3. Fuzzy match (SequenceMatcher ratio >= threshold) to catch typos
    4. Create new record if no match found
    """
    normalized = _normalize_name(name)
    with conn.cursor() as cur:
        # 1. Exact match — search ALL officials (current and former)
        cur.execute(
            """SELECT id FROM officials
               WHERE city_fips = %s AND normalized_name = %s
               ORDER BY is_current DESC
               LIMIT 1""",
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
                   WHERE city_fips = %s AND normalized_name = %s
                   ORDER BY is_current DESC
                   LIMIT 1""",
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

        # 4. No match — create new record (is_current defaults to false;
        #    only the ground-truth migration sets current members to true)
        official_id = uuid.uuid4()
        cur.execute(
            """INSERT INTO officials (id, city_fips, name, normalized_name, role, is_current)
               VALUES (%s, %s, %s, %s, %s, FALSE)""",
            (official_id, city_fips, name, normalized, role),
        )
        if commit:
            conn.commit()
        return official_id


def _default_role_for_body_type(body_type: Optional[str]) -> str:
    """Map body_type to the default official role for members of that body.

    Used when the extraction data doesn't include an explicit role.
    Prevents commission/board members from being tagged as 'councilmember'.
    """
    return {
        "city_council": "councilmember",
        "commission": "commissioner",
        "board": "board_member",
        "authority": "board_member",
        "committee": "committee_member",
        "joint": "member",
    }.get(body_type or "", "councilmember")


def _resolve_body_type(conn, body_id: Optional[uuid.UUID]) -> Optional[str]:
    """Look up body_type for a given body_id. Returns None if not found."""
    if body_id is None:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT body_type FROM bodies WHERE id = %s", (body_id,))
        row = cur.fetchone()
        return row[0] if row else None


def resolve_body_id(
    conn, city_fips: str, body_name: str,
) -> Optional[uuid.UUID]:
    """Look up body_id by name for a city. Returns None if not found."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM bodies WHERE city_fips = %s AND name = %s",
            (city_fips, body_name),
        )
        row = cur.fetchone()
        return row[0] if row else None
