"""
Vote explainer for council motions (S3.2).

Generates 3-5 sentence contextual explanations of city council votes:
what was decided, why it matters, and whether it was contentious.

Prompts are loaded from src/prompts/ (version-controlled, re-runnable).
Publication tier: Graduated (operator-only until framing validated).
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


def _format_votes_list(votes: list[dict[str, str]]) -> str:
    """Format individual votes into a readable list for the prompt.

    Each vote dict has 'official_name' and 'vote_choice'.
    Groups by choice for readability.
    """
    if not votes:
        return "(No individual votes recorded)"

    by_choice: dict[str, list[str]] = {}
    for v in votes:
        choice = v.get("vote_choice", "unknown")
        name = v.get("official_name", "Unknown")
        by_choice.setdefault(choice, []).append(name)

    lines = []
    for choice in ["aye", "nay", "abstain", "absent"]:
        if choice in by_choice:
            names = ", ".join(by_choice[choice])
            lines.append(f"{choice.capitalize()}: {names}")

    return "\n".join(lines)


def generate_vote_explainer(
    *,
    item_title: str,
    category: str | None = None,
    department: str | None = None,
    financial_amount: str | None = None,
    plain_language_summary: str | None = None,
    motion_text: str,
    motion_type: str | None = None,
    moved_by: str | None = None,
    seconded_by: str | None = None,
    result: str,
    vote_tally: str | None = None,
    votes: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Generate a contextual vote explanation for a motion.

    Loads prompts from src/prompts/vote_explainer_*.txt.
    Returns dict with 'explainer' and 'model' keys.

    Raises ImportError if anthropic package is not installed.
    """
    if anthropic is None:
        raise ImportError("anthropic package required for vote explainer generation")

    system_prompt = _load_prompt("vote_explainer_system.txt")
    user_template = _load_prompt("vote_explainer_user.txt")

    votes_list = _format_votes_list(votes or [])

    user_prompt = user_template.format(
        item_title=item_title,
        category=category or "unknown",
        department=department or "Not specified",
        financial_amount=financial_amount or "None",
        plain_language_summary=plain_language_summary or "(No summary available)",
        motion_text=motion_text,
        motion_type=motion_type or "original",
        moved_by=moved_by or "Not recorded",
        seconded_by=seconded_by or "Not recorded",
        result=result,
        vote_tally=vote_tally or "Not recorded",
        votes_list=votes_list,
    )

    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return {
        "explainer": response.content[0].text,
        "model": response.model,
    }


def should_explain(
    *,
    category: str | None,
    is_consent_calendar: bool = False,
    vote_tally: str | None = None,
    votes: list[dict[str, str]] | None = None,
) -> bool:
    """Check if a motion should get a vote explainer.

    Skip rules:
    - Procedural items (roll call, adjournment, etc.)
    - Consent calendar items that passed unanimously (no meaningful vote context)

    Generate for everything else, especially split votes.
    """
    # Always skip procedural
    if category == "procedural":
        return False

    # Skip unanimous consent calendar items
    if is_consent_calendar:
        if _is_unanimous(vote_tally=vote_tally, votes=votes):
            return False

    return True


def _is_unanimous(
    *,
    vote_tally: str | None = None,
    votes: list[dict[str, str]] | None = None,
) -> bool:
    """Check if a vote was unanimous (no nays or abstentions).

    Checks both the tally string and individual votes for robustness.
    """
    # Check tally string (e.g., "7-0", "6-0")
    if vote_tally:
        parts = vote_tally.split("-")
        if len(parts) == 2:
            try:
                nays = int(parts[1].strip())
                if nays == 0:
                    return True
            except ValueError:
                pass

    # Check individual votes
    if votes:
        non_aye = [v for v in votes if v.get("vote_choice") not in ("aye", "absent")]
        return len(non_aye) == 0

    # If we can't determine, default to not unanimous (generate the explainer)
    return False
