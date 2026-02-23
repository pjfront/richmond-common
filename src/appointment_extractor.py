# src/appointment_extractor.py
"""
Extract commission/board appointment actions from council meeting minutes.

Uses Claude API to identify appointment, reappointment, resignation, and
removal actions from already-extracted council meeting JSONs. These become
the authoritative (Tier 1) record of who sits on which commission.

Cost: ~$0.02 per meeting, ~$0.50 total for 21 meetings.

Usage:
    python appointment_extractor.py --meetings-dir src/data/extracted/   # All meetings
    python appointment_extractor.py --meeting src/data/extracted/FILE    # One meeting
    python appointment_extractor.py --output FILE                       # Save JSON
    python appointment_extractor.py --compare-website                   # Run staleness check
    python appointment_extractor.py --load                              # Load to DB
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import anthropic

logger = logging.getLogger(__name__)

CITY_FIPS = "0660620"

APPOINTMENT_SCHEMA = [
    {
        "person_name": "Full name of person being appointed/reappointed/resigned/removed",
        "commission_name": "Name of the commission or board",
        "action": "appoint | reappoint | resign | remove | confirm",
        "appointed_by": "Name of appointing official (e.g., 'Mayor Martinez', 'Councilmember Brown')",
        "term_end": "YYYY-MM-DD or null if not mentioned",
        "item_number": "Agenda item number where this action appears",
        "confidence": "0.0-1.0 confidence in extraction accuracy",
    }
]

SYSTEM_PROMPT = """You are a precise data extraction system for the Richmond Transparency Project.
Your job is to extract commission and board APPOINTMENT ACTIONS from city council meeting data.

Look for these action types:
- APPOINT: New appointment to a commission/board
- REAPPOINT: Renewal of existing appointment
- RESIGN: Resignation from a commission/board
- REMOVE: Removal from a commission/board
- CONFIRM: Council confirmation of an appointment

Only extract actions related to commissions, boards, and committees.
Do NOT extract employment actions (hiring, promotions) or contract approvals.
Do NOT extract council member elections or swearing-in ceremonies.

Return valid JSON array. If no appointment actions are found, return [].
"""


def normalize_commission_name(name: str) -> str:
    """Normalize a commission name for matching."""
    lower = " ".join(name.lower().strip().split())
    # Strip common prefixes
    for prefix in ["city of richmond ", "richmond ", "city of "]:
        if lower.startswith(prefix):
            lower = lower[len(prefix):]
    return lower


def _normalize_name(name: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return " ".join(name.lower().split())


def parse_claude_response(text: str) -> list[dict]:
    """Parse Claude's JSON response, handling markdown fences."""
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines)
    try:
        data = json.loads(clean)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        logger.error("Failed to parse Claude response as JSON")
        return []


def build_appointment_record(
    raw: dict,
    *,
    meeting_date: str,
    city_fips: str = CITY_FIPS,
) -> dict:
    """Build a full appointment record from Claude extraction output."""
    return {
        "city_fips": city_fips,
        "name": raw.get("person_name", ""),
        "normalized_name": _normalize_name(raw.get("person_name", "")),
        "commission_name": raw.get("commission_name", ""),
        "action": raw.get("action", ""),
        "appointed_by": raw.get("appointed_by"),
        "term_end": raw.get("term_end"),
        "item_number": raw.get("item_number"),
        "confidence": raw.get("confidence", 0.0),
        "meeting_date": meeting_date,
        "source": "council_minutes",
    }


def extract_appointments_from_meeting(meeting_data: dict) -> list[dict]:
    """Extract appointment actions from one meeting's JSON.

    Sends the meeting data to Claude API with a focused prompt.
    Returns list of appointment records.
    """
    meeting_date = meeting_data.get("meeting_date", "unknown")

    # Build a text representation of all agenda items
    items_text = []
    for section in ["consent_calendar", "action_items", "housing_authority_items"]:
        section_data = meeting_data.get(section, {})
        if isinstance(section_data, dict):
            section_items = section_data.get("items", [])
        elif isinstance(section_data, list):
            section_items = section_data
        else:
            continue

        for item in section_items:
            num = item.get("item_number", "?")
            title = item.get("title", "")
            desc = item.get("description", "")
            items_text.append(f"[{num}] {title}\n{desc}")

    if not items_text:
        return []

    prompt = f"""Extract all commission/board APPOINTMENT ACTIONS from the following council meeting agenda items.
Meeting date: {meeting_date}

Return a JSON array matching this schema:
{json.dumps(APPOINTMENT_SCHEMA, indent=2)}

If no appointment actions are found, return an empty array [].

Agenda items:
---
{chr(10).join(items_text)}
---

Return ONLY valid JSON. No explanation."""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text
    cost = (message.usage.input_tokens * 3 + message.usage.output_tokens * 15) / 1_000_000
    logger.info(
        "  Meeting %s: %d input + %d output tokens (~$%.4f)",
        meeting_date, message.usage.input_tokens, message.usage.output_tokens, cost,
    )

    raw_appointments = parse_claude_response(response_text)
    return [
        build_appointment_record(a, meeting_date=meeting_date)
        for a in raw_appointments
    ]


def extract_from_directory(
    meetings_dir: Path, *, city_fips: str = CITY_FIPS
) -> list[dict]:
    """Extract appointments from all meeting JSONs in a directory."""
    all_appointments = []
    json_files = sorted(meetings_dir.glob("*.json"))
    logger.info("Processing %d meeting files...", len(json_files))

    for f in json_files:
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError:
            logger.warning("Skipping invalid JSON: %s", f.name)
            continue

        appointments = extract_appointments_from_meeting(data)
        all_appointments.extend(appointments)
        if appointments:
            logger.info("  %s: %d appointments found", f.name, len(appointments))

    logger.info("Total: %d appointments from %d meetings", len(all_appointments), len(json_files))
    return all_appointments


def compare_with_website(
    appointments: list[dict],
    website_members: dict[str, list[dict]],
) -> list[dict]:
    """Compare minutes-derived appointments against website roster.

    Returns list of staleness findings.
    """
    findings = []
    for appt in appointments:
        if appt["action"] not in ("appoint", "reappoint", "confirm"):
            continue

        commission = appt["commission_name"]
        norm_commission = normalize_commission_name(commission)

        # Find matching commission in website data
        website_roster = None
        for wc_name, wc_members in website_members.items():
            if normalize_commission_name(wc_name) == norm_commission:
                website_roster = wc_members
                break

        if website_roster is None:
            continue  # Commission not scraped

        # Check if this person is on the website roster
        website_names = {m["normalized_name"] for m in website_roster}
        if appt["normalized_name"] not in website_names:
            findings.append({
                "type": "member_not_on_website",
                "commission": commission,
                "member": appt["name"],
                "appointed_date": appt["meeting_date"],
                "action": appt["action"],
            })

    return findings


def load_to_db(appointments: list[dict], *, city_fips: str = CITY_FIPS) -> None:
    """Load extracted appointments to Supabase commission_members table."""
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            loaded = 0
            for appt in appointments:
                if appt["action"] in ("resign", "remove"):
                    # Mark member as no longer current
                    cur.execute(
                        """UPDATE commission_members
                           SET is_current = FALSE, updated_at = NOW()
                           WHERE city_fips = %s
                             AND normalized_name = %s
                             AND commission_id IN (
                                 SELECT id FROM commissions
                                 WHERE city_fips = %s AND LOWER(name) = LOWER(%s)
                             )""",
                        (city_fips, appt["normalized_name"], city_fips, appt["commission_name"]),
                    )
                else:
                    # Find the commission
                    cur.execute(
                        "SELECT id FROM commissions WHERE city_fips = %s AND LOWER(name) = LOWER(%s)",
                        (city_fips, appt["commission_name"]),
                    )
                    row = cur.fetchone()
                    if not row:
                        logger.warning("Commission '%s' not in DB", appt["commission_name"])
                        continue
                    commission_id = row[0]

                    cur.execute(
                        """INSERT INTO commission_members
                           (city_fips, commission_id, name, normalized_name, role,
                            appointed_by, term_end, is_current, source)
                           VALUES (%s, %s, %s, %s, 'member', %s, %s, TRUE, 'council_minutes')
                           ON CONFLICT ON CONSTRAINT uq_commission_member
                           DO UPDATE SET
                               appointed_by = EXCLUDED.appointed_by,
                               term_end = EXCLUDED.term_end,
                               is_current = TRUE,
                               source = 'council_minutes',
                               updated_at = NOW()""",
                        (
                            city_fips, commission_id, appt["name"],
                            appt["normalized_name"], appt["appointed_by"],
                            appt["term_end"],
                        ),
                    )
                loaded += 1

            conn.commit()
        logger.info("Loaded %d appointment records to database", loaded)
    finally:
        conn.close()


# ── CLI ─────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract commission appointments from council meeting minutes"
    )
    parser.add_argument("--meetings-dir", type=Path, help="Directory of extracted meeting JSONs")
    parser.add_argument("--meeting", type=Path, help="Single meeting JSON file")
    parser.add_argument("--output", type=Path, help="Save extracted appointments JSON")
    parser.add_argument("--compare-website", type=Path, help="Website roster JSON for staleness check")
    parser.add_argument("--load", action="store_true", help="Load to Supabase")
    parser.add_argument("--city-fips", default=None, help="City FIPS code")
    args = parser.parse_args()

    fips = args.city_fips or CITY_FIPS
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.meeting:
        data = json.loads(args.meeting.read_text())
        appointments = extract_appointments_from_meeting(data)
    elif args.meetings_dir:
        appointments = extract_from_directory(args.meetings_dir, city_fips=fips)
    else:
        parser.print_help()
        return

    # Print summary
    print(f"\nExtracted {len(appointments)} appointment actions:")
    for a in appointments:
        print(f"  [{a['action']:10s}] {a['name']:25s} → {a['commission_name']:30s} (by {a.get('appointed_by', 'N/A')})")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(appointments, indent=2, default=str))
        logger.info("Saved to %s", args.output)

    if args.compare_website:
        website_data = json.loads(args.compare_website.read_text())
        findings = compare_with_website(appointments, website_data)
        if findings:
            print(f"\nStaleness findings ({len(findings)}):")
            for f in findings:
                print(f"  {f['commission']:30s} — {f['member']} ({f['action']} on {f['appointed_date']}) NOT on website")
        else:
            print("\nNo staleness findings — website roster matches minutes.")

    if args.load:
        load_to_db(appointments, city_fips=fips)


if __name__ == "__main__":
    main()
