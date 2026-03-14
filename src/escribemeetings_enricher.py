"""
Richmond Common -- eSCRIBE Attachment Enrichment

Enriches extracted agenda/meeting JSON with text from eSCRIBE full agenda
packet attachments (staff reports, contracts, bid matrices). This feeds
richer entity text into the conflict scanner for better donor matching.

The enrichment is purely additive: if no eSCRIBE data is available, the
pipeline works identically to before. When eSCRIBE data IS available,
each matched agenda item gets its description field augmented with
attachment text (staff reports, contracts, etc.), giving the conflict
scanner's regex-based entity extraction much more to work with.

Usage:
    # Preview matches without modifying anything
    python escribemeetings_enricher.py <meeting.json> <escribemeetings_data.json> --dry-run

    # Enrich and save augmented meeting JSON
    python escribemeetings_enricher.py <meeting.json> <escribemeetings_data.json> --output enriched.json

    # Used programmatically by comment_generator.py
    from escribemeetings_enricher import enrich_meeting_data
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional


# ── Platform Profile (for multi-city scaling) ────────────────
# eSCRIBE (OnBoard/Diligent) is used by hundreds of cities.
# These URL patterns are standard across deployments. To onboard
# a new eSCRIBE city, change only the base_url.

ESCRIBEMEETINGS_PLATFORM_PROFILE = {
    "platform_name": "eSCRIBE (OnBoard/Diligent)",
    "base_url_pattern": "https://pub-{city}.escribemeetings.com/",
    "known_deployments": [
        # Add cities as discovered
        {"city": "richmond", "base_url": "https://pub-richmond.escribemeetings.com/"},
    ],
    "api_endpoints": {
        "calendar": "MeetingsCalendarView.aspx/GetCalendarMeetings",
        "meeting_page": "Meeting.aspx?Id={guid}&Agenda=Agenda&lang=English",
        "document": "filestream.ashx?DocumentId={id}",
    },
    "api_headers": {
        "calendar_post": {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    },
    "html_selectors": {
        "agenda_item_container": ".AgendaItemContainer",
        "item_number": ".AgendaItemCounter",
        "item_title": ".AgendaItemTitle a",
        "item_description": ".AgendaItemDescription",
        "item_body": ".RichText",
        "attachment_link": ".AgendaItemAttachment a[href*=filestream.ashx]",
    },
    "notes": [
        "Individual meeting pages return parseable HTML with requests + BeautifulSoup",
        "Calendar listing page is JS-rendered (use AJAX API instead)",
        "Must establish session first by GET-ing the calendar page for cookies",
        "Parent items nest child items in HTML -- dedup attachments by assigning to deepest item",
    ],
}


# ── Title Matching ───────────────────────────────────────────

# Action verb prefixes that appear in Claude extraction titles
# but not in eSCRIBE titles (or vice versa)
_ACTION_PREFIXES = [
    r"approve\b", r"adopt\b", r"receive\b", r"direct\b",
    r"authorize\b", r"accept\b", r"ratify\b", r"confirm\b",
    r"consider\b", r"discuss\b", r"review\b",
    r"approve a\b", r"adopt a\b", r"adopt the\b",
    r"approve the\b", r"receive a\b", r"receive the\b",
    r"direct the city manager to\b",
    r"direct the city manager\b",
    r"direct staff to\b",
]

# Compiled pattern to strip action verb prefixes
_ACTION_PREFIX_RE = re.compile(
    r"^\s*(?:" + "|".join(_ACTION_PREFIXES) + r")\s*",
    re.IGNORECASE,
)


def normalize_title(title: str) -> str:
    """Normalize a title for fuzzy comparison.

    Lowercases, strips action verb prefixes (APPROVE, ADOPT, etc.),
    removes punctuation, and collapses whitespace.
    """
    text = title.lower().strip()
    # Strip action verb prefixes
    text = _ACTION_PREFIX_RE.sub("", text)
    # Remove punctuation
    text = re.sub(r'[,.\'"!?;:()\[\]{}\-/]', " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def title_similarity(title_a: str, title_b: str) -> float:
    """Compute similarity between two agenda item titles.

    Uses word-overlap Jaccard coefficient on normalized titles,
    with a bonus for substring containment.

    Returns:
        Float 0.0-1.0. Higher = more similar.
    """
    norm_a = normalize_title(title_a)
    norm_b = normalize_title(title_b)

    if not norm_a or not norm_b:
        return 0.0

    # Exact match after normalization
    if norm_a == norm_b:
        return 1.0

    # Substring containment — one title fully inside the other
    if norm_a in norm_b or norm_b in norm_a:
        return 0.9

    # Jaccard word overlap
    words_a = set(norm_a.split())
    words_b = set(norm_b.split())

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b
    jaccard = len(intersection) / len(union)

    return jaccard


# ── Attachment Text Loading ──────────────────────────────────

def load_attachment_text(
    escribemeetings_data: dict,
    max_chars_per_item: int = 10_000,
) -> dict[str, str]:
    """Load and concatenate attachment text for each eSCRIBE item.

    Reads the .txt files that the eSCRIBE scraper created alongside
    downloaded PDFs. Concatenates all attachment texts per agenda item,
    truncated to max_chars_per_item.

    Args:
        escribemeetings_data: Parsed meeting_data.json from eSCRIBE scraper
        max_chars_per_item: Maximum chars of attachment text per item

    Returns:
        Dict mapping eSCRIBE item_number -> concatenated attachment text.
        Items with no readable attachment text are omitted.
    """
    item_texts: dict[str, str] = {}

    for item in escribemeetings_data.get("items", []):
        item_num = item.get("item_number", "")
        if not item_num:
            continue

        texts = []
        for att in item.get("attachments", []):
            text_path = att.get("text_path")
            if not text_path:
                continue

            path = Path(text_path)
            if not path.exists():
                continue

            try:
                text = path.read_text(encoding="utf-8")
                if text and len(text.strip()) > 50:  # skip trivially short extracts
                    texts.append(text.strip())
            except (OSError, UnicodeDecodeError):
                continue

        if texts:
            combined = "\n\n---\n\n".join(texts)
            if len(combined) > max_chars_per_item:
                combined = combined[:max_chars_per_item]
            item_texts[item_num] = combined

    return item_texts


# ── Item Matching ────────────────────────────────────────────

def match_items(
    agenda_items: list[dict],
    escribemeetings_items: list[dict],
    threshold: float = 0.4,
) -> dict[str, str]:
    """Match extracted agenda items to eSCRIBE items by title similarity.

    Uses greedy best-match: each eSCRIBE item matched to at most one
    agenda item. This prevents one eSCRIBE item from being claimed by
    multiple agenda items.

    Args:
        agenda_items: Items from Claude-extracted meeting JSON
            (item_number like "O.3.a", "C.1", "P.1")
        escribemeetings_items: Items from eSCRIBE meeting_data.json
            (item_number like "V.1", "V.1.a", "A")
        threshold: Minimum title_similarity score to consider a match

    Returns:
        Dict mapping agenda item_number -> eSCRIBE item_number.
        Only includes items that matched above threshold.
    """
    # Build all candidate pairs with scores
    candidates = []
    for agenda_item in agenda_items:
        agenda_num = agenda_item.get("item_number", "")
        agenda_title = agenda_item.get("title", "")
        if not agenda_num or not agenda_title:
            continue

        for escribe_item in escribemeetings_items:
            escribe_num = escribe_item.get("item_number", "")
            escribe_title = escribe_item.get("title", "")
            if not escribe_num or not escribe_title:
                continue

            score = title_similarity(agenda_title, escribe_title)
            if score >= threshold:
                candidates.append((score, agenda_num, escribe_num))

    # Sort by score descending — best matches first
    candidates.sort(key=lambda x: x[0], reverse=True)

    # Greedy assignment: each item matched at most once
    matched_agenda: set[str] = set()
    matched_escribe: set[str] = set()
    result: dict[str, str] = {}

    for score, agenda_num, escribe_num in candidates:
        if agenda_num in matched_agenda or escribe_num in matched_escribe:
            continue
        result[agenda_num] = escribe_num
        matched_agenda.add(agenda_num)
        matched_escribe.add(escribe_num)

    return result


# ── Meeting Data Enrichment ──────────────────────────────────

def _collect_all_items(meeting_data: dict) -> list[dict]:
    """Collect all agenda items from meeting data across all sections."""
    items = []
    consent = meeting_data.get("consent_calendar", {})
    items.extend(consent.get("items", []))
    items.extend(meeting_data.get("action_items", []))
    items.extend(meeting_data.get("housing_authority_items", []))
    return items


def enrich_meeting_data(
    meeting_data: dict,
    escribemeetings_path: str | Path,
    max_chars_per_item: int = 10_000,
    match_threshold: float = 0.4,
) -> tuple[dict, list[str]]:
    """Enrich meeting_data dict with eSCRIBE attachment text.

    Loads eSCRIBE data, matches items by title similarity, and appends
    attachment text to matched items' description fields.

    The meeting_data dict is mutated in place (description fields extended).

    Args:
        meeting_data: The Claude-extracted meeting JSON (will be mutated)
        escribemeetings_path: Path to eSCRIBE meeting_data.json
        max_chars_per_item: Maximum attachment text chars per item
        match_threshold: Minimum title similarity for matching

    Returns:
        Tuple of (meeting_data, enriched_item_numbers).
        meeting_data is the same dict, mutated with enriched descriptions.
        enriched_item_numbers lists agenda item numbers that got attachment text.
    """
    escribemeetings_path = Path(escribemeetings_path)
    if not escribemeetings_path.exists():
        print(f"  [ENRICHER] eSCRIBE data not found: {escribemeetings_path}")
        return meeting_data, []

    with open(escribemeetings_path, encoding="utf-8") as f:
        escribe_data = json.load(f)

    # Load attachment text per eSCRIBE item
    attachment_texts = load_attachment_text(escribe_data, max_chars_per_item)
    if not attachment_texts:
        print("  [ENRICHER] No attachment text found in eSCRIBE data")
        return meeting_data, []

    print(f"  [ENRICHER] Loaded attachment text for {len(attachment_texts)} eSCRIBE items")

    # Collect all agenda items from meeting data
    all_items = _collect_all_items(meeting_data)
    escribe_items = escribe_data.get("items", [])

    # Match items by title
    item_map = match_items(all_items, escribe_items, match_threshold)
    print(f"  [ENRICHER] Matched {len(item_map)} agenda items to eSCRIBE items")

    # Enrich matched items with attachment text
    enriched_items: list[str] = []

    # Items whose attachments are previous meeting transcripts (not
    # staff reports) — enriching these loads 20-30KB of names from
    # prior meetings, causing massive false positive matches in the
    # conflict scanner.
    _SKIP_ENRICHMENT_PATTERNS = [
        "minutes", "draft minutes", "approve minutes",
        "approve the minutes", "city council minutes",
    ]

    for item in all_items:
        item_num = item.get("item_number", "")
        escribe_num = item_map.get(item_num)
        if not escribe_num:
            continue

        att_text = attachment_texts.get(escribe_num)
        if not att_text:
            continue

        # Skip enrichment for minutes-approval items — their attachments
        # are previous meeting transcripts, not staff reports
        item_title_lower = item.get("title", "").lower()
        if any(pat in item_title_lower for pat in _SKIP_ENRICHMENT_PATTERNS):
            print(f"  [ENRICHER] Skipping minutes item {item_num}: {item.get('title', '')[:60]}")
            continue

        # Append attachment text to description
        existing_desc = item.get("description", "")
        item["description"] = (
            f"{existing_desc}\n\n"
            f"[eSCRIBE Staff Report/Attachment Text]\n"
            f"{att_text}"
        )
        enriched_items.append(item_num)

    if enriched_items:
        print(f"  [ENRICHER] Enriched {len(enriched_items)} items with attachment text: "
              f"{', '.join(enriched_items)}")
    else:
        print("  [ENRICHER] No items enriched (matched items had no attachment text)")

    return meeting_data, enriched_items


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Richmond Common -- eSCRIBE Attachment Enrichment"
    )
    parser.add_argument("meeting_json", help="Path to extracted meeting JSON file")
    parser.add_argument("escribemeetings_json", help="Path to eSCRIBE meeting_data.json")
    parser.add_argument("--output", help="Save enriched meeting JSON to file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show matches without modifying data")
    parser.add_argument("--max-chars", type=int, default=10_000,
                        help="Max attachment text chars per item (default: 10000)")
    parser.add_argument("--threshold", type=float, default=0.4,
                        help="Min title similarity for matching (default: 0.4)")

    args = parser.parse_args()

    # Load meeting data
    with open(args.meeting_json, encoding="utf-8") as f:
        meeting_data = json.load(f)

    # Load eSCRIBE data
    with open(args.escribemeetings_json, encoding="utf-8") as f:
        escribe_data = json.load(f)

    # Collect items for matching preview
    all_items = _collect_all_items(meeting_data)
    escribe_items = escribe_data.get("items", [])
    attachment_texts = load_attachment_text(escribe_data, args.max_chars)

    print(f"Agenda items: {len(all_items)}")
    print(f"eSCRIBE items: {len(escribe_items)}")
    print(f"eSCRIBE items with attachment text: {len(attachment_texts)}")
    print()

    # Show matches
    item_map = match_items(all_items, escribe_items, args.threshold)
    print(f"Matched {len(item_map)} items (threshold={args.threshold}):")
    print("-" * 70)

    for item in all_items:
        item_num = item.get("item_number", "")
        item_title = item.get("title", "")
        escribe_num = item_map.get(item_num)

        if escribe_num:
            # Find the eSCRIBE title for display
            escribe_title = ""
            for ei in escribe_items:
                if ei.get("item_number") == escribe_num:
                    escribe_title = ei.get("title", "")
                    break

            score = title_similarity(item_title, escribe_title)
            has_text = escribe_num in attachment_texts
            text_len = len(attachment_texts.get(escribe_num, ""))

            print(f"  {item_num} -> {escribe_num}  (score={score:.2f})")
            print(f"    Agenda:  {item_title[:80]}")
            print(f"    eSCRIBE: {escribe_title[:80]}")
            if has_text:
                print(f"    Attachment text: {text_len:,} chars")
            else:
                print(f"    Attachment text: none")
            print()
        else:
            print(f"  {item_num} -> NO MATCH")
            print(f"    Agenda: {item_title[:80]}")
            print()

    # Show unmatched eSCRIBE items
    matched_escribe = set(item_map.values())
    unmatched_escribe = [
        ei for ei in escribe_items
        if ei.get("item_number") and ei["item_number"] not in matched_escribe
    ]
    if unmatched_escribe:
        print(f"\nUnmatched eSCRIBE items ({len(unmatched_escribe)}):")
        for ei in unmatched_escribe:
            print(f"  {ei.get('item_number', '?')}: {ei.get('title', '')[:80]}")

    if args.dry_run:
        print("\n[DRY RUN] No data modified.")
        return

    # Enrich and optionally save
    meeting_data_copy = json.loads(json.dumps(meeting_data))  # deep copy
    enriched_data, enriched_items = enrich_meeting_data(
        meeting_data_copy,
        args.escribemeetings_json,
        max_chars_per_item=args.max_chars,
        match_threshold=args.threshold,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, indent=2, ensure_ascii=False)
        print(f"\nEnriched meeting data saved to {args.output}")
    else:
        print(f"\nEnriched {len(enriched_items)} items. Use --output to save.")


if __name__ == "__main__":
    main()
