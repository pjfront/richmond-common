"""
Donor-level entity classification enrichment (S28.2).

Classifies donors by entity type using the existing name-pattern heuristics
from contributor_classifier.py. Writes to donors.entity_type and
donors.entity_slug (both added by migration 123).

Only touches rows WHERE entity_type IS NULL — idempotent on re-run.

Reads from contributor_classifier.py. Does NOT read from contributions or
any derivative table. Does NOT call external APIs (CA SOS / Apify stay manual).

Maps contributor_classifier output to donors.entity_type enum:
  corporate  -> corporation
  union      -> union
  individual -> person
  pac_ie     -> committee
  other      -> other_org
"""
from __future__ import annotations

import re

from contributor_classifier import (
    classify_contributor,
    CORPORATE,
    UNION,
    INDIVIDUAL,
    PAC_IE,
    OTHER,
)

# ── Mapping: contributor_classifier output -> donors.entity_type ──
_CLASS_TO_ENTITY_TYPE: dict[str, str] = {
    CORPORATE: "corporation",
    UNION: "union",
    INDIVIDUAL: "person",
    PAC_IE: "committee",
    OTHER: "other_org",
}


def _slugify(text: str) -> str:
    """Convert a donor name to a URL-safe slug.

    Lowercases, replaces runs of non-alphanumeric chars with hyphens,
    strips leading/trailing hyphens, caps at 200 chars (well under
    the VARCHAR(400) column limit).
    """
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:200]


def _resolve_slug(cur, base_slug: str, donor_id: str) -> str:
    """Return a unique slug, appending -2, -3, ... on collision.

    ponytail: per-donor SELECT is fine — the donors table is <5000 rows
    city-wide and only ~5-15 new donors/week hit this path.
    """
    slug = base_slug
    counter = 1
    while True:
        cur.execute(
            "SELECT 1 FROM donors WHERE entity_slug = %s AND id != %s",
            (slug, donor_id),
        )
        if not cur.fetchone():
            return slug
        counter += 1
        slug = f"{base_slug}-{counter}"


def sync_donor_classification(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id: int | None = None,
) -> dict:
    """Classify all untyped donors and generate entity slugs.

    Only processes donors WHERE entity_type IS NULL.
    Idempotent: re-running on a clean state is a no-op.

    Returns dict with keys: records_fetched, records_classified, errors.
    """
    stats: dict[str, int] = {
        "records_fetched": 0,
        "records_classified": 0,
        "errors": 0,
    }

    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, name, normalized_name
                 FROM donors
                WHERE entity_type IS NULL
                ORDER BY normalized_name""",
        )
        rows = cur.fetchall()
        stats["records_fetched"] = len(rows)

        for donor_id, name, normalized_name in rows:
            try:
                # Classify by name alone (no entity_code at donor level)
                cls_type, _source_label = classify_contributor(
                    name=name, entity_code=None, source="netfile",
                )
                entity_type = _CLASS_TO_ENTITY_TYPE.get(cls_type, "other_org")

                # Slug from normalized_name (more stable than raw name)
                slug = _slugify(normalized_name)
                slug = _resolve_slug(cur, slug, donor_id)

                cur.execute(
                    """UPDATE donors
                          SET entity_type = %s, entity_slug = %s
                        WHERE id = %s""",
                    (entity_type, slug, donor_id),
                )
                stats["records_classified"] += 1
            except Exception:
                stats["errors"] += 1

    conn.commit()
    return stats
