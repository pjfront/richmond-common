"""
Vote explainer for council motions (S3.2).

Two generators live here:

1. `generate_vote_explainer()` — the original 3-5 sentence text blob.
   Reads agenda item + motion + votes + (optional) per-category history.
   Returns {"explainer": str, "model": str}.

2. `generate_structured_vote_explainer()` — 5-field structured JSON
   (basics / why_it_matters / the_other_side / decisions / whats_next).
   Reads everything (1) reads PLUS the per-item transcript window (raw
   auto-caption sliced to this item's discussion segment) and public
   comments for the item. The transcript window is the source-closest
   artifact for `the_other_side` — without it, the model has no way to
   know dissent reasoning and falls back to fabricating "departure from
   usual pattern" filler.

Prompts are loaded from src/prompts/ (version-controlled, re-runnable).
Publication tier: Graduated (operator-only until framing validated).
"""

from __future__ import annotations

import json
import re
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
    historical_context: str = "",
    extra_system_instructions: str | None = None,
) -> dict[str, Any]:
    """Generate a contextual vote explanation for a motion.

    Loads prompts from src/prompts/vote_explainer_*.txt.
    Returns dict with 'explainer' and 'model' keys.

    Args:
        historical_context: Pre-formatted text block with per-member voting
            history in the same category. Empty string when insufficient data.

    Raises ImportError if anthropic package is not installed.
    """
    if anthropic is None:
        raise ImportError("anthropic package required for vote explainer generation")

    system_prompt = _load_prompt("vote_explainer_system.txt")
    if extra_system_instructions:
        # Per-run additional rules (e.g. literal-citation discipline for
        # targeted regenerations of motions where the model previously
        # extrapolated). NOT a permanent prompt change — that would be a
        # judgment call per .claude/rules/judgment-boundaries.md.
        system_prompt = system_prompt + "\n\n" + extra_system_instructions.strip()
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
        historical_context=historical_context,
    )

    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        temperature=0,  # Reproducible regeneration; voice belongs in the prompt, not in sampling.
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return {
        "explainer": response.content[0].text,
        "model": response.model,
    }


def _format_council_roster(council: list[dict[str, str]] | None) -> str:
    if not council:
        return "(roster unavailable)"
    return "\n".join(
        f"  - {m['name']}" + (f" ({m.get('role')})" if m.get("role") else "")
        for m in council
    )


def _format_public_comments_block(comments: list[dict[str, Any]] | None) -> str:
    if not comments:
        return "(no public comments recorded for this item)"
    lines = []
    for c in comments[:25]:  # cap to avoid prompt bloat
        speaker = c.get("speaker_name") or "Unnamed speaker"
        body = (c.get("comment_text") or c.get("summary") or "").strip()
        if not body:
            continue
        body = body[:400] + ("..." if len(body) > 400 else "")
        lines.append(f"  - {speaker}: {body}")
    return "\n".join(lines) if lines else "(no comment text available)"


def _format_transcript_window_block(window: dict[str, Any] | None) -> str:
    if not window or not window.get("transcript_text"):
        return (
            "(no transcript window available — the_other_side must be null "
            "unless an unambiguous dissent reason is in the agenda or comments)"
        )
    text = window["transcript_text"]
    # Cap at ~30K chars to keep prompts reasonable. Most discussion windows
    # are under that; the Liftech 76-min window is the upper bound at ~70K
    # and gets truncated. The cap preserves the start (item announcement,
    # staff presentation) and the end (deliberation + roll call).
    if len(text) > 30000:
        head = text[:18000]
        tail = text[-12000:]
        text = head + "\n\n[... transcript truncated for length ...]\n\n" + tail
    return text


def _parse_structured_response(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None


def generate_structured_vote_explainer(
    *,
    item_title: str,
    item_description: str | None = None,
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
    council_roster: list[dict[str, str]] | None = None,
    public_comments: list[dict[str, Any]] | None = None,
    transcript_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a 5-field structured vote explainer.

    Returns a dict with the parsed JSON object under "structured" plus
    "model", "input_tokens", "output_tokens", "approx_cost", and
    "transcript_window_used" (bool) for audit.

    The transcript_window arg is the per-item slice produced by
    `window_meeting_transcript.py` and persisted in
    `data/transcripts/{date}_windows.json`. When None, the_other_side
    will almost always be null (the prompt is explicit about not
    fabricating).
    """
    if anthropic is None:
        raise ImportError("anthropic package required for vote explainer generation")

    system_prompt = _load_prompt("vote_explainer_structured_system.txt")
    user_template = _load_prompt("vote_explainer_structured_user.txt")

    user_prompt = user_template.format(
        council_roster=_format_council_roster(council_roster),
        item_title=item_title,
        category=category or "unknown",
        department=department or "Not specified",
        financial_amount=financial_amount or "None",
        plain_language_summary=plain_language_summary or "(No summary available)",
        item_description=(item_description or "(No description available)").strip(),
        motion_text=motion_text,
        motion_type=motion_type or "original",
        moved_by=moved_by or "Not recorded",
        seconded_by=seconded_by or "Not recorded",
        result=result,
        vote_tally=vote_tally or "Not recorded",
        votes_list=_format_votes_list(votes or []),
        public_comments_block=_format_public_comments_block(public_comments),
        transcript_window_block=_format_transcript_window_block(transcript_window),
    )

    client = anthropic.Anthropic(timeout=120.0)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        # Reproducible regeneration; voice belongs in the prompt, not in
        # sampling. Especially important here: the failure mode this
        # generator is fixing (the "97.9% of contract items"
        # fabrication) is a sampling-driven hallucination class. With
        # temperature=0 the model is forced to commit to the prompt's
        # explicit anti-fabrication rules rather than improvise.
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    parsed = _parse_structured_response(response.content[0].text)
    return {
        "structured": parsed,
        "raw_response": response.content[0].text,
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "approx_cost": (
            response.usage.input_tokens * 3 / 1_000_000
            + response.usage.output_tokens * 15 / 1_000_000
        ),
        "transcript_window_used": bool(transcript_window and transcript_window.get("transcript_text")),
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
