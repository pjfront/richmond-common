"""Push alerting core (P1.1a) — the keystone of the self-tending pipeline.

Reads from: the pipeline-manifest liveness expectations run against the live
DB (pipeline_map.run_liveness_checks), pipeline_journal api_cost rows
(cost_digest.compact_mtd_summary), docs/scheduled_civic_events.yaml,
docs/alerting-suppressions.yaml, docs/operator-review-queue.yaml, and the
email_subscribers table. It also makes bounded, read-only requests to the
public Richmond Commons homepage and /api/health. Does NOT read health_reports
JSON (derivative, saved only by local runs).

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
  - cost telemetry unavailable on its weekly/monthly review cadence
  - subscriber-count telemetry unavailable in the monthly summary
  - calendar horizon < 90 days of future entries
  - the public homepage or /api/health does not pass its bounded daily probe
Weekly mode (Mondays) always emails: the all-clear digest proves the channel
itself is alive. Monthly mode (1st) adds the summary (spend vs cap,
subscribers, pending graduations, open alert issues).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import yaml

SRC_DIR = Path(__file__).parent
REPO_ROOT = SRC_DIR.parent
sys.path.insert(0, str(SRC_DIR))

SUPPRESSIONS_PATH = REPO_ROOT / "docs" / "alerting-suppressions.yaml"
CALENDAR_PATH = REPO_ROOT / "docs" / "scheduled_civic_events.yaml"
REVIEW_QUEUE_PATH = REPO_ROOT / "docs" / "operator-review-queue.yaml"
LLM_HANDOFF_PATH = SRC_DIR / "prompts" / "operator_alert_handoff.txt"
OPERATOR_PLAYBOOK_URL = (
    "https://github.com/pjfront/richmond-common/blob/main/"
    "docs/operator-alert-playbook.md"
)

CAP_WARN_RATIO = 0.80
HORIZON_MIN_DAYS = 90
ACTION_KINDS = {"direct", "decision", "llm"}
TELEMETRY_COST_ALERT_ID = "cost-telemetry-unavailable"
TELEMETRY_SUBSCRIBER_ALERT_ID = "subscriber-telemetry-unavailable"
ISSUE_ALERT_KINDS = {
    "liveness",
    "suppression_expired",
    "site_health",
    "telemetry",
}
CALENDAR_RECURRENCE_LOOKBACK_DAYS = 30
CALENDAR_RECURRENCE_FUTURE_YEARS = 2
MAX_CALENDAR_EVENTS = 200
MAX_RECURRING_EVENTS = 50
MAX_CALENDAR_OVERRIDES = 20
CALENDAR_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
EVIDENCE_KEYS = ("entity_id", "meeting_date", "detail")
MAX_EVIDENCE_ROWS = 3
MAX_EVIDENCE_VALUE_CHARS = 300
DEFAULT_PUBLIC_SITE_URL = "https://richmondcommons.org/"
DEFAULT_PUBLIC_HEALTH_URL = "https://richmondcommons.org/api/health"
PUBLIC_SITE_MARKER = "Richmond Commons"
SITE_PROBE_TIMEOUT_SECONDS = 10
SITE_PROBE_MAX_ATTEMPTS = 2
SITE_PROBE_MAX_BYTES = 64 * 1024


class _NoPublicProbeRedirects(urllib.request.HTTPRedirectHandler):
    """Keep the fixed public probes on their configured origins."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_public_probe(request: urllib.request.Request, *, timeout: int):
    return urllib.request.build_opener(_NoPublicProbeRedirects()).open(
        request, timeout=timeout,
    )


def _safe_operator_text(value: Any, limit: int = 600) -> str:
    """Collapse and bound alert text while removing common secret/PII shapes."""
    text = " ".join(str(value or "").split())
    text = re.sub(
        r"(?i)\b([A-Z0-9._%+-]+)@([A-Z0-9.-]+\.[A-Z]{2,})\b",
        "[redacted-email]",
        text,
    )
    text = re.sub(
        r"(?i)\bauthorization\s*[:=]\s*\S+(?:\s+\S+)?",
        "Authorization=[redacted]",
        text,
    )
    text = re.sub(
        r"(?i)\b[A-Z0-9_]*(?:API_KEY|SERVICE_KEY|DATABASE_URL|SECRET|TOKEN|PASSWORD)"
        r"\s*[:=]\s*\S+",
        "credential=[redacted]",
        text,
    )
    text = re.sub(
        r"(?i)\b(bearer|password|secret|token)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        text,
    )
    text = re.sub(r"(?i)\b(?:postgres(?:ql)?|supabase)://\S+", "[redacted-dsn]", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
                  "[redacted-jwt]", text)
    text = re.sub(r"\b(?:sk-|sk_|dsk_|sbp_)[A-Za-z0-9_-]{8,}\b",
                  "[redacted-key]", text)
    text = re.sub(
        r"\b(?:gh[pousr]_|github_pat_|re_|sb_secret_)[A-Za-z0-9_-]{8,}\b",
        "[redacted-key]",
        text,
    )
    text = re.sub(
        r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}\b",
        "credential=[redacted]",
        text,
    )
    text = re.sub(
        r"(?i)https?://hc-ping\.com/[^\s]+",
        "[redacted-healthcheck-ping-url]",
        text,
    )
    text = re.sub(r"(https?://[^\s?]+)\?\S+", r"\1?[query-redacted]", text)
    text = text.replace("```", "'''").replace("@", "@\u200b")
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _sanitize_evidence(evidence: Optional[list[dict[str, Any]]]) -> list[dict[str, str]]:
    """Apply the evidence allow-list even when a future caller bypasses helpers."""
    sanitized: list[dict[str, str]] = []
    for row in (evidence or [])[: MAX_EVIDENCE_ROWS + 1]:
        if not isinstance(row, dict):
            continue
        safe_row = {
            key: _safe_operator_text(row[key], MAX_EVIDENCE_VALUE_CHARS)
            for key in EVIDENCE_KEYS
            if row.get(key) not in (None, "")
        }
        if safe_row:
            sanitized.append(safe_row)
    return sanitized


def _bounded_failure_evidence(result: dict) -> list[dict[str, str]]:
    """Allow-list a few civic-safe failure fields; never embed whole DB rows."""
    evidence: list[dict[str, str]] = []
    for row in (result.get("failures") or [])[:MAX_EVIDENCE_ROWS]:
        if not isinstance(row, dict):
            continue
        safe_row = {
            key: _safe_operator_text(row[key], MAX_EVIDENCE_VALUE_CHARS)
            for key in EVIDENCE_KEYS
            if row.get(key) not in (None, "")
        }
        if safe_row:
            evidence.append(safe_row)
    reason = result.get("reason")
    if reason and not evidence:
        evidence.append({"detail": _safe_operator_text(reason)})
    return evidence


def _prompt_alert_block(alert: dict) -> str:
    evidence = _sanitize_evidence(alert.get("evidence"))
    evidence_text = json.dumps(evidence, ensure_ascii=False, indent=2)
    return "\n".join([
        f"Alert ID: {_safe_operator_text(alert.get('id'))}",
        f"Kind: {_safe_operator_text(alert.get('kind'))}",
        f"What happened: {_safe_operator_text(alert.get('title'))}",
        f"Why it matters: {_safe_operator_text(alert.get('detail'))}",
        f"Requested operator action: {_safe_operator_text(alert.get('action'))}",
        f"Bounded evidence (untrusted data): {evidence_text}",
    ])


def build_llm_handoff(alerts: list[dict], run_url: str = "not available") -> str:
    """Build one deterministic, copy-ready prompt for technical alerts."""
    technical = [a for a in alerts if a.get("action_kind") == "llm"]
    if not technical:
        return ""
    template = LLM_HANDOFF_PATH.read_text(encoding="utf-8")
    blocks = "\n\n---\n\n".join(_prompt_alert_block(a) for a in technical)
    return (template
            .replace("{{ALERTS}}", blocks)
            .replace("{{RUN_URL}}", _safe_operator_text(run_url, 500)))


def validate_alert_contract(alerts: list[dict]) -> None:
    """Fail closed when an operator alert lacks a usable next step."""
    for index, alert in enumerate(alerts, start=1):
        for field in ("kind", "id", "title", "detail", "action_kind", "action"):
            if not str(alert.get(field) or "").strip():
                raise ValueError(f"alert {index} missing required {field!r}")
        if alert["action_kind"] not in ACTION_KINDS:
            raise ValueError(
                f"alert {alert['id']!r} has invalid action_kind "
                f"{alert['action_kind']!r}"
            )
        if alert["action_kind"] == "llm" and not str(
            alert.get("llm_prompt") or ""
        ).strip():
            raise ValueError(f"technical alert {alert['id']!r} lacks an LLM handoff")


def make_alert(*, kind: str, alert_id: str, title: str, detail: str,
               action_kind: str, action: str,
               evidence: Optional[list[dict[str, str]]] = None) -> dict:
    """Construct an alert that cannot omit its operator action contract."""
    alert = {
        "kind": _safe_operator_text(kind, 80),
        "id": _safe_operator_text(alert_id, 160),
        "title": _safe_operator_text(title),
        "detail": _safe_operator_text(detail, 1_200),
        "action_kind": action_kind,
        "action": _safe_operator_text(action, 1_200),
        "evidence": _sanitize_evidence(evidence),
        "llm_prompt": "",
    }
    if action_kind == "llm":
        alert["llm_prompt"] = build_llm_handoff([alert])
    validate_alert_contract([alert])
    return alert


def alert_issue_marker(alert_id: str) -> str:
    """Return the exact, machine-readable key used for alert issue lifecycle."""
    return f"<!-- richmond-alert-key:{_safe_operator_text(alert_id, 160)} -->"


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
            out["suppressed"].append({**r, "suppression": active[rid]})
        elif rid in expired:
            out["expired"].append({**r, "suppression": expired[rid]})
        else:
            out["visible"].append(r)
    return out


def _severity(result: dict) -> str:
    return (result.get("expectation") or {}).get("severity", "medium")


def _calendar_should_alert(event: dict) -> bool:
    """Use bounded reminders instead of emailing every day in a lead window."""
    days_until = int(event.get("days_until") or 0)
    if days_until >= 0:
        lead = int(event.get("lead_days", 7))
        return days_until in {lead, 14, 7, 3, 1, 0}
    days_overdue = abs(days_until)
    return days_overdue in {1, 3, 7, 14, 30} or (
        days_overdue > 30 and days_overdue % 30 == 0
    )


def _calendar_date(value: Any, field: str) -> dt.date:
    """Parse one YAML calendar date with a field-specific fail-closed error."""
    if isinstance(value, dt.datetime):
        raise ValueError(f"calendar {field} must be a date, not a datetime")
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"calendar {field} must use YYYY-MM-DD"
            ) from exc
    raise ValueError(f"calendar {field} must use YYYY-MM-DD")


def _validate_calendar_contract(
    entry: dict[str, Any], *, label: str, active: bool,
) -> None:
    """Validate the operator-facing contract shared by dated and recurring items."""
    event_id = entry.get("id")
    if not isinstance(event_id, str) or not CALENDAR_ID_RE.fullmatch(event_id):
        raise ValueError(
            f"calendar {label} id must be a lowercase dash-separated slug"
        )
    lead_days = entry.get("lead_days", 7)
    if (
        isinstance(lead_days, bool)
        or not isinstance(lead_days, int)
        or not 0 <= lead_days <= 366
    ):
        raise ValueError(f"calendar {label} lead_days must be 0..366")
    if entry.get("owner") not in {"operator", "ai"}:
        raise ValueError(f"calendar {label} owner must be operator or ai")
    if not active:
        return
    if not str(entry.get("action") or "").strip():
        raise ValueError(f"calendar {label} missing required action")
    if entry.get("response_mode") not in ACTION_KINDS:
        raise ValueError(
            f"calendar {label} response_mode must be direct, decision, or llm"
        )
    source_url = entry.get("source_url")
    if (
        not isinstance(source_url, str)
        or not re.fullmatch(r"https://[^\s]+", source_url)
    ):
        raise ValueError(f"calendar {label} requires an https source_url")


def _normalize_annual_rule(
    entry: dict[str, Any], *, label: str,
) -> tuple[int, int, dict[int, dt.date]]:
    """Validate the deliberately small annual rule and normalize overrides."""
    rule = entry.get("rule")
    if not isinstance(rule, dict):
        raise ValueError(f"calendar {label} rule must be a mapping")
    unknown = set(rule) - {"frequency", "month", "day", "overrides"}
    if unknown:
        raise ValueError(
            f"calendar {label} rule has unsupported fields: {sorted(unknown)}"
        )
    if rule.get("frequency") != "annual":
        raise ValueError(f"calendar {label} only supports annual recurrence")
    month, day = rule.get("month"), rule.get("day")
    if (
        isinstance(month, bool)
        or isinstance(day, bool)
        or not isinstance(month, int)
        or not isinstance(day, int)
    ):
        raise ValueError(f"calendar {label} month and day must be integers")
    try:
        # A non-leap reference year deliberately rejects Feb. 29. This schema
        # represents a reminder every year, not an intermittent RRULE.
        dt.date(2001, month, day)
    except ValueError as exc:
        raise ValueError(f"calendar {label} has an invalid annual date") from exc

    raw_overrides = rule.get("overrides") or {}
    if not isinstance(raw_overrides, dict):
        raise ValueError(f"calendar {label} overrides must be a mapping")
    if len(raw_overrides) > MAX_CALENDAR_OVERRIDES:
        raise ValueError(
            f"calendar {label} has more than {MAX_CALENDAR_OVERRIDES} overrides"
        )
    overrides: dict[int, dt.date] = {}
    for raw_year, raw_date in raw_overrides.items():
        year_text = str(raw_year)
        if not re.fullmatch(r"\d{4}", year_text):
            raise ValueError(f"calendar {label} override years must use YYYY")
        year = int(year_text)
        if year in overrides:
            raise ValueError(f"calendar {label} has duplicate override year {year}")
        override = _calendar_date(raw_date, f"{label} override {year}")
        if override.year != year:
            raise ValueError(
                f"calendar {label} override {year} must stay in that year"
            )
        overrides[year] = override
    return month, day, overrides


def _expand_annual_event(
    entry: dict[str, Any], *, today: dt.date,
) -> list[dict[str, Any]]:
    """Expand one annual series into a fixed four-year window at most."""
    label = str(entry.get("id") or "recurring event")
    _validate_calendar_contract(entry, label=label, active=True)
    month, day, overrides = _normalize_annual_rule(entry, label=label)
    cutoff = today - dt.timedelta(days=CALENDAR_RECURRENCE_LOOKBACK_DAYS)
    occurrences: list[dict[str, Any]] = []
    years = range(
        today.year - 1,
        today.year + CALENDAR_RECURRENCE_FUTURE_YEARS + 1,
    )
    for year in years:
        due = overrides.get(year, dt.date(year, month, day))
        if due < cutoff:
            continue
        occurrences.append({
            **entry,
            "id": f"{entry['id']}--{year}",
            "series_id": entry["id"],
            "occurrence_year": year,
            "due_date": due,
        })
    return occurrences


def calendar_state(path: Path, today: dt.date) -> dict[str, Any]:
    """Validate, finitely expand, and classify operator calendar entries."""
    if not path.exists():
        return {
            "overdue": [], "due_soon": [], "horizon_days": 0,
            "horizon_ok": False, "event_count": 0,
            "occurrence_count": 0, "completed_event_count": 0,
        }
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("calendar root must be a mapping")
    events = data.get("events") or []
    recurring = data.get("recurring_events") or []
    if not isinstance(events, list) or not isinstance(recurring, list):
        raise ValueError("calendar events and recurring_events must be lists")
    if len(events) > MAX_CALENDAR_EVENTS:
        raise ValueError(f"calendar has more than {MAX_CALENDAR_EVENTS} events")
    if len(recurring) > MAX_RECURRING_EVENTS:
        raise ValueError(
            f"calendar has more than {MAX_RECURRING_EVENTS} recurring events"
        )

    overdue, due_soon = [], []
    completed_count = 0
    horizon_days = 0
    active_events: list[dict[str, Any]] = []
    base_ids: set[str] = set()
    for index, ev in enumerate(events, start=1):
        if not isinstance(ev, dict):
            raise ValueError(f"calendar event {index} must be a mapping")
        label = str(ev.get("id") or f"event {index}")
        _validate_calendar_contract(
            ev, label=label, active=not bool(ev.get("completed_on")),
        )
        if ev["id"] in base_ids:
            raise ValueError(f"calendar duplicate id {ev['id']!r}")
        base_ids.add(ev["id"])
        due = _calendar_date(ev.get("due_date"), f"{label} due_date")
        if ev.get("completed_on"):
            _calendar_date(ev["completed_on"], f"{label} completed_on")
            completed_count += 1
            continue
        if ev.get("window_start"):
            window_start = _calendar_date(
                ev["window_start"], f"{label} window_start",
            )
            if window_start > due:
                raise ValueError(
                    f"calendar {label} window_start must not follow due_date"
                )
        active_events.append({**ev, "due_date": due})

    for index, entry in enumerate(recurring, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"calendar recurring event {index} must be a mapping")
        label = str(entry.get("id") or f"recurring event {index}")
        if entry.get("completed_on"):
            raise ValueError(
                f"calendar {label} cannot complete an entire recurring series"
            )
        # Contract validation is repeated inside expansion so the helper is
        # independently safe; validating the base id first catches collisions.
        _validate_calendar_contract(entry, label=label, active=True)
        if entry["id"] in base_ids:
            raise ValueError(f"calendar duplicate id {entry['id']!r}")
        base_ids.add(entry["id"])
        active_events.extend(_expand_annual_event(entry, today=today))

    occurrence_ids: set[str] = set()
    for ev in active_events:
        if ev["id"] in occurrence_ids:
            raise ValueError(f"calendar duplicate occurrence id {ev['id']!r}")
        occurrence_ids.add(ev["id"])
        due = ev["due_date"]
        lead = int(ev.get("lead_days", 7))
        delta = (due - today).days
        horizon_days = max(horizon_days, delta)
        enriched = {**ev, "due_date": due.isoformat(), "days_until": delta}
        if delta < 0:
            overdue.append(enriched)
        elif delta <= lead:
            due_soon.append(enriched)
    overdue.sort(key=lambda event: (event["due_date"], event["id"]))
    due_soon.sort(key=lambda event: (event["due_date"], event["id"]))
    return {
        "overdue": overdue,
        "due_soon": due_soon,
        "horizon_days": horizon_days,
        "horizon_ok": horizon_days >= HORIZON_MIN_DAYS,
        "event_count": len(events) - completed_count + len(recurring),
        "occurrence_count": len(active_events),
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


def load_notification_state(path: Optional[Path]) -> dict[str, dict[str, str]]:
    """Read exact alert issue keys and dates for bounded reminder cadence."""
    if path is None or not path.exists():
        return {}
    try:
        issues = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    state: dict[str, dict[str, str]] = {}
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict):
            continue
        body = str(issue.get("body") or "")
        title = str(issue.get("title") or "")
        marker = re.search(r"<!-- richmond-alert-key:([^>\r\n]+) -->", body)
        notified = re.search(
            r"<!-- richmond-alert-notified:(\d{4}-\d{2}-\d{2}) -->",
            body,
        )
        alert_id = marker.group(1).strip() if marker else ""
        if not alert_id:
            legacy = re.match(
                r"^\[(?:liveness|suppression expired)\] ([A-Za-z0-9_.-]+) ",
                title,
            )
            alert_id = legacy.group(1) if legacy else ""
        if alert_id:
            state[alert_id] = {
                "created_at": str(issue.get("createdAt") or ""),
                # This marker is written only when the alert body is emitted.
                # GitHub's generic updatedAt is not trusted because comments,
                # labels, or outside activity can change it.
                "notified_at": (
                    notified.group(1) if notified
                    else str(issue.get("createdAt") or "")
                ),
            }
    return state


def _github_date(value: str) -> Optional[dt.date]:
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (AttributeError, TypeError, ValueError):
        return None


def _notification_due(alert_id: str, today: dt.date,
                      state: dict[str, dict[str, str]]) -> bool:
    """Notify first occurrence, then at 3/7/14/30 days and monthly."""
    existing = state.get(alert_id)
    if not existing:
        return True
    created = _github_date(existing.get("created_at", ""))
    notified = _github_date(existing.get("notified_at", ""))
    if created is None or notified is None:
        return True
    if notified >= today:
        return False
    age = max(0, (today - created).days)
    notified_age = max(0, (notified - created).days)
    for milestone in (3, 7, 14, 30):
        if age >= milestone > notified_age:
            return True
    return age > 30 and (today - notified).days >= 30


def _public_probe_error(exc: Exception) -> str:
    """Return useful error shape without copying provider bodies or secrets."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return f"network error ({type(reason).__name__})"
    if isinstance(exc, TimeoutError):
        return "timeout"
    return type(exc).__name__


def _bounded_public_get(
    url: str,
    label: str,
    opener: Any,
    sleeper: Any,
) -> dict[str, Any]:
    """GET one public URL with fixed time, attempt, and response-size bounds."""
    last_error = "unknown error"
    for attempt in range(1, SITE_PROBE_MAX_ATTEMPTS + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json,text/html;q=0.9,*/*;q=0.1",
                    "User-Agent": "RichmondCommons-Alerting/1.0",
                },
                method="GET",
            )
            with opener(request, timeout=SITE_PROBE_TIMEOUT_SECONDS) as response:
                status = int(
                    getattr(response, "status", None) or response.getcode()
                )
                body = response.read(SITE_PROBE_MAX_BYTES)[:SITE_PROBE_MAX_BYTES]
            if 200 <= status < 300:
                return {
                    "label": label,
                    "status": "pass",
                    "http_status": status,
                    "attempts": attempt,
                    "body": body,
                }
            last_error = f"HTTP {status}"
        except Exception as exc:  # this probe must become alert data, not abort mail
            last_error = _public_probe_error(exc)
        if attempt < SITE_PROBE_MAX_ATTEMPTS:
            sleeper(1)
    return {
        "label": label,
        "status": "fail",
        "attempts": SITE_PROBE_MAX_ATTEMPTS,
        "detail": (
            f"{label}: request failed after {SITE_PROBE_MAX_ATTEMPTS} "
            f"attempts ({last_error})"
        ),
    }


def probe_public_site(
    site_url: Optional[str] = None,
    health_url: Optional[str] = None,
    *,
    opener: Any = None,
    sleeper: Any = None,
) -> dict[str, Any]:
    """Check the public front door and API health without ever raising.

    The response contract intentionally contains only bounded, civic-safe
    summaries. Provider response bodies, headers, and exception messages never
    become alert evidence.
    """
    resolved_site_url = site_url or os.environ.get(
        "PUBLIC_SITE_URL", DEFAULT_PUBLIC_SITE_URL
    )
    resolved_health_url = health_url or os.environ.get(
        "PUBLIC_HEALTH_URL", DEFAULT_PUBLIC_HEALTH_URL
    )
    resolved_opener = opener or _open_public_probe
    resolved_sleeper = sleeper or time.sleep
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    try:
        homepage = _bounded_public_get(
            resolved_site_url, "homepage", resolved_opener, resolved_sleeper
        )
        if homepage["status"] == "pass":
            page_text = homepage.pop("body").decode("utf-8", errors="replace")
            if PUBLIC_SITE_MARKER in page_text:
                homepage["detail"] = (
                    f"HTTP {homepage['http_status']}; expected page marker present"
                )
            else:
                homepage["status"] = "fail"
                homepage["detail"] = (
                    "homepage: HTTP response did not contain the expected "
                    "Richmond Commons page marker"
                )
        checks.append(homepage)
        if homepage["status"] == "fail":
            failures.append({"detail": homepage["detail"]})

        health = _bounded_public_get(
            resolved_health_url, "api_health", resolved_opener, resolved_sleeper
        )
        if health["status"] == "pass":
            health_body = health.pop("body")
            try:
                payload = json.loads(health_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                health["status"] = "fail"
                health["detail"] = (
                    "/api/health: response was not valid bounded JSON"
                )
            else:
                reported = (
                    payload.get("status") if isinstance(payload, dict) else None
                )
                if reported == "healthy":
                    health["detail"] = (
                        f"HTTP {health['http_status']}; API reported healthy"
                    )
                elif isinstance(reported, str):
                    safe_status = _safe_operator_text(reported, 60)
                    health["status"] = "fail"
                    health["detail"] = (
                        f"/api/health: API reported status={safe_status}"
                    )
                else:
                    health["status"] = "fail"
                    health["detail"] = (
                        "/api/health: API response had invalid or missing status"
                    )
        checks.append(health)
        if health["status"] == "fail":
            failures.append({"detail": health["detail"]})
    except Exception as exc:  # fail closed into the alert contract
        failures.append(
            {
                "detail": (
                    "public-site probe could not complete safely "
                    f"({_public_probe_error(exc)})"
                )
            }
        )

    return {
        "status": "fail" if failures else "pass",
        "checks": checks,
        "failures": failures,
        "checked_endpoints": 2,
        "timeout_seconds": SITE_PROBE_TIMEOUT_SECONDS,
        "attempt_limit": SITE_PROBE_MAX_ATTEMPTS,
        "response_cap_bytes": SITE_PROBE_MAX_BYTES,
    }


def decide_alerts(
    splits: dict[str, list[dict]],
    cal: dict[str, Any],
    cost: Optional[dict],
    today: dt.date,
    dead_man_armed: bool = True,
    notification_state: Optional[dict[str, dict[str, str]]] = None,
    site_health: Optional[dict[str, Any]] = None,
    telemetry_errors: Optional[dict[str, str]] = None,
    mode: Optional[str] = None,
) -> list[dict]:
    """The alert list: everything that must reach the operator's inbox."""
    alerts: list[dict] = []
    notice_state = notification_state or {}
    for r in splits["visible"]:
        sev = _severity(r)
        if r.get("status") == "error" or sev == "high":
            if not _notification_due(str(r.get("id") or ""), today, notice_state):
                continue
            expectation = r.get("expectation") or {}
            evidence = _bounded_failure_evidence(r)
            evidence.append({
                "detail": _safe_operator_text(
                    f"status={r.get('status')}; severity={sev}; "
                    f"owner={expectation.get('owner', 'unknown')}; "
                    f"failing_rows={len(r.get('failures') or [])}"
                )
            })
            alerts.append(make_alert(
                kind="liveness",
                alert_id=r["id"],
                title=f"Pipeline check {r['id']} is {r.get('status')}",
                detail=(expectation.get("description") or
                        "A high-severity production expectation did not pass."),
                action_kind="llm",
                action=("Copy the LLM handoff below in this alert into "
                        "Codex or ChatGPT. Ask for a read-only diagnosis first; "
                        "do not approve production-data changes."),
                evidence=evidence,
            ))
    for r in splits["expired"]:
        if not _notification_due(str(r.get("id") or ""), today, notice_state):
            continue
        suppression = r.get("suppression") or {}
        evidence = _bounded_failure_evidence(r)
        evidence.append({
            "detail": _safe_operator_text(
                f"previous reason={suppression.get('reason', 'not recorded')}; "
                f"expired={suppression.get('expires', 'not recorded')}"
            )
        })
        alerts.append(make_alert(
            kind="suppression_expired",
            alert_id=r["id"],
            title=f"The temporary hold for {r['id']} expired and it still fails",
            detail=("A known problem reached its review date. It now needs a "
                    "fresh diagnosis before it can be fixed or given a new "
                    "bounded expiry."),
            action_kind="llm",
            action=("Copy the LLM handoff below into Codex or ChatGPT. Ask it "
                    "to return either a focused fix or a proposed dated "
                    "suppression for your approval."),
            evidence=evidence,
        ))
    if site_health and site_health.get("status") == "fail":
        alert_id = "public-site-health"
        if _notification_due(alert_id, today, notice_state):
            evidence = [
                {"detail": _safe_operator_text(row.get("detail"))}
                for row in (site_health.get("failures") or [])[:MAX_EVIDENCE_ROWS]
                if isinstance(row, dict) and row.get("detail")
            ]
            evidence.append({
                "detail": _safe_operator_text(
                    f"checked_endpoints={site_health.get('checked_endpoints', 2)}; "
                    f"timeout_seconds={site_health.get('timeout_seconds', SITE_PROBE_TIMEOUT_SECONDS)}; "
                    f"attempt_limit={site_health.get('attempt_limit', SITE_PROBE_MAX_ATTEMPTS)}; "
                    f"response_cap_bytes={site_health.get('response_cap_bytes', SITE_PROBE_MAX_BYTES)}"
                )
            })
            alerts.append(make_alert(
                kind="site_health",
                alert_id=alert_id,
                title="The public Richmond Commons site did not pass its daily check",
                detail=("The homepage or /api/health did not pass a bounded, "
                        "read-only check. Visitors may be unable to use the site, "
                        "or the site may be reporting degraded backend health."),
                action_kind="llm",
                action=("Open https://richmondcommons.org/ once. If it still "
                        "fails, copy the LLM handoff below into Codex or ChatGPT "
                        "for a read-only Vercel and Supabase diagnosis. Do not "
                        "publish, migrate, or correct production data."),
                evidence=evidence,
            ))
    for ev in cal["overdue"]:
        if not _calendar_should_alert(ev):
            continue
        event_action = _safe_operator_text(ev.get("action"))
        missing_action = not event_action
        if missing_action:
            event_action = ("Copy the LLM handoff below into Codex or ChatGPT "
                            "and ask for step-by-step help completing this "
                            "overdue item.")
        action_kind = ev.get("response_mode")
        if action_kind not in ACTION_KINDS:
            action_kind = "direct" if ev.get("owner") == "operator" else "llm"
        if missing_action:
            action_kind = "llm"
        alerts.append(make_alert(
            kind="calendar_overdue",
            alert_id=ev.get("id", "calendar"),
            title=f"Calendar item {ev.get('id')} is overdue",
            detail=f"It was due {ev.get('due_date')}.",
            action_kind=action_kind,
            action=event_action,
            evidence=[{"detail": _safe_operator_text(
                f"due_date={ev.get('due_date')}; days_overdue={abs(int(ev.get('days_until') or 0))}; "
                f"owner={ev.get('owner', 'not recorded')}; "
                f"official_source={ev.get('source_url')}"
            )}],
        ))
    for ev in cal["due_soon"]:
        if not _calendar_should_alert(ev):
            continue
        event_action = _safe_operator_text(ev.get("action"))
        missing_action = not event_action
        if missing_action:
            event_action = ("Copy the LLM handoff below into Codex or ChatGPT "
                            "and ask for step-by-step help completing this "
                            "item.")
        action_kind = ev.get("response_mode")
        if action_kind not in ACTION_KINDS:
            action_kind = "direct" if ev.get("owner") == "operator" else "llm"
        if missing_action:
            action_kind = "llm"
        alerts.append(make_alert(
            kind="calendar_due",
            alert_id=ev.get("id", "calendar"),
            title=f"Calendar item {ev.get('id')} is due soon",
            detail=(f"It is due {ev.get('due_date')} "
                    f"({ev.get('days_until')} days from today)."),
            action_kind=action_kind,
            action=event_action,
            evidence=[{"detail": _safe_operator_text(
                f"due_date={ev.get('due_date')}; days_until={ev.get('days_until')}; "
                f"owner={ev.get('owner', 'not recorded')}; "
                f"official_source={ev.get('source_url')}"
            )}],
        ))
    telemetry = telemetry_errors or {}
    review_mode = mode or resolve_mode("auto", today)
    if telemetry.get("cost") and review_mode in {"weekly", "monthly"}:
        alerts.append(make_alert(
            kind="telemetry",
            alert_id=TELEMETRY_COST_ALERT_ID,
            title="The scheduled cost check could not read this month's usage",
            detail=("This summary cannot confirm month-to-date routed LLM spend "
                    "against the configured safety cap. The cap itself remains "
                    "unchanged."),
            action_kind="llm",
            action=("Copy the LLM handoff below into Codex or ChatGPT and ask "
                    "for a read-only diagnosis of the cost telemetry query. "
                    "Do not change the cap, rerun paid work, or expose credentials."),
            evidence=[{"detail": _safe_operator_text(
                f"collection_stage=cost; error_type={telemetry['cost']}"
            )}],
        ))
    if telemetry.get("subscribers") and review_mode == "monthly":
        alerts.append(make_alert(
            kind="telemetry",
            alert_id=TELEMETRY_SUBSCRIBER_ALERT_ID,
            title="The monthly summary could not count active subscribers",
            detail=("The subscriber total is unavailable, so the monthly summary "
                    "is incomplete. This count failure does not itself change any "
                    "subscription or send any email."),
            action_kind="llm",
            action=("Copy the LLM handoff below into Codex or ChatGPT and ask "
                    "for a read-only diagnosis of the subscriber-count query. "
                    "Do not edit subscriber rows or resend email."),
            evidence=[{"detail": _safe_operator_text(
                "collection_stage=subscribers; "
                f"error_type={telemetry['subscribers']}"
            )}],
        ))
    if (not cal["horizon_ok"] and
            (today.weekday() == 0 or today.day == 1)):
        alerts.append(make_alert(
            kind="calendar_horizon",
            alert_id="calendar-horizon",
            title="The upkeep calendar does not reach far enough ahead",
            detail=(f"Its latest active entry is only {cal['horizon_days']} "
                    f"days away; the minimum is {HORIZON_MIN_DAYS} days."),
            action_kind="llm",
            action=("Copy the LLM handoff below into Codex or ChatGPT and ask "
                    "it to prepare a calendar-only draft PR using verified "
                    "official dates."),
            evidence=[{"detail": _safe_operator_text(
                f"active_entries={cal['event_count']}; "
                f"horizon_days={cal['horizon_days']}"
            )}],
        ))
    if not dead_man_armed and (today.weekday() == 0 or today.day == 1):
        alerts.append(make_alert(
            kind="monitoring",
            alert_id="external-dead-man-unarmed",
            title="The outside alert monitor is not connected",
            detail=("If the Richmond Commons alert workflow stops, no "
                    "independent service can currently notify you."),
            action_kind="direct",
            action=("Create a healthchecks.io check with a 1-day period and "
                    "6-hour grace, then add its ping URL in GitHub as the "
                    "Actions secret HEALTHCHECKS_PING_URL. Follow the "
                    f"click-by-click steps at {OPERATOR_PLAYBOOK_URL}"),
            evidence=[{"detail": "HEALTHCHECKS_PING_URL is not configured."}],
        ))
    validate_alert_contract(alerts)
    return alerts


def compose_email(mode: str, today: dt.date, alerts: list[dict],
                  splits: dict[str, list[dict]], cal: dict[str, Any],
                  cost: Optional[dict], liveness_counts: dict[str, int],
                  subscribers: Optional[int], graduations: dict[str, Any],
                  open_issues: int, oldest_issue: str,
                  run_url: str = "not available",
                  site_health: Optional[dict[str, Any]] = None) -> tuple[str, str]:
    """Return (subject, body). Plain text, scannable in a phone notification."""
    site = "Richmond Commons"
    validate_alert_contract(alerts)
    alert_ids = {str(alert.get("id") or "") for alert in alerts}
    if mode in {"weekly", "monthly"} and cost is None:
        if TELEMETRY_COST_ALERT_ID not in alert_ids:
            raise ValueError(
                "weekly/monthly cost telemetry is unavailable without an action alert"
            )
    if mode == "monthly" and subscribers is None:
        if TELEMETRY_SUBSCRIBER_ALERT_ID not in alert_ids:
            raise ValueError(
                "monthly subscriber telemetry is unavailable without an action alert"
            )
    site_state = site_health or {"status": "not_checked", "checks": []}
    cap = float(cost.get("cap_usd") or 0) if cost else 0
    cost_ratio = (float(cost["mtd_total"]) / cap) if cost and cap else 0
    cost_near_cap = bool(cap and cost_ratio >= CAP_WARN_RATIO)
    unresolved_status = bool(
        splits["visible"] or splits["suppressed"] or splits["expired"] or
        cal["overdue"] or cal["due_soon"] or open_issues or
        graduations.get("count") or site_state.get("status") == "fail"
    )
    if alerts:
        subject = (f"[{site}] ACTION — {len(alerts)} item"
                   f"{'s' if len(alerts) != 1 else ''} — {today.isoformat()}")
    elif mode == "monthly" and unresolved_status:
        subject = (f"[{site}] NO NEW ACTION — monthly status — "
                   f"{today.strftime('%B %Y')}")
    elif mode == "monthly":
        subject = f"[{site}] NO ACTION — monthly summary — {today.strftime('%B %Y')}"
    elif unresolved_status:
        subject = f"[{site}] NO NEW ACTION — status — {today.isoformat()}"
    elif cost_near_cap:
        subject = f"[{site}] NO ACTION — capped spend status — {today.isoformat()}"
    else:
        subject = f"[{site}] NO ACTION — all clear — week of {today.isoformat()}"

    lines: list[str] = []
    if alerts:
        lines.append("ACTION: Complete the numbered action(s) below.")
        lines.append("")
        lines.append("NEEDS ATTENTION")
        lines.append("=" * 40)
        for number, a in enumerate(alerts, start=1):
            lines.append(f"{number}. {a['title']}")
            if a.get("detail"):
                lines.append(f"   WHY: {a['detail']}")
            lines.append(f"   ACTION: {a['action']}")
            lines.append("")
        handoff = build_llm_handoff(alerts, run_url)
        if handoff:
            lines.append("COPY/PASTE MESSAGE FOR YOUR CODING ASSISTANT")
            lines.append("=" * 40)
            lines.append(handoff)
        lines.append("")
    elif unresolved_status:
        lines.append(
            "ACTION: None today — this status email adds no new task. "
            "Continue only actions assigned in an earlier alert."
        )
        lines.append("")
        lines.append(
            "Status only: unresolved, suppressed, or previously notified "
            "items remain on their bounded reminder schedule."
        )
        lines.append("")
    else:
        lines.append("ACTION: None — no reply or technical work is needed.")
        lines.append("")
        if cost_near_cap:
            lines.append(
                "Status only: no unsuppressed failures or overdue calendar "
                "entries. Runtime spend is near its cap, which remains unchanged "
                "and blocks further unapproved spend."
            )
        elif cost is None:
            lines.append(
                "All clear: no unsuppressed failures or overdue calendar "
                "entries. Cost telemetry is reviewed in the weekly or monthly "
                "summary."
            )
        else:
            lines.append("All clear: no unsuppressed failures, no overdue calendar "
                         "entries, spend under threshold.")
        lines.append("")

    lines.append("PIPELINE LIVENESS")
    pipeline_alert_kinds = {"liveness", "suppression_expired", "monitoring"}
    if any(a.get("kind") in pipeline_alert_kinds for a in alerts):
        lines.append(
            "ACTION: Follow the matching numbered item(s) in NEEDS ATTENTION "
            "above. All other rows in this section are status only."
        )
    else:
        lines.append(
            "ACTION: NO ACTION NEEDED — this section is status only."
        )
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

    lines.append(f"SITE HEALTH: {site_state.get('status', 'not_checked')}")
    if any(a.get("kind") == "site_health" for a in alerts):
        lines.append(
            "ACTION: Follow the matching numbered item in NEEDS ATTENTION above."
        )
    elif site_state.get("status") == "fail":
        lines.append(
            "ACTION: NO NEW ACTION — this ongoing failure remains on its "
            "bounded reminder schedule."
        )
    elif site_state.get("status") == "pass":
        lines.append(
            "ACTION: NO ACTION NEEDED — the public homepage and API health "
            "check passed."
        )
    else:
        lines.append(
            "ACTION: NO ACTION NEEDED — no site probe result was included in "
            "this summary; a separate alert will say if follow-up is required."
        )
    for check in site_state.get("checks") or []:
        if not isinstance(check, dict):
            continue
        lines.append(
            f"  [{_safe_operator_text(check.get('status'), 20)}] "
            f"{_safe_operator_text(check.get('label'), 40)}: "
            f"{_safe_operator_text(check.get('detail'), 180)}"
        )
    lines.append("")

    if cost:
        pct = f" ({cost_ratio:.0%})" if cap else ""
        lines.append(f"COST: ${float(cost['mtd_total']):.2f} / ${cap:.2f} MTD{pct}")
        if cost_near_cap:
            lines.append(
                "ACTION: NO ACTION NEEDED — leave the cap unchanged. It will "
                "block further unapproved runtime spend; request a separate "
                "bounded decision only if a time-sensitive civic update is blocked."
            )
        else:
            lines.append(
                "ACTION: NO ACTION NEEDED — spend is shown for awareness only."
            )
        for t in cost.get("top") or []:
            lines.append(f"  {t.get('caller')}: ${float(t.get('cost', 0)):.2f}")
    else:
        lines.append("COST: unavailable in this summary.")
        if TELEMETRY_COST_ALERT_ID in alert_ids:
            lines.append(
                "ACTION: Follow the matching numbered item in NEEDS ATTENTION above."
            )
        else:
            lines.append(
                "ACTION: NO ACTION NEEDED TODAY — cost telemetry is reviewed for "
                "operator follow-up in the weekly or monthly summary."
            )
    lines.append("")

    lines.append(f"CALENDAR: {cal['event_count']} entries, horizon {cal['horizon_days']}d"
                 + ("" if cal["horizon_ok"] else "  << thin"))
    calendar_alert_kinds = {"calendar_overdue", "calendar_due", "calendar_horizon"}
    if any(a.get("kind") in calendar_alert_kinds for a in alerts):
        lines.append(
            "ACTION: Follow the matching numbered item(s) in NEEDS ATTENTION above."
        )
    else:
        lines.append(
            "ACTION: NO ACTION NEEDED — this section is status only."
        )
    for ev in cal["due_soon"]:
        lines.append(f"  due {ev['due_date']}: {ev.get('id')}")
    lines.append("")

    if mode == "monthly":
        lines.append("MONTHLY SUMMARY")
        lines.append("=" * 40)
        if TELEMETRY_SUBSCRIBER_ALERT_ID in alert_ids:
            lines.append(
                "ACTION: Follow the matching numbered item in NEEDS ATTENTION "
                "above. All other counts in this section are status only."
            )
        else:
            lines.append(
                "ACTION: NO ACTION NEEDED — this section is status only; any task "
                "appears in NEEDS ATTENTION above."
            )
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


def compose_issue_body(alert: dict, today: dt.date, mode: str,
                       run_url: str = "not available") -> str:
    """Render the same action contract into the GitHub audit trail."""
    validate_alert_contract([alert])
    lines = [
        alert_issue_marker(alert["id"]),
        f"<!-- richmond-alert-notified:{today.isoformat()} -->",
        f"ACTION: {alert['action']}",
        "",
        f"WHY: {alert['detail']}",
        "",
        (f"Detected by the Richmond Commons alerting run on "
         f"{today.isoformat()} (mode={mode})."),
    ]
    # GitHub issues are public. Preserve the copy-ready technical handoff but
    # never copy row-level evidence from the private operator email into them.
    public_alert = {**alert, "evidence": []}
    handoff = build_llm_handoff([public_alert], run_url)
    if handoff:
        lines.extend([
            "",
            ("Evidence details are intentionally omitted from this public "
             "audit issue. Inspect the linked run read-only."),
            "",
            "## Copy/paste message for your coding assistant",
            "",
            "--- BEGIN COPY/PASTE MESSAGE ---",
            handoff,
            "--- END COPY/PASTE MESSAGE ---",
        ])
    lines.extend([
        "",
        "This issue is the audit trail. It will close automatically when the "
        "expectation passes again.",
    ])
    return "\n".join(lines)


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
    telemetry_errors: dict[str, str] = {}
    conn = None
    try:
        conn = get_connection()
    except Exception as exc:
        error_type = type(exc).__name__
        telemetry_errors.update({
            "cost": error_type,
            "subscribers": error_type,
        })
        print(
            f"WARNING: cost/subscriber connection failed ({error_type})",
            file=sys.stderr,
        )
    else:
        try:
            cost = compact_mtd_summary(conn)
            if cost is None:
                raise ValueError("cost summary returned no result")
        except Exception as exc:
            error_type = type(exc).__name__
            telemetry_errors["cost"] = error_type
            print(
                f"WARNING: cost telemetry collection failed ({error_type})",
                file=sys.stderr,
            )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM email_subscribers WHERE status = 'active'"
                )
                row = cur.fetchone()
                if not row or row[0] is None:
                    raise ValueError("subscriber count returned no result")
                subscribers = row[0]
        except Exception as exc:
            error_type = type(exc).__name__
            telemetry_errors["subscribers"] = error_type
            print(
                f"WARNING: subscriber telemetry collection failed ({error_type})",
                file=sys.stderr,
            )
        finally:
            try:
                conn.close()
            except Exception as exc:
                print(
                    f"WARNING: telemetry connection close failed ({type(exc).__name__})",
                    file=sys.stderr,
                )

    return {"results": results, "counts": counts, "cost": cost,
            "subscribers": subscribers, "telemetry_errors": telemetry_errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="Richmond Commons push alerting (P1.1a)")
    parser.add_argument("--mode", default="auto",
                        choices=["auto", "daily", "weekly", "monthly"])
    parser.add_argument("--today", default=None, help="YYYY-MM-DD override (tests)")
    parser.add_argument("--out-dir", default="alert_out")
    parser.add_argument("--open-alert-issues", type=int, default=0)
    parser.add_argument("--oldest-alert-issue", default="")
    parser.add_argument("--open-alert-issues-file", type=Path, default=None)
    args = parser.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    mode = resolve_mode(args.mode, today)

    active, expired = load_suppressions(SUPPRESSIONS_PATH, today)
    cal = calendar_state(CALENDAR_PATH, today)
    grads = pending_graduations(REVIEW_QUEUE_PATH)

    site_health = probe_public_site()
    live = collect_live_state()
    splits = split_failures(live["results"], active, expired)
    notification_state = load_notification_state(args.open_alert_issues_file)
    dead_man_armed = (
        os.environ.get("DEAD_MAN_ARMED", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    alerts = decide_alerts(
        splits, cal, live["cost"], today,
        dead_man_armed=dead_man_armed,
        notification_state=notification_state,
        site_health=site_health,
        telemetry_errors=live["telemetry_errors"],
        mode=mode,
    )
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repository = os.environ.get("GITHUB_REPOSITORY", "pjfront/richmond-common")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = (f"{server_url}/{repository}/actions/runs/{run_id}"
               if run_id else f"{server_url}/{repository}/actions")
    subject, body = compose_email(
        mode, today, alerts, splits, cal, live["cost"], live["counts"],
        live["subscribers"], grads, args.open_alert_issues,
        args.oldest_alert_issue, run_url, site_health,
    )
    send = should_send(mode, alerts)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "email_body.txt").write_text(body, encoding="utf-8")
    with (out / "issues.jsonl").open("w", encoding="utf-8") as f:
        for a in alerts:
            if a["kind"] in ISSUE_ALERT_KINDS:
                issue_body = compose_issue_body(a, today, mode, run_url)
                f.write(json.dumps({"id": a["id"],
                                    "title": _safe_operator_text(
                                        f"ACTION: {a['title']}", 240,
                                    ),
                                    "body": issue_body}) + "\n")
    recovered_alert_ids = [
        str(r["id"]) for r in live["results"]
        if r.get("status") == "pass" and r.get("id")
    ]
    if site_health.get("status") == "pass":
        recovered_alert_ids.append("public-site-health")
    if "cost" not in live["telemetry_errors"]:
        recovered_alert_ids.append(TELEMETRY_COST_ALERT_ID)
    if "subscribers" not in live["telemetry_errors"]:
        recovered_alert_ids.append(TELEMETRY_SUBSCRIBER_ALERT_ID)
    (out / "recovered_alert_ids.txt").write_text(
        "".join(
            f"{alert_id}\n" for alert_id in recovered_alert_ids
        ),
        encoding="utf-8",
    )
    with (out / "outputs.env").open("w", encoding="utf-8") as f:
        f.write(f"mode={mode}\n")
        f.write(f"send_email={'true' if send else 'false'}\n")
        f.write(f"alert_count={len(alerts)}\n")
        f.write(f"subject={subject}\n")
    (out / "alert_summary.json").write_text(json.dumps({
        "date": today.isoformat(), "mode": mode, "alerts": alerts,
        "liveness": live["counts"],
        "suppressed": [r["id"] for r in splits["suppressed"]],
        "site_health": site_health,
        "calendar": cal,
    }, indent=2, default=str), encoding="utf-8")

    print(f"mode={mode} alerts={len(alerts)} send_email={send}")
    for a in alerts:
        print(f"  ALERT: {a['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
