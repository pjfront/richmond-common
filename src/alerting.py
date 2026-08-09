"""Push alerting core (P1.1a) — the keystone of the self-tending pipeline.

Reads from: the pipeline-manifest liveness expectations run against the live
DB (pipeline_map.run_liveness_checks), pipeline_journal api_cost rows
(cost_digest.compact_mtd_summary), docs/scheduled_civic_events.yaml,
docs/alerting-suppressions.yaml, docs/operator-review-queue.yaml, and the
email_subscribers table. Does NOT read health_reports JSON (derivative,
saved only by local runs).

No LLM anywhere. Runs daily from .github/workflows/alerting.yml.

Outputs (to --out-dir, consumed by the workflow):
  outputs.env       — KEY=VALUE lines appended to $GITHUB_OUTPUT
                      (send_email, alert_count, mode, subject)
  email_body.txt    — composed message (plain text)
  issues.jsonl      — one line per NEW alert-worthy finding, for the
                      deduplicated GitHub-issue audit trail

Exit codes: 0 = the alerting ran (alerts are DATA in the outputs, not exit
codes); nonzero = the alerting itself broke. The workflow pings the external
dead-man's switch only after a fully successful run, so a nonzero exit here
eventually surfaces via healthchecks.io even if email is down — that is the
point of P1.1b.

Alert policy (daily mode emails only when something needs attention):
  - any visible (unsuppressed) high-severity or errored liveness expectation
  - any failing expectation whose suppression has EXPIRED (escalation — a
    suppression must never rot into permanent silence)
  - any overdue calendar entry, or one inside its lead window
  - Anthropic MTD spend >= 80% of cap
  - calendar horizon < 90 days of future entries
Weekly mode (Mondays) always emails: the all-clear digest proves the channel
itself is alive. Monthly mode (1st) adds the summary (spend vs cap,
subscribers, pending graduations, open alert issues).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

SRC_DIR = Path(__file__).parent
REPO_ROOT = SRC_DIR.parent
sys.path.insert(0, str(SRC_DIR))

SUPPRESSIONS_PATH = REPO_ROOT / "docs" / "alerting-suppressions.yaml"
CALENDAR_PATH = REPO_ROOT / "docs" / "scheduled_civic_events.yaml"
REVIEW_QUEUE_PATH = REPO_ROOT / "docs" / "operator-review-queue.yaml"

CAP_WARN_RATIO = 0.80
HORIZON_MIN_DAYS = 90


# ── Pure helpers (unit-tested in tests/test_alerting.py) ──────────────────

def resolve_mode(mode_arg: str, today: dt.date) -> str:
    """auto → monthly on the 1st, weekly on Mondays, else daily."""
    if mode_arg != "auto":
        return mode_arg
    if today.day == 1:
        return "monthly"
    if today.weekday() == 0:
        return "weekly"
    return "daily"


def load_suppressions(path: Path, today: dt.date) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (active, expired) suppression maps keyed by expectation id.

    Every entry MUST carry an expiry — open-ended suppressions are how the
    June 2026 freeze stayed invisible. Entries without one are treated as
    already expired.
    """
    if not path.exists():
        return {}, {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    active: dict[str, dict] = {}
    expired: dict[str, dict] = {}
    for entry in data.get("suppressions") or []:
        sid = entry.get("id")
        if not sid:
            continue
        expires = entry.get("expires")
        if isinstance(expires, str):
            expires = dt.date.fromisoformat(expires)
        if expires and expires >= today:
            active[sid] = entry
        else:
            expired[sid] = entry
    return active, expired


def split_failures(results: list[dict], active: dict[str, dict],
                   expired: dict[str, dict]) -> dict[str, list[dict]]:
    """Split liveness results into visible / suppressed / expired-but-failing."""
    out: dict[str, list[dict]] = {"visible": [], "suppressed": [], "expired": []}
    for r in results:
        if r.get("status") not in ("fail", "error"):
            continue
        rid = r.get("id", "")
        if rid in active:
            out["suppressed"].append(r)
        elif rid in expired:
            out["expired"].append(r)
        else:
            out["visible"].append(r)
    return out


def _severity(result: dict) -> str:
    return (result.get("expectation") or {}).get("severity", "medium")


def calendar_state(path: Path, today: dt.date) -> dict[str, Any]:
    """Overdue / due-soon entries + the horizon meta-check."""
    events = []
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        events = data.get("events") or []
    overdue, due_soon = [], []
    completed_count = 0
    horizon_days = 0
    for ev in events:
        if ev.get("completed_on"):
            completed_count += 1
            continue
        due = ev.get("due_date")
        if isinstance(due, str):
            due = dt.date.fromisoformat(due)
        if due is None:
            continue
        lead = int(ev.get("lead_days") or 7)
        delta = (due - today).days
        horizon_days = max(horizon_days, delta)
        enriched = {**ev, "due_date": due.isoformat(), "days_until": delta}
        if delta < 0:
            overdue.append(enriched)
        elif delta <= lead:
            due_soon.append(enriched)
    return {
        "overdue": overdue,
        "due_soon": due_soon,
        "horizon_days": horizon_days,
        "horizon_ok": horizon_days >= HORIZON_MIN_DAYS,
        "event_count": len(events) - completed_count,
        "completed_event_count": completed_count,
    }


def pending_graduations(path: Path) -> dict[str, Any]:
    """Count + oldest pending_graduation entries from the review queue."""
    if not path.exists():
        return {"count": 0, "oldest": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = [e for e in (data.get("gates") or data.get("entries") or [])
               if e.get("category") == "pending_graduation"]
    entries.sort(key=lambda e: str(e.get("gated_at", "9999")))
    return {
        "count": len(entries),
        "oldest": [{"id": e.get("id"), "gated_at": str(e.get("gated_at"))}
                   for e in entries[:3]],
    }


def decide_alerts(splits: dict[str, list[dict]], cal: dict[str, Any],
                  cost: Optional[dict], today: dt.date) -> list[dict]:
    """The alert list: everything that must reach the operator's inbox."""
    alerts: list[dict] = []
    for r in splits["visible"]:
        sev = _severity(r)
        if r.get("status") == "error" or sev == "high":
            alerts.append({
                "kind": "liveness",
                "id": r["id"],
                "title": f"[liveness] {r['id']} ({sev}, {r.get('status')})",
                "detail": (r.get("expectation") or {}).get("description", ""),
            })
    for r in splits["expired"]:
        alerts.append({
            "kind": "suppression_expired",
            "id": r["id"],
            "title": f"[suppression expired] {r['id']} is still failing",
            "detail": "The suppression window for this known failure has "
                      "lapsed — either fix it or renew the suppression with "
                      "a new expiry and reason.",
        })
    for ev in cal["overdue"]:
        alerts.append({
            "kind": "calendar_overdue",
            "id": ev.get("id", "calendar"),
            "title": f"[calendar OVERDUE] {ev.get('id')} (due {ev.get('due_date')})",
            "detail": ev.get("action", ""),
        })
    for ev in cal["due_soon"]:
        alerts.append({
            "kind": "calendar_due",
            "id": ev.get("id", "calendar"),
            "title": f"[calendar] {ev.get('id')} due {ev.get('due_date')} "
                     f"({ev.get('days_until')}d)",
            "detail": ev.get("action", ""),
        })
    if cost and cost.get("cap_usd"):
        ratio = float(cost["mtd_total"]) / float(cost["cap_usd"])
        if ratio >= CAP_WARN_RATIO:
            alerts.append({
                "kind": "cost",
                "id": "anthropic-cap-approach",
                "title": f"[cost] Anthropic MTD ${cost['mtd_total']:.2f} is "
                         f"{ratio:.0%} of the ${float(cost['cap_usd']):.2f} cap",
                "detail": "P1.10 degradation policy applies: consider Haiku "
                          "fallback / deferring low-priority enrichment, or a "
                          "one-line cap-bump decision.",
            })
    if not cal["horizon_ok"]:
        alerts.append({
            "kind": "calendar_horizon",
            "id": "calendar-horizon",
            "title": f"[calendar] horizon is only {cal['horizon_days']}d "
                     f"(< {HORIZON_MIN_DAYS}d)",
            "detail": "An empty calendar must not look like nothing is due — "
                      "add the next quarter's civic/infrastructure entries "
                      "(docs/scheduled_civic_events.yaml).",
        })
    return alerts


def compose_email(mode: str, today: dt.date, alerts: list[dict],
                  splits: dict[str, list[dict]], cal: dict[str, Any],
                  cost: Optional[dict], liveness_counts: dict[str, int],
                  subscribers: Optional[int], graduations: dict[str, Any],
                  open_issues: int, oldest_issue: str) -> tuple[str, str]:
    """Return (subject, body). Plain text, scannable in a phone notification."""
    site = "Richmond Commons"
    if alerts:
        subject = f"[{site}] {len(alerts)} alert{'s' if len(alerts) != 1 else ''} — {today.isoformat()}"
    elif mode == "monthly":
        subject = f"[{site}] monthly summary — {today.strftime('%B %Y')}"
    else:
        subject = f"[{site}] all clear — week of {today.isoformat()}"

    lines: list[str] = []
    if alerts:
        lines.append("NEEDS ATTENTION")
        lines.append("=" * 40)
        for a in alerts:
            lines.append(f"* {a['title']}")
            if a.get("detail"):
                lines.append(f"    {a['detail']}")
        lines.append("")
    else:
        lines.append("All clear: no unsuppressed failures, no overdue calendar "
                     "entries, spend under threshold.")
        lines.append("")

    lines.append("PIPELINE LIVENESS")
    lines.append(f"  {liveness_counts.get('passing', 0)}/{liveness_counts.get('total', 0)} passing, "
                 f"{liveness_counts.get('failing', 0)} failing "
                 f"({len(splits['suppressed'])} suppressed with expiry, "
                 f"{len(splits['visible'])} visible, "
                 f"{len(splits['expired'])} expired-suppression)")
    for r in splits["suppressed"]:
        lines.append(f"  [suppressed] {r['id']} ({_severity(r)})")
    for r in splits["visible"]:
        if _severity(r) not in ("high",) and r.get("status") != "error":
            lines.append(f"  [visible, {_severity(r)}] {r['id']}")
    lines.append("")

    if cost:
        cap = float(cost.get("cap_usd") or 0)
        pct = f" ({float(cost['mtd_total']) / cap:.0%})" if cap else ""
        lines.append(f"COST: ${float(cost['mtd_total']):.2f} / ${cap:.2f} MTD{pct}")
        for t in cost.get("top") or []:
            lines.append(f"  {t.get('caller')}: ${float(t.get('cost', 0)):.2f}")
    else:
        lines.append("COST: unavailable (DB read failed) — investigate if this persists")
    lines.append("")

    lines.append(f"CALENDAR: {cal['event_count']} entries, horizon {cal['horizon_days']}d"
                 + ("" if cal["horizon_ok"] else "  << thin"))
    for ev in cal["due_soon"]:
        lines.append(f"  due {ev['due_date']}: {ev.get('id')}")
    lines.append("")

    if mode == "monthly":
        lines.append("MONTHLY SUMMARY")
        lines.append("=" * 40)
        lines.append(f"  Email subscribers: {subscribers if subscribers is not None else 'unavailable'}")
        lines.append(f"  Pending graduations: {graduations['count']}"
                     + (f" (oldest: {', '.join(g['id'] + ' since ' + g['gated_at'] for g in graduations['oldest'])})"
                        if graduations["oldest"] else ""))
        lines.append(f"  Open alert issues: {open_issues}"
                     + (f" (oldest {oldest_issue[:10]})" if oldest_issue else ""))
        lines.append("")

    lines.append("--")
    lines.append("Automated by .github/workflows/alerting.yml (P1.1a). "
                 "Suppressions: docs/alerting-suppressions.yaml. "
                 "Calendar: docs/scheduled_civic_events.yaml.")
    return subject, "\n".join(lines)


def should_send(mode: str, alerts: list[dict]) -> bool:
    return bool(alerts) or mode in ("weekly", "monthly")


# ── Live data collection ──────────────────────────────────────────────────

def collect_live_state() -> dict[str, Any]:
    """Everything that needs the DB. Import here so unit tests stay DB-free."""
    from db import get_connection
    from pipeline_map import load_manifest, run_liveness_checks
    from cost_digest import compact_mtd_summary

    manifest = load_manifest()
    results = run_liveness_checks(manifest.get("expectations") or [])
    counts = {
        "total": len(results),
        "passing": sum(1 for r in results if r.get("status") == "pass"),
        "failing": sum(1 for r in results if r.get("status") in ("fail", "error")),
        "skipped": sum(1 for r in results if r.get("status") == "skipped"),
    }

    cost = None
    subscribers = None
    try:
        conn = get_connection()
        cost = compact_mtd_summary(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM email_subscribers WHERE status = 'active'")
            subscribers = cur.fetchone()[0]
        conn.close()
    except Exception as e:  # cost/subscribers are context, not the alert path
        print(f"WARNING: cost/subscriber collection failed: {e}", file=sys.stderr)

    return {"results": results, "counts": counts, "cost": cost,
            "subscribers": subscribers}


def main() -> int:
    parser = argparse.ArgumentParser(description="Richmond Commons push alerting (P1.1a)")
    parser.add_argument("--mode", default="auto",
                        choices=["auto", "daily", "weekly", "monthly"])
    parser.add_argument("--today", default=None, help="YYYY-MM-DD override (tests)")
    parser.add_argument("--out-dir", default="alert_out")
    parser.add_argument("--open-alert-issues", type=int, default=0)
    parser.add_argument("--oldest-alert-issue", default="")
    args = parser.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    mode = resolve_mode(args.mode, today)

    active, expired = load_suppressions(SUPPRESSIONS_PATH, today)
    cal = calendar_state(CALENDAR_PATH, today)
    grads = pending_graduations(REVIEW_QUEUE_PATH)

    live = collect_live_state()
    splits = split_failures(live["results"], active, expired)
    alerts = decide_alerts(splits, cal, live["cost"], today)
    subject, body = compose_email(
        mode, today, alerts, splits, cal, live["cost"], live["counts"],
        live["subscribers"], grads, args.open_alert_issues,
        args.oldest_alert_issue,
    )
    send = should_send(mode, alerts)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "email_body.txt").write_text(body, encoding="utf-8")
    with (out / "issues.jsonl").open("w", encoding="utf-8") as f:
        for a in alerts:
            if a["kind"] in ("liveness", "suppression_expired"):
                issue_body = (
                    f"{a.get('detail', '')}\n\n"
                    f"Detected by the daily alerting run on {today.isoformat()} "
                    f"(mode={mode}).\n\n"
                    "This issue is the audit trail (P1.1a); the alert email is "
                    "the notification. Close when the expectation passes again."
                )
                f.write(json.dumps({"id": a["id"], "title": a["title"],
                                    "body": issue_body}) + "\n")
    with (out / "outputs.env").open("w", encoding="utf-8") as f:
        f.write(f"mode={mode}\n")
        f.write(f"send_email={'true' if send else 'false'}\n")
        f.write(f"alert_count={len(alerts)}\n")
        f.write(f"subject={subject}\n")
    (out / "alert_summary.json").write_text(json.dumps({
        "date": today.isoformat(), "mode": mode, "alerts": alerts,
        "liveness": live["counts"],
        "suppressed": [r["id"] for r in splits["suppressed"]],
        "calendar": cal,
    }, indent=2, default=str), encoding="utf-8")

    print(f"mode={mode} alerts={len(alerts)} send_email={send}")
    for a in alerts:
        print(f"  ALERT: {a['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
