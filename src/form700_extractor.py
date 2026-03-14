"""
Richmond Common — Form 700 Extractor

Extracts structured financial disclosure data from Form 700 PDF text
using Claude API's tool_use for guaranteed schema compliance.

Pipeline:
  1. PDF bytes → text (PyMuPDF via pipeline.extract_text_from_document)
  2. Text → Claude API → structured JSON (this module)
  3. JSON → database (load_form700_to_db in db.py)

Usage:
    from form700_extractor import extract_form700, match_filer_to_official

    result = extract_form700(pdf_text, filer_name="Eduardo Martinez",
                             agency="City of Richmond", filing_year=2024,
                             statement_type="annual")

CLI:
    python form700_extractor.py --pdf data/form700/sample.pdf
    python form700_extractor.py --text "Cover Page: ..."
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)


# ── Extraction Schema ──────────────────────────────────────────

FORM700_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "filer_name", "filer_agency", "filer_position",
        "statement_type", "period_start", "period_end",
        "no_interests_declared", "interests",
        "extraction_confidence", "extraction_notes",
    ],
    "properties": {
        "filer_name": {
            "type": "string",
            "description": "Full name of the filer as printed on the Cover Page",
        },
        "filer_agency": {
            "type": "string",
            "description": "Agency name (e.g., 'City of Richmond')",
        },
        "filer_position": {
            "type": "string",
            "description": "Position/title (e.g., 'Council Member', 'City Manager')",
        },
        "statement_type": {
            "type": "string",
            "enum": ["annual", "assuming_office", "leaving_office", "candidate", "amendment"],
            "description": "Type of filing statement",
        },
        "period_start": {
            "type": ["string", "null"],
            "description": "Filing period start date (YYYY-MM-DD or null if not found)",
        },
        "period_end": {
            "type": ["string", "null"],
            "description": "Filing period end date (YYYY-MM-DD or null if not found)",
        },
        "no_interests_declared": {
            "type": "boolean",
            "description": "True if filer checked 'No reportable interests on any schedule'",
        },
        "interests": {
            "type": "array",
            "description": "All disclosed interests across all schedules",
            "items": {
                "type": "object",
                "required": ["schedule", "interest_type", "description"],
                "properties": {
                    "schedule": {
                        "type": "string",
                        "enum": ["A-1", "A-2", "B", "C", "D", "E"],
                        "description": "Schedule section (A-1 investments, A-2 business entities, B real property, C income, D gifts, E travel)",
                    },
                    "interest_type": {
                        "type": "string",
                        "enum": [
                            "investment", "business_entity", "real_property",
                            "income", "business_position", "gift", "travel",
                        ],
                        "description": "Type of interest",
                    },
                    "description": {
                        "type": "string",
                        "description": "Name of entity, property address, income source, etc.",
                    },
                    "value_range": {
                        "type": ["string", "null"],
                        "description": "Value range as printed (e.g., '$2,000 - $10,000')",
                    },
                    "income_amount": {
                        "type": ["string", "null"],
                        "description": "Income amount or range for Schedule C entries",
                    },
                    "income_type": {
                        "type": ["string", "null"],
                        "description": "Type of income (salary, commission, rental, etc.)",
                    },
                    "business_activity": {
                        "type": ["string", "null"],
                        "description": "General description of business activity",
                    },
                    "business_position": {
                        "type": ["string", "null"],
                        "description": "Position held in the business entity (e.g., 'Director', 'Owner')",
                    },
                    "location": {
                        "type": ["string", "null"],
                        "description": "Address or APN for real property (Schedule B)",
                    },
                    "gift_source": {
                        "type": ["string", "null"],
                        "description": "Who gave the gift (Schedule D)",
                    },
                    "gift_description": {
                        "type": ["string", "null"],
                        "description": "What the gift was (Schedule D)",
                    },
                    "gift_value": {
                        "type": ["number", "null"],
                        "description": "Dollar value of the gift (Schedule D)",
                    },
                    "travel_destination": {
                        "type": ["string", "null"],
                        "description": "Travel destination (Schedule E)",
                    },
                    "travel_dates": {
                        "type": ["string", "null"],
                        "description": "Travel dates (Schedule E)",
                    },
                    "travel_payer": {
                        "type": ["string", "null"],
                        "description": "Who paid for travel (Schedule E)",
                    },
                    "nature_of_interest": {
                        "type": ["string", "null"],
                        "description": "Nature of investment interest (e.g., 'stock', 'partnership', 'sole proprietorship')",
                    },
                    "acquired_or_disposed": {
                        "type": ["string", "null"],
                        "description": "'acquired', 'disposed', or null if held throughout",
                    },
                },
            },
        },
        "extraction_confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence score for extraction quality (0.0 to 1.0)",
        },
        "extraction_notes": {
            "type": "string",
            "description": "Notes about extraction quality, garbled text, or issues encountered",
        },
    },
}


# ── Prompt Loading ─────────────────────────────────────────────

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text().strip()


def _get_system_prompt() -> str:
    """Load the Form 700 extraction system prompt."""
    return _load_prompt("form700_extraction_system.txt")


def _get_user_prompt(
    pdf_text: str,
    filer_name: str = "",
    agency: str = "",
    filing_year: int = 0,
    statement_type: str = "",
) -> str:
    """Build the user prompt from template + PDF text."""
    template = _load_prompt("form700_extraction_user.txt")
    return template.format(
        filer_name=filer_name or "Unknown",
        agency=agency or "Unknown",
        filing_year=filing_year or "Unknown",
        statement_type=statement_type or "Unknown",
        pdf_text=pdf_text[:120000],  # ~30K tokens, well within context window
    )


# ── Claude API Extraction ─────────────────────────────────────

def extract_form700(
    pdf_text: str,
    filer_name: str = "",
    agency: str = "",
    filing_year: int = 0,
    statement_type: str = "",
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """Extract structured Form 700 data from PDF text using Claude API.

    Uses tool_use for guaranteed schema compliance. One API call per filing.

    Args:
        pdf_text: Extracted text from Form 700 PDF.
        filer_name: Expected filer name (hint from scraper metadata).
        agency: Expected agency name.
        filing_year: Expected filing year.
        statement_type: Expected statement type.
        model: Claude model to use.

    Returns:
        Dict matching FORM700_EXTRACTION_SCHEMA with all extracted interests.
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment")

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = _get_system_prompt()
    user_prompt = _get_user_prompt(
        pdf_text, filer_name, agency, filing_year, statement_type
    )

    tool_definition = {
        "name": "save_form700_data",
        "description": "Save the extracted Form 700 financial disclosure data",
        "input_schema": FORM700_EXTRACTION_SCHEMA,
    }

    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=system_prompt,
        tools=[tool_definition],
        tool_choice={"type": "tool", "name": "save_form700_data"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract structured data from tool_use response
    for block in response.content:
        if block.type == "tool_use":
            result = block.input
            # Attach API usage metadata
            result["_extraction_metadata"] = {
                "model": model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            return result

    raise ValueError("No tool_use block in Claude API response")


# ── PDF Text Extraction ────────────────────────────────────────

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a Form 700 PDF using PyMuPDF.

    Detects Type3 fonts (image-based PDFs) and warns about potential
    garbled text. Form 700s filed through NetFile/FPPC since 2018 are
    generated PDFs with clean, extractable text.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    text_parts = []
    has_type3 = False

    for page in doc:
        fonts = page.get_fonts()
        if any(f[2] == "Type3" for f in fonts):
            has_type3 = True
            logger.warning(
                "Page %d uses Type3 fonts (image-based). Text may be garbled.",
                page.number + 1,
            )
        text_parts.append(page.get_text())

    doc.close()
    text = "\n".join(text_parts)

    if has_type3:
        logger.warning(
            "Type3 fonts detected in %s. Consider OCR for better extraction.",
            pdf_path.name,
        )

    return text


# ── Filer-to-Official Matching ─────────────────────────────────

def match_filer_to_official(
    filer_name: str,
    city_fips: str = "0660620",
    threshold: float = 0.85,
) -> dict[str, Any]:
    """Match a Form 700 filer name to a known official.

    Uses the same three-step strategy as db.ensure_official():
      1. Exact match on normalized name
      2. Alias match from officials.json
      3. Fuzzy match (SequenceMatcher)

    Returns:
        Dict with keys: matched (bool), canonical_name (str or None),
        match_type (str), confidence (float), category (str or None).
    """
    gt_path = Path(__file__).parent / "ground_truth" / "officials.json"
    if not gt_path.exists():
        return {
            "matched": False,
            "canonical_name": None,
            "match_type": "no_ground_truth",
            "confidence": 0.0,
            "category": None,
        }

    data = json.loads(gt_path.read_text())
    if data.get("city_fips") != city_fips:
        return {
            "matched": False,
            "canonical_name": None,
            "match_type": "wrong_city",
            "confidence": 0.0,
            "category": None,
        }

    normalized_filer = _normalize_name(filer_name)

    # Build lookup structures
    all_officials: list[tuple[str, str, str]] = []  # (normalized, canonical, category)
    alias_map: dict[str, tuple[str, str]] = {}  # normalized_alias -> (canonical, category)

    for category in ("current_council_members", "former_council_members", "city_leadership"):
        for official in data.get(category, []):
            canonical = official.get("name", "")
            norm = _normalize_name(canonical)
            all_officials.append((norm, canonical, category))
            for alias in official.get("aliases", []):
                alias_map[_normalize_name(alias)] = (canonical, category)

    # 1. Exact match
    for norm, canonical, category in all_officials:
        if norm == normalized_filer:
            return {
                "matched": True,
                "canonical_name": canonical,
                "match_type": "exact",
                "confidence": 1.0,
                "category": category,
            }

    # 2. Alias match
    if normalized_filer in alias_map:
        canonical, category = alias_map[normalized_filer]
        return {
            "matched": True,
            "canonical_name": canonical,
            "match_type": "alias",
            "confidence": 0.95,
            "category": category,
        }

    # 3. Fuzzy match
    best_score = 0.0
    best_canonical = None
    best_category = None
    for norm, canonical, category in all_officials:
        score = SequenceMatcher(None, normalized_filer, norm).ratio()
        if score > best_score:
            best_score = score
            best_canonical = canonical
            best_category = category

    if best_score >= threshold:
        return {
            "matched": True,
            "canonical_name": best_canonical,
            "match_type": "fuzzy",
            "confidence": round(best_score, 3),
            "category": best_category,
        }

    return {
        "matched": False,
        "canonical_name": None,
        "match_type": "no_match",
        "confidence": round(best_score, 3),
        "category": None,
    }


def _normalize_name(name: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return " ".join(name.lower().split())


# ── Interest Flattening for Conflict Scanner ───────────────────

def flatten_interests_for_scanner(
    extraction_result: dict[str, Any],
    filer_name: str,
    filing_year: int,
    source_url: str = "",
) -> list[dict[str, Any]]:
    """Convert extraction result into the format the conflict scanner expects.

    The conflict scanner's scan_meeting_json() expects form700_interests
    as a list of dicts with keys:
        council_member, interest_type, description, location,
        filing_year, source_url

    This bridges the extraction schema to the scanner contract.
    """
    interests = []
    for item in extraction_result.get("interests", []):
        interest_type = item.get("interest_type", "")

        # Map extraction interest_type to scanner's expected types
        type_map = {
            "investment": "investment",
            "business_entity": "investment",
            "real_property": "real_property",
            "income": "income",
            "business_position": "income",
            "gift": "gift",
            "travel": "travel",
        }
        scanner_type = type_map.get(interest_type, interest_type)

        interests.append({
            "council_member": filer_name,
            "interest_type": scanner_type,
            "description": item.get("description", ""),
            "location": item.get("location", ""),
            "filing_year": filing_year,
            "source_url": source_url,
            "schedule": item.get("schedule", ""),
            "value_range": item.get("value_range", ""),
        })

    return interests


# ── Batch Processing ──────────────────────────────────────────

def process_filing(
    pdf_path: Path,
    filer_name: str = "",
    agency: str = "",
    filing_year: int = 0,
    statement_type: str = "",
    city_fips: str = "0660620",
) -> dict[str, Any]:
    """End-to-end processing of a single Form 700 filing.

    1. Extract text from PDF
    2. Call Claude API for structured extraction
    3. Match filer to known official
    4. Return combined result

    Args:
        pdf_path: Path to Form 700 PDF file.
        filer_name: Filer name from scraper metadata (hint).
        agency: Agency name from scraper metadata.
        filing_year: Filing year from scraper metadata.
        statement_type: Statement type from scraper metadata.
        city_fips: FIPS code for the city.

    Returns:
        Dict with extraction result, official match, and scanner-ready interests.
    """
    # 1. PDF to text
    pdf_text = extract_text_from_pdf(pdf_path)
    if not pdf_text.strip():
        return {
            "extraction": None,
            "official_match": None,
            "scanner_interests": [],
            "error": "Empty PDF text. File may be image-based or corrupt.",
        }

    # 2. Claude API extraction
    extraction = extract_form700(
        pdf_text,
        filer_name=filer_name,
        agency=agency,
        filing_year=filing_year,
        statement_type=statement_type,
    )

    # Use extracted filer name (from PDF) if available, fall back to metadata
    resolved_name = extraction.get("filer_name") or filer_name

    # 3. Match to official
    match_result = match_filer_to_official(resolved_name, city_fips)

    # 4. Build scanner-ready interests
    scanner_interests = flatten_interests_for_scanner(
        extraction,
        filer_name=match_result.get("canonical_name") or resolved_name,
        filing_year=extraction.get("period_end", "")[:4] if extraction.get("period_end") else filing_year,
        source_url="",
    )

    return {
        "extraction": extraction,
        "official_match": match_result,
        "scanner_interests": scanner_interests,
        "pdf_path": str(pdf_path),
    }


# ── CLI ────────────────────────────────────────────────────────

def main():
    """CLI entry point for Form 700 extraction."""
    parser = argparse.ArgumentParser(
        description="Extract structured data from Form 700 PDFs"
    )
    parser.add_argument("--pdf", type=Path, help="Path to Form 700 PDF file")
    parser.add_argument("--text", help="Raw PDF text (alternative to --pdf)")
    parser.add_argument("--filer-name", default="", help="Expected filer name")
    parser.add_argument("--agency", default="", help="Expected agency")
    parser.add_argument("--filing-year", type=int, default=0, help="Expected filing year")
    parser.add_argument("--statement-type", default="", help="Expected statement type")
    parser.add_argument("--city-fips", default="0660620", help="City FIPS code")
    parser.add_argument("--output", type=Path, help="Save JSON output to file")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.pdf:
        result = process_filing(
            args.pdf,
            filer_name=args.filer_name,
            agency=args.agency,
            filing_year=args.filing_year,
            statement_type=args.statement_type,
            city_fips=args.city_fips,
        )
    elif args.text:
        result = {
            "extraction": extract_form700(
                args.text,
                filer_name=args.filer_name,
                agency=args.agency,
                filing_year=args.filing_year,
                statement_type=args.statement_type,
            ),
            "official_match": match_filer_to_official(args.filer_name, args.city_fips)
            if args.filer_name
            else None,
        }
    else:
        parser.error("Either --pdf or --text is required")
        return

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str))
        print(f"Saved extraction to {args.output}")
    else:
        print(json.dumps(result, indent=2, default=str))

    # Summary
    if result.get("extraction"):
        ext = result["extraction"]
        n_interests = len(ext.get("interests", []))
        confidence = ext.get("extraction_confidence", 0)
        print(f"\n--- Summary ---")
        print(f"Filer: {ext.get('filer_name', 'N/A')}")
        print(f"Agency: {ext.get('filer_agency', 'N/A')}")
        print(f"Position: {ext.get('filer_position', 'N/A')}")
        print(f"Period: {ext.get('period_start', '?')} to {ext.get('period_end', '?')}")
        print(f"No interests declared: {ext.get('no_interests_declared', False)}")
        print(f"Interests extracted: {n_interests}")
        print(f"Confidence: {confidence:.2f}")

        if result.get("official_match"):
            match = result["official_match"]
            if match["matched"]:
                print(f"Official match: {match['canonical_name']} ({match['match_type']}, {match['confidence']:.3f})")
            else:
                print(f"Official match: None ({match['match_type']}, best similarity: {match['confidence']:.3f})")


if __name__ == "__main__":
    main()
