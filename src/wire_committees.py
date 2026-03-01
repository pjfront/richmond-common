"""Wire committee records to officials by matching candidate names.

Extracts candidate names from committee name strings, then fuzzy-matches
against the officials table. Sets both `official_id` and `candidate_name`
on matching committees.

Usage:
    python wire_committees.py [--dry-run] [--city-fips 0660620]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    name = name.lower().strip()
    name = re.sub(r'[,.\'"!?;:()\[\]{}]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def flip_last_first(name: str) -> str | None:
    """Convert 'Last, First' to 'First Last'. Returns None if not that format."""
    if ',' in name:
        parts = [p.strip() for p in name.split(',', 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[1]} {parts[0]}"
    return None


def extract_candidate_from_committee(committee_name: str) -> str | None:
    """Extract candidate name from a campaign committee name.

    Handles patterns like:
      "Eduardo Martinez for Richmond Mayor 2022"
      "Eduardo Martinez 4 Richmond City Council 2018"
      "Friends of Tom Butt for Richmond City Council 2016"
      "Committee to Elect Andrew Butt for Richmond City Council District 2 2022"
      "Reelect Melvin Willis for Richmond City Council District 1 2024"
      "Vote Demnlus Johnson III for City Council 2018"
      "BECKLES FOR ASSEMBLY 2018, JOVANKA"  (reversed with comma)
      "MC LAUGHLIN FOR LIEUTENANT GOVERNOR 2018; GAYLE" (reversed with semicolon)
      "ROGERS, NEIGHBORS FOR" (reversed with comma)
      "Vote Sue Wilson for 2024 Richmond City Council District 5"
    """
    norm = committee_name.strip()

    # Handle CAL-ACCESS reversed format: "LASTNAME FOR OFFICE YEAR, FIRSTNAME"
    # or "LASTNAME FOR OFFICE YEAR; FIRSTNAME"
    reversed_m = re.match(
        r'^(.+?)\s+for\s+.+?[,;]\s*(\w[\w\s]*?)\s*$',
        norm, re.IGNORECASE,
    )
    if reversed_m:
        last_part = reversed_m.group(1).strip()
        first_part = reversed_m.group(2).strip()
        # Verify the last_part looks like a name (not too long, not a committee desc)
        if len(last_part.split()) <= 3 and len(first_part.split()) <= 3:
            return f"{first_part} {last_part}"

    # Handle "LASTNAME, NEIGHBORS FOR" / "ROGERS, NEIGHBORS FOR" pattern
    comma_m = re.match(r'^(\w+),\s*(neighbors|friends|committee)\s+for\b', norm, re.IGNORECASE)
    if comma_m:
        return comma_m.group(1).strip()

    # Pattern: "[prefix] [Name] for [Office]" or "[prefix] [Name] 4 [Office]"
    m = re.match(r'^(.+?)\s+(?:for|4)\s+', norm, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        # Strip known prefixes
        candidate = re.sub(
            r'^(friends of|committee to elect|elect|re-elect|reelect|vote)\s+',
            '', candidate, flags=re.IGNORECASE,
        ).strip()
        # Strip known suffixes
        candidate = re.sub(
            r'\s+(committee to elect|committee)\s*$',
            '', candidate, flags=re.IGNORECASE,
        ).strip()
        if candidate and len(candidate) > 2:
            return candidate

    return None


# Words that are clearly not person names
_NOT_A_NAME = {
    'coalition', 'committee', 'richmond', 'east bay', 'northern california',
    'bay area', 'pride and purpose', 'richmond progress',
}


def _is_plausible_person_name(name: str) -> bool:
    """Filter out extracted 'candidates' that are clearly not person names."""
    norm = name.lower().strip()
    # Too long (real names are 2-4 words)
    if len(norm.split()) > 5:
        return False
    # Known non-name phrases
    for bad in _NOT_A_NAME:
        if norm.startswith(bad):
            return False
    return True


def match_candidate_to_official(
    candidate_name: str,
    officials: list[dict],
) -> dict | None:
    """Match an extracted candidate name against the officials list.

    Returns the best matching official dict, or None.
    """
    cand_norm = normalize_name(candidate_name)
    cand_parts = set(cand_norm.split())

    best_match = None
    best_score = 0

    for official in officials:
        off_norm = official['normalized']
        off_parts = set(off_norm.split())

        # Exact normalized match
        if cand_norm == off_norm:
            return official  # Perfect match, return immediately

        # Check if candidate name has "Last, First" format
        flipped = flip_last_first(candidate_name)
        if flipped and normalize_name(flipped) == off_norm:
            return official

        # All parts of one name appear in the other (handles partial names)
        if len(cand_parts) >= 1 and len(off_parts) >= 2:
            # Candidate words that appear in official name
            overlap = cand_parts & off_parts
            if len(overlap) >= min(len(cand_parts), len(off_parts)):
                score = len(overlap)
                if score > best_score:
                    best_score = score
                    best_match = official
                    continue

        # Single-word candidate (e.g., "Anderson") — match against last names
        if len(cand_parts) == 1:
            cand_word = list(cand_parts)[0]
            for off_part in off_parts:
                if cand_word == off_part and len(cand_word) >= 4:
                    # Only if no better match found (single-word is weak)
                    if best_score < 1:
                        best_score = 1
                        best_match = official

    # Require at least 2-word overlap for multi-word candidates
    if best_match and len(cand_parts) >= 2 and best_score < 2:
        return None

    return best_match


def wire_committees(city_fips: str = "0660620", dry_run: bool = False) -> dict:
    """Match committees to officials and update the database.

    Returns summary dict with counts.
    """
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Load all officials for this city
    cur.execute(
        """SELECT id, name, normalized_name, role, is_current
           FROM officials WHERE city_fips = %s""",
        (city_fips,),
    )
    officials_raw = cur.fetchall()

    # Build officials list with normalized names (handle "Last, First" format)
    officials = []
    for row in officials_raw:
        name = row[1]
        normalized = normalize_name(name)
        officials.append({
            'id': row[0],
            'name': name,
            'normalized': normalized,
            'role': row[3],
            'is_current': row[4],
        })
        # Also add flipped version for "Last, First" names
        flipped = flip_last_first(name)
        if flipped:
            officials.append({
                'id': row[0],
                'name': name,
                'normalized': normalize_name(flipped),
                'role': row[3],
                'is_current': row[4],
            })

    # Role priority for when duplicate officials match (lower = preferred)
    council_role_priority = {
        'mayor': 1, 'vice_mayor': 2, 'councilmember': 3,
        'council_member': 3, 'city/town council member': 4,
    }
    council_roles = set(council_role_priority.keys())

    # Load all committees
    cur.execute(
        """SELECT id, name FROM committees WHERE city_fips = %s""",
        (city_fips,),
    )
    committees = cur.fetchall()

    matched = 0
    extracted = 0
    skipped = 0
    results = []

    for comm_id, comm_name in committees:
        candidate = extract_candidate_from_committee(comm_name)
        if not candidate or not _is_plausible_person_name(candidate):
            skipped += 1
            results.append((comm_name, None, None, 'no_candidate'))
            continue

        extracted += 1
        official = match_candidate_to_official(candidate, officials)

        if official:
            # If multiple officials match (e.g., Eduardo Martinez appears twice),
            # prefer the council-level role
            cand_norm = normalize_name(candidate)
            all_matches = [
                o for o in officials
                if normalize_name(o['name']) == normalize_name(official['name'])
                or o['normalized'] == official['normalized']
            ]
            # Deduplicate by id
            seen_ids = set()
            unique_matches = []
            for m in all_matches:
                if m['id'] not in seen_ids:
                    seen_ids.add(m['id'])
                    unique_matches.append(m)

            if len(unique_matches) > 1:
                # Prefer higher-priority council roles (mayor > vice_mayor > councilmember)
                council_matches = [
                    m for m in unique_matches
                    if m['role'].lower() in council_roles
                ]
                if council_matches:
                    council_matches.sort(
                        key=lambda m: council_role_priority.get(m['role'].lower(), 99)
                    )
                    official = council_matches[0]

            matched += 1
            results.append((comm_name, candidate, official['name'], 'matched'))

            if not dry_run:
                cur.execute(
                    """UPDATE committees
                       SET candidate_name = %s, official_id = %s
                       WHERE id = %s""",
                    (candidate, str(official['id']), str(comm_id)),
                )
        else:
            # Set candidate_name even without official match
            results.append((comm_name, candidate, None, 'unmatched'))
            if not dry_run:
                cur.execute(
                    """UPDATE committees
                       SET candidate_name = %s
                       WHERE id = %s""",
                    (candidate, str(comm_id)),
                )

    if not dry_run:
        conn.commit()

    conn.close()

    summary = {
        'total': len(committees),
        'extracted': extracted,
        'matched': matched,
        'unmatched': extracted - matched,
        'skipped': skipped,
    }

    return summary, results


def main():
    parser = argparse.ArgumentParser(description="Wire committees to officials")
    parser.add_argument("--city-fips", default="0660620")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show matches without updating database")
    args = parser.parse_args()

    summary, results = wire_committees(args.city_fips, args.dry_run)

    print(f"\n{'=== DRY RUN ===' if args.dry_run else '=== RESULTS ==='}")
    print(f"Total committees:  {summary['total']}")
    print(f"Candidate extracted: {summary['extracted']}")
    print(f"  Matched to official: {summary['matched']}")
    print(f"  Unmatched:          {summary['unmatched']}")
    print(f"Skipped (PAC/ballot): {summary['skipped']}")

    print("\n--- Matched ---")
    for comm, cand, off, status in results:
        if status == 'matched':
            print(f"  {comm}")
            print(f"    → candidate: {cand} → official: {off}")

    print("\n--- Extracted but unmatched ---")
    for comm, cand, off, status in results:
        if status == 'unmatched':
            print(f"  {comm}")
            print(f"    → candidate: {cand}")

    print("\n--- Skipped (no candidate extractable) ---")
    for comm, cand, off, status in results:
        if status == 'no_candidate':
            print(f"  {comm}")


if __name__ == "__main__":
    main()
