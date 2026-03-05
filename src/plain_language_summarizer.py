"""
Plain language summarizer for agenda items.

Generates 2-3 sentence plain English explanations of city council agenda items
so any resident can understand what their government is doing.

Prompts are loaded from src/prompts/ (version-controlled, re-runnable).
Publication tier: Graduated (operator-only until pilot validation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text().strip()


def generate_plain_language_summary(
    *,
    title: str,
    description: str | None = None,
    category: str | None = None,
    department: str | None = None,
    financial_amount: str | None = None,
) -> dict[str, Any]:
    """Generate a plain language summary for an agenda item.

    Loads prompts from src/prompts/plain_language_*.txt.
    Returns dict with 'summary' and 'model' keys.

    Raises ImportError if anthropic package is not installed.
    """
    if anthropic is None:
        raise ImportError("anthropic package required for summary generation")

    system_prompt = _load_prompt("plain_language_system.txt")
    user_template = _load_prompt("plain_language_user.txt")

    user_prompt = user_template.format(
        title=title,
        description=description or "(No description provided)",
        category=category or "unknown",
        department=department or "Not specified",
        financial_amount=financial_amount or "None",
    )

    client = anthropic.Anthropic(timeout=60.0)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return {
        "summary": response.content[0].text,
        "model": response.model,
    }


def should_summarize(category: str | None) -> bool:
    """Check if an agenda item should get a plain language summary.

    Procedural items (roll call, adjournment, etc.) don't need explanation.
    """
    return category != "procedural"
