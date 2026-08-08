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
import hashlib
import json
import os
from pathlib import Path
import re
import stat
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
MAX_MIGRATION_BYTES = 1_000_000
MAX_MIGRATIONS_BYTES = 16_000_000
MAX_BASELINE_BYTES = 2_000_000
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
)

_PROJECT_REF_RE = re.compile(r"^[a-z0-9]{20}$")
_MIGRATION_RE = re.compile(r"^(\d{14})_([a-z][a-z0-9_]*)\.sql$")
_MIGRATION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_LEDGER_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
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
    _validate_absorbed_migration_set(
        baseline, trusted_migrations, label="Trusted-main"
    )
    _validate_absorbed_migration_set(baseline, pr_migrations, label="PR")
    pending = [m for m in pr_migrations if m.version > baseline.cutoff_version]
    for migration in pending:
        if any(_transaction_statement(s) for s in _top_level_sql_statements(migration.sql)):
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
) -> None:
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
) -> None:
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
    baseline: PreviewBaseline,
    migrations: Sequence[Migration],
    trusted_migrations: Sequence[Migration],
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
    _validate_absorbed_migration_set(baseline, trusted_migrations, label="Trusted-main")
    _validate_absorbed_migration_set(baseline, migrations, label="PR")
    expected_pending = [
        migration
        for migration in migrations
        if migration.version > baseline.cutoff_version
    ]
    for migration in expected_pending:
        if any(
            _transaction_statement(statement)
            for statement in _top_level_sql_statements(migration.sql)
        ):
            raise PreviewError(
                f"{migration.path.name} contains explicit transaction control."
            )
    # This read-only production gate runs before replacing a branch or Vercel
    # target. Only the two manifest-declared historical name exceptions pass.
    verify_production_ledger(
        supabase,
        parent_ref,
        baseline,
        trusted_migrations,
        migrations,
    )
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
            pr_number=pr_number,
            git_branch=git_branch,
            branch=existing,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )

    created: BranchRecord | None = None
    try:
        try:
            candidate = supabase.create_branch(
                parent_ref, name=name, git_branch=git_branch
            )
        except ApiError as exc:
            if not exc.ambiguous:
                raise
            # POST may have succeeded. Reconcile once by exact identity; never
            # blindly create a second branch.
            candidate = find_branch(supabase, parent_ref, name)
            if candidate is None:
                raise PreviewError(
                    "Supabase branch create has ambiguous state and no exact "
                    "branch was observable; no retry was attempted."
                ) from exc
        # An unsafe response is never promoted to a rollback target. This
        # assignment occurs only after the immutable identity is proven exact.
        candidate.assert_safe_preview(
            parent_ref=parent_ref, expected_name=name, git_branch=git_branch
        )
        created = candidate
        wait_for_database(
            supabase,
            created,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )

        apply_preview_baseline(supabase, created, baseline)
        pending = migration_plan(migrations, read_ledger(supabase, created))
        if [migration.version for migration in pending] != [
            migration.version for migration in expected_pending
        ]:
            raise PreviewError(
                "Preview ledger did not expose only the post-cutoff PR suffix."
            )
        for migration in pending:
            apply_migration(supabase, created, migration)
        if migration_plan(migrations, read_ledger(supabase, created)):
            raise PreviewError("Preview migration ledger did not reach exact parity.")

        verify_post_migration_security(supabase, created, baseline)
        created = _read_exact_branch_identity(
            supabase, parent_ref, created
        )
        created.assert_safe_preview(
            parent_ref=parent_ref,
            expected_name=name,
            git_branch=git_branch,
        )
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
    bootstrap.add_argument("--migrations-root", type=Path, required=True)
    bootstrap.add_argument("--baseline-dir", type=Path, required=True)
    bootstrap.add_argument("--replace", action="store_true")
    return parser


def _main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    trusted_root = Path.cwd()
    if args.command == "validate":
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
        print(
            f"Validated trusted baseline at cutoff {baseline.cutoff_version}: "
            f"absorbed={len(baseline.absorbed_migrations)} "
            f"post_cutoff={len(pending)}."
        )
        return 0

    baseline: PreviewBaseline | None = None
    migrations: list[Migration] | None = None
    if args.command == "bootstrap":
        baseline = load_preview_baseline(args.baseline_dir, root=trusted_root)
        migrations = load_migrations(
            args.migrations_dir, root=args.migrations_root
        )
        trusted_migrations = load_migrations(
            args.baseline_dir.parent / "migrations", root=trusted_root
        )
        validate_baseline_migrations(baseline, migrations, trusted_migrations)

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
