"""
Validate text extraction quality across all downloaded meeting minutes.

Checks for the key patterns that the Claude extraction pipeline needs:
- Roll call vote format ("Ayes: ... Noes: ... Abstentions: ...")
- Council member names appearing in text
- Agenda item numbering patterns
- Meeting date headers
- Common section markers (consent calendar, public hearings, etc.)

This gives confidence that the text extraction is good enough for Claude
to produce structured JSON from, WITHOUT needing to run the API.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"

# Known Richmond council members (current + recent)
COUNCIL_MEMBERS = [
    "Martinez", "Zepeda", "Bana", "Brown", "Jimenez", "Robinson", "Wilson",
    # Historical
    "Butt", "Bates", "McLaughlin", "Willis", "Recinos",
]

# Key patterns that indicate parseable minutes
PATTERNS = {
    "roll_call_votes": re.compile(
        r"Ayes\s*(?:\(\d+\))?\s*:\s*(?:Council\s*(?:member|President)|Commissioner)?\s*[\w,\s]+",
        re.IGNORECASE,
    ),
    "vote_simple": re.compile(
        r"Ayes\s*(?:\(\d+\))?\s*:",
        re.IGNORECASE,
    ),
    "consent_calendar": re.compile(
        r"consent\s+calendar",
        re.IGNORECASE,
    ),
    "public_hearing": re.compile(
        r"public\s+hearing",
        re.IGNORECASE,
    ),
    "closed_session": re.compile(
        r"closed\s+session",
        re.IGNORECASE,
    ),
    "agenda_item_number": re.compile(
        r"\b[A-Z]\.\d+(?:\.[a-z])?\b"  # e.g., O.3.a, H.1, P.2
    ),
    "resolution_number": re.compile(
        r"Resolution\s+No\.\s*\d+[-–]\d+",
        re.IGNORECASE,
    ),
    "ordinance_number": re.compile(
        r"Ordinance\s+No\.\s*\d+[-–]\d+",
        re.IGNORECASE,
    ),
    "meeting_date": re.compile(
        r"(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2},?\s+\d{4}",
        re.IGNORECASE,
    ),
    "dollar_amount": re.compile(
        r"\$[\d,]+(?:\.\d{2})?"
    ),
    "motion_made": re.compile(
        r"(?:motion|moved)\s+(?:by|was made)",
        re.IGNORECASE,
    ),
}


def validate_meeting(txt_path: Path) -> dict:
    """Validate a single meeting's extracted text."""
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    adid = txt_path.stem.replace("adid_", "")

    result = {
        "adid": adid,
        "char_count": len(text),
        "line_count": text.count("\n"),
        "council_members_found": [],
        "pattern_counts": {},
        "issues": [],
        "quality_score": 0,
    }

    # Check for council member names
    for name in COUNCIL_MEMBERS:
        if name.lower() in text.lower():
            result["council_members_found"].append(name)

    # Count pattern occurrences
    for pattern_name, pattern in PATTERNS.items():
        matches = pattern.findall(text)
        result["pattern_counts"][pattern_name] = len(matches)

    # Quality checks
    score = 0

    # Must have at least some content
    if len(text) < 1000:
        result["issues"].append("Very short text (<1000 chars) — may be a stub or error page")
    else:
        score += 10

    # Should find council members
    if len(result["council_members_found"]) >= 3:
        score += 20
    elif len(result["council_members_found"]) >= 1:
        score += 10
        result["issues"].append(f"Only {len(result['council_members_found'])} council members found")
    else:
        result["issues"].append("No council member names found — may not be meeting minutes")

    # Should have vote records
    if result["pattern_counts"]["vote_simple"] >= 1:
        score += 20
    else:
        result["issues"].append("No vote records (Ayes/Noes) found")

    # Should have a meeting date
    if result["pattern_counts"]["meeting_date"] >= 1:
        score += 10
    else:
        result["issues"].append("No meeting date found")

    # Should have agenda item numbers
    if result["pattern_counts"]["agenda_item_number"] >= 3:
        score += 15
    elif result["pattern_counts"]["agenda_item_number"] >= 1:
        score += 10
        result["issues"].append("Few agenda item numbers found")
    else:
        result["issues"].append("No agenda item numbers found")

    # Should have consent calendar section
    if result["pattern_counts"]["consent_calendar"] >= 1:
        score += 10

    # Should have dollar amounts (budgets, contracts)
    if result["pattern_counts"]["dollar_amount"] >= 1:
        score += 5

    # Should have motion records
    if result["pattern_counts"]["motion_made"] >= 1:
        score += 5

    # Resolution or ordinance numbers are a good sign
    if result["pattern_counts"]["resolution_number"] >= 1:
        score += 5

    result["quality_score"] = score
    return result


def validate_all() -> list[dict]:
    """Validate all downloaded meetings."""
    txt_files = sorted(RAW_DIR.glob("adid_*.txt"))
    if not txt_files:
        print("No text files found in data/raw/")
        return []

    results = []
    for txt_path in txt_files:
        result = validate_meeting(txt_path)
        results.append(result)

    return results


def print_report(results: list[dict]):
    """Print a validation report."""
    print("=" * 70)
    print("MEETING TEXT EXTRACTION QUALITY REPORT")
    print("=" * 70)
    print(f"\nTotal meetings: {len(results)}")

    scores = [r["quality_score"] for r in results]
    print(f"Quality scores: min={min(scores)}, max={max(scores)}, avg={sum(scores)/len(scores):.0f}")

    # Count by quality tier
    excellent = sum(1 for s in scores if s >= 80)
    good = sum(1 for s in scores if 60 <= s < 80)
    fair = sum(1 for s in scores if 40 <= s < 60)
    poor = sum(1 for s in scores if s < 40)
    print(f"  Excellent (80+): {excellent}")
    print(f"  Good (60-79):    {good}")
    print(f"  Fair (40-59):    {fair}")
    print(f"  Poor (<40):      {poor}")

    # Pattern totals across all meetings
    print(f"\n{'Pattern':<25s} {'Total':>8s} {'Avg/Meeting':>12s}")
    print("-" * 50)
    pattern_totals = {}
    for r in results:
        for k, v in r["pattern_counts"].items():
            pattern_totals[k] = pattern_totals.get(k, 0) + v

    for pattern, total in sorted(pattern_totals.items(), key=lambda x: -x[1]):
        avg = total / len(results)
        print(f"  {pattern:<23s} {total:>8d} {avg:>10.1f}")

    # Council member coverage
    print(f"\n{'Council Member':<20s} {'Meetings Found In':>20s}")
    print("-" * 45)
    member_counts = {}
    for r in results:
        for m in r["council_members_found"]:
            member_counts[m] = member_counts.get(m, 0) + 1
    for member, count in sorted(member_counts.items(), key=lambda x: -x[1]):
        pct = count / len(results) * 100
        print(f"  {member:<18s} {count:>8d} ({pct:.0f}%)")

    # Meetings with issues
    meetings_with_issues = [r for r in results if r["issues"]]
    if meetings_with_issues:
        print(f"\nMeetings with issues ({len(meetings_with_issues)}):")
        for r in meetings_with_issues:
            print(f"  ADID {r['adid']} (score={r['quality_score']}):")
            for issue in r["issues"]:
                print(f"    - {issue}")

    # Per-meeting detail (sorted by date/ADID descending)
    print(f"\n{'ADID':>8s} {'Chars':>8s} {'Score':>6s} {'Members':>8s} {'Votes':>6s} {'Items':>6s} {'Issues':>7s}")
    print("-" * 60)
    for r in sorted(results, key=lambda x: int(x["adid"]), reverse=True):
        print(
            f"  {r['adid']:>6s} {r['char_count']:>8,d} {r['quality_score']:>5d} "
            f"{len(r['council_members_found']):>7d} "
            f"{r['pattern_counts']['vote_simple']:>5d} "
            f"{r['pattern_counts']['agenda_item_number']:>5d} "
            f"{len(r['issues']):>6d}"
        )


def main():
    results = validate_all()
    if results:
        print_report(results)

        # Save detailed results
        output_path = DATA_DIR / "text_quality_report.json"
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nDetailed results saved to: {output_path}")


if __name__ == "__main__":
    main()
