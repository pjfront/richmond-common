from __future__ import annotations
"""
Extract structured data from a Richmond city council AGENDA (pre-meeting).

Unlike minutes extraction, this processes the agenda before the meeting happens,
producing structured JSON that can be fed into the conflict scanner to generate
a public comment before the meeting.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
# .env is in repo root, one level above src/
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import anthropic

SYSTEM_PROMPT = """You are a precise data extraction system for the Richmond Common.
Your job is to extract structured data from a Richmond, CA City Council meeting AGENDA.

This is a PRE-MEETING agenda, not minutes. There are no votes or motions yet.
Extract all agenda items, their descriptions, departments, financial amounts, and categories.

Return valid JSON with all items in a structure compatible with meeting minutes analysis."""

SCHEMA = {
    "meeting_date": "YYYY-MM-DD",
    "meeting_type": "regular|special",
    "members_present": [{"name": "string", "role": "mayor|vice_mayor|councilmember"}],
    "members_absent": [],
    "conflict_of_interest_declared": [],
    "closed_session_items": [{"item_number": "string", "description": "string", "legal_authority": "string"}],
    "consent_calendar": {
        "items": [{
            "item_number": "string",
            "title": "string",
            "description": "full text of what council will vote on",
            "department": "string",
            "staff_contact": "string",
            "category": "zoning|budget|housing|public_safety|environment|infrastructure|personnel|contracts|governance|proclamation|litigation|other|procedural",
            "financial_amount": "dollar amount if applicable",
        }]
    },
    "action_items": [{
        "item_number": "string",
        "title": "string",
        "description": "string",
        "department": "string",
        "category": "string",
    }],
    "housing_authority_items": [{
        "item_number": "string",
        "title": "string",
        "description": "string",
        "department": "string",
        "financial_amount": "string",
    }],
}


def extract_agenda(txt_path: Path, output_path: Path) -> dict:
    """Extract structured data from agenda text using Claude API."""
    agenda_text = txt_path.read_text(encoding="utf-8")

    prompt = f"""Extract all structured data from the following Richmond, CA City Council meeting AGENDA.
Return valid JSON matching this schema:

{json.dumps(SCHEMA, indent=2)}

IMPORTANT:
- This is an AGENDA, not minutes. Extract what will be discussed/voted on.
- Include ALL consent calendar items with full descriptions.
- Include ALL housing authority items.
- Include ALL closed session items.
- Capture financial amounts for contracts and expenditures.
- Use the category that best fits each item.
- For members_present, list all council members shown on the agenda header.

Agenda text:
---
{agenda_text}
---

Return ONLY valid JSON. No explanation."""

    client = anthropic.Anthropic()
    print("Calling Claude API for agenda extraction...")
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    cost = (input_tokens * 3 + output_tokens * 15) / 1_000_000

    print(f"Response: {len(response_text)} chars")
    print(f"Tokens: {input_tokens} input + {output_tokens} output")
    print(f"Cost: ~${cost:.4f}")

    # Parse JSON — strip markdown code fences if present
    clean = response_text.strip()
    if clean.startswith("```"):
        # Remove ```json ... ``` wrapping
        lines = clean.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines)
    data = json.loads(clean)

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    consent_count = len(data.get("consent_calendar", {}).get("items", []))
    action_count = len(data.get("action_items", []))
    housing_count = len(data.get("housing_authority_items", []))
    print(f"Saved to {output_path}")
    print(f"Items: {consent_count} consent, {action_count} action, {housing_count} housing auth")

    return data


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract structured data from council agenda")
    parser.add_argument("input", help="Path to agenda text file")
    parser.add_argument("--output", help="Output JSON path (default: auto-named in data/extracted/)")
    args = parser.parse_args()

    txt_path = Path(args.input)
    if not txt_path.exists():
        print(f"ERROR: {txt_path} not found")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(__file__).parent / "data" / "extracted" / f"{txt_path.stem}_agenda.json"

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "sk-ant-...":
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    extract_agenda(txt_path, output_path)
