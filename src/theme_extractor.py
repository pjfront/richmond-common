"""
S21 Phase B — Comment Theme Extraction

Clusters public comment speakers by substantive topic and generates
narrative summaries per theme. Themes are topics ("Privacy & Data
Retention"), never positions ("Opposition").

Workflow:
  1. Find agenda items with 3+ public comments
  2. Send comments to Claude API for theme clustering
  3. Upsert comment_themes, write assignments + narratives

Usage:
  python theme_extractor.py extract                      # All eligible items
  python theme_extractor.py extract --item-id UUID       # Single item
  python theme_extractor.py extract --meeting-date DATE  # Single meeting
  python theme_extractor.py extract --dry-run            # Preview only
  python theme_extractor.py extract --limit 5            # Cap items
  python theme_extractor.py status                       # Coverage report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from db import get_connection, RICHMOND_FIPS  # noqa: E402
from topic_tagger import get_topic_label_seeds  # noqa: E402

# -- Constants ------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8000
MIN_COMMENTS = 3  # Minimum comments to warrant theme extraction

PROMPT_PATH = Path(__file__).parent / "prompts" / "theme_extraction_system.txt"
RESULTS_DIR = Path(__file__).parent.parent / "data" / "theme_extraction"

SOURCE_LLM = "llm"


def _ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(label: str) -> str:
    """Convert a theme label to a URL-safe slug."""
    s = label.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:100]


# -- DB helpers -----------------------------------------------


def get_items_needing_themes(
    city_fips: str = RICHMOND_FIPS,
    *,
    meeting_date: str | None = None,
    item_id: str | None = None,
    include_already_extracted: bool = False,
    include_stale: bool = False,
) -> list[dict[str, Any]]:
    """Find agenda items with enough comments for theme extraction.

    Modes (evaluated in order):
    - include_already_extracted: return ALL items with enough comments
    - include_stale: return items without themes PLUS items with themes
      but unassigned comments (themes were extracted before new comments arrived)
    - default: return only items without themes
    """
    conn = get_connection()
    conditions = ["pc.city_fips = %s", "pc.summary IS NOT NULL"]
    params: list[Any] = [city_fips]

    if item_id:
        conditions.append("ai.id = %s::uuid")
        params.append(item_id)

    if meeting_date:
        conditions.append("m.meeting_date = %s")
        params.append(meeting_date)

    if not include_already_extracted and not include_stale:
        conditions.append("""
            NOT EXISTS (
                SELECT 1 FROM item_theme_narratives itn
                WHERE itn.agenda_item_id = ai.id
            )
        """)

    where = " AND ".join(conditions)

    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT ai.id, ai.item_number, LEFT(ai.title, 120) as title,
                       m.meeting_date, COUNT(pc.id) as comment_count
                FROM public_comments pc
                JOIN agenda_items ai ON pc.agenda_item_id = ai.id
                JOIN meetings m ON pc.meeting_id = m.id
                WHERE {where}
                GROUP BY ai.id, ai.item_number, ai.title, m.meeting_date
                HAVING COUNT(pc.id) >= %s
                ORDER BY m.meeting_date, ai.item_number""",
            params + [MIN_COMMENTS],
        )
        rows = cur.fetchall()

    # When include_stale, filter to: no themes yet OR has unassigned comments
    if include_stale and not include_already_extracted:
        item_ids = [str(r[0]) for r in rows]
        stale_ids = _find_stale_item_ids(conn, item_ids) if item_ids else set()
        themed_ids = _find_themed_item_ids(conn, item_ids) if item_ids else set()
        rows = [r for r in rows if str(r[0]) not in themed_ids
                or str(r[0]) in stale_ids]

    conn.close()  # noqa: must stay after stale filtering

    return [
        {
            "item_id": str(r[0]),
            "item_number": r[1],
            "title": r[2],
            "meeting_date": str(r[3]),
            "comment_count": r[4],
        }
        for r in rows
    ]


def _find_themed_item_ids(conn: Any, item_ids: list[str]) -> set[str]:
    """Batch check which items already have theme narratives."""
    if not item_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT agenda_item_id::text FROM item_theme_narratives WHERE agenda_item_id = ANY(%s::uuid[])",
            (item_ids,),
        )
        return {str(r[0]) for r in cur.fetchall()}


def _find_stale_item_ids(conn: Any, item_ids: list[str]) -> set[str]:
    """Find items with themes but unassigned comments (= stale extraction).

    An item is stale when it has narratives but also has comments with
    summaries that lack a comment_theme_assignment row.
    """
    if not item_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT pc.agenda_item_id::text
               FROM public_comments pc
               LEFT JOIN comment_theme_assignments cta ON cta.comment_id = pc.id
               WHERE pc.agenda_item_id = ANY(%s::uuid[])
                 AND pc.summary IS NOT NULL
                 AND cta.comment_id IS NULL
                 AND EXISTS (
                     SELECT 1 FROM item_theme_narratives itn
                     WHERE itn.agenda_item_id = pc.agenda_item_id
                 )""",
            (item_ids,),
        )
        return {str(r[0]) for r in cur.fetchall()}


def get_comments_for_item(item_id: str) -> list[dict[str, Any]]:
    """Get all public comments for an agenda item."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, speaker_name, method, summary
               FROM public_comments
               WHERE agenda_item_id = %s::uuid AND summary IS NOT NULL
               ORDER BY created_at""",
            (item_id,),
        )
        rows = cur.fetchall()
    conn.close()

    return [
        {
            "comment_id": str(r[0]),
            "speaker_name": r[1],
            "method": r[2],
            "summary": r[3],
        }
        for r in rows
    ]


def get_existing_theme_seeds(city_fips: str = RICHMOND_FIPS) -> list[str]:
    """Get existing comment_themes labels + topic labels for seeding."""
    conn = get_connection()
    seeds: set[str] = set()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT label FROM comment_themes WHERE city_fips = %s AND status = 'active'",
            (city_fips,),
        )
        for row in cur.fetchall():
            seeds.add(row[0])

    # Also pull topic labels for cross-pollination
    topic_seeds = get_topic_label_seeds(conn, city_fips)
    seeds.update(topic_seeds)

    conn.close()
    return sorted(seeds)


def _format_seed_prompt(seeds: list[str]) -> str:
    """Format seed themes as a prompt addendum."""
    if not seeds:
        return ""
    seed_list = ", ".join(seeds)
    return (
        f"\n\nExisting theme labels (reuse when the topic matches, "
        f"create a new label only when none of these fit): {seed_list}"
    )


# -- Extraction -----------------------------------------------


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def extract_themes_for_item(
    item: dict[str, Any],
    comments: list[dict[str, Any]],
    seeds: list[str],
) -> dict[str, Any] | None:
    """Send comments to Claude API and extract themes."""
    if anthropic is None:
        print("ERROR: anthropic package required. Run: pip install anthropic")
        return None

    system_prompt = _load_system_prompt() + _format_seed_prompt(seeds)

    comment_text = "\n".join(
        f"- {c['speaker_name']} ({c['method']}): {c['summary']}"
        for c in comments
    )

    user_prompt = (
        f"AGENDA ITEM: {item['item_number']} — {item['title']}\n"
        f"MEETING DATE: {item['meeting_date']}\n"
        f"TOTAL SPEAKERS: {len(comments)}\n\n"
        f"PUBLIC COMMENTS:\n{comment_text}\n\n"
        f"Identify the recurring themes in these comments. Return JSON."
    )

    est_tokens = len(user_prompt) // 4
    print(f"  Sending to Claude API (~{est_tokens:,} input tokens)...")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = response.content[0].text
    cost = (
        response.usage.input_tokens * 0.003 / 1000
        + response.usage.output_tokens * 0.015 / 1000
    )
    print(
        f"  API: {response.usage.input_tokens:,} in / "
        f"{response.usage.output_tokens:,} out (${cost:.3f})"
    )

    # Parse JSON — strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  ERROR: Failed to parse JSON: {e}")
        print(f"  Raw response: {text[:500]}")
        return None

    themes = result.get("themes", [])
    assignments = result.get("assignments", [])
    narratives = result.get("narratives", [])
    print(
        f"  Extracted {len(themes)} themes, "
        f"{len(assignments)} assignments, "
        f"{len(narratives)} narratives"
    )

    return result


def import_themes(
    result: dict[str, Any],
    item_id: str,
    comments: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    city_fips: str = RICHMOND_FIPS,
) -> dict[str, int]:
    """Write theme data to the database.

    Returns stats dict with counts.
    """
    themes = result.get("themes", [])
    assignments = result.get("assignments", [])
    narratives = result.get("narratives", [])
    now = datetime.now(timezone.utc)

    stats = {
        "themes_created": 0,
        "themes_reused": 0,
        "assignments": 0,
        "narratives": 0,
        "unmatched_speakers": 0,
    }

    if not themes:
        return stats

    # Build comment lookup by speaker name
    comment_by_speaker: dict[str, str] = {}
    for c in comments:
        comment_by_speaker[c["speaker_name"]] = c["comment_id"]

    if dry_run:
        print("  [DRY RUN]")
        for t in themes:
            print(f"    Theme: {t['label']} ({t['slug']})")
            if t.get("description"):
                print(f"      {t['description'][:80]}")
        for n in narratives:
            print(f"    Narrative ({n['theme_slug']}): {n.get('narrative', '')[:100]}...")
        matching = sum(1 for a in assignments if a["speaker_name"] in comment_by_speaker)
        print(f"    Assignments: {matching} matched, {len(assignments) - matching} unmatched")
        stats["themes_created"] = len(themes)
        stats["assignments"] = matching
        stats["narratives"] = len(narratives)
        return stats

    conn = get_connection()

    # 0. Clean up old narratives and assignments for this item
    #    (re-extraction replaces everything — old slugs would leave orphans)
    with conn.cursor() as cur:
        cur.execute(
            """DELETE FROM comment_theme_assignments
               WHERE comment_id IN (
                   SELECT id FROM public_comments WHERE agenda_item_id = %s::uuid
               )""",
            (item_id,),
        )
        old_assignments = cur.rowcount
        cur.execute(
            "DELETE FROM item_theme_narratives WHERE agenda_item_id = %s::uuid",
            (item_id,),
        )
        old_narratives = cur.rowcount
        if old_assignments > 0 or old_narratives > 0:
            print(f"  Cleared {old_assignments} old assignments, {old_narratives} old narratives")
        conn.commit()

    # 1. Upsert themes
    theme_ids: dict[str, str] = {}  # slug -> uuid
    for t in themes:
        slug = _slugify(t.get("slug") or t["label"])
        label = t["label"]
        description = t.get("description")

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO comment_themes (city_fips, slug, label, description, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (city_fips, slug) DO UPDATE SET updated_at = EXCLUDED.updated_at
                   RETURNING id""",
                (city_fips, slug, label, description, now, now),
            )
            theme_id = str(cur.fetchone()[0])
            theme_ids[slug] = theme_id

            # Check if this was a new insert or reuse
            if cur.statusmessage and "INSERT" in cur.statusmessage:
                stats["themes_created"] += 1
            else:
                stats["themes_reused"] += 1

    # 2. Write assignments
    for a in assignments:
        speaker_name = a["speaker_name"]
        theme_slug = _slugify(a.get("theme_slug", ""))
        confidence = a.get("confidence", 0.9)

        comment_id = comment_by_speaker.get(speaker_name)
        if not comment_id:
            stats["unmatched_speakers"] += 1
            continue

        theme_id = theme_ids.get(theme_slug)
        if not theme_id:
            continue

        with conn.cursor() as cur:
            try:
                cur.execute(
                    """INSERT INTO comment_theme_assignments
                       (comment_id, theme_id, confidence, source, created_at)
                       VALUES (%s::uuid, %s::uuid, %s, %s, %s)
                       ON CONFLICT (comment_id, theme_id) DO NOTHING""",
                    (comment_id, theme_id, confidence, SOURCE_LLM, now),
                )
                if cur.rowcount > 0:
                    stats["assignments"] += 1
            except Exception as e:
                print(f"    ERROR assigning {speaker_name} -> {theme_slug}: {e}")
                conn.rollback()

    # 3. Write narratives
    for n in narratives:
        theme_slug = _slugify(n.get("theme_slug", ""))
        narrative = n.get("narrative", "")
        comment_count = n.get("comment_count", 0)

        theme_id = theme_ids.get(theme_slug)
        if not theme_id or not narrative:
            continue

        with conn.cursor() as cur:
            try:
                cur.execute(
                    """INSERT INTO item_theme_narratives
                       (agenda_item_id, theme_id, narrative, comment_count,
                        confidence, model, generated_at)
                       VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s)
                       ON CONFLICT (agenda_item_id, theme_id)
                       DO UPDATE SET narrative = EXCLUDED.narrative,
                                     comment_count = EXCLUDED.comment_count,
                                     generated_at = EXCLUDED.generated_at""",
                    (item_id, theme_id, narrative, comment_count, 0.9, MODEL, now),
                )
                if cur.rowcount > 0:
                    stats["narratives"] += 1
            except Exception as e:
                print(f"    ERROR writing narrative for {theme_slug}: {e}")
                conn.rollback()

    conn.commit()
    conn.close()

    print(
        f"  Wrote: {stats['themes_created']} new themes "
        f"({stats['themes_reused']} reused), "
        f"{stats['assignments']} assignments, "
        f"{stats['narratives']} narratives"
    )
    if stats["unmatched_speakers"]:
        print(f"  Warning: {stats['unmatched_speakers']} speaker names didn't match DB records")

    return stats


# -- Commands -------------------------------------------------


def cmd_extract(
    *,
    item_id: str | None = None,
    meeting_date: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    force: bool = False,
    include_stale: bool = False,
) -> None:
    """Extract themes for eligible agenda items."""
    items = get_items_needing_themes(
        item_id=item_id,
        meeting_date=meeting_date,
        include_already_extracted=force,
        include_stale=include_stale,
    )

    if not items:
        if item_id:
            print(f"Item {item_id} not found, has <{MIN_COMMENTS} comments, or already extracted (use --force)")
        elif meeting_date:
            print(f"No items with {MIN_COMMENTS}+ comments for {meeting_date}, or already extracted")
        else:
            print("All eligible items already have themes extracted.")
        return

    if limit:
        items = items[:limit]

    _ensure_dirs()
    seeds = get_existing_theme_seeds()

    total_themes = 0
    total_assignments = 0

    print(f"Extracting themes for {len(items)} items ({sum(i['comment_count'] for i in items)} total comments)...")
    if dry_run:
        print("[DRY RUN — no DB writes]\n")
    else:
        print()

    for item in items:
        print(f"\n-- {item['meeting_date']} {item['item_number']}: {item['title'][:60]} ({item['comment_count']} comments) --")

        comments = get_comments_for_item(item["item_id"])
        if len(comments) < MIN_COMMENTS:
            print(f"  Skipped: only {len(comments)} comments with summaries")
            continue

        result = extract_themes_for_item(item, comments, seeds)
        if not result:
            continue

        # Save raw result for audit
        result_path = RESULTS_DIR / f"{item['meeting_date']}_{item['item_number']}_themes.json"
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        stats = import_themes(result, item["item_id"], comments, dry_run=dry_run)
        total_themes += stats["themes_created"]
        total_assignments += stats["assignments"]

        # Refresh seeds for subsequent items (new themes become available)
        if not dry_run and stats["themes_created"] > 0:
            seeds = get_existing_theme_seeds()

    print(f"\n{'=' * 50}")
    print(
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"Complete: {total_themes} new themes, {total_assignments} assignments "
        f"across {len(items)} items"
    )


def cmd_status(city_fips: str = RICHMOND_FIPS) -> None:
    """Show theme extraction coverage."""
    conn = get_connection()
    with conn.cursor() as cur:
        # Items eligible for themes
        cur.execute(
            """SELECT COUNT(DISTINCT ai.id)
               FROM public_comments pc
               JOIN agenda_items ai ON pc.agenda_item_id = ai.id
               WHERE pc.city_fips = %s AND pc.summary IS NOT NULL
               GROUP BY ai.id
               HAVING COUNT(pc.id) >= %s""",
            (city_fips, MIN_COMMENTS),
        )
        eligible = cur.rowcount

        # Items with themes already
        cur.execute(
            "SELECT COUNT(DISTINCT agenda_item_id) FROM item_theme_narratives"
        )
        themed = cur.fetchone()[0]

        # Total themes
        cur.execute(
            "SELECT COUNT(*) FROM comment_themes WHERE city_fips = %s AND status = 'active'",
            (city_fips,),
        )
        total_themes = cur.fetchone()[0]

        # Total assignments
        cur.execute("SELECT COUNT(*) FROM comment_theme_assignments")
        total_assignments = cur.fetchone()[0]

        # Total narratives
        cur.execute("SELECT COUNT(*) FROM item_theme_narratives")
        total_narratives = cur.fetchone()[0]

        # Needs extraction
        needs = get_items_needing_themes(city_fips=city_fips)

        # Stale items (have themes but unassigned comments)
        stale_needs = get_items_needing_themes(city_fips=city_fips, include_stale=True)

    conn.close()

    stale_count = len(stale_needs) - len(needs)

    print("Theme Extraction Status")
    print("=" * 40)
    print(f"  Eligible items (3+ comments): {eligible}")
    print(f"  Items with themes:            {themed}")
    print(f"  Items remaining:              {len(needs)}")
    print(f"  Items stale (new comments):   {stale_count}")
    print(f"  Theme catalog size:           {total_themes}")
    print(f"  Total assignments:            {total_assignments}")
    print(f"  Total narratives:             {total_narratives}")

    if needs:
        print(f"\n  Next {min(5, len(needs))} to extract:")
        for item in needs[:5]:
            print(f"    {item['meeting_date']} {item['item_number']}: {item['title'][:50]} ({item['comment_count']} comments)")

    if stale_count > 0:
        stale_only = [i for i in stale_needs if i not in needs]
        print(f"\n  Stale items (use --include-stale to re-extract):")
        for item in stale_only[:5]:
            print(f"    {item['meeting_date']} {item['item_number']}: {item['title'][:50]} ({item['comment_count']} comments)")


# -- CLI ------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Comment theme extraction — cluster speakers by topic"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract themes via LLM")
    extract_parser.add_argument("--item-id", help="Single agenda item UUID")
    extract_parser.add_argument("--meeting-date", help="Single meeting date (YYYY-MM-DD)")
    extract_parser.add_argument("--dry-run", action="store_true", help="Preview without DB writes")
    extract_parser.add_argument("--limit", type=int, help="Limit number of items")
    extract_parser.add_argument("--force", action="store_true", help="Re-extract even if done")
    extract_parser.add_argument("--include-stale", action="store_true",
                                help="Also re-extract items with unassigned comments (stale themes)")

    subparsers.add_parser("status", help="Show extraction coverage")

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(
            item_id=args.item_id,
            meeting_date=args.meeting_date,
            dry_run=args.dry_run,
            limit=args.limit,
            force=args.force,
            include_stale=args.include_stale,
        )
    elif args.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
