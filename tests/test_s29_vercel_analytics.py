"""No-network tests for the bounded S29 aggregate checkpoint collector."""
from __future__ import annotations

import datetime as dt
import io
import json
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import s29_vercel_analytics as analytics  # noqa: E402


UTC = dt.timezone.utc
START = dt.datetime(2026, 11, 1, tzinfo=UTC)
END = dt.datetime(2026, 11, 8, tzinfo=UTC)
ROOT = Path(__file__).parent.parent


def _response(request, data, *, include_group=True):
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
    since, until = (dt.date.fromisoformat(query[name][0]) for name in ("since", "until"))
    metadata = {
        "since": analytics._timestamp(dt.datetime.combine(since, dt.time(), tzinfo=UTC)),
        "until": analytics._timestamp(dt.datetime.combine(
            until + dt.timedelta(days=1), dt.time(), tzinfo=UTC
        )),
        "filter": query["filter"][0],
    }
    if "by" in query:
        if include_group:
            metadata["groupBy"] = query["by"]
        metadata["limit"] = int(query["limit"][0])
    return {"version": 1, "query": metadata, "data": data}


def _config(tmp_path, *, active=False, treatment=False):
    value = json.loads((ROOT / "docs/s29-measurement.json").read_text(encoding="utf-8"))
    if active:
        value["measurement_status"] = "active"
        value["phases"][0].update(start_utc="2026-11-01T00:00:00Z", deployment_sha="a" * 40)
    if treatment:
        value["phases"][1].update(start_utc="2026-11-15T00:00:00Z", deployment_sha="b" * 40)
    path = tmp_path / "measurement.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class FakeClient:
    def __init__(self, *, mismatched=False):
        self.calls = []
        self.mismatched = mismatched

    def count(self, start, end):
        self.calls.append(("count", start, end))
        return {"pageviews": 8 if self.mismatched else 7, "visitors": 4}

    def aggregate(self, start, end, *, group_by, limit, filter_expression=analytics.PRODUCTION_FILTER):
        self.calls.append((group_by, limit, filter_expression))
        if group_by == "day":
            return [{"timestamp": analytics._timestamp(start), "pageviews": 7, "visitors": 4}]
        if group_by == "requestPath":
            return [{"requestPath": "/", "pageviews": 5, "visitors": 3}]
        if group_by == "referrerHostname":
            return [
                {"referrerHostname": "news.publisher.org", "pageviews": 6, "visitors": 5},
                {"referrerHostname": "rare.publisher.org", "pageviews": 1, "visitors": 1},
                {"referrerHostname": None, "pageviews": 2, "visitors": 2},
            ]
        raise AssertionError(group_by)


def test_client_uses_verified_date_only_boundaries_and_exact_queries():
    requests = []

    def transport(request, timeout):
        requests.append(request)
        data = {"pageviews": 12, "visitors": 8} if "visits/count" in request.full_url else []
        return _response(request, data)

    client = analytics.VercelAnalyticsClient("secret", "project", "team", transport=transport)
    assert client.count(START, END) == {"pageviews": 12, "visitors": 8}
    client.aggregate(START, END, group_by="requestPath", limit=5,
                     filter_expression="environment eq 'production' and requestPath eq '/o''hare'")
    count = urllib.parse.parse_qs(urllib.parse.urlsplit(requests[0].full_url).query)
    assert count == {
        "projectId": ["project"], "teamId": ["team"], "since": ["2026-11-01"],
        "until": ["2026-11-07"], "filter": [analytics.PRODUCTION_FILTER],
    }
    route = urllib.parse.parse_qs(urllib.parse.urlsplit(requests[1].full_url).query)
    assert route["by"] == ["requestPath"]
    assert route["filter"] == ["environment eq 'production' and requestPath eq '/o''hare'"]
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert "secret" not in requests[0].full_url


def test_client_rejects_boundary_or_nonempty_groupby_drift_but_allows_empty_omission():
    def bad_boundary(request, timeout):
        response = _response(request, {"pageviews": 0, "visitors": 0})
        response["query"]["until"] = "2026-11-07T23:59:59.999Z"
        return response

    client = analytics.VercelAnalyticsClient("t", "p", "o", transport=bad_boundary)
    with pytest.raises(analytics.CheckpointError, match="end boundary"):
        client.count(START, END)

    def omitted(request, timeout):
        nonempty = "limit=14" in request.full_url
        data = [{"timestamp": analytics._timestamp(START), "pageviews": 1, "visitors": 1}] if nonempty else []
        return _response(request, data, include_group=False)

    client = analytics.VercelAnalyticsClient("t", "p", "o", transport=omitted)
    assert client.aggregate(START, END, group_by="requestPath", limit=5) == []
    with pytest.raises(analytics.CheckpointError, match="groupBy"):
        client.aggregate(START, END, group_by="day", limit=14)


def test_http_errors_never_echo_body_token_or_url(monkeypatch):
    request = analytics.urllib.request.Request(
        "https://api.vercel.com/test?projectId=private", headers={"Authorization": "Bearer secret"}
    )

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"secret body"))

    monkeypatch.setattr(analytics.urllib.request, "urlopen", fail)
    with pytest.raises(analytics.CheckpointError) as error:
        analytics._default_transport(request, 1)
    assert str(error.value) == "Vercel Web Analytics API returned HTTP 401"

    monkeypatch.setattr(analytics.urllib.request, "urlopen",
                        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("Bearer secret")))
    with pytest.raises(analytics.CheckpointError) as error:
        analytics._default_transport(request, 1)
    assert str(error.value) == "Vercel Web Analytics API request failed"


def test_committed_config_is_pending_exact_and_gitignored():
    config = analytics._read_config(ROOT / "docs/s29-measurement.json")
    assert config["measurement_status"] == "pending"
    assert tuple(config["analytics"]["production_hostnames"]) == analytics.EXPECTED_HOSTNAMES
    assert tuple((item["label"], item["path"]) for item in config["analytics"]["routes"]) == analytics.EXPECTED_ROUTES
    assert tuple((phase["id"], tuple((item["id"], item["complete_days"])
                 for item in phase["checkpoints"])) for phase in config["phases"]) == analytics.EXPECTED_PHASES
    assert all(phase["start_utc"] is None for phase in config["phases"])
    assert "src/data/analytics_checkpoints/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_config_rejects_scope_expansion_overlap_and_incomplete_completion(tmp_path):
    value = json.loads(_config(tmp_path).read_text(encoding="utf-8"))
    value["analytics"]["production_hostnames"].append("preview.vercel.app")
    with pytest.raises(analytics.CheckpointError, match="apex/www"):
        analytics._validate_config(value)
    value = json.loads(_config(tmp_path).read_text(encoding="utf-8"))
    value["analytics"]["routes"].append({"label": "richmond_101", "path": "/richmond-101"})
    with pytest.raises(analytics.CheckpointError, match="route"):
        analytics._validate_config(value)
    value = json.loads(_config(tmp_path, active=True, treatment=True).read_text(encoding="utf-8"))
    value["phases"][1]["start_utc"] = "2026-11-14T00:00:00Z"
    with pytest.raises(analytics.CheckpointError, match="baseline closes"):
        analytics._validate_config(value)
    value = json.loads(_config(tmp_path, active=True).read_text(encoding="utf-8"))
    value["measurement_status"] = "complete"
    with pytest.raises(analytics.CheckpointError, match="both phase"):
        analytics._validate_config(value)


def test_referrers_suppress_small_private_and_ip_cells_and_reject_paths():
    rows = [
        {"referrerHostname": "named.publisher.org", "pageviews": 7, "visitors": 5},
        {"referrerHostname": "rare.publisher.org", "pageviews": 2, "visitors": 2},
        {"referrerHostname": "[2001:db8::1]", "pageviews": 4, "visitors": 4},
        {"referrerHostname": "person.internal", "pageviews": 6, "visitors": 6},
        {"referrerHostname": "service.onion", "pageviews": 3, "visitors": 3},
        {"referrerHostname": None, "pageviews": 8, "visitors": 8},
    ]
    assert analytics._referrers(rows) == [
        {"hostname": "missing_or_direct", "pageviews": 8, "visitor_days": 8},
        {"hostname": "named.publisher.org", "pageviews": 7, "visitor_days": 5},
        {"hostname": "Suppressed referrer hostnames", "pageviews": 15, "visitor_days": 15},
    ]
    rows[0]["referrerHostname"] = "https://named.publisher.org/person"
    with pytest.raises(analytics.CheckpointError, match="more than a hostname"):
        analytics._referrers(rows)
    with pytest.raises(analytics.CheckpointError, match="unexpected shape"):
        analytics._referrers([{"pageviews": 1, "visitors": 1}])


def test_capture_is_due_only_when_active_and_emits_bounded_labels(tmp_path):
    pending = analytics._read_config(_config(tmp_path))
    with pytest.raises(analytics.CheckpointError, match="active"):
        analytics.capture_packet(FakeClient(), pending, "B7", END)
    active = analytics._read_config(_config(tmp_path, active=True))
    with pytest.raises(analytics.CheckpointError, match="not due"):
        analytics.capture_packet(FakeClient(), active, "B7", END - dt.timedelta(seconds=1))

    client = FakeClient()
    packet = analytics.capture_packet(client, active, "B7", END)
    assert packet["total_public_pageviews"] == 7
    assert packet["visitor_days"] == 4
    assert len(packet["daily"]) == 7
    assert packet["daily"][0]["daily_reset_visitors"] == 4
    assert packet["allowlisted_routes"][0]["visitor_days"] == 3
    assert packet["top_referrer_hostnames"][-1]["hostname"] == "Suppressed referrer hostnames"
    assert client.calls[2] == (
        "requestPath", 5, analytics._route_filter([path for _, path in analytics.EXPECTED_ROUTES])
    )
    manual_join = " ".join(packet["manual_join_required"])
    assert "rolling 30-day Active CPU" in manual_join
    assert "billing cycle" not in manual_join
    text = json.dumps(packet)
    assert '"visitors"' not in text and "referrerPath" not in text and "projectId" not in text


def test_capture_fails_when_count_and_daily_aggregates_disagree(tmp_path):
    active = analytics._read_config(_config(tmp_path, active=True))
    with pytest.raises(analytics.CheckpointError, match="disagree"):
        analytics.capture_packet(FakeClient(mismatched=True), active, "B7", END)


def test_writer_is_canonical_and_cannot_escape_gitignored_root(tmp_path, monkeypatch):
    monkeypatch.setattr(analytics, "DEFAULT_OUTPUT_DIR", tmp_path / "checkpoints")
    packet = {"checkpoint": "B7", "z": 1, "a": 2}
    path = analytics._write_packet(packet, tmp_path / "checkpoints" / "local")
    assert path.read_text(encoding="utf-8") == analytics._canonical_json(packet)
    with pytest.raises(analytics.CheckpointError, match="already exists"):
        analytics._write_packet(packet, path.parent)
    with pytest.raises(analytics.CheckpointError, match="output must remain"):
        analytics._write_packet(packet, tmp_path / "elsewhere")


def test_checkpoint_workflow_is_manual_main_only_and_has_no_public_state():
    text = (ROOT / ".github/workflows/s29-analytics-checkpoint.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch:" not in text
    assert "repository_dispatch:" in text
    assert "types: [operator-s29-analytics-checkpoint]" in text
    assert "github.event.action == 'operator-s29-analytics-checkpoint'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert 'keys == ["checkpoint"]' in text
    assert all(f'.checkpoint == "{value}"' in text for value in ("B7", "B14", "T7", "T14"))
    assert "contents: read" in text
    assert "RESEND_API_KEY" in text and "OPERATOR_EMAIL" in text
    for forbidden in ("schedule:", "upload-artifact", "heartbeat", "git push"):
        assert forbidden not in text
