"""
Plain language summarizer for agenda items.

Generates plain English explanations of city council agenda items
so any resident can understand what their government is doing.

Produces three outputs per item:
- summary: 2-4 sentence explanation (max 75 words) with yes/no vote structure
- headline: single sentence (~15-20 words) for compact card display
- topic_label: 1-4 word specific subject (e.g. "Point Molate", "SEIU MOU")

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
        topic_raw = (data.get("topic_label") or "").strip() or None
        return {
            "summary": (data.get("summary") or "").strip() or None,
            "headline": (data.get("headline") or "").strip() or None,
            "topic_label": topic_raw[:50] if topic_raw else None,
        }
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Failed to parse JSON response, falling back to plain text")
        return {
            "summary": text.strip() or None,
            "headline": None,
            "topic_label": None,
        }


def generate_plain_language_summary(
    *,
    title: str,
    description: str | None = None,
    category: str | None = None,
    department: str | None = None,
    financial_amount: str | None = None,
    staff_report: str | None = None,
    topic_seed_prompt: str = "",
) -> dict[str, Any]:
    """Generate a plain language summary and headline for an agenda item.

    Loads prompts from src/prompts/plain_language_*.txt.
    Returns dict with 'summary', 'headline', 'topic_label', and 'model' keys.

    Args:
        staff_report: Extracted text from staff report attachment(s).
            Truncated to first 4000 chars to stay within token budget.
        topic_seed_prompt: Pre-formatted seed list appended to system prompt
            for topic label consistency. Generate with format_topic_seed_prompt().

    Raises ImportError if anthropic package is not installed.
    """
    if anthropic is None:
        raise ImportError("anthropic package required for summary generation")

    system_prompt = _load_prompt("plain_language_system.txt") + topic_seed_prompt
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
        "topic_label": parsed["topic_label"],
        "model": response.model,
    }


def should_summarize(category: str | None) -> bool:
    """Check if an agenda item should get a plain language summary.

    Procedural items (roll call, adjournment, etc.) don't need explanation.
    """
    return category != "procedural"


# ── Pre-summarization consistency gate ─────────────────────────────────────


def validate_item_for_summarization(
    item: dict,
    siblings: list[dict] | None = None,
) -> list[str]:
    """Lightweight pre-flight check before sending an item to the LLM.

    Returns a list of warning strings. Empty list = item is clean.
    Warnings are informational — callers decide whether to skip or proceed.

    Checks:
    1. Financial amount sanity: does the extracted amount appear in the text?
    2. Near-duplicate detection: is this item >80% word overlap with a sibling?
    """
    warnings: list[str] = []
    title = (item.get("title") or "").strip()
    desc = (item.get("description") or "").strip()
    text = f"{title} {desc}"

    # ── Check 1: financial_amount should appear in the item's own text ──
    amount = item.get("financial_amount")
    if amount:
        # Normalize both sides: strip $ and commas for comparison
        raw = amount.replace(",", "").replace("$", "")
        if raw and raw not in text.replace(",", ""):
            warnings.append(
                f"financial_amount {amount} not found in item text"
            )

    # ── Check 2: near-duplicate detection against siblings ──
    if siblings and desc and len(desc.split()) > 10:
        desc_words = set(desc.lower().split())
        item_num = item.get("item_number", "")
        for sib in siblings:
            if sib.get("item_number") == item_num:
                continue  # Skip self
            sib_desc = (sib.get("description") or "").strip()
            if not sib_desc or len(sib_desc.split()) < 10:
                continue
            sib_words = set(sib_desc.lower().split())
            overlap = len(desc_words & sib_words)
            smaller = min(len(desc_words), len(sib_words))
            if smaller > 0 and overlap / smaller > 0.8:
                warnings.append(
                    f"near-duplicate of item {sib.get('item_number', '?')} "
                    f"({overlap}/{smaller} words overlap)"
                )

    return warnings
