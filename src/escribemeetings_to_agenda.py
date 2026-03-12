"""
Convert eSCRIBE meeting_data.json to the agenda JSON format expected by
the conflict scanner and comment generator.

This avoids a Claude API call when we already have structured data from eSCRIBE.
The eSCRIBE scraper produces item-level data (titles, descriptions, attachments)
that maps directly to the schema used by extract_agenda.py.

Usage:
    python escribemeetings_to_agenda.py data/raw/escribemeetings/2026-02-17_City_Council/meeting_data.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# Richmond City Council meeting section mapping (eSCRIBE item prefixes)
# These are consistent across Richmond meetings:
#   V = City Council Consent Calendar
#   M = Housing Authority Consent Calendar
#   O-U = Regular meeting procedural sections
CONSENT_PREFIX = "V."
HOUSING_PREFIX = "M."


def classify_category(title: str, description: str) -> str:
    """Classify an agenda item into a category based on its text."""
    text = f"{title} {description}".lower()

    if any(w in text for w in ["roll call", "pledge of allegiance", "pledge to the flag",
                                "approval of minutes", "approve minutes", "approval of the agenda",
                                "approve the agenda", "agenda reorder", "adjournment", "adjourned",
                                "recess"]):
        return "procedural"
    if any(w in text for w in ["zone", "zoning", "land use", "general plan", "parcel"]):
        return "zoning"
    if any(w in text for w in ["budget", "appropriat", "fiscal", "revenue", "tax"]):
        return "budget"
    if any(w in text for w in ["housing", "tenant", "rent", "affordable", "harc"]):
        return "housing"
    if any(w in text for w in ["police", "fire", "public safety", "emergency"]):
        return "public_safety"
    if any(w in text for w in ["environment", "climate", "pollution", "chevron"]):
        return "environment"
    if any(w in text for w in ["infrastructure", "road", "sewer", "water", "bridge", "paving"]):
        return "infrastructure"
    if any(w in text for w in ["personnel", "hiring", "appointment", "salary", "employee"]):
        return "personnel"
    if any(w in text for w in ["contract", "agreement", "vendor", "rfp", "bid", "amendment"]):
        return "contracts"
    if any(w in text for w in ["ordinance", "resolution", "governance", "council", "policy"]):
        return "governance"
    if any(w in text for w in ["proclamation", "recognition", "honoring"]):
        return "proclamation"
    if any(w in text for w in ["litigation", "legal", "lawsuit", "claim"]):
        return "litigation"
    return "other"


def extract_financial_amount(text: str) -> str | None:
    """Extract the largest dollar amount from text.

    Handles $X,XXX and $X.X million/billion patterns.
    Returns the largest amount found, normalized to "$X,XXX" format.
    """
    if not text:
        return None

    amounts: list[int] = []

    # Match $X million / $X.X billion patterns first (highest value)
    for m in re.finditer(r'\$(\d+(?:\.\d+)?)\s*(million|billion)', text, re.IGNORECASE):
        val = float(m.group(1))
        multiplier = 1_000_000_000 if m.group(2).lower() == 'billion' else 1_000_000
        amounts.append(int(val * multiplier))

    # Match $X,XXX,XXX or $X,XXX patterns
    for m in re.finditer(r'\$([\d,]+(?:\.\d{2})?)', text):
        raw = m.group(1).replace(',', '')
        try:
            val = float(raw)
            amounts.append(int(val))
        except ValueError:
            continue

    if not amounts:
        return None

    largest = max(amounts)
    return f"${largest:,}"


def convert_escribemeetings_to_agenda(meeting_data_path: Path, output_path: Path) -> dict:
    """Convert eSCRIBE meeting_data.json to conflict-scanner-compatible agenda JSON."""
    with open(meeting_data_path) as f:
        data = json.load(f)

    meeting_date = data.get("meeting_date", "")
    meeting_name = data.get("meeting_name", "City Council")
    meeting_type = "special" if "special" in meeting_name.lower() else "regular"

    # Build agenda structure
    agenda = {
        "meeting_date": meeting_date,
        "meeting_type": meeting_type,
        "city_fips": "0660620",
        "members_present": [],  # eSCRIBE doesn't list members; will be empty
        "members_absent": [],
        "conflict_of_interest_declared": [],
        "closed_session_items": [],
        "consent_calendar": {"items": []},
        "action_items": [],
        "housing_authority_items": [],
        "source": "escribemeetings",
        "source_url": data.get("url", ""),
    }

    for item in data.get("items", []):
        item_num = item.get("item_number", "")
        title = item.get("title", "")
        description = item.get("description", "")

        # Skip top-level section headers (no dot = section header like V, M, O)
        if not "." in item_num:
            continue

        # Skip sub-items if parent already captured the content
        # V.1.a, V.1.b are sub-items of V.1 — include them as separate items

        converted = {
            "item_number": item_num,
            "title": title,
            "description": description,
            "category": classify_category(title, description),
            "financial_amount": extract_financial_amount(f"{title} {description}"),
        }

        # Extract department from title or description
        dept_match = re.search(
            r'[-–—]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Department|Office|Division)))',
            f"{title} {description}"
        )
        if dept_match:
            converted["department"] = dept_match.group(1)

        if item_num.startswith(CONSENT_PREFIX):
            agenda["consent_calendar"]["items"].append(converted)
        elif item_num.startswith(HOUSING_PREFIX):
            agenda["housing_authority_items"].append(converted)
        elif item_num.startswith("C."):
            # Closed session items
            agenda["closed_session_items"].append({
                "item_number": item_num,
                "description": f"{title} {description}",
                "legal_authority": "",
            })
        else:
            # Other numbered items (action items, reports, etc.)
            agenda["action_items"].append(converted)

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(agenda, f, indent=2)

    consent_count = len(agenda["consent_calendar"]["items"])
    action_count = len(agenda["action_items"])
    housing_count = len(agenda["housing_authority_items"])
    closed_count = len(agenda["closed_session_items"])

    print(f"Converted eSCRIBE meeting data -> agenda JSON")
    print(f"  Meeting: {meeting_date} ({meeting_type})")
    print(f"  Consent items: {consent_count}")
    print(f"  Action items: {action_count}")
    print(f"  Housing authority items: {housing_count}")
    print(f"  Closed session items: {closed_count}")
    print(f"  Saved to: {output_path}")

    return agenda


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert eSCRIBE meeting_data.json to conflict-scanner-compatible agenda JSON"
    )
    parser.add_argument("meeting_data", help="Path to eSCRIBE meeting_data.json")
    parser.add_argument("--output", help="Output path (default: auto-named in data/extracted/)")
    args = parser.parse_args()

    meeting_data_path = Path(args.meeting_data)
    if not meeting_data_path.exists():
        print(f"ERROR: {meeting_data_path} not found")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        # Auto-name from meeting date
        with open(meeting_data_path) as f:
            d = json.load(f)
        date = d.get("meeting_date", "unknown")
        output_path = Path(__file__).parent / "data" / "extracted" / f"{date}_agenda.json"

    convert_escribemeetings_to_agenda(meeting_data_path, output_path)
