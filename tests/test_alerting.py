# tests/test_alerting.py
"""Unit tests for the push-alerting core (src/alerting.py, P1.1a).

Pure-function coverage only — no DB, no network. The live-collection path
(collect_live_state) is exercised by the daily workflow itself.
"""
import datetime as dt
import json
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alerting import (  # noqa: E402
    alert_issue_marker,
    build_llm_handoff,
    calendar_state,
    compose_email,
    compose_issue_body,
    decide_alerts,
    load_suppressions,
    load_notification_state,
    make_alert,
    resolve_mode,
    should_send,
    split_failures,
    validate_alert_contract,
)

TODAY = dt.date(2026, 7, 8)  # a Wednesday


def _fail(fid, severity="high", status="fail"):
    return {"id": fid, "status": status,
            "expectation": {"severity": severity, "description": f"desc {fid}",
                            "owner": "test-owner", "rationale": "test rationale"},
            "failures": [{"entity_id": "public-1", "meeting_date": "2026-07-01",
                          "detail": f"failure detail {fid}"}]}


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


class TestResolveMode:
    def test_auto_daily(self):
        assert resolve_mode("auto", dt.date(2026, 7, 8)) == "daily"     # Wed

    def test_auto_weekly_on_monday(self):
        assert resolve_mode("auto", dt.date(2026, 7, 6)) == "weekly"    # Mon

    def test_auto_monthly_on_first(self):
        assert resolve_mode("auto", dt.date(2026, 8, 1)) == "monthly"

    def test_monthly_wins_over_weekly(self):
        # 2027-02-01 is a Monday — monthly takes precedence
        assert resolve_mode("auto", dt.date(2027, 2, 1)) == "monthly"

    def test_explicit_mode_passthrough(self):
        assert resolve_mode("weekly", dt.date(2026, 7, 8)) == "weekly"


class TestSuppressions:
    def test_active_vs_expired_split(self, tmp_path):
        p = _write(tmp_path, "s.yaml", """
            suppressions:
              - id: still-good
                reason: known
                expires: 2026-12-31
              - id: lapsed
                reason: old
                expires: 2026-07-01
        """)
        active, expired = load_suppressions(p, TODAY)
        assert "still-good" in active
        assert "lapsed" in expired

    def test_missing_expiry_is_treated_as_expired(self, tmp_path):
        p = _write(tmp_path, "s.yaml", """
            suppressions:
              - id: open-ended
                reason: never do this
        """)
        active, expired = load_suppressions(p, TODAY)
        assert active == {}
        assert "open-ended" in expired

    def test_missing_file_is_empty(self, tmp_path):
        active, expired = load_suppressions(tmp_path / "nope.yaml", TODAY)
        assert (active, expired) == ({}, {})

    def test_split_failures_routes_by_suppression(self):
        results = [
            _fail("visible-high"),
            _fail("suppressed-one"),
            _fail("expired-one"),
            {"id": "passing", "status": "pass", "expectation": {}},
        ]
        splits = split_failures(
            results,
            active={"suppressed-one": {}},
            expired={"expired-one": {}},
        )
        assert [r["id"] for r in splits["visible"]] == ["visible-high"]
        assert [r["id"] for r in splits["suppressed"]] == ["suppressed-one"]
        assert [r["id"] for r in splits["expired"]] == ["expired-one"]


class TestCalendar:
    def test_overdue_due_soon_and_horizon(self, tmp_path):
        p = _write(tmp_path, "c.yaml", """
            events:
              - id: overdue-item
                due_date: 2026-07-01
                lead_days: 3
              - id: due-soon
                due_date: 2026-07-10
                lead_days: 5
              - id: far-future
                due_date: 2026-12-01
                lead_days: 7
        """)
        cal = calendar_state(p, TODAY)
        assert [e["id"] for e in cal["overdue"]] == ["overdue-item"]
        assert [e["id"] for e in cal["due_soon"]] == ["due-soon"]
        assert cal["horizon_ok"] is True  # Dec 1 is >90 days out

    def test_thin_horizon_flags(self, tmp_path):
        p = _write(tmp_path, "c.yaml", """
            events:
              - id: only-near
                due_date: 2026-08-01
                lead_days: 3
        """)
        cal = calendar_state(p, TODAY)
        assert cal["horizon_ok"] is False

    def test_completed_event_is_retained_but_not_alerted(self, tmp_path):
        p = _write(tmp_path, "c.yaml", """
            events:
              - id: completed-cap-revert
                due_date: 2026-08-01
                lead_days: 3
                completed_on: 2026-08-01
              - id: far-future
                due_date: 2027-03-20
                lead_days: 30
        """)
        cal = calendar_state(p, dt.date(2026, 8, 8))
        assert cal["overdue"] == []
        assert cal["due_soon"] == []
        assert cal["event_count"] == 1
        assert cal["completed_event_count"] == 1
        assert cal["horizon_ok"] is True

    def test_missing_calendar_is_empty_and_thin(self, tmp_path):
        cal = calendar_state(tmp_path / "nope.yaml", TODAY)
        assert cal["event_count"] == 0
        assert cal["horizon_ok"] is False


class TestDecideAlerts:
    def _cal(self, **over):
        base = {"overdue": [], "due_soon": [], "horizon_days": 200,
                "horizon_ok": True, "event_count": 4}
        base.update(over)
        return base

    def test_visible_high_alerts(self):
        splits = {"visible": [_fail("x", "high")], "suppressed": [], "expired": []}
        alerts = decide_alerts(splits, self._cal(), None, TODAY)
        assert any(a["kind"] == "liveness" and a["id"] == "x" for a in alerts)

    def test_visible_medium_does_not_alert_daily(self):
        splits = {"visible": [_fail("m", "medium")], "suppressed": [], "expired": []}
        assert decide_alerts(splits, self._cal(), None, TODAY) == []

    def test_errored_expectation_alerts_regardless_of_severity(self):
        splits = {"visible": [_fail("e", "low", status="error")],
                  "suppressed": [], "expired": []}
        alerts = decide_alerts(splits, self._cal(), None, TODAY)
        assert len(alerts) == 1

    def test_expired_suppression_escalates(self):
        splits = {"visible": [], "suppressed": [], "expired": [_fail("old", "medium")]}
        alerts = decide_alerts(splits, self._cal(), None, TODAY)
        assert alerts[0]["kind"] == "suppression_expired"

    def test_suppressed_failure_stays_quiet(self):
        splits = {"visible": [], "suppressed": [_fail("known", "high")], "expired": []}
        assert decide_alerts(splits, self._cal(), None, TODAY) == []

    def test_cost_threshold(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cost = {"mtd_total": 17.0, "cap_usd": 20.0, "top": []}
        alerts = decide_alerts(splits, self._cal(), cost, dt.date(2026, 7, 6))
        assert any(a["kind"] == "cost" for a in alerts)

    def test_cost_under_threshold_quiet(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cost = {"mtd_total": 10.0, "cap_usd": 20.0, "top": []}
        assert decide_alerts(splits, self._cal(), cost, TODAY) == []

    def test_thin_horizon_alerts(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        alerts = decide_alerts(splits, self._cal(horizon_days=30, horizon_ok=False),
                               None, dt.date(2026, 7, 6))
        assert any(a["kind"] == "calendar_horizon" for a in alerts)

    def test_thin_horizon_does_not_repeat_daily(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        alerts = decide_alerts(
            splits, self._cal(horizon_days=30, horizon_ok=False), None, TODAY,
        )
        assert not any(a["kind"] == "calendar_horizon" for a in alerts)

    def test_overdue_calendar_alerts(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = self._cal(overdue=[{"id": "cap-revert", "due_date": "2026-07-01",
                                  "days_until": -7, "owner": "operator",
                                  "response_mode": "direct",
                                  "action": "Keep the $5 cap unchanged."}])
        alerts = decide_alerts(splits, cal, None, TODAY)
        assert alerts[0]["kind"] == "calendar_overdue"

    def test_dead_man_missing_is_an_actionable_alert(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        alerts = decide_alerts(
            splits, self._cal(), None, dt.date(2026, 7, 6), dead_man_armed=False,
        )
        alert = next(a for a in alerts if a["kind"] == "monitoring")
        assert alert["action_kind"] == "direct"
        assert "HEALTHCHECKS_PING_URL" in alert["action"]
        assert "https://github.com/pjfront/richmond-common" in alert["action"]

    def test_existing_liveness_uses_bounded_bot_controlled_reminders(self):
        splits = {"visible": [_fail("x")], "suppressed": [], "expired": []}
        same_day = {
            "x": {
                "created_at": "2026-07-01T10:00:00Z",
                "notified_at": "2026-07-08",
            }
        }
        assert decide_alerts(
            splits, self._cal(), None, TODAY, notification_state=same_day,
        ) == []

        day_seven_due = {
            "x": {
                "created_at": "2026-07-01T10:00:00Z",
                "notified_at": "2026-07-04",
            }
        }
        alerts = decide_alerts(
            splits, self._cal(), None, TODAY,
            notification_state=day_seven_due,
        )
        assert [a["id"] for a in alerts] == ["x"]


class TestOperatorActionContract:
    def test_every_current_alert_kind_has_an_action(self):
        splits = {
            "visible": [_fail("live")],
            "suppressed": [],
            "expired": [{**_fail("expired"), "suppression": {
                "reason": "bounded hold", "expires": "2026-07-01",
            }}],
        }
        cal = {
            "overdue": [{"id": "late", "due_date": "2026-07-01",
                         "days_until": -7, "owner": "operator",
                         "response_mode": "direct", "action": "Do the simple step."}],
            "due_soon": [{"id": "soon", "due_date": "2026-07-13",
                          "days_until": 7, "owner": "ai",
                          "response_mode": "llm",
                          "action": "Copy the handoff into Codex."}],
            "horizon_days": 30,
            "horizon_ok": False,
            "event_count": 2,
        }
        cost = {"mtd_total": 4.5, "cap_usd": 5.0, "top": []}
        alerts = decide_alerts(
            splits, cal, cost, dt.date(2026, 7, 6), dead_man_armed=False,
        )
        assert {a["kind"] for a in alerts} == {
            "liveness", "suppression_expired", "calendar_overdue",
            "calendar_due", "cost", "calendar_horizon", "monitoring",
        }
        validate_alert_contract(alerts)
        assert all(a["action"].strip() for a in alerts)
        assert all(
            a["llm_prompt"].strip()
            for a in alerts if a["action_kind"] == "llm"
        )

    def test_contract_rejects_missing_action(self):
        with pytest.raises(ValueError, match="action"):
            validate_alert_contract([{
                "kind": "liveness", "id": "x", "title": "x", "detail": "x",
                "action_kind": "direct", "action": "",
            }])

    def test_contract_rejects_missing_llm_handoff(self):
        with pytest.raises(ValueError, match="LLM handoff"):
            validate_alert_contract([{
                "kind": "liveness", "id": "x", "title": "x", "detail": "x",
                "action_kind": "llm", "action": "copy this", "llm_prompt": "",
            }])

    def test_handoff_contains_site_context_constraints_and_alert(self):
        alert = make_alert(
            kind="liveness", alert_id="sample-check", title="Sample failed",
            detail="A safe sample failure", action_kind="llm",
            action="Copy this prompt.",
            evidence=[{"detail": "bounded evidence"}],
        )
        prompt = build_llm_handoff([alert], "https://github.com/example/run/1")
        assert "richmondcommons.org" in prompt
        assert "Richmond, California" in prompt
        assert "sample-check" in prompt
        assert "Supabase Pro" in prompt
        assert "D2 = 0.50" in prompt
        assert "Migration 134 is a HARD NO-GO" in prompt
        assert "No unbounded sync" in prompt
        assert "https://github.com/example/run/1" in prompt
        assert "{{ALERTS}}" not in prompt
        assert "{{RUN_URL}}" not in prompt
        assert "AGENTS.md" in prompt

    def test_evidence_is_bounded_and_redacted(self):
        result = _fail("private-shape")
        result["failures"] = [{
            "entity_id": "person@example.com",
            "meeting_date": "2026-07-01",
            "detail": "Authorization: Bearer secret-token " + "x" * 600,
            "ignored_secret_column": "must-not-appear",
        }] * 5
        splits = {"visible": [result], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        alert = decide_alerts(splits, cal, None, TODAY)[0]
        rendered = str(alert["evidence"])
        assert "person@example.com" not in rendered
        assert "secret-token" not in rendered
        assert "ignored_secret_column" not in rendered
        assert len(alert["evidence"]) <= 4  # 3 rows + status summary

    def test_direct_caller_evidence_redacts_common_provider_tokens(self):
        alert = make_alert(
            kind="liveness",
            alert_id="token-shapes",
            title="Credential-shaped output",
            detail="Safe summary",
            action_kind="llm",
            action="Copy the handoff.",
            evidence=[{
                "detail": (
                    "Basic abcdefghijkl ghp_1234567890abcdef "
                    "github_pat_1234567890 re_1234567890 "
                    "postgresql://user:pass@example.com/db "
                    "https://hc-ping.com/12345678-abcd-secret-ping "
                    "person@example.com ``` @operator"
                ),
                "not_allowed": "never copied",
            }],
        )
        rendered = str(alert["evidence"])
        for secret in (
            "abcdefghijkl", "ghp_1234567890abcdef",
            "github_pat_1234567890", "re_1234567890",
            "user:pass", "12345678-abcd-secret-ping",
            "person@example.com", "```", "@operator",
            "not_allowed",
        ):
            assert secret not in rendered

    def test_notification_state_ignores_generic_github_updated_at(self, tmp_path):
        state_file = tmp_path / "issues.json"
        state_file.write_text(json.dumps([{
            "title": "Pipeline check x is fail",
            "body": (
                f"{alert_issue_marker('x')}\n"
                "<!-- richmond-alert-notified:2026-07-04 -->\nACTION: copy"
            ),
            "createdAt": "2026-07-01T10:00:00Z",
            # An outside comment can change this and must not postpone mail.
            "updatedAt": "2026-07-08T09:00:00Z",
        }]), encoding="utf-8")
        state = load_notification_state(state_file)
        assert state["x"]["notified_at"] == "2026-07-04"


class TestSendPolicyAndCompose:
    def test_daily_quiet_no_email(self):
        assert should_send("daily", []) is False

    def test_daily_with_alerts_sends(self):
        assert should_send("daily", [{"kind": "liveness"}]) is True

    def test_weekly_always_sends(self):
        assert should_send("weekly", []) is True

    def test_monthly_always_sends(self):
        assert should_send("monthly", []) is True

    def test_compose_all_clear_weekly(self):
        splits = {"visible": [], "suppressed": [_fail("known", "high")], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        subject, body = compose_email(
            "weekly", TODAY, [], splits, cal,
            {"mtd_total": 13.4, "cap_usd": 20.0, "top": []},
            {"total": 30, "passing": 25, "failing": 5, "skipped": 0},
            42, {"count": 3, "oldest": []}, 0, "",
        )
        assert "status" in subject
        assert "NO NEW ACTION" in subject
        assert body.startswith("ACTION: None today")
        assert "Status only" in body
        assert "[suppressed] known" in body
        assert "$13.40 / $20.00" in body

    def test_compose_monthly_includes_summary(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        subject, body = compose_email(
            "monthly", dt.date(2026, 8, 1), [], splits, cal, None,
            {"total": 30, "passing": 30, "failing": 0, "skipped": 0},
            42, {"count": 2, "oldest": [{"id": "pac-index", "gated_at": "2026-04-29"}]},
            1, "2026-07-06T00:00:00Z",
        )
        assert "monthly status" in subject
        assert "NO NEW ACTION" in subject
        assert body.startswith("ACTION: None today")
        assert "Email subscribers: 42" in body
        assert "Pending graduations: 2" in body
        assert "pac-index" in body

    def test_compose_alert_subject_counts(self):
        splits = {"visible": [_fail("x", "high")], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        alerts = decide_alerts(splits, cal, None, TODAY)
        subject, body = compose_email(
            "daily", TODAY, alerts, splits, cal, None,
            {"total": 30, "passing": 29, "failing": 1, "skipped": 0},
            None, {"count": 0, "oldest": []}, 0, "",
        )
        assert "ACTION" in subject
        assert "1 item" in subject
        assert body.startswith("ACTION: Complete")
        assert "NEEDS ATTENTION" in body
        assert "Pipeline check x" in body
        assert "ACTION:" in body
        assert "COPY/PASTE MESSAGE FOR YOUR CODING ASSISTANT" in body
        assert "richmondcommons.org" in body

    def test_every_status_section_has_an_explicit_action_disposition(self):
        splits = {
            "visible": [_fail("high-check", "high"), _fail("medium-check", "medium")],
            "suppressed": [_fail("held-check", "medium")],
            "expired": [],
        }
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        alerts = decide_alerts(splits, cal, None, TODAY)
        _, body = compose_email(
            "monthly", TODAY, alerts, splits, cal, None,
            {"total": 30, "passing": 27, "failing": 3, "skipped": 0},
            42, {"count": 0, "oldest": []}, 0, "",
        )

        pipeline = body.split("PIPELINE LIVENESS", 1)[1].split("COST:", 1)[0]
        cost = body.split("COST:", 1)[1].split("CALENDAR:", 1)[0]
        calendar = body.split("CALENDAR:", 1)[1].split("MONTHLY SUMMARY", 1)[0]
        monthly = body.split("MONTHLY SUMMARY", 1)[1].split("\n--", 1)[0]

        assert pipeline.count("ACTION:") == 1
        assert "Follow the matching numbered item" in pipeline
        assert "medium-check" in pipeline
        assert "held-check" in pipeline
        assert cost.count("ACTION:") == 1
        assert "NO ACTION NEEDED" in cost
        assert calendar.count("ACTION:") == 1
        assert "NO ACTION NEEDED" in calendar
        assert monthly.count("ACTION:") == 1
        assert "NO ACTION NEEDED" in monthly

    def test_issue_body_carries_same_action_and_handoff(self):
        splits = {"visible": [_fail("x", "high")], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        alert = decide_alerts(splits, cal, None, TODAY)[0]
        body = compose_issue_body(alert, TODAY, "daily", "https://example/run")
        visible_lines = [
            line for line in body.splitlines()
            if line and not line.startswith("<!--")
        ]
        assert visible_lines[0].startswith("ACTION:")
        assert alert_issue_marker("x") in body
        assert "<!-- richmond-alert-notified:2026-07-08 -->" in body
        assert "Copy/paste message for your coding assistant" in body
        assert "x" in body
        assert "Evidence details are intentionally omitted" in body

    def test_public_issue_omits_private_row_evidence(self):
        alert = make_alert(
            kind="liveness", alert_id="public-safe", title="Check failed",
            detail="A production expectation failed", action_kind="llm",
            action="Copy the handoff.",
            evidence=[{"detail": "private-row-marker-8675309"}],
        )
        body = compose_issue_body(alert, TODAY, "daily", "https://example/run")
        assert "private-row-marker-8675309" not in body
