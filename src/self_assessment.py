"""
Self-Assessment — Pipeline health reports (Autonomy Zones Phase A).

Reads recent pipeline journal entries, sends them to Claude Sonnet for
structured health assessment, and stores the result as a journal entry.

Usage:
    python self_assessment.py --days 7
    python self_assessment.py --days 1 --city-fips 0660620
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from db import get_connection, get_journal_entries
from pipeline_journal import PipelineJournal

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text().strip()


# ── Context Builder ─────────────────────────────────────────


def build_assessment_context(
    conn,
    city_fips: str,
    days: int = 7,
) -> dict[str, Any]:
    """Gather journal entries and compute summary stats for the assessment.

    Returns a dict with raw entries and computed metrics that feed
    into the LLM prompt.
    """
    entries = get_journal_entries(conn, city_fips, days=days)

    # Compute summary stats
    run_starts = [e for e in entries if e["entry_type"] == "run_started"]
    run_completions = [e for e in entries if e["entry_type"] == "run_completed"]
    run_failures = [e for e in entries if e["entry_type"] == "run_failed"]
    anomalies = [e for e in entries if e["entry_type"] == "anomaly_detected"]
    steps = [e for e in entries if e["entry_type"] in ("step_completed", "step_failed")]

    return {
        "entries": entries,
        "total_runs": len(run_starts),
        "completed_runs": len(run_completions),
        "failed_runs": len(run_failures),
        "anomaly_count": len(anomalies),
        "step_count": len(steps),
        "days": days,
        "city_fips": city_fips,
    }


def _format_entries_for_prompt(entries: list[dict]) -> str:
    """Format journal entries as readable text for the LLM prompt."""
    if not entries:
        return "(No journal entries found in this period.)"

    lines = []
    for entry in entries:
        ts = entry.get("created_at", "")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        line = f"[{ts}] {entry['entry_type']}"
        if entry.get("target_artifact"):
            line += f" | {entry['target_artifact']}"
        line += f" | {entry['description']}"
        if entry.get("metrics"):
            # Compact JSON for metrics
            metrics_str = json.dumps(entry["metrics"], default=str)
            if len(metrics_str) > 200:
                metrics_str = metrics_str[:200] + "..."
            line += f" | metrics: {metrics_str}"
        lines.append(line)

    return "\n".join(lines)


# ── Assessment Runner ───────────────────────────────────────


def run_self_assessment(
    conn,
    city_fips: str,
    days: int = 7,
) -> dict[str, Any]:
    """Run a self-assessment of pipeline health.

    Gathers recent journal entries, sends them to Claude Sonnet,
    parses the structured response, and stores it in the journal.

    Returns the assessment dict.
    """
    if anthropic is None:
        raise ImportError("anthropic package required for self-assessment")

    context = build_assessment_context(conn, city_fips, days=days)

    # Build the prompt
    system_prompt = _load_prompt("self_assessment_system.txt")
    user_template = _load_prompt("self_assessment_user.txt")

    entries_text = _format_entries_for_prompt(context["entries"])
    user_prompt = user_template.format(
        days=context["days"],
        journal_entries=entries_text,
        total_runs=context["total_runs"],
        completed_runs=context["completed_runs"],
        failed_runs=context["failed_runs"],
        anomaly_count=context["anomaly_count"],
    )

    # Call Claude Sonnet
    client = anthropic.Anthropic(timeout=60.0)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()
    token_usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    # Parse JSON response
    try:
        assessment = json.loads(raw_text)
    except json.JSONDecodeError:
        assessment = {
            "overall_health": "unknown",
            "summary": f"Failed to parse assessment response: {raw_text[:200]}",
            "findings": [],
            "metrics": {
                "runs_analyzed": context["total_runs"],
                "steps_completed": context["step_count"],
                "steps_failed": 0,
                "anomalies_detected": context["anomaly_count"],
                "avg_execution_seconds": None,
            },
            "recommendation": "Assessment parsing failed. Check raw response.",
            "_raw_response": raw_text[:500],
        }

    # Store assessment in journal
    journal = PipelineJournal(conn, city_fips)
    journal.log_assessment(assessment, token_usage=token_usage)

    return {
        "assessment": assessment,
        "token_usage": token_usage,
        "context": {
            "days": days,
            "total_entries": len(context["entries"]),
            "total_runs": context["total_runs"],
        },
    }


# ── Decision Packet Formatter ───────────────────────────────


def format_decision_packet(result: dict[str, Any]) -> str:
    """Format an assessment result as a human-readable decision packet.

    Printed to stdout in GitHub Actions logs for operator review.
    """
    assessment = result["assessment"]
    token_usage = result.get("token_usage", {})
    context = result.get("context", {})

    health = assessment.get("overall_health", "unknown")
    health_icon = {"healthy": "OK", "degraded": "WARN", "unhealthy": "FAIL"}.get(health, "??")

    lines = [
        "",
        "=" * 60,
        f"  Pipeline Self-Assessment [{health_icon}]",
        "=" * 60,
        "",
        f"  Health: {health.upper()}",
        f"  Period: last {context.get('days', '?')} days",
        f"  Runs analyzed: {context.get('total_runs', '?')}",
        f"  Journal entries: {context.get('total_entries', '?')}",
        "",
        f"  Summary: {assessment.get('summary', 'No summary')}",
    ]

    findings = assessment.get("findings", [])
    if findings:
        lines.append("")
        lines.append("  Findings:")
        for i, finding in enumerate(findings, 1):
            severity = finding.get("severity", "?").upper()
            category = finding.get("category", "?")
            desc = finding.get("description", "No description")
            lines.append(f"    {i}. [{severity}] ({category}) {desc}")
            evidence = finding.get("evidence")
            if evidence:
                lines.append(f"       Evidence: {evidence}")

    recommendation = assessment.get("recommendation")
    if recommendation:
        lines.append("")
        lines.append(f"  Recommendation: {recommendation}")

    metrics = assessment.get("metrics", {})
    if metrics:
        lines.append("")
        lines.append("  Metrics:")
        for key, value in metrics.items():
            lines.append(f"    {key}: {value}")

    if token_usage:
        input_tokens = token_usage.get("input_tokens", 0)
        output_tokens = token_usage.get("output_tokens", 0)
        # Sonnet pricing: $3/M input, $15/M output
        cost = (input_tokens * 3 + output_tokens * 15) / 1_000_000
        lines.append("")
        lines.append(f"  Cost: ~${cost:.4f} ({input_tokens} in + {output_tokens} out tokens)")

    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    return "\n".join(lines)


# ── Decision Queue Producer ─────────────────────────────────


def create_assessment_decisions(
    conn,
    city_fips: str,
    assessment: dict[str, Any],
) -> list[str]:
    """Create decision queue entries from self-assessment findings.

    Examines the assessment's findings list and creates decisions
    for high and medium severity items.

    Returns list of created decision IDs (UUIDs as strings).
    """
    from decision_queue import create_decision

    findings = assessment.get("findings", [])
    overall_health = assessment.get("overall_health", "unknown")
    created = []

    # Map assessment severity to decision queue severity
    severity_map = {
        "high": "high",
        "medium": "medium",
        "low": "low",
        "critical": "critical",
    }

    for finding in findings:
        finding_severity = finding.get("severity", "info").lower()
        # Only create decisions for high/medium/critical findings
        if finding_severity not in ("high", "medium", "critical"):
            continue

        category = finding.get("category", "unknown")
        description = finding.get("description", "No description")
        evidence_text = finding.get("evidence", "")
        today = datetime.now().strftime("%Y-%m-%d")

        result = create_decision(
            conn,
            city_fips=city_fips,
            decision_type="assessment_finding",
            severity=severity_map.get(finding_severity, "medium"),
            title=f"Assessment finding: {category}",
            description=description,
            source="self_assessment",
            evidence={
                "category": category,
                "evidence": evidence_text,
                "overall_health": overall_health,
                "assessment_date": today,
            },
            dedup_key=f"assessment:{category}:{today}",
        )
        if result is not None:
            created.append(str(result))

    return created


# ── CLI ─────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Richmond Common — Pipeline Self-Assessment",
    )
    parser.add_argument("--days", type=int, default=7, help="Number of days to assess (default: 7)")
    parser.add_argument("--city-fips", default="0660620", help="City FIPS code")
    parser.add_argument("--context-only", action="store_true",
                        help="Print assessment context without calling LLM")
    parser.add_argument("--create-decisions", action="store_true",
                        help="Create decision queue entries from assessment findings")
    args = parser.parse_args()

    conn = get_connection()

    if args.context_only:
        context = build_assessment_context(conn, args.city_fips, days=args.days)
        print(f"\nAssessment context for {args.city_fips} (last {args.days} days):")
        print(f"  Total runs: {context['total_runs']}")
        print(f"  Completed: {context['completed_runs']}")
        print(f"  Failed: {context['failed_runs']}")
        print(f"  Anomalies: {context['anomaly_count']}")
        print(f"  Steps: {context['step_count']}")
        print(f"  Journal entries: {len(context['entries'])}")
        if context["entries"]:
            print(f"\nEntries:")
            print(_format_entries_for_prompt(context["entries"]))
        conn.close()
        return

    try:
        result = run_self_assessment(conn, args.city_fips, days=args.days)
        print(format_decision_packet(result))

        if args.create_decisions:
            created = create_assessment_decisions(
                conn, args.city_fips, result["assessment"],
            )
            if created:
                print(f"Created {len(created)} assessment decision(s).")
            else:
                print("No new assessment decisions created.")
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Self-assessment failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
