"""
Plain language summarizer for agenda items.

Generates plain English explanations of city council agenda items
so any resident can understand what their government is doing.

Produces two outputs per item:
- summary: 2-4 sentence explanation (max 75 words) with yes/no vote structure
- headline: single sentence (~15-20 words) for compact card display

Prompts are loaded from src/prompts/ (version-controlled, re-runnable).
Publication tier: Public (graduated from operator-only after S3.1 pilot).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text().strip()


def _parse_response(text: str) -> dict[str, str | None]:
    """Parse JSON response with summary and headline fields.

    Falls back gracefully: if JSON parsing fails, treat the entire
    response as the summary with no headline (never lose data).
    """
    text = text.strip()

    # Strip markdown code fences if the model wraps the JSON
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[: -3].strip()

    try:
        data = json.loads(text)
        return {
            "summary": (data.get("summary") or "").strip() or None,
            "headline": (data.get("headline") or "").strip() or None,
        }
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Failed to parse JSON response, falling back to plain text")
        return {
            "summary": text.strip() or None,
            "headline": None,
        }


def generate_plain_language_summary(
    *,
    title: str,
    description: str | None = None,
    category: str | None = None,
    department: str | None = None,
    financial_amount: str | None = None,
    staff_report: str | None = None,
) -> dict[str, Any]:
    """Generate a plain language summary and headline for an agenda item.

    Loads prompts from src/prompts/plain_language_*.txt.
    Returns dict with 'summary', 'headline', and 'model' keys.

    Args:
        staff_report: Extracted text from staff report attachment(s).
            Truncated to first 4000 chars to stay within token budget.

    Raises ImportError if anthropic package is not installed.
    """
    if anthropic is None:
        raise ImportError("anthropic package required for summary generation")

    system_prompt = _load_prompt("plain_language_system.txt")
    user_template = _load_prompt("plain_language_user.txt")

    # Truncate staff report to keep token budget reasonable
    report_text = "(No staff report available)"
    if staff_report and len(staff_report.strip()) > 50:
        report_text = staff_report.strip()[:4000]

    user_prompt = user_template.format(
        title=title,
        description=description or "(No description provided)",
        category=category or "unknown",
        department=department or "Not specified",
        financial_amount=financial_amount or "None",
        staff_report=report_text,
    )

    client = anthropic.Anthropic(timeout=60.0)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    parsed = _parse_response(response.content[0].text)

    return {
        "summary": parsed["summary"],
        "headline": parsed["headline"],
        "model": response.model,
    }


def should_summarize(category: str | None) -> bool:
    """Check if an agenda item should get a plain language summary.

    Procedural items (roll call, adjournment, etc.) don't need explanation.
    """
    return category != "procedural"
