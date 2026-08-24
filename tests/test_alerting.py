# tests/test_alerting.py
"""Unit tests for the push-alerting core (src/alerting.py, P1.1a).

Most coverage is pure and DB/network-free. The live-collection tests replace
its database and liveness dependencies with bounded fakes.
"""
import datetime as dt
import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alerting import (  # noqa: E402
    SITE_PROBE_MAX_BYTES,
    SITE_PROBE_TIMEOUT_SECONDS,
    alert_issue_marker,
    build_llm_handoff,
    calendar_state,
    compose_email,
    compose_issue_body,
    compose_monitor_issue_body,
    collect_live_state,
    decide_alerts,
    load_suppressions,
    load_notification_state,
    make_alert,
    probe_public_site,
    resolve_mode,
    _recovered_liveness_alert_ids,
    _issue_title,
    _reviewed_monitor_issue_updates,
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


class _FakeResponse:
    def __init__(self, body, status=200):
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.status = status
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status

    def read(self, limit):
        self.read_limits.append(limit)
        return self.body[:limit]


class _SequenceOpener:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request.full_url, timeout))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _site_failure(detail="homepage: timeout"):
    return {
        "status": "fail",
        "checks": [],
        "failures": [{"detail": detail}],
        "checked_endpoints": 2,
        "timeout_seconds": 10,
        "attempt_limit": 2,
        "response_cap_bytes": 64 * 1024,
    }


def _site_pass():
    return {
        "status": "pass",
        "checks": [
            {"label": "homepage", "status": "pass", "detail": "HTTP 200"},
            {"label": "api_health", "status": "pass", "detail": "healthy"},
        ],
        "failures": [],
    }


def _provider_pass():
    return {
        "schema_version": 1,
        "status": "pass",
        "coverage": "configuration_invariants_only",
        "calls_attempted": 6,
        "call_limit": 6,
        "timeout_seconds": 12,
        "response_cap_bytes": 64 * 1024,
        "checks": [
            {"id": "vercel_plan", "status": "pass",
             "detail": "Vercel account plan is Hobby."},
            {"id": "supabase_plan", "status": "pass",
             "detail": "Supabase organization plan is Pro."},
            {"id": "supabase_project_health", "status": "pass",
             "detail": "Supabase production project is healthy."},
            {"id": "supabase_quota_scope", "status": "pass",
             "detail": "Two active projects share organization quotas."},
            {"id": "supabase_paid_addons", "status": "pass",
             "detail": "No paid add-on is selected."},
            {"id": "supabase_preview_branches", "status": "pass",
             "detail": "No Preview branch is running."},
        ],
        "manual_usage_required": True,
    }


def _provider_failure():
    return {
        "status": "fail",
        "coverage": "configuration_invariants_only",
        "checks": [{
            "id": "vercel_plan",
            "status": "fail",
            "detail": "Vercel read failed (HTTP 401).",
        }],
        "manual_usage_required": True,
    }


class TestPublicSiteProbe:
    def test_two_endpoints_pass_with_fixed_timeout_and_size_cap(self):
        homepage = _FakeResponse("<title>Richmond Commons</title>")
        health = _FakeResponse('{"status":"healthy","private":"do-not-copy"}')
        opener = _SequenceOpener(homepage, health)

        result = probe_public_site(
            "https://richmondcommons.org/",
            "https://richmondcommons.org/api/health",
            opener=opener,
            sleeper=lambda _: None,
        )

        assert result["status"] == "pass"
        assert opener.calls == [
            ("https://richmondcommons.org/", SITE_PROBE_TIMEOUT_SECONDS),
            (
                "https://richmondcommons.org/api/health",
                SITE_PROBE_TIMEOUT_SECONDS,
            ),
        ]
        assert homepage.read_limits == [SITE_PROBE_MAX_BYTES]
        assert health.read_limits == [SITE_PROBE_MAX_BYTES]
        assert "do-not-copy" not in str(result)
        assert "body" not in str(result)

    def test_transient_failure_retries_once(self):
        homepage = _FakeResponse("Richmond Commons")
        health = _FakeResponse('{"status":"healthy"}')
        opener = _SequenceOpener(
            TimeoutError("private provider detail"), homepage, health,
        )
        sleeps = []

        result = probe_public_site(
            opener=opener,
            sleeper=sleeps.append,
        )

        assert result["status"] == "pass"
        assert len(opener.calls) == 3
        assert sleeps == [1]
        assert result["checks"][0]["attempts"] == 2

    def test_permanent_failure_becomes_safe_result_and_still_checks_api(self):
        private = "postgresql://user:password@example.invalid/db"
        health = _FakeResponse('{"status":"healthy"}')
        opener = _SequenceOpener(
            TimeoutError(private), TimeoutError(private), health,
        )

        result = probe_public_site(opener=opener, sleeper=lambda _: None)

        assert result["status"] == "fail"
        assert len(opener.calls) == 3
        assert result["checks"][0]["attempts"] == 2
        assert result["checks"][1]["status"] == "pass"
        assert private not in str(result)
        assert "password" not in str(result)

    def test_degraded_api_reports_only_bounded_status(self):
        homepage = _FakeResponse("Richmond Commons")
        health = _FakeResponse(
            '{"status":"degraded","private":"resident@example.com"}'
        )

        result = probe_public_site(
            opener=_SequenceOpener(homepage, health),
            sleeper=lambda _: None,
        )

        assert result["status"] == "fail"
        assert "status=degraded" in str(result)
        assert "resident@example.com" not in str(result)

    def test_nested_api_status_never_reaches_alert_evidence(self):
        private = "resident@example.com"
        result = probe_public_site(
            opener=_SequenceOpener(
                _FakeResponse("Richmond Commons"),
                _FakeResponse(
                    '{"status":{"private":"resident@example.com"}}'
                ),
            ),
            sleeper=lambda _: None,
        )

        assert result["status"] == "fail"
        assert "invalid or missing status" in str(result)
        assert private not in str(result)

    @pytest.mark.parametrize(
        ("homepage_body", "health_body", "expected"),
        [
            ("unexpected site", '{"status":"healthy"}', "page marker"),
            ("Richmond Commons", "not-json", "not valid bounded JSON"),
        ],
    )
    def test_invalid_content_fails_without_raising(
        self, homepage_body, health_body, expected,
    ):
        result = probe_public_site(
            opener=_SequenceOpener(
                _FakeResponse(homepage_body), _FakeResponse(health_body),
            ),
            sleeper=lambda _: None,
        )

        assert result["status"] == "fail"
        assert expected in str(result)


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


class TestLiveTelemetryCollection:
    class _Cursor:
        def __init__(self, row=(12,), error=None):
            self.row = row
            self.error = error

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, _query):
            if self.error:
                raise self.error

        def fetchone(self):
            return self.row

    class _Connection:
        def __init__(self, cursor):
            self._cursor = cursor
            self.closed = False

        def cursor(self):
            return self._cursor

        def close(self):
            self.closed = True

    @staticmethod
    def _patch_liveness(monkeypatch):
        monkeypatch.setattr("pipeline_map.load_manifest", lambda: {"expectations": []})
        monkeypatch.setattr("pipeline_map.run_liveness_checks", lambda _items: [])

    def test_cost_failure_does_not_erase_available_subscriber_count(
        self, monkeypatch,
    ):
        self._patch_liveness(monkeypatch)
        conn = self._Connection(self._Cursor(row=(12,)))
        monkeypatch.setattr("db.get_connection", lambda: conn)
        monkeypatch.setattr("cost_digest.compact_mtd_summary", lambda _conn: None)

        state = collect_live_state()

        assert state["cost"] is None
        assert state["subscribers"] == 12
        assert state["telemetry_errors"] == {"cost": "ValueError"}
        assert conn.closed is True

    def test_connection_failure_marks_both_telemetry_surfaces_without_detail(
        self, monkeypatch, capsys,
    ):
        self._patch_liveness(monkeypatch)

        class PrivateConnectionError(Exception):
            pass

        def fail_connection():
            raise PrivateConnectionError("postgresql://user:secret@example.invalid/db")

        monkeypatch.setattr("db.get_connection", fail_connection)

        state = collect_live_state()
        stderr = capsys.readouterr().err

        assert state["telemetry_errors"] == {
            "cost": "PrivateConnectionError",
            "subscribers": "PrivateConnectionError",
        }
        assert "postgresql://" not in stderr
        assert "secret" not in stderr

    def test_provider_reads_are_opt_in_for_the_monthly_caller(
        self, monkeypatch,
    ):
        self._patch_liveness(monkeypatch)
        conn = self._Connection(self._Cursor(row=(12,)))
        monkeypatch.setattr("db.get_connection", lambda: conn)
        monkeypatch.setattr(
            "cost_digest.compact_mtd_summary",
            lambda _conn: {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
        )
        calls = []
        monkeypatch.setattr(
            "provider_capacity.collect_provider_capacity",
            lambda: calls.append("monthly") or _provider_pass(),
        )

        daily = collect_live_state()
        monthly = collect_live_state(include_provider_capacity=True)

        assert daily["provider_capacity"] is None
        assert monthly["provider_capacity"] == _provider_pass()
        assert calls == ["monthly"]


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
                owner: ai
                response_mode: llm
                source_url: https://example.org/overdue
                action: Copy the handoff.
              - id: due-soon
                due_date: 2026-07-10
                lead_days: 5
                owner: operator
                response_mode: direct
                source_url: https://example.org/due-soon
                action: Open the source and review it.
              - id: far-future
                due_date: 2026-12-01
                lead_days: 7
                owner: ai
                response_mode: llm
                source_url: https://example.org/future
                action: Copy the handoff.
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
                owner: operator
                response_mode: direct
                source_url: https://example.org/near
                action: Open the source and review it.
        """)
        cal = calendar_state(p, TODAY)
        assert cal["horizon_ok"] is False

    def test_completed_event_is_retained_but_not_alerted(self, tmp_path):
        p = _write(tmp_path, "c.yaml", """
            events:
              - id: completed-cap-revert
                due_date: 2026-08-01
                lead_days: 3
                owner: operator
                completed_on: 2026-08-01
              - id: far-future
                due_date: 2027-03-20
                lead_days: 30
                owner: ai
                response_mode: llm
                source_url: https://example.org/future
                action: Copy the handoff.
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
        assert cal["occurrence_count"] == 0
        assert cal["horizon_ok"] is False

    def test_annual_rule_uses_override_and_stable_occurrence_id(self, tmp_path):
        p = _write(tmp_path, "c.yaml", """
            recurring_events:
              - id: semiannual-review
                rule:
                  frequency: annual
                  month: 1
                  day: 31
                  overrides:
                    "2027": 2027-02-01
                lead_days: 60
                owner: ai
                response_mode: llm
                source_url: https://example.org/official
                action: Copy the handoff and verify the official date.
        """)
        cal = calendar_state(p, dt.date(2026, 12, 15))
        assert [e["id"] for e in cal["due_soon"]] == [
            "semiannual-review--2027"
        ]
        assert cal["due_soon"][0]["due_date"] == "2027-02-01"
        assert cal["due_soon"][0]["series_id"] == "semiannual-review"
        assert cal["occurrence_count"] == 2  # 2027 and 2028 only
        assert cal["event_count"] == 1
        assert cal["horizon_ok"] is True

    def test_annual_expansion_is_bounded_to_four_occurrences(self, tmp_path):
        p = _write(tmp_path, "c.yaml", """
            recurring_events:
              - id: year-end-review
                rule:
                  frequency: annual
                  month: 12
                  day: 31
                lead_days: 30
                owner: ai
                response_mode: llm
                source_url: https://example.org/official
                action: Copy the handoff.
        """)
        cal = calendar_state(p, dt.date(2026, 1, 1))
        assert cal["occurrence_count"] == 4
        assert [event["id"] for event in cal["overdue"]] == [
            "year-end-review--2025"
        ]
        assert cal["horizon_days"] == (dt.date(2028, 12, 31) - dt.date(2026, 1, 1)).days

    def test_july_series_starts_in_2027_without_retroactive_alert(self):
        path = (
            Path(__file__).parent.parent
            / "docs"
            / "scheduled_civic_events.yaml"
        )
        august_2026 = dt.date(2026, 8, 30)
        calendar = calendar_state(path, august_2026)
        visible_occurrences = calendar["overdue"] + calendar["due_soon"]
        assert not any(
            event["id"] == "form-460-july-semiannual-review--2026"
            for event in visible_occurrences
        )
        alerts = decide_alerts(
            {"visible": [], "suppressed": [], "expired": []},
            calendar,
            None,
            august_2026,
        )
        assert not any(
            alert["id"] == "form-460-july-semiannual-review--2026"
            for alert in alerts
        )

        july_2027 = calendar_state(path, dt.date(2027, 7, 1))
        assert any(
            event["id"] == "form-460-july-semiannual-review--2027"
            for event in july_2027["due_soon"]
        )

    def test_old_recurring_occurrence_rolls_off_after_thirty_days(self, tmp_path):
        p = _write(tmp_path, "c.yaml", """
            recurring_events:
              - id: april-review
                rule:
                  frequency: annual
                  month: 4
                  day: 1
                lead_days: 30
                owner: ai
                response_mode: llm
                source_url: https://example.org/official
                action: Copy the handoff.
        """)
        assert [event["id"] for event in calendar_state(
            p, dt.date(2026, 4, 2),
        )["overdue"]] == ["april-review--2026"]
        rolled = calendar_state(p, dt.date(2026, 5, 2))
        assert rolled["overdue"] == []
        assert all(
            event_id != "april-review--2026"
            for event_id in [event["id"] for event in rolled["due_soon"]]
        )

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("action", "", "action"),
            ("response_mode", "email", "response_mode"),
            ("source_url", "http://example.org", "source_url"),
        ],
    )
    def test_active_item_contract_fails_closed(
        self, tmp_path, field, value, error,
    ):
        event = {
            "id": "review-item",
            "due_date": "2026-12-01",
            "lead_days": 7,
            "owner": "ai",
            "response_mode": "llm",
            "source_url": "https://example.org/official",
            "action": "Copy the handoff.",
        }
        event[field] = value
        p = tmp_path / "c.yaml"
        p.write_text(yaml.safe_dump({"events": [event]}), encoding="utf-8")
        with pytest.raises(ValueError, match=error):
            calendar_state(p, TODAY)

    @pytest.mark.parametrize(
        "rule",
        [
            {"frequency": "monthly", "month": 4, "day": 1},
            {"frequency": "annual", "month": 2, "day": 29},
            {"frequency": "annual", "month": 4, "day": 1,
             "timezone": "America/Los_Angeles"},
            {"frequency": "annual", "month": 1, "day": 31,
             "overrides": {"2027": "2028-01-31"}},
        ],
    )
    def test_unsupported_or_invalid_recurrence_fails_closed(
        self, tmp_path, rule,
    ):
        p = tmp_path / "c.yaml"
        p.write_text(yaml.safe_dump({"recurring_events": [{
            "id": "annual-review", "rule": rule, "lead_days": 30,
            "owner": "ai", "response_mode": "llm",
            "source_url": "https://example.org/official",
            "action": "Copy the handoff.",
        }]}), encoding="utf-8")
        with pytest.raises(ValueError):
            calendar_state(p, TODAY)

    @pytest.mark.parametrize("start_year", [True, "2027", 999, 10_000])
    def test_invalid_start_year_fails_closed(self, tmp_path, start_year):
        p = tmp_path / "c.yaml"
        p.write_text(yaml.safe_dump({"recurring_events": [{
            "id": "future-review",
            "rule": {
                "frequency": "annual", "month": 7, "day": 31,
                "start_year": start_year,
            },
            "lead_days": 30, "owner": "ai", "response_mode": "llm",
            "source_url": "https://example.org/official",
            "action": "Copy the handoff.",
        }]}), encoding="utf-8")
        with pytest.raises(ValueError, match="four-digit integer"):
            calendar_state(p, TODAY)

    def test_override_before_start_year_fails_closed(self, tmp_path):
        p = _write(tmp_path, "c.yaml", """
            recurring_events:
              - id: future-review
                rule:
                  frequency: annual
                  month: 7
                  day: 31
                  start_year: 2027
                  overrides:
                    "2026": 2026-08-03
                lead_days: 30
                owner: ai
                response_mode: llm
                source_url: https://example.org/official
                action: Copy the handoff.
        """)
        with pytest.raises(ValueError, match="earlier than start_year"):
            calendar_state(p, TODAY)

    def test_duplicate_base_ids_fail_closed(self, tmp_path):
        p = _write(tmp_path, "c.yaml", """
            events:
              - id: same-id
                due_date: 2026-12-01
                owner: ai
                response_mode: llm
                source_url: https://example.org/one
                action: Copy the handoff.
            recurring_events:
              - id: same-id
                rule: {frequency: annual, month: 4, day: 1}
                owner: ai
                response_mode: llm
                source_url: https://example.org/two
                action: Copy the handoff.
        """)
        with pytest.raises(ValueError, match="duplicate id"):
            calendar_state(p, TODAY)

    def test_calendar_alert_carries_source_and_copy_ready_handoff(self):
        calendar = calendar_state(
            Path(__file__).parent.parent / "docs" / "scheduled_civic_events.yaml",
            dt.date(2026, 9, 24),
        )
        alerts = decide_alerts(
            {"visible": [], "suppressed": [], "expired": []},
            calendar,
            None,
            dt.date(2026, 9, 24),
        )
        alert = next(
            item for item in alerts
            if item["id"] == "nov-2026-form-460-first-preelection"
        )
        assert alert["action_kind"] == "llm"
        assert "richmondca.gov/DocumentCenter/View/78447" in str(alert["evidence"])
        assert "COPY/PASTE" not in alert["llm_prompt"]
        assert "Requested operator action" in alert["llm_prompt"]

    def test_domain_reminder_alerts_at_lead_day_with_direct_steps(self):
        today = dt.date(2027, 2, 10)  # 45 days before the RDAP expiry date
        calendar = calendar_state(
            Path(__file__).parent.parent / "docs" / "scheduled_civic_events.yaml",
            today,
        )
        alerts = decide_alerts(
            {"visible": [], "suppressed": [], "expired": []},
            calendar,
            None,
            today,
        )
        alert = next(
            item for item in alerts
            if item["id"] == "richmondcommons-domain-renewal"
        )
        assert alert["action_kind"] == "direct"
        assert "https://dash.cloudflare.com/" in alert["action"]
        assert "auto-renew is On" in alert["action"]
        assert alert["llm_prompt"] == ""


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

    def test_reviewed_expired_dates_are_status_only_until_they_pass(self):
        reviewed = _fail(
            "past_meetings_have_transcript_recap_within_5_days", "medium"
        )
        reviewed["failures"] = [
            {"meeting_date": "2026-07-07", "detail": "known gap"},
            {"meeting_date": "2026-07-21", "detail": "known gap"},
        ]
        reviewed["suppression"] = {
            "reason": "reviewed",
            "expires": "2026-08-15",
            "post_expiry": "monitor_exact_meeting_dates_until_pass",
            "monitor_only_meeting_dates": [
                dt.date(2026, 7, 7),
                dt.date(2026, 7, 21),
                dt.date(2026, 7, 28),
            ],
        }
        splits = {"visible": [], "suppressed": [], "expired": [reviewed]}
        open_issue = {
            "past_meetings_have_transcript_recap_within_5_days": {
                "created_at": "2026-07-01T10:00:00Z",
                "notified_at": "2026-07-01",
            }
        }

        assert decide_alerts(
            splits, self._cal(), None, TODAY, notification_state=open_issue,
        ) == []

        _, body = compose_email(
            "weekly", TODAY, [], splits, self._cal(),
            {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
            {"total": 1, "passing": 0, "failing": 1, "skipped": 0},
            2, {"count": 0, "oldest": []}, 0, "",
            notification_state=open_issue,
        )
        assert body.startswith("ACTION: None today")
        assert (
            "[reviewed, monitor-until-pass] "
            "past_meetings_have_transcript_recap_within_5_days" in body
        )
        assert "replaces any earlier alert action" in body
        assert "proposed dated suppression" not in body

    def test_reviewed_expired_monitor_fails_closed_for_a_new_meeting(self):
        reviewed = _fail(
            "past_meetings_have_transcript_recap_within_5_days", "medium"
        )
        reviewed["failures"] = [
            {"meeting_date": "2026-07-07", "detail": "known gap"},
            {"meeting_date": "2026-08-04", "detail": "new gap"},
        ]
        reviewed["suppression"] = {
            "post_expiry": "monitor_exact_meeting_dates_until_pass",
            "monitor_only_meeting_dates": [
                "2026-07-07", "2026-07-21", "2026-07-28",
            ],
        }
        splits = {"visible": [], "suppressed": [], "expired": [reviewed]}
        open_issue = {
            "past_meetings_have_transcript_recap_within_5_days": {
                "created_at": "2026-07-01T10:00:00Z",
                "notified_at": "2026-07-01",
            }
        }

        alerts = decide_alerts(
            splits, self._cal(), None, TODAY, notification_state=open_issue,
        )
        assert [alert["kind"] for alert in alerts] == ["suppression_expired"]

    def test_broken_monitor_bypasses_old_issue_reminder_cadence(self):
        expectation_id = "past_meetings_have_transcript_recap_within_5_days"
        reviewed = _fail(expectation_id, "medium")
        reviewed["failures"] = [
            {"meeting_date": "2026-08-04", "detail": "new gap"},
        ]
        reviewed["suppression"] = {
            "post_expiry": "monitor_exact_meeting_dates_until_pass",
            "monitor_only_meeting_dates": [
                "2026-07-07", "2026-07-21", "2026-07-28",
            ],
        }
        recent_status = {
            expectation_id: {
                "created_at": "2026-07-08T06:00:00Z",
                "notified_at": "2026-07-08",
                "monitor_only": "true",
            }
        }

        alerts = decide_alerts(
            {"visible": [], "suppressed": [], "expired": [reviewed]},
            self._cal(), None, TODAY, notification_state=recent_status,
        )

        assert [alert["kind"] for alert in alerts] == ["suppression_expired"]

    @pytest.mark.parametrize(
        "mutation",
        [
            "no-open-issue",
            "unrelated-expectation",
            "malformed-date",
            "error-status",
            "wrong-configured-cohort",
        ],
    )
    def test_reviewed_expired_monitor_fails_closed_outside_exact_state(
        self, mutation,
    ):
        expectation_id = "past_meetings_have_transcript_recap_within_5_days"
        reviewed = _fail(expectation_id, "medium")
        reviewed["failures"] = [
            {"meeting_date": "2026-07-07", "detail": "known gap"},
        ]
        reviewed["suppression"] = {
            "post_expiry": "monitor_exact_meeting_dates_until_pass",
            "monitor_only_meeting_dates": [
                "2026-07-07", "2026-07-21", "2026-07-28",
            ],
        }
        open_issue = {
            expectation_id: {
                "created_at": "2026-07-01T10:00:00Z",
                "notified_at": "2026-07-01",
            }
        }
        if mutation == "no-open-issue":
            open_issue = {}
        elif mutation == "unrelated-expectation":
            reviewed["id"] = "another_expectation"
        elif mutation == "malformed-date":
            reviewed["failures"][0]["meeting_date"] = "07/07/2026"
        elif mutation == "error-status":
            reviewed["status"] = "error"
        elif mutation == "wrong-configured-cohort":
            reviewed["suppression"]["monitor_only_meeting_dates"] = [
                "2026-07-07",
            ]
        splits = {"visible": [], "suppressed": [], "expired": [reviewed]}

        alerts = decide_alerts(
            splits, self._cal(), None, TODAY, notification_state=open_issue,
        )
        assert [alert["kind"] for alert in alerts] == ["suppression_expired"]

    def test_reviewed_pass_closes_issue_then_same_dates_recur_actionably(self):
        expectation_id = "past_meetings_have_transcript_recap_within_5_days"
        assert _recovered_liveness_alert_ids([
            {"id": expectation_id, "status": "pass"},
        ]) == [expectation_id]

        recurrence = _fail(expectation_id, "medium")
        recurrence["failures"] = [
            {"meeting_date": "2026-07-07", "detail": "recurred"},
        ]
        recurrence["suppression"] = {
            "post_expiry": "monitor_exact_meeting_dates_until_pass",
            "monitor_only_meeting_dates": [
                "2026-07-07", "2026-07-21", "2026-07-28",
            ],
        }
        splits = {"visible": [], "suppressed": [], "expired": [recurrence]}

        alerts = decide_alerts(
            splits, self._cal(), None, TODAY, notification_state={},
        )
        assert [alert["kind"] for alert in alerts] == ["suppression_expired"]

    def test_reviewed_monitor_refreshes_open_issue_without_action_timestamp(self):
        expectation_id = "past_meetings_have_transcript_recap_within_5_days"
        reviewed = _fail(expectation_id, "medium")
        reviewed["failures"] = [
            {"meeting_date": "2026-07-07", "detail": "known gap"},
        ]
        reviewed["suppression"] = {
            "post_expiry": "monitor_exact_meeting_dates_until_pass",
            "monitor_only_meeting_dates": [
                "2026-07-07", "2026-07-21", "2026-07-28",
            ],
        }
        state = {
            expectation_id: {
                "created_at": "2026-07-01T10:00:00Z",
                "notified_at": "2026-07-01",
            }
        }
        updates = _reviewed_monitor_issue_updates(
            {"visible": [], "suppressed": [], "expired": [reviewed]}, state,
        )

        assert [update["kind"] for update in updates] == ["monitor_only"]
        body = compose_monitor_issue_body(updates[0])
        assert body.startswith("<!-- richmond-alert-key:")
        assert "ACTION: None" in body
        assert "one or more gaps only within the reviewed" in body
        assert "no later meeting is failing" in body
        assert "Only the July 7" not in body
        assert "replaces the issue's earlier action" in body
        assert "richmond-alert-notified" not in body
        assert _issue_title(updates[0]).startswith("ACTION: None —")

        state[expectation_id]["monitor_only"] = "true"
        assert _reviewed_monitor_issue_updates(
            {"visible": [], "suppressed": [], "expired": [reviewed]}, state,
        ) == []

    def test_suppressed_failure_stays_quiet(self):
        splits = {"visible": [], "suppressed": [_fail("known", "high")], "expired": []}
        assert decide_alerts(splits, self._cal(), None, TODAY) == []

    def test_cost_threshold_is_status_only(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cost = {"mtd_total": 17.0, "cap_usd": 20.0, "top": []}
        alerts = decide_alerts(splits, self._cal(), cost, dt.date(2026, 7, 6))
        assert not any(a["kind"] == "cost" for a in alerts)

    def test_cost_under_threshold_quiet(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cost = {"mtd_total": 10.0, "cap_usd": 20.0, "top": []}
        assert decide_alerts(splits, self._cal(), cost, TODAY) == []

    def test_cost_telemetry_failure_is_actionable_only_weekly_or_monthly(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        weekday = decide_alerts(
            splits, self._cal(), None, TODAY,
            telemetry_errors={"cost": "OperationalError"},
        )
        monday = decide_alerts(
            splits, self._cal(), None, dt.date(2026, 7, 6),
            telemetry_errors={"cost": "OperationalError"},
        )
        forced_weekly = decide_alerts(
            splits, self._cal(), None, TODAY,
            telemetry_errors={"cost": "OperationalError"}, mode="weekly",
        )

        assert weekday == []
        assert [a["id"] for a in monday] == ["cost-telemetry-unavailable"]
        assert [a["id"] for a in forced_weekly] == [
            "cost-telemetry-unavailable"
        ]
        assert monday[0]["kind"] == "telemetry"
        assert monday[0]["action_kind"] == "llm"
        assert "read-only diagnosis" in monday[0]["action"]

    def test_subscriber_telemetry_failure_is_actionable_monthly_only(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        monday = decide_alerts(
            splits, self._cal(), None, dt.date(2026, 7, 6),
            telemetry_errors={"subscribers": "OperationalError"},
        )
        month_start = decide_alerts(
            splits, self._cal(), {"mtd_total": 0, "cap_usd": 5, "top": []},
            dt.date(2026, 8, 1),
            telemetry_errors={"subscribers": "OperationalError"},
            provider_capacity=_provider_pass(),
        )
        forced_monthly = decide_alerts(
            splits, self._cal(), {"mtd_total": 0, "cap_usd": 5, "top": []},
            TODAY, telemetry_errors={"subscribers": "OperationalError"},
            mode="monthly",
            provider_capacity=_provider_pass(),
        )

        assert monday == []
        assert [a["id"] for a in month_start] == [
            "subscriber-telemetry-unavailable",
            "monthly-provider-usage-review",
        ]
        assert [a["id"] for a in forced_monthly] == [
            "subscriber-telemetry-unavailable",
            "monthly-provider-usage-review",
        ]
        assert month_start[0]["action_kind"] == "llm"
        assert "Do not edit subscriber rows" in month_start[0]["action"]
        assert "does not itself change any subscription or send any email" in (
            month_start[0]["detail"]
        )

    def test_monthly_provider_pass_requires_direct_dashboard_review(self):
        alerts = decide_alerts(
            {"visible": [], "suppressed": [], "expired": []},
            self._cal(),
            {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
            dt.date(2026, 8, 1),
            provider_capacity=_provider_pass(),
        )

        assert [alert["id"] for alert in alerts] == [
            "monthly-provider-usage-review"
        ]
        assert alerts[0]["action_kind"] == "direct"
        assert "By the 7th" in alerts[0]["action"]
        assert "below 75%" in alerts[0]["action"]

    def test_monthly_provider_failure_has_safe_llm_handoff(self):
        alerts = decide_alerts(
            {"visible": [], "suppressed": [], "expired": []},
            self._cal(),
            {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
            dt.date(2026, 8, 1),
            provider_capacity=_provider_failure(),
        )

        assert [alert["id"] for alert in alerts] == [
            "provider-capacity-unavailable-or-drifted"
        ]
        assert alerts[0]["action_kind"] == "llm"
        assert "Do not upgrade" in alerts[0]["action"]
        assert "richmondcommons.org" in alerts[0]["llm_prompt"]

    def test_incomplete_claimed_pass_fails_closed_as_misleading_coverage(self):
        incomplete = _provider_pass()
        incomplete["checks"] = incomplete["checks"][:-1]

        alerts = decide_alerts(
            {"visible": [], "suppressed": [], "expired": []},
            self._cal(),
            {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
            dt.date(2026, 8, 1),
            provider_capacity=incomplete,
        )

        assert [alert["id"] for alert in alerts] == [
            "provider-capacity-unavailable-or-drifted"
        ]

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

    def test_site_failure_is_an_actionable_llm_alert(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        alerts = decide_alerts(
            splits, self._cal(), None, TODAY,
            site_health=_site_failure(),
        )

        assert [a["kind"] for a in alerts] == ["site_health"]
        assert alerts[0]["id"] == "public-site-health"
        assert alerts[0]["action_kind"] == "llm"
        assert "Open https://richmondcommons.org/ once" in alerts[0]["action"]
        assert alerts[0]["llm_prompt"].strip()

    def test_passing_site_is_quiet(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        assert decide_alerts(
            splits, self._cal(), None, TODAY, site_health=_site_pass(),
        ) == []

    def test_site_failure_uses_bounded_reminder_cadence(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        state = {
            "public-site-health": {
                "created_at": "2026-07-08T06:00:00Z",
                "notified_at": "2026-07-08",
            }
        }
        assert decide_alerts(
            splits, self._cal(), None, TODAY,
            notification_state=state,
            site_health=_site_failure(),
        ) == []

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
        alerts = decide_alerts(
            splits, cal, None, dt.date(2026, 7, 6), dead_man_armed=False,
            site_health=_site_failure(),
            telemetry_errors={"cost": "OperationalError"},
        )
        assert {a["kind"] for a in alerts} == {
            "liveness", "suppression_expired", "calendar_overdue",
            "calendar_due", "telemetry", "calendar_horizon", "monitoring",
            "site_health",
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
        assert "CLAUDE.md" in prompt
        assert ".claude/rules/judgment-boundaries.md" in prompt
        assert "AGENTS.md" not in prompt
        assert ".Codex/" not in prompt

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
        assert state["x"]["monitor_only"] == "false"

    def test_notification_state_recognizes_monitor_only_issue_body(self, tmp_path):
        state_file = tmp_path / "issues.json"
        state_file.write_text(json.dumps([{
            "title": "STATUS: reviewed gap",
            "body": (
                f"{alert_issue_marker('reviewed')}\n"
                "<!-- richmond-alert-status:monitor-only -->\n"
                "ACTION: None"
            ),
            "createdAt": "2026-07-01T10:00:00Z",
        }]), encoding="utf-8")

        state = load_notification_state(state_file)

        assert state["reviewed"]["monitor_only"] == "true"
        assert state["reviewed"]["notified_at"] == "2026-07-01T10:00:00Z"


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
        provider = _provider_pass()
        alerts = decide_alerts(
            splits, cal, {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
            dt.date(2026, 8, 1), provider_capacity=provider,
        )
        subject, body = compose_email(
            "monthly", dt.date(2026, 8, 1), alerts, splits, cal,
            {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
            {"total": 30, "passing": 30, "failing": 0, "skipped": 0},
            42, {"count": 2, "oldest": [{"id": "pac-index", "gated_at": "2026-04-29"}]},
            1, "2026-07-06T00:00:00Z",
            provider_capacity=provider,
        )
        assert "ACTION" in subject
        assert body.startswith("ACTION: Complete")
        assert "five-minute monthly Vercel and Supabase usage check" in body
        assert "Email subscribers: 42" in body
        assert "Pending graduations: 2" in body
        assert "pac-index" in body
        assert "LLM API COST:" in body
        assert "PROVIDER USAGE AND LIMITS" in body

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
        provider = _provider_pass()
        alerts = decide_alerts(
            splits, cal, None, TODAY,
            mode="monthly", provider_capacity=provider,
        )
        _, body = compose_email(
            "monthly", TODAY, alerts, splits, cal,
            {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
            {"total": 30, "passing": 27, "failing": 3, "skipped": 0},
            42, {"count": 0, "oldest": []}, 0, "",
            site_health=_site_pass(),
            provider_capacity=provider,
        )

        pipeline = body.split("PIPELINE LIVENESS", 1)[1].split("SITE HEALTH", 1)[0]
        site = body.split("SITE HEALTH", 1)[1].split("LLM API COST:", 1)[0]
        cost = body.split("LLM API COST:", 1)[1].split(
            "\nPROVIDER USAGE AND LIMITS\n", 1
        )[0]
        provider_section = body.split("\nPROVIDER USAGE AND LIMITS\n", 1)[1].split(
            "CALENDAR:", 1
        )[0]
        calendar = body.split("CALENDAR:", 1)[1].split("MONTHLY SUMMARY", 1)[0]
        monthly = body.split("MONTHLY SUMMARY", 1)[1].split("\n--", 1)[0]

        assert pipeline.count("ACTION:") == 1
        assert "Follow the matching numbered item" in pipeline
        assert "medium-check" in pipeline
        assert "held-check" in pipeline
        assert site.count("ACTION:") == 1
        assert "NO ACTION NEEDED" in site
        assert "api_health" in site
        assert cost.count("ACTION:") == 1
        assert "NO ACTION NEEDED" in cost
        assert provider_section.count("ACTION:") == 1
        assert "five-minute monthly usage item" in provider_section
        assert "below 75%" in provider_section
        assert "below 80%" not in provider_section
        assert "COPY/PASTE MESSAGE FOR PROVIDER USAGE HELP" in provider_section
        assert calendar.count("ACTION:") == 1
        assert "NO ACTION NEEDED" in calendar
        assert monthly.count("ACTION:") == 1
        assert "NO ACTION NEEDED" in monthly

    def test_near_cap_is_a_truthful_status_not_an_action_alert(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        subject, body = compose_email(
            "weekly", dt.date(2026, 7, 6), [], splits, cal,
            {"mtd_total": 4.5, "cap_usd": 5.0, "top": []},
            {"total": 30, "passing": 30, "failing": 0, "skipped": 0},
            42, {"count": 0, "oldest": []}, 0, "",
        )

        assert "NO ACTION — capped spend status" in subject
        assert body.startswith("ACTION: None")
        assert "NEEDS ATTENTION" not in body
        cost = body.split("COST:", 1)[1].split("CALENDAR:", 1)[0]
        assert cost.count("ACTION:") == 1
        assert "leave the cap unchanged" in cost
        assert "Do nothing now" not in body

    def test_unavailable_daily_cost_never_claims_spend_is_under_threshold(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        _, body = compose_email(
            "daily", TODAY, [], splits, cal, None,
            {"total": 30, "passing": 30, "failing": 0, "skipped": 0},
            None, {"count": 0, "oldest": []}, 0, "",
        )

        assert "spend under threshold" not in body
        assert "Cost telemetry is reviewed in the weekly or monthly summary" in body

    def test_unavailable_cost_has_numbered_action_and_handoff(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        alerts = decide_alerts(
            splits, cal, None, dt.date(2026, 7, 6),
            telemetry_errors={"cost": "OperationalError"},
        )
        subject, body = compose_email(
            "weekly", dt.date(2026, 7, 6), alerts, splits, cal, None,
            {"total": 30, "passing": 30, "failing": 0, "skipped": 0},
            42, {"count": 0, "oldest": []}, 0, "",
        )

        assert "ACTION" in subject
        assert "The scheduled LLM API cost check" in body
        cost = body.split("COST:", 1)[1].split("CALENDAR:", 1)[0]
        assert "Follow the matching numbered item" in cost
        assert "COPY/PASTE MESSAGE FOR YOUR CODING ASSISTANT" in body

    def test_unavailable_monthly_subscriber_count_has_numbered_action(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        day = dt.date(2026, 8, 1)
        cost = {"mtd_total": 1.0, "cap_usd": 5.0, "top": []}
        alerts = decide_alerts(
            splits, cal, cost, day,
            telemetry_errors={"subscribers": "OperationalError"},
            provider_capacity=_provider_pass(),
        )
        _, body = compose_email(
            "monthly", day, alerts, splits, cal, cost,
            {"total": 30, "passing": 30, "failing": 0, "skipped": 0},
            None, {"count": 0, "oldest": []}, 0, "",
            provider_capacity=_provider_pass(),
        )

        monthly = body.split("MONTHLY SUMMARY", 1)[1].split("\n--", 1)[0]
        assert "Follow the matching numbered item" in monthly
        assert "Email subscribers: unavailable" in monthly

    @pytest.mark.parametrize(
        ("mode", "cost", "subscribers", "expected"),
        [
            ("weekly", None, 42, "cost telemetry"),
            (
                "monthly",
                {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
                None,
                "subscriber telemetry",
            ),
        ],
    )
    def test_periodic_summary_fails_closed_without_matching_telemetry_alert(
        self, mode, cost, subscribers, expected,
    ):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        with pytest.raises(ValueError, match=expected):
            compose_email(
                mode, dt.date(2026, 8, 1), [], splits, cal, cost,
                {"total": 30, "passing": 30, "failing": 0, "skipped": 0},
                subscribers, {"count": 0, "oldest": []}, 0, "",
            )

    def test_monthly_summary_fails_closed_without_provider_state(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        alerts = [make_alert(
            kind="provider_usage",
            alert_id="monthly-provider-usage-review",
            title="Review provider usage",
            detail="Dashboard totals require review.",
            action_kind="direct",
            action="Open the provider dashboards.",
        )]
        with pytest.raises(ValueError, match="provider capacity state"):
            compose_email(
                "monthly", dt.date(2026, 8, 1), alerts, splits, cal,
                {"mtd_total": 1.0, "cap_usd": 5.0, "top": []},
                {"total": 30, "passing": 30, "failing": 0, "skipped": 0},
                42, {"count": 0, "oldest": []}, 0, "",
            )

    def test_site_failure_email_has_one_clear_action_and_handoff(self):
        splits = {"visible": [], "suppressed": [], "expired": []}
        cal = {"overdue": [], "due_soon": [], "horizon_days": 200,
               "horizon_ok": True, "event_count": 4}
        site_health = _site_failure()
        alerts = decide_alerts(
            splits, cal, None, TODAY, site_health=site_health,
        )
        subject, body = compose_email(
            "daily", TODAY, alerts, splits, cal, None,
            {"total": 30, "passing": 30, "failing": 0, "skipped": 0},
            None, {"count": 0, "oldest": []}, 0, "",
            site_health=site_health,
        )

        site = body.split("SITE HEALTH", 1)[1].split("COST:", 1)[0]
        assert "ACTION" in subject
        assert site.count("ACTION:") == 1
        assert "Follow the matching numbered item" in site
        assert "COPY/PASTE MESSAGE FOR YOUR CODING ASSISTANT" in body

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
