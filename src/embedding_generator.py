"""
Embedding generator for Layer 3 — pgvector semantic search.

Generates embeddings for the four content tables using OpenAI
text-embedding-3-small (1536 dimensions). Each content unit is
already a compact semantic unit (200-500 tokens) that doesn't
need chunking — we embed directly on the row.

Text composition per table:
  - agenda_items: title + plain_language_summary + category + topic_label
  - meetings: meeting_type + meeting_date + meeting_summary
  - officials: name + role + bio_summary
  - motions: vote_explainer (fallback: motion_text)

Usage:
    from embedding_generator import embed_table, get_coverage_stats

    embed_table(conn, "agenda_items")   # Embed all un-embedded rows
    stats = get_coverage_stats(conn)    # Coverage per table
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
BATCH_SIZE = 100  # Texts per API call (OpenAI supports up to 2048)

# ── Text composition ────────────────────────────────────────────

TABLE_CONFIGS: dict[str, dict[str, Any]] = {
    "agenda_items": {
        "query": """
            SELECT ai.id,
                   coalesce(ai.title, '') AS title,
                   coalesce(ai.plain_language_summary, ai.description, '') AS summary,
                   coalesce(ai.category, '') AS category,
                   coalesce(ai.topic_label, '') AS topic_label
            FROM agenda_items ai
            JOIN meetings m ON m.id = ai.meeting_id
            WHERE m.city_fips = %s
              AND ai.embedding IS NULL
            ORDER BY ai.id
        """,
        "compose": lambda r: " ".join(filter(None, [
            r["title"], r["summary"], r["category"], r["topic_label"]
        ])),
    },
    "meetings": {
        "query": """
            SELECT id,
                   coalesce(meeting_type, '') AS meeting_type,
                   coalesce(to_char(meeting_date, 'FMMonth DD, YYYY'), '') AS meeting_date_str,
                   coalesce(meeting_summary, '') AS meeting_summary
            FROM meetings
            WHERE city_fips = %s
              AND embedding IS NULL
              AND meeting_summary IS NOT NULL
            ORDER BY id
        """,
        "compose": lambda r: " ".join(filter(None, [
            r["meeting_type"], "meeting", r["meeting_date_str"], r["meeting_summary"]
        ])),
    },
    "officials": {
        "query": """
            SELECT id,
                   coalesce(name, '') AS name,
                   coalesce(role, '') AS role,
                   coalesce(bio_summary, '') AS bio_summary
            FROM officials
            WHERE city_fips = %s
              AND embedding IS NULL
              AND bio_summary IS NOT NULL
            ORDER BY id
        """,
        "compose": lambda r: " ".join(filter(None, [
            r["name"], r["role"], r["bio_summary"]
        ])),
    },
    "motions": {
        "query": """
            SELECT mo.id,
                   coalesce(mo.vote_explainer, mo.motion_text, '') AS text
            FROM motions mo
            JOIN agenda_items ai ON ai.id = mo.agenda_item_id
            JOIN meetings m ON m.id = ai.meeting_id
            WHERE m.city_fips = %s
              AND mo.embedding IS NULL
            ORDER BY mo.id
        """,
        "compose": lambda r: r["text"],
    },
}


def _get_openai_client():
    """Lazy-import OpenAI client."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "openai package required for embeddings. "
            "Install with: pip install openai"
        )
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Add it to .env or environment."
        )
    return OpenAI(api_key=api_key)


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts via OpenAI API.

    Returns list of 1536-dimensional float vectors, one per input text.
    Empty texts get zero vectors to avoid API errors.
    """
    client = _get_openai_client()

    # Filter empties — OpenAI rejects empty strings
    non_empty_indices = [i for i, t in enumerate(texts) if t.strip()]
    non_empty_texts = [texts[i] for i in non_empty_indices]

    if not non_empty_texts:
        return [[0.0] * DIMENSIONS] * len(texts)

    response = client.embeddings.create(
        model=MODEL,
        input=non_empty_texts,
        dimensions=DIMENSIONS,
    )

    # Map back to original positions
    result: list[list[float]] = [[0.0] * DIMENSIONS] * len(texts)
    for idx, emb_data in zip(non_empty_indices, response.data):
        result[idx] = emb_data.embedding

    return result


def embed_table(
    conn,
    table_name: str,
    city_fips: str = "0660620",
    limit: int | None = None,
) -> int:
    """Generate and store embeddings for un-embedded rows in a table.

    Returns the number of rows embedded.
    """
    if table_name not in TABLE_CONFIGS:
        raise ValueError(f"Unknown table: {table_name}. Valid: {list(TABLE_CONFIGS)}")

    config = TABLE_CONFIGS[table_name]
    query = config["query"]
    compose = config["compose"]

    if limit:
        query = query.rstrip().rstrip(";") + f" LIMIT {limit}"

    with conn.cursor(cursor_factory=_dict_cursor_factory()) as cur:
        cur.execute(query, (city_fips,))
        rows = cur.fetchall()

    if not rows:
        logger.info(f"{table_name}: all rows already embedded")
        return 0

    logger.info(f"{table_name}: {len(rows)} rows to embed")
    total_embedded = 0

    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        texts = [compose(r) for r in batch]

        # Skip batch if all texts are empty
        if not any(t.strip() for t in texts):
            logger.warning(f"{table_name}: skipping batch of {len(batch)} empty texts")
            continue

        embeddings = generate_embeddings(texts)
        now = datetime.now(timezone.utc)

        with conn.cursor() as cur:
            for row, embedding in zip(batch, embeddings):
                # Skip zero vectors (from empty text)
                if all(v == 0.0 for v in embedding[:10]):
                    continue
                cur.execute(
                    f"""
                    UPDATE {table_name}
                    SET embedding = %s::vector,
                        embedding_model = %s,
                        embedding_generated_at = %s
                    WHERE id = %s
                    """,
                    (embedding, MODEL, now, row["id"]),
                )
                total_embedded += 1
        conn.commit()

        logger.info(
            f"{table_name}: embedded batch {batch_start // BATCH_SIZE + 1}"
            f" ({total_embedded}/{len(rows)})"
        )
        # Small delay between batches to be polite to OpenAI
        if batch_start + BATCH_SIZE < len(rows):
            time.sleep(0.1)

    logger.info(f"{table_name}: done — {total_embedded} rows embedded")
    return total_embedded


def embed_query(query_text: str) -> list[float]:
    """Generate embedding for a single search query.

    Used by the search API route to embed user queries for hybrid search.
    Returns a 1536-dimensional float vector.
    """
    result = generate_embeddings([query_text])
    return result[0]


def get_coverage_stats(conn, city_fips: str = "0660620") -> dict[str, dict[str, int]]:
    """Get embedding coverage statistics per table.

    Returns dict like:
        {"agenda_items": {"total": 15000, "embedded": 12000, "pending": 3000}, ...}
    """
    stats = {}
    with conn.cursor() as cur:
        for table_name, config in TABLE_CONFIGS.items():
            # Count total eligible rows
            if table_name == "agenda_items":
                cur.execute(
                    """SELECT count(*) FROM agenda_items ai
                       JOIN meetings m ON m.id = ai.meeting_id
                       WHERE m.city_fips = %s""",
                    (city_fips,),
                )
            elif table_name == "motions":
                cur.execute(
                    """SELECT count(*) FROM motions mo
                       JOIN agenda_items ai ON ai.id = mo.agenda_item_id
                       JOIN meetings m ON m.id = ai.meeting_id
                       WHERE m.city_fips = %s""",
                    (city_fips,),
                )
            else:
                cur.execute(
                    f"SELECT count(*) FROM {table_name} WHERE city_fips = %s",
                    (city_fips,),
                )
            total = cur.fetchone()[0]

            # Count embedded rows
            if table_name == "agenda_items":
                cur.execute(
                    """SELECT count(*) FROM agenda_items ai
                       JOIN meetings m ON m.id = ai.meeting_id
                       WHERE m.city_fips = %s AND ai.embedding IS NOT NULL""",
                    (city_fips,),
                )
            elif table_name == "motions":
                cur.execute(
                    """SELECT count(*) FROM motions mo
                       JOIN agenda_items ai ON ai.id = mo.agenda_item_id
                       JOIN meetings m ON m.id = ai.meeting_id
                       WHERE m.city_fips = %s AND mo.embedding IS NOT NULL""",
                    (city_fips,),
                )
            else:
                cur.execute(
                    f"SELECT count(*) FROM {table_name} WHERE city_fips = %s AND embedding IS NOT NULL",
                    (city_fips,),
                )
            embedded = cur.fetchone()[0]

            stats[table_name] = {
                "total": total,
                "embedded": embedded,
                "pending": total - embedded,
            }
    return stats


def _dict_cursor_factory():
    """Return psycopg2 DictCursor factory."""
    import psycopg2.extras
    return psycopg2.extras.DictCursor
