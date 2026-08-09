# tests/test_alerting.py
"""Unit tests for the push-alerting core (src/alerting.py, P1.1a).

Pure-function coverage only — no DB, no network. The live-collection path
(collect_live_state) is exercised by the daily workflow itself.
"""
import datetime as dt
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alerting import (  # noqa: E402
    calendar_state,
    compose_email,
    decide_alerts,
    load_suppressions,
    resolve_mode,
    should_send,
    split_failures,
)

TODAY = dt.date(2026, 7, 8)  # a Wednesday


def _fail(fid, severity="high", status="fail"):
    return {"id": fid, "status": status,
            "expectation": {"severity": severity, "description": f"desc {fid}"},
            "failures": []}


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
        alerts = decide_alerts(splits, self._cal(), cost, TODAY)
        assert any(a["kind"] == "cost" for a in alerts)

    def test_cost_under_threshold_quiet(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cost = {"mtd_total": 10.0, "cap_usd": 20.0, "top": []}
        assert decide_alerts(splits, self._cal(), cost, TODAY) == []

    def test_thin_horizon_alerts(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        alerts = decide_alerts(splits, self._cal(horizon_days=30, horizon_ok=False),
                               None, TODAY)
        assert any(a["kind"] == "calendar_horizon" for a in alerts)

    def test_overdue_calendar_alerts(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = self._cal(overdue=[{"id": "cap-revert", "due_date": "2026-07-01",
                                  "days_until": -7, "action": "revert it"}])
        alerts = decide_alerts(splits, cal, None, TODAY)
        assert alerts[0]["kind"] == "calendar_overdue"


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
        assert "all clear" in subject
        assert "All clear" in body
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
        assert "monthly summary" in subject
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
        assert "1 alert" in subject
        assert "NEEDS ATTENTION" in body
        assert "[liveness] x" in body
