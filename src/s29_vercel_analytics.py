"""Capture one bounded, aggregate-only Vercel Web Analytics checkpoint.

The Vercel API cannot filter by request hostname. Browser intake therefore
admits only Richmond Commons' apex and www hosts. This CLI queries production
aggregates, suppresses small/private referrer cells, and writes canonical JSON
only below the repository's gitignored analytics-checkpoint directory.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

API_BASE = "https://api.vercel.com"
COUNT_ENDPOINT = "/v1/query/web-analytics/visits/count"
AGGREGATE_ENDPOINT = "/v1/query/web-analytics/visits/aggregate"
PRODUCTION_FILTER = "environment eq 'production'"
EXPECTED_HOSTNAMES = ("richmondcommons.org", "www.richmondcommons.org")
EXPECTED_ROUTES = (
    ("homepage", "/"),
    ("november_election", "/elections/2026-general"),
    ("meeting_index", "/meetings"),
    ("council_index", "/council"),
    ("district_finder", "/elections/find-my-district"),
)
EXPECTED_PHASES = (
    ("baseline", (("B7", 7), ("B14", 14))),
    ("treatment", (("T7", 7), ("T14", 14))),
)
CHECKPOINT_IDS = tuple(checkpoint_id for _, checkpoints in EXPECTED_PHASES
                       for checkpoint_id, _ in checkpoints)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "analytics_checkpoints"
UTC = dt.timezone.utc
SHA = re.compile(r"^[0-9a-f]{40}$")
Transport = Callable[[urllib.request.Request, float], Mapping[str, Any]]

class CheckpointError(RuntimeError):
    """Fail-closed configuration, API, privacy, or persistence error."""

def _canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"

def _require_keys(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CheckpointError(f"{label} has an unexpected shape")
    return value

def _read_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError("measurement config is unreadable or invalid JSON") from exc
    return _validate_config(value)

def _parse_utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str):
        raise CheckpointError(f"{label} must be an ISO-8601 UTC timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CheckpointError(f"{label} must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise CheckpointError(f"{label} must use UTC")
    return parsed.astimezone(UTC)

def _midnight(value: Any, label: str) -> dt.datetime:
    parsed = _parse_utc(value, label)
    if parsed.time() != dt.time():
        raise CheckpointError(f"{label} must be exactly 00:00:00Z")
    return parsed

def _timestamp(value: dt.datetime) -> str:
    return value.astimezone(UTC).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")

def _window_params(start: dt.datetime, end: dt.datetime) -> tuple[str, str]:
    if start >= end or start.time() != dt.time() or end.time() != dt.time():
        raise CheckpointError("analytics windows must be complete UTC days")
    # Live verification: date-only inclusive-last-day inputs normalize to the
    # intended half-open response window. Timestamp end-of-day inputs did not.
    return start.date().isoformat(), (end.date() - dt.timedelta(days=1)).isoformat()

def _validate_config(value: Any) -> dict[str, Any]:
    config = _require_keys(value, {
        "schema_version", "experiment_id", "measurement_status", "analytics", "phases",
    }, "measurement config")
    if config["schema_version"] != 1 or config["experiment_id"] != "s29-november-demand-test":
        raise CheckpointError("measurement config identity changed")
    status = config["measurement_status"]
    if status not in {"pending", "active", "complete"}:
        raise CheckpointError("measurement_status must be pending, active, or complete")
    analytics = _require_keys(
        config["analytics"], {"production_hostnames", "routes", "top_referrers",
                              "referrer_min_visitor_days"}, "analytics config")
    hostnames = analytics["production_hostnames"]
    if not isinstance(hostnames, list) or tuple(hostnames) != EXPECTED_HOSTNAMES:
        raise CheckpointError("analytics hostnames must be exact apex/www production hosts")
    route_pairs = tuple((route.get("label"), route.get("path"))
                        for route in analytics["routes"] if isinstance(route, dict)
                        ) if isinstance(analytics["routes"], list) else ()
    if route_pairs != EXPECTED_ROUTES or any(
        set(route) != {"label", "path"} for route in analytics["routes"]
    ):
        raise CheckpointError("analytics routes must match the exact bounded S29 allowlist")
    if analytics["top_referrers"] != 10 or analytics["referrer_min_visitor_days"] != 5:
        raise CheckpointError("referrer bounds must remain top 10 and five visitor-days")
    phases = config["phases"]
    if not isinstance(phases, list) or len(phases) != 2:
        raise CheckpointError("phases must match the exact baseline/treatment contract")
    starts: list[dt.datetime | None] = []
    for phase, (phase_id, expected_checkpoints) in zip(phases, EXPECTED_PHASES):
        phase = _require_keys(phase, {
            "id", "start_utc", "deployment_sha", "checkpoints",
        }, f"{phase_id} phase")
        checkpoint_pairs = tuple((item.get("id"), item.get("complete_days"))
                                 for item in phase["checkpoints"]
                                 if isinstance(item, dict)
                                 ) if isinstance(phase["checkpoints"], list) else ()
        if phase["id"] != phase_id or checkpoint_pairs != expected_checkpoints:
            raise CheckpointError("phases must contain exact B7/B14/T7/T14 checkpoints")
        if any(set(item) != {"id", "complete_days"} for item in phase["checkpoints"]):
            raise CheckpointError("checkpoint definitions have an unexpected shape")
        start, sha = phase["start_utc"], phase["deployment_sha"]
        if (start is None) != (sha is None):
            raise CheckpointError(f"{phase_id} start and deployment SHA must be set together")
        starts.append(None if start is None else _midnight(start, f"{phase_id}.start_utc"))
        if sha is not None and (not isinstance(sha, str) or SHA.fullmatch(sha) is None):
            raise CheckpointError(f"{phase_id}.deployment_sha must be 40 lowercase hex characters")
    if status == "pending" and any(start is not None for start in starts):
        raise CheckpointError("pending measurement must not contain phase dates")
    if status in {"active", "complete"} and starts[0] is None:
        raise CheckpointError("active measurement requires the baseline start and SHA")
    if status == "complete" and starts[1] is None:
        raise CheckpointError("complete measurement requires both phase starts and SHAs")
    if starts[1] is not None and starts[1] < starts[0] + dt.timedelta(days=14):
        raise CheckpointError("treatment starts before the 14-day baseline closes")
    return dict(config)

def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CheckpointError(f"{label} must be a non-negative integer")
    return value

def _odata(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"

def _route_filter(paths: Sequence[str]) -> str:
    choices = " or ".join(f"requestPath eq {_odata(path)}" for path in paths)
    return f"{PRODUCTION_FILTER} and ({choices})"

def _default_transport(request: urllib.request.Request, timeout: float) -> Mapping[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        # Never echo response bodies, URLs, queries, or authorization headers.
        raise CheckpointError(f"Vercel Web Analytics API returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError,
            UnicodeError, json.JSONDecodeError) as exc:
        raise CheckpointError("Vercel Web Analytics API request failed") from exc
    if not isinstance(payload, dict):
        raise CheckpointError("Vercel Web Analytics API returned a non-object")
    return payload

class VercelAnalyticsClient:
    def __init__(
        self, token: str, project_id: str, team_id: str,
        *,
        transport: Transport = _default_transport,
        timeout: float = 20.0,
    ) -> None:
        if not token or not project_id or not team_id:
            raise CheckpointError(
                "VERCEL_TOKEN, VERCEL_PROJECT_ID, and VERCEL_ORG_ID are required")
        self._token, self._project_id, self._team_id = token, project_id, team_id
        self._transport, self._timeout = transport, timeout

    def _get(self, endpoint: str, parameters: list[tuple[str, str]]) -> Mapping[str, Any]:
        query = urllib.parse.urlencode(
            [("projectId", self._project_id), ("teamId", self._team_id), *parameters]
        )
        request = urllib.request.Request(
            f"{API_BASE}{endpoint}?{query}",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "User-Agent": "Richmond-Commons-S29-checkpoint/1",
            },
        )
        return self._transport(request, self._timeout)

    def count(self, start: dt.datetime, end: dt.datetime) -> dict[str, int]:
        since, until = _window_params(start, end)
        response = self._get(
            COUNT_ENDPOINT,
            [("since", since), ("until", until), ("filter", PRODUCTION_FILTER)],
        )
        data = _validate_response(response, start, end, PRODUCTION_FILTER, None, None)
        if not isinstance(data, dict) or set(data) != {"pageviews", "visitors"}:
            raise CheckpointError("count response data has an unexpected shape")
        return {name: _nonnegative_int(data[name], f"count {name}") for name in data}

    def aggregate(
        self,
        start: dt.datetime,
        end: dt.datetime,
        *,
        group_by: str,
        limit: int,
        filter_expression: str = PRODUCTION_FILTER,
    ) -> list[dict[str, Any]]:
        since, until = _window_params(start, end)
        response = self._get(
            AGGREGATE_ENDPOINT,
            [
                ("since", since), ("until", until), ("by", group_by),
                ("limit", str(limit)), ("filter", filter_expression),
            ],
        )
        data = _validate_response(response, start, end, filter_expression, group_by, limit)
        if not isinstance(data, list):
            raise CheckpointError("aggregate response data must be an array")
        return data

def _validate_response(
    response: Mapping[str, Any],
    start: dt.datetime,
    end: dt.datetime,
    filter_expression: str,
    group_by: str | None,
    limit: int | None,
) -> Any:
    if set(response) != {"version", "query", "data"} or response.get("version") != 1:
        raise CheckpointError("Vercel response envelope changed")
    query = response.get("query")
    if not isinstance(query, dict):
        raise CheckpointError("Vercel response query metadata is missing")
    if _parse_utc(query.get("since"), "response query.since") != start:
        raise CheckpointError("Vercel response start boundary changed")
    if _parse_utc(query.get("until"), "response query.until") != end:
        raise CheckpointError("Vercel response end boundary changed")
    if query.get("filter") != filter_expression:
        raise CheckpointError("Vercel response filter changed")
    if group_by is None:
        if "groupBy" in query:
            raise CheckpointError("count response unexpectedly contains groupBy")
    elif query.get("groupBy") != [group_by]:
        if not ("groupBy" not in query and response.get("data") == []):
            raise CheckpointError("Vercel response groupBy changed")
    if limit is not None and query.get("limit") != limit:
        raise CheckpointError("Vercel response limit changed")
    return response["data"]

def _metric_row(value: Any, dimension: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {dimension, "pageviews", "visitors"}:
        raise CheckpointError("aggregate row has an unexpected shape")
    return {
        dimension: value.get(dimension),
        "pageviews": _nonnegative_int(value["pageviews"], "aggregate pageviews"),
        "visitors": _nonnegative_int(value["visitors"], "aggregate visitors"),
    }

def _daily(
    rows: Sequence[Mapping[str, Any]], start: dt.datetime, end: dt.datetime
) -> list[dict[str, Any]]:
    dates = [(start + dt.timedelta(days=offset)).date()
             for offset in range((end - start).days)]
    observed: dict[dt.date, dict[str, int]] = {}
    for value in rows:
        row = _metric_row(value, "timestamp")
        timestamp = _midnight(row["timestamp"], "daily timestamp")
        if timestamp.date() not in dates or timestamp.date() in observed:
            raise CheckpointError("daily aggregate has a duplicate or out-of-window date")
        observed[timestamp.date()] = {
            "pageviews": row["pageviews"], "daily_reset_visitors": row["visitors"],
        }
    return [
        {
            "date": day.isoformat(),
            **observed.get(day, {"pageviews": 0, "daily_reset_visitors": 0}),
        }
        for day in dates
    ]

def _routes(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    labels = {path: label for label, path in EXPECTED_ROUTES}
    observed: dict[str, dict[str, int]] = {}
    for value in rows:
        row = _metric_row(value, "requestPath")
        path = row["requestPath"]
        if not isinstance(path, str) or path not in labels or path in observed:
            raise CheckpointError("route aggregate has an unknown or duplicate path")
        observed[path] = {"pageviews": row["pageviews"], "visitor_days": row["visitors"]}
    return [
        {
            "label": label,
            "path": path,
            **observed.get(path, {"pageviews": 0, "visitor_days": 0}),
        }
        for label, path in EXPECTED_ROUTES
    ]

def _safe_referrer(value: Any) -> str:
    if value in (None, "", "Direct"):
        return "missing_or_direct"
    if value in ("Other", "Others"):
        return "suppressed"
    if not isinstance(value, str) or not value or len(value) > 253:
        raise CheckpointError("referrer hostname is invalid")
    candidate = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    try:
        ipaddress.ip_address(candidate)
        return "suppressed"
    except ValueError:
        pass
    if any(character in value for character in "/\\?#@:\r\n\t "):
        raise CheckpointError("referrer aggregate exposed more than a hostname")
    try:
        hostname = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise CheckpointError("referrer hostname is invalid") from exc
    labels = hostname.split(".")
    if any(
        not re.fullmatch(r"(?!-)[a-z0-9-]{1,63}(?<!-)", label)
        for label in labels
    ):
        raise CheckpointError("referrer hostname is invalid")
    special = {
        "alt", "arpa", "example", "example.com", "example.net", "example.org",
        "home", "home.arpa", "internal", "invalid", "lan", "local",
        "localdomain", "localhost", "onion", "test",
    }
    if len(labels) == 1 or any(
        hostname == suffix or hostname.endswith(f".{suffix}") for suffix in special
    ):
        return "suppressed"
    return hostname

def _referrers(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) > 11:
        raise CheckpointError("referrer aggregate exceeded its bounded limit")
    named: list[dict[str, Any]] = []
    seen: set[str] = set()
    suppressed = {"pageviews": 0, "visitor_days": 0}
    for value in rows:
        row = _metric_row(value, "referrerHostname")
        hostname = _safe_referrer(row["referrerHostname"])
        if hostname != "suppressed":
            if hostname in seen:
                raise CheckpointError("referrer aggregate has a duplicate hostname")
            seen.add(hostname)
        if hostname == "suppressed" or (
            hostname != "missing_or_direct" and row["visitors"] < 5
        ):
            suppressed["pageviews"] += row["pageviews"]
            suppressed["visitor_days"] += row["visitors"]
        else:
            named.append({
                "hostname": hostname,
                "pageviews": row["pageviews"],
                "visitor_days": row["visitors"],
            })
    named.sort(key=lambda row: (-row["pageviews"], row["hostname"]))
    if suppressed["pageviews"] or suppressed["visitor_days"]:
        named.append({"hostname": "Suppressed referrer hostnames", **suppressed})
    return named

def capture_packet(
    client: VercelAnalyticsClient,
    config: Mapping[str, Any],
    checkpoint_id: str,
    captured_at: dt.datetime,
) -> dict[str, Any]:
    if config["measurement_status"] != "active":
        raise CheckpointError("measurement config must be active to capture a checkpoint")
    if checkpoint_id not in CHECKPOINT_IDS:
        raise CheckpointError("checkpoint must be one of B7, B14, T7, or T14")
    phase = next(
        phase
        for phase in config["phases"]
        if any(item["id"] == checkpoint_id for item in phase["checkpoints"])
    )
    if phase["start_utc"] is None:
        raise CheckpointError(f"{checkpoint_id} phase has not started")
    checkpoint = next(
        item for item in phase["checkpoints"] if item["id"] == checkpoint_id
    )
    start = _midnight(phase["start_utc"], f"{phase['id']}.start_utc")
    end = start + dt.timedelta(days=checkpoint["complete_days"])
    if captured_at.tzinfo is None or captured_at.astimezone(UTC) < end:
        raise CheckpointError(f"{checkpoint_id} is not due until {_timestamp(end)}")

    totals = client.count(start, end)
    daily = _daily(
        client.aggregate(start, end, group_by="day", limit=14), start, end
    )
    if totals["pageviews"] != sum(row["pageviews"] for row in daily):
        raise CheckpointError("count and daily pageview aggregates disagree")
    if totals["visitors"] != sum(row["daily_reset_visitors"] for row in daily):
        raise CheckpointError("count and daily visitor-day aggregates disagree")
    paths = [path for _, path in EXPECTED_ROUTES]
    routes = _routes(client.aggregate(
        start,
        end,
        group_by="requestPath",
        limit=len(paths),
        filter_expression=_route_filter(paths),
    ))
    referrers = _referrers(client.aggregate(
        start, end, group_by="referrerHostname", limit=10
    ))
    return {
        "schema_version": 1,
        "experiment_id": config["experiment_id"],
        "checkpoint": checkpoint_id,
        "phase": phase["id"],
        "captured_at_utc": _timestamp(captured_at),
        "window_start_utc": _timestamp(start),
        "window_end_exclusive_utc": _timestamp(end),
        "production_deployment_sha": phase["deployment_sha"],
        "scope": {
            "environment": "production",
            "production_hostnames": list(EXPECTED_HOSTNAMES),
        },
        "total_public_pageviews": totals["pageviews"],
        "visitor_days": totals["visitors"],
        "daily": daily,
        "allowlisted_routes": routes,
        "top_referrer_hostnames": referrers,
        "privacy_notes": [
            "No event rows, query strings, referrer paths, or full referrer URLs are retained.",
            "Named referrer hostnames require at least five visitor-days; private and small cells are combined.",
            "Visitor-days are daily-reset visitors, not unique or returning people.",
        ],
        "manual_join_required": [
            "Vercel Production dashboard for both exact hosts: bounce rate, "
            "collection continuity, resource-specific usage periods including "
            "rolling 30-day Active CPU, and account-wide usage/limits.",
            "Private Supabase activation and delivery aggregates for the identical UTC window.",
        ],
        "interpretation_limit": (
            "Sequential descriptive comparison only: calendar/election-interest changes, "
            "SEO lag, and the bundled treatment prevent causal or component-level attribution."
        ),
    }

def _write_packet(packet: Mapping[str, Any], output_dir: Path) -> Path:
    root = DEFAULT_OUTPUT_DIR.resolve()
    destination = output_dir.resolve()
    if destination != root and root not in destination.parents:
        raise CheckpointError("output must remain under src/data/analytics_checkpoints")
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"s29-{str(packet['checkpoint']).lower()}.json"
    if path.exists():
        raise CheckpointError("checkpoint output already exists; verify it before recapture")
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination,
        prefix=".s29-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(_canonical_json(packet))
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return path

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, choices=CHECKPOINT_IDS)
    parser.add_argument("--config", type=Path, default=Path("docs/s29-measurement.json"))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        config = _read_config(args.config)
        client = VercelAnalyticsClient(
            os.environ.get("VERCEL_TOKEN", ""),
            os.environ.get("VERCEL_PROJECT_ID", ""),
            os.environ.get("VERCEL_ORG_ID", ""),
        )
        captured_at = dt.datetime.now(UTC)
        packet = capture_packet(client, config, args.checkpoint, captured_at)
        path = _write_packet(packet, args.out_dir)
    except CheckpointError as exc:
        print(f"S29 checkpoint failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote aggregate-only S29 {args.checkpoint} checkpoint to {path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
