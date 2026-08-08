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

import llm_budget_lock

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
BATCH_SIZE = 100  # Texts per API call (OpenAI supports up to 2048)
EMBEDDING_USD_PER_MILLION_TOKENS = 0.02


class EmbeddingAccountingError(RuntimeError):
    """Raised when a paid embedding cannot be accounted for safely."""

# ── Text composition ────────────────────────────────────────────

# Each entry maps a base table to its embedding sidecar (migration 111).
# Embedding writes target the sidecar; the "not yet embedded" query LEFT
# JOINs the sidecar and filters where the join produced no row.
TABLE_CONFIGS: dict[str, dict[str, Any]] = {
    "agenda_items": {
        "sidecar": "agenda_items_embeddings",
        "query": """
            SELECT ai.id,
                   coalesce(ai.title, '') AS title,
                   coalesce(ai.plain_language_summary, ai.description, '') AS summary,
                   coalesce(ai.category, '') AS category,
                   coalesce(ai.topic_label, '') AS topic_label
            FROM agenda_items ai
            JOIN meetings m ON m.id = ai.meeting_id
            LEFT JOIN agenda_items_embeddings aie ON aie.id = ai.id
            WHERE m.city_fips = %s
              AND ai.agenda_source_retired_at IS NULL
              AND m.source_cancelled_at IS NULL
              AND aie.id IS NULL
            ORDER BY ai.id
        """,
        "compose": lambda r: " ".join(filter(None, [
            r["title"], r["summary"], r["category"], r["topic_label"]
        ])),
    },
    "meetings": {
        "sidecar": "meetings_embeddings",
        "query": """
            SELECT m.id,
                   coalesce(m.meeting_type, '') AS meeting_type,
                   coalesce(to_char(m.meeting_date, 'FMMonth DD, YYYY'), '') AS meeting_date_str,
                   coalesce(m.meeting_summary, '') AS meeting_summary
            FROM meetings m
            LEFT JOIN meetings_embeddings me ON me.id = m.id
            WHERE m.city_fips = %s
              AND me.id IS NULL
              AND m.meeting_summary IS NOT NULL
            ORDER BY m.id
        """,
        "compose": lambda r: " ".join(filter(None, [
            r["meeting_type"], "meeting", r["meeting_date_str"], r["meeting_summary"]
        ])),
    },
    "officials": {
        "sidecar": "officials_embeddings",
        "query": """
            SELECT o.id,
                   coalesce(o.name, '') AS name,
                   coalesce(o.role, '') AS role,
                   coalesce(o.bio_summary, '') AS bio_summary
            FROM officials o
            LEFT JOIN officials_embeddings oe ON oe.id = o.id
            WHERE o.city_fips = %s
              AND oe.id IS NULL
              AND o.bio_summary IS NOT NULL
            ORDER BY o.id
        """,
        "compose": lambda r: " ".join(filter(None, [
            r["name"], r["role"], r["bio_summary"]
        ])),
    },
    "motions": {
        "sidecar": "motions_embeddings",
        "query": """
            SELECT mo.id,
                   coalesce(mo.vote_explainer, mo.motion_text, '') AS text
            FROM motions mo
            JOIN agenda_items ai ON ai.id = mo.agenda_item_id
            JOIN meetings m ON m.id = ai.meeting_id
            LEFT JOIN motions_embeddings moe ON moe.id = mo.id
            WHERE m.city_fips = %s
              AND ai.agenda_source_retired_at IS NULL
              AND m.source_cancelled_at IS NULL
              AND moe.id IS NULL
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
    # The SDK otherwise retries selected failures twice. A retry is another
    # potentially billable request that the single reservation cannot prove,
    # so retries are disabled at the client boundary.
    return OpenAI(api_key=api_key, max_retries=0)


def _embedding_cost(token_count: int) -> float:
    """Return exact text-embedding-3-small input cost at $0.02 / 1M."""
    if token_count < 0:
        raise ValueError("Embedding token count cannot be negative")
    return token_count / 1_000_000.0 * EMBEDDING_USD_PER_MILLION_TOKENS


def _conservative_input_token_ceiling(texts: list[str]) -> int:
    """Bound tokenizer usage without making an unmetered tokenizer call.

    OpenAI's embedding tokenizer operates on UTF-8 bytes, and every token
    consumes at least one byte. The encoded byte count is therefore a safe
    request ceiling while remaining much tighter than reserving the API-wide
    300k-token batch maximum for every small Richmond content batch.
    """
    return sum(len(text.encode("utf-8")) for text in texts)


def _reserve_embedding_budget(texts: list[str]):
    """Apply the shared kill/event/monthly rails and return a reservation ID."""
    projected_cost = _embedding_cost(_conservative_input_token_ceiling(texts))
    # This shared preflight serializes the event-cap check, atomic monthly
    # reservation, and process-local ceiling so concurrent calls cannot race.
    return llm_budget_lock._reserve_projected_spend_pre_call(
        MODEL,
        projected_cost,
        caller="embedding_generator",
    )


def _settle_embedding_cost(reservation_id, response) -> int:
    """Settle from provider usage and append the matching cost journal row."""
    usage = getattr(response, "usage", None)
    raw_tokens = getattr(usage, "total_tokens", None)
    if (
        isinstance(raw_tokens, bool)
        or not isinstance(raw_tokens, int)
        or raw_tokens <= 0
    ):
        # The open reservation remains at its conservative ceiling. Poisoning
        # prevents this process from spending again with ambiguous accounting.
        llm_budget_lock._invalidate_mtd_cache(poison=True)
        raise EmbeddingAccountingError(
            "OpenAI embedding response omitted valid usage.total_tokens"
        )

    actual_cost = _embedding_cost(raw_tokens)
    settlement_metadata = {
        "provider": "openai",
        "input_tokens": raw_tokens,
        "output_tokens": 0,
        "price_per_million_tokens": EMBEDDING_USD_PER_MILLION_TOKENS,
    }
    try:
        settled = llm_budget_lock._settle_cost_reservation(
            reservation_id,
            actual_cost,
            metadata=settlement_metadata,
        )
        logged = llm_budget_lock._log_cost(
            MODEL,
            raw_tokens,
            0,
            actual_cost,
            "embedding_generator",
            extra={
                **settlement_metadata,
                "reservation_id": str(reservation_id),
            },
        )
    except Exception as exc:
        llm_budget_lock._invalidate_mtd_cache(poison=True)
        raise EmbeddingAccountingError(
            "Embedding cost accounting raised after the provider call"
        ) from exc
    if not settled or not logged:
        llm_budget_lock._invalidate_mtd_cache(poison=True)
        failed = []
        if not settled:
            failed.append("reservation settlement")
        if not logged:
            failed.append("cost journal")
        raise EmbeddingAccountingError(
            "Embedding cost accounting failed after the provider call: "
            + ", ".join(failed)
        )

    try:
        # Durable accounting succeeded. Replace the conservative local ceiling
        # with actual usage; every earlier failure path deliberately retains it.
        llm_budget_lock._settle_process_spend(reservation_id, actual_cost)
    except Exception as exc:
        llm_budget_lock._invalidate_mtd_cache(poison=True)
        raise EmbeddingAccountingError(
            "Embedding process-spend settlement failed after durable accounting"
        ) from exc

    llm_budget_lock._add_cached_mtd_spend(actual_cost)
    return raw_tokens


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts via OpenAI API.

    Returns list of 1536-dimensional float vectors, one per input text.
    Empty texts get zero vectors to avoid API errors.
    """
    # Filter empties — OpenAI rejects empty strings
    non_empty_indices = [i for i, t in enumerate(texts) if t.strip()]
    non_empty_texts = [texts[i] for i in non_empty_indices]

    if not non_empty_texts:
        return [[0.0] * DIMENSIONS] * len(texts)

    client = _get_openai_client()
    # Reservation/accounting failures happen before the SDK request,
    # guaranteeing that an unaccounted paid call is never attempted.
    reservation_id = _reserve_embedding_budget(non_empty_texts)
    response = client.embeddings.create(
        model=MODEL,
        input=non_empty_texts,
        dimensions=DIMENSIONS,
    )
    _settle_embedding_cost(reservation_id, response)

    if len(response.data) != len(non_empty_texts):
        raise RuntimeError(
            "OpenAI embedding response length did not match the input batch"
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

        sidecar = config["sidecar"]
        with conn.cursor() as cur:
            for row, embedding in zip(batch, embeddings):
                # Skip zero vectors (from empty text)
                if all(v == 0.0 for v in embedding[:10]):
                    continue
                cur.execute(
                    f"""
                    INSERT INTO {sidecar} (id, embedding, embedding_model, embedding_generated_at)
                    VALUES (%s, %s::halfvec, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        embedding_model = EXCLUDED.embedding_model,
                        embedding_generated_at = EXCLUDED.embedding_generated_at
                    """,
                    (row["id"], embedding, MODEL, now),
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
                       WHERE m.city_fips = %s
                         AND ai.agenda_source_retired_at IS NULL
                         AND m.source_cancelled_at IS NULL""",
                    (city_fips,),
                )
            elif table_name == "motions":
                cur.execute(
                    """SELECT count(*) FROM motions mo
                       JOIN agenda_items ai ON ai.id = mo.agenda_item_id
                       JOIN meetings m ON m.id = ai.meeting_id
                       WHERE m.city_fips = %s
                         AND ai.agenda_source_retired_at IS NULL
                         AND m.source_cancelled_at IS NULL""",
                    (city_fips,),
                )
            else:
                cur.execute(
                    f"SELECT count(*) FROM {table_name} WHERE city_fips = %s",
                    (city_fips,),
                )
            total = cur.fetchone()[0]

            # Count embedded rows (sidecar tables, migration 111)
            sidecar = config["sidecar"]
            if table_name == "agenda_items":
                cur.execute(
                    f"""SELECT count(*) FROM {sidecar} s
                       JOIN agenda_items ai ON ai.id = s.id
                       JOIN meetings m ON m.id = ai.meeting_id
                       WHERE m.city_fips = %s
                         AND ai.agenda_source_retired_at IS NULL
                         AND m.source_cancelled_at IS NULL""",
                    (city_fips,),
                )
            elif table_name == "motions":
                cur.execute(
                    f"""SELECT count(*) FROM {sidecar} s
                       JOIN motions mo ON mo.id = s.id
                       JOIN agenda_items ai ON ai.id = mo.agenda_item_id
                       JOIN meetings m ON m.id = ai.meeting_id
                       WHERE m.city_fips = %s
                         AND ai.agenda_source_retired_at IS NULL
                         AND m.source_cancelled_at IS NULL""",
                    (city_fips,),
                )
            else:
                cur.execute(
                    f"""SELECT count(*) FROM {sidecar} s
                       JOIN {table_name} t ON t.id = s.id
                       WHERE t.city_fips = %s""",
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
