"""
Bio generator for council member profiles.

Two-layer structure:
- Layer 1 (Factual): Pure data aggregation from database queries. No AI inference.
- Layer 2 (Summary): AI-synthesized narrative with mandatory transparency disclosure.

Publication tiers:
- Layer 1: Public (factual, no judgment)
- Layer 2: Graduated (operator reviews before public exposure)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]


BIO_CONSTRAINTS = """Constraints on the summary:
- State what the data shows. Do not interpret why.
- Do not characterize political orientation or ideology.
- Do not compare members to each other.
- Do not use value-laden language (good/bad, strong/weak, effective/ineffective).
- Do not mention vote category percentages or distributions. Council members do not control what comes to a vote.
- Write in third person.
- Keep to 2-3 sentences maximum.
- Focus on attendance, voting alignment, and notable dissents."""


def build_factual_profile(
    *,
    official_name: str,
    official_role: str,
    official_seat: str | None,
    term_start: str | None,
    term_end: str | None,
    vote_count: int,
    meetings_attended: int,
    meetings_total: int,
    majority_alignment_rate: float,
    sole_dissent_count: int,
    sole_dissent_categories: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build Layer 1 factual profile from database query results.

    No AI inference. No editorial judgment. Pure data aggregation.
    Note: top_categories removed (council members don't control what
    comes to a vote, so category percentages are misleading).
    """
    attendance_rate = (
        round(meetings_attended / meetings_total * 100)
        if meetings_total > 0
        else 0
    )

    return {
        "name": official_name,
        "role": official_role,
        "seat": official_seat,
        "term_start": term_start,
        "term_end": term_end,
        "vote_count": vote_count,
        "attendance_rate": f"{attendance_rate}%",
        "attendance_fraction": f"{meetings_attended} of {meetings_total}",
        "majority_alignment_rate": f"{round(majority_alignment_rate * 100)}%",
        "sole_dissent_count": sole_dissent_count,
        "sole_dissent_categories": sole_dissent_categories,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def generate_bio_summary(factual_profile: dict[str, Any]) -> dict[str, Any]:
    """Generate Layer 2 AI-synthesized narrative from factual data.

    Requires ANTHROPIC_API_KEY in environment.
    Returns dict with 'summary' and 'model' keys.
    """
    if anthropic is None:
        raise ImportError("anthropic package required for bio generation")

    client = anthropic.Anthropic()

    name = factual_profile["name"]
    sole_dissent_detail = ""
    sole_cats = factual_profile.get("sole_dissent_categories", [])
    if sole_cats:
        sole_dissent_detail = f" (topics: {', '.join(c['category'] for c in sole_cats)})"

    prompt = f"""Based on the following factual voting record data, write a brief summary paragraph (2-3 sentences) about this council member's participation.

Factual data:
- Name: {name}
- Role: {factual_profile.get("role", "councilmember")}
- Votes cast: {factual_profile["vote_count"]}
- Attendance: {factual_profile["attendance_fraction"]} meetings ({factual_profile["attendance_rate"]})
- Voted with majority: {factual_profile["majority_alignment_rate"]}
- Sole dissenting vote: {factual_profile["sole_dissent_count"]} times{sole_dissent_detail}

{BIO_CONSTRAINTS}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "summary": response.content[0].text,
        "model": response.model,
    }
