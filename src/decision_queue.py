"""
Operator Decision Queue -- Structured decisions requiring human judgment (S7).

Creates, deduplicates, resolves, and queries operator decisions.
Producers (staleness monitor, completeness monitor, self-assessment) create
decisions. The operator resolves them via Claude Code sessions.

Usage:
    from decision_queue import create_decision, resolve_decision, get_pending

    # Producer creates a decision
    create_decision(conn, city_fips="0660620",
        decision_type="staleness_alert",
        severity="medium",
        title="NetFile data is 21 days stale",
        description="Last sync 21 days ago, threshold is 14 days.",
        source="staleness_monitor",
        dedup_key="staleness:netfile",
        link="https://rtp-gray.vercel.app/data-quality",
    )

    # Operator resolves it
    resolve_decision(conn, decision_id, verdict="approved",
        note="Triggered manual sync")

    # CLI briefing queries pending decisions
    briefing = get_decision_briefing(conn, city_fips="0660620")
    print(briefing)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import (
    count_decisions_by_severity,
    insert_pending_decision,
    query_pending_decisions,
    query_resolved_decisions,
    update_decision_status,
)

VALID_TYPES = {
    "staleness_alert",
    "anomaly",
    "tier_graduation",
    "conflict_review",
    "assessment_finding",
    "pipeline_failure",
    "general",
}

VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}

VALID_VERDICTS = {"approved", "rejected", "deferred"}

SEVERITY_ICONS = {
    "critical": "!!!",
    "high": "!!",
    "medium": "!",
    "low": ".",
    "info": " ",
}


# ── Create / Resolve ───────────────────────────────────────


def create_decision(
    conn,
    city_fips: str,
    decision_type: str,
    severity: str,
    title: str,
    description: str,
    source: str,
    evidence: dict = None,
    entity_type: str = None,
    entity_id: str = None,
    link: str = None,
    dedup_key: str = None,
) -> Optional[uuid.UUID]:
    """Create a pending decision. Returns UUID, or None if deduplicated.

    If a pending decision with the same dedup_key already exists,
    returns None without creating a duplicate.
    """
    if decision_type not in VALID_TYPES:
        raise ValueError(
            f"Invalid decision_type '{decision_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_TYPES))}"
        )
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. "
            f"Must be one of: {', '.join(sorted(VALID_SEVERITIES))}"
        )

    return insert_pending_decision(
        conn,
        city_fips=city_fips,
        decision_type=decision_type,
        severity=severity,
        title=title,
        description=description,
        source=source,
        evidence=evidence,
        entity_type=entity_type,
        entity_id=entity_id,
        link=link,
        dedup_key=dedup_key,
    )


def resolve_decision(
    conn,
    decision_id: str | uuid.UUID,
    verdict: str,
    resolved_by: str = "operator",
    note: str = None,
) -> bool:
    """Resolve a pending decision. Returns True if updated.

    verdict must be one of: approved, rejected, deferred.
    """
    if verdict not in VALID_VERDICTS:
        raise ValueError(
            f"Invalid verdict '{verdict}'. "
            f"Must be one of: {', '.join(sorted(VALID_VERDICTS))}"
        )

    if isinstance(decision_id, str):
        decision_id = uuid.UUID(decision_id)

    return update_decision_status(
        conn,
        decision_id=decision_id,
        status=verdict,
        resolved_by=resolved_by,
        resolution_note=note,
    )


# ── Query ──────────────────────────────────────────────────


def get_pending(
    conn,
    city_fips: str,
    decision_type: str = None,
    severity: str = None,
) -> list[dict]:
    """Get pending decisions, ordered by severity then age."""
    return query_pending_decisions(
        conn, city_fips,
        decision_type=decision_type,
        severity=severity,
    )


def get_recently_resolved(
    conn,
    city_fips: str,
    days: int = 7,
    limit: int = 20,
) -> list[dict]:
    """Get recently resolved decisions."""
    return query_resolved_decisions(conn, city_fips, days=days, limit=limit)


def get_decision_summary(
    conn,
    city_fips: str,
) -> dict[str, Any]:
    """Summary counts for the briefing header."""
    counts = count_decisions_by_severity(conn, city_fips)
    total = sum(counts.values())
    return {
        "total_pending": total,
        "counts": counts,
    }


# ── Briefing Formatter ─────────────────────────────────────


def _format_age(created_at: datetime | str) -> str:
    """Human-readable age string."""
    if isinstance(created_at, str):
        # Handle ISO format strings from DB
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return "unknown age"

    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    delta = now - created_at
    days = delta.days
    hours = delta.seconds // 3600

    if days > 1:
        return f"{days} days ago"
    elif days == 1:
        return "1 day ago"
    elif hours > 1:
        return f"{hours} hours ago"
    elif hours == 1:
        return "1 hour ago"
    else:
        return "just now"


def get_decision_briefing(
    conn,
    city_fips: str,
    include_resolved: bool = False,
) -> str:
    """Format pending decisions as a readable briefing.

    Designed for Claude Code to present to the operator at session start.
    """
    summary = get_decision_summary(conn, city_fips)
    decisions = get_pending(conn, city_fips)

    if summary["total_pending"] == 0:
        return (
            "=" * 60 + "\n"
            "  Operator Decision Queue\n"
            "  No pending decisions.\n"
            "=" * 60
        )

    # Build count summary
    count_parts = []
    for sev in ["critical", "high", "medium", "low", "info"]:
        cnt = summary["counts"].get(sev, 0)
        if cnt > 0:
            count_parts.append(f"{cnt} {sev}")

    lines = [
        "",
        "=" * 60,
        f"  Operator Decision Queue",
        f"  Pending: {summary['total_pending']} ({', '.join(count_parts)})",
        "=" * 60,
    ]

    # Group by severity
    current_severity = None
    item_num = 0
    for d in decisions:
        sev = d["severity"]
        if sev != current_severity:
            current_severity = sev
            lines.append("")
            sev_count = summary["counts"].get(sev, 0)
            lines.append(f"  {sev.upper()} ({sev_count})")
            lines.append("  " + "-" * 56)

        item_num += 1
        icon = SEVERITY_ICONS.get(sev, " ")
        age = _format_age(d["created_at"])
        decision_id = d["id"]
        if isinstance(decision_id, str) and len(decision_id) > 8:
            short_id = decision_id[:8]
        else:
            short_id = str(decision_id)

        lines.append(f"  {item_num}. [{icon}] {d['title']} [{d['decision_type']}]")
        lines.append(f"     Source: {d['source']} | Age: {age}")

        desc = d.get("description", "")
        if len(desc) > 120:
            desc = desc[:117] + "..."
        lines.append(f"     {desc}")

        if d.get("link"):
            lines.append(f"     Link: {d['link']}")

        lines.append(f"     ID: {short_id}")

    if include_resolved:
        resolved = get_recently_resolved(conn, city_fips)
        if resolved:
            lines.append("")
            lines.append(f"  RECENTLY RESOLVED ({len(resolved)})")
            lines.append("  " + "-" * 56)
            for r in resolved:
                age = _format_age(r.get("resolved_at") or r["created_at"])
                verdict = r.get("status", "?").upper()
                lines.append(
                    f"  [{verdict}] {r['title']} | {age}"
                )
                if r.get("resolution_note"):
                    lines.append(f"     Note: {r['resolution_note']}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    return "\n".join(lines)
