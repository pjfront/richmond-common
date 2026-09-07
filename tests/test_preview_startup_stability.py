"""A successful SQL read must not race a fresh Preview's automatic restart."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from typing import Any
from uuid import uuid4

import pytest

import supabase_preview as preview


PARENT = preview.PRODUCTION_PROJECT_REF
REF = 'abcdefghijklmnopqrst'


class StartupClock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.base = datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, delay: float) -> None:
        self.elapsed += delay


class StartupClient:
    def __init__(self, clock: StartupClock, *, branch_age: float = 0.0,
                 postmaster_age: float = 0.0) -> None:
        self.clock = clock
        self.branch = preview.BranchRecord(
            id=str(uuid4()), name='pr-82-preview', project_ref=REF,
            parent_project_ref=PARENT, git_branch='codex/startup-test',
            persistent=False, is_default=False, status='MIGRATIONS_FAILED',
            preview_project_status='ACTIVE_HEALTHY',
            created_at=clock.base - timedelta(seconds=branch_age),
            desired_instance_size='micro', with_data=False,
        )
        self.started = clock.base - timedelta(seconds=postmaster_age)
        self.samples: list[float] = []
        self.identities: list[float] = []
        self.restart_at: float | None = None
        self.unhealthy_at: float | None = None
        self.error_at: float | None = None
        self.error: Exception | None = None
        self.replacement: dict[str, Any] | None = None
        self.sample_override: dict[str, Any] | None = None

    def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
        assert parent_ref == PARENT
        self.identities.append(self.clock.elapsed)
        if self.replacement and self.clock.elapsed >= 5:
            return [replace(self.branch, **self.replacement)]
        if self.clock.elapsed == self.unhealthy_at:
            return [replace(self.branch, preview_project_status='COMING_UP')]
        return [self.branch]

    def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
        assert project_ref == REF
        assert read_only is True
        assert sql == preview._DATABASE_STARTUP_HEALTH_QUERY
        self.samples.append(self.clock.elapsed)
        if self.clock.elapsed == self.error_at:
            assert self.error is not None
            raise self.error
        started = self.started
        if self.restart_at is not None and self.clock.elapsed >= self.restart_at:
            started = self.clock.base + timedelta(seconds=self.restart_at)
        row = {'postmaster_started_at': started.isoformat(),
               'observed_at': (self.clock.base + timedelta(seconds=self.clock.elapsed)).isoformat(),
               'in_recovery': False}
        row.update(self.sample_override or {})
        return [row]


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> StartupClock:
    clock = StartupClock()
    monkeypatch.setattr(preview.time, 'monotonic', clock.monotonic)
    monkeypatch.setattr(preview.time, 'sleep', clock.sleep)
    return clock


def wait(client: StartupClient, timeout: float = 180) -> preview.BranchRecord:
    return preview.wait_for_stable_preview(
        client, parent_ref=PARENT, pr_number=82, git_branch='codex/startup-test',
        branch=client.branch, timeout_seconds=timeout, interval_seconds=5,
    )


def test_startup_waits_past_fresh_branch_window_despite_every_select_succeeding(clock):
    client = StartupClient(clock)
    assert wait(client) == client.branch
    assert clock.elapsed == 65
    assert client.samples == list(range(0, 66, 5))
    assert client.identities == client.samples


def test_restart_after_first_successful_select_resets_readiness(clock):
    client = StartupClient(clock, branch_age=120, postmaster_age=120)
    client.restart_at = 5
    assert wait(client) == client.branch
    # First mature process passed at t=0. Its replacement must reach uptime30
    # and then pass a second identity/SQL sample; t=5 cannot release the write.
    assert clock.elapsed == 40
    assert client.samples == list(range(0, 41, 5))


def test_control_plane_unhealthy_sample_resets_consecutive_health(clock):
    client = StartupClient(clock, branch_age=120, postmaster_age=120)
    client.unhealthy_at = 5
    wait(client)
    assert clock.elapsed == 15
    assert client.samples == [0, 10, 15]


def test_recognized_startup_error_resets_consecutive_health(clock):
    client = StartupClient(clock, branch_age=120, postmaster_age=120)
    client.error_at = 5
    client.error = preview.ApiError('startup', method='POST',
        path=f'/v1/projects/{REF}/database/query/read-only', status=400,
        response_body=json.dumps({'message': 'Failed to run sql query: FATAL: 57P01: terminating connection due to administrator command'}))
    wait(client)
    assert clock.elapsed == 15
    assert client.samples == [0, 5, 10, 15]


@pytest.mark.parametrize('status,message', [
    (401, 'Unauthorized'), (403, 'Forbidden'),
    (400, 'Failed to run sql query: ERROR: 42601: syntax error'),
    (400, 'Failed to run sql query: ERROR: 42501: permission denied'),
])
def test_unrelated_read_errors_stop_without_retry(clock, status, message):
    client = StartupClient(clock, branch_age=120, postmaster_age=120)
    client.error_at = 0
    client.error = preview.ApiError('failure', method='POST',
        path=f'/v1/projects/{REF}/database/query/read-only', status=status,
        response_body=json.dumps({'message': message}))
    with pytest.raises(preview.ApiError):
        wait(client)
    assert client.samples == [0]
    assert clock.elapsed == 0


@pytest.mark.parametrize('replacement', [
    {'id': str(uuid4())}, {'project_ref': 'zyxwvutsrqponmlkjihg'},
    {'created_at': datetime.now(timezone.utc) - timedelta(minutes=1)},
    {'persistent': True}, {'is_default': True}, {'with_data': True},
    {'desired_instance_size': 'small'}, {'git_branch': 'codex/replaced'},
    {'parent_project_ref': 'zyxwvutsrqponmlkjihg'},
])
def test_identity_or_adoption_boundary_change_stops_before_next_query(clock, replacement):
    client = StartupClient(clock, branch_age=120, postmaster_age=120)
    client.replacement = replacement
    with pytest.raises(preview.PreviewError):
        wait(client)
    assert client.samples == [0]


@pytest.mark.parametrize('override', [
    {'in_recovery': None}, {'in_recovery': 'false'},
    {'postmaster_started_at': None}, {'observed_at': 'not-a-timestamp'},
    {'postmaster_started_at': '2099-01-01T00:00:00Z'},
    {'observed_at': '2099-01-01T00:00:00Z'},
])
def test_malformed_or_impossible_database_sample_fails_closed(clock, override):
    client = StartupClient(clock, branch_age=120, postmaster_age=120)
    client.sample_override = override
    with pytest.raises(preview.PreviewError):
        wait(client)
    assert client.samples == [0]


def test_recovery_never_releases_writes_and_wait_is_capped(clock):
    client = StartupClient(clock, branch_age=120, postmaster_age=120)
    client.sample_override = {'in_recovery': True}
    with pytest.raises(preview.PreviewError, match='Timed out.*stable'):
        wait(client, timeout=600)
    assert clock.elapsed == 180
    assert max(client.samples) == 175


def test_caller_shorter_timeout_is_preserved(clock):
    client = StartupClient(clock)
    with pytest.raises(preview.PreviewError, match='Timed out.*stable'):
        wait(client, timeout=12)
    assert clock.elapsed == 12
    assert client.samples == [0, 5, 10]
