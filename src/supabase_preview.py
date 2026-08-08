"""Clean-room Supabase Preview branch lifecycle.

Reads from: ``supabase/migrations/*.sql`` and the Supabase/Vercel management
control planes. It never reads ``.env`` and never accepts a production
database URL, password, service-role key, or application secret.

Writes to: one non-persistent, data-less Supabase branch and four
branch-scoped Vercel Preview variables. Cleanup targets the immutable branch
UUID/project ref returned by Supabase and exact Vercel environment-variable
IDs; it never mutates production-scoped variables.

Why this does not shell out to the Supabase CLI
------------------------------------------------
Supabase CLI 2.112.0 failed to parse Management API timestamps containing an
ISO-8601 ``+00:00`` offset during the PR #82 audit. A blind CLI retry after a
create/delete timeout also makes it unclear whether the first mutation took
effect. This controller uses the Management API directly, never retries a
mutation blindly, and reconciles ambiguous responses with a read before it
continues.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import UUID


SUPABASE_API_BASE = "https://api.supabase.com"
VERCEL_API_BASE = "https://api.vercel.com"
PRODUCTION_PROJECT_REF = "ahrwvmizzykyyfavdvfv"

PREVIEW_ENV_KEYS = (
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "RICHMOND_PREVIEW_GIT_BRANCH",
    "RICHMOND_PREVIEW_SUPABASE_REF",
)

_PROJECT_REF_RE = re.compile(r"^[a-z0-9]{20}$")
_MIGRATION_RE = re.compile(r"^(\d{14})_([a-z][a-z0-9_]*)\.sql$")
_TRANSACTION_CONTROL_RE = re.compile(
    r"^\s*(?:BEGIN|START\s+TRANSACTION|COMMIT|ROLLBACK)\s*;",
    re.IGNORECASE | re.MULTILINE,
)
_SECRET_PATTERNS = (
    re.compile(r"\bsb_secret_[A-Za-z0-9._-]+"),
    re.compile(r"\bsbp_[A-Za-z0-9._-]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    re.compile(r"postgres(?:ql)?://[^\s\"']+", re.IGNORECASE),
)


class PreviewError(RuntimeError):
    """Fail-closed lifecycle error with a user-safe message."""


class ApiError(PreviewError):
    """HTTP/control-plane failure. ``status=None`` means ambiguous I/O."""

    def __init__(
        self,
        message: str,
        *,
        method: str,
        path: str,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.method = method
        self.path = path
        self.status = status

    @property
    def ambiguous(self) -> bool:
        return self.status is None or self.status >= 500


def _redact(value: str) -> str:
    """Best-effort defense against credentials surfacing in an API error."""
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted[:500]


class JsonApiClient:
    """Small stdlib JSON client. Mutations deliberately have no retries."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 30.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not token.strip():
            raise PreviewError("A non-empty control-plane token is required.")
        self.base_url = base_url.rstrip("/")
        self._token = token.strip()
        self.timeout = timeout
        self._opener = opener

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | Sequence[Any] | None = None,
        query: Mapping[str, str] | None = None,
        expected: Iterable[int] = (200,),
    ) -> Any:
        suffix = f"?{urlencode(query)}" if query else ""
        url = f"{self.base_url}{path}{suffix}"
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "richmond-commons-preview-controller/1",
        }
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener(request, timeout=self.timeout) as response:
                status = int(response.status)
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise ApiError(
                f"{method} {path} returned HTTP {exc.code}: {_redact(raw)}",
                method=method,
                path=path,
                status=exc.code,
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise ApiError(
                f"{method} {path} had an ambiguous network failure: "
                f"{_redact(str(exc))}",
                method=method,
                path=path,
            ) from exc

        if status not in set(expected):
            raise ApiError(
                f"{method} {path} returned unexpected HTTP {status}: "
                f"{_redact(raw)}",
                method=method,
                path=path,
                status=status,
            )
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ApiError(
                f"{method} {path} returned invalid JSON: {_redact(raw)}",
                method=method,
                path=path,
                status=status,
            ) from exc


def parse_api_timestamp(value: str) -> datetime:
    """Parse both ``Z`` and the ``+00:00`` form that broke CLI 2.112.0."""
    if not isinstance(value, str) or not value.strip():
        raise PreviewError(f"Invalid control-plane timestamp: {value!r}")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PreviewError(f"Invalid control-plane timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise PreviewError(f"Control-plane timestamp lacks a UTC offset: {value!r}")
    return parsed


def validate_project_ref(value: str, *, label: str) -> str:
    value = (value or "").strip()
    if not _PROJECT_REF_RE.fullmatch(value):
        raise PreviewError(f"{label} must be a 20-character Supabase project ref.")
    return value


def preview_branch_name(pr_number: int) -> str:
    if pr_number <= 0:
        raise PreviewError("PR number must be a positive integer.")
    return f"pr-{pr_number}-preview"


def validate_git_branch(value: str) -> str:
    value = (value or "").strip()
    if not value or value in {"main", "master"}:
        raise PreviewError("Preview git branch must be a non-production branch.")
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", value)
        or ".." in value
        or "@{" in value
        or value.endswith(("/", "."))
        or "//" in value
    ):
        raise PreviewError("Preview git branch is not a safe canonical Git ref.")
    return value


@dataclass(frozen=True)
class BranchRecord:
    """Immutable identity plus the mutable fields needed for safety checks."""

    id: str
    name: str
    project_ref: str
    parent_project_ref: str
    git_branch: str
    persistent: bool
    is_default: bool
    status: str
    preview_project_status: str
    created_at: datetime | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "BranchRecord":
        if not isinstance(payload, Mapping):
            raise PreviewError("Supabase returned a non-object branch record.")
        branch_id = str(payload.get("id") or "")
        try:
            UUID(branch_id)
        except (ValueError, AttributeError) as exc:
            raise PreviewError("Supabase branch record has no valid immutable UUID.") from exc
        project_ref = validate_project_ref(
            str(payload.get("project_ref") or ""), label="Branch project_ref"
        )
        parent_ref = validate_project_ref(
            str(payload.get("parent_project_ref") or ""),
            label="Branch parent_project_ref",
        )
        if not isinstance(payload.get("persistent"), bool):
            raise PreviewError("Supabase branch record lacks a boolean persistent flag.")
        if not isinstance(payload.get("is_default"), bool):
            raise PreviewError("Supabase branch record lacks a boolean is_default flag.")
        created_raw = payload.get("created_at")
        created_at = parse_api_timestamp(str(created_raw)) if created_raw else None
        return cls(
            id=branch_id,
            name=str(payload.get("name") or ""),
            project_ref=project_ref,
            parent_project_ref=parent_ref,
            git_branch=str(payload.get("git_branch") or ""),
            persistent=payload["persistent"],
            is_default=payload["is_default"],
            status=str(payload.get("status") or ""),
            preview_project_status=str(payload.get("preview_project_status") or ""),
            created_at=created_at,
        )

    def assert_safe_preview(
        self,
        *,
        parent_ref: str,
        expected_name: str,
        git_branch: str,
    ) -> None:
        if self.parent_project_ref != parent_ref:
            raise PreviewError(
                "Refusing branch mutation: parent_project_ref does not match "
                "the configured Richmond production project."
            )
        if self.name != expected_name or self.git_branch != git_branch:
            raise PreviewError(
                "Refusing branch mutation: branch name/git identity mismatch."
            )
        if self.persistent:
            raise PreviewError("Refusing to mutate a persistent Supabase branch.")
        if self.is_default or self.project_ref == parent_ref:
            raise PreviewError("Refusing to mutate a default/production branch.")


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    sql: str


def load_migrations(directory: Path) -> list[Migration]:
    """Read strict timestamped migrations; loose aliases fail closed."""
    if not directory.is_dir():
        raise PreviewError(f"Migration directory does not exist: {directory}")
    migrations: list[Migration] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.sql")):
        match = _MIGRATION_RE.fullmatch(path.name)
        if match is None:
            raise PreviewError(
                f"Migration must use <14-digit UTC timestamp>_<name>.sql: "
                f"{path.name}"
            )
        version, name = match.groups()
        try:
            datetime.strptime(version, "%Y%m%d%H%M%S")
        except ValueError as exc:
            raise PreviewError(f"Migration has invalid UTC timestamp: {path.name}") from exc
        if version in seen:
            raise PreviewError(f"Duplicate migration version: {version}")
        seen.add(version)
        sql = path.read_text(encoding="utf-8-sig").strip()
        if not sql:
            raise PreviewError(f"Migration is empty: {path.name}")
        migrations.append(Migration(version, name, path, sql))
    if not migrations:
        raise PreviewError(f"No timestamped migrations found in {directory}")
    return migrations


def migration_plan(
    migrations: Sequence[Migration], remote_rows: Sequence[Mapping[str, Any]]
) -> list[Migration]:
    """Return the contiguous pending suffix, rejecting all ledger drift."""
    local = {migration.version: migration for migration in migrations}
    remote: dict[str, str] = {}
    for row in remote_rows:
        version = str(row.get("version") or "")
        name = str(row.get("name") or "")
        if not re.fullmatch(r"\d{14}", version):
            raise PreviewError(
                f"Remote ledger contains a non-14-digit migration version: {version!r}"
            )
        if version in remote:
            raise PreviewError(f"Remote ledger contains duplicate version {version}.")
        remote[version] = name

    orphaned = sorted(set(remote) - set(local))
    if orphaned:
        raise PreviewError(
            "Remote migration versions are absent from the checked-out PR: "
            + ", ".join(orphaned)
        )
    mismatches = [
        version
        for version, name in remote.items()
        if name != local[version].name
    ]
    if mismatches:
        raise PreviewError(
            "Remote migration names do not match their committed filenames: "
            + ", ".join(sorted(mismatches))
        )

    pending = [migration for migration in migrations if migration.version not in remote]
    if remote and pending:
        highest_applied = max(remote)
        holes = [m.version for m in pending if m.version < highest_applied]
        if holes:
            raise PreviewError(
                "Remote ledger has a history hole; refusing out-of-order apply: "
                + ", ".join(holes)
            )
    return pending


def _rows(payload: Any, *, context: str) -> list[Mapping[str, Any]]:
    """Normalize Management API list/result/data response shapes."""
    candidate = payload
    if isinstance(payload, Mapping):
        for key in ("result", "data", "branches", "keys", "envs"):
            if key in payload:
                candidate = payload[key]
                break
    if not isinstance(candidate, list) or not all(
        isinstance(item, Mapping) for item in candidate
    ):
        raise PreviewError(f"Unexpected {context} response shape.")
    return list(candidate)


class SupabaseManagementClient:
    def __init__(self, token: str, *, api: JsonApiClient | None = None) -> None:
        self.api = api or JsonApiClient(SUPABASE_API_BASE, token)

    def list_branches(self, parent_ref: str) -> list[BranchRecord]:
        payload = self.api.request("GET", f"/v1/projects/{parent_ref}/branches")
        return [
            BranchRecord.from_payload(item)
            for item in _rows(payload, context="branch list")
        ]

    def create_branch(
        self, parent_ref: str, *, name: str, git_branch: str
    ) -> BranchRecord:
        payload = self.api.request(
            "POST",
            f"/v1/projects/{parent_ref}/branches",
            body={
                "branch_name": name,
                "git_branch": git_branch,
                "is_default": False,
                "persistent": False,
                "with_data": False,
            },
            expected=(201,),
        )
        return BranchRecord.from_payload(payload)

    def delete_branch(self, project_ref: str) -> None:
        self.api.request(
            "DELETE",
            f"/v1/branches/{project_ref}",
            query={"force": "true"},
            expected=(200,),
        )

    def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
        suffix = "/read-only" if read_only else ""
        return self.api.request(
            "POST",
            f"/v1/projects/{project_ref}/database/query{suffix}",
            body={"query": sql, "parameters": []},
            expected=(200, 201),
        )

    def api_keys(self, project_ref: str) -> Any:
        return self.api.request(
            "GET",
            f"/v1/projects/{project_ref}/api-keys",
            query={"reveal": "true"},
        )


def find_branch(
    client: SupabaseManagementClient, parent_ref: str, name: str
) -> BranchRecord | None:
    matches = [branch for branch in client.list_branches(parent_ref) if branch.name == name]
    if len(matches) > 1:
        raise PreviewError(f"Supabase returned duplicate branches named {name!r}.")
    return matches[0] if matches else None


def _branch_present(
    client: SupabaseManagementClient,
    parent_ref: str,
    identity: BranchRecord,
) -> bool:
    return any(
        branch.id == identity.id and branch.project_ref == identity.project_ref
        for branch in client.list_branches(parent_ref)
    )


def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float,
    interval_seconds: float,
    description: str,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
            last_error = None
        except ApiError as exc:
            if exc.status in {401, 403}:
                raise
            last_error = exc
        time.sleep(interval_seconds)
    detail = f" Last error: {last_error}" if last_error else ""
    raise PreviewError(f"Timed out waiting for {description}.{detail}")


def wait_for_database(
    client: SupabaseManagementClient,
    branch: BranchRecord,
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> None:
    def ready() -> bool:
        payload = client.query(branch.project_ref, "select 1 as ok", read_only=True)
        rows = _rows(payload, context="database readiness")
        return bool(rows) and int(rows[0].get("ok") or 0) == 1

    wait_until(
        ready,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        description=f"Supabase branch {branch.project_ref} database readiness",
    )


_LEDGER_QUERY = (
    "select version, coalesce(name, '') as name "
    "from supabase_migrations.schema_migrations order by version"
)


def read_ledger(
    client: SupabaseManagementClient, branch: BranchRecord
) -> list[Mapping[str, Any]]:
    return _rows(
        client.query(branch.project_ref, _LEDGER_QUERY, read_only=True),
        context="migration ledger",
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def apply_migration(
    client: SupabaseManagementClient,
    branch: BranchRecord,
    migration: Migration,
) -> None:
    if _TRANSACTION_CONTROL_RE.search(migration.sql):
        raise PreviewError(
            f"{migration.path.name} contains explicit transaction control. "
            "The Management API bootstrap requires an atomic migration body; "
            "remove the wrapper or use the pinned Supabase CLI after reviewing it."
        )
    body = migration.sql.rstrip()
    if not body.endswith(";"):
        body += ";"
    batch = (
        "begin;\n"
        f"{body}\n"
        "insert into supabase_migrations.schema_migrations (version, name) "
        f"values ({_sql_literal(migration.version)}, "
        f"{_sql_literal(migration.name)});\n"
        "commit;"
    )
    try:
        client.query(branch.project_ref, batch, read_only=False)
    except ApiError as exc:
        if not exc.ambiguous:
            raise
        # A timed-out write may have committed. Never replay blindly: reconcile
        # against the exact ledger version first.
        ledger = {
            str(row.get("version") or ""): str(row.get("name") or "")
            for row in read_ledger(client, branch)
        }
        if ledger.get(migration.version) == migration.name:
            return
        raise PreviewError(
            f"Migration {migration.version} has ambiguous apply state and was "
            "not replayed. Inspect the Preview ledger before rerunning."
        ) from exc

    ledger = {
        str(row.get("version") or ""): str(row.get("name") or "")
        for row in read_ledger(client, branch)
    }
    if ledger.get(migration.version) != migration.name:
        raise PreviewError(
            f"Migration {migration.version} executed but exact ledger parity "
            "was not observed."
        )


def _decode_jwt_role(value: str) -> str | None:
    parts = value.split(".")
    if len(parts) != 3:
        return None
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    role = payload.get("role")
    return str(role) if role is not None else None


def choose_public_api_key(payload: Any) -> str:
    """Select only a publishable/anon key; elevated keys are never returned."""
    candidates: list[tuple[int, str]] = []
    for row in _rows(payload, context="API key list"):
        name = str(row.get("name") or "").strip().lower()
        key_type = str(row.get("type") or "").strip().lower()
        value = str(row.get("api_key") or row.get("value") or "").strip()
        if not value:
            continue
        elevated_label = any(word in f"{name} {key_type}" for word in ("secret", "service"))
        if elevated_label or value.startswith("sb_secret_"):
            continue
        if value.startswith("sb_publishable_"):
            candidates.append((0, value))
        elif name == "anon" and _decode_jwt_role(value) == "anon":
            candidates.append((1, value))
    if not candidates:
        raise PreviewError(
            "Supabase returned no verified publishable/anon API key for the branch."
        )
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


class VercelClient:
    def __init__(
        self,
        token: str,
        *,
        project_id: str,
        team_id: str,
        api: JsonApiClient | None = None,
    ) -> None:
        if not project_id.strip() or not team_id.strip():
            raise PreviewError("VERCEL_PROJECT_ID and VERCEL_ORG_ID are required.")
        self.project_id = project_id.strip()
        self.team_id = team_id.strip()
        self.api = api or JsonApiClient(VERCEL_API_BASE, token)

    def list_envs(self, git_branch: str) -> list[Mapping[str, Any]]:
        payload = self.api.request(
            "GET",
            f"/v10/projects/{quote(self.project_id, safe='')}/env",
            query={"teamId": self.team_id, "gitBranch": git_branch, "limit": "100"},
        )
        return _rows(payload, context="Vercel environment list")

    def create_preview_env(self, *, key: str, value: str, git_branch: str) -> None:
        if key not in PREVIEW_ENV_KEYS:
            raise PreviewError(f"Refusing non-allowlisted Preview variable: {key}")
        self.api.request(
            "POST",
            f"/v10/projects/{quote(self.project_id, safe='')}/env",
            query={"teamId": self.team_id},
            body={
                "key": key,
                "value": value,
                "type": "plain",
                "target": ["preview"],
                "gitBranch": git_branch,
            },
            expected=(200, 201),
        )

    def delete_env(self, env_id: str) -> None:
        if not env_id.strip():
            raise PreviewError("Refusing to delete a Vercel variable without an ID.")
        self.api.request(
            "DELETE",
            f"/v9/projects/{quote(self.project_id, safe='')}/env/"
            f"{quote(env_id, safe='')}",
            query={"teamId": self.team_id},
            expected=(200,),
        )


def _env_targets(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("target")
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(value) for value in raw}
    return set()


def branch_preview_envs(
    client: VercelClient, git_branch: str
) -> list[Mapping[str, Any]]:
    matches: list[Mapping[str, Any]] = []
    for row in client.list_envs(git_branch):
        if str(row.get("key") or "") not in PREVIEW_ENV_KEYS:
            continue
        if str(row.get("gitBranch") or "") != git_branch:
            continue
        if _env_targets(row) != {"preview"}:
            raise PreviewError(
                "Refusing Vercel variable mutation: expected an exact "
                "branch-scoped Preview target."
            )
        matches.append(row)
    return matches


def sync_vercel_preview(
    client: VercelClient,
    *,
    git_branch: str,
    branch: BranchRecord,
    public_key: str,
) -> None:
    expected = {
        "NEXT_PUBLIC_SUPABASE_URL": f"https://{branch.project_ref}.supabase.co",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": public_key,
        "RICHMOND_PREVIEW_GIT_BRANCH": git_branch,
        "RICHMOND_PREVIEW_SUPABASE_REF": branch.project_ref,
    }
    # A key may exist in Production and in this exact Preview branch. Vercel's
    # name-based upsert semantics are ambiguous in that shape, so delete only
    # exact branch+Preview rows by immutable ID and then create without upsert.
    cleanup_vercel_preview(client, git_branch=git_branch)
    for key, value in expected.items():
        client.create_preview_env(key=key, value=value, git_branch=git_branch)

    rows = branch_preview_envs(client, git_branch)
    by_key: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_key.setdefault(str(row.get("key") or ""), []).append(row)
    bad_counts = [key for key in PREVIEW_ENV_KEYS if len(by_key.get(key, [])) != 1]
    if bad_counts:
        raise PreviewError(
            "Vercel branch-scoped Preview variable verification failed: "
            + ", ".join(bad_counts)
        )
    for key, value in expected.items():
        observed = str(by_key[key][0].get("value") or "")
        if observed and observed != value:
            # Sensitive values may be redacted/omitted by the API; an explicit,
            # different readable value is a real mismatch.
            raise PreviewError(f"Vercel Preview variable verification failed: {key}")


def cleanup_vercel_preview(client: VercelClient, *, git_branch: str) -> int:
    rows = branch_preview_envs(client, git_branch)
    deleted = 0
    for row in rows:
        env_id = str(row.get("id") or "")
        client.delete_env(env_id)
        deleted += 1
    remaining = branch_preview_envs(client, git_branch)
    if remaining:
        raise PreviewError(
            "Vercel still reports branch-scoped Preview variables after cleanup."
        )
    return deleted


@dataclass(frozen=True)
class BootstrapResult:
    branch: BranchRecord
    applied_migrations: int


def delete_supabase_preview(
    client: SupabaseManagementClient,
    *,
    parent_ref: str,
    branch: BranchRecord,
    timeout_seconds: float,
    interval_seconds: float,
) -> None:
    try:
        client.delete_branch(branch.project_ref)
    except ApiError as exc:
        if not exc.ambiguous:
            raise
        # Never issue a second DELETE after an ambiguous response. Observe the
        # immutable UUID/ref and let a later idempotent cleanup retry if needed.
    wait_until(
        lambda: not _branch_present(client, parent_ref, branch),
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        description=f"deletion of Supabase branch {branch.project_ref}",
    )


def bootstrap_preview(
    supabase: SupabaseManagementClient,
    vercel: VercelClient,
    *,
    parent_ref: str,
    pr_number: int,
    git_branch: str,
    migrations: Sequence[Migration],
    replace: bool,
    timeout_seconds: float = 600.0,
    interval_seconds: float = 5.0,
) -> BootstrapResult:
    parent_ref = validate_project_ref(parent_ref, label="Parent project ref")
    if parent_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError(
            "Configured parent ref is not the Richmond production project; "
            "refusing control-plane mutation."
        )
    git_branch = validate_git_branch(git_branch)
    name = preview_branch_name(pr_number)
    existing = find_branch(supabase, parent_ref, name)
    if existing is not None:
        existing.assert_safe_preview(
            parent_ref=parent_ref, expected_name=name, git_branch=git_branch
        )
        if not replace:
            raise PreviewError(
                f"Preview branch {name} already exists; use --replace for a "
                "clean-room rebuild."
            )
        cleanup_vercel_preview(vercel, git_branch=git_branch)
        delete_supabase_preview(
            supabase,
            parent_ref=parent_ref,
            branch=existing,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )

    created: BranchRecord | None = None
    try:
        try:
            created = supabase.create_branch(
                parent_ref, name=name, git_branch=git_branch
            )
        except ApiError as exc:
            if not exc.ambiguous:
                raise
            # POST may have succeeded. Reconcile once by exact identity; never
            # blindly create a second branch.
            created = find_branch(supabase, parent_ref, name)
            if created is None:
                raise PreviewError(
                    "Supabase branch create has ambiguous state and no exact "
                    "branch was observable; no retry was attempted."
                ) from exc
        created.assert_safe_preview(
            parent_ref=parent_ref, expected_name=name, git_branch=git_branch
        )
        wait_for_database(
            supabase,
            created,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )

        pending = migration_plan(migrations, read_ledger(supabase, created))
        for migration in pending:
            apply_migration(supabase, created, migration)
        if migration_plan(migrations, read_ledger(supabase, created)):
            raise PreviewError("Preview migration ledger did not reach exact parity.")

        public_key = choose_public_api_key(supabase.api_keys(created.project_ref))
        sync_vercel_preview(
            vercel,
            git_branch=git_branch,
            branch=created,
            public_key=public_key,
        )
        return BootstrapResult(created, len(pending))
    except Exception:
        # A failed bootstrap is not a useful environment. Remove partial
        # Vercel values first, then the exact branch created by this invocation.
        try:
            cleanup_vercel_preview(vercel, git_branch=git_branch)
        except Exception as cleanup_error:
            print(
                f"::warning::Vercel rollback needs follow-up: {cleanup_error}",
                file=sys.stderr,
            )
        if created is not None:
            try:
                delete_supabase_preview(
                    supabase,
                    parent_ref=parent_ref,
                    branch=created,
                    timeout_seconds=timeout_seconds,
                    interval_seconds=interval_seconds,
                )
            except Exception as cleanup_error:
                print(
                    f"::warning::Supabase rollback needs follow-up for immutable "
                    f"ref {created.project_ref}: {cleanup_error}",
                    file=sys.stderr,
                )
        raise


def cleanup_preview(
    supabase: SupabaseManagementClient,
    vercel: VercelClient | None,
    *,
    parent_ref: str,
    pr_number: int,
    git_branch: str,
    timeout_seconds: float = 600.0,
    interval_seconds: float = 5.0,
) -> tuple[bool, int]:
    parent_ref = validate_project_ref(parent_ref, label="Parent project ref")
    if parent_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError("Refusing cleanup for an unknown production parent ref.")
    git_branch = validate_git_branch(git_branch)
    name = preview_branch_name(pr_number)
    branch = find_branch(supabase, parent_ref, name)
    if branch is not None:
        branch.assert_safe_preview(
            parent_ref=parent_ref, expected_name=name, git_branch=git_branch
        )

    # Remove routing first so a concurrent build fails closed instead of
    # targeting a branch during deletion. Supabase deletion still runs when
    # Vercel cleanup fails, so an expired Vercel token cannot leak compute cost.
    vercel_error: Exception | None = None
    deleted_envs = 0
    if vercel is None:
        vercel_error = PreviewError(
            "Vercel credentials were unavailable; branch-scoped Preview "
            "variables still need control-plane cleanup."
        )
    else:
        try:
            deleted_envs = cleanup_vercel_preview(vercel, git_branch=git_branch)
        except Exception as exc:
            vercel_error = exc

    if branch is not None:
        delete_supabase_preview(
            supabase,
            parent_ref=parent_ref,
            branch=branch,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )
    if vercel_error is not None:
        raise PreviewError(
            "Supabase cleanup completed, but Vercel cleanup needs follow-up: "
            f"{vercel_error}"
        ) from vercel_error
    return branch is not None, deleted_envs


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise PreviewError(f"Required environment variable is missing: {name}")
    return value


def _write_github_output(name: str, value: str) -> None:
    output_path = (os.getenv("GITHUB_OUTPUT") or "").strip()
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, migrate, verify, and clean Richmond Supabase Preview branches."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate", help="Validate strict local migration filenames without network access."
    )
    validate.add_argument("--migrations-dir", type=Path, required=True)

    for name in ("bootstrap", "cleanup"):
        command = subparsers.add_parser(name)
        command.add_argument("--parent-ref", required=True)
        command.add_argument("--pr-number", type=int, required=True)
        command.add_argument("--git-branch", required=True)
        command.add_argument("--timeout-seconds", type=float, default=600.0)
        command.add_argument("--interval-seconds", type=float, default=5.0)
        command.add_argument("--vercel-project-id")
        command.add_argument("--vercel-org-id")
    bootstrap = subparsers.choices["bootstrap"]
    bootstrap.add_argument("--migrations-dir", type=Path, required=True)
    bootstrap.add_argument("--replace", action="store_true")
    return parser


def _main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        migrations = load_migrations(args.migrations_dir)
        print(f"Validated {len(migrations)} exact timestamped migrations.")
        return 0

    supabase_token = _require_env("SUPABASE_ACCESS_TOKEN")
    supabase = SupabaseManagementClient(supabase_token)
    vercel_token = (os.getenv("VERCEL_TOKEN") or "").strip()
    project_id = (args.vercel_project_id or os.getenv("VERCEL_PROJECT_ID") or "").strip()
    team_id = (args.vercel_org_id or os.getenv("VERCEL_ORG_ID") or "").strip()
    vercel = (
        VercelClient(
            vercel_token,
            project_id=project_id,
            team_id=team_id,
        )
        if vercel_token and project_id and team_id
        else None
    )

    if args.command == "bootstrap":
        if vercel is None:
            raise PreviewError(
                "Bootstrap requires VERCEL_TOKEN, VERCEL_PROJECT_ID, and "
                "VERCEL_ORG_ID before any Supabase branch is created."
            )
        migrations = load_migrations(args.migrations_dir)
        result = bootstrap_preview(
            supabase,
            vercel,
            parent_ref=args.parent_ref,
            pr_number=args.pr_number,
            git_branch=args.git_branch,
            migrations=migrations,
            replace=args.replace,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.interval_seconds,
        )
        _write_github_output("supabase_branch_ref", result.branch.project_ref)
        _write_github_output(
            "supabase_url", f"https://{result.branch.project_ref}.supabase.co"
        )
        print(
            "Preview ready: "
            f"name={result.branch.name} ref={result.branch.project_ref} "
            f"migrations_applied={result.applied_migrations} "
            "vercel_scope=preview+exact-git-branch"
        )
        return 0

    deleted, env_count = cleanup_preview(
        supabase,
        vercel,
        parent_ref=args.parent_ref,
        pr_number=args.pr_number,
        git_branch=args.git_branch,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )
    print(
        f"Preview cleanup complete: supabase_deleted={str(deleted).lower()} "
        f"vercel_envs_deleted={env_count}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except PreviewError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
