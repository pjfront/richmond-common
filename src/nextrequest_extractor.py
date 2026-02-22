"""
Richmond Transparency Project — NextRequest Document Extractor

Claude API extraction of CPRA document contents into structured data.
Generic-first prompt identifies document type and extracts accordingly.

Usage:
  python nextrequest_extractor.py --document path/to/doc.pdf
  python nextrequest_extractor.py --batch path/to/dir/
  python nextrequest_extractor.py --cross-ref meeting.json
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:
    anthropic = None

# Minimum text length for extraction (below this, not worth the API cost)
MIN_TEXT_LENGTH = 50

EXTRACTION_PROMPT = """You are analyzing a document released through a California Public Records Act (CPRA) request from the City of Richmond, California.

First, identify the document type from this list:
- contract: Agreements, MOUs, professional services agreements
- correspondence: Emails, letters, memos
- report: Staff reports, analyses, audits, studies
- financial: Invoices, purchase orders, payment records
- policy: Policies, procedures, guidelines, ordinances
- legal: Legal opinions, court documents, settlement agreements
- permit: Permits, applications, approvals
- other: Anything that doesn't fit the above categories

Then extract structured information appropriate to the document type.

Document filename: {filename}
Document type hint from extension: {file_type}

Respond with a JSON object containing:
{{
  "document_type": "<type from list above>",
  "summary": "<1-2 sentence summary>",
  "entities": ["<list of organizations, companies, people mentioned>"],
  "amounts": [<list of dollar amounts mentioned as numbers>],
  "dates": ["<list of dates mentioned in YYYY-MM-DD format>"],
  "department": "<city department if identifiable>",
  "parties": ["<list of parties to agreements/contracts if applicable>"],
  "amount": <primary dollar amount if applicable, null otherwise>,
  "term_start": "<contract start date if applicable, YYYY-MM-DD>",
  "term_end": "<contract end date if applicable, YYYY-MM-DD>",
  "key_findings": ["<list of notable findings, conclusions, or decisions>"]
}}

Document text:
{text}
"""


def extract_document(
    text: str,
    filename: str = "unknown",
    file_type: str = "pdf",
) -> dict | None:
    """Extract structured data from a CPRA document using Claude API.

    Returns dict with document_type, summary, entities, amounts, etc.
    Returns None if text is too short or extraction fails.
    """
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        return None

    if not anthropic:
        logger.error("anthropic package not installed — cannot extract")
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        return None

    client = anthropic.Anthropic(api_key=api_key)

    # Truncate very long documents (Claude context limit)
    max_chars = 100_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated ...]"

    prompt = EXTRACTION_PROMPT.format(
        filename=filename,
        file_type=file_type,
        text=text,
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = response.content[0].text.strip()

        # Parse JSON from response (handle markdown code blocks)
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            result_text = result_text.rsplit("```", 1)[0]

        return json.loads(result_text)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse extraction response: {e}")
        return None
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return None


def cross_reference_agenda(
    extracted: dict,
    agenda_items: list[dict],
) -> list[dict]:
    """Cross-reference extracted document entities against agenda items.

    Uses entity name matching (same pattern as conflict_scanner.py).
    Returns list of matching agenda items with match reason.
    """
    entities = [e.lower() for e in extracted.get("entities", []) if e]
    # Filter out generic entities
    skip_entities = {"city of richmond", "richmond", "california", "state of california"}
    entities = [e for e in entities if e not in skip_entities]

    # Strip common corporate suffixes for better matching
    # (same pattern as conflict_scanner.py entity normalization)
    import re
    suffix_pattern = re.compile(
        r"\s*,?\s*\b(llc|inc|corp|corporation|company|co|ltd|lp|llp|"
        r"pllc|pc|pa|dba|group|associates|partners)\b\.?\s*$",
        re.IGNORECASE,
    )
    entities = [suffix_pattern.sub("", e).strip() for e in entities]
    entities = [e for e in entities if e]  # Remove any that became empty

    if not entities:
        return []

    matches = []
    for item in agenda_items:
        title = (item.get("title") or "").lower()
        desc = (item.get("description") or "").lower()
        combined = f"{title} {desc}"

        for entity in entities:
            # Check if entity name appears in agenda item
            # Use word boundaries for short names
            if len(entity) < 12:
                words = entity.split()
                if all(w in combined for w in words):
                    matches.append({
                        **item,
                        "match_entity": entity,
                        "match_type": "entity_name",
                    })
                    break
            elif entity in combined:
                matches.append({
                    **item,
                    "match_entity": entity,
                    "match_type": "entity_name",
                })
                break

    return matches


# ── CLI ───────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — NextRequest Document Extractor",
    )
    parser.add_argument("--document", type=str, help="Extract single document")
    parser.add_argument("--batch", type=str, help="Extract all PDFs in directory")
    parser.add_argument("--cross-ref", type=str, help="Cross-reference against meeting JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.document:
        filepath = Path(args.document)
        try:
            import fitz
            doc = fitz.open(str(filepath))
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
        except ImportError:
            text = filepath.read_text()

        result = extract_document(text, filepath.name, filepath.suffix[1:])
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("No extraction result")

    elif args.batch:
        batch_dir = Path(args.batch)
        for filepath in sorted(batch_dir.glob("*.pdf")):
            print(f"\n{'='*50}\n{filepath.name}")
            try:
                import fitz
                doc = fitz.open(str(filepath))
                text = "\n".join(page.get_text() for page in doc)
                doc.close()
                result = extract_document(text, filepath.name, "pdf")
                if result:
                    print(f"  Type: {result.get('document_type')}")
                    print(f"  Summary: {result.get('summary', 'N/A')[:100]}")
            except Exception as e:
                print(f"  Error: {e}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
