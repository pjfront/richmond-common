"""
Richmond Common — Topic Tagger

Assigns civic topics to agenda items. Two modes:
  1. Keyword matching (fast, free — for backfill and incremental)
  2. LLM extraction (future — for discovering topics beyond the keyword list)

Keywords mirror web/src/lib/local-issues.ts. The database is the source of
truth; the frontend keyword list becomes a fallback for client-side display
before the DB-backed system is wired.

Usage:
    # Detect topics in text
    from topic_tagger import tag_topics
    matches = tag_topics("Approve Chevron refinery air quality permit")
    # [TopicMatch(slug='chevron', confidence=1.0, source='keyword'),
    #  TopicMatch(slug='environment', confidence=1.0, source='keyword')]

    # Batch backfill existing agenda items
    python topic_tagger.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


# ── Topic keyword definitions ──
# Mirrors web/src/lib/local-issues.ts. Single source of truth for keywords.
# When adding keywords here, also update local-issues.ts (and vice versa).

@dataclass
class TopicDef:
    """Definition of a topic with its keyword patterns."""
    slug: str
    name: str
    keywords: list[str]
    primary_category: str = ""


TOPIC_DEFS: list[TopicDef] = [
    TopicDef(
        slug="chevron",
        name="Chevron & the Refinery",
        keywords=[
            "chevron", "refinery", "richmond refinery",
            "flaring", "flare", "crude oil", "hydrogen",
            "community benefits agreement", "cba",
            "richmond standard",
        ],
        primary_category="environment",
    ),
    TopicDef(
        slug="point-molate",
        name="Point Molate",
        keywords=[
            "point molate", "pt. molate", "pt molate",
            "winehaven", "wine haven",
        ],
        primary_category="zoning",
    ),
    TopicDef(
        slug="rent-board",
        name="Rent Board & Tenants",
        keywords=[
            "rent control", "rent board", "rent program",
            "rent stabilization", "rent adjustment",
            "just cause", "just cause eviction",
            "tenant", "tenants", "tenant protection",
            "eviction", "relocation payment",
            "habitability", "rental inspection",
        ],
        primary_category="housing",
    ),
    TopicDef(
        slug="hilltop",
        name="The Hilltop",
        keywords=[
            "hilltop", "hilltop mall", "hilltop district",
            "dream fleetwood",
        ],
        primary_category="zoning",
    ),
    TopicDef(
        slug="terminal-port",
        name="Terminal 1 & the Port",
        keywords=[
            "terminal 1", "terminal one",
            "port of richmond", "port director",
            "maritime", "ferry service", "ferry terminal",
            "offshore wind", "wharf",
        ],
        primary_category="infrastructure",
    ),
    TopicDef(
        slug="ford-point",
        name="Ford Point & Richmond Village",
        keywords=[
            "ford assembly", "ford point", "ford building",
            "richmond village", "craneway",
            "assemble", "marina bay",
        ],
        primary_category="zoning",
    ),
    TopicDef(
        slug="macdonald",
        name="Macdonald Avenue",
        keywords=[
            "macdonald avenue", "macdonald corridor",
            "macdonald task force",
            "iron triangle",
            "downtown richmond",
        ],
        primary_category="infrastructure",
    ),
    TopicDef(
        slug="police-reform",
        name="Police & Community Safety",
        keywords=[
            "police", "rpd", "police department",
            "public safety", "law enforcement",
            "officer involved", "officer-involved",
            "use of force", "body-worn camera", "body worn camera",
            "community police review", "cprc",
            "crisis intervention", "crisis response",
            "neighborhood safety", "ons",
            "gun violence", "firearm",
            "crime report", "crime prevention",
        ],
        primary_category="public_safety",
    ),
    TopicDef(
        slug="environment",
        name="Environmental Justice",
        keywords=[
            "climate", "environmental",
            "greenhouse", "carbon", "emissions",
            "air quality", "air monitoring",
            "pollution", "contamination", "contaminated",
            "brownfield", "remediation", "superfund",
            "toxic", "hazardous",
            "green new deal", "solar", "sustainability",
            "transformative climate",
            "urban greening", "greenway", "richmond greenway",
        ],
        primary_category="environment",
    ),
    TopicDef(
        slug="labor",
        name="Labor & City Workers",
        keywords=[
            "seiu", "local 1021",
            "memorandum of understanding",
            "collective bargaining",
            "overtime report", "pension",
            "opeb", "other post-employment",
            "staffing", "vacancy", "vacancies",
            "cost of living increase",
        ],
        primary_category="personnel",
    ),
    TopicDef(
        slug="cannabis",
        name="Cannabis",
        keywords=[
            "cannabis", "marijuana",
            "dispensary", "dispensaries",
            "cannabis tax",
        ],
        primary_category="governance",
    ),
    TopicDef(
        slug="youth",
        name="Youth & Community Programs",
        keywords=[
            "youth", "young adults",
            "youth outdoors richmond",
            "ryse", "mentoring", "mentor",
            "afterschool", "after-school", "after school",
            "workforce development board",
            "job training", "job center",
            "american job centers",
        ],
        primary_category="budget",
    ),
    TopicDef(
        slug="political-statements",
        name="Political Statements",
        keywords=[
            "opposing", "condemning",
            "in support of", "in opposition to",
            "urging", "calling upon",
            "ceasefire", "solidarity",
            "resolution declaring", "resolution opposing",
            "resolution supporting", "resolution urging",
            "sanctuary", "immigrant", "immigration",
            "juneteenth", "pride month",
            "day of remembrance", "black history",
            "military intervention",
        ],
        primary_category="governance",
    ),
    TopicDef(
        slug="housing-development",
        name="Housing & Homelessness",
        keywords=[
            "affordable housing", "housing element",
            "housing authority", "homekey",
            "homeless", "homelessness", "encampment",
            "transitional housing", "supportive housing",
            "section 8", "housing voucher",
            "inclusionary",
        ],
        primary_category="housing",
    ),
]

# Build slug lookup for fast access
_TOPIC_BY_SLUG: dict[str, TopicDef] = {t.slug: t for t in TOPIC_DEFS}


@dataclass
class TopicMatch:
    """A topic matched to an agenda item."""
    slug: str
    confidence: float = 1.0
    source: str = "keyword"  # "keyword", "llm", "manual"
    matched_keywords: list[str] = field(default_factory=list)


def tag_topics(
    text: str,
    topic_defs: list[TopicDef] | None = None,
) -> list[TopicMatch]:
    """Match text against topic keyword lists.

    Args:
        text: Agenda item title + description (concatenated).
        topic_defs: Override topic definitions (for testing). Defaults to TOPIC_DEFS.

    Returns:
        List of TopicMatch for each matching topic. An item can match multiple
        topics (e.g., a Chevron air quality item matches both "chevron" and
        "environment").
    """
    if not text:
        return []

    defs = topic_defs if topic_defs is not None else TOPIC_DEFS
    lower = text.lower()
    matches = []

    for topic in defs:
        matched_kws = [kw for kw in topic.keywords if kw in lower]
        if matched_kws:
            # Confidence scales with keyword hits: 1 hit = 0.8, 2+ = 1.0
            confidence = 1.0 if len(matched_kws) >= 2 else 0.8
            matches.append(TopicMatch(
                slug=topic.slug,
                confidence=confidence,
                source="keyword",
                matched_keywords=matched_kws,
            ))

    return matches


# ── Database operations ──


def _get_topic_id_map(conn, city_fips: str = "0660620") -> dict[str, str]:
    """Load slug→UUID mapping for all active topics.

    Returns dict of {slug: id_hex_string}.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT slug, id FROM topics WHERE city_fips = %s AND status = 'active'",
            (city_fips,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def load_item_topics_to_db(
    conn,
    agenda_item_id: str,
    matches: list[TopicMatch],
    topic_id_map: dict[str, str],
) -> int:
    """Save topic assignments for an agenda item.

    Args:
        conn: Database connection.
        agenda_item_id: UUID of the agenda item.
        matches: Topic matches from tag_topics().
        topic_id_map: slug→UUID mapping from _get_topic_id_map().

    Returns:
        Number of topic assignments saved.
    """
    if not matches:
        return 0

    saved = 0
    with conn.cursor() as cur:
        for match in matches:
            topic_id = topic_id_map.get(match.slug)
            if not topic_id:
                continue

            cur.execute(
                """INSERT INTO item_topics (id, agenda_item_id, topic_id, confidence, source)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (agenda_item_id, topic_id)
                   DO UPDATE SET confidence = EXCLUDED.confidence,
                                 source = EXCLUDED.source""",
                (uuid.uuid4(), agenda_item_id, topic_id, match.confidence, match.source),
            )
            saved += 1

    return saved


def backfill_topics(
    conn,
    city_fips: str = "0660620",
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Backfill topic tags for all existing agenda items.

    Scans agenda_items.title + description against keyword lists.
    Idempotent: ON CONFLICT updates existing assignments.

    Returns:
        Stats dict with items_scanned, items_tagged, assignments_created.
    """
    topic_id_map = _get_topic_id_map(conn, city_fips)
    if not topic_id_map:
        print("ERROR: No topics found in database. Run migration 049 first.")
        return {"items_scanned": 0, "items_tagged": 0, "assignments_created": 0}

    print(f"Loaded {len(topic_id_map)} active topics")

    # Fetch agenda items
    with conn.cursor() as cur:
        query = """
            SELECT ai.id, COALESCE(ai.title, '') || ' ' || COALESCE(ai.description, '') AS text
            FROM agenda_items ai
            JOIN meetings m ON m.id = ai.meeting_id
            WHERE m.city_fips = %s
            ORDER BY m.meeting_date DESC NULLS LAST, ai.item_number
        """
        params: list = [city_fips]
        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cur.execute(query, params)
        items = cur.fetchall()

    print(f"Scanning {len(items)} agenda items...")

    stats = {"items_scanned": 0, "items_tagged": 0, "assignments_created": 0}

    for i, (item_id, text) in enumerate(items):
        stats["items_scanned"] += 1
        matches = tag_topics(text)

        if matches:
            stats["items_tagged"] += 1
            if not dry_run:
                saved = load_item_topics_to_db(conn, item_id, matches, topic_id_map)
                stats["assignments_created"] += saved
            else:
                stats["assignments_created"] += len(matches)

        if (i + 1) % 2000 == 0:
            if not dry_run:
                conn.commit()
            print(f"  {i + 1}/{len(items)} scanned, {stats['items_tagged']} tagged, {stats['assignments_created']} assignments")

    if not dry_run:
        conn.commit()

    return stats


# ── CLI ──


def main():
    parser = argparse.ArgumentParser(description="Topic tagger for agenda items")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be tagged without writing to DB")
    parser.add_argument("--limit", type=int, help="Limit number of items to scan")
    parser.add_argument("--city-fips", default="0660620", help="City FIPS code")
    args = parser.parse_args()

    from db import get_connection
    conn = get_connection()

    try:
        stats = backfill_topics(conn, args.city_fips, args.limit, args.dry_run)
        prefix = "[DRY RUN] " if args.dry_run else ""
        print(f"\n{prefix}Done: {stats['items_scanned']} scanned, "
              f"{stats['items_tagged']} tagged ({stats['assignments_created']} assignments)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
