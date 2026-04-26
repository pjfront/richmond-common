"""
Sync the auto-managed sections of canonical_names.md from the DB.

The file has two kinds of sections:

1. **Auto-synced** (this script regenerates them):
   - "Richmond City Council (current term)" — from `officials` table
   - "Richmond Municipal Staff (current, FY2026)" — from `city_employees` table

2. **Hand-curated** (preserved verbatim):
   - Former officials, Contra Costa County, retained counsel,
     recurring organizations, header text, maintenance footer.

For auto-synced entries that already exist, the "Often misheard as:" alias
lines are preserved — only the canonical name and role/title get regenerated.
This means operators can curate aliases by hand and the sync won't clobber
them.

Usage:
  python sync_canonical_names.py             # regenerate, write file
  python sync_canonical_names.py --dry-run   # show diff, don't write
  python sync_canonical_names.py --check     # exit 1 if file is stale

Run after any council member change, role change, or department-head update.
Idempotent — running twice in a row produces no diff.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

CANONICAL_NAMES_PATH = Path(__file__).parent / "prompts" / "canonical_names.md"
RICHMOND_FIPS = "0660620"
CURRENT_FISCAL_YEAR = "2026"

COUNCIL_HEADING = "## Richmond City Council (current term)"
STAFF_HEADING = f"## Richmond Municipal Staff (current, FY{CURRENT_FISCAL_YEAR})"

# Job titles we treat as canonical-worthy. Matched as ILIKE prefixes/exact.
# These appear in transcripts often enough that misspelling them is a
# credibility risk; departmental staff below this level rarely surface in
# council meetings.
KEY_TITLE_PATTERNS = [
    "CITY MANAGER",
    "CITY ATTORNEY",
    "CITY CLERK",
    "FIRE CHIEF",
    "POLICE CHIEF",
    "PORT DIRECTOR",
    "ADMINISTRATIVE CHIEF",
    "DIRECTOR OF",
    "EXECUTIVE DIRECTOR",
    "DEPUTY CITY MANAGER",
    "DEP DIR PW",
    "SR AST CITY ATTORNEY",
]


def _title_case_role(raw_title: str, raw_dept: str | None) -> str:
    """Map payroll job_title (ALL CAPS, abbreviated) to a readable role.

    Payroll uses fixed-width abbreviations like "DIR DEV" or "SR AST CITY
    ATTORNEY - ANNUITA". We expand the common ones; everything else gets
    title-cased verbatim.
    """
    t = raw_title.strip().upper()

    overrides = {
        "CITY MANAGER": "City Manager",
        "CITY ATTORNEY": "City Attorney",
        "CITY CLERK": "City Clerk",
        "FIRE CHIEF": "Fire Chief",
        "POLICE CHIEF": "Police Chief",
        "PORT DIRECTOR": "Port Director",
        "ADMINISTRATIVE CHIEF": "Administrative Chief (City Manager's office)",
        "DIRECTOR OF FINANCE": "Director of Finance",
        "DIRECTOR OF HUMAN RESOURCES": "Director of Human Resources",
        "DIRECTOR OF INFORMATION TECH": "Director of Information Technology",
        "DIRECTOR OF PUBLIC WORKS": "Director of Public Works",
        "DIRECTOR OF COMMUNITY DEV": "Director of Community Development (Planning & Building)",
        "DIRECTOR OF ECONOMIC DEVELOPME": "Director of Economic Development",
        "EXECUTIVE DIRECTOR RENT PRGRM": "Executive Director, Rent Program",
        "DEP DIR PW - CITY ENGINEER": "Deputy Director of Public Works / City Engineer",
        "SR AST CITY ATTORNEY - ANNUITA": "Senior Assistant City Attorney",
        "DEPUTY CITY MANAGER": None,  # handled below — disambiguate by dept
    }

    if t in overrides and overrides[t] is not None:
        return overrides[t]  # type: ignore[return-value]

    # Deputy City Manager — disambiguate by department since multiple exist.
    if t == "DEPUTY CITY MANAGER":
        dept = (raw_dept or "").strip().title()
        # Cleaner labels for the two we know about
        dept_map = {
            "Community Services": "Community Services",
            "Finance": "Finance",
        }
        nicer = dept_map.get(dept, dept or "")
        return f"Deputy City Manager ({nicer})" if nicer else "Deputy City Manager"

    # Generic fallback: title-case
    return raw_title.strip().title()


def _name_title_case(name: str) -> str:
    """Convert payroll ALL-CAPS / mixed-case name to canonical Title Case.

    Handles hyphens and apostrophes. e.g.:
      'Abigail Sims-evelyn' -> 'Abigail Sims-Evelyn'
      'Heather Mclaughlin Westmoreland' -> 'Heather McLaughlin Westmoreland'
    """
    parts = []
    for word in name.split():
        if "-" in word:
            sub = "-".join(p.capitalize() for p in word.split("-"))
            parts.append(sub)
        elif word.lower().startswith("mc") and len(word) > 2:
            # McLaughlin, McDonald — capitalize the letter after "Mc"
            parts.append("Mc" + word[2:].capitalize())
        else:
            parts.append(word.capitalize())
    return " ".join(parts)


def _query_council() -> list[dict]:
    """Return current Richmond council members from `officials`."""
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT name, role, seat FROM officials
                   WHERE city_fips = %s AND is_current = TRUE
                   ORDER BY
                     CASE role
                       WHEN 'mayor' THEN 0
                       WHEN 'vice_mayor' THEN 1
                       ELSE 2
                     END,
                     seat NULLS LAST,
                     name
                """,
                (RICHMOND_FIPS,),
            )
            return [
                {"name": r[0], "role": r[1], "seat": r[2]}
                for r in cur.fetchall()
            ]
    finally:
        conn.close()


def _query_staff() -> list[dict]:
    """Return current key Richmond municipal staff from `city_employees`."""
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Match titles starting with any of KEY_TITLE_PATTERNS
            ilike_clauses = " OR ".join(
                ["job_title ILIKE %s" for _ in KEY_TITLE_PATTERNS],
            )
            params = (
                [RICHMOND_FIPS, CURRENT_FISCAL_YEAR]
                + [p + "%" for p in KEY_TITLE_PATTERNS]
            )
            cur.execute(
                f"""SELECT name, job_title, department
                    FROM city_employees
                    WHERE city_fips = %s
                      AND is_current = TRUE
                      AND fiscal_year = %s
                      AND ({ilike_clauses})
                    ORDER BY hierarchy_level NULLS LAST, job_title, name
                """,
                params,
            )
            return [
                {"name": r[0], "title": r[1], "department": r[2]}
                for r in cur.fetchall()
            ]
    finally:
        conn.close()


def _format_council_role(member: dict) -> str:
    """Render '{role}, District N' label for a council member."""
    seat = member.get("seat") or ""
    role = member.get("role") or ""
    if role == "mayor":
        return "Mayor"
    if role == "vice_mayor":
        return f"Vice Mayor, {seat}" if seat else "Vice Mayor"
    return f"Councilmember, {seat}" if seat else "Councilmember"


def _parse_existing_aliases(existing_text: str, heading: str) -> dict[str, list[str]]:
    """Extract `name -> [alias_lines]` map from an existing section.

    "alias_lines" are the bullet lines under each `**Name** — Role` header,
    preserved verbatim (with leading "- " kept). This is what we want to
    keep across regenerations.
    """
    aliases: dict[str, list[str]] = {}
    section = _extract_section(existing_text, heading)
    if not section:
        return aliases

    # Split into entries on blank lines after a `**Name**` header.
    entries = re.split(r"\n(?=\*\*[^*]+\*\*)", section)
    for entry in entries:
        m = re.match(r"\*\*([^*]+)\*\*", entry.strip())
        if not m:
            continue
        name = m.group(1).strip()
        # Collect bullet lines after the header
        bullet_lines = []
        for line in entry.splitlines()[1:]:
            if line.strip().startswith("- "):
                bullet_lines.append(line.rstrip())
        if bullet_lines:
            aliases[name] = bullet_lines
    return aliases


def _extract_section(text: str, heading: str) -> str | None:
    """Return the body of a section between `## heading` and the next `## `."""
    pattern = re.compile(
        rf"^{re.escape(heading)}\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _replace_section(text: str, heading: str, new_body: str) -> str:
    """Replace the body of `## heading` with `new_body`. Add if missing."""
    pattern = re.compile(
        rf"(^{re.escape(heading)}\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(rf"\1\n{new_body}\n\n", text)
    # Section missing — append before final `## Maintenance` if exists
    maint_idx = text.find("## Maintenance")
    insertion = f"\n{heading}\n\n{new_body}\n\n---\n\n"
    if maint_idx >= 0:
        return text[:maint_idx] + insertion + text[maint_idx:]
    return text + "\n" + insertion


def _render_council_entry(member: dict, alias_map: dict[str, list[str]]) -> str:
    """Format a single council member entry."""
    name = member["name"]
    role_label = _format_council_role(member)
    aliases = alias_map.get(name, [])
    lines = [f"**{name}** — {role_label}"]
    lines.extend(aliases)
    return "\n".join(lines)


def _render_staff_entry(emp: dict, alias_map: dict[str, list[str]]) -> str:
    """Format a single municipal-staff entry."""
    name = _name_title_case(emp["name"])
    role = _title_case_role(emp["title"], emp.get("department"))
    aliases = alias_map.get(name, [])
    lines = [f"**{name}** — {role}"]
    lines.extend(aliases)
    return "\n".join(lines)


def build_council_section(existing_text: str) -> str:
    """Generate body of the Richmond City Council section."""
    members = _query_council()
    if not members:
        raise RuntimeError("No current officials found — refusing to wipe section.")
    alias_map = _parse_existing_aliases(existing_text, COUNCIL_HEADING)
    entries = [_render_council_entry(m, alias_map) for m in members]
    return "\n\n".join(entries) + "\n\n---"


def build_staff_section(existing_text: str) -> str:
    """Generate body of the Richmond Municipal Staff section."""
    staff = _query_staff()
    if not staff:
        raise RuntimeError("No current staff found — refusing to wipe section.")
    alias_map = _parse_existing_aliases(existing_text, STAFF_HEADING)

    intro = (
        "Auto-synced from `city_employees` table. Source: City of Richmond "
        "payroll (Socrata dataset `crbs-mam9`).\n"
    )
    entries = [_render_staff_entry(e, alias_map) for e in staff]
    return intro + "\n" + "\n\n".join(entries) + "\n\n---"


def regenerate(existing_text: str) -> str:
    """Return new file text with both auto-sections regenerated."""
    new_text = _replace_section(
        existing_text, COUNCIL_HEADING, build_council_section(existing_text),
    )
    new_text = _replace_section(
        new_text, STAFF_HEADING, build_staff_section(existing_text),
    )
    # Normalize trailing whitespace / multiple blank lines from regeneration
    new_text = re.sub(r"\n{3,}", "\n\n", new_text)
    if not new_text.endswith("\n"):
        new_text += "\n"
    return new_text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show diff, don't write")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if file is stale (for CI)")
    args = parser.parse_args()

    existing = CANONICAL_NAMES_PATH.read_text(encoding="utf-8")
    new_text = regenerate(existing)

    if existing == new_text:
        print(f"canonical_names.md is up to date ({len(existing)} chars)")
        return

    if args.check:
        print("canonical_names.md is STALE — run sync_canonical_names.py")
        sys.exit(1)

    if args.dry_run:
        # Tiny diff: just show line count change + first diverging line
        old_lines = existing.splitlines()
        new_lines = new_text.splitlines()
        print(f"Would change canonical_names.md")
        print(f"  before: {len(old_lines)} lines, {len(existing)} chars")
        print(f"  after:  {len(new_lines)} lines, {len(new_text)} chars")
        for i, (a, b) in enumerate(zip(old_lines, new_lines)):
            if a != b:
                print(f"  first diff at line {i + 1}:")
                print(f"    -  {a}")
                print(f"    +  {b}")
                break
        return

    CANONICAL_NAMES_PATH.write_text(new_text, encoding="utf-8")
    print(f"Wrote canonical_names.md ({len(new_text)} chars)")


if __name__ == "__main__":
    main()
