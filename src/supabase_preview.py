"""Clean-room Supabase Preview branch lifecycle.

Reads from: ``supabase/migrations/*.sql`` and the Supabase/Vercel management
control planes. It never reads ``.env`` and never accepts a production
database URL, password, service-role key, or application secret.

Writes to: one non-persistent, data-less Supabase branch, five identity
variables, and four branch-scoped lifecycle state variables. Cleanup targets
the immutable branch
UUID/project ref returned by Supabase and exact Vercel environment-variable
IDs; after schema/type verification, the trusted controller requests one
exact-SHA Vercel Preview deployment. It never mutates production-scoped
variables.

Why management mutations do not shell out to the Supabase CLI
--------------------------------------------------------------
Supabase CLI 2.112.0 failed to parse Management API timestamps containing an
ISO-8601 ``+00:00`` offset during the PR #82 audit. A blind CLI retry after a
create/delete timeout also makes it unclear whether the first mutation took
effect. This controller uses the Management API directly, never retries a
mutation blindly, and reconciles ambiguous responses with a read before it
continues. The ``generate-types`` command is a narrow exception: it wraps the
pinned CLI's read-only type generator with an exact-error, bounded retry.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
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
BASELINE_FORMAT_VERSION = 1
BASELINE_CUTOFF_VERSION = "20260807013300"
# Migration 134 is a production reconciliation plan, not replayable Preview
# history. Reject it by exact timestamp before any branch mutation.
NON_REPLAYABLE_MIGRATION_VERSIONS = frozenset({"20260807013400"})
NON_REPLAYABLE_MIGRATION_NAMES = frozenset({"source_reconciliation_enforcement"})
MAX_MIGRATION_BYTES = 1_000_000
MAX_MIGRATIONS_BYTES = 16_000_000
MAX_BASELINE_BYTES = 2_000_000
MAX_DATABASE_TYPES_BYTES = 2_000_000
MAX_PREVIEW_LIFETIME_SECONDS = 2 * 60 * 60
PREVIEW_SWEEP_AGE_SECONDS = 90 * 60
PREVIEW_WATCHDOG_AGE_SECONDS = 110 * 60
MAX_SWEEP_BRANCHES = 10
MAX_TYPEGEN_RETRY_SECONDS = 120.0
TYPEGEN_ACTIVE_TRANSIENT = (
    'failed to retrieve generated types: '
    '{"message":"Project must be active and healthy."}'
)
CREATE_REQUEST_CLOCK_SKEW_SECONDS = 5
MAX_CONTROL_PLANE_FUTURE_SKEW_SECONDS = 5 * 60
GITHUB_OWNER = "pjfront"
GITHUB_REPO = "richmond-common"
EXPECTED_BASELINE_EXTENSIONS = (
    ("pgcrypto", "1.3", "extensions"),
    ("uuid-ossp", "1.1", "extensions"),
    ("vector", "0.8.2", "extensions"),
)
EXPECTED_PREVIEW_PARITY_EXCEPTIONS = (
    {
        "type": "omitted_default_privileges",
        "production_rows_omitted": 3,
        "owner": "supabase_admin",
        "schema": "public",
        "object_types": ["S", "f", "r"],
        "reason": "permission_boundary",
    },
    {
        "type": "extension_version_substitution",
        "name": "vector",
        "production_version": "0.8.0",
        "preview_version": "0.8.2",
        "schema": "extensions",
        "reason": "supabase_branch_runtime",
    },
)

PREVIEW_ENV_KEYS = (
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "RICHMOND_PREVIEW_GIT_BRANCH",
    "RICHMOND_PREVIEW_SUPABASE_REF",
    "RICHMOND_PREVIEW_SOURCE_HEAD_SHA",
)
PREVIEW_DEPLOYMENT_ENV_KEY = "RICHMOND_PREVIEW_DEPLOYMENT_ID"
PREVIEW_PR_ENV_KEY = "RICHMOND_PREVIEW_PR_NUMBER"
PREVIEW_CREATED_AT_ENV_KEY = "RICHMOND_PREVIEW_CREATED_AT"
PREVIEW_PARENT_REF_ENV_KEY = "RICHMOND_PREVIEW_PARENT_REF"
PREVIEW_STATIC_ENV_KEYS = PREVIEW_ENV_KEYS + (
    PREVIEW_PR_ENV_KEY,
    PREVIEW_CREATED_AT_ENV_KEY,
    PREVIEW_PARENT_REF_ENV_KEY,
)
PREVIEW_ALLOWED_ENV_KEYS = PREVIEW_STATIC_ENV_KEYS + (PREVIEW_DEPLOYMENT_ENV_KEY,)

_PROJECT_REF_RE = re.compile(r"^[a-z0-9]{20}$")
_MIGRATION_RE = re.compile(r"^(\d{14})_([a-z][a-z0-9_]*)\.sql$")
_MIGRATION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_LEDGER_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_GIT_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
_SECRET_PATTERNS = (
    re.compile(r"\bsb_secret_[A-Za-z0-9._-]+"),
    re.compile(r"\bsbp_[A-Za-z0-9._-]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    re.compile(r"postgres(?:ql)?://[^\s\"']+", re.IGNORECASE),
)
_BASELINE_SECRET_PATTERNS = (
    ("Supabase secret key", re.compile(r"\bsb_secret_[A-Za-z0-9._-]+")),
    ("Supabase access token", re.compile(r"\bsbp_[A-Za-z0-9._-]+")),
    (
        "JWT",
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    ),
    (
        "database connection URI",
        re.compile(r"postgres(?:ql)?://[^\s\"']+", re.IGNORECASE),
    ),
    (
        "private key",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    ),
    (
        "provider API key",
        re.compile(
            r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|"
            r"sk_live_[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,})"
        ),
    ),
)


class PreviewError(RuntimeError):
    """Fail-closed lifecycle error with a user-safe message."""


class PreviewSelectionChanged(PreviewError):
    """A stale-sweep immutable target disappeared or was replaced before mutation."""


class PreviewCostBoundaryError(PreviewError):
    """A control-plane response explicitly violated an approved cost boundary."""


class PreviewDataBoundaryError(PreviewError):
    """A control-plane response explicitly violated the data-less branch boundary."""


class ApiError(PreviewError):
    """HTTP/control-plane failure. ``status=None`` means ambiguous I/O."""

    def __init__(
        self,
        message: str,
        *,
        method: str,
        path: str,
        status: int | None = None,
        response_body: str = "",
    ) -> None:
        super().__init__(message)
        self.method = method
        self.path = path
        self.status = status
        self.response_body = response_body

    @property
    def ambiguous(self) -> bool:
        return self.status is None or self.status >= 500


def _mutation_may_have_succeeded(error: ApiError) -> bool:
    """Treat transport/server failures and malformed 2xx bodies as committed writes."""
    return error.ambiguous or (
        error.status is not None and 200 <= error.status < 300
    )


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
                response_body=raw,
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
                response_body=raw,
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
                response_body=raw,
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


def validate_git_sha(value: str, *, label: str) -> str:
    value = (value or "").strip().lower()
    if not _GIT_SHA_RE.fullmatch(value):
        raise PreviewError(f"{label} must be a full lowercase 40-character Git SHA.")
    return value


def validate_github_repo_part(value: str, *, label: str) -> str:
    value = (value or "").strip()
    if (
        not value
        or len(value) > 100
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(character.isspace() for character in value)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", value)
    ):
        raise PreviewError(f"{label} is not a safe GitHub repository identifier.")
    return value


def _reported_branch_instance_size(payload: Mapping[str, Any]) -> str | None:
    explicit_sizes: list[str] = []
    for key in ("desired_instance_size", "instance_size"):
        if key not in payload:
            continue
        normalized = str(payload.get(key) or "").strip().lower()
        explicit_sizes.append(normalized or "invalid")
    return next(
        (size for size in explicit_sizes if size != "micro"),
        explicit_sizes[0] if explicit_sizes else None,
    )


def _reported_branch_with_data(payload: Mapping[str, Any]) -> bool | str | None:
    if "with_data" not in payload:
        return None
    if isinstance(payload.get("with_data"), bool):
        return payload["with_data"]
    return "invalid"


def _assert_explicit_branch_adoption_boundaries(payload: Mapping[str, Any]) -> None:
    if _reported_branch_instance_size(payload) not in {None, "micro"}:
        raise PreviewCostBoundaryError(
            "Supabase branch explicitly reports a non-Micro compute size."
        )
    if _reported_branch_with_data(payload) not in {None, False}:
        raise PreviewDataBoundaryError(
            "Supabase branch explicitly reports a data-bearing or invalid "
            "with_data state."
        )


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
    deletion_scheduled_at: datetime | None = None
    desired_instance_size: str | None = None
    with_data: bool | str | None = None

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
        deletion_raw = payload.get("deletion_scheduled_at")
        deletion_scheduled_at = (
            parse_api_timestamp(str(deletion_raw)) if deletion_raw else None
        )
        # Preserve an explicit non-Micro value on the immutable record so the
        # controller can still identify and hard-delete that exact branch.
        # Adoption paths call ``assert_micro_compute`` before schema or Vercel
        # writes; parsing must not make cost-violation containment impossible.
        reported_size = _reported_branch_instance_size(payload)
        # Preserve malformed explicit state as unsafe while keeping immutable
        # identity parseable for exact containment.
        reported_with_data = _reported_branch_with_data(payload)
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
            deletion_scheduled_at=deletion_scheduled_at,
            desired_instance_size=reported_size,
            with_data=reported_with_data,
        )

    def assert_micro_compute(self) -> None:
        if self.desired_instance_size not in {None, "micro"}:
            raise PreviewCostBoundaryError(
                "Supabase branch explicitly reports a non-Micro compute size."
            )

    def assert_data_less(self) -> None:
        if self.with_data not in {None, False}:
            raise PreviewDataBoundaryError(
                "Supabase branch explicitly reports a data-bearing or invalid "
                "with_data state."
            )

    def assert_preview_adoption_boundaries(self) -> None:
        """Reject any explicit compute/data violation before Preview adoption."""
        self.assert_micro_compute()
        self.assert_data_less()

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
    sha256: str


@dataclass(frozen=True)
class BaselineMigration:
    version: str
    name: str
    sha256: str
    production_name: str | None = None

    @property
    def production_ledger_name(self) -> str:
        return self.production_name or self.name


@dataclass(frozen=True)
class BaselineExtension:
    name: str
    version: str
    schema: str


@dataclass(frozen=True)
class PreviewBaseline:
    directory: Path
    manifest_path: Path
    schema_path: Path
    schema_sql: str
    schema_sha256: str
    cutoff_version: str
    absorbed_migrations: tuple[BaselineMigration, ...]
    schema_inventory: Mapping[str, int]
    extensions: tuple[BaselineExtension, ...]


@dataclass(frozen=True)
class ProductionLedgerState:
    """Trusted production history observed before any Preview mutation."""

    applied_versions: tuple[str, ...]


_INVENTORY_FIELDS = (
    "tables",
    "views",
    "functions",
    "security_definer_functions",
    "policies",
    "indexes",
    "constraints",
    "triggers",
    "event_triggers",
    "non_postgres_owned_relations",
    "non_postgres_owned_routines",
    "non_postgres_owned_event_triggers",
    "sequences",
    "rls_enabled",
    "default_privilege_rows",
)


def _canonical_utf8_text(path: Path, *, max_bytes: int, label: str) -> str:
    """Decode one bounded, non-symlinked SQL artifact deterministically."""
    if path.is_symlink():
        raise PreviewError(f"{label} must not be a symlink: {path}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PreviewError(f"Unable to read {label}: {path}") from exc
    if len(raw) > max_bytes:
        raise PreviewError(f"{label} exceeds the {max_bytes}-byte safety limit: {path}")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PreviewError(f"{label} is not valid UTF-8: {path}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _canonical_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bounded_path(
    path: Path,
    *,
    root: Path,
    label: str,
    kind: str,
) -> Path:
    """Resolve one path inside an explicit root, rejecting every symlink hop."""
    root_absolute = Path(os.path.abspath(os.fspath(root)))
    path_absolute = Path(os.path.abspath(os.fspath(path)))
    try:
        relative = path_absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise PreviewError(f"{label} escapes its explicit trusted root.") from exc

    candidates = [root_absolute]
    current = root_absolute
    for component in relative.parts:
        current = current / component
        candidates.append(current)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for candidate in candidates:
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise PreviewError(f"{label} does not exist: {candidate}") from exc
        if stat.S_ISLNK(metadata.st_mode) or (
            reparse_flag
            and getattr(metadata, "st_file_attributes", 0) & reparse_flag
        ):
            raise PreviewError(
                f"{label} contains a symlink/reparse-point component: {candidate}"
            )

    try:
        resolved_root = root_absolute.resolve(strict=True)
        resolved_path = path_absolute.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise PreviewError(f"{label} resolves outside its explicit trusted root.") from exc
    if kind == "directory" and not resolved_path.is_dir():
        raise PreviewError(f"{label} is not a directory: {resolved_path}")
    if kind == "file" and not resolved_path.is_file():
        raise PreviewError(f"{label} is not a regular file: {resolved_path}")
    return resolved_path


TYPE_FILE_RELATIVE_PATH = Path("web/src/lib/database.types.ts")
IMMUTABLE_TYPE_VERIFY_DIRECTORIES = (
    Path("supabase/migrations"),
    Path("supabase/preview-baseline"),
)


def _raw_file_sha256(path: Path, *, max_bytes: int, label: str) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PreviewError(f"Unable to inspect {label}: {path}") from exc
    if size > max_bytes:
        raise PreviewError(f"{label} exceeds the {max_bytes}-byte safety limit: {path}")
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PreviewError(f"Unable to read {label}: {path}") from exc


def _path_blob_inventory(root: Path, relative_directory: Path) -> dict[str, str]:
    directory = _bounded_path(
        root / relative_directory,
        root=root,
        label=f"{relative_directory.as_posix()} inventory directory",
        kind="directory",
    )
    inventory: dict[str, str] = {}
    total_bytes = 0
    for candidate in sorted(directory.rglob("*")):
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise PreviewError(f"Unable to inspect inventory path: {candidate}") from exc
        if stat.S_ISDIR(metadata.st_mode):
            _bounded_path(
                candidate,
                root=root,
                label="Inventory directory",
                kind="directory",
            )
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise PreviewError(f"Inventory path must be a regular file: {candidate}")
        bounded = _bounded_path(
            candidate,
            root=root,
            label="Inventory file",
            kind="file",
        )
        total_bytes += bounded.stat().st_size
        if total_bytes > MAX_MIGRATIONS_BYTES + MAX_BASELINE_BYTES:
            raise PreviewError("Immutable path/blob inventory exceeds its safety limit.")
        relative = bounded.relative_to(root.resolve(strict=True)).as_posix()
        inventory[relative] = _raw_file_sha256(
            bounded,
            max_bytes=max(MAX_MIGRATION_BYTES, MAX_BASELINE_BYTES),
            label="Inventory file",
        )
    return inventory


def verify_type_update_inputs(
    *,
    metadata: Mapping[str, Any],
    source_root: Path,
    head_root: Path,
    source_head_sha: str,
    head_sha: str,
) -> Path:
    """Validate the only allowed H0 -> H1 change without executing PR code."""
    source_head_sha = validate_git_sha(source_head_sha, label="Source head SHA")
    head_sha = validate_git_sha(head_sha, label="Current head SHA")
    if source_head_sha == head_sha:
        raise PreviewError("Current head SHA must differ from source head SHA.")
    if set(metadata) != {"head_sha", "parent_shas", "files"}:
        raise PreviewError("Commit metadata has an unexpected shape.")
    if validate_git_sha(str(metadata.get("head_sha") or ""), label="Metadata head SHA") != head_sha:
        raise PreviewError("Commit metadata is not bound to the current PR head SHA.")
    parents = metadata.get("parent_shas")
    if not isinstance(parents, list) or len(parents) != 1:
        raise PreviewError("Current PR head must be a direct one-parent child of H0.")
    if validate_git_sha(str(parents[0]), label="Parent SHA") != source_head_sha:
        raise PreviewError("Current PR head is not a direct child of H0.")
    files = metadata.get("files")
    if not isinstance(files, list) or len(files) != 1:
        raise PreviewError("H0..H1 must contain exactly one changed file.")
    changed = files[0]
    if not isinstance(changed, Mapping) or set(changed) != {
        "path",
        "status",
        "previous_path",
    }:
        raise PreviewError("Changed-file metadata has an unexpected shape.")
    if (
        str(changed.get("path") or "") != TYPE_FILE_RELATIVE_PATH.as_posix()
        or str(changed.get("status") or "") != "modified"
        or changed.get("previous_path") not in (None, "")
    ):
        raise PreviewError(
            "H0..H1 must modify only web/src/lib/database.types.ts without rename."
        )

    source_root = _bounded_path(
        source_root, root=source_root, label="H0 checkout", kind="directory"
    )
    head_root = _bounded_path(
        head_root, root=head_root, label="H1 checkout", kind="directory"
    )
    for relative_directory in IMMUTABLE_TYPE_VERIFY_DIRECTORIES:
        source_inventory = _path_blob_inventory(source_root, relative_directory)
        head_inventory = _path_blob_inventory(head_root, relative_directory)
        if source_inventory != head_inventory:
            raise PreviewError(
                f"H0 and H1 {relative_directory.as_posix()} path/blob inventories differ."
            )

    _bounded_path(
        source_root / TYPE_FILE_RELATIVE_PATH,
        root=source_root,
        label="H0 database types",
        kind="file",
    )
    head_types = _bounded_path(
        head_root / TYPE_FILE_RELATIVE_PATH,
        root=head_root,
        label="H1 database types",
        kind="file",
    )
    _raw_file_sha256(
        head_types,
        max_bytes=MAX_DATABASE_TYPES_BYTES,
        label="H1 database types",
    )
    return head_types


def load_migrations(directory: Path, *, root: Path) -> list[Migration]:
    """Read strict timestamped migrations; loose aliases fail closed."""
    directory = _bounded_path(
        directory,
        root=root,
        label="Migration directory",
        kind="directory",
    )
    migrations: list[Migration] = []
    seen: set[str] = set()
    total_bytes = 0
    for path in sorted(directory.glob("*.sql")):
        path = _bounded_path(
            path,
            root=root,
            label="Migration",
            kind="file",
        )
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
        canonical_text = _canonical_utf8_text(
            path, max_bytes=MAX_MIGRATION_BYTES, label="Migration"
        )
        total_bytes += len(canonical_text.encode("utf-8"))
        if total_bytes > MAX_MIGRATIONS_BYTES:
            raise PreviewError(
                "Migration set exceeds the aggregate untrusted-input safety limit."
            )
        sql = canonical_text.strip()
        if not sql:
            raise PreviewError(f"Migration is empty: {path.name}")
        migrations.append(
            Migration(version, name, path, sql, _canonical_sha256(canonical_text))
        )
    if not migrations:
        raise PreviewError(f"No timestamped migrations found in {directory}")
    return migrations


def _mask_sql_non_code(sql: str) -> str:
    """Mask comments and quoted regions while preserving statement boundaries."""
    masked = list(sql)

    def blank(start: int, end: int) -> None:
        for index in range(start, end):
            if masked[index] not in {"\r", "\n"}:
                masked[index] = " "

    index = 0
    length = len(sql)
    while index < length:
        if sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            if end < 0:
                end = length
            blank(index, end)
            index = end
            continue

        if sql.startswith("/*", index):
            depth = 1
            cursor = index + 2
            while cursor < length and depth:
                if sql.startswith("/*", cursor):
                    depth += 1
                    cursor += 2
                elif sql.startswith("*/", cursor):
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            if depth:
                raise PreviewError("Baseline SQL contains an unterminated block comment.")
            blank(index, cursor)
            index = cursor
            continue

        if sql[index] in {"'", '"'}:
            quote_char = sql[index]
            # PostgreSQL has standard_conforming_strings=on. A backslash is
            # therefore special only in an explicit E'...' escape string;
            # treating it as an escape in an ordinary string could mask a
            # following top-level COMMIT/ABORT from the atomicity guard.
            escape_string = (
                quote_char == "'"
                and index > 0
                and sql[index - 1] in {"e", "E"}
                and (
                    index < 2
                    or not (sql[index - 2].isalnum() or sql[index - 2] in {"_", "$"})
                )
            )
            cursor = index + 1
            while cursor < length:
                if sql[cursor] == "\\" and escape_string:
                    cursor = min(cursor + 2, length)
                    continue
                if sql[cursor] == quote_char:
                    if cursor + 1 < length and sql[cursor + 1] == quote_char:
                        cursor += 2
                        continue
                    cursor += 1
                    break
                cursor += 1
            else:
                raise PreviewError("Baseline SQL contains an unterminated quoted value.")
            blank(index, cursor)
            index = cursor
            continue

        if sql[index] == "$":
            match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", sql[index:])
            if match is not None:
                tag = match.group(0)
                end = sql.find(tag, index + len(tag))
                if end < 0:
                    raise PreviewError("Baseline SQL contains an unterminated dollar quote.")
                cursor = end + len(tag)
                blank(index, cursor)
                index = cursor
                continue

        index += 1
    return "".join(masked)


def _top_level_sql_statements(sql: str) -> list[str]:
    masked = _mask_sql_non_code(sql)
    if re.search(r"^\s*\\", masked, re.MULTILINE):
        raise PreviewError("Baseline SQL contains a psql backslash meta-command.")
    return [statement.strip() for statement in masked.split(";") if statement.strip()]


def _transaction_statement(statement: str) -> bool:
    head = statement.lstrip()[:160]
    return re.match(
        r"(?:"
        r"ABORT|BEGIN|COMMIT|END|RELEASE|ROLLBACK|SAVEPOINT|"
        r"PREPARE\s+TRANSACTION|"
        r"SET\s+TRANSACTION|"
        r"START\s+TRANSACTION|"
        r"SET\s+SESSION\s+CHARACTERISTICS\s+AS\s+TRANSACTION"
        r")\b",
        head,
        re.IGNORECASE,
    ) is not None


def _validate_baseline_sql(sql: str, *, path: Path) -> None:
    if not sql.strip():
        raise PreviewError(f"Baseline schema SQL is empty: {path}")
    for label, pattern in _BASELINE_SECRET_PATTERNS:
        if pattern.search(sql):
            # Never echo the matched value into CI logs.
            raise PreviewError(f"Baseline schema contains a prohibited {label} pattern.")
    if re.search(
        r'^\s*ALTER\s+DEFAULT\s+PRIVILEGES\s+FOR\s+(?:ROLE|USER)\s+'
        r'"?supabase_admin"?\b',
        sql,
        re.IGNORECASE | re.MULTILINE,
    ):
        raise PreviewError(
            "Baseline schema contains a prohibited supabase_admin default ACL."
        )

    statements = _top_level_sql_statements(sql)
    forbidden_dml = {"COPY", "INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE"}
    creates_public = False
    for statement in statements:
        words = re.findall(r"[A-Za-z]+", statement[:200].upper())
        if not words:
            continue
        if _transaction_statement(statement):
            raise PreviewError("Baseline schema contains top-level transaction control.")
        if words[0] in forbidden_dml:
            raise PreviewError(
                f"Baseline schema contains prohibited top-level {words[0]} DML."
            )
        if words[0] == "WITH" and re.search(
            r"\b(?:COPY|INSERT|UPDATE|DELETE|MERGE|TRUNCATE)\b",
            statement,
            re.IGNORECASE,
        ):
            raise PreviewError("Baseline schema contains prohibited top-level WITH DML.")
        if words[0] == "ALTER" and re.search(
            r"\bOWNER\s+TO\b", statement, re.IGNORECASE
        ):
            raise PreviewError("Baseline schema contains prohibited ALTER OWNER DDL.")
        if words[:3] == ["CREATE", "SCHEMA", "PUBLIC"]:
            creates_public = True
    if not creates_public:
        raise PreviewError(
            "Baseline schema must contain the non-idempotent CREATE SCHEMA public safety fuse."
        )


def _required_manifest_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PreviewError(f"Baseline manifest field {key!r} must be a non-empty string.")
    return value.strip()


def load_preview_baseline(directory: Path, *, root: Path) -> PreviewBaseline:
    """Load and verify the trusted-main schema artifact and its audit manifest."""
    directory = _bounded_path(
        directory,
        root=root,
        label="Baseline directory",
        kind="directory",
    )
    manifest_path = _bounded_path(
        directory / "manifest.json",
        root=root,
        label="Baseline manifest",
        kind="file",
    )
    try:
        raw_manifest = manifest_path.read_text(encoding="utf-8-sig")
        payload = json.loads(raw_manifest)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreviewError(f"Baseline manifest is unreadable: {manifest_path}") from exc
    if not isinstance(payload, Mapping):
        raise PreviewError("Baseline manifest must contain one JSON object.")
    if payload.get("format_version") != BASELINE_FORMAT_VERSION:
        raise PreviewError(
            f"Unsupported baseline manifest format_version; expected "
            f"{BASELINE_FORMAT_VERSION}."
        )

    source_ref = _required_manifest_string(payload, "source_project_ref")
    if source_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError("Baseline manifest source_project_ref is not Richmond production.")
    cutoff = _required_manifest_string(payload, "cutoff_version")
    if cutoff != BASELINE_CUTOFF_VERSION:
        raise PreviewError(
            f"Baseline cutoff must be the reviewed production cutoff "
            f"{BASELINE_CUTOFF_VERSION}."
        )
    try:
        datetime.strptime(cutoff, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise PreviewError("Baseline cutoff_version is not a UTC timestamp.") from exc

    schema_file = _required_manifest_string(payload, "schema_file")
    if (
        Path(schema_file).name != schema_file
        or schema_file != f"{cutoff}_public_schema.sql"
    ):
        raise PreviewError(
            "Baseline schema_file must be the cutoff-prefixed SQL filename in "
            "the trusted baseline directory."
        )
    schema_sha256 = _required_manifest_string(payload, "schema_sha256")
    if not _SHA256_RE.fullmatch(schema_sha256):
        raise PreviewError("Baseline schema_sha256 must be lowercase SHA-256 hex.")
    raw_sha256 = payload.get("raw_schema_sha256")
    if raw_sha256 is not None and (
        not isinstance(raw_sha256, str) or not _SHA256_RE.fullmatch(raw_sha256)
    ):
        raise PreviewError("Baseline raw_schema_sha256 must be lowercase SHA-256 hex.")
    if "captured_at" in payload:
        parse_api_timestamp(_required_manifest_string(payload, "captured_at"))
    for metadata_key in ("server_version", "pg_dump_version"):
        if metadata_key in payload:
            _required_manifest_string(payload, metadata_key)

    schema_path = _bounded_path(
        directory / schema_file,
        root=root,
        label="Baseline schema",
        kind="file",
    )
    schema_sql = _canonical_utf8_text(
        schema_path, max_bytes=MAX_BASELINE_BYTES, label="Baseline schema"
    )
    observed_schema_sha256 = _canonical_sha256(schema_sql)
    if observed_schema_sha256 != schema_sha256:
        raise PreviewError("Baseline schema SHA-256 does not match its trusted manifest.")
    _validate_baseline_sql(schema_sql, path=schema_path)

    inventory_payload = payload.get("schema_inventory")
    if not isinstance(inventory_payload, Mapping):
        raise PreviewError("Baseline manifest requires a schema_inventory object.")
    if set(inventory_payload) != set(_INVENTORY_FIELDS):
        raise PreviewError(
            "Baseline schema_inventory must contain exactly: "
            + ", ".join(_INVENTORY_FIELDS)
        )
    inventory: dict[str, int] = {}
    for key in _INVENTORY_FIELDS:
        value = inventory_payload[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PreviewError(
                f"Baseline schema_inventory field {key!r} must be a non-negative integer."
            )
        inventory[key] = value
    if inventory["default_privilege_rows"] != 3:
        raise PreviewError(
            "Preview baseline must retain exactly three postgres default ACL rows."
        )

    parity_exceptions = payload.get("preview_parity_exceptions")
    if parity_exceptions != list(EXPECTED_PREVIEW_PARITY_EXCEPTIONS):
        raise PreviewError(
            "Baseline preview_parity_exceptions does not match the two allowed "
            "Preview runtime exceptions."
        )

    extensions_payload = payload.get("extensions")
    if not isinstance(extensions_payload, list):
        raise PreviewError("Baseline manifest requires an ordered extensions list.")
    extensions: list[BaselineExtension] = []
    for index, item in enumerate(extensions_payload):
        if not isinstance(item, Mapping) or set(item) != {
            "name",
            "version",
            "schema",
        }:
            raise PreviewError(
                f"Baseline extension entry {index} must contain name/version/schema."
            )
        name = _required_manifest_string(item, "name")
        version = _required_manifest_string(item, "version")
        schema = _required_manifest_string(item, "schema")
        if not re.fullmatch(r"\d+(?:\.\d+)*", version):
            raise PreviewError(f"Baseline extension {name!r} has an invalid version.")
        if schema != "extensions":
            raise PreviewError(f"Baseline extension {name!r} is outside extensions schema.")
        extensions.append(BaselineExtension(name, version, schema))

    vector_extension = next(
        (extension for extension in extensions if extension.name == "vector"),
        None,
    )
    vector_exception = parity_exceptions[1]
    if (
        vector_extension is None
        or vector_extension.name != vector_exception["name"]
        or vector_extension.version != vector_exception["preview_version"]
        or vector_extension.schema != vector_exception["schema"]
    ):
        raise PreviewError(
            "Baseline vector extension must match its exact Preview parity exception."
        )
    if tuple(
        (extension.name, extension.version, extension.schema)
        for extension in extensions
    ) != EXPECTED_BASELINE_EXTENSIONS:
        raise PreviewError(
            "Baseline extensions must be exactly pgcrypto 1.3, uuid-ossp 1.1, "
            "and Preview vector 0.8.2 in order."
        )

    absorbed_payload = payload.get("absorbed_migrations")
    if not isinstance(absorbed_payload, list) or not absorbed_payload:
        raise PreviewError("Baseline manifest requires absorbed_migrations.")
    absorbed: list[BaselineMigration] = []
    previous_version = ""
    for index, item in enumerate(absorbed_payload):
        if not isinstance(item, Mapping):
            raise PreviewError(f"Absorbed migration entry {index} must be an object.")
        allowed_keys = {"version", "name", "sha256", "production_name"}
        if not set(item).issubset(allowed_keys):
            raise PreviewError(f"Absorbed migration entry {index} has unknown fields.")
        version = _required_manifest_string(item, "version")
        name = _required_manifest_string(item, "name")
        sha256 = _required_manifest_string(item, "sha256")
        production_name_raw = item.get("production_name")
        production_name = None
        if production_name_raw is not None:
            if not isinstance(production_name_raw, str):
                raise PreviewError(
                    f"Absorbed migration {version} production_name must be a string."
                )
            production_name = production_name_raw.strip()
        if not re.fullmatch(r"\d{14}", version):
            raise PreviewError(f"Absorbed migration entry {index} has an invalid version.")
        try:
            datetime.strptime(version, "%Y%m%d%H%M%S")
        except ValueError as exc:
            raise PreviewError(f"Absorbed migration {version} has an invalid timestamp.") from exc
        if version <= previous_version:
            raise PreviewError("Absorbed migrations must be strictly version ordered.")
        if version > cutoff:
            raise PreviewError(f"Absorbed migration {version} is after the cutoff.")
        if not _MIGRATION_NAME_RE.fullmatch(name):
            raise PreviewError(f"Absorbed migration {version} has an invalid filename name.")
        if not _SHA256_RE.fullmatch(sha256):
            raise PreviewError(f"Absorbed migration {version} has an invalid SHA-256.")
        if production_name is not None:
            if not _LEDGER_NAME_RE.fullmatch(production_name):
                raise PreviewError(
                    f"Absorbed migration {version} has an invalid production_name."
                )
            if production_name == name:
                raise PreviewError(
                    f"Absorbed migration {version} has a redundant production_name."
                )
        absorbed.append(BaselineMigration(version, name, sha256, production_name))
        previous_version = version
    if absorbed[-1].version != cutoff:
        raise PreviewError("Final absorbed migration does not equal the baseline cutoff.")

    return PreviewBaseline(
        directory=directory,
        manifest_path=manifest_path,
        schema_path=schema_path,
        schema_sql=schema_sql,
        schema_sha256=schema_sha256,
        cutoff_version=cutoff,
        absorbed_migrations=tuple(absorbed),
        schema_inventory=inventory,
        extensions=tuple(extensions),
    )


def _validate_absorbed_migration_set(
    baseline: PreviewBaseline,
    migrations: Sequence[Migration],
    *,
    label: str,
) -> None:
    observed = [m for m in migrations if m.version <= baseline.cutoff_version]
    expected = baseline.absorbed_migrations
    if len(observed) != len(expected):
        raise PreviewError(
            f"{label} absorbed migration count does not match the trusted manifest."
        )
    for migration, manifest_entry in zip(observed, expected):
        if (migration.version, migration.name) != (
            manifest_entry.version,
            manifest_entry.name,
        ):
            raise PreviewError(
                f"{label} absorbed migration identity differs at "
                f"{manifest_entry.version}."
            )
        if migration.sha256 != manifest_entry.sha256:
            raise PreviewError(
                f"{label} absorbed migration SHA-256 differs at "
                f"{manifest_entry.version}."
            )


def validate_baseline_migrations(
    baseline: PreviewBaseline,
    pr_migrations: Sequence[Migration],
    trusted_migrations: Sequence[Migration],
) -> list[Migration]:
    """Prove the absorbed prefix immutable and return only the PR suffix."""
    forbidden = sorted(
        migration.version
        for migration in pr_migrations
        if (
            migration.version in NON_REPLAYABLE_MIGRATION_VERSIONS
            or migration.name in NON_REPLAYABLE_MIGRATION_NAMES
        )
    )
    if forbidden:
        raise PreviewError(
            "Non-replayable migration 134 is present in the PR migration set."
        )
    _validate_absorbed_migration_set(
        baseline, trusted_migrations, label="Trusted-main"
    )
    _validate_absorbed_migration_set(baseline, pr_migrations, label="PR")
    pr_by_version = {migration.version: migration for migration in pr_migrations}
    for trusted_migration in trusted_migrations:
        if trusted_migration.version <= baseline.cutoff_version:
            continue
        pr_migration = pr_by_version.get(trusted_migration.version)
        if pr_migration is None or (
            pr_migration.name != trusted_migration.name
            or pr_migration.sha256 != trusted_migration.sha256
        ):
            raise PreviewError(
                "PR does not contain the exact trusted-main migration "
                f"{trusted_migration.version}."
            )
    pending = [m for m in pr_migrations if m.version > baseline.cutoff_version]
    for migration in pending:
        if any(
            _transaction_statement(statement)
            for statement in _top_level_sql_statements(migration.sql)
        ):
            raise PreviewError(
                f"{migration.path.name} contains explicit transaction control. "
                "The Management API bootstrap requires an atomic migration body."
            )
    return pending


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
        for key in ("result", "data", "branches", "deployments", "keys", "envs"):
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
        # A 340 KB schema restore with hundreds of indexes can legitimately run
        # longer than the generic control-plane default. Ambiguous writes are
        # still never retried; callers reconcile them through the ledger.
        self.api = api or JsonApiClient(SUPABASE_API_BASE, token, timeout=120.0)

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
                "desired_instance_size": "micro",
            },
            expected=(201,),
        )
        if isinstance(payload, Mapping):
            _assert_explicit_branch_adoption_boundaries(payload)
        branch = BranchRecord.from_payload(payload)
        branch.assert_preview_adoption_boundaries()
        return branch

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


def controller_preview_branches(
    client: SupabaseManagementClient, parent_ref: str
) -> list[BranchRecord]:
    """Return only exact, safe branches owned by this PR Preview controller."""
    matches: list[BranchRecord] = []
    for branch in client.list_branches(parent_ref):
        name_match = re.fullmatch(r"pr-([1-9][0-9]*)-preview", branch.name)
        if name_match is None:
            continue
        try:
            branch.assert_safe_preview(
                parent_ref=parent_ref,
                expected_name=preview_branch_name(int(name_match.group(1))),
                git_branch=validate_git_branch(branch.git_branch),
            )
        except PreviewError:
            continue
        matches.append(branch)
    return matches


def reconcile_created_supabase_branch(
    client: SupabaseManagementClient,
    parent_ref: str,
    name: str,
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> BranchRecord | None:
    """Poll a bounded read window after one possibly committed create POST."""
    deadline = time.monotonic() + min(max(timeout_seconds, 0.0), 30.0)
    while True:
        candidate = find_branch(client, parent_ref, name)
        if candidate is not None:
            return candidate
        if time.monotonic() >= deadline:
            return None
        time.sleep(max(min(interval_seconds, 5.0), 0.05))


def _branch_present(
    client: SupabaseManagementClient,
    parent_ref: str,
    identity: BranchRecord,
) -> bool:
    return any(
        branch.id == identity.id and branch.project_ref == identity.project_ref
        for branch in client.list_branches(parent_ref)
    )


def _read_exact_branch_identity(
    client: SupabaseManagementClient,
    parent_ref: str,
    identity: BranchRecord,
) -> BranchRecord:
    matches = [
        branch
        for branch in client.list_branches(parent_ref)
        if branch.project_ref == identity.project_ref
    ]
    if len(matches) != 1:
        raise PreviewError(
            "Supabase branch identity check could not find exactly one immutable "
            "project ref."
        )
    observed = matches[0]
    if observed.id != identity.id:
        raise PreviewError(
            "Supabase branch identity check observed a replaced branch UUID."
        )
    return observed


def _read_stale_sweep_branch_identity(
    client: SupabaseManagementClient,
    parent_ref: str,
    identity: BranchRecord,
) -> BranchRecord:
    matches = [
        branch
        for branch in client.list_branches(parent_ref)
        if branch.project_ref == identity.project_ref
    ]
    if len(matches) != 1 or matches[0].id != identity.id:
        raise PreviewSelectionChanged(
            "Supabase stale-sweep selection disappeared or was replaced; "
            "refusing mutable-name cleanup."
        )
    return matches[0]


def wait_for_active_preview(
    client: SupabaseManagementClient,
    *,
    parent_ref: str,
    pr_number: int,
    git_branch: str,
    branch: BranchRecord,
    timeout_seconds: float,
    interval_seconds: float,
) -> BranchRecord:
    """Poll the same immutable branch until its authoritative service is healthy.

    Supabase's deprecated top-level ``status`` describes its built-in migration
    workflow and may remain ``MIGRATIONS_FAILED`` after the clean-room restore.
    Only ``preview_project_status`` is authoritative for API/type generation.
    """
    expected_name = preview_branch_name(pr_number)
    branch.assert_safe_preview(
        parent_ref=parent_ref, expected_name=expected_name, git_branch=git_branch
    )
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    last_status = ""
    while True:
        observed = _read_exact_branch_identity(client, parent_ref, branch)
        observed.assert_safe_preview(
            parent_ref=parent_ref,
            expected_name=expected_name,
            git_branch=git_branch,
        )
        observed.assert_preview_adoption_boundaries()
        last_status = observed.preview_project_status
        if last_status == "ACTIVE_HEALTHY":
            return observed
        if time.monotonic() >= deadline:
            raise PreviewError(
                "Timed out waiting for the exact Supabase Preview service to "
                f"be ACTIVE_HEALTHY; last preview_project_status={last_status!r}."
            )
        time.sleep(max(min(interval_seconds, 5.0), 0.0))


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
_EMPTY_APPLICATION_CATALOG_QUERY = """\
select object_kind, object_name
from (
  select 'public relation'::text as object_kind, c.relname::text as object_name
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relkind in ('r', 'p', 'v', 'm', 'S', 'f', 'c')
  union all
  select 'public routine', p.proname
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
  union all
  select 'public type', t.typname
  from pg_type t
  join pg_namespace n on n.oid = t.typnamespace
  where n.nspname = 'public'
    and t.typrelid = 0
    and not (t.typelem <> 0 and t.typname like '\\_%' escape '\\')
  union all
  select 'public collation', c.collname
  from pg_collation c
  join pg_namespace n on n.oid = c.collnamespace
  where n.nspname = 'public'
  union all
  select 'public conversion', c.conname
  from pg_conversion c
  join pg_namespace n on n.oid = c.connamespace
  where n.nspname = 'public'
  union all
  select 'migration ledger', c.relname
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'supabase_migrations'
    and c.relname = 'schema_migrations'
  union all
  select 'database event trigger', e.evtname
  from pg_event_trigger e
  where e.evtname = 'ensure_rls'
) as application_objects
order by object_kind, object_name
limit 50
"""

_SCHEMA_INVENTORY_QUERY = """\
select
  (select count(*)::bigint
   from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind in ('r', 'p')) as tables,
  (select count(*)::bigint
   from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind in ('v', 'm')) as views,
  (select count(*)::bigint
   from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.prokind in ('f', 'p')) as functions,
  (select count(*)::bigint
   from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.prokind in ('f', 'p')
     and p.prosecdef) as security_definer_functions,
  (select count(*)::bigint
   from pg_policy p join pg_class c on c.oid = p.polrelid
   join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public') as policies,
  (select count(*)::bigint
   from pg_index i join pg_class c on c.oid = i.indexrelid
   join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public') as indexes,
  (select count(*)::bigint
   from pg_constraint c join pg_namespace n on n.oid = c.connamespace
   where n.nspname = 'public') as constraints,
  (select count(*)::bigint
   from pg_trigger t join pg_class c on c.oid = t.tgrelid
   join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and not t.tgisinternal) as triggers,
  (select count(*)::bigint
   from pg_event_trigger e
   where e.evtname = 'ensure_rls'
     and e.evtevent = 'ddl_command_end'
     and e.evtenabled = 'O'
     and cardinality(e.evttags) = 3
     and e.evttags @> array['CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO']::text[]
     and e.evttags <@ array['CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO']::text[]
     and e.evtfoid = 'public.rls_auto_enable()'::regprocedure) as event_triggers,
  (select count(*)::bigint
   from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public'
     and pg_get_userbyid(c.relowner) <> 'postgres') as non_postgres_owned_relations,
  (select count(*)::bigint
   from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public'
     and pg_get_userbyid(p.proowner) <> 'postgres') as non_postgres_owned_routines,
  (select count(*)::bigint
   from pg_event_trigger e
   where e.evtname = 'ensure_rls'
     and pg_get_userbyid(e.evtowner) <> 'postgres') as non_postgres_owned_event_triggers,
  (select count(*)::bigint
   from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind = 'S') as sequences,
  (select count(*)::bigint
   from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind in ('r', 'p')
     and c.relrowsecurity) as rls_enabled,
  (select count(*)::bigint
   from pg_default_acl d join pg_namespace n on n.oid = d.defaclnamespace
   where n.nspname = 'public') as default_privilege_rows
"""
_EXTENSION_INVENTORY_QUERY = """\
select e.extname as name, e.extversion as version, n.nspname as schema
from pg_extension e
join pg_namespace n on n.oid = e.extnamespace
where e.extname in ('pgcrypto', 'uuid-ossp', 'vector')
order by e.extname
"""
_LEDGER_INIT_SQL = """\
create schema if not exists supabase_migrations;
create table if not exists supabase_migrations.schema_migrations (
  version text not null primary key,
  statements text[],
  name text,
  created_by text,
  idempotency_key text unique,
  rollback text[]
);
alter table supabase_migrations.schema_migrations
  add column if not exists statements text[];
alter table supabase_migrations.schema_migrations
  add column if not exists name text;
alter table supabase_migrations.schema_migrations
  add column if not exists created_by text;
alter table supabase_migrations.schema_migrations
  add column if not exists idempotency_key text;
alter table supabase_migrations.schema_migrations
  add column if not exists rollback text[];
do $$
begin
  if not exists (
    select 1
    from pg_index i
    join pg_attribute a
      on a.attrelid = i.indrelid
     and a.attnum = any(i.indkey::smallint[])
    where i.indrelid =
      'supabase_migrations.schema_migrations'::regclass
      and i.indisunique
      and i.indnkeyatts = 1
      and a.attname = 'idempotency_key'
  ) then
    alter table supabase_migrations.schema_migrations
      add constraint schema_migrations_idempotency_key_key
      unique (idempotency_key);
  end if;
end
$$;
"""


def _assert_nonproduction_branch(branch: BranchRecord) -> None:
    if (
        branch.parent_project_ref != PRODUCTION_PROJECT_REF
        or branch.project_ref == PRODUCTION_PROJECT_REF
        or branch.project_ref == branch.parent_project_ref
        or branch.is_default
        or branch.persistent
    ):
        raise PreviewError(
            "Refusing schema restore outside an immutable non-production branch."
        )


def verify_production_ledger(
    client: SupabaseManagementClient,
    parent_ref: str,
    baseline: PreviewBaseline,
    trusted_migrations: Sequence[Migration],
    pr_migrations: Sequence[Migration],
) -> ProductionLedgerState:
    """Verify the live production history prefix without ever mutating it."""
    if parent_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError("Refusing production ledger verification for an unknown ref.")
    payload = client.query(parent_ref, _LEDGER_QUERY, read_only=True)
    rows = _rows(payload, context="production migration ledger")
    observed_prefix: list[tuple[str, str]] = []
    observed_suffix: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        version = str(row.get("version") or "")
        name = str(row.get("name") or "")
        if not re.fullmatch(r"\d{14}", version) or version in seen:
            raise PreviewError("Production migration ledger has invalid version identity.")
        seen.add(version)
        if version <= baseline.cutoff_version:
            observed_prefix.append((version, name))
        else:
            observed_suffix.append((version, name))
    expected_prefix = [
        (entry.version, entry.production_ledger_name)
        for entry in baseline.absorbed_migrations
    ]
    if observed_prefix != expected_prefix:
        raise PreviewError(
            "Production migration ledger prefix does not match the trusted baseline manifest."
        )
    trusted_suffix = [
        migration
        for migration in trusted_migrations
        if migration.version > baseline.cutoff_version
    ]
    trusted_identities = [
        (migration.version, migration.name) for migration in trusted_suffix
    ]
    if observed_suffix != trusted_identities[: len(observed_suffix)]:
        raise PreviewError(
            "Production post-cutoff ledger is not an ordered prefix of trusted main."
        )
    pr_by_version = {migration.version: migration for migration in pr_migrations}
    for trusted_migration in trusted_suffix[: len(observed_suffix)]:
        pr_migration = pr_by_version.get(trusted_migration.version)
        if pr_migration is None or (
            pr_migration.name != trusted_migration.name
            or pr_migration.sha256 != trusted_migration.sha256
        ):
            raise PreviewError(
                "PR does not contain the exact trusted production migration "
                f"{trusted_migration.version}."
            )
    return ProductionLedgerState(
        tuple(str(row.get("version") or "") for row in rows)
    )


def verify_empty_preview_branch(
    client: SupabaseManagementClient,
    branch: BranchRecord,
) -> None:
    """Prove no application object or migration ledger exists before restore."""
    _assert_nonproduction_branch(branch)
    payload = client.query(
        branch.project_ref, _EMPTY_APPLICATION_CATALOG_QUERY, read_only=True
    )
    objects = _rows(payload, context="empty Preview application catalog")
    if objects:
        labels = sorted(
            {
                str(row.get("object_kind") or "unknown object")
                for row in objects
            }
        )
        raise PreviewError(
            "Preview branch is not an empty application catalog; found: "
            + ", ".join(labels)
        )


def _inventory_assertion_sql(inventory: Mapping[str, int]) -> str:
    checks = []
    for field in _INVENTORY_FIELDS:
        checks.append(
            f"  if observed.{field} <> {int(inventory[field])} then\n"
            f"    raise exception 'Preview baseline inventory mismatch: {field}' "
            "using errcode = '55000';\n"
            "  end if;"
        )
    return (
        "do $preview_inventory$\n"
        "declare\n"
        "  observed record;\n"
        "begin\n"
        f"  {_SCHEMA_INVENTORY_QUERY.strip()} into observed;\n"
        + "\n".join(checks)
        + "\nend\n$preview_inventory$;"
    )


def _expected_extensions(
    baseline: PreviewBaseline,
) -> list[tuple[str, str, str]]:
    return [
        (extension.name, extension.version, extension.schema)
        for extension in baseline.extensions
    ]


def _extension_pin_sql(baseline: PreviewBaseline) -> str:
    return "\n".join(
        "create extension if not exists "
        f"{_sql_identifier(extension.name)} with schema "
        f"{_sql_identifier(extension.schema)} version "
        f"{_sql_literal(extension.version)};"
        for extension in baseline.extensions
    )


def _extension_assertion_sql(baseline: PreviewBaseline) -> str:
    expected_json = json.dumps(
        [
            {
                "name": extension.name,
                "version": extension.version,
                "schema": extension.schema,
            }
            for extension in baseline.extensions
        ],
        separators=(",", ":"),
    )
    observed_json = (
        "select coalesce(jsonb_agg(jsonb_build_object("
        "'name', e.extname, 'version', e.extversion, 'schema', n.nspname) "
        "order by e.extname), '[]'::jsonb) "
        "from pg_extension e join pg_namespace n on n.oid = e.extnamespace "
        "where e.extname in ('pgcrypto', 'uuid-ossp', 'vector')"
    )
    return (
        "do $preview_extensions$\n"
        "begin\n"
        f"  if ({observed_json}) is distinct from "
        f"{_sql_literal(expected_json)}::jsonb then\n"
        "    raise exception 'Preview baseline extension inventory mismatch' "
        "using errcode = '55000';\n"
        "  end if;\n"
        "end\n$preview_extensions$;"
    )


def _read_extension_inventory(
    client: SupabaseManagementClient,
    branch: BranchRecord,
) -> list[tuple[str, str, str]]:
    rows = _rows(
        client.query(
            branch.project_ref, _EXTENSION_INVENTORY_QUERY, read_only=True
        ),
        context="restored extension inventory",
    )
    return [
        (
            str(row.get("name") or ""),
            str(row.get("version") or ""),
            str(row.get("schema") or ""),
        )
        for row in rows
    ]


def _read_schema_inventory(
    client: SupabaseManagementClient,
    branch: BranchRecord,
    *,
    context: str,
) -> dict[str, int]:
    rows = _rows(
        client.query(branch.project_ref, _SCHEMA_INVENTORY_QUERY, read_only=True),
        context=context,
    )
    if len(rows) != 1:
        raise PreviewError(f"{context.capitalize()} returned an unexpected shape.")
    inventory: dict[str, int] = {}
    for field in _INVENTORY_FIELDS:
        try:
            inventory[field] = int(rows[0].get(field))
        except (TypeError, ValueError) as exc:
            raise PreviewError(
                f"{context.capitalize()} field {field!r} is invalid."
            ) from exc
    return inventory


def verify_post_migration_security(
    client: SupabaseManagementClient,
    branch: BranchRecord,
    baseline: PreviewBaseline,
) -> None:
    """Recheck invariants that no post-baseline migration may weaken."""

    _assert_nonproduction_branch(branch)
    observed = _read_schema_inventory(
        client, branch, context="post-migration schema inventory"
    )
    if observed["tables"] != observed["rls_enabled"]:
        raise PreviewError("Post-migration Preview contains a table without RLS.")
    for field in (
        "event_triggers",
        "non_postgres_owned_relations",
        "non_postgres_owned_routines",
        "non_postgres_owned_event_triggers",
        "default_privilege_rows",
    ):
        if observed[field] != baseline.schema_inventory[field]:
            raise PreviewError(
                f"Post-migration Preview weakened security invariant: {field}."
            )
    if _read_extension_inventory(client, branch) != _expected_extensions(baseline):
        raise PreviewError(
            "Post-migration extension inventory does not match the manifest."
        )


def _expected_preview_ledger(
    baseline: PreviewBaseline,
) -> list[tuple[str, str]]:
    return [(entry.version, entry.name) for entry in baseline.absorbed_migrations]


def _read_existing_ledger(
    client: SupabaseManagementClient,
    branch: BranchRecord,
) -> list[Mapping[str, Any]]:
    payload = client.query(branch.project_ref, _LEDGER_QUERY, read_only=True)
    return _rows(payload, context="migration ledger")


def _ledger_pairs(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for row in rows:
        version = str(row.get("version") or "")
        name = str(row.get("name") or "")
        if not re.fullmatch(r"\d{14}", version):
            raise PreviewError("Preview ledger contains an invalid migration version.")
        pairs.append((version, name))
    return pairs


def apply_preview_baseline(
    client: SupabaseManagementClient,
    branch: BranchRecord,
    baseline: PreviewBaseline,
) -> None:
    """Replace only an empty Preview public schema and seed absorbed history."""
    _assert_nonproduction_branch(branch)
    verify_empty_preview_branch(client, branch)

    role_guard = (
        "do $preview_role_guard$\n"
        "begin\n"
        "  if current_user <> 'postgres' then\n"
        "    raise exception 'Preview restore requires postgres execution role' "
        "using errcode = '42501';\n"
        "  end if;\n"
        "end\n$preview_role_guard$;"
    )
    empty_guard = (
        "do $preview_empty_guard$\n"
        "begin\n"
        "  if exists (\n"
        f"    {_EMPTY_APPLICATION_CATALOG_QUERY.strip()}\n"
        "  ) then\n"
        "    raise exception 'Preview application catalog is no longer empty' "
        "using errcode = '55000';\n"
        "  end if;\n"
        "end\n$preview_empty_guard$;"
    )
    seed_values = ",\n".join(
        f"  ({_sql_literal(entry.version)}, {_sql_literal(entry.name)})"
        for entry in baseline.absorbed_migrations
    )
    schema_body = baseline.schema_sql.rstrip()
    batch = (
        "begin;\n"
        f"{role_guard}\n"
        f"{empty_guard}\n"
        f"{_extension_pin_sql(baseline)}\n"
        "drop schema public cascade;\n"
        f"{schema_body}\n"
        f"{_inventory_assertion_sql(baseline.schema_inventory)}\n"
        f"{_extension_assertion_sql(baseline)}\n"
        f"{_LEDGER_INIT_SQL.rstrip()}\n"
        "insert into supabase_migrations.schema_migrations (version, name) values\n"
        f"{seed_values};\n"
        "commit;"
    )
    expected_ledger = _expected_preview_ledger(baseline)
    try:
        client.query(branch.project_ref, batch, read_only=False)
    except ApiError as exc:
        if not exc.ambiguous:
            raise
        # Never retry a possibly committed schema restore. One read-only ledger
        # reconciliation is the transaction's commit witness.
        try:
            observed_ledger = _ledger_pairs(_read_existing_ledger(client, branch))
        except ApiError as reconciliation_error:
            raise PreviewError(
                "Baseline restore has ambiguous state and was not replayed."
            ) from reconciliation_error
        if observed_ledger != expected_ledger:
            raise PreviewError(
                "Baseline restore has ambiguous state and no exact ledger parity."
            ) from exc

    observed_ledger = _ledger_pairs(_read_existing_ledger(client, branch))
    if observed_ledger != expected_ledger:
        raise PreviewError("Baseline restore did not seed exact absorbed ledger parity.")
    observed_inventory = _read_schema_inventory(
        client, branch, context="restored schema inventory"
    )
    for field in _INVENTORY_FIELDS:
        if observed_inventory[field] != baseline.schema_inventory[field]:
            raise PreviewError(f"Restored schema inventory mismatch: {field}.")
    if _read_extension_inventory(client, branch) != _expected_extensions(baseline):
        raise PreviewError("Restored extension inventory does not match the manifest.")


def _is_missing_ledger_error(exc: ApiError) -> bool:
    """Match only PostgreSQL undefined_table for our exact ledger relation."""
    if not exc.response_body:
        return False
    try:
        payload = json.loads(exc.response_body)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, Mapping):
        return False
    error = payload.get("error")
    if isinstance(error, Mapping):
        payload = error
    code = str(payload.get("code") or "")
    message = str(payload.get("message") or "").lower()
    return (
        (code == "42P01" or re.search(r"\b42p01\b", message) is not None)
        and 'relation "supabase_migrations.schema_migrations" does not exist'
        in message
    )


def _database_error_code(exc: ApiError) -> str:
    """Extract a PostgreSQL code only from the Management API JSON error body."""

    if not exc.response_body:
        return ""
    try:
        payload = json.loads(exc.response_body)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, Mapping):
        return ""
    error = payload.get("error")
    if isinstance(error, Mapping):
        payload = error
    return str(payload.get("code") or "").upper()


def read_ledger(
    client: SupabaseManagementClient, branch: BranchRecord
) -> list[Mapping[str, Any]]:
    try:
        payload = client.query(branch.project_ref, _LEDGER_QUERY, read_only=True)
    except ApiError as exc:
        if not _is_missing_ledger_error(exc):
            raise
        # A brand-new data-less branch has no CLI-managed history table. Use
        # a full, CLI-compatible idempotent shape, then re-run the exact read.
        # No other query error is swallowed.
        client.query(branch.project_ref, _LEDGER_INIT_SQL, read_only=False)
        payload = client.query(branch.project_ref, _LEDGER_QUERY, read_only=True)
    return _rows(payload, context="migration ledger")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def apply_migration(
    client: SupabaseManagementClient,
    branch: BranchRecord,
    migration: Migration,
    *,
    allow_trusted_inheritance: bool = False,
) -> bool:
    """Apply a migration; return false only for proven production inheritance."""
    if (
        migration.version in NON_REPLAYABLE_MIGRATION_VERSIONS
        or migration.name in NON_REPLAYABLE_MIGRATION_NAMES
    ):
        raise PreviewError("Refusing to replay non-replayable migration 134.")
    if any(
        _transaction_statement(statement)
        for statement in _top_level_sql_statements(migration.sql)
    ):
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
        ledger = {
            str(row.get("version") or ""): str(row.get("name") or "")
            for row in read_ledger(client, branch)
        }
        exact_ledger_witness = ledger.get(migration.version) == migration.name
        if exc.ambiguous and exact_ledger_witness:
            # A timed-out write may have committed. Never replay blindly: the
            # exact ledger row is the transaction's commit witness.
            return True
        if (
            allow_trusted_inheritance
            and _database_error_code(exc) == "23505"
            and exact_ledger_witness
        ):
            # Supabase can finish cloning the trusted production suffix after
            # the clean-room baseline transaction. Accept only a version that
            # the earlier read-only production gate proved was already live.
            return False
        if not exc.ambiguous:
            raise
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
    return True


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

    def project(self) -> Mapping[str, Any]:
        payload = self.api.request(
            "GET",
            f"/v9/projects/{quote(self.project_id, safe='')}",
            query={"teamId": self.team_id},
        )
        if not isinstance(payload, Mapping):
            raise PreviewError("Vercel project lookup returned an invalid payload.")
        return payload

    def project_name(self) -> str:
        """Resolve the project ID to the name required by create-deployment."""
        payload = self.project()
        name = str(payload.get("name") or "").strip()
        if not name or len(name) > 100:
            raise PreviewError("Vercel project lookup did not return a valid name.")
        return name

    def list_envs(self, git_branch: str) -> list[Mapping[str, Any]]:
        payload = self.api.request(
            "GET",
            f"/v10/projects/{quote(self.project_id, safe='')}/env",
            query={"teamId": self.team_id, "gitBranch": git_branch, "limit": "100"},
        )
        return _rows(payload, context="Vercel environment list")

    def list_all_preview_envs(self) -> list[Mapping[str, Any]]:
        payload = self.api.request(
            "GET",
            f"/v10/projects/{quote(self.project_id, safe='')}/env",
            query={
                "teamId": self.team_id,
                "target": "preview",
                "limit": "100",
            },
        )
        rows = _rows(payload, context="Vercel Preview environment list")
        if len(rows) >= 100:
            raise PreviewError(
                "Vercel Preview environment inventory reached the bounded page limit."
            )
        return rows

    def create_preview_env(self, *, key: str, value: str, git_branch: str) -> None:
        if key not in PREVIEW_ALLOWED_ENV_KEYS:
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

    @staticmethod
    def _assert_fresh_created_deployment(
        deployment: "VercelDeployment", *, request_started_at: datetime
    ) -> None:
        observed_now = datetime.now(timezone.utc)
        if deployment.created_at < request_started_at:
            raise PreviewError(
                "Vercel deployment creation time predates this exact create request."
            )
        if deployment.created_at > observed_now + timedelta(
            seconds=MAX_CONTROL_PLANE_FUTURE_SKEW_SECONDS
        ):
            raise PreviewError(
                "Vercel deployment creation time is implausibly in the future."
            )

    def create_preview_deployment(
        self,
        *,
        git_owner: str,
        git_repo: str,
        git_branch: str,
        source_head_sha: str,
        timeout_seconds: float = 600.0,
        interval_seconds: float = 5.0,
        on_created: Callable[[str], None] | None = None,
    ) -> "VercelDeployment":
        project_name = self.project_name()
        git_owner = validate_github_repo_part(git_owner, label="GitHub owner")
        git_repo = validate_github_repo_part(git_repo, label="GitHub repository")
        git_branch = validate_git_branch(git_branch)
        source_head_sha = validate_git_sha(
            source_head_sha, label="Approved deployment SHA"
        )
        request_started_at = datetime.now(timezone.utc) - timedelta(
            seconds=CREATE_REQUEST_CLOCK_SKEW_SECONDS
        )
        returned_id = ""
        try:
            payload = self.api.request(
                "POST",
                "/v13/deployments",
                query={"teamId": self.team_id},
                # Vercel selects Preview when target is omitted. A literal
                # "preview" target can instead be treated as a custom environment.
                body={
                    "name": project_name,
                    "project": self.project_id,
                    "gitSource": {
                        "type": "github",
                        "org": git_owner,
                        "repo": git_repo,
                        "ref": git_branch,
                        "sha": source_head_sha,
                    },
                },
                expected=(200, 201),
            )
        except ApiError as exc:
            if not _mutation_may_have_succeeded(exc):
                raise
        else:
            if isinstance(payload, Mapping):
                candidate_id = str(payload.get("id") or "").strip()
                if candidate_id.startswith("dpl_"):
                    returned_id = candidate_id
        deployment_id = ""
        first_state: VercelDeployment | None = None
        if returned_id:
            try:
                candidate = self.get_preview_deployment(
                    returned_id,
                    git_owner=git_owner,
                    git_repo=git_repo,
                    git_branch=git_branch,
                    source_head_sha=source_head_sha,
                )
                self._assert_fresh_created_deployment(
                    candidate, request_started_at=request_started_at
                )
            except (ApiError, PreviewError):
                # A returned ID is not a safe persistence or deletion target
                # until its immutable project/Preview/Git/time identity passes.
                # Reconcile the actual exact candidate without mutating this ID.
                pass
            else:
                deployment_id = returned_id
                first_state = candidate
        if not deployment_id:
            # A 2xx response with invalid JSON, a malformed payload, or no valid
            # immutable ID may still have created the deployment. Reconcile by
            # exact fresh identity; never issue a second POST.
            deployment_id = self.reconcile_ambiguous_preview_deployment(
                request_started_at=request_started_at,
                git_owner=git_owner,
                git_repo=git_repo,
                git_branch=git_branch,
                source_head_sha=source_head_sha,
            )
        try:
            if on_created is not None:
                on_created(deployment_id)
            deadline = time.monotonic() + timeout_seconds
            last = first_state
            while True:
                if last is None:
                    last = self.get_preview_deployment(
                        deployment_id,
                        git_owner=git_owner,
                        git_repo=git_repo,
                        git_branch=git_branch,
                        source_head_sha=source_head_sha,
                    )
                    self._assert_fresh_created_deployment(
                        last, request_started_at=request_started_at
                    )
                if last.ready_state == "READY":
                    return last
                if last.ready_state in {"BLOCKED", "CANCELED", "ERROR"}:
                    raise PreviewError(
                        "Vercel exact-SHA Preview deployment failed: "
                        f"state={last.ready_state}."
                    )
                if time.monotonic() >= deadline:
                    break
                time.sleep(interval_seconds)
                last = None
            state = last.ready_state if last else "UNKNOWN"
            raise PreviewError(
                "Timed out waiting for exact-SHA Vercel Preview deployment: "
                f"state={state}."
            )
        except Exception:
            try:
                self.rollback_created_deployment(deployment_id)
            except Exception as cleanup_error:
                print(
                    "::warning::Exact Vercel deployment rollback needs follow-up: "
                    f"{cleanup_error}",
                    file=sys.stderr,
                )
            raise

    def reconcile_ambiguous_preview_deployment(
        self,
        *,
        request_started_at: datetime,
        git_owner: str,
        git_repo: str,
        git_branch: str,
        source_head_sha: str,
    ) -> str:
        """Find exactly one freshly created, fully attested deployment; never retry POST."""
        deadline = time.monotonic() + 30.0
        while time.monotonic() <= deadline:
            payload = self.api.request(
                "GET",
                "/v6/deployments",
                query={
                    "teamId": self.team_id,
                    "projectId": self.project_id,
                    "target": "preview",
                    "sha": source_head_sha,
                    "limit": "20",
                },
            )
            candidates: list[VercelDeployment] = []
            rows = _rows(payload, context="Vercel deployment reconciliation")
            if len(rows) >= 20:
                raise PreviewError(
                    "Vercel deployment reconciliation reached its bounded page limit."
                )
            for row in rows:
                deployment_id = str(row.get("uid") or row.get("id") or "").strip()
                if not deployment_id.startswith("dpl_"):
                    continue
                try:
                    deployment = self.get_preview_deployment(
                        deployment_id,
                        git_owner=git_owner,
                        git_repo=git_repo,
                        git_branch=git_branch,
                        source_head_sha=source_head_sha,
                    )
                except ApiError as candidate_error:
                    if candidate_error.status in {401, 403}:
                        raise
                    continue
                except PreviewError:
                    continue
                try:
                    self._assert_fresh_created_deployment(
                        deployment, request_started_at=request_started_at
                    )
                except PreviewError:
                    continue
                candidates.append(deployment)
            if len(candidates) == 1:
                return candidates[0].id
            if len(candidates) > 1:
                cleanup_failures: list[str] = []
                for deployment in candidates:
                    try:
                        self.rollback_created_deployment(deployment.id)
                    except Exception:
                        cleanup_failures.append(deployment.id)
                if cleanup_failures:
                    raise PreviewError(
                        "Ambiguous Vercel create produced multiple exact deployments; "
                        "retirement needs follow-up for IDs="
                        + ",".join(cleanup_failures)
                    )
                raise PreviewError(
                    "Ambiguous Vercel create produced multiple exact deployments; "
                    "all were retired."
                )
            time.sleep(5.0)
        raise PreviewError(
            "Ambiguous Vercel create could not be reconciled to an exact "
            "deployment. ACTION: inspect the failed run and exact branch/SHA "
            "deployments before retrying anything."
        )

    def rollback_created_deployment(self, deployment_id: str) -> None:
        """Retire only an ID already attested exact and fresh by this invocation."""
        if not deployment_id.startswith("dpl_"):
            raise PreviewError("Refusing rollback for an invalid deployment ID.")
        try:
            self.api.request(
                "PATCH",
                f"/v12/deployments/{quote(deployment_id, safe='')}/cancel",
                query={"teamId": self.team_id},
                expected=(200,),
            )
        except ApiError as exc:
            if exc.status not in {400, 404, 409}:
                raise
        try:
            self.api.request(
                "DELETE",
                f"/v13/deployments/{quote(deployment_id, safe='')}",
                query={"teamId": self.team_id},
                expected=(200,),
            )
        except ApiError as exc:
            if exc.status != 404:
                raise

    def get_preview_deployment(
        self,
        deployment_id: str,
        *,
        git_owner: str,
        git_repo: str,
        git_branch: str,
        source_head_sha: str,
    ) -> "VercelDeployment":
        payload = self.api.request(
            "GET",
            f"/v13/deployments/{quote(deployment_id, safe='')}",
            query={"teamId": self.team_id},
        )
        if not isinstance(payload, Mapping):
            raise PreviewError("Vercel deployment lookup returned an invalid payload.")
        return VercelDeployment.from_payload(
            payload,
            expected_id=deployment_id,
            expected_project_id=self.project_id,
            git_owner=git_owner,
            git_repo=git_repo,
            git_branch=git_branch,
            source_head_sha=source_head_sha,
        )

    def retire_preview_deployment(
        self,
        deployment_id: str,
        *,
        git_owner: str,
        git_repo: str,
        git_branch: str,
        source_head_sha: str,
    ) -> None:
        try:
            deployment = self.get_preview_deployment(
                deployment_id,
                git_owner=git_owner,
                git_repo=git_repo,
                git_branch=git_branch,
                source_head_sha=source_head_sha,
            )
        except ApiError as exc:
            if exc.status == 404:
                return
            raise
        if deployment.ready_state not in {"CANCELED", "ERROR", "READY", "BLOCKED"}:
            self.api.request(
                "PATCH",
                f"/v12/deployments/{quote(deployment_id, safe='')}/cancel",
                query={"teamId": self.team_id},
                expected=(200,),
            )
        try:
            self.api.request(
                "DELETE",
                f"/v13/deployments/{quote(deployment_id, safe='')}",
                query={"teamId": self.team_id},
                expected=(200,),
            )
        except ApiError as exc:
            if exc.status != 404:
                raise


@dataclass(frozen=True)
class VercelDeployment:
    id: str
    url: str
    ready_state: str
    source_head_sha: str
    created_at: datetime

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        expected_id: str,
        expected_project_id: str,
        git_owner: str,
        git_repo: str,
        git_branch: str,
        source_head_sha: str,
    ) -> "VercelDeployment":
        deployment_id = str(payload.get("id") or "").strip()
        url = str(payload.get("url") or "").strip()
        ready_state = str(payload.get("readyState") or "").strip().upper()
        created_raw = payload.get("createdAt")
        if not isinstance(created_raw, (int, float)):
            raise PreviewError("Vercel deployment lacks immutable creation time.")
        created_at = datetime.fromtimestamp(created_raw / 1000, tz=timezone.utc)
        if deployment_id != expected_id or not deployment_id.startswith("dpl_"):
            raise PreviewError("Vercel deployment immutable ID mismatch.")
        if str(payload.get("projectId") or "") != expected_project_id:
            raise PreviewError("Vercel deployment project attestation failed.")
        if str(payload.get("target") or "").lower() != "preview":
            raise PreviewError("Vercel deployment target is not Preview.")
        if not url or any(character.isspace() for character in url):
            raise PreviewError("Vercel deployment response lacks a valid URL.")
        if ready_state not in {
            "BLOCKED",
            "BUILDING",
            "CANCELED",
            "ERROR",
            "INITIALIZING",
            "QUEUED",
            "READY",
        }:
            raise PreviewError("Vercel deployment response has an unknown state.")
        expected = {
            "githubCommitOrg": validate_github_repo_part(
                git_owner, label="GitHub owner"
            ),
            "githubCommitRepo": validate_github_repo_part(
                git_repo, label="GitHub repository"
            ),
            "githubCommitRef": validate_git_branch(git_branch),
            "githubCommitSha": validate_git_sha(
                source_head_sha, label="Approved deployment SHA"
            ),
        }
        meta = payload.get("meta")
        if not isinstance(meta, Mapping) or any(
            str(meta.get(key) or "") != value for key, value in expected.items()
        ):
            raise PreviewError("Vercel deployment Git metadata attestation failed.")
        git_source = payload.get("gitSource")
        if not isinstance(git_source, Mapping) or any(
            (
                str(git_source.get(key) or "")
                != value
            )
            for key, value in {
                "type": "github",
                "ref": expected["githubCommitRef"],
                "sha": expected["githubCommitSha"],
            }.items()
        ):
            raise PreviewError("Vercel deployment Git source attestation failed.")
        return cls(
            id=deployment_id,
            url=url,
            ready_state=ready_state,
            source_head_sha=validate_git_sha(
                expected["githubCommitSha"], label="Approved deployment SHA"
            ),
            created_at=created_at,
        )


@dataclass(frozen=True)
class AuthorizedPreviewDeployment:
    branch: BranchRecord
    deployment: VercelDeployment


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
        if str(row.get("gitBranch") or "") != git_branch:
            continue
        if _env_targets(row) != {"preview"}:
            raise PreviewError(
                "Refusing Vercel variable mutation: expected an exact "
                "branch-scoped Preview target."
            )
        if str(row.get("key") or "") not in PREVIEW_ALLOWED_ENV_KEYS:
            raise PreviewError(
                "Refusing Vercel variable mutation: exact Preview branch has "
                "an unexpected variable."
            )
        matches.append(row)
    return matches


PreviewEnvSnapshot = tuple[tuple[str, str, str, tuple[str, ...], str], ...]


def preview_env_snapshot(rows: Sequence[Mapping[str, Any]]) -> PreviewEnvSnapshot:
    """Capture immutable env IDs plus non-secret lifecycle identity values."""
    snapshot: list[tuple[str, str, str, tuple[str, ...], str]] = []
    for row in rows:
        env_id = str(row.get("id") or "").strip()
        key = str(row.get("key") or "").strip()
        git_branch = str(row.get("gitBranch") or "").strip()
        if not env_id or key not in PREVIEW_ALLOWED_ENV_KEYS or not git_branch:
            raise PreviewError("Vercel Preview environment snapshot lacks immutable identity.")
        value = (
            "<public-key-value-omitted>"
            if key == "NEXT_PUBLIC_SUPABASE_ANON_KEY"
            else str(row.get("value") or "")
        )
        snapshot.append(
            (env_id, key, git_branch, tuple(sorted(_env_targets(row))), value)
        )
    return tuple(sorted(snapshot))


def attest_preview_envs_for_branch(
    rows: Sequence[Mapping[str, Any]],
    *,
    parent_ref: str,
    pr_number: int,
    git_branch: str,
    branch: BranchRecord,
) -> PreviewEnvSnapshot:
    """Bind stale-sweep Vercel state to the selected immutable Supabase branch."""
    if not rows:
        return ()
    by_key: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_key.setdefault(str(row.get("key") or ""), []).append(row)
    if frozenset(by_key) not in {
        frozenset(PREVIEW_STATIC_ENV_KEYS),
        frozenset(PREVIEW_ALLOWED_ENV_KEYS),
    } or any(len(values) != 1 for values in by_key.values()):
        raise PreviewError("Vercel Preview environment set is not exact for stale cleanup.")
    if branch.created_at is None:
        raise PreviewError("Selected Supabase Preview lacks immutable creation time.")
    expected = {
        PREVIEW_PR_ENV_KEY: str(pr_number),
        "RICHMOND_PREVIEW_GIT_BRANCH": git_branch,
        "RICHMOND_PREVIEW_SUPABASE_REF": branch.project_ref,
        PREVIEW_PARENT_REF_ENV_KEY: parent_ref,
        "NEXT_PUBLIC_SUPABASE_URL": f"https://{branch.project_ref}.supabase.co",
    }
    for key, value in expected.items():
        if str(by_key[key][0].get("value") or "") != value:
            raise PreviewError(
                f"Vercel stale-cleanup identity no longer matches selected branch: {key}"
            )
    observed_created_at = parse_api_timestamp(
        str(by_key[PREVIEW_CREATED_AT_ENV_KEY][0].get("value") or "")
    )
    if observed_created_at != branch.created_at:
        raise PreviewError(
            "Vercel stale-cleanup creation marker no longer matches selected branch."
        )
    validate_git_sha(
        str(by_key["RICHMOND_PREVIEW_SOURCE_HEAD_SHA"][0].get("value") or ""),
        label="Vercel Preview source SHA",
    )
    return preview_env_snapshot(rows)


def _expected_preview_env_values(
    *,
    pr_number: int,
    git_branch: str,
    branch: BranchRecord,
    public_key: str,
    source_head_sha: str,
) -> dict[str, str]:
    if pr_number <= 0:
        raise PreviewError("Preview PR number must be positive.")
    if branch.created_at is None:
        raise PreviewError("Preview branch lacks creation time for lifecycle state.")
    return {
        "NEXT_PUBLIC_SUPABASE_URL": f"https://{branch.project_ref}.supabase.co",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": public_key,
        "RICHMOND_PREVIEW_GIT_BRANCH": git_branch,
        "RICHMOND_PREVIEW_SUPABASE_REF": branch.project_ref,
        "RICHMOND_PREVIEW_SOURCE_HEAD_SHA": validate_git_sha(
            source_head_sha, label="Source head SHA"
        ),
        PREVIEW_PR_ENV_KEY: str(pr_number),
        PREVIEW_CREATED_AT_ENV_KEY: branch.created_at.isoformat(),
        PREVIEW_PARENT_REF_ENV_KEY: branch.parent_project_ref,
    }


def sync_vercel_preview(
    client: VercelClient,
    *,
    pr_number: int,
    git_branch: str,
    branch: BranchRecord,
    public_key: str,
    source_head_sha: str,
) -> None:
    expected = _expected_preview_env_values(
        pr_number=pr_number,
        git_branch=git_branch,
        branch=branch,
        public_key=public_key,
        source_head_sha=source_head_sha,
    )
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
    bad_counts = [
        key for key in PREVIEW_STATIC_ENV_KEYS if len(by_key.get(key, [])) != 1
    ]
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


def verify_retained_preview(
    supabase: SupabaseManagementClient,
    vercel: VercelClient,
    *,
    parent_ref: str,
    pr_number: int,
    git_branch: str,
    source_head_sha: str,
    max_age_seconds: float = MAX_PREVIEW_LIFETIME_SECONDS,
    now: datetime | None = None,
) -> BranchRecord:
    """Read-only proof that the one retained Preview still belongs to H0."""
    parent_ref = validate_project_ref(parent_ref, label="Parent project ref")
    if parent_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError("Refusing verification for an unknown production parent.")
    git_branch = validate_git_branch(git_branch)
    source_head_sha = validate_git_sha(source_head_sha, label="Source head SHA")
    if max_age_seconds <= 0 or max_age_seconds > MAX_PREVIEW_LIFETIME_SECONDS:
        raise PreviewError("Retained Preview age limit must be within two hours.")
    name = preview_branch_name(pr_number)
    branch = find_branch(supabase, parent_ref, name)
    if branch is None:
        raise PreviewError(f"Retained Preview branch {name} was not found.")
    branch.assert_safe_preview(
        parent_ref=parent_ref, expected_name=name, git_branch=git_branch
    )
    branch = _read_exact_branch_identity(supabase, parent_ref, branch)
    branch.assert_safe_preview(
        parent_ref=parent_ref, expected_name=name, git_branch=git_branch
    )
    branch.assert_preview_adoption_boundaries()
    controller_inventory = controller_preview_branches(supabase, parent_ref)
    if (
        len(controller_inventory) != 1
        or controller_inventory[0].id != branch.id
        or controller_inventory[0].project_ref != branch.project_ref
    ):
        raise PreviewError(
            "Retained Preview is not the sole exact controller-owned Supabase branch."
        )
    if branch.created_at is None:
        raise PreviewError("Retained Preview branch has no immutable creation time.")
    if branch.preview_project_status != "ACTIVE_HEALTHY":
        raise PreviewError(
            "Retained Preview service is not ACTIVE_HEALTHY; cleanup comes first."
        )
    observed_now = now or datetime.now(timezone.utc)
    if observed_now.tzinfo is None:
        raise PreviewError("Retained Preview verification time must include UTC offset.")
    age_seconds = (observed_now - branch.created_at).total_seconds()
    if age_seconds < 0:
        raise PreviewError("Retained Preview branch creation time is in the future.")
    if age_seconds >= max_age_seconds:
        raise PreviewError("Retained Preview branch exceeds the two-hour cost ceiling.")

    public_key = choose_public_api_key(supabase.api_keys(branch.project_ref))
    expected = _expected_preview_env_values(
        pr_number=pr_number,
        git_branch=git_branch,
        branch=branch,
        public_key=public_key,
        source_head_sha=source_head_sha,
    )
    exact_rows: list[Mapping[str, Any]] = []
    for row in vercel.list_envs(git_branch):
        if str(row.get("gitBranch") or "") != git_branch:
            continue
        if _env_targets(row) != {"preview"}:
            raise PreviewError(
                "Retained Vercel identity is not exact branch-scoped Preview state."
            )
        key = str(row.get("key") or "")
        if key not in PREVIEW_ALLOWED_ENV_KEYS:
            raise PreviewError("Retained Vercel branch has an unexpected variable.")
        exact_rows.append(row)
    by_key: dict[str, list[Mapping[str, Any]]] = {}
    for row in exact_rows:
        by_key.setdefault(str(row.get("key") or ""), []).append(row)
    if not set(by_key).issubset(set(PREVIEW_ALLOWED_ENV_KEYS)) or any(
        len(by_key[key]) != 1 for key in PREVIEW_STATIC_ENV_KEYS
    ) or any(key not in by_key for key in PREVIEW_STATIC_ENV_KEYS) or len(
        by_key.get(PREVIEW_DEPLOYMENT_ENV_KEY, [])
    ) > 1:
        raise PreviewError("Retained Vercel branch variable set is not exact.")
    for key, value in expected.items():
        if str(by_key[key][0].get("value") or "") != value:
            raise PreviewError(f"Retained Vercel branch identity mismatch: {key}")
    return branch


def authorize_preview_deployment(
    supabase: SupabaseManagementClient,
    vercel: VercelClient,
    *,
    parent_ref: str,
    pr_number: int,
    git_branch: str,
    source_head_sha: str,
    approved_head_sha: str,
    git_owner: str,
    git_repo: str,
    verified_type_only_rebind: bool,
    max_age_seconds: float = MAX_PREVIEW_LIFETIME_SECONDS,
    timeout_seconds: float = 600.0,
    interval_seconds: float = 5.0,
    now: datetime | None = None,
) -> AuthorizedPreviewDeployment:
    """Bind and request one trusted exact-SHA Preview deployment.

    H0 is already bound during bootstrap. H1 may replace that SHA marker only
    after the trusted workflow has proven it is the permitted direct-child,
    type-only update and its generated types match the retained schema.
    """
    source_head_sha = validate_git_sha(source_head_sha, label="Source head SHA")
    approved_head_sha = validate_git_sha(
        approved_head_sha, label="Approved deployment SHA"
    )
    if approved_head_sha != source_head_sha and not verified_type_only_rebind:
        raise PreviewError(
            "A different deployment SHA requires the trusted verified-type-only rebind."
        )
    branch = verify_retained_preview(
        supabase,
        vercel,
        parent_ref=parent_ref,
        pr_number=pr_number,
        git_branch=git_branch,
        source_head_sha=source_head_sha,
        max_age_seconds=max_age_seconds,
        now=now,
    )
    if approved_head_sha != source_head_sha:
        public_key = choose_public_api_key(supabase.api_keys(branch.project_ref))
        sync_vercel_preview(
            vercel,
            pr_number=pr_number,
            git_branch=git_branch,
            branch=branch,
            public_key=public_key,
            source_head_sha=approved_head_sha,
        )
        branch = verify_retained_preview(
            supabase,
            vercel,
            parent_ref=parent_ref,
            pr_number=pr_number,
            git_branch=git_branch,
            source_head_sha=approved_head_sha,
            max_age_seconds=max_age_seconds,
            now=now,
        )

    def persist_deployment_id(deployment_id: str) -> None:
        vercel.create_preview_env(
            key=PREVIEW_DEPLOYMENT_ENV_KEY,
            value=deployment_id,
            git_branch=git_branch,
        )
        state_rows = [
            row
            for row in branch_preview_envs(vercel, git_branch)
            if str(row.get("key") or "") == PREVIEW_DEPLOYMENT_ENV_KEY
        ]
        if (
            len(state_rows) != 1
            or str(state_rows[0].get("value") or "") != deployment_id
        ):
            raise PreviewError("Vercel deployment ID persistence verification failed.")

    deployment = vercel.create_preview_deployment(
        git_owner=git_owner,
        git_repo=git_repo,
        git_branch=git_branch,
        source_head_sha=approved_head_sha,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        on_created=persist_deployment_id,
    )
    return AuthorizedPreviewDeployment(branch=branch, deployment=deployment)


def cleanup_vercel_preview(
    client: VercelClient,
    *,
    git_branch: str,
    git_owner: str = GITHUB_OWNER,
    git_repo: str = GITHUB_REPO,
    expected_snapshot: PreviewEnvSnapshot | None = None,
) -> int:
    rows = branch_preview_envs(client, git_branch)
    if (
        expected_snapshot is not None
        and preview_env_snapshot(rows) != expected_snapshot
    ):
        raise PreviewSelectionChanged(
            "Vercel Preview environment state changed after stale inventory; "
            "refusing to mutate replacement state."
        )
    by_key: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_key.setdefault(str(row.get("key") or ""), []).append(row)
    deployment_rows = by_key.get(PREVIEW_DEPLOYMENT_ENV_KEY, [])
    if len(deployment_rows) > 1:
        raise PreviewError("Refusing cleanup with duplicate deployment ID state.")
    if deployment_rows:
        source_rows = by_key.get("RICHMOND_PREVIEW_SOURCE_HEAD_SHA", [])
        if len(source_rows) != 1:
            raise PreviewError("Refusing deployment cleanup without exact source SHA state.")
        client.retire_preview_deployment(
            str(deployment_rows[0].get("value") or ""),
            git_owner=git_owner,
            git_repo=git_repo,
            git_branch=git_branch,
            source_head_sha=str(source_rows[0].get("value") or ""),
        )
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
    pr_number: int,
    git_branch: str,
    branch: BranchRecord,
    timeout_seconds: float,
    interval_seconds: float,
) -> None:
    parent_ref = validate_project_ref(parent_ref, label="Parent project ref")
    if parent_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError("Refusing branch deletion for an unknown production parent.")
    git_branch = validate_git_branch(git_branch)
    branch.assert_safe_preview(
        parent_ref=parent_ref,
        expected_name=preview_branch_name(pr_number),
        git_branch=git_branch,
    )
    live_branch = _read_exact_branch_identity(client, parent_ref, branch)
    live_branch.assert_safe_preview(
        parent_ref=parent_ref,
        expected_name=preview_branch_name(pr_number),
        git_branch=git_branch,
    )
    try:
        client.delete_branch(live_branch.project_ref)
    except ApiError as exc:
        if not _mutation_may_have_succeeded(exc):
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
    baseline: PreviewBaseline,
    migrations: Sequence[Migration],
    trusted_migrations: Sequence[Migration],
    source_head_sha: str,
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
    if replace:
        raise PreviewError(
            "Supabase Preview replacement is disabled. Cleanup must complete "
            "before a separately approved new bootstrap."
        )
    git_branch = validate_git_branch(git_branch)
    source_head_sha = validate_git_sha(source_head_sha, label="Source head SHA")
    validate_baseline_migrations(baseline, migrations, trusted_migrations)
    # This read-only production gate runs before replacing a branch or Vercel
    # target. Only the two manifest-declared historical name exceptions pass.
    production_ledger = verify_production_ledger(
        supabase,
        parent_ref,
        baseline,
        trusted_migrations,
        migrations,
    )
    name = preview_branch_name(pr_number)
    initial_controller_branches = controller_preview_branches(supabase, parent_ref)
    existing_matches = [
        branch for branch in initial_controller_branches if branch.name == name
    ]
    if len(existing_matches) > 1:
        raise PreviewError(f"Supabase returned duplicate branches named {name!r}.")
    other_previews = [
        branch for branch in initial_controller_branches if branch.name != name
    ]
    if other_previews:
        raise PreviewError(
            "Another controller-owned Supabase Preview branch already exists; "
            "the approved cost boundary permits one branch total."
        )
    existing = existing_matches[0] if existing_matches else None
    if existing is not None:
        existing.assert_safe_preview(
            parent_ref=parent_ref, expected_name=name, git_branch=git_branch
        )
        raise PreviewError(
            f"Preview branch {name} already exists. Cleanup comes first; "
            "this controller never replaces a branch."
        )

    created: BranchRecord | None = None
    try:
        create_started_at = datetime.now(timezone.utc) - timedelta(
            seconds=CREATE_REQUEST_CLOCK_SKEW_SECONDS
        )
        create_problem: Exception | None = None
        explicit_cost_error: PreviewCostBoundaryError | None = None
        explicit_data_error: PreviewDataBoundaryError | None = None
        candidate: BranchRecord | None = None
        try:
            candidate = supabase.create_branch(
                parent_ref, name=name, git_branch=git_branch
            )
        except ApiError as exc:
            if not _mutation_may_have_succeeded(exc):
                raise
            create_problem = exc
        except PreviewCostBoundaryError as exc:
            # The POST may have committed at the explicitly wrong size. Resolve
            # only for exact containment; never accept a list response that
            # happens to omit the size field.
            create_problem = exc
            explicit_cost_error = exc
        except PreviewDataBoundaryError as exc:
            # A later list response that omits with_data cannot erase an
            # explicit data-bearing create response. Reconcile only so the
            # exact fresh branch can be contained.
            create_problem = exc
            explicit_data_error = exc
        except PreviewError as exc:
            # A successful response can still omit or corrupt immutable fields.
            # The POST may have committed, so reconcile instead of replaying it.
            create_problem = exc

        if candidate is not None:
            try:
                candidate.assert_safe_preview(
                    parent_ref=parent_ref,
                    expected_name=name,
                    git_branch=git_branch,
                )
            except PreviewError as exc:
                # Never trust an unsafe response body as a deletion target. A
                # fresh exact list record is the only acceptable witness.
                create_problem = exc
                candidate = None

        if candidate is None:
            # Reconcile once by exact immutable identity and creation time;
            # never issue a second POST.
            candidate = reconcile_created_supabase_branch(
                supabase,
                parent_ref,
                name,
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
            )
            if candidate is None:
                raise PreviewError(
                    "Supabase branch create has ambiguous or malformed state and "
                    "no exact branch was observable; no retry was attempted."
                ) from create_problem
            candidate.assert_safe_preview(
                parent_ref=parent_ref, expected_name=name, git_branch=git_branch
            )
        # An unsafe response is never promoted to a rollback target. This
        # assignment occurs only after exact identity and freshness are proven.
        candidate.assert_safe_preview(
            parent_ref=parent_ref, expected_name=name, git_branch=git_branch
        )
        if candidate.created_at is None:
            raise PreviewError("Created Supabase branch lacks immutable creation time.")
        if candidate.created_at < create_started_at:
            raise PreviewError(
                "Created Supabase branch predates this exact create request."
            )
        if candidate.created_at > datetime.now(timezone.utc) + timedelta(
            seconds=MAX_CONTROL_PLANE_FUTURE_SKEW_SECONDS
        ):
            raise PreviewError(
                "Created Supabase branch creation time is implausibly in the future."
            )
        created = candidate
        if explicit_cost_error is not None:
            raise PreviewCostBoundaryError(
                "Supabase explicitly reported a non-Micro branch; the exact "
                "fresh branch is being removed."
            ) from explicit_cost_error
        if explicit_data_error is not None:
            raise PreviewDataBoundaryError(
                "Supabase explicitly reported a data-bearing branch; the exact "
                "fresh branch is being removed."
            ) from explicit_data_error
        try:
            created.assert_micro_compute()
        except PreviewCostBoundaryError as observed_cost_error:
            raise PreviewCostBoundaryError(
                "Supabase explicitly reported a non-Micro branch; the exact "
                "fresh branch is being removed."
            ) from observed_cost_error
        try:
            created.assert_data_less()
        except PreviewDataBoundaryError as observed_data_error:
            raise PreviewDataBoundaryError(
                "Supabase explicitly reported a data-bearing branch; the exact "
                "fresh branch is being removed."
            ) from observed_data_error
        observed_created = _read_exact_branch_identity(
            supabase, parent_ref, created
        )
        observed_created.assert_safe_preview(
            parent_ref=parent_ref, expected_name=name, git_branch=git_branch
        )
        created = observed_created
        try:
            created.assert_micro_compute()
        except PreviewCostBoundaryError as observed_cost_error:
            raise PreviewCostBoundaryError(
                "Supabase explicitly reported a non-Micro branch; the exact "
                "fresh branch is being removed."
            ) from observed_cost_error
        try:
            created.assert_data_less()
        except PreviewDataBoundaryError as observed_data_error:
            raise PreviewDataBoundaryError(
                "Supabase explicitly reported a data-bearing branch; the exact "
                "fresh branch is being removed."
            ) from observed_data_error
        observed_controller_branches = controller_preview_branches(
            supabase, parent_ref
        )
        exact_created = [
            branch
            for branch in observed_controller_branches
            if branch.id == created.id and branch.project_ref == created.project_ref
        ]
        if len(observed_controller_branches) != 1 or len(exact_created) != 1:
            raise PreviewError(
                "Post-create inventory did not prove one exact controller-owned "
                "Supabase Preview branch; the new immutable branch will be removed."
            )
        created = exact_created[0]
        created.assert_preview_adoption_boundaries()
        wait_for_database(
            supabase,
            created,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )

        apply_preview_baseline(supabase, created, baseline)
        applied_migrations = 0
        production_versions = set(production_ledger.applied_versions)
        while True:
            # Supabase's own branch clone may finish recording trusted live
            # migrations after the baseline restore. Re-plan before every
            # write so inherited live rows are never replayed from a stale
            # suffix snapshot.
            pending = migration_plan(migrations, read_ledger(supabase, created))
            if not pending:
                break
            migration = pending[0]
            applied = apply_migration(
                supabase,
                created,
                migration,
                allow_trusted_inheritance=(
                    migration.version in production_versions
                ),
            )
            if applied:
                applied_migrations += 1

        verify_post_migration_security(supabase, created, baseline)
        created = _read_exact_branch_identity(
            supabase, parent_ref, created
        )
        created.assert_safe_preview(
            parent_ref=parent_ref,
            expected_name=name,
            git_branch=git_branch,
        )
        created.assert_preview_adoption_boundaries()
        # A Supabase soft delete immediately deactivates the Preview during its
        # grace period. Keep the branch active and require the authoritative
        # service status on the same immutable UUID/ref before API keys,
        # Vercel state, or the workflow's type generator can touch it. The
        # independent 90- and 110-minute hard-delete jobs bound normal lifetime.
        created = wait_for_active_preview(
            supabase,
            parent_ref=parent_ref,
            pr_number=pr_number,
            git_branch=git_branch,
            branch=created,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )
        public_key = choose_public_api_key(supabase.api_keys(created.project_ref))
        sync_vercel_preview(
            vercel,
            pr_number=pr_number,
            git_branch=git_branch,
            branch=created,
            public_key=public_key,
            source_head_sha=source_head_sha,
        )
        return BootstrapResult(created, applied_migrations)
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
                    pr_number=pr_number,
                    git_branch=git_branch,
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
    expected_branch: BranchRecord | None = None,
    timeout_seconds: float = 600.0,
    interval_seconds: float = 5.0,
) -> tuple[bool, int]:
    parent_ref = validate_project_ref(parent_ref, label="Parent project ref")
    if parent_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError("Refusing cleanup for an unknown production parent ref.")
    git_branch = validate_git_branch(git_branch)
    name = preview_branch_name(pr_number)
    if expected_branch is not None:
        expected_branch.assert_safe_preview(
            parent_ref=parent_ref, expected_name=name, git_branch=git_branch
        )
        # Re-attest the sweep-selected UUID/ref before any Vercel or Supabase
        # mutation. A missing/replaced branch is never resolved by mutable name.
        branch = _read_stale_sweep_branch_identity(
            supabase, parent_ref, expected_branch
        )
    else:
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
            expected_snapshot: PreviewEnvSnapshot | None = None
            if expected_branch is not None and branch is not None:
                initial_rows = branch_preview_envs(vercel, git_branch)
                expected_snapshot = attest_preview_envs_for_branch(
                    initial_rows,
                    parent_ref=parent_ref,
                    pr_number=pr_number,
                    git_branch=git_branch,
                    branch=branch,
                )
            deleted_envs = cleanup_vercel_preview(
                vercel,
                git_branch=git_branch,
                expected_snapshot=expected_snapshot,
            )
        except Exception as exc:
            vercel_error = exc

    if branch is not None:
        delete_supabase_preview(
            supabase,
            parent_ref=parent_ref,
            pr_number=pr_number,
            git_branch=git_branch,
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


def sweep_expired_previews(
    supabase: SupabaseManagementClient,
    vercel: VercelClient | None,
    *,
    parent_ref: str,
    max_age_seconds: float = PREVIEW_SWEEP_AGE_SECONDS,
    max_branches: int = MAX_SWEEP_BRANCHES,
    now: datetime | None = None,
    timeout_seconds: float = 600.0,
    interval_seconds: float = 5.0,
) -> int:
    """Bounded trusted backstop for stale, exact Richmond Preview branches."""
    parent_ref = validate_project_ref(parent_ref, label="Parent project ref")
    if parent_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError("Refusing sweep for an unknown production parent ref.")
    if max_age_seconds < 60 * 60 or max_age_seconds > MAX_PREVIEW_LIFETIME_SECONDS:
        raise PreviewError("Preview sweep age must be between one and two hours.")
    if max_branches < 1 or max_branches > MAX_SWEEP_BRANCHES:
        raise PreviewError("Preview sweep batch exceeds the bounded safety limit.")
    observed_now = now or datetime.now(timezone.utc)
    if observed_now.tzinfo is None:
        raise PreviewError("Preview sweep time must include UTC offset.")
    candidates: list[tuple[datetime, int, BranchRecord]] = []
    for branch in supabase.list_branches(parent_ref):
        match = re.fullmatch(r"pr-([1-9][0-9]*)-preview", branch.name)
        if match is None or branch.created_at is None:
            continue
        pr_number = int(match.group(1))
        try:
            branch.assert_safe_preview(
                parent_ref=parent_ref,
                expected_name=preview_branch_name(pr_number),
                git_branch=validate_git_branch(branch.git_branch),
            )
        except PreviewError:
            continue
        age_seconds = (observed_now - branch.created_at).total_seconds()
        if age_seconds >= max_age_seconds:
            candidates.append((branch.created_at, pr_number, branch))
    candidates.sort(key=lambda item: item[0])
    failures: list[str] = []
    cleaned = 0
    attempted_scope_count = 0
    attempted_git_branches: set[str] = set()
    for _, pr_number, branch in candidates[:max_branches]:
        attempted_scope_count += 1
        attempted_git_branches.add(branch.git_branch)
        try:
            cleanup_preview(
                supabase,
                vercel,
                parent_ref=parent_ref,
                pr_number=pr_number,
                git_branch=branch.git_branch,
                expected_branch=branch,
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
            )
            cleaned += 1
        except PreviewSelectionChanged:
            # The selected immutable branch was removed/replaced after the
            # inventory read. Mutate neither replacement; the independent,
            # freshly inventoried Vercel marker sweep below decides its state.
            continue
        except Exception as exc:
            failures.append(f"{branch.name}: {exc}")

    # A lifecycle cleanup can remove Supabase before this 90-minute sweep runs.
    # Sweep the independently persisted Vercel lifecycle state as well, while
    # requiring the complete exact controller-owned marker set.
    if vercel is not None and attempted_scope_count < max_branches:
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for row in vercel.list_all_preview_envs():
            git_branch = str(row.get("gitBranch") or "")
            if not git_branch or _env_targets(row) != {"preview"}:
                continue
            grouped.setdefault(git_branch, []).append(row)
        stale_vercel: list[tuple[datetime, str, PreviewEnvSnapshot]] = []
        for git_branch, rows in grouped.items():
            if git_branch in attempted_git_branches:
                continue
            try:
                validate_git_branch(git_branch)
                by_key: dict[str, list[Mapping[str, Any]]] = {}
                for row in rows:
                    by_key.setdefault(str(row.get("key") or ""), []).append(row)
                if frozenset(by_key) not in {
                    frozenset(PREVIEW_STATIC_ENV_KEYS),
                    frozenset(PREVIEW_ALLOWED_ENV_KEYS),
                } or any(len(values) != 1 for values in by_key.values()):
                    continue
                pr_number = int(str(by_key[PREVIEW_PR_ENV_KEY][0].get("value") or ""))
                if pr_number <= 0:
                    continue
                preview_branch_name(pr_number)
                if str(by_key["RICHMOND_PREVIEW_GIT_BRANCH"][0].get("value") or "") != git_branch:
                    continue
                branch_ref = validate_project_ref(
                    str(by_key["RICHMOND_PREVIEW_SUPABASE_REF"][0].get("value") or ""),
                    label="Vercel Preview Supabase ref",
                )
                if branch_ref == parent_ref:
                    continue
                if str(by_key[PREVIEW_PARENT_REF_ENV_KEY][0].get("value") or "") != parent_ref:
                    continue
                expected_url = f"https://{branch_ref}.supabase.co"
                if str(by_key["NEXT_PUBLIC_SUPABASE_URL"][0].get("value") or "") != expected_url:
                    continue
                validate_git_sha(
                    str(by_key["RICHMOND_PREVIEW_SOURCE_HEAD_SHA"][0].get("value") or ""),
                    label="Vercel Preview source SHA",
                )
                created_at = parse_api_timestamp(
                    str(by_key[PREVIEW_CREATED_AT_ENV_KEY][0].get("value") or "")
                )
            except (PreviewError, TypeError, ValueError):
                continue
            age_seconds = (observed_now - created_at).total_seconds()
            if age_seconds >= max_age_seconds:
                try:
                    snapshot = preview_env_snapshot(rows)
                except PreviewError:
                    continue
                stale_vercel.append((created_at, git_branch, snapshot))
        stale_vercel.sort(key=lambda item: (item[0], item[1]))
        for _, git_branch, snapshot in stale_vercel[
            : max_branches - attempted_scope_count
        ]:
            attempted_scope_count += 1
            attempted_git_branches.add(git_branch)
            try:
                cleanup_vercel_preview(
                    vercel,
                    git_branch=git_branch,
                    expected_snapshot=snapshot,
                )
                cleaned += 1
            except PreviewSelectionChanged:
                # Immutable env IDs/markers changed after inventory. Never
                # delete the replacement state by mutable Git branch.
                continue
            except Exception as exc:
                failures.append(f"Vercel {git_branch}: {exc}")
    if failures:
        raise PreviewError(
            "Stale Preview sweep needs follow-up. ACTION: do not rerun or create "
            "a branch; inspect and contain only the exact immutable failures="
            + "; ".join(failures)
        )
    return cleaned


def snapshot_watchdog_preview(
    supabase: SupabaseManagementClient,
    *,
    parent_ref: str,
    pr_number: int,
    git_branch: str,
    bootstrap_started_at: datetime,
    bootstrap_completed_at: datetime,
) -> BranchRecord | None:
    """Snapshot the sole branch provably created during one bootstrap run.

    The workflow-run title identifies the PR, while these trusted GitHub API
    timestamps bind the branch creation time to that exact completed run. If
    the old branch is already gone, a later replacement is not adopted.
    """
    parent_ref = validate_project_ref(parent_ref, label="Parent project ref")
    if parent_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError("Refusing watchdog snapshot for an unknown parent ref.")
    git_branch = validate_git_branch(git_branch)
    if bootstrap_started_at.tzinfo is None or bootstrap_completed_at.tzinfo is None:
        raise PreviewError("Watchdog run timestamps must include UTC offsets.")
    if bootstrap_completed_at < bootstrap_started_at:
        raise PreviewError("Watchdog bootstrap completion predates its start.")

    name = preview_branch_name(pr_number)
    inventory = controller_preview_branches(supabase, parent_ref)
    named = [branch for branch in inventory if branch.name == name]
    if not named:
        return None
    if len(inventory) != 1 or len(named) != 1:
        raise PreviewError(
            "Watchdog could not prove one sole exact controller-owned branch."
        )
    branch = _read_exact_branch_identity(supabase, parent_ref, named[0])
    branch.assert_safe_preview(
        parent_ref=parent_ref, expected_name=name, git_branch=git_branch
    )
    branch.assert_preview_adoption_boundaries()
    if branch.created_at is None:
        raise PreviewError("Watchdog branch lacks immutable creation time.")
    if not (
        bootstrap_started_at <= branch.created_at <= bootstrap_completed_at
    ):
        raise PreviewError(
            "Watchdog branch creation time is outside the exact bootstrap run; "
            "refusing to adopt a possible replacement."
        )
    final_inventory = controller_preview_branches(supabase, parent_ref)
    if (
        len(final_inventory) != 1
        or final_inventory[0].id != branch.id
        or final_inventory[0].project_ref != branch.project_ref
    ):
        raise PreviewError(
            "Watchdog branch identity changed during its immutable snapshot."
        )
    return branch


def cleanup_watchdog_preview(
    supabase: SupabaseManagementClient,
    vercel: VercelClient,
    *,
    parent_ref: str,
    pr_number: int,
    git_branch: str,
    snapshot_branch_id: str,
    snapshot_project_ref: str,
    snapshot_created_at: datetime,
    now: datetime | None = None,
    timeout_seconds: float = 600.0,
    interval_seconds: float = 5.0,
) -> tuple[bool, int]:
    """Hard-delete only the immutable branch captured by the watchdog.

    Missing or replaced state is a successful no-op. A same-name replacement
    is never resolved by mutable PR/Git identity.
    """
    parent_ref = validate_project_ref(parent_ref, label="Parent project ref")
    if parent_ref != PRODUCTION_PROJECT_REF:
        raise PreviewError("Refusing watchdog cleanup for an unknown parent ref.")
    git_branch = validate_git_branch(git_branch)
    try:
        UUID(snapshot_branch_id)
    except (ValueError, AttributeError) as exc:
        raise PreviewError("Watchdog snapshot lacks a valid immutable UUID.") from exc
    snapshot_project_ref = validate_project_ref(
        snapshot_project_ref, label="Watchdog branch project ref"
    )
    if snapshot_project_ref == parent_ref:
        raise PreviewError("Watchdog snapshot must not target production.")
    if snapshot_created_at.tzinfo is None:
        raise PreviewError("Watchdog creation timestamp must include a UTC offset.")

    observed_now = now or datetime.now(timezone.utc)
    if observed_now.tzinfo is None:
        raise PreviewError("Watchdog cleanup time must include a UTC offset.")
    deadline = snapshot_created_at + timedelta(
        seconds=PREVIEW_WATCHDOG_AGE_SECONDS
    )
    if observed_now < deadline:
        raise PreviewError(
            "Watchdog cleanup was invoked before the 110-minute deadline."
        )

    exact = [
        branch
        for branch in supabase.list_branches(parent_ref)
        if branch.id == snapshot_branch_id
        and branch.project_ref == snapshot_project_ref
    ]
    if not exact:
        return False, 0
    if len(exact) != 1:
        raise PreviewError("Watchdog immutable branch identity is not unique.")
    branch = exact[0]
    branch.assert_safe_preview(
        parent_ref=parent_ref,
        expected_name=preview_branch_name(pr_number),
        git_branch=git_branch,
    )
    branch.assert_preview_adoption_boundaries()
    if branch.created_at != snapshot_created_at:
        raise PreviewError(
            "Watchdog branch creation time changed; refusing replacement cleanup."
        )
    try:
        return cleanup_preview(
            supabase,
            vercel,
            parent_ref=parent_ref,
            pr_number=pr_number,
            git_branch=git_branch,
            expected_branch=branch,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )
    except PreviewSelectionChanged:
        return False, 0


def generate_supabase_types_with_retry(
    project_ref: str,
    output_path: Path,
    *,
    max_wait_seconds: float = MAX_TYPEGEN_RETRY_SECONDS,
    retry_interval_seconds: float = 5.0,
    runner: Callable[..., Any] = subprocess.run,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Run read-only typegen with one narrowly classified transient retry.

    Only the exact Supabase inactive-project response is retried. Authentication,
    authorization, CLI, and every unrelated error fail immediately.
    """
    project_ref = validate_project_ref(project_ref, label="Typegen project ref")
    if project_ref == PRODUCTION_PROJECT_REF:
        raise PreviewError("Preview typegen must not target production.")
    if max_wait_seconds <= 0 or max_wait_seconds > MAX_TYPEGEN_RETRY_SECONDS:
        raise PreviewError("Typegen retry window must be within 120 seconds.")
    if retry_interval_seconds <= 0 or retry_interval_seconds > 30:
        raise PreviewError(
            "Typegen retry interval must be greater than 0 and at most 30 seconds."
        )
    if output_path.exists() or output_path.is_symlink():
        raise PreviewError("Typegen output path must not already exist.")
    if not output_path.parent.is_dir():
        raise PreviewError("Typegen output directory does not exist.")

    deadline = monotonic() + max_wait_seconds
    attempts = 0
    command = [
        "supabase",
        "gen",
        "types",
        "typescript",
        "--project-id",
        project_ref,
        "--schema",
        "public",
    ]
    environment = os.environ.copy()
    environment["NO_COLOR"] = "1"
    while True:
        attempts += 1
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise PreviewError(
                "Supabase typegen stayed inactive for the bounded retry window."
            )
        try:
            completed = runner(
                command,
                capture_output=True,
                check=False,
                timeout=remaining,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise PreviewError(
                "Supabase typegen exceeded the bounded retry window."
            ) from exc
        except OSError as exc:
            raise PreviewError(f"Unable to execute Supabase typegen: {exc}") from exc

        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8")
        if isinstance(stderr, bytes):
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
        else:
            stderr_text = str(stderr).strip()
        if int(completed.returncode) == 0:
            if len(stdout) > MAX_DATABASE_TYPES_BYTES:
                raise PreviewError("Generated database types exceed the 2 MB gate.")
            with output_path.open("xb") as handle:
                handle.write(stdout)
            return attempts
        if stderr_text != TYPEGEN_ACTIVE_TRANSIENT:
            raise PreviewError(
                "Supabase typegen failed without the exact retryable inactive-project "
                f"response: {_redact(stderr_text)}"
            )
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise PreviewError(
                "Supabase typegen stayed inactive for the bounded retry window."
            )
        sleeper(min(retry_interval_seconds, remaining))


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
        "validate",
        help="Validate the trusted baseline and immutable migration prefix offline.",
    )
    validate.add_argument("--migrations-dir", type=Path, required=True)
    validate.add_argument("--migrations-root", type=Path, required=True)
    validate.add_argument("--baseline-dir", type=Path, required=True)

    schema_state = subparsers.add_parser(
        "schema-state",
        help="Compare inert PR migrations with the trusted production ledger.",
    )
    schema_state.add_argument("--parent-ref", required=True)
    schema_state.add_argument("--migrations-dir", type=Path, required=True)
    schema_state.add_argument("--migrations-root", type=Path, required=True)
    schema_state.add_argument("--baseline-dir", type=Path, required=True)

    for name in ("bootstrap", "cleanup", "verify-retained"):
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
    bootstrap.add_argument("--migrations-root", type=Path, required=True)
    bootstrap.add_argument("--baseline-dir", type=Path, required=True)
    bootstrap.add_argument("--source-head-sha", required=True)
    verify_retained = subparsers.choices["verify-retained"]
    verify_retained.add_argument("--source-head-sha", required=True)
    verify_retained.add_argument(
        "--max-age-seconds",
        type=float,
        default=MAX_PREVIEW_LIFETIME_SECONDS,
    )

    authorize_deployment = subparsers.add_parser(
        "authorize-deployment",
        help="Request one trusted exact-SHA Vercel Preview deployment.",
    )
    authorize_deployment.add_argument("--parent-ref", required=True)
    authorize_deployment.add_argument("--pr-number", type=int, required=True)
    authorize_deployment.add_argument("--git-branch", required=True)
    authorize_deployment.add_argument("--source-head-sha", required=True)
    authorize_deployment.add_argument("--approved-head-sha", required=True)
    authorize_deployment.add_argument("--git-owner", required=True)
    authorize_deployment.add_argument("--git-repo", required=True)
    authorize_deployment.add_argument(
        "--verified-type-only-rebind", action="store_true"
    )
    authorize_deployment.add_argument(
        "--max-age-seconds",
        type=float,
        default=MAX_PREVIEW_LIFETIME_SECONDS,
    )
    authorize_deployment.add_argument("--vercel-project-id")
    authorize_deployment.add_argument("--vercel-org-id")
    authorize_deployment.add_argument("--timeout-seconds", type=float, default=600.0)
    authorize_deployment.add_argument("--interval-seconds", type=float, default=5.0)

    sweep = subparsers.add_parser(
        "sweep-expired",
        help="Delete stale exact-name non-persistent Preview branches.",
    )
    sweep.add_argument("--parent-ref", required=True)
    sweep.add_argument(
        "--max-age-seconds", type=float, default=PREVIEW_SWEEP_AGE_SECONDS
    )
    sweep.add_argument("--max-branches", type=int, default=MAX_SWEEP_BRANCHES)
    sweep.add_argument("--timeout-seconds", type=float, default=600.0)
    sweep.add_argument("--interval-seconds", type=float, default=5.0)
    sweep.add_argument("--vercel-project-id")
    sweep.add_argument("--vercel-org-id")

    watchdog_snapshot = subparsers.add_parser(
        "watchdog-snapshot",
        help="Snapshot one immutable Preview created during an exact bootstrap run.",
    )
    watchdog_snapshot.add_argument("--parent-ref", required=True)
    watchdog_snapshot.add_argument("--pr-number", type=int, required=True)
    watchdog_snapshot.add_argument("--git-branch", required=True)
    watchdog_snapshot.add_argument("--bootstrap-started-at", required=True)
    watchdog_snapshot.add_argument("--bootstrap-completed-at", required=True)

    watchdog_cleanup = subparsers.add_parser(
        "watchdog-cleanup",
        help="Hard-delete only one previously snapshotted immutable Preview.",
    )
    watchdog_cleanup.add_argument("--parent-ref", required=True)
    watchdog_cleanup.add_argument("--pr-number", type=int, required=True)
    watchdog_cleanup.add_argument("--git-branch", required=True)
    watchdog_cleanup.add_argument("--snapshot-branch-id", required=True)
    watchdog_cleanup.add_argument("--snapshot-project-ref", required=True)
    watchdog_cleanup.add_argument("--snapshot-created-at", required=True)
    watchdog_cleanup.add_argument("--timeout-seconds", type=float, default=600.0)
    watchdog_cleanup.add_argument("--interval-seconds", type=float, default=5.0)
    watchdog_cleanup.add_argument("--vercel-project-id")
    watchdog_cleanup.add_argument("--vercel-org-id")

    generate_types = subparsers.add_parser(
        "generate-types",
        help="Run Preview typegen with an exact transient-only bounded retry.",
    )
    generate_types.add_argument("--project-ref", required=True)
    generate_types.add_argument("--output", type=Path, required=True)
    generate_types.add_argument(
        "--max-wait-seconds",
        type=float,
        default=MAX_TYPEGEN_RETRY_SECONDS,
    )
    generate_types.add_argument(
        "--retry-interval-seconds",
        type=float,
        default=5.0,
    )

    verify_type_update = subparsers.add_parser(
        "verify-type-update",
        help="Validate the bounded H0-to-H1 database type-only update offline.",
    )
    verify_type_update.add_argument("--metadata-json", type=Path, required=True)
    verify_type_update.add_argument("--source-root", type=Path, required=True)
    verify_type_update.add_argument("--head-root", type=Path, required=True)
    verify_type_update.add_argument("--source-head-sha", required=True)
    verify_type_update.add_argument("--head-sha", required=True)
    return parser


def _main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    trusted_root = Path.cwd()
    baseline: PreviewBaseline | None = None
    migrations: list[Migration] | None = None
    trusted_migrations: list[Migration] | None = None
    pending: list[Migration] = []
    if args.command in ("validate", "schema-state"):
        baseline = load_preview_baseline(args.baseline_dir, root=trusted_root)
        migrations = load_migrations(
            args.migrations_dir, root=args.migrations_root
        )
        trusted_migrations = load_migrations(
            args.baseline_dir.parent / "migrations", root=trusted_root
        )
        pending = validate_baseline_migrations(
            baseline, migrations, trusted_migrations
        )
        if args.command == "validate":
            print(
                f"Validated trusted baseline at cutoff {baseline.cutoff_version}: "
                f"absorbed={len(baseline.absorbed_migrations)} "
                f"post_cutoff={len(pending)}."
            )
            return 0

    if args.command == "bootstrap":
        baseline = load_preview_baseline(args.baseline_dir, root=trusted_root)
        migrations = load_migrations(
            args.migrations_dir, root=args.migrations_root
        )
        trusted_migrations = load_migrations(
            args.baseline_dir.parent / "migrations", root=trusted_root
        )
        validate_baseline_migrations(baseline, migrations, trusted_migrations)

    if args.command == "verify-type-update":
        metadata_text = _canonical_utf8_text(
            args.metadata_json,
            max_bytes=100_000,
            label="Commit metadata",
        )
        try:
            metadata = json.loads(metadata_text)
        except json.JSONDecodeError as exc:
            raise PreviewError("Commit metadata is not valid JSON.") from exc
        if not isinstance(metadata, Mapping):
            raise PreviewError("Commit metadata must be a JSON object.")
        types_path = verify_type_update_inputs(
            metadata=metadata,
            source_root=args.source_root,
            head_root=args.head_root,
            source_head_sha=args.source_head_sha,
            head_sha=args.head_sha,
        )
        _write_github_output("types_path", str(types_path))
        print(
            "Verified bounded type-only update: "
            f"source={args.source_head_sha} head={args.head_sha}"
        )
        return 0

    if args.command == "generate-types":
        attempts = generate_supabase_types_with_retry(
            args.project_ref,
            args.output,
            max_wait_seconds=args.max_wait_seconds,
            retry_interval_seconds=args.retry_interval_seconds,
        )
        print(f"Preview type generation complete: attempts={attempts}")
        return 0

    supabase_token = _require_env("SUPABASE_ACCESS_TOKEN")
    supabase = SupabaseManagementClient(supabase_token)
    vercel_token = (os.getenv("VERCEL_TOKEN") or "").strip()
    project_id = (
        getattr(args, "vercel_project_id", None)
        or os.getenv("VERCEL_PROJECT_ID")
        or ""
    ).strip()
    team_id = (
        getattr(args, "vercel_org_id", None)
        or os.getenv("VERCEL_ORG_ID")
        or ""
    ).strip()
    vercel = (
        VercelClient(
            vercel_token,
            project_id=project_id,
            team_id=team_id,
        )
        if vercel_token and project_id and team_id
        else None
    )

    if args.command == "watchdog-snapshot":
        branch = snapshot_watchdog_preview(
            supabase,
            parent_ref=args.parent_ref,
            pr_number=args.pr_number,
            git_branch=args.git_branch,
            bootstrap_started_at=parse_api_timestamp(args.bootstrap_started_at),
            bootstrap_completed_at=parse_api_timestamp(
                args.bootstrap_completed_at
            ),
        )
        _write_github_output("present", "true" if branch is not None else "false")
        if branch is None:
            print("Preview watchdog snapshot: branch already absent")
            return 0
        if branch.created_at is None:
            raise PreviewError("Watchdog branch lacks immutable creation time.")
        _write_github_output("branch_id", branch.id)
        _write_github_output("project_ref", branch.project_ref)
        _write_github_output("created_at", branch.created_at.isoformat())
        print(
            "Preview watchdog snapshot captured: "
            f"name={branch.name} ref={branch.project_ref}"
        )
        return 0

    if args.command == "watchdog-cleanup":
        if vercel is None:
            raise PreviewError(
                "Watchdog cleanup requires VERCEL_TOKEN, VERCEL_PROJECT_ID, "
                "and VERCEL_ORG_ID."
            )
        deleted, env_count = cleanup_watchdog_preview(
            supabase,
            vercel,
            parent_ref=args.parent_ref,
            pr_number=args.pr_number,
            git_branch=args.git_branch,
            snapshot_branch_id=args.snapshot_branch_id,
            snapshot_project_ref=args.snapshot_project_ref,
            snapshot_created_at=parse_api_timestamp(args.snapshot_created_at),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.interval_seconds,
        )
        print(
            "Preview watchdog cleanup complete: "
            f"supabase_deleted={str(deleted).lower()} "
            f"vercel_envs_deleted={env_count}"
        )
        return 0

    if args.command == "schema-state":
        assert baseline is not None
        assert migrations is not None
        assert trusted_migrations is not None
        state = verify_production_ledger(
            supabase,
            args.parent_ref,
            baseline,
            trusted_migrations,
            migrations,
        )
        applied_versions = set(state.applied_versions)
        production_pending = [
            migration
            for migration in pending
            if migration.version not in applied_versions
        ]
        _write_github_output("pending_count", str(len(production_pending)))
        _write_github_output(
            "pending_versions",
            ",".join(migration.version for migration in production_pending),
        )
        print(
            "Trusted schema state: "
            f"production_pending={len(production_pending)} "
            "versions="
            + (",".join(m.version for m in production_pending) or "none")
        )
        return 0

    if args.command == "bootstrap":
        assert baseline is not None and migrations is not None
        if vercel is None:
            raise PreviewError(
                "Bootstrap requires VERCEL_TOKEN, VERCEL_PROJECT_ID, and "
                "VERCEL_ORG_ID before any Supabase branch is created."
            )
        result = bootstrap_preview(
            supabase,
            vercel,
            parent_ref=args.parent_ref,
            pr_number=args.pr_number,
            git_branch=args.git_branch,
            baseline=baseline,
            migrations=migrations,
            trusted_migrations=trusted_migrations,
            source_head_sha=args.source_head_sha,
            replace=False,
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

    if args.command == "verify-retained":
        if vercel is None:
            raise PreviewError(
                "Retained Preview verification requires VERCEL_TOKEN, "
                "VERCEL_PROJECT_ID, and VERCEL_ORG_ID."
            )
        branch = verify_retained_preview(
            supabase,
            vercel,
            parent_ref=args.parent_ref,
            pr_number=args.pr_number,
            git_branch=args.git_branch,
            source_head_sha=args.source_head_sha,
            max_age_seconds=args.max_age_seconds,
        )
        _write_github_output("supabase_branch_ref", branch.project_ref)
        print(
            "Retained Preview verified read-only: "
            f"name={branch.name} ref={branch.project_ref} source={args.source_head_sha}"
        )
        return 0

    if args.command == "authorize-deployment":
        if vercel is None:
            raise PreviewError(
                "Preview deployment authorization requires VERCEL_TOKEN, "
                "VERCEL_PROJECT_ID, and VERCEL_ORG_ID."
            )
        result = authorize_preview_deployment(
            supabase,
            vercel,
            parent_ref=args.parent_ref,
            pr_number=args.pr_number,
            git_branch=args.git_branch,
            source_head_sha=args.source_head_sha,
            approved_head_sha=args.approved_head_sha,
            git_owner=args.git_owner,
            git_repo=args.git_repo,
            verified_type_only_rebind=args.verified_type_only_rebind,
            max_age_seconds=args.max_age_seconds,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.interval_seconds,
        )
        _write_github_output("deployment_id", result.deployment.id)
        deployment_url = result.deployment.url
        if not deployment_url.startswith(("https://", "http://")):
            deployment_url = f"https://{deployment_url}"
        _write_github_output("deployment_url", deployment_url)
        _write_github_output(
            "approved_head_sha", result.deployment.source_head_sha
        )
        print(
            "Exact-SHA Preview deployment requested: "
            f"id={result.deployment.id} state={result.deployment.ready_state} "
            f"sha={result.deployment.source_head_sha} url={result.deployment.url}"
        )
        return 0

    if args.command == "sweep-expired":
        if vercel is None:
            raise PreviewError(
                "Expiry sweep requires VERCEL_TOKEN, VERCEL_PROJECT_ID, and "
                "VERCEL_ORG_ID so deployment state is retired first."
            )
        cleaned = sweep_expired_previews(
            supabase,
            vercel,
            parent_ref=args.parent_ref,
            max_age_seconds=args.max_age_seconds,
            max_branches=args.max_branches,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.interval_seconds,
        )
        print(f"Preview expiry sweep complete: cleaned={cleaned}")
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
