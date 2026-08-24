"""
Generate pre-meeting orientation previews from agenda item data.

Reads source-closest persisted agenda item titles and descriptions from the
official agenda. Does NOT read AI-generated item summaries or topic labels,
existing orientation previews, meeting summaries, or recaps (derivatives).

Produces a 3-5 paragraph narrative preview for each meeting, stored in
meetings.orientation_preview. Uses only bounded official agenda text to create
a forward-looking "what to watch for" briefing.

Unlike meeting_summary (which requires votes/minutes), orientations can
be generated immediately when agenda items are scraped from eSCRIBE.

Usage:
    python generate_orientation_previews.py                  # all ungenerated
    python generate_orientation_previews.py --limit 10       # first 10
    python generate_orientation_previews.py --meeting-id X   # specific meeting
    python generate_orientation_previews.py --force           # regenerate bounded upcoming batch
    python generate_orientation_previews.py --dry-run         # preview without saving

Publication tier: Public (factual presentation of published agenda data).
"""
from __future__ import annotations

from llm_client import LLMClient

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import provenance as prov  # noqa: E402
from orientation_scope import (  # noqa: E402
    ORIENTATION_CANDIDATE_CAP,
    ORIENTATION_CONTEXT_MAX_CHARS,
    ORIENTATION_DESCRIPTION_MAX_CHARS,
    ORIENTATION_ELIGIBLE_AGENDA_ITEMS_SQL,
    ORIENTATION_ITEM_NUMBER_MAX_CHARS,
    ORIENTATION_LOOKAHEAD_DAYS,
    ORIENTATION_SECTION_ITEM_CAP,
    ORIENTATION_SECTION_FETCH_CAP,
    ORIENTATION_TITLE_MAX_CHARS,
    RICHMOND_FIPS,
    RICHMOND_TODAY_SQL,
    require_richmond_fips,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text().strip()


# ── Agenda items query (no vote data — pre-meeting) ──────────────────

_AGENDA_ITEMS_QUERY = """
    SELECT
        ai.item_number,
        ai.title,
        ai.description,
        ai.is_consent_calendar
    FROM agenda_items ai
    WHERE ai.meeting_id = %s
    AND ai.agenda_source_retired_at IS NULL
    AND NULLIF(BTRIM(CONCAT_WS(' ', ai.title, ai.description)), '') IS NOT NULL
    AND ai.is_consent_calendar = %s
    ORDER BY ai.item_number, ai.id
    LIMIT %s
"""


def _fetch_items(cur, meeting_id: str) -> list[dict]:
    """Fetch bounded source rows independently for action and consent items."""
    items: list[dict] = []
    for is_consent in (False, True):
        cur.execute(
            _AGENDA_ITEMS_QUERY,
            (meeting_id, is_consent, ORIENTATION_SECTION_FETCH_CAP),
        )
        items.extend(
            {
                "item_number": row[0],
                "title": row[1],
                "description": row[2],
                "is_consent_calendar": row[3],
            }
            for row in cur.fetchall()
        )
    return items


def _bounded_candidate_limit(requested_limit: int | None) -> int:
    """Return a positive per-run candidate limit capped by the safety rail."""
    if requested_limit is None:
        return ORIENTATION_CANDIDATE_CAP
    if requested_limit < 1:
        raise ValueError("Orientation preview limit must be at least 1")
    if requested_limit > ORIENTATION_CANDIDATE_CAP:
        logger.warning(
            "Clamping requested orientation limit %s to hard cap %s",
            requested_limit,
            ORIENTATION_CANDIDATE_CAP,
        )
    return min(requested_limit, ORIENTATION_CANDIDATE_CAP)


def _select_candidate_meetings(
    cur,
    *,
    city_fips: str,
    force: bool,
    meeting_id: str | None,
    limit: int | None,
) -> list[tuple]:
    """Select a bounded, Richmond-only batch of eligible upcoming meetings."""
    require_richmond_fips(city_fips)

    query = f"""
        SELECT m.id, m.meeting_date, m.meeting_type, m.agenda_url
        FROM meetings m
        JOIN bodies b ON b.id = m.body_id AND b.city_fips = m.city_fips
        WHERE m.city_fips = %s
          AND b.city_fips = %s
          AND b.body_type = 'city_council'
          AND m.meeting_type = 'regular'
          AND m.source_cancelled_at IS NULL
          AND m.meeting_date >= {RICHMOND_TODAY_SQL}
          AND m.meeting_date <= {RICHMOND_TODAY_SQL} + %s
          AND {ORIENTATION_ELIGIBLE_AGENDA_ITEMS_SQL}
    """
    params: list[object] = [city_fips, city_fips, ORIENTATION_LOOKAHEAD_DAYS]

    if not force:
        query += " AND m.orientation_preview IS NULL"

    if meeting_id:
        query += " AND m.id = %s"
        params.append(meeting_id)
        candidate_limit = 1
    else:
        candidate_limit = _bounded_candidate_limit(limit)

    query += " ORDER BY m.meeting_date ASC, m.id ASC LIMIT %s"
    params.append(candidate_limit)
    cur.execute(query, tuple(params))
    return cur.fetchall()


def _clean_source_text(value: object, max_chars: int) -> str:
    """Collapse whitespace and bound one source field for prompt safety."""
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _build_orientation_context(items: list[dict]) -> str:
    """Build a deterministic, bounded prompt from official agenda text."""
    lines = []
    consent_items = []
    action_items = []

    for item in items:
        if item.get("is_consent_calendar"):
            consent_items.append(item)
        else:
            action_items.append(item)

    if consent_items:
        consent_truncated = len(consent_items) > ORIENTATION_SECTION_ITEM_CAP
        consent_count = min(len(consent_items), ORIENTATION_SECTION_ITEM_CAP)
        consent_heading = f"CONSENT CALENDAR ({consent_count} items shown"
        if consent_truncated:
            consent_heading += "; additional items omitted by safety limit"
        lines.append(consent_heading + "):")
        for item in consent_items[:ORIENTATION_SECTION_ITEM_CAP]:
            number = _clean_source_text(
                item.get("item_number"), ORIENTATION_ITEM_NUMBER_MAX_CHARS,
            )
            title = _clean_source_text(item.get("title"), ORIENTATION_TITLE_MAX_CHARS)
            description = _clean_source_text(
                item.get("description"), ORIENTATION_DESCRIPTION_MAX_CHARS,
            )
            lines.append(f"  - Item {number}: {title}")
            if description and description != title:
                lines.append(f"    Agenda description: {description}")
        if consent_truncated:
            lines.append("  - ... additional consent items omitted by safety limit")

    if action_items:
        action_truncated = len(action_items) > ORIENTATION_SECTION_ITEM_CAP
        action_count = min(len(action_items), ORIENTATION_SECTION_ITEM_CAP)
        action_heading = f"\nACTION ITEMS ({action_count} items shown"
        if action_truncated:
            action_heading += "; additional items omitted by safety limit"
        lines.append(action_heading + "):")
        for item in action_items[:ORIENTATION_SECTION_ITEM_CAP]:
            number = _clean_source_text(
                item.get("item_number"), ORIENTATION_ITEM_NUMBER_MAX_CHARS,
            )
            title = _clean_source_text(item.get("title"), ORIENTATION_TITLE_MAX_CHARS)
            description = _clean_source_text(
                item.get("description"), ORIENTATION_DESCRIPTION_MAX_CHARS,
            )
            lines.append(f"  - Item {number}: {title}")
            if description and description != title:
                lines.append(f"    Agenda description: {description}")
        if action_truncated:
            lines.append("  - ... additional action items omitted by safety limit")

    context = "\n".join(lines)
    if len(context) > ORIENTATION_CONTEXT_MAX_CHARS:
        marker = "\n... additional agenda text omitted by the safety limit"
        context = context[: ORIENTATION_CONTEXT_MAX_CHARS - len(marker)].rstrip() + marker
    return context


def _parse_orientation(text: str) -> str | None:
    """Parse JSON response to extract orientation_preview."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
        return (data.get("orientation_preview") or "").strip() or None
    except (json.JSONDecodeError, AttributeError):
        # Last resort: try to extract orientation_preview from partial JSON
        if '"orientation_preview"' in text:
            try:
                import re
                match = re.search(r'"orientation_preview"\s*:\s*"(.*)"', text, re.DOTALL)
                if match:
                    # Unescape JSON string
                    raw_val = match.group(1)
                    return raw_val.replace("\\n", "\n").strip() or None
            except Exception:
                pass
        logger.warning("Failed to parse JSON, using raw text")
        return text.strip() or None


def generate_orientation(
    items: list[dict],
) -> dict[str, str | None]:
    """Generate a pre-meeting orientation from agenda item data.

    Returns dict with 'orientation_preview' and 'model' keys.
    """
    system_prompt = _load_prompt("orientation_preview_system.txt")
    context = _build_orientation_context(items)

    if not context.strip():
        return {"orientation_preview": None, "model": None}

    user_prompt = f"Write a pre-meeting orientation for this city council agenda:\n\n{context}"

    client = LLMClient(timeout=60.0)
    response = client.messages.create(
        model="deepseek-v4-pro",
        max_tokens=800,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    preview = _parse_orientation(response.content[0].text)
    return {"orientation_preview": preview, "model": response.model}


def generate_previews(
    conn,
    city_fips: str = RICHMOND_FIPS,
    force: bool = False,
    meeting_id: str | None = None,
    limit: int | None = None,
    delay: float = 0.5,
) -> dict:
    """Generate orientation previews. Callable from data_sync or CLI.

    Returns dict with 'total', 'generated', 'skipped', 'errors' counts.
    """
    stats = {"total": 0, "generated": 0, "skipped": 0, "errors": 0}

    with conn.cursor() as cur:
        # No vote gate: the source-material EXISTS clause is the eligibility gate.
        meetings = _select_candidate_meetings(
            cur,
            city_fips=city_fips,
            force=force,
            meeting_id=meeting_id,
            limit=limit,
        )

        stats["total"] = len(meetings)
        logger.info(f"Found {len(meetings)} meetings to generate orientations for")

        for mid, meeting_date, meeting_type, agenda_url in meetings:
            items = _fetch_items(cur, mid)

            if not items:
                logger.info(f"  {meeting_date} ({meeting_type}): no non-procedural items, skipping")
                stats["skipped"] += 1
                continue

            logger.info(f"  {meeting_date} ({meeting_type}): {len(items)} source items")

            try:
                result = generate_orientation(items)
                if result["orientation_preview"]:
                    p = prov.agenda_packet(
                        agenda_url=agenda_url,
                        generator="generate_orientation_previews.py",
                    )
                    update_sql = (
                        "UPDATE meetings SET orientation_preview = %s, "
                        "orientation_preview_provenance = %s WHERE id = %s"
                    )
                    if not force:
                        update_sql += " AND orientation_preview IS NULL"
                    cur.execute(
                        update_sql,
                        (result["orientation_preview"], prov.to_json(p), mid),
                    )
                    if cur.rowcount != 1:
                        conn.rollback()
                        logger.info(
                            "    Preview changed before save; preserving the existing value"
                        )
                        stats["skipped"] += 1
                        continue
                    conn.commit()
                    logger.info(f"    Saved orientation ({len(result['orientation_preview'])} chars)")
                    stats["generated"] += 1
                else:
                    logger.warning(f"    No orientation generated")
                    stats["skipped"] += 1
            except Exception as e:
                logger.error(f"    Error: {e}")
                conn.rollback()
                stats["errors"] += 1

            if delay > 0:
                time.sleep(delay)

    logger.info(f"Done. Generated {stats['generated']}/{stats['total']} orientations.")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate pre-meeting orientation previews")
    parser.add_argument(
        "--limit",
        type=int,
        help=f"Max meetings to process (hard cap: {ORIENTATION_CANDIDATE_CAP})",
    )
    parser.add_argument("--meeting-id", help="Process specific meeting")
    parser.add_argument("--force", action="store_true", help="Regenerate existing orientations")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    import psycopg2

    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    try:
        if args.dry_run:
            with conn.cursor() as cur:
                meetings = _select_candidate_meetings(
                    cur,
                    city_fips=RICHMOND_FIPS,
                    force=args.force,
                    meeting_id=args.meeting_id,
                    limit=args.limit,
                )
                logger.info(f"Found {len(meetings)} meetings to generate orientations for")
                for mid, meeting_date, meeting_type, _agenda_url in meetings:
                    items = _fetch_items(cur, mid)
                    context = _build_orientation_context(items)
                    print(f"\n--- {meeting_date} ({meeting_type}) ---")
                    print(f"  {len(items)} source items")
                    print(context[:800])
                    if len(context) > 800:
                        print("...")
        else:
            generate_previews(
                conn,
                force=args.force,
                meeting_id=args.meeting_id,
                limit=args.limit,
                delay=args.delay,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
