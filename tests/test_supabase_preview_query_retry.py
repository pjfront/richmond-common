"""Bounded read retries for a new Preview database restarting after readiness."""
from __future__ import annotations

import json
from typing import Any

import pytest

import supabase_preview as preview


PROJECT_REF = "abcdefghijklmnopqrst"
READ_PATH = f"/v1/projects/{PROJECT_REF}/database/query/read-only"
TRANSIENT = "Failed to run sql query: Connection terminated unexpectedly"


def api_error(message: str, status: int | None = 400) -> preview.ApiError:
    return preview.ApiError(
        message, method="POST", path=READ_PATH, status=status,
        response_body=json.dumps({"message": message}),
    )


class QueryApi:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.requests.append({"method": method, "path": path, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"now": 0.0, "sleeps": []}

    def sleep(seconds: float) -> None:
        state["sleeps"].append(seconds)
        state["now"] += seconds

    monkeypatch.setattr(preview.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(preview.time, "sleep", sleep)
    return state


@pytest.mark.parametrize("message", [
    TRANSIENT,
    "Failed to run sql query: FATAL:  57P03: the database system is shutting down\n",
    "Failed to run sql query: FATAL:  57P03: the database system is starting up\n",
    "Failed to run sql query: FATAL:  57P01: terminating connection due to administrator command\n",
])
def test_catalog_read_recovers_after_readiness(
    message: str, clock: dict[str, Any],
) -> None:
    api = QueryApi([{"ok": 1}], api_error(message), [{"object_kind": "schema"}])
    client = preview.SupabaseManagementClient("token", api=api)

    assert client.query(PROJECT_REF, "select 1 as ok", read_only=True) == [{"ok": 1}]
    assert client.query(PROJECT_REF, "select * from pg_catalog.pg_namespace", read_only=True) == [{"object_kind": "schema"}]
    assert clock["sleeps"] == [2.0]
    assert api.requests[1] == api.requests[2]
    assert all(request["path"] == READ_PATH for request in api.requests)
    assert api.requests[1]["body"] == {
        "query": "select * from pg_catalog.pg_namespace", "parameters": [],
    }


def test_repeated_startup_failure_stops_after_four_requests(clock: dict[str, Any]) -> None:
    error = api_error(TRANSIENT)
    api = QueryApi(error, error, error, error)
    with pytest.raises(preview.ApiError) as caught:
        preview.SupabaseManagementClient("token", api=api).query(PROJECT_REF, "select 1", read_only=True)
    assert caught.value is error
    assert len(api.requests) == 4
    assert clock["sleeps"] == [2.0, 4.0, 8.0]


def test_slow_failed_read_does_not_start_retry_after_deadline(clock: dict[str, Any]) -> None:
    class SlowApi(QueryApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            clock["now"] += 31.0
            return super().request(method, path, **kwargs)

    api = SlowApi(api_error(TRANSIENT))
    with pytest.raises(preview.ApiError):
        preview.SupabaseManagementClient("token", api=api).query(PROJECT_REF, "select 1", read_only=True)
    assert len(api.requests) == 1
    assert clock["sleeps"] == []


def test_delayed_sleep_does_not_start_retry_after_deadline(
    clock: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preview.time, "sleep", lambda seconds: clock.update(now=31.0))
    api = QueryApi(api_error(TRANSIENT))
    with pytest.raises(preview.ApiError):
        preview.SupabaseManagementClient("token", api=api).query(PROJECT_REF, "select 1", read_only=True)
    assert len(api.requests) == 1


@pytest.mark.parametrize(("message", "status"), [
    (TRANSIENT, 401),
    (TRANSIENT, 403),
    (TRANSIENT, 404),
    (TRANSIENT, 429),
    (TRANSIENT, None),
    ("Failed to run sql query: ERROR: 42501: permission denied", 400),
    ('Failed to run sql query: ERROR: 42601: syntax error at "FATAL: 57P03: starting up"', 400),
    ("Failed to run sql query: ERROR: 23505: duplicate key", 400),
    ("Failed to run sql query: FATAL: 57P02: crash shutdown", 400),
    ("Failed to run sql query: FATAL: 28P01: password authentication failed", 400),
    ("Connection terminated unexpectedly", 400),
    ("Failed to run sql query: statement timeout", 504),
    ("Project must be active and healthy.", 400),
    ("Internal server error", 500),
])
def test_unrelated_read_errors_are_not_retried(
    message: str, status: int | None, clock: dict[str, Any],
) -> None:
    api = QueryApi(api_error(message, status))
    with pytest.raises(preview.ApiError):
        preview.SupabaseManagementClient("token", api=api).query(PROJECT_REF, "select 1", read_only=True)
    assert len(api.requests) == 1
    assert clock["sleeps"] == []


@pytest.mark.parametrize("body", ["", "not-json", "[]", '{"message":42}'])
def test_malformed_error_envelopes_are_not_retried(body: str, clock: dict[str, Any]) -> None:
    error = api_error(TRANSIENT)
    error.response_body = body
    api = QueryApi(error)
    with pytest.raises(preview.ApiError):
        preview.SupabaseManagementClient("token", api=api).query(PROJECT_REF, "select 1", read_only=True)
    assert len(api.requests) == 1
    assert clock["sleeps"] == []


@pytest.mark.parametrize("status", [400, 500, None])
def test_writes_never_retry_even_recognized_restart_errors(status: int | None, clock: dict[str, Any]) -> None:
    api = QueryApi(api_error(TRANSIENT, status))
    with pytest.raises(preview.ApiError):
        preview.SupabaseManagementClient("token", api=api).query(PROJECT_REF, "create table example(id int)", read_only=False)
    assert len(api.requests) == 1
    assert api.requests[0]["path"] == READ_PATH.removesuffix("/read-only")
    assert clock["sleeps"] == []


def test_retry_stops_immediately_when_failure_changes(clock: dict[str, Any]) -> None:
    error = api_error("Failed to run sql query: ERROR: 42501: permission denied")
    api = QueryApi(api_error(TRANSIENT), error)
    with pytest.raises(preview.ApiError) as caught:
        preview.SupabaseManagementClient("token", api=api).query(PROJECT_REF, "select 1", read_only=True)
    assert caught.value is error
    assert len(api.requests) == 2
    assert clock["sleeps"] == [2.0]
