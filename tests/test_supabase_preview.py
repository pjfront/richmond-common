"""Security and lifecycle regression tests for Supabase Preview branches."""
from __future__ import annotations

import base64
from dataclasses import replace
from datetime import timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

import pytest

import supabase_preview as preview


PARENT_REF = preview.PRODUCTION_PROJECT_REF
BRANCH_REF = "abcdefghijklmnopqrst"
GIT_BRANCH = "codex/example-preview"
SOURCE_HEAD_SHA = "1" * 40
REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "supabase-preview.yml"
EXPIRY_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "supabase-preview-expiry.yml"
)
WATCHDOG_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "supabase-preview-watchdog.yml"
)
WATCHDOG_REAL_RUN_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "supabase_preview_workflow_run_32793118575.json"
)
SCHEMA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "schema-drift.yml"


def _branch_payload(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "name": "pr-82-preview",
        "project_ref": BRANCH_REF,
        "parent_project_ref": PARENT_REF,
        "git_branch": GIT_BRANCH,
        "persistent": False,
        "is_default": False,
        "status": "ACTIVE_HEALTHY",
        "preview_project_status": "ACTIVE_HEALTHY",
        "created_at": "2026-08-07T18:19:20.123456+00:00",
        "deletion_scheduled_at": "2026-08-07T19:19:20.123456+00:00",
    }
    payload.update(updates)
    return payload


def _migration(
    tmp_path: Path,
    version: str = "20260807013500",
    name: str = "example_preview_change",
    sql: str = "create table if not exists example_preview(id bigint primary key);",
) -> preview.Migration:
    path = tmp_path / f"{version}_{name}.sql"
    path.write_text(sql, encoding="utf-8")
    canonical = preview._canonical_utf8_text(
        path, max_bytes=preview.MAX_MIGRATION_BYTES, label="Test migration"
    )
    return preview.Migration(
        version,
        name,
        path,
        canonical.strip(),
        preview._canonical_sha256(canonical),
    )


def _baseline(
    tmp_path: Path,
    absorbed: list[preview.Migration],
    *,
    schema_sql: str = "create schema public;\n",
    production_names: Mapping[str, str] | None = None,
) -> preview.PreviewBaseline:
    schema_path = tmp_path / "baseline_public_schema.sql"
    schema_path.write_text(schema_sql, encoding="utf-8")
    canonical = preview._canonical_utf8_text(
        schema_path, max_bytes=preview.MAX_BASELINE_BYTES, label="Test baseline"
    )
    production_names = production_names or {}
    entries = tuple(
        preview.BaselineMigration(
            migration.version,
            migration.name,
            migration.sha256,
            production_names.get(migration.version),
        )
        for migration in absorbed
    )
    return preview.PreviewBaseline(
        directory=tmp_path,
        manifest_path=tmp_path / "manifest.json",
        schema_path=schema_path,
        schema_sql=canonical,
        schema_sha256=preview._canonical_sha256(canonical),
        cutoff_version=absorbed[-1].version,
        absorbed_migrations=entries,
        schema_inventory={field: 0 for field in preview._INVENTORY_FIELDS},
        extensions=(
            preview.BaselineExtension("pgcrypto", "1.3", "extensions"),
            preview.BaselineExtension("uuid-ossp", "1.1", "extensions"),
            preview.BaselineExtension("vector", "0.8.2", "extensions"),
        ),
    )


def _write_baseline_bundle(
    tmp_path: Path,
    absorbed: list[preview.Migration],
    *,
    schema_sql: str = "create schema public;\n",
    manifest_updates: Mapping[str, Any] | None = None,
) -> Path:
    baseline_dir = tmp_path / "supabase" / "preview-baseline"
    baseline_dir.mkdir(parents=True)
    schema_name = f"{preview.BASELINE_CUTOFF_VERSION}_public_schema.sql"
    schema_path = baseline_dir / schema_name
    schema_path.write_text(schema_sql, encoding="utf-8")
    canonical_schema = preview._canonical_utf8_text(
        schema_path, max_bytes=preview.MAX_BASELINE_BYTES, label="Test baseline"
    )
    manifest: dict[str, Any] = {
        "format_version": preview.BASELINE_FORMAT_VERSION,
        "source_project_ref": PARENT_REF,
        "captured_at": "2026-08-08T05:23:44Z",
        "server_version": "17.6",
        "pg_dump_version": "17.10",
        "raw_schema_sha256": "0" * 64,
        "cutoff_version": preview.BASELINE_CUTOFF_VERSION,
        "schema_file": schema_name,
        "schema_sha256": preview._canonical_sha256(canonical_schema),
        "schema_inventory": {
            field: (3 if field == "default_privilege_rows" else 0)
            for field in preview._INVENTORY_FIELDS
        },
        "preview_parity_exceptions": [
            dict(exception)
            for exception in preview.EXPECTED_PREVIEW_PARITY_EXCEPTIONS
        ],
        "extensions": [
            {"name": "pgcrypto", "version": "1.3", "schema": "extensions"},
            {"name": "uuid-ossp", "version": "1.1", "schema": "extensions"},
            {"name": "vector", "version": "0.8.2", "schema": "extensions"},
        ],
        "absorbed_migrations": [
            {
                "version": migration.version,
                "name": migration.name,
                "sha256": migration.sha256,
            }
            for migration in absorbed
        ],
    }
    if manifest_updates:
        manifest.update(manifest_updates)
    (baseline_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return baseline_dir


def _jwt(role: str) -> str:
    def encode(value: Mapping[str, Any]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none'})}.{encode({'role': role})}.signature"


def test_api_timestamp_accepts_offset_that_broke_cli_2_112():
    offset = preview.parse_api_timestamp("2026-08-07T18:19:20.123456+00:00")
    zulu = preview.parse_api_timestamp("2026-08-07T18:19:20Z")
    assert offset.tzinfo == timezone.utc
    assert zulu.tzinfo == timezone.utc

    with pytest.raises(preview.PreviewError, match="lacks a UTC offset"):
        preview.parse_api_timestamp("2026-08-07T18:19:20")


def test_branch_record_requires_immutable_and_explicit_safety_fields():
    branch = preview.BranchRecord.from_payload(_branch_payload())
    branch.assert_safe_preview(
        parent_ref=PARENT_REF,
        expected_name="pr-82-preview",
        git_branch=GIT_BRANCH,
    )

    for field in ("persistent", "is_default"):
        payload = _branch_payload()
        payload.pop(field)
        with pytest.raises(preview.PreviewError, match=field):
            preview.BranchRecord.from_payload(payload)

    with pytest.raises(preview.PreviewError, match="immutable UUID"):
        preview.BranchRecord.from_payload(_branch_payload(id="mutable-name"))


def test_branch_create_requests_data_less_micro_and_rejects_boundary_violations():
    class RecordingApi:
        def __init__(self, size: str, *, with_data: Any = None) -> None:
            self.size = size
            self.with_data = with_data
            self.requests: list[dict[str, Any]] = []

        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            response = _branch_payload(desired_instance_size=self.size)
            if self.with_data is not None:
                response["with_data"] = self.with_data
            return response

    micro_api = RecordingApi("micro")
    branch = preview.SupabaseManagementClient(
        "token", api=micro_api
    ).create_branch(PARENT_REF, name="pr-82-preview", git_branch=GIT_BRANCH)
    assert branch.desired_instance_size == "micro"
    assert micro_api.requests == [
        {
            "method": "POST",
            "path": f"/v1/projects/{PARENT_REF}/branches",
            "body": {
                "branch_name": "pr-82-preview",
                "git_branch": GIT_BRANCH,
                "is_default": False,
                "persistent": False,
                "with_data": False,
                "desired_instance_size": "micro",
            },
            "expected": (201,),
        }
    ]

    with pytest.raises(preview.PreviewCostBoundaryError, match="non-Micro"):
        preview.SupabaseManagementClient(
            "token", api=RecordingApi("small")
        ).create_branch(PARENT_REF, name="pr-82-preview", git_branch=GIT_BRANCH)

    with pytest.raises(preview.PreviewDataBoundaryError, match="data-bearing"):
        preview.SupabaseManagementClient(
            "token", api=RecordingApi("micro", with_data=True)
        ).create_branch(PARENT_REF, name="pr-82-preview", git_branch=GIT_BRANCH)

    class MalformedIdentityApi(RecordingApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            response = super().request(method, path, **kwargs)
            response["id"] = "missing-immutable-identity"
            return response

    with pytest.raises(preview.PreviewDataBoundaryError, match="data-bearing"):
        preview.SupabaseManagementClient(
            "token", api=MalformedIdentityApi("micro", with_data=True)
        ).create_branch(PARENT_REF, name="pr-82-preview", git_branch=GIT_BRANCH)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"parent_project_ref": "zyxwvutsrqponmlkjihg"}, "parent_project_ref"),
        ({"persistent": True}, "persistent"),
        ({"is_default": True}, "default/production"),
        ({"project_ref": PARENT_REF}, "default/production"),
        ({"git_branch": "codex/other"}, "identity mismatch"),
    ],
)
def test_branch_safety_checks_fail_closed(updates: dict[str, Any], message: str):
    branch = preview.BranchRecord.from_payload(_branch_payload(**updates))
    with pytest.raises(preview.PreviewError, match=message):
        branch.assert_safe_preview(
            parent_ref=PARENT_REF,
            expected_name="pr-82-preview",
            git_branch=GIT_BRANCH,
        )


def test_migrations_require_exact_14_digit_utc_versions(tmp_path: Path):
    good = tmp_path / "good"
    good.mkdir()
    _migration(good)
    loaded = preview.load_migrations(good, root=tmp_path)
    assert loaded[0].version == "20260807013500"

    alias = tmp_path / "alias"
    alias.mkdir()
    (alias / "134_example_preview_change.sql").write_text("select 1;", encoding="utf-8")
    with pytest.raises(preview.PreviewError, match="14-digit UTC timestamp"):
        preview.load_migrations(alias, root=tmp_path)

    impossible = tmp_path / "impossible"
    impossible.mkdir()
    (impossible / "20261399019999_bad_time.sql").write_text("select 1;", encoding="utf-8")
    with pytest.raises(preview.PreviewError, match="invalid UTC timestamp"):
        preview.load_migrations(impossible, root=tmp_path)


def test_parent_component_symlink_cannot_escape_pr_migration_root(tmp_path: Path):
    preview_root = tmp_path / "preview-head"
    outside_supabase = tmp_path / "outside-supabase"
    outside_migrations = outside_supabase / "migrations"
    preview_root.mkdir()
    outside_migrations.mkdir(parents=True)
    _migration(outside_migrations)
    try:
        (preview_root / "supabase").symlink_to(
            outside_supabase, target_is_directory=True
        )
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    with pytest.raises(preview.PreviewError, match="symlink/reparse-point component"):
        preview.load_migrations(
            preview_root / "supabase" / "migrations",
            root=preview_root,
        )


def test_migration_plan_only_returns_a_contiguous_suffix(tmp_path: Path):
    first = _migration(tmp_path, "20260807013300", "first")
    second = _migration(tmp_path, "20260807013400", "second")
    third = _migration(tmp_path, "20260807013500", "third")
    migrations = [first, second, third]

    assert preview.migration_plan(
        migrations,
        [{"version": first.version, "name": first.name}],
    ) == [second, third]

    with pytest.raises(preview.PreviewError, match="history hole"):
        preview.migration_plan(
            migrations,
            [{"version": second.version, "name": second.name}],
        )
    with pytest.raises(preview.PreviewError, match="absent from the checked-out PR"):
        preview.migration_plan(
            migrations,
            [{"version": "20260807013200", "name": "orphan"}],
        )
    with pytest.raises(preview.PreviewError, match="names do not match"):
        preview.migration_plan(
            migrations,
            [{"version": first.version, "name": "wrong_name"}],
        )


def test_committed_baseline_matches_trusted_history_and_inventory():
    baseline_dir = REPO_ROOT / "supabase" / "preview-baseline"
    migrations_dir = REPO_ROOT / "supabase" / "migrations"
    baseline = preview.load_preview_baseline(baseline_dir, root=REPO_ROOT)
    trusted = preview.load_migrations(migrations_dir, root=REPO_ROOT)
    pending = preview.validate_baseline_migrations(baseline, trusted, trusted)

    assert baseline.cutoff_version == "20260807013300"
    assert len(baseline.absorbed_migrations) == 134
    assert [migration.version for migration in pending] == [
        "20260807013500",
        "20260808013600",
        "20260810013800",
        "20260815013900",
        "20260816014000",
        "20260816014100",
        "20260816014200",
        "20260818014300",
        "20260818014400",
        "20260824014500",
        "20260824014600",
    ]
    assert baseline.schema_inventory == {
        "tables": 83,
        "views": 20,
        "functions": 24,
        "security_definer_functions": 12,
        "policies": 90,
        "indexes": 397,
        "constraints": 265,
        "triggers": 1,
        "event_triggers": 1,
        "non_postgres_owned_relations": 0,
        "non_postgres_owned_routines": 0,
        "non_postgres_owned_event_triggers": 0,
        "sequences": 1,
        "rls_enabled": 83,
        "default_privilege_rows": 3,
    }
    exceptions = {
        entry.version: entry.production_name
        for entry in baseline.absorbed_migrations
        if entry.production_name is not None
    }
    assert exceptions == {
        "20260713051000": "124_city_contracts",
        "20260713061500": "125_influence_patterns",
    }
    assert [
        (extension.name, extension.version, extension.schema)
        for extension in baseline.extensions
    ] == [
        ("pgcrypto", "1.3", "extensions"),
        ("uuid-ossp", "1.1", "extensions"),
        ("vector", "0.8.2", "extensions"),
    ]
    assert (
        "CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions "
        "VERSION '1.3';"
    ) in baseline.schema_sql
    assert (
        'CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA extensions '
        "VERSION '1.1';"
    ) in baseline.schema_sql
    assert (
        "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions "
        "VERSION '0.8.2';"
    ) in baseline.schema_sql
    assert (
        "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions "
        "VERSION '0.8.0';"
    ) not in baseline.schema_sql
    manifest = json.loads(baseline.manifest_path.read_text(encoding="utf-8-sig"))
    assert manifest["preview_parity_exceptions"] == list(
        preview.EXPECTED_PREVIEW_PARITY_EXCEPTIONS
    )
    assert (
        "ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin"
        not in baseline.schema_sql
    )
    for object_type in ("SEQUENCES", "FUNCTIONS", "TABLES"):
        for grantee in ("postgres", "anon", "authenticated", "service_role"):
            assert (
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                f"GRANT ALL ON {object_type} TO {grantee};"
            ) in baseline.schema_sql


def test_canonical_migration_hash_is_stable_across_line_endings(tmp_path: Path):
    lf_dir = tmp_path / "lf"
    crlf_dir = tmp_path / "crlf"
    lf_dir.mkdir()
    crlf_dir.mkdir()
    name = "20260807013300_line_endings.sql"
    (lf_dir / name).write_bytes(b"create table t(id int);\n-- end\n")
    (crlf_dir / name).write_bytes(b"create table t(id int);\r\n-- end\r\n")
    assert preview.load_migrations(lf_dir, root=tmp_path)[0].sha256 == preview.load_migrations(
        crlf_dir, root=tmp_path
    )[0].sha256


def test_baseline_schema_and_absorbed_hash_tampering_fail_closed(tmp_path: Path):
    migration = _migration(
        tmp_path, preview.BASELINE_CUTOFF_VERSION, "captured_cutoff"
    )
    baseline_dir = _write_baseline_bundle(tmp_path, [migration])
    baseline = preview.load_preview_baseline(baseline_dir, root=tmp_path)

    baseline.schema_path.write_text(
        "create schema public;\nselect 1;\n", encoding="utf-8"
    )
    with pytest.raises(preview.PreviewError, match="SHA-256"):
        preview.load_preview_baseline(baseline_dir, root=tmp_path)

    baseline.schema_path.write_text("create schema public;\n", encoding="utf-8")
    pr_dir = tmp_path / "pr"
    trusted_dir = tmp_path / "trusted"
    pr_dir.mkdir()
    trusted_dir.mkdir()
    _migration(pr_dir, migration.version, migration.name, "select 2;")
    _migration(trusted_dir, migration.version, migration.name, migration.sql)
    with pytest.raises(preview.PreviewError, match="PR absorbed migration SHA-256"):
        preview.validate_baseline_migrations(
            baseline,
            preview.load_migrations(pr_dir, root=tmp_path),
            preview.load_migrations(trusted_dir, root=tmp_path),
        )


@pytest.mark.parametrize("mutation", ["default_owner", "vector_version", "extra"])
def test_preview_parity_exception_contract_rejects_any_variant(
    tmp_path: Path, mutation: str
):
    migration = _migration(
        tmp_path, preview.BASELINE_CUTOFF_VERSION, "captured_cutoff"
    )
    baseline_dir = _write_baseline_bundle(tmp_path, [migration])
    manifest_path = baseline_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "default_owner":
        manifest["preview_parity_exceptions"][0]["owner"] = "postgres"
    elif mutation == "vector_version":
        manifest["preview_parity_exceptions"][1]["preview_version"] = "0.8.3"
    else:
        manifest["preview_parity_exceptions"].append(
            dict(manifest["preview_parity_exceptions"][1])
        )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(preview.PreviewError, match="two allowed"):
        preview.load_preview_baseline(baseline_dir, root=tmp_path)


def test_vector_extension_must_match_exact_preview_parity_exception(tmp_path: Path):
    migration = _migration(
        tmp_path, preview.BASELINE_CUTOFF_VERSION, "captured_cutoff"
    )
    baseline_dir = _write_baseline_bundle(tmp_path, [migration])
    manifest_path = baseline_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["extensions"][2]["version"] = "0.8.3"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(preview.PreviewError, match="exact Preview parity exception"):
        preview.load_preview_baseline(baseline_dir, root=tmp_path)


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("create schema public;\ninsert into t values (1);", "INSERT DML"),
        ("create schema public;\ncopy t from stdin;", "COPY DML"),
        (
            "create schema public;\nwith x as (select 1) delete from t;",
            "WITH DML",
        ),
        ("begin;\ncreate schema public;\ncommit;", "transaction control"),
        ("create schema public;\nabort;", "transaction control"),
        (
            "create schema public;\nalter table public.t owner to app_user;",
            "ALTER OWNER",
        ),
        (
            "create schema public;\nALTER DEFAULT PRIVILEGES FOR ROLE "
            "supabase_admin IN SCHEMA public GRANT ALL ON TABLES TO postgres;",
            "supabase_admin default ACL",
        ),
        (
            "create schema public;\nALTER DEFAULT PRIVILEGES FOR USER "
            "supabase_admin IN SCHEMA public GRANT ALL ON FUNCTIONS TO postgres;",
            "supabase_admin default ACL",
        ),
        ("create schema public;\n\\copy t from 'x'", "meta-command"),
        (
            "create schema public;\ncomment on schema public is "
            "'postgresql://user:password@example.test/db';",
            "connection URI",
        ),
    ],
)
def test_baseline_rejects_top_level_data_transactions_meta_and_secrets(
    tmp_path: Path, sql: str, message: str
):
    with pytest.raises(preview.PreviewError, match=message):
        preview._validate_baseline_sql(sql, path=tmp_path / "schema.sql")


def test_baseline_allows_function_body_dml_and_privilege_verbs(tmp_path: Path):
    sql = """
create schema public;
create table public.audit_log(id bigint);
create function public.record_change() returns trigger
language plpgsql as $body$
begin
  insert into public.audit_log(id) values (new.id);
  update public.audit_log set id = id where id = new.id;
  return new;
end;
$body$;
grant insert, update, delete on table public.audit_log to authenticated;
"""
    preview._validate_baseline_sql(sql, path=tmp_path / "schema.sql")


@pytest.mark.parametrize(
    "statement",
    [
        "ABORT",
        "PREPARE TRANSACTION 'preview_escape'",
        "RELEASE preview_savepoint",
        "SAVEPOINT preview_savepoint",
        "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE",
        "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY",
    ],
)
def test_postgres_transaction_control_variants_are_rejected(statement: str):
    assert preview._transaction_statement(statement) is True


def test_transaction_named_setting_is_not_transaction_control():
    assert preview._transaction_statement("SET transaction_timeout = 0") is False


def test_standard_string_backslash_cannot_mask_top_level_commit():
    sql = r"select '\'; COMMIT; select 'still quoted';"
    statements = preview._top_level_sql_statements(sql)
    assert any(preview._transaction_statement(statement) for statement in statements)


def test_escape_string_backslash_keeps_transaction_word_inside_string():
    sql = r"select E'not transaction control: \' COMMIT'; create table safe(id int);"
    statements = preview._top_level_sql_statements(sql)
    assert not any(
        preview._transaction_statement(statement) for statement in statements
    )


def test_choose_public_key_rejects_all_elevated_key_shapes():
    publishable = "sb_publishable_branch-public-value"
    assert preview.choose_public_api_key(
        [
            {"name": "service_role", "api_key": _jwt("service_role")},
            {"name": "backend", "type": "secret", "api_key": "sb_secret_nope"},
            {"name": "default", "type": "publishable", "api_key": publishable},
            {"name": "anon", "api_key": _jwt("anon")},
        ]
    ) == publishable

    with pytest.raises(preview.PreviewError, match="no verified publishable/anon"):
        preview.choose_public_api_key(
            [
                {"name": "service_role", "api_key": _jwt("service_role")},
                {"name": "mislabelled", "api_key": _jwt("anon")},
                {"name": "secret", "api_key": "sb_secret_nope"},
            ]
        )


def test_control_plane_response_wrappers_include_vercel_envs():
    row = {"id": "env-id"}
    assert preview._rows({"envs": [row]}, context="test") == [row]


def _database_error(code: str, message: str) -> preview.ApiError:
    body = json.dumps({"code": code, "message": message})
    return preview.ApiError(
        f"database query failed: {body}",
        method="POST",
        path=f"/v1/projects/{BRANCH_REF}/database/query/read-only",
        status=500,
        response_body=body,
    )


def _live_missing_ledger_error() -> preview.ApiError:
    body = json.dumps(
        {
            "message": "Failed to run sql query: ERROR:  42P01: relation "
            '"supabase_migrations.schema_migrations" does not exist\n'
            "LINE 1: select version, coalesce(name, '') as name ..."
        }
    )
    return preview.ApiError(
        f"database query failed: {body}",
        method="POST",
        path=f"/v1/projects/{BRANCH_REF}/database/query/read-only",
        status=500,
        response_body=body,
    )


class FreshLedgerClient:
    def __init__(self) -> None:
        self.ledger_exists = False
        self.ledger: dict[str, str] = {}
        self.calls: list[tuple[str, bool]] = []

    def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
        assert project_ref == BRANCH_REF
        self.calls.append((sql, read_only))
        if sql == preview._LEDGER_QUERY:
            if not self.ledger_exists:
                raise _live_missing_ledger_error()
            return [
                {"version": version, "name": name}
                for version, name in sorted(self.ledger.items())
            ]
        if sql == preview._LEDGER_INIT_SQL:
            assert read_only is False
            self.ledger_exists = True
            return []
        assert read_only is False
        match = re.search(
            r"values \('(?P<version>\d{14})', '(?P<name>[a-z0-9_]+)'\)", sql
        )
        assert match is not None
        self.ledger[match.group("version")] = match.group("name")
        return []


def test_brand_new_data_less_branch_initializes_exact_cli_ledger_then_applies(
    tmp_path: Path,
):
    client = FreshLedgerClient()
    branch = preview.BranchRecord.from_payload(_branch_payload())
    migration = _migration(tmp_path)

    assert preview.read_ledger(client, branch) == []
    assert client.calls[:3] == [
        (preview._LEDGER_QUERY, True),
        (preview._LEDGER_INIT_SQL, False),
        (preview._LEDGER_QUERY, True),
    ]
    assert "version text not null primary key" in preview._LEDGER_INIT_SQL
    assert "statements text[]" in preview._LEDGER_INIT_SQL
    assert "name text" in preview._LEDGER_INIT_SQL
    assert "created_by text" in preview._LEDGER_INIT_SQL
    assert "idempotency_key text unique" in preview._LEDGER_INIT_SQL
    assert "rollback text[]" in preview._LEDGER_INIT_SQL
    assert "unique (idempotency_key)" in preview._LEDGER_INIT_SQL

    preview.apply_migration(client, branch, migration)
    assert client.ledger == {migration.version: migration.name}


def test_missing_ledger_matches_exact_live_management_api_error_shape():
    assert preview._is_missing_ledger_error(_live_missing_ledger_error()) is True


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (
            "42501",
            'permission denied for relation "supabase_migrations.schema_migrations"',
        ),
        ("42P01", 'relation "public.some_other_table" does not exist'),
        ("57014", "canceling statement due to statement timeout"),
    ],
)
def test_ledger_read_does_not_swallow_other_database_errors(
    code: str, message: str
):
    branch = preview.BranchRecord.from_payload(_branch_payload())

    class FailingClient:
        def __init__(self) -> None:
            self.calls = 0

        def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
            self.calls += 1
            raise _database_error(code, message)

    client = FailingClient()
    with pytest.raises(preview.ApiError):
        preview.read_ledger(client, branch)
    assert client.calls == 1


class FakeSupabase:
    def __init__(
        self,
        baseline: preview.PreviewBaseline,
        *,
        application_objects: list[Mapping[str, Any]] | None = None,
    ) -> None:
        self.baseline = baseline
        self.branches: list[preview.BranchRecord] = []
        self.ledger: dict[str, str] = {}
        self.production_ledger = {
            entry.version: entry.production_ledger_name
            for entry in baseline.absorbed_migrations
        }
        self.application_objects = list(application_objects or [])
        self.created_payloads: list[dict[str, Any]] = []
        self.deleted_refs: list[str] = []
        self.scheduled_refs: list[str] = []
        self.schema_inventory_reads = 0
        self.extension_inventory_reads = 0
        self.write_queries: list[str] = []

    def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
        assert parent_ref == PARENT_REF
        return list(self.branches)

    def create_branch(
        self, parent_ref: str, *, name: str, git_branch: str
    ) -> preview.BranchRecord:
        assert parent_ref == PARENT_REF
        self.created_payloads.append(
            {
                "branch_name": name,
                "git_branch": git_branch,
                "is_default": False,
                "persistent": False,
                "with_data": False,
                "desired_instance_size": "micro",
            }
        )
        created_at = preview.datetime.now(preview.timezone.utc)
        branch = preview.BranchRecord.from_payload(
            _branch_payload(
                name=name,
                git_branch=git_branch,
                created_at=created_at.isoformat(),
                deletion_scheduled_at=(created_at + timedelta(hours=1)).isoformat(),
                desired_instance_size="micro",
            )
        )
        self.branches.append(branch)
        return branch

    def delete_branch(self, project_ref: str) -> None:
        self.deleted_refs.append(project_ref)
        self.branches = [b for b in self.branches if b.project_ref != project_ref]

    def schedule_branch_deletion(self, project_ref: str) -> None:
        self.scheduled_refs.append(project_ref)
        self.branches = [
            replace(
                branch,
                deletion_scheduled_at=branch.created_at + timedelta(hours=1),
            )
            if branch.project_ref == project_ref
            else branch
            for branch in self.branches
        ]

    def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
        if project_ref == PARENT_REF and sql == preview._LEDGER_QUERY:
            assert read_only is True
            return [
                {"version": version, "name": name}
                for version, name in sorted(self.production_ledger.items())
            ]
        assert project_ref == BRANCH_REF
        if sql == "select 1 as ok":
            return [{"ok": 1}]
        if sql == preview._EMPTY_APPLICATION_CATALOG_QUERY:
            assert read_only is True
            return list(self.application_objects)
        if sql == preview._SCHEMA_INVENTORY_QUERY:
            assert read_only is True
            self.schema_inventory_reads += 1
            return [dict(self.baseline.schema_inventory)]
        if sql == preview._EXTENSION_INVENTORY_QUERY:
            assert read_only is True
            self.extension_inventory_reads += 1
            return [
                {
                    "name": extension.name,
                    "version": extension.version,
                    "schema": extension.schema,
                }
                for extension in self.baseline.extensions
            ]
        if sql == preview._LEDGER_QUERY:
            return [
                {"version": version, "name": name}
                for version, name in sorted(self.ledger.items())
            ]
        assert read_only is False
        self.write_queries.append(sql)
        matches = re.findall(
            r"values \('(?P<version>\d{14})', '(?P<name>[a-z0-9_]+)'\)", sql
        )
        if not matches:
            matches = re.findall(
                r"\('(?P<version>\d{14})', '(?P<name>[a-z0-9_]+)'\)", sql
            )
        assert matches
        for version, name in matches:
            self.ledger[version] = name
        return []

    def api_keys(self, project_ref: str) -> Any:
        assert project_ref == BRANCH_REF
        return [
            {"name": "service_role", "api_key": _jwt("service_role")},
            {"name": "anon", "api_key": _jwt("anon")},
        ]


class FakeVercel:
    def __init__(self, *, fail_on_key: str | None = None) -> None:
        self.rows: list[dict[str, Any]] = []
        self.deleted_ids: list[str] = []
        self.fail_on_key = fail_on_key
        self.deployments: list[dict[str, str]] = []
        self.retired_deployments: list[str] = []
        self.events: list[str] = []

    def list_envs(self, git_branch: str) -> list[Mapping[str, Any]]:
        return list(self.rows)

    def list_all_preview_envs(self) -> list[Mapping[str, Any]]:
        return list(self.rows)

    def create_preview_env(self, *, key: str, value: str, git_branch: str) -> None:
        if key == self.fail_on_key:
            raise preview.PreviewError("injected Vercel failure")
        self.rows.append(
            {
                "id": f"env-{len(self.rows) + 1}",
                "key": key,
                "value": value,
                "target": ["preview"],
                "gitBranch": git_branch,
            }
        )

    def delete_env(self, env_id: str) -> None:
        self.events.append(f"env:{env_id}")
        self.deleted_ids.append(env_id)
        self.rows = [row for row in self.rows if row["id"] != env_id]

    def create_preview_deployment(
        self,
        *,
        git_owner: str,
        git_repo: str,
        git_branch: str,
        source_head_sha: str,
        timeout_seconds: float = 600.0,
        interval_seconds: float = 5.0,
        on_created: Any = None,
    ) -> preview.VercelDeployment:
        record = {
            "git_owner": git_owner,
            "git_repo": git_repo,
            "git_branch": git_branch,
            "source_head_sha": source_head_sha,
        }
        self.deployments.append(record)
        deployment_id = f"dpl_{len(self.deployments)}"
        if on_created is not None:
            on_created(deployment_id)
        return preview.VercelDeployment(
            id=deployment_id,
            url=f"rtp-{source_head_sha[:8]}.vercel.app",
            ready_state="READY",
            source_head_sha=source_head_sha,
            created_at=preview.parse_api_timestamp(
                "2026-08-07T18:30:00+00:00"
            ),
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
        self.events.append(f"deployment:{deployment_id}")
        self.retired_deployments.append(deployment_id)


def _safe_vercel_project_payload() -> dict[str, Any]:
    return {
        "id": "prj_test",
        "name": "rtp",
    }


class RecordingVercelApi:
    def __init__(
        self,
        project: Mapping[str, Any],
        deployment: Mapping[str, Any] | None = None,
    ) -> None:
        self.project = project
        self.deployment = deployment or {
            "id": "dpl_exact",
            "url": "rtp-exact.vercel.app",
            "readyState": "READY",
            "projectId": "prj_test",
            "target": "preview",
            "meta": {
                "githubCommitOrg": "pjfront",
                "githubCommitRepo": "richmond-common",
                "githubCommitRef": GIT_BRANCH,
                "githubCommitSha": SOURCE_HEAD_SHA,
            },
            "gitSource": {
                "type": "github",
                "ref": GIT_BRANCH,
                "sha": SOURCE_HEAD_SHA,
            },
            "createdAt": int(
                preview.datetime.now(preview.timezone.utc).timestamp() * 1000
            ),
        }
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        query: Mapping[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        self.requests.append(
            {
                "method": method,
                "path": path,
                "body": body,
                "query": query,
                "expected": expected,
            }
        )
        if method == "GET" and path.startswith("/v9/projects/"):
            return self.project
        return self.deployment


def test_vercel_controller_requests_exact_sha_rest_api_preview():
    api = RecordingVercelApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    deployment = client.create_preview_deployment(
        git_owner="pjfront",
        git_repo="richmond-common",
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
    )

    assert deployment.source_head_sha == SOURCE_HEAD_SHA
    request = next(
        request for request in api.requests
        if request["method"] == "POST" and request["path"] == "/v13/deployments"
    )
    assert request["method"] == "POST"
    assert request["path"] == "/v13/deployments"
    assert request["query"] == {"teamId": "team_test"}
    assert "target" not in request["body"]
    assert request["body"] == {
        "name": "rtp",
        "project": "prj_test",
        "gitSource": {
            "type": "github",
            "org": "pjfront",
            "repo": "richmond-common",
            "ref": GIT_BRANCH,
            "sha": SOURCE_HEAD_SHA,
        },
    }
    assert deployment.ready_state == "READY"


def test_vercel_controller_rejects_terminal_deployment_response():
    api = RecordingVercelApi(
        _safe_vercel_project_payload(),
        {
            "id": "dpl_blocked",
            "url": "rtp-blocked.vercel.app",
            "readyState": "BLOCKED",
            "projectId": "prj_test",
            "target": "preview",
            "meta": {
                "githubCommitOrg": "pjfront",
                "githubCommitRepo": "richmond-common",
                "githubCommitRef": GIT_BRANCH,
                "githubCommitSha": SOURCE_HEAD_SHA,
            },
            "gitSource": {
                "type": "github",
                "ref": GIT_BRANCH,
                "sha": SOURCE_HEAD_SHA,
            },
            "createdAt": int(
                preview.datetime.now(preview.timezone.utc).timestamp() * 1000
            ),
        },
    )
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    with pytest.raises(preview.PreviewError, match="state=BLOCKED"):
        client.create_preview_deployment(
            git_owner="pjfront",
            git_repo="richmond-common",
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
        )

    assert any(
        request["method"] == "DELETE"
        and request["path"] == "/v13/deployments/dpl_blocked"
        for request in api.requests
    )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"projectId": "prj_wrong"}, "project attestation"),
        ({"target": "production"}, "target is not Preview"),
        ({"meta": {}}, "metadata attestation"),
        ({"gitSource": {}}, "source attestation"),
    ],
)
def test_vercel_controller_never_persists_or_retires_unattested_returned_id(
    updates: Mapping[str, Any], message: str, monkeypatch: pytest.MonkeyPatch
):
    clock = [0.0]
    payload = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    payload.update(updates)
    api = RecordingVercelApi(_safe_vercel_project_payload(), payload)
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )
    monkeypatch.setattr(preview.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        preview.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    persisted: list[str] = []
    with pytest.raises(preview.PreviewError, match="bounded read-after-create"):
        client.create_preview_deployment(
            git_owner="pjfront",
            git_repo="richmond-common",
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            timeout_seconds=0,
            interval_seconds=0,
            on_created=persisted.append,
        )
    assert message  # Documents which immutable attestation was invalidated.
    assert persisted == []
    assert not any(
        request["method"] in {"PATCH", "DELETE"}
        for request in api.requests
    )


def test_vercel_controller_timeout_cancels_then_deletes_exact_deployment():
    deployment = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    deployment["readyState"] = "BUILDING"
    api = RecordingVercelApi(_safe_vercel_project_payload(), deployment)
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    with pytest.raises(preview.PreviewError, match="Timed out"):
        client.create_preview_deployment(
            git_owner="pjfront",
            git_repo="richmond-common",
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            timeout_seconds=0,
            interval_seconds=0,
        )

    mutations = [
        (request["method"], request["path"])
        for request in api.requests
        if request["method"] in {"PATCH", "DELETE"}
    ]
    assert mutations == [
        ("PATCH", "/v12/deployments/dpl_exact/cancel"),
        ("DELETE", "/v13/deployments/dpl_exact"),
    ]


def test_ambiguous_vercel_create_reconciles_once_without_retrying_post():
    deployment = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    deployment["id"] = "dpl_reconciled"
    deployment["createdAt"] = int(
        preview.datetime.now(preview.timezone.utc).timestamp() * 1000
    )

    class AmbiguousCreateApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                raise preview.ApiError(
                    "ambiguous create",
                    method=method,
                    path=path,
                )
            if method == "GET" and path == "/v6/deployments":
                return {"deployments": [{"uid": "dpl_reconciled"}]}
            return self.deployment

    api = AmbiguousCreateApi(_safe_vercel_project_payload(), deployment)
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    result = client.create_preview_deployment(
        git_owner="pjfront",
        git_repo="richmond-common",
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
    )

    assert result.id == "dpl_reconciled"
    assert sum(
        request["method"] == "POST" and request["path"] == "/v13/deployments"
        for request in api.requests
    ) == 1


def test_incomplete_returned_vercel_id_is_reattested_after_old_30_second_window(
    monkeypatch: pytest.MonkeyPatch,
):
    clock = [0.0]
    complete = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    complete["id"] = "dpl_late_returned"
    incomplete = {**complete, "meta": {}}

    class LateReturnedIdApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                return {"id": "dpl_late_returned"}
            if method == "GET" and path == "/v6/deployments":
                return {"deployments": []}
            if method == "GET" and path.endswith("/dpl_late_returned"):
                return complete if clock[0] >= 50.0 else incomplete
            raise AssertionError((method, path))

    monkeypatch.setattr(preview.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        preview.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    api = LateReturnedIdApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    result = client.create_preview_deployment(
        git_owner="pjfront",
        git_repo="richmond-common",
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
    )

    assert result.id == "dpl_late_returned"
    assert clock[0] == 50.0
    assert sum(
        request["method"] == "POST" and request["path"] == "/v13/deployments"
        for request in api.requests
    ) == 1
    assert not any(
        request["method"] in {"PATCH", "DELETE"} for request in api.requests
    )


@pytest.mark.parametrize("inventory_failure", ["http-500", "malformed-200"])
def test_returned_vercel_id_retries_independently_of_transient_inventory_failure(
    monkeypatch: pytest.MonkeyPatch,
    inventory_failure: str,
):
    clock = [0.0]
    complete = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    complete["id"] = "dpl_returned"
    incomplete = {**complete, "gitSource": {}}

    class FailingInventoryApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                return {"id": "dpl_returned"}
            if method == "GET" and path == "/v6/deployments":
                if inventory_failure == "http-500":
                    raise preview.ApiError(
                        "transient list failure",
                        method=method,
                        path=path,
                        status=500,
                    )
                return {"unexpected": "shape"}
            if method == "GET" and path.endswith("/dpl_returned"):
                return complete if clock[0] >= 10.0 else incomplete
            raise AssertionError((method, path))

    monkeypatch.setattr(preview.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        preview.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    api = FailingInventoryApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    result = client.create_preview_deployment(
        git_owner="pjfront",
        git_repo="richmond-common",
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
    )

    assert result.id == "dpl_returned"
    assert clock[0] == 10.0
    assert sum(
        request["method"] == "POST" and request["path"] == "/v13/deployments"
        for request in api.requests
    ) == 1


@pytest.mark.parametrize("status", [401, 403])
def test_vercel_inventory_auth_failure_is_never_retried(status: int):
    class InventoryAuthFailureApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                raise preview.ApiError(
                    "ambiguous create",
                    method=method,
                    path=path,
                )
            if method == "GET" and path == "/v6/deployments":
                raise preview.ApiError(
                    "authentication failed",
                    method=method,
                    path=path,
                    status=status,
                )
            raise AssertionError((method, path))

    api = InventoryAuthFailureApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    with pytest.raises(preview.ApiError) as error:
        client.create_preview_deployment(
            git_owner="pjfront",
            git_repo="richmond-common",
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
        )

    assert error.value.status == status
    assert sum(
        request["method"] == "GET" and request["path"] == "/v6/deployments"
        for request in api.requests
    ) == 1
    assert not any(
        request["method"] in {"PATCH", "DELETE"} for request in api.requests
    )


def test_late_vercel_inventory_attests_exact_candidate_without_unrelated_deletion(
    monkeypatch: pytest.MonkeyPatch,
):
    clock = [0.0]
    template = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    exact = {**template, "id": "dpl_late_exact"}
    unrelated = {
        **template,
        "id": "dpl_unrelated",
        "meta": {**template["meta"], "githubCommitSha": "2" * 40},
        "gitSource": {**template["gitSource"], "sha": "2" * 40},
    }

    class LateInventoryApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                raise preview.ApiError(
                    "ambiguous create",
                    method=method,
                    path=path,
                )
            if method == "GET" and path == "/v6/deployments":
                if clock[0] < 50.0:
                    return {"deployments": [{"uid": "dpl_unrelated"}]}
                return {
                    "deployments": [
                        {"uid": "dpl_unrelated"},
                        {"uid": "dpl_late_exact"},
                    ]
                }
            if method == "GET" and path.endswith("/dpl_unrelated"):
                return unrelated
            if method == "GET" and path.endswith("/dpl_late_exact"):
                return exact
            raise AssertionError((method, path))

    monkeypatch.setattr(preview.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        preview.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    api = LateInventoryApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    result = client.create_preview_deployment(
        git_owner="pjfront",
        git_repo="richmond-common",
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
    )

    assert result.id == "dpl_late_exact"
    assert clock[0] == 50.0
    assert sum(
        request["method"] == "POST" and request["path"] == "/v13/deployments"
        for request in api.requests
    ) == 1
    assert not any(
        request["method"] in {"PATCH", "DELETE"}
        and "dpl_unrelated" in request["path"]
        for request in api.requests
    )


def test_vercel_reconciliation_deadline_is_bounded_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
):
    clock = [0.0]
    template = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    unrelated = {
        **template,
        "id": "dpl_unrelated",
        "projectId": "prj_unrelated",
    }

    class NeverExactApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                raise preview.ApiError(
                    "ambiguous create",
                    method=method,
                    path=path,
                )
            if method == "GET" and path == "/v6/deployments":
                return {"deployments": [{"uid": "dpl_unrelated"}]}
            if method == "GET" and path.endswith("/dpl_unrelated"):
                return unrelated
            raise AssertionError((method, path))

    monkeypatch.setattr(preview.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        preview.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    api = NeverExactApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    with pytest.raises(preview.PreviewError, match="bounded read-after-create"):
        client.create_preview_deployment(
            git_owner="pjfront",
            git_repo="richmond-common",
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
        )

    assert clock[0] == preview.VERCEL_CREATE_RECONCILE_MAX_WAIT_SECONDS
    assert sum(
        request["method"] == "POST" and request["path"] == "/v13/deployments"
        for request in api.requests
    ) == 1
    assert not any(
        request["method"] in {"PATCH", "DELETE"} for request in api.requests
    )


def test_slow_vercel_detail_reads_stop_after_one_in_flight_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    clock = [0.0]
    template = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    exact = {**template, "id": "dpl_exact"}
    slow_unrelated = {
        **template,
        "id": "dpl_slow",
        "projectId": "prj_unrelated",
    }

    class SlowDetailsApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                raise preview.ApiError(
                    "ambiguous create",
                    method=method,
                    path=path,
                )
            if method == "GET" and path == "/v6/deployments":
                clock[0] += 85.0
                return {
                    "deployments": [
                        {"uid": "dpl_exact"},
                        {"uid": "dpl_slow"},
                        {"uid": "dpl_unread"},
                    ]
                }
            if method == "GET" and path.endswith("/dpl_exact"):
                return exact
            if method == "GET" and path.endswith("/dpl_slow"):
                clock[0] += 30.0
                return slow_unrelated
            if method == "GET" and path.endswith("/dpl_unread"):
                raise AssertionError("deadline permitted an extra detail read")
            if method in {"PATCH", "DELETE"}:
                return {}
            raise AssertionError((method, path))

    monkeypatch.setattr(preview.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(preview.time, "sleep", lambda seconds: None)
    api = SlowDetailsApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    with pytest.raises(preview.PreviewError, match="bounded read-after-create"):
        client.create_preview_deployment(
            git_owner="pjfront",
            git_repo="richmond-common",
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
        )

    assert clock[0] == 115.0
    assert clock[0] <= preview.VERCEL_CREATE_RECONCILE_MAX_WAIT_SECONDS + 30.0
    assert not any(
        request["method"] == "GET" and request["path"].endswith("/dpl_unread")
        for request in api.requests
    )
    assert [
        (request["method"], request["path"])
        for request in api.requests
        if request["method"] in {"PATCH", "DELETE"}
    ] == [
        ("PATCH", "/v12/deployments/dpl_exact/cancel"),
        ("DELETE", "/v13/deployments/dpl_exact"),
    ]


def test_returned_vercel_id_is_reattested_before_slow_inventory_request(
    monkeypatch: pytest.MonkeyPatch,
):
    clock = [0.0]
    returned_reads = [0]
    template = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    returned_exact = {**template, "id": "dpl_zzz"}
    returned_incomplete = {**returned_exact, "meta": {}}

    class ReturnedFirstApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                return {"id": "dpl_zzz"}
            if method == "GET" and path == "/v6/deployments":
                clock[0] += 120.0
                raise AssertionError("inventory ran before returned-ID re-attestation")
            if method == "GET" and path.endswith("/dpl_zzz"):
                returned_reads[0] += 1
                return returned_incomplete if returned_reads[0] == 1 else returned_exact
            raise AssertionError((method, path))

    monkeypatch.setattr(preview.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(preview.time, "sleep", lambda seconds: None)
    api = ReturnedFirstApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    result = client.create_preview_deployment(
        git_owner="pjfront",
        git_repo="richmond-common",
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
    )

    assert result.id == "dpl_zzz"
    assert clock[0] == 0.0
    detail_paths = [
        request["path"]
        for request in api.requests
        if request["method"] == "GET"
        and request["path"].startswith("/v13/deployments/dpl_")
    ]
    assert detail_paths == [
        "/v13/deployments/dpl_zzz",
        "/v13/deployments/dpl_zzz",
        "/v13/deployments/dpl_zzz",
    ]
    assert not any(
        request["method"] == "GET" and request["path"] == "/v6/deployments"
        for request in api.requests
    )
    assert not any(
        request["method"] in {"PATCH", "DELETE"} for request in api.requests
    )


def test_ambiguous_vercel_create_attempts_retirement_for_every_exact_duplicate():
    template = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)

    class DuplicateCreateApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                raise preview.ApiError(
                    "ambiguous create",
                    method=method,
                    path=path,
                )
            if method == "GET" and path == "/v6/deployments":
                return {
                    "deployments": [
                        {"uid": "dpl_first"},
                        {"uid": "dpl_second"},
                    ]
                }
            if method == "GET" and path.endswith("/dpl_first"):
                return {**template, "id": "dpl_first"}
            if method == "GET" and path.endswith("/dpl_second"):
                return {**template, "id": "dpl_second"}
            if method == "PATCH" and path.endswith("/dpl_first/cancel"):
                raise preview.ApiError(
                    "first retirement failed",
                    method=method,
                    path=path,
                    status=500,
                )
            if method in {"PATCH", "DELETE"}:
                return {}
            raise AssertionError((method, path))

    api = DuplicateCreateApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )

    with pytest.raises(preview.PreviewError, match="dpl_first") as error:
        client.create_preview_deployment(
            git_owner="pjfront",
            git_repo="richmond-common",
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
        )
    assert "ACTION: Do not retry or create another Preview" in str(error.value)

    attempted_cancels = {
        request["path"]
        for request in api.requests
        if request["method"] == "PATCH"
    }
    assert attempted_cancels == {
        "/v12/deployments/dpl_first/cancel",
        "/v12/deployments/dpl_second/cancel",
    }
    assert any(
        request["method"] == "DELETE"
        and request["path"] == "/v13/deployments/dpl_second"
        for request in api.requests
    )


@pytest.mark.parametrize("malformed_mode", ["missing-id", "invalid-json-201"])
def test_malformed_successful_vercel_create_reconciles_without_second_post(
    malformed_mode: str,
):
    deployment = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    deployment["id"] = "dpl_fresh"

    class MalformedSuccessApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                if malformed_mode == "invalid-json-201":
                    raise preview.ApiError(
                        "invalid JSON after committed create",
                        method=method,
                        path=path,
                        status=201,
                    )
                return {}
            if method == "GET" and path == "/v6/deployments":
                return {"deployments": [{"uid": "dpl_fresh"}]}
            return self.deployment

    api = MalformedSuccessApi(_safe_vercel_project_payload(), deployment)
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )
    persisted: list[str] = []

    result = client.create_preview_deployment(
        git_owner="pjfront",
        git_repo="richmond-common",
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
        on_created=persisted.append,
    )

    assert result.id == "dpl_fresh"
    assert persisted == ["dpl_fresh"]
    assert sum(
        request["method"] == "POST" and request["path"] == "/v13/deployments"
        for request in api.requests
    ) == 1


@pytest.mark.parametrize(
    "returned_update",
    [
        {"createdAt": 1},
        {"projectId": "prj_unrelated"},
    ],
)
def test_unproven_returned_vercel_id_is_not_persisted_or_retired(
    returned_update: Mapping[str, Any],
):
    template = dict(RecordingVercelApi(_safe_vercel_project_payload()).deployment)
    returned = dict(template)
    returned.update(returned_update)
    returned["id"] = "dpl_unproven"
    fresh = dict(template)
    fresh["id"] = "dpl_fresh"

    class ReconciledCreateApi(RecordingVercelApi):
        def request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.requests.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path.startswith("/v9/projects/"):
                return self.project
            if method == "POST" and path == "/v13/deployments":
                return {"id": "dpl_unproven"}
            if method == "GET" and path == "/v6/deployments":
                return {
                    "deployments": [
                        {"uid": "dpl_unproven"},
                        {"uid": "dpl_fresh"},
                    ]
                }
            if path.endswith("/dpl_unproven"):
                return returned
            if path.endswith("/dpl_fresh"):
                return fresh
            raise AssertionError((method, path))

    api = ReconciledCreateApi(_safe_vercel_project_payload())
    client = preview.VercelClient(
        "token", project_id="prj_test", team_id="team_test", api=api
    )
    persisted: list[str] = []

    result = client.create_preview_deployment(
        git_owner="pjfront",
        git_repo="richmond-common",
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
        on_created=persisted.append,
    )

    assert result.id == "dpl_fresh"
    assert persisted == ["dpl_fresh"]
    assert not any(
        request["method"] in {"PATCH", "DELETE"}
        and "dpl_unproven" in request["path"]
        for request in api.requests
    )
    assert sum(
        request["method"] == "POST" and request["path"] == "/v13/deployments"
        for request in api.requests
    ) == 1


def test_active_readiness_polls_authoritative_preview_status_same_identity():
    branch = preview.BranchRecord.from_payload(
        _branch_payload(
            status="MIGRATIONS_FAILED",
            preview_project_status="COMING_UP",
            deletion_scheduled_at=None,
        )
    )

    class ReadinessClient:
        def __init__(self) -> None:
            self.reads = 0

        def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
            assert parent_ref == PARENT_REF
            self.reads += 1
            status = "COMING_UP" if self.reads == 1 else "ACTIVE_HEALTHY"
            return [replace(branch, preview_project_status=status)]

    client = ReadinessClient()
    observed = preview.wait_for_active_preview(
        client,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert observed.preview_project_status == "ACTIVE_HEALTHY"
    assert observed.status == "MIGRATIONS_FAILED"
    assert client.reads == 2


def test_active_readiness_timeout_never_soft_deletes():
    branch = preview.BranchRecord.from_payload(
        _branch_payload(
            preview_project_status="COMING_UP",
            deletion_scheduled_at=None,
        )
    )

    class NeverActiveClient:
        def __init__(self) -> None:
            self.requests: list[str] = []

        def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
            self.requests.append("GET")
            return [branch]

    client = NeverActiveClient()
    with pytest.raises(preview.PreviewError, match="ACTIVE_HEALTHY"):
        preview.wait_for_active_preview(
            client,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            branch=branch,
            timeout_seconds=0,
            interval_seconds=0,
        )
    assert client.requests == ["GET"]


def test_management_controller_exposes_hard_delete_only():
    source = (REPO_ROOT / "src" / "supabase_preview.py").read_text(
        encoding="utf-8"
    )
    assert 'query={"force": "true"}' in source
    assert 'query={"force": "false"}' not in source
    assert "schedule_branch_deletion" not in source


@pytest.mark.parametrize("committed", [True, False])
def test_malformed_200_hard_delete_is_observed_without_second_delete(
    committed: bool,
):
    branch = preview.BranchRecord.from_payload(_branch_payload())

    class MalformedHardDeleteClient:
        def __init__(self) -> None:
            self.branches = [branch]
            self.delete_calls = 0

        def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
            assert parent_ref == PARENT_REF
            return list(self.branches)

        def delete_branch(self, project_ref: str) -> None:
            assert project_ref == BRANCH_REF
            self.delete_calls += 1
            if committed:
                self.branches = []
            raise preview.ApiError(
                "malformed successful hard-delete response",
                method="DELETE",
                path=f"/v1/branches/{project_ref}",
                status=200,
            )

    client = MalformedHardDeleteClient()
    if committed:
        preview.delete_supabase_preview(
            client,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            branch=branch,
            timeout_seconds=0.1,
            interval_seconds=0,
        )
    else:
        with pytest.raises(preview.PreviewError, match="Timed out"):
            preview.delete_supabase_preview(
                client,
                parent_ref=PARENT_REF,
                pr_number=82,
                git_branch=GIT_BRANCH,
                branch=branch,
                timeout_seconds=0.01,
                interval_seconds=0,
            )
    assert client.delete_calls == 1


def test_nonempty_preview_catalog_blocks_every_baseline_write(tmp_path: Path):
    absorbed = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [absorbed])
    supabase = FakeSupabase(
        snapshot,
        application_objects=[
            {"object_kind": "public relation", "object_name": "unexpected"}
        ],
    )
    branch = preview.BranchRecord.from_payload(_branch_payload())

    with pytest.raises(preview.PreviewError, match="not an empty application catalog"):
        preview.apply_preview_baseline(supabase, branch, snapshot)
    assert supabase.write_queries == []


def test_restore_is_one_guarded_inventory_checked_ledger_seed_transaction(
    tmp_path: Path,
):
    absorbed = _migration(
        tmp_path,
        "20260807013300",
        "baseline",
        "create table historical_body_must_not_run(id int);",
    )
    snapshot = _baseline(
        tmp_path,
        [absorbed],
        production_names={absorbed.version: "legacy_baseline_name"},
    )
    supabase = FakeSupabase(snapshot)
    branch = preview.BranchRecord.from_payload(_branch_payload())

    preview.apply_preview_baseline(supabase, branch, snapshot)

    assert len(supabase.write_queries) == 1
    batch = supabase.write_queries[0]
    assert batch.startswith("begin;\n")
    assert batch.rstrip().endswith("commit;")
    assert "preview_role_guard" in batch
    assert "current_user <> 'postgres'" in batch
    assert "preview_empty_guard" in batch
    assert "drop schema public cascade" in batch
    assert "create schema public" in batch
    assert "preview_inventory" in batch
    assert "preview_extensions" in batch
    assert 'create extension if not exists "vector"' in batch
    assert "version '0.8.2'" in batch
    assert "Preview baseline inventory mismatch: tables" in batch
    assert "insert into supabase_migrations.schema_migrations" in batch
    assert absorbed.sql not in batch
    assert "legacy_baseline_name" not in batch
    assert supabase.ledger == {absorbed.version: absorbed.name}


def test_production_ledger_drift_fails_before_branch_creation(tmp_path: Path):
    absorbed = _migration(tmp_path, "20260807013300", "baseline")
    suffix = _migration(tmp_path, "20260807013500", "trusted_suffix")
    snapshot = _baseline(tmp_path, [absorbed])
    supabase = FakeSupabase(snapshot)
    supabase.production_ledger["20260807013400"] = "manual_untracked_entry"

    with pytest.raises(preview.PreviewError, match="post-cutoff ledger"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[absorbed, suffix],
            trusted_migrations=[absorbed, suffix],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )
    assert supabase.branches == []
    assert supabase.write_queries == []


@pytest.mark.parametrize(
    ("unsafe_fields", "message"),
    [
        ({"project_ref": PARENT_REF}, "default/production"),
        ({"is_default": True}, "default/production"),
        ({"parent_project_ref": "zyxwvutsrqponmlkjihg"}, "parent_project_ref"),
        ({"git_branch": "codex/wrong-preview"}, "identity mismatch"),
    ],
)
def test_unsafe_create_response_is_never_used_as_rollback_delete_target(
    tmp_path: Path,
    unsafe_fields: Mapping[str, Any],
    message: str,
):
    absorbed = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [absorbed])

    class UnsafeCreateSupabase(FakeSupabase):
        def create_branch(
            self, parent_ref: str, *, name: str, git_branch: str
        ) -> preview.BranchRecord:
            payload_updates: dict[str, Any] = {
                "name": name,
                "git_branch": git_branch,
            }
            payload_updates.update(unsafe_fields)
            candidate = preview.BranchRecord.from_payload(
                _branch_payload(**payload_updates)
            )
            self.branches.append(candidate)
            return candidate

    supabase = UnsafeCreateSupabase(snapshot)
    with pytest.raises(preview.PreviewError, match=message):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[absorbed],
            trusted_migrations=[absorbed],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == []
    assert len(supabase.branches) == 1


def test_delete_boundary_reasserts_exact_preview_identity(tmp_path: Path):
    absorbed = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [absorbed]))
    unsafe = preview.BranchRecord.from_payload(_branch_payload(is_default=True))
    supabase.branches = [unsafe]

    with pytest.raises(preview.PreviewError, match="default/production"):
        preview.delete_supabase_preview(
            supabase,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            branch=unsafe,
            timeout_seconds=0.1,
            interval_seconds=0,
        )
    assert supabase.deleted_refs == []


def test_production_name_exception_is_narrow_and_filename_seeded(tmp_path: Path):
    absorbed = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(
        tmp_path,
        [absorbed],
        production_names={absorbed.version: "124_legacy_baseline"},
    )
    supabase = FakeSupabase(snapshot)
    preview.verify_production_ledger(
        supabase, PARENT_REF, snapshot, [absorbed], [absorbed]
    )
    supabase.production_ledger[absorbed.version] = absorbed.name
    with pytest.raises(preview.PreviewError, match="trusted baseline manifest"):
        preview.verify_production_ledger(
            supabase, PARENT_REF, snapshot, [absorbed], [absorbed]
        )


def test_ambiguous_baseline_restore_reconciles_once_without_replay(tmp_path: Path):
    absorbed = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [absorbed])

    class AmbiguousAfterCommit(FakeSupabase):
        def __init__(self, baseline: preview.PreviewBaseline) -> None:
            super().__init__(baseline)
            self.injected = False

        def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
            result = super().query(project_ref, sql, read_only=read_only)
            if (
                not read_only
                and "drop schema public cascade" in sql
                and not self.injected
            ):
                self.injected = True
                raise preview.ApiError(
                    "injected ambiguous restore",
                    method="POST",
                    path=f"/v1/projects/{BRANCH_REF}/database/query",
                )
            return result

    supabase = AmbiguousAfterCommit(snapshot)
    preview.apply_preview_baseline(
        supabase, preview.BranchRecord.from_payload(_branch_payload()), snapshot
    )
    assert len(supabase.write_queries) == 1
    assert supabase.ledger == {absorbed.version: absorbed.name}


def test_bootstrap_is_data_less_exactly_migrated_and_branch_scoped(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    pending = _migration(tmp_path, "20260807013500", "pending")
    snapshot = _baseline(tmp_path, [baseline])
    supabase = FakeSupabase(snapshot)

    class OrderedVercel(FakeVercel):
        def create_preview_env(
            self, *, key: str, value: str, git_branch: str
        ) -> None:
            assert supabase.schema_inventory_reads >= 2
            assert supabase.extension_inventory_reads >= 2
            super().create_preview_env(
                key=key, value=value, git_branch=git_branch
            )

    vercel = OrderedVercel()

    result = preview.bootstrap_preview(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        baseline=snapshot,
        migrations=[baseline, pending],
        trusted_migrations=[baseline, pending],
        source_head_sha=SOURCE_HEAD_SHA,
        replace=False,
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert result.applied_migrations == 1
    assert result.branch.project_ref == BRANCH_REF
    assert result.branch.preview_project_status == "ACTIVE_HEALTHY"
    assert supabase.scheduled_refs == []
    assert supabase.created_payloads == [
        {
            "branch_name": "pr-82-preview",
            "git_branch": GIT_BRANCH,
            "is_default": False,
            "persistent": False,
            "with_data": False,
            "desired_instance_size": "micro",
        }
    ]
    assert "drop schema public cascade" in supabase.write_queries[0]
    assert baseline.version in supabase.write_queries[0]
    assert pending.version not in supabase.write_queries[0]
    assert pending.version in supabase.write_queries[1]
    assert "insert into supabase_migrations.schema_migrations" in supabase.write_queries[0]
    assert set(row["key"] for row in vercel.rows) == set(
        preview.PREVIEW_STATIC_ENV_KEYS
    )
    assert all(row["target"] == ["preview"] for row in vercel.rows)
    assert all(row["gitBranch"] == GIT_BRANCH for row in vercel.rows)
    assert not any("service" in row["value"] for row in vercel.rows)


@pytest.mark.parametrize("malformed_mode", ["invalid-json-201", "missing-identity"])
def test_malformed_successful_supabase_create_reconciles_without_second_post(
    tmp_path: Path,
    malformed_mode: str,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class MalformedCreate(FakeSupabase):
        def __init__(self, baseline: preview.PreviewBaseline) -> None:
            super().__init__(baseline)
            self.create_calls = 0

        def create_branch(
            self, parent_ref: str, *, name: str, git_branch: str
        ) -> preview.BranchRecord:
            self.create_calls += 1
            super().create_branch(parent_ref, name=name, git_branch=git_branch)
            if malformed_mode == "invalid-json-201":
                raise preview.ApiError(
                    "invalid JSON after committed branch create",
                    method="POST",
                    path=f"/v1/projects/{parent_ref}/branches",
                    status=201,
                )
            raise preview.PreviewError(
                "Supabase branch record has no valid immutable UUID."
            )

    supabase = MalformedCreate(snapshot)
    result = preview.bootstrap_preview(
        supabase,
        FakeVercel(),
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        baseline=snapshot,
        migrations=[baseline],
        trusted_migrations=[baseline],
        source_head_sha=SOURCE_HEAD_SHA,
        replace=False,
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert result.branch.project_ref == BRANCH_REF
    assert supabase.create_calls == 1
    assert len(supabase.branches) == 1


def test_ambiguous_supabase_create_polls_bounded_eventual_consistency(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class DelayedCreateVisibility(FakeSupabase):
        def __init__(self, baseline: preview.PreviewBaseline) -> None:
            super().__init__(baseline)
            self.created = False
            self.hidden_reads = 0
            self.create_calls = 0

        def create_branch(
            self, parent_ref: str, *, name: str, git_branch: str
        ) -> preview.BranchRecord:
            self.create_calls += 1
            super().create_branch(parent_ref, name=name, git_branch=git_branch)
            self.created = True
            raise preview.ApiError(
                "ambiguous committed create",
                method="POST",
                path=f"/v1/projects/{parent_ref}/branches",
            )

        def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
            if self.created and self.hidden_reads < 1:
                self.hidden_reads += 1
                return []
            return super().list_branches(parent_ref)

    supabase = DelayedCreateVisibility(snapshot)
    result = preview.bootstrap_preview(
        supabase,
        FakeVercel(),
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        baseline=snapshot,
        migrations=[baseline],
        trusted_migrations=[baseline],
        source_head_sha=SOURCE_HEAD_SHA,
        replace=False,
        timeout_seconds=0.2,
        interval_seconds=0,
    )

    assert result.branch.project_ref == BRANCH_REF
    assert supabase.create_calls == 1
    assert supabase.hidden_reads == 1


def test_explicit_non_micro_create_is_contained_not_accepted_from_size_omitting_list(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class NonMicroCreate(FakeSupabase):
        def create_branch(
            self, parent_ref: str, *, name: str, git_branch: str
        ) -> preview.BranchRecord:
            super().create_branch(parent_ref, name=name, git_branch=git_branch)
            raise preview.PreviewCostBoundaryError(
                "Supabase branch explicitly reports a non-Micro compute size."
            )

    supabase = NonMicroCreate(snapshot)
    with pytest.raises(preview.PreviewCostBoundaryError, match="being removed"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert supabase.branches == []


def test_explicit_non_micro_list_record_remains_deletable_for_containment(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class NonMicroCreateAndList(FakeSupabase):
        def create_branch(
            self, parent_ref: str, *, name: str, git_branch: str
        ) -> preview.BranchRecord:
            created = super().create_branch(
                parent_ref, name=name, git_branch=git_branch
            )
            self.branches = [replace(created, desired_instance_size="small")]
            raise preview.PreviewCostBoundaryError(
                "Supabase branch explicitly reports a non-Micro compute size."
            )

    supabase = NonMicroCreateAndList(snapshot)
    with pytest.raises(preview.PreviewCostBoundaryError, match="being removed"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert supabase.branches == []


def test_explicit_data_bearing_create_is_contained_despite_omitting_list(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class DataBearingCreate(FakeSupabase):
        def create_branch(
            self, parent_ref: str, *, name: str, git_branch: str
        ) -> preview.BranchRecord:
            super().create_branch(parent_ref, name=name, git_branch=git_branch)
            raise preview.PreviewDataBoundaryError(
                "Supabase branch explicitly reports a data-bearing branch."
            )

    supabase = DataBearingCreate(snapshot)
    with pytest.raises(preview.PreviewDataBoundaryError, match="being removed"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert supabase.branches == []


def test_explicit_data_bearing_list_record_remains_deletable_for_containment(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class DataBearingCreateAndList(FakeSupabase):
        def create_branch(
            self, parent_ref: str, *, name: str, git_branch: str
        ) -> preview.BranchRecord:
            created = super().create_branch(
                parent_ref, name=name, git_branch=git_branch
            )
            self.branches = [replace(created, with_data=True)]
            raise preview.PreviewDataBoundaryError(
                "Supabase branch explicitly reports a data-bearing branch."
            )

    supabase = DataBearingCreateAndList(snapshot)
    with pytest.raises(preview.PreviewDataBoundaryError, match="being removed"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert supabase.branches == []


def test_bootstrap_refuses_second_controller_preview_before_create(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])
    supabase = FakeSupabase(snapshot)
    supabase.branches = [
        preview.BranchRecord.from_payload(
            _branch_payload(
                name="pr-83-preview",
                project_ref="bcdefghijklmnopqrstu",
                git_branch="codex/other-preview",
            )
        )
    ]

    with pytest.raises(preview.PreviewError, match="one branch total"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.created_payloads == []
    assert supabase.deleted_refs == []


def test_post_create_singleton_race_deletes_only_new_immutable_branch(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class ConcurrentOtherPreview(FakeSupabase):
        def create_branch(
            self, parent_ref: str, *, name: str, git_branch: str
        ) -> preview.BranchRecord:
            created = super().create_branch(
                parent_ref, name=name, git_branch=git_branch
            )
            other_created_at = preview.datetime.now(preview.timezone.utc)
            self.branches.append(
                preview.BranchRecord.from_payload(
                    _branch_payload(
                        id=str(uuid4()),
                        name="pr-83-preview",
                        project_ref="bcdefghijklmnopqrstu",
                        git_branch="codex/other-preview",
                        created_at=other_created_at.isoformat(),
                        deletion_scheduled_at=(
                            other_created_at + timedelta(hours=1)
                        ).isoformat(),
                    )
                )
            )
            return created

    supabase = ConcurrentOtherPreview(snapshot)
    with pytest.raises(preview.PreviewError, match="one exact controller-owned"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert [branch.name for branch in supabase.branches] == ["pr-83-preview"]


@pytest.mark.parametrize(
    ("boundary_update", "error_type", "message"),
    [
        (
            {"desired_instance_size": "small"},
            preview.PreviewCostBoundaryError,
            "non-Micro",
        ),
        (
            {"with_data": True},
            preview.PreviewDataBoundaryError,
            "data-bearing",
        ),
    ],
)
def test_singleton_inventory_boundary_violation_is_deleted_before_schema_writes(
    tmp_path: Path,
    boundary_update: Mapping[str, Any],
    error_type: type[preview.PreviewError],
    message: str,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class BoundaryAppearsAtSingletonInventory(FakeSupabase):
        def __init__(self, current: preview.PreviewBaseline) -> None:
            super().__init__(current)
            self.list_calls = 0

        def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
            self.list_calls += 1
            branches = super().list_branches(parent_ref)
            if self.list_calls >= 3 and branches:
                return [replace(branches[0], **boundary_update)]
            return branches

    supabase = BoundaryAppearsAtSingletonInventory(snapshot)
    vercel = FakeVercel()
    with pytest.raises(error_type, match=message):
        preview.bootstrap_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert supabase.branches == []
    assert supabase.write_queries == []
    assert vercel.rows == []


def test_bootstrap_replace_flag_is_hard_refused_before_control_plane_reads(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])
    supabase = FakeSupabase(snapshot)

    with pytest.raises(preview.PreviewError, match="replacement is disabled"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=True,
        )

    assert supabase.created_payloads == []
    assert supabase.write_queries == []


def test_bootstrap_reconciles_inherited_135_136_then_applies_exact_head_suffix(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    inherited_135 = _migration(tmp_path, "20260807013500", "trusted_135")
    inherited_136 = _migration(tmp_path, "20260808013600", "trusted_136")
    pending_138 = _migration(tmp_path, "20260810013800", "trusted_138")
    pending_139 = _migration(tmp_path, "20260815013900", "trusted_139")
    pending_140 = _migration(tmp_path, "20260816014000", "trusted_140")
    pr_141 = _migration(tmp_path, "20260816014100", "pr_141")
    snapshot = _baseline(tmp_path, [baseline])

    class InheritedSuffixDuringApply(FakeSupabase):
        def __init__(self, preview_baseline: preview.PreviewBaseline) -> None:
            super().__init__(preview_baseline)
            self.injected = False

        def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
            if (
                project_ref == BRANCH_REF
                and not read_only
                and not self.injected
                and f"values ('{inherited_135.version}'" in sql
            ):
                self.injected = True
                self.ledger[inherited_135.version] = inherited_135.name
                self.ledger[inherited_136.version] = inherited_136.name
                body = json.dumps(
                    {
                        "code": "23505",
                        "message": "duplicate key value violates unique constraint",
                    }
                )
                raise preview.ApiError(
                    "injected inherited ledger race",
                    method="POST",
                    path=f"/v1/projects/{BRANCH_REF}/database/query",
                    status=400,
                    response_body=body,
                )
            return super().query(project_ref, sql, read_only=read_only)

    supabase = InheritedSuffixDuringApply(snapshot)
    supabase.production_ledger.update(
        {
            inherited_135.version: inherited_135.name,
            inherited_136.version: inherited_136.name,
        }
    )
    migrations = [
        baseline,
        inherited_135,
        inherited_136,
        pending_138,
        pending_139,
        pending_140,
        pr_141,
    ]

    result = preview.bootstrap_preview(
        supabase,
        FakeVercel(),
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        baseline=snapshot,
        migrations=migrations,
        trusted_migrations=migrations[:-1],
        source_head_sha=SOURCE_HEAD_SHA,
        replace=False,
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert result.applied_migrations == 4
    assert supabase.ledger == {
        baseline.version: baseline.name,
        inherited_135.version: inherited_135.name,
        inherited_136.version: inherited_136.name,
        pending_138.version: pending_138.name,
        pending_139.version: pending_139.name,
        pending_140.version: pending_140.name,
        pr_141.version: pr_141.name,
    }
    writes = "\n".join(supabase.write_queries)
    assert f"values ('{inherited_136.version}'" not in writes
    assert f"values ('{pending_138.version}'" in writes
    assert f"values ('{pending_139.version}'" in writes
    assert f"values ('{pending_140.version}'" in writes
    assert f"values ('{pr_141.version}'" in writes


def test_migration_134_is_rejected_before_branch_mutation(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    forbidden_134 = _migration(
        tmp_path, "20260807013400", "source_reconciliation_enforcement"
    )
    snapshot = _baseline(tmp_path, [baseline])
    supabase = FakeSupabase(snapshot)

    with pytest.raises(preview.PreviewError, match="Non-replayable migration 134"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline, forbidden_134],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.branches == []
    assert supabase.write_queries == []


def test_pr_cannot_rewrite_unapplied_trusted_main_migration(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    trusted_138 = _migration(tmp_path, "20260810013800", "trusted_138")
    changed_138 = _migration(
        tmp_path,
        "20260810013800",
        "trusted_138",
        "create table if not exists rewritten_trusted_history(id bigint);",
    )
    snapshot = _baseline(tmp_path, [baseline])

    with pytest.raises(preview.PreviewError, match="exact trusted-main migration"):
        preview.validate_baseline_migrations(
            snapshot,
            [baseline, changed_138],
            [baseline, trusted_138],
        )


@pytest.mark.parametrize(
    ("baseline_updates", "weakened_updates", "message"),
    [
        (
            {"tables": 1, "rls_enabled": 1},
            {"rls_enabled": 0},
            "table without RLS",
        ),
        (
            {"event_triggers": 1},
            {"event_triggers": 0},
            "event_triggers",
        ),
        (
            {},
            {"non_postgres_owned_routines": 1},
            "non_postgres_owned_routines",
        ),
    ],
)
def test_post_migration_security_regression_blocks_preview_publication(
    tmp_path: Path,
    baseline_updates: Mapping[str, int],
    weakened_updates: Mapping[str, int],
    message: str,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    pending = _migration(tmp_path, "20260807013500", "weakens_security")
    snapshot = _baseline(tmp_path, [baseline])
    snapshot.schema_inventory.update(baseline_updates)

    class WeakenedAfterMigration(FakeSupabase):
        def __init__(self, baseline: preview.PreviewBaseline) -> None:
            super().__init__(baseline)
            self.inventory_reads = 0

        def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
            result = super().query(project_ref, sql, read_only=read_only)
            if read_only and sql == preview._SCHEMA_INVENTORY_QUERY:
                self.inventory_reads += 1
                if self.inventory_reads >= 2:
                    row = dict(result[0])
                    row.update(weakened_updates)
                    return [row]
            return result

    supabase = WeakenedAfterMigration(snapshot)
    vercel = FakeVercel()
    with pytest.raises(preview.PreviewError, match=message):
        preview.bootstrap_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline, pending],
            trusted_migrations=[baseline, pending],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert supabase.branches == []
    assert vercel.rows == []


def test_post_migration_extension_drift_blocks_preview_publication(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    pending = _migration(tmp_path, "20260807013500", "changes_vector")
    snapshot = _baseline(tmp_path, [baseline])

    class DriftedExtensionAfterMigration(FakeSupabase):
        def __init__(self, baseline: preview.PreviewBaseline) -> None:
            super().__init__(baseline)
            self.extension_reads = 0

        def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
            result = super().query(project_ref, sql, read_only=read_only)
            if read_only and sql == preview._EXTENSION_INVENTORY_QUERY:
                self.extension_reads += 1
                if self.extension_reads >= 2:
                    rows = [dict(row) for row in result]
                    rows[-1]["version"] = "99.0.0"
                    return rows
            return result

    supabase = DriftedExtensionAfterMigration(snapshot)
    with pytest.raises(preview.PreviewError, match="Post-migration extension"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline, pending],
            trusted_migrations=[baseline, pending],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]


def test_replaced_uuid_before_vercel_publication_is_never_routed_or_deleted(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class ReplacedBeforePublication(FakeSupabase):
        def __init__(self, baseline: preview.PreviewBaseline) -> None:
            super().__init__(baseline)
            self.injected = False

        def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
            if self.branches and not self.injected:
                self.branches = [replace(self.branches[0], id=str(uuid4()))]
                self.injected = True
            return super().list_branches(parent_ref)

    supabase = ReplacedBeforePublication(snapshot)
    vercel = FakeVercel()
    with pytest.raises(preview.PreviewError, match="replaced branch UUID"):
        preview.bootstrap_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == []
    assert len(supabase.branches) == 1
    assert vercel.rows == []


def test_persistent_flag_change_before_vercel_publication_is_never_routed(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class PersistentBeforePublication(FakeSupabase):
        def __init__(self, baseline: preview.PreviewBaseline) -> None:
            super().__init__(baseline)
            self.injected = False

        def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
            if self.branches and not self.injected:
                self.branches = [replace(self.branches[0], persistent=True)]
                self.injected = True
            return super().list_branches(parent_ref)

    supabase = PersistentBeforePublication(snapshot)
    vercel = FakeVercel()
    with pytest.raises(preview.PreviewError, match="persistent"):
        preview.bootstrap_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == []
    assert len(supabase.branches) == 1
    assert vercel.rows == []


def test_failed_bootstrap_rolls_back_exact_created_ref_and_partial_env(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    pending = _migration(tmp_path, "20260807013500", "pending")
    snapshot = _baseline(tmp_path, [baseline])
    supabase = FakeSupabase(snapshot)
    vercel = FakeVercel(fail_on_key="RICHMOND_PREVIEW_GIT_BRANCH")

    with pytest.raises(preview.PreviewError, match="injected Vercel failure"):
        preview.bootstrap_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline, pending],
            trusted_migrations=[baseline, pending],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert supabase.branches == []
    assert vercel.rows == []


def test_sync_preserves_production_duplicate_ids_and_replaces_branch_ids():
    branch = preview.BranchRecord.from_payload(_branch_payload())
    vercel = FakeVercel()
    vercel.rows = [
        {
            "id": "production-url",
            "key": "NEXT_PUBLIC_SUPABASE_URL",
            "value": f"https://{PARENT_REF}.supabase.co",
            "target": ["production"],
            "gitBranch": "",
        },
        {
            "id": "old-preview-url",
            "key": "NEXT_PUBLIC_SUPABASE_URL",
            "value": "https://oldoldoldoldoldoldol.supabase.co",
            "target": ["preview"],
            "gitBranch": GIT_BRANCH,
        },
    ]

    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )

    assert "old-preview-url" in vercel.deleted_ids
    assert "production-url" not in vercel.deleted_ids
    assert any(row["id"] == "production-url" for row in vercel.rows)
    branch_rows = [row for row in vercel.rows if row["gitBranch"] == GIT_BRANCH]
    assert set(row["key"] for row in branch_rows) == set(
        preview.PREVIEW_STATIC_ENV_KEYS
    )


def test_cleanup_deletes_only_exact_branch_scoped_preview_vars(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    vercel = FakeVercel()
    vercel.rows = [
        {
            "id": "branch-url",
            "key": "NEXT_PUBLIC_SUPABASE_URL",
            "value": f"https://{BRANCH_REF}.supabase.co",
            "target": ["preview"],
            "gitBranch": GIT_BRANCH,
        },
        {
            "id": "other-branch",
            "key": "NEXT_PUBLIC_SUPABASE_URL",
            "value": "https://zyxwvutsrqponmlkjihg.supabase.co",
            "target": ["preview"],
            "gitBranch": "codex/other-preview",
        },
        {
            "id": "production",
            "key": "NEXT_PUBLIC_SUPABASE_URL",
            "value": f"https://{PARENT_REF}.supabase.co",
            "target": ["production"],
            "gitBranch": "",
        },
    ]

    deleted_branch, deleted_env_count = preview.cleanup_preview(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert deleted_branch is True
    assert deleted_env_count == 1
    assert supabase.deleted_refs == [BRANCH_REF]
    assert {row["id"] for row in vercel.rows} == {"other-branch", "production"}


def test_cleanup_retires_persisted_deployment_before_env_and_supabase(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )
    vercel.create_preview_env(
        key=preview.PREVIEW_DEPLOYMENT_ENV_KEY,
        value="dpl_exact",
        git_branch=GIT_BRANCH,
    )

    preview.cleanup_preview(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert vercel.events[0] == "deployment:dpl_exact"
    assert all(event.startswith("env:") for event in vercel.events[1:])
    assert supabase.deleted_refs == [BRANCH_REF]


def test_stale_sweeper_is_exact_bounded_and_skips_unsafe_branches(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    stale = preview.BranchRecord.from_payload(_branch_payload())
    recent = preview.BranchRecord.from_payload(
        _branch_payload(
            id=str(uuid4()),
            name="pr-83-preview",
            project_ref="bcdefghijklmnopqrstu",
            git_branch="codex/recent-preview",
            created_at="2026-08-07T19:18:20.123456+00:00",
            deletion_scheduled_at="2026-08-07T20:18:20.123456+00:00",
        )
    )
    unsafe = replace(
        preview.BranchRecord.from_payload(
            _branch_payload(
                id=str(uuid4()),
                name="pr-84-preview",
                project_ref="cdefghijklmnopqrstuv",
                git_branch="codex/unsafe-preview",
            )
        ),
        persistent=True,
    )
    supabase.branches = [stale, recent, unsafe]

    cleaned = preview.sweep_expired_previews(
        supabase,
        FakeVercel(),
        parent_ref=PARENT_REF,
        now=stale.created_at + timedelta(minutes=91),
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert cleaned == 1
    assert supabase.deleted_refs == [BRANCH_REF]
    assert {branch.name for branch in supabase.branches} == {
        "pr-83-preview",
        "pr-84-preview",
    }


def test_expiry_cli_without_vercel_still_hard_deletes_then_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "test-token")
    for name in ("VERCEL_TOKEN", "VERCEL_PROJECT_ID", "VERCEL_ORG_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        preview, "SupabaseManagementClient", lambda token: supabase
    )

    with pytest.raises(preview.PreviewError, match=r"ACTION:.*Vercel cleanup"):
        preview._main(
            [
                "sweep-expired",
                "--parent-ref",
                PARENT_REF,
                "--max-age-seconds",
                "5400",
                "--timeout-seconds",
                "0.1",
                "--interval-seconds",
                "0",
            ]
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert supabase.branches == []


def test_stale_sweeper_bounds_attempted_scopes_even_when_git_branch_repeats(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    first = preview.BranchRecord.from_payload(_branch_payload())
    second = preview.BranchRecord.from_payload(
        _branch_payload(
            id=str(uuid4()),
            name="pr-83-preview",
            project_ref="bcdefghijklmnopqrstu",
            git_branch=GIT_BRANCH,
        )
    )

    class DisappearingSelections(FakeSupabase):
        def __init__(self, snapshot: preview.PreviewBaseline) -> None:
            super().__init__(snapshot)
            self.branches = [first, second]
            self.list_calls = 0

        def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
            self.list_calls += 1
            if self.list_calls == 1:
                return super().list_branches(parent_ref)
            assert parent_ref == PARENT_REF
            return []

    class InventoryProbe(FakeVercel):
        def __init__(self) -> None:
            super().__init__()
            self.inventory_called = False

        def list_all_preview_envs(self) -> list[Mapping[str, Any]]:
            self.inventory_called = True
            return super().list_all_preview_envs()

    supabase = DisappearingSelections(_baseline(tmp_path, [baseline]))
    vercel = InventoryProbe()
    cleaned = preview.sweep_expired_previews(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        max_branches=2,
        now=first.created_at + timedelta(minutes=91),
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert cleaned == 0
    assert supabase.list_calls == 3
    assert vercel.inventory_called is False


def test_stale_sweeper_cleans_vercel_after_native_supabase_deletion(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )
    vercel.create_preview_env(
        key=preview.PREVIEW_DEPLOYMENT_ENV_KEY,
        value="dpl_exact",
        git_branch=GIT_BRANCH,
    )

    cleaned = preview.sweep_expired_previews(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        now=branch.created_at + timedelta(minutes=91),
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert cleaned == 1
    assert supabase.deleted_refs == []
    assert vercel.retired_deployments == ["dpl_exact"]
    assert vercel.rows == []


def _fresh_replacement_vercel_rows(
    *, branch: preview.BranchRecord, git_branch: str
) -> list[dict[str, Any]]:
    replacement = FakeVercel()
    preview.sync_vercel_preview(
        replacement,
        pr_number=82,
        git_branch=git_branch,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )
    return [
        {**row, "id": f"fresh-{index}-{row['id']}"}
        for index, row in enumerate(replacement.rows, start=1)
    ]


def test_stale_sweep_skips_recreated_supabase_and_fresh_vercel_state(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    stale = preview.BranchRecord.from_payload(_branch_payload())
    observed_now = stale.created_at + timedelta(minutes=91)
    fresh = preview.BranchRecord.from_payload(
        _branch_payload(
            id=str(uuid4()),
            project_ref="bcdefghijklmnopqrstu",
            created_at=observed_now.isoformat(),
            deletion_scheduled_at=(observed_now + timedelta(hours=1)).isoformat(),
        )
    )
    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=stale,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )

    class RecreatedDuringSweep(FakeSupabase):
        def __init__(self, baseline: preview.PreviewBaseline) -> None:
            super().__init__(baseline)
            self.branches = [stale]
            self.list_calls = 0

        def list_branches(self, parent_ref: str) -> list[preview.BranchRecord]:
            self.list_calls += 1
            if self.list_calls == 2:
                self.branches = [fresh]
                vercel.rows = _fresh_replacement_vercel_rows(
                    branch=fresh, git_branch=GIT_BRANCH
                )
            return super().list_branches(parent_ref)

    supabase = RecreatedDuringSweep(_baseline(tmp_path, [baseline]))
    cleaned = preview.sweep_expired_previews(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        now=observed_now,
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert cleaned == 0
    assert supabase.deleted_refs == []
    assert supabase.branches == [fresh]
    assert vercel.deleted_ids == []
    assert vercel.retired_deployments == []
    assert all(str(row["id"]).startswith("fresh-") for row in vercel.rows)


def test_vercel_only_sweep_skips_env_replacement_after_stale_inventory(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    stale = preview.BranchRecord.from_payload(_branch_payload())
    observed_now = stale.created_at + timedelta(minutes=91)
    fresh = replace(
        stale,
        id=str(uuid4()),
        project_ref="bcdefghijklmnopqrstu",
        created_at=observed_now,
        deletion_scheduled_at=observed_now + timedelta(hours=1),
    )

    class ReplacedEnvInventory(FakeVercel):
        def __init__(self) -> None:
            super().__init__()
            self.replace_on_exact_read = False
            preview.sync_vercel_preview(
                self,
                pr_number=82,
                git_branch=GIT_BRANCH,
                branch=stale,
                public_key=_jwt("anon"),
                source_head_sha=SOURCE_HEAD_SHA,
            )

        def list_all_preview_envs(self) -> list[Mapping[str, Any]]:
            self.replace_on_exact_read = True
            return list(self.rows)

        def list_envs(self, git_branch: str) -> list[Mapping[str, Any]]:
            if self.replace_on_exact_read:
                self.replace_on_exact_read = False
                self.rows = _fresh_replacement_vercel_rows(
                    branch=fresh, git_branch=git_branch
                )
            return super().list_envs(git_branch)

    vercel = ReplacedEnvInventory()
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    cleaned = preview.sweep_expired_previews(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        now=observed_now,
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert cleaned == 0
    assert vercel.deleted_ids == []
    assert vercel.retired_deployments == []
    assert all(str(row["id"]).startswith("fresh-") for row in vercel.rows)


def test_bootstrap_never_active_hard_deletes_before_vercel(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])

    class NeverActiveSupabase(FakeSupabase):
        def create_branch(
            self, parent_ref: str, *, name: str, git_branch: str
        ) -> preview.BranchRecord:
            branch = super().create_branch(parent_ref, name=name, git_branch=git_branch)
            branch = replace(
                branch,
                preview_project_status="COMING_UP",
                deletion_scheduled_at=None,
            )
            self.branches = [branch]
            return branch

    supabase = NeverActiveSupabase(snapshot)
    vercel = FakeVercel()
    with pytest.raises(preview.PreviewError, match="ACTIVE_HEALTHY"):
        preview.bootstrap_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.scheduled_refs == []
    assert supabase.deleted_refs == [BRANCH_REF]
    assert vercel.rows == []


def test_vercel_scope_mismatch_fails_instead_of_deleting_production():
    vercel = FakeVercel()
    vercel.rows = [
        {
            "id": "dangerous",
            "key": "NEXT_PUBLIC_SUPABASE_URL",
            "value": f"https://{PARENT_REF}.supabase.co",
            "target": ["production"],
            "gitBranch": GIT_BRANCH,
        }
    ]
    with pytest.raises(preview.PreviewError, match="exact branch-scoped Preview"):
        preview.cleanup_vercel_preview(vercel, git_branch=GIT_BRANCH)
    assert vercel.deleted_ids == []


def test_cleanup_stops_supabase_compute_even_when_vercel_cleanup_fails(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    supabase.branches = [preview.BranchRecord.from_payload(_branch_payload())]
    vercel = FakeVercel()
    vercel.rows = [
        {
            "id": "wrong-scope",
            "key": "NEXT_PUBLIC_SUPABASE_URL",
            "value": f"https://{PARENT_REF}.supabase.co",
            "target": ["production"],
            "gitBranch": GIT_BRANCH,
        }
    ]

    with pytest.raises(preview.PreviewError, match="Vercel cleanup needs follow-up"):
        preview.cleanup_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            timeout_seconds=0.1,
            interval_seconds=0,
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert vercel.deleted_ids == []


def test_migration_with_explicit_transaction_is_not_partially_replayed(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    wrapped = _migration(
        tmp_path,
        "20260807013500",
        "wrapped",
        "BEGIN;\ncreate table wrapped(id int);\nCOMMIT;",
    )
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    with pytest.raises(preview.PreviewError, match="explicit transaction control"):
        preview.apply_migration(supabase, branch, wrapped)
    assert supabase.write_queries == []


@pytest.mark.parametrize(
    "sql",
    [
        "create table wrapped(id int);\nABORT;",
        "create table wrapped(id int);\nPREPARE TRANSACTION 'escape';",
        r"select '\'; COMMIT; select 'previous lexer hid this';",
    ],
)
def test_migration_atomicity_guard_rejects_hidden_transaction_control(
    tmp_path: Path, sql: str
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    wrapped = _migration(tmp_path, "20260807013500", "wrapped", sql)
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())

    with pytest.raises(preview.PreviewError, match="explicit transaction control"):
        preview.apply_migration(supabase, branch, wrapped)
    assert supabase.write_queries == []


def _write_type_verify_tree(root: Path, *, types: str) -> None:
    (root / "supabase" / "migrations").mkdir(parents=True)
    (root / "supabase" / "preview-baseline").mkdir(parents=True)
    (root / "web" / "src" / "lib").mkdir(parents=True)
    (root / "supabase" / "migrations" / "20260810013800_example.sql").write_text(
        "select 1;\n", encoding="utf-8"
    )
    (root / "supabase" / "preview-baseline" / "manifest.json").write_text(
        '{"format_version":1}\n', encoding="utf-8"
    )
    (root / "web" / "src" / "lib" / "database.types.ts").write_text(
        types, encoding="utf-8"
    )


def _type_update_metadata(**updates: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "head_sha": "2" * 40,
        "parent_shas": [SOURCE_HEAD_SHA],
        "files": [
            {
                "path": "web/src/lib/database.types.ts",
                "status": "modified",
                "previous_path": None,
            }
        ],
    }
    metadata.update(updates)
    return metadata


def test_type_update_requires_direct_child_single_regular_bounded_file(
    tmp_path: Path,
):
    source = tmp_path / "source"
    head = tmp_path / "head"
    _write_type_verify_tree(source, types="export type Old = true;\n")
    _write_type_verify_tree(head, types="export type New = true;\n")

    result = preview.verify_type_update_inputs(
        metadata=_type_update_metadata(),
        source_root=source,
        head_root=head,
        source_head_sha=SOURCE_HEAD_SHA,
        head_sha="2" * 40,
    )
    assert result == (head / preview.TYPE_FILE_RELATIVE_PATH).resolve()


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        (_type_update_metadata(parent_shas=["3" * 40]), "direct child"),
        (_type_update_metadata(parent_shas=[SOURCE_HEAD_SHA, "3" * 40]), "one-parent"),
        (
            _type_update_metadata(
                files=[
                    {
                        "path": "web/src/lib/database.types.ts",
                        "status": "modified",
                        "previous_path": None,
                    },
                    {
                        "path": "README.md",
                        "status": "modified",
                        "previous_path": None,
                    },
                ]
            ),
            "exactly one changed file",
        ),
        (
            _type_update_metadata(
                files=[
                    {
                        "path": "../web/src/lib/database.types.ts",
                        "status": "modified",
                        "previous_path": None,
                    }
                ]
            ),
            "modify only",
        ),
    ],
)
def test_type_update_rejects_graph_and_path_variants(
    tmp_path: Path, metadata: dict[str, Any], message: str
):
    source = tmp_path / "source"
    head = tmp_path / "head"
    _write_type_verify_tree(source, types="old\n")
    _write_type_verify_tree(head, types="new\n")
    with pytest.raises(preview.PreviewError, match=message):
        preview.verify_type_update_inputs(
            metadata=metadata,
            source_root=source,
            head_root=head,
            source_head_sha=SOURCE_HEAD_SHA,
            head_sha="2" * 40,
        )


@pytest.mark.parametrize("relative", preview.IMMUTABLE_TYPE_VERIFY_DIRECTORIES)
def test_type_update_rejects_changed_migration_or_baseline_inventory(
    tmp_path: Path, relative: Path
):
    source = tmp_path / "source"
    head = tmp_path / "head"
    _write_type_verify_tree(source, types="old\n")
    _write_type_verify_tree(head, types="new\n")
    changed = next(path for path in (head / relative).rglob("*") if path.is_file())
    changed.write_text("drift\n", encoding="utf-8")
    with pytest.raises(preview.PreviewError, match="path/blob inventories differ"):
        preview.verify_type_update_inputs(
            metadata=_type_update_metadata(),
            source_root=source,
            head_root=head,
            source_head_sha=SOURCE_HEAD_SHA,
            head_sha="2" * 40,
        )


def test_type_update_rejects_symlink_and_oversized_types(tmp_path: Path):
    source = tmp_path / "source"
    head = tmp_path / "head"
    _write_type_verify_tree(source, types="old\n")
    _write_type_verify_tree(head, types="new\n")
    types_path = head / preview.TYPE_FILE_RELATIVE_PATH
    outside = tmp_path / "outside.ts"
    outside.write_text("escape\n", encoding="utf-8")
    types_path.unlink()
    try:
        types_path.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")
    with pytest.raises(preview.PreviewError, match="symlink/reparse-point"):
        preview.verify_type_update_inputs(
            metadata=_type_update_metadata(),
            source_root=source,
            head_root=head,
            source_head_sha=SOURCE_HEAD_SHA,
            head_sha="2" * 40,
        )

    types_path.unlink()
    types_path.write_bytes(b"x" * (preview.MAX_DATABASE_TYPES_BYTES + 1))
    with pytest.raises(preview.PreviewError, match="exceeds"):
        preview.verify_type_update_inputs(
            metadata=_type_update_metadata(),
            source_root=source,
            head_root=head,
            source_head_sha=SOURCE_HEAD_SHA,
            head_sha="2" * 40,
        )


def test_retained_preview_requires_exact_h0_env_identity_and_bounded_age(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )

    observed = preview.verify_retained_preview(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
        now=branch.created_at + timedelta(minutes=30),
    )
    assert observed.id == branch.id
    assert supabase.write_queries == []

    marker = next(
        row for row in vercel.rows
        if row["key"] == "RICHMOND_PREVIEW_SOURCE_HEAD_SHA"
    )
    marker["value"] = "3" * 40
    with pytest.raises(preview.PreviewError, match="identity mismatch"):
        preview.verify_retained_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            now=branch.created_at + timedelta(minutes=30),
        )
    marker["value"] = SOURCE_HEAD_SHA
    with pytest.raises(preview.PreviewError, match="bounded eligibility window"):
        preview.verify_retained_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            now=branch.created_at
            + timedelta(seconds=preview.PREVIEW_VERIFY_MAX_AGE_SECONDS),
        )
    supabase.branches = [
        replace(branch, preview_project_status="COMING_UP")
    ]
    with pytest.raises(preview.PreviewError, match="not ACTIVE_HEALTHY"):
        preview.verify_retained_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            now=branch.created_at + timedelta(minutes=30),
        )
    supabase.branches = [replace(branch, with_data=True)]
    with pytest.raises(preview.PreviewDataBoundaryError, match="data-bearing"):
        preview.verify_retained_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            now=branch.created_at + timedelta(minutes=30),
        )


def test_retained_preview_requires_singleton_before_rebind_or_deploy(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    other = preview.BranchRecord.from_payload(
        _branch_payload(
            id=str(uuid4()),
            name="pr-83-preview",
            project_ref="bcdefghijklmnopqrstu",
            git_branch="codex/other-preview",
        )
    )
    supabase.branches = [branch, other]
    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )

    with pytest.raises(preview.PreviewError, match="sole exact controller-owned"):
        preview.verify_retained_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            now=branch.created_at + timedelta(minutes=30),
        )

    assert vercel.deployments == []
    assert supabase.write_queries == []


def test_authorize_preview_deployment_requests_exact_h0_without_rebind(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )

    result = preview.authorize_preview_deployment(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
        approved_head_sha=SOURCE_HEAD_SHA,
        git_owner="pjfront",
        git_repo="richmond-common",
        verified_type_only_rebind=False,
        now=branch.created_at + timedelta(minutes=30),
    )

    assert result.deployment.source_head_sha == SOURCE_HEAD_SHA
    assert vercel.deployments == [
        {
            "git_owner": "pjfront",
            "git_repo": "richmond-common",
            "git_branch": GIT_BRANCH,
            "source_head_sha": SOURCE_HEAD_SHA,
        }
    ]
    marker = next(
        row
        for row in vercel.rows
        if row["key"] == "RICHMOND_PREVIEW_SOURCE_HEAD_SHA"
    )
    assert marker["value"] == SOURCE_HEAD_SHA


def test_authorize_preview_deployment_rebinds_only_explicit_verified_h1(
    tmp_path: Path,
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )
    h1_sha = "2" * 40

    with pytest.raises(preview.PreviewError, match="verified-type-only rebind"):
        preview.authorize_preview_deployment(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            approved_head_sha=h1_sha,
            git_owner="pjfront",
            git_repo="richmond-common",
            verified_type_only_rebind=False,
            now=branch.created_at + timedelta(minutes=30),
        )
    assert vercel.deployments == []

    result = preview.authorize_preview_deployment(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        source_head_sha=SOURCE_HEAD_SHA,
        approved_head_sha=h1_sha,
        git_owner="pjfront",
        git_repo="richmond-common",
        verified_type_only_rebind=True,
        now=branch.created_at + timedelta(minutes=30),
    )

    assert result.deployment.source_head_sha == h1_sha
    branch_rows = [row for row in vercel.rows if row["gitBranch"] == GIT_BRANCH]
    assert set(row["key"] for row in branch_rows) == set(
        preview.PREVIEW_ALLOWED_ENV_KEYS
    )
    marker = next(
        row
        for row in branch_rows
        if row["key"] == "RICHMOND_PREVIEW_SOURCE_HEAD_SHA"
    )
    assert marker["value"] == h1_sha
    assert vercel.deployments[-1]["source_head_sha"] == h1_sha


def test_h1_authorization_cannot_expand_into_watchdog_window(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )
    original_rows = [dict(row) for row in vercel.rows]

    with pytest.raises(preview.PreviewError, match="70-minute watchdog-safe"):
        preview.authorize_preview_deployment(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            approved_head_sha="2" * 40,
            git_owner="pjfront",
            git_repo="richmond-common",
            verified_type_only_rebind=True,
            max_age_seconds=preview.MAX_PREVIEW_LIFETIME_SECONDS,
            now=branch.created_at + timedelta(minutes=30),
        )

    assert vercel.rows == original_rows
    assert vercel.deployments == []
    assert supabase.deleted_refs == []


def test_retained_preview_rejects_branch_or_vercel_set_identity_drift(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [replace(branch, persistent=True)]
    with pytest.raises(preview.PreviewError, match="persistent"):
        preview.verify_retained_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            now=branch.created_at + timedelta(minutes=1),
        )

    supabase.branches = [branch]
    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )
    vercel.rows.append(
        {
            "id": "unexpected",
            "key": "UNEXPECTED",
            "value": "drift",
            "target": ["preview"],
            "gitBranch": GIT_BRANCH,
        }
    )
    with pytest.raises(preview.PreviewError, match="unexpected variable"):
        preview.verify_retained_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            source_head_sha=SOURCE_HEAD_SHA,
            now=branch.created_at + timedelta(minutes=1),
        )


def test_bootstrap_refuses_existing_branch_without_create_or_replace(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [baseline])
    supabase = FakeSupabase(snapshot)
    supabase.branches = [preview.BranchRecord.from_payload(_branch_payload())]
    with pytest.raises(preview.PreviewError, match="already exists"):
        preview.bootstrap_preview(
            supabase,
            FakeVercel(),
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            baseline=snapshot,
            migrations=[baseline],
            trusted_migrations=[baseline],
            source_head_sha=SOURCE_HEAD_SHA,
            replace=False,
            timeout_seconds=0.1,
            interval_seconds=0,
        )
    assert supabase.created_payloads == []
    assert supabase.deleted_refs == []
    assert supabase.write_queries == []


def test_schema_state_cli_preserves_loaded_baseline_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    absorbed = _migration(tmp_path, "20260807013300", "baseline")
    snapshot = _baseline(tmp_path, [absorbed])
    seen: dict[str, Any] = {}

    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(preview, "load_preview_baseline", lambda *a, **k: snapshot)
    monkeypatch.setattr(preview, "load_migrations", lambda *a, **k: [absorbed])
    monkeypatch.setattr(preview, "validate_baseline_migrations", lambda *a, **k: [])
    monkeypatch.setattr(preview, "SupabaseManagementClient", lambda token: object())

    def verify(client: Any, parent: str, baseline: Any, trusted: Any, pr: Any):
        seen["baseline"] = baseline
        return preview.ProductionLedgerState(())

    monkeypatch.setattr(preview, "verify_production_ledger", verify)
    result = preview._main(
        [
            "schema-state",
            "--parent-ref", PARENT_REF,
            "--migrations-dir", str(tmp_path),
            "--migrations-root", str(tmp_path),
            "--baseline-dir", str(tmp_path),
        ]
    )
    assert result == 0
    assert seen["baseline"] is snapshot


def test_typegen_retries_only_exact_inactive_response_then_writes(tmp_path: Path):
    responses = [
        preview.subprocess.CompletedProcess(
            [], 1, b"", preview.TYPEGEN_ACTIVE_TRANSIENT.encode("utf-8")
        ),
        preview.subprocess.CompletedProcess([], 0, b"export type Database = {}\n", b""),
    ]
    calls: list[dict[str, Any]] = []
    clock = [0.0]

    def runner(command: list[str], **kwargs: Any) -> Any:
        calls.append({"command": command, **kwargs})
        return responses.pop(0)

    output = tmp_path / "database.types.ts"
    attempts = preview.generate_supabase_types_with_retry(
        BRANCH_REF,
        output,
        max_wait_seconds=10,
        retry_interval_seconds=2,
        runner=runner,
        monotonic=lambda: clock[0],
        sleeper=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    assert attempts == 2
    assert output.read_bytes() == b"export type Database = {}\n"
    assert len(calls) == 2
    assert all(call["timeout"] <= 10 for call in calls)
    assert all(call["env"]["NO_COLOR"] == "1" for call in calls)


@pytest.mark.parametrize(
    "stderr",
    [
        b"request returned 401 Unauthorized",
        b"request returned 403 Forbidden",
        b"prefix: " + preview.TYPEGEN_ACTIVE_TRANSIENT.encode("utf-8"),
        b"failed to connect to the Supabase API",
    ],
)
def test_typegen_auth_and_unrelated_errors_fail_without_retry(
    tmp_path: Path, stderr: bytes
):
    calls = 0

    def runner(command: list[str], **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return preview.subprocess.CompletedProcess(command, 1, b"", stderr)

    output = tmp_path / "database.types.ts"
    with pytest.raises(preview.PreviewError, match="without the exact retryable"):
        preview.generate_supabase_types_with_retry(
            BRANCH_REF,
            output,
            runner=runner,
        )
    assert calls == 1
    assert not output.exists()


def test_typegen_exact_transient_stops_at_bounded_deadline(tmp_path: Path):
    clock = [0.0]
    calls = 0

    def runner(command: list[str], **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return preview.subprocess.CompletedProcess(
            command,
            1,
            b"",
            preview.TYPEGEN_ACTIVE_TRANSIENT.encode("utf-8"),
        )

    with pytest.raises(preview.PreviewError, match="bounded retry window"):
        preview.generate_supabase_types_with_retry(
            BRANCH_REF,
            tmp_path / "database.types.ts",
            max_wait_seconds=1,
            retry_interval_seconds=0.4,
            runner=runner,
            monotonic=lambda: clock[0],
            sleeper=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
        )
    assert clock[0] == pytest.approx(1.0)
    assert calls == 3


def test_watchdog_snapshots_and_cleans_only_exact_run_branch(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(
        _branch_payload(deletion_scheduled_at=None)
    )
    supabase.branches = [branch]
    started = branch.created_at - timedelta(minutes=1)
    completed = branch.created_at + timedelta(minutes=2)

    snapshot = preview.snapshot_watchdog_preview(
        supabase,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        bootstrap_started_at=started,
        bootstrap_completed_at=completed,
    )
    assert snapshot == branch

    vercel = FakeVercel()
    preview.sync_vercel_preview(
        vercel,
        pr_number=82,
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
        source_head_sha=SOURCE_HEAD_SHA,
    )
    deleted, env_count = preview.cleanup_watchdog_preview(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        snapshot_branch_id=branch.id,
        snapshot_project_ref=branch.project_ref,
        snapshot_created_at=branch.created_at,
        now=branch.created_at
        + timedelta(seconds=preview.PREVIEW_WATCHDOG_AGE_SECONDS),
        timeout_seconds=0.1,
        interval_seconds=0,
    )
    assert deleted is True
    assert env_count == len(preview.PREVIEW_STATIC_ENV_KEYS)
    assert supabase.deleted_refs == [BRANCH_REF]


def test_watchdog_cli_without_vercel_still_hard_deletes_then_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "test-token")
    for name in ("VERCEL_TOKEN", "VERCEL_PROJECT_ID", "VERCEL_ORG_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        preview, "SupabaseManagementClient", lambda token: supabase
    )

    with pytest.raises(preview.PreviewError, match="Vercel cleanup needs follow-up"):
        preview._main(
            [
                "watchdog-cleanup",
                "--parent-ref",
                PARENT_REF,
                "--pr-number",
                "82",
                "--git-branch",
                GIT_BRANCH,
                "--snapshot-branch-id",
                branch.id,
                "--snapshot-project-ref",
                branch.project_ref,
                "--snapshot-created-at",
                branch.created_at.isoformat(),
                "--timeout-seconds",
                "0.1",
                "--interval-seconds",
                "0",
            ]
        )

    assert supabase.deleted_refs == [BRANCH_REF]
    assert supabase.branches == []


def test_watchdog_refuses_early_cleanup(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    vercel = FakeVercel()

    with pytest.raises(preview.PreviewError, match="before the 110-minute"):
        preview.cleanup_watchdog_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            snapshot_branch_id=branch.id,
            snapshot_project_ref=branch.project_ref,
            snapshot_created_at=branch.created_at,
            now=branch.created_at + timedelta(minutes=109),
        )
    assert supabase.deleted_refs == []
    assert vercel.deleted_ids == []


@pytest.mark.parametrize("replacement", [False, True])
def test_watchdog_disappearance_or_replacement_is_safe_noop(
    tmp_path: Path, replacement: bool
):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]
    vercel = FakeVercel()
    if replacement:
        supabase.branches = [replace(branch, id=str(uuid4()))]
    else:
        supabase.branches = []

    result = preview.cleanup_watchdog_preview(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        snapshot_branch_id=branch.id,
        snapshot_project_ref=branch.project_ref,
        snapshot_created_at=branch.created_at,
        now=branch.created_at
        + timedelta(seconds=preview.PREVIEW_WATCHDOG_AGE_SECONDS),
    )
    assert result == (False, 0)
    assert supabase.deleted_refs == []
    assert vercel.deleted_ids == []


def test_watchdog_snapshot_rejects_branch_outside_exact_run_window(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(_baseline(tmp_path, [baseline]))
    branch = preview.BranchRecord.from_payload(_branch_payload())
    supabase.branches = [branch]

    with pytest.raises(preview.PreviewError, match="outside the exact bootstrap run"):
        preview.snapshot_watchdog_preview(
            supabase,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            bootstrap_started_at=branch.created_at - timedelta(minutes=3),
            bootstrap_completed_at=branch.created_at - timedelta(minutes=1),
        )


def test_workflow_keeps_executable_code_trusted_and_secret_surface_narrow():
    text = WORKFLOW.read_text(encoding="utf-8")
    trusted_checkout = text.index("name: Check out trusted lifecycle controller")
    inert_checkout = text.index("name: Check out exact current PR head as inert input")
    lifecycle = text.index("python src/supabase_preview.py bootstrap")
    assert trusted_checkout < inert_checkout < lifecycle
    assert "ref: main" in text
    assert "persist-credentials: false" in text
    assert "types: [closed]" in text
    assert "pull_request_target" in text
    assert "preview-head/supabase/migrations" in text
    assert text.count("--migrations-root preview-head") == 2
    assert text.count("--baseline-dir supabase/preview-baseline") == 2
    assert "--baseline-dir preview-head/" not in text
    assert "working-directory: preview-head" not in text
    assert "DATABASE_URL:" not in text
    assert "SUPABASE_SERVICE" not in text
    assert "with_data" not in text  # enforced inside the trusted controller
    assert "statuses: write" in text
    assert "steps.pr.outputs.head_sha" in text
    assert text.count("python src/supabase_preview.py generate-types") == 2
    assert text.count("--max-wait-seconds 120") == 2
    assert "preview-head/web/src/lib/database.types.ts" in text
    assert "must be a regular non-symlink file" in text
    assert "actions/upload-artifact@v4" in text
    assert "runner.temp" in text
    assert "npm run" not in text
    assert "verify-types" in text
    assert "github.event.client_payload.source_head_sha" in text
    assert "bootstrap and verify-types require a full lowercase H0 SHA" in text
    assert "verify-type-update" in text
    assert "verify-retained" in text
    assert "RICHMOND_PREVIEW_SOURCE_HEAD_SHA" not in text  # controller owns values
    assert "timeout-minutes: 35" in text
    assert text.count("--max-age-seconds 4200") == 2
    assert text.count("--max-age-seconds 7200") == 1
    assert "--replace" not in text
    assert text.count("python src/supabase_preview.py bootstrap") == 1
    assert text.count("python src/supabase_preview.py authorize-deployment") == 2
    assert "--approved-head-sha \"$APPROVED_HEAD_SHA\"" in text
    assert "GIT_OWNER: ${{ github.repository_owner }}" in text
    assert "GIT_REPO: ${{ github.event.repository.name }}" in text
    assert "commit.parents.map(parent => parent.sha)" in text
    assert "comparison.files" in text
    assert "steps.preview_types.outputs.type_mismatch != 'true'" in text
    assert "steps.preview_types_artifact.outcome != 'success'" in text
    assert "steps.verify_types.outcome != 'success'" in text
    assert "sha: process.env.HEAD_SHA" in text
    assert "group: supabase-preview-control-plane" in text
    assert "queue: max" in text
    assert "cancel-in-progress: false" in text
    assert "github.event_name == 'pull_request_target'" in text
    assert "github.event_name == 'repository_dispatch'" in text
    assert "github.event.action == 'supabase-preview-lifecycle'" in text
    assert "types: [supabase-preview-lifecycle]" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "  workflow_dispatch:" not in text

    with pytest.raises(SystemExit):
        preview._parser().parse_args(
            [
                "bootstrap",
                "--parent-ref", PARENT_REF,
                "--pr-number", "82",
                "--git-branch", GIT_BRANCH,
                "--migrations-dir", "supabase/migrations",
                "--migrations-root", ".",
                "--baseline-dir", "supabase/preview-baseline",
                "--source-head-sha", SOURCE_HEAD_SHA,
                "--replace",
            ]
        )


def test_workflow_retention_cleanup_and_status_conditions_fail_closed():
    text = WORKFLOW.read_text(encoding="utf-8")
    first_cleanup = text.index("name: Remove failed bootstrap except retained type mismatch")
    h0_status = text.index("name: Bind bootstrap type result to exact H0")
    h0_status_cleanup = text.index(
        "name: Remove otherwise-retainable bootstrap if H0 status binding fails"
    )
    h0_deployment = text.index(
        "name: Request trusted exact H0 Vercel Preview deployment"
    )
    h0_deployment_cleanup = text.index(
        "name: Remove H0 Preview after trusted deployment request failure"
    )
    verify_cleanup = text.index("name: Remove retained Preview after any verify failure")
    h1_status = text.index("name: Bind verify-types result to exact H1")
    h1_status_cleanup = text.index(
        "name: Remove retained Preview if successful H1 status binding fails"
    )
    h1_deployment = text.index(
        "name: Rebind and request trusted exact H1 Vercel Preview deployment"
    )
    h1_deployment_cleanup = text.index(
        "name: Remove H1 Preview after trusted deployment request failure"
    )
    assert (
        first_cleanup
        < h0_status
        < h0_status_cleanup
        < h0_deployment
        < h0_deployment_cleanup
    )
    assert (
        verify_cleanup
        < h1_status
        < h1_status_cleanup
        < h1_deployment
        < h1_deployment_cleanup
    )

    bootstrap_guard = text[first_cleanup:h0_status]
    assert "steps.preview_types.outputs.type_mismatch != 'true'" in bootstrap_guard
    assert "steps.preview_types_artifact.outcome != 'success'" in bootstrap_guard
    assert "steps.preview_types.outcome != 'success'" in bootstrap_guard
    assert "python src/supabase_preview.py cleanup" in bootstrap_guard

    artifact_guard = text[
        text.index("name: Upload SHA-bound generated types"):first_cleanup
    ]
    assert "steps.preview_types.outcome == 'success'" in artifact_guard
    assert "steps.preview_types.outputs.type_mismatch == 'true'" in artifact_guard

    h0_status_failure_guard = text[h0_status_cleanup:h0_deployment]
    assert "steps.preview_types_artifact.outcome == 'success'" in h0_status_failure_guard
    assert "steps.preview_types.outputs.type_mismatch == 'true'" in h0_status_failure_guard
    assert "steps.bootstrap_status.outcome != 'success'" in h0_status_failure_guard
    assert "python src/supabase_preview.py cleanup" in h0_status_failure_guard

    h0_deployment_guard = text[h0_deployment:h0_deployment_cleanup]
    assert "steps.preview_types.outcome == 'success'" in h0_deployment_guard
    assert "steps.bootstrap_status.outcome == 'success'" in h0_deployment_guard
    assert "--verified-type-only-rebind" not in h0_deployment_guard
    assert "--source-head-sha \"$SOURCE_HEAD_SHA\"" in h0_deployment_guard
    assert "--approved-head-sha \"$APPROVED_HEAD_SHA\"" in h0_deployment_guard
    assert "--max-age-seconds 7200" in h0_deployment_guard

    h0_deployment_failure_guard = text[h0_deployment_cleanup:verify_cleanup]
    assert "steps.h0_deployment.outcome != 'success'" in h0_deployment_failure_guard
    assert "python src/supabase_preview.py cleanup" in h0_deployment_failure_guard

    verify_failure_guard = text[verify_cleanup:h1_status]
    assert "steps.verify_types.outcome != 'success'" in verify_failure_guard
    assert "python src/supabase_preview.py cleanup" in verify_failure_guard

    h1_status_failure_guard = text[h1_status_cleanup:h1_deployment]
    assert "steps.verify_types.outcome == 'success'" in h1_status_failure_guard
    assert "steps.verify_status.outcome != 'success'" in h1_status_failure_guard
    assert "python src/supabase_preview.py cleanup" in h1_status_failure_guard

    h1_deployment_guard = text[h1_deployment:h1_deployment_cleanup]
    assert "steps.verify_types.outcome == 'success'" in h1_deployment_guard
    assert "steps.verify_status.outcome == 'success'" in h1_deployment_guard
    assert "--verified-type-only-rebind" in h1_deployment_guard
    assert "--source-head-sha \"$SOURCE_HEAD_SHA\"" in h1_deployment_guard
    assert "--approved-head-sha \"$APPROVED_HEAD_SHA\"" in h1_deployment_guard
    assert "--max-age-seconds 4200" in h1_deployment_guard

    h1_deployment_failure_guard = text[h1_deployment_cleanup:]
    assert "steps.h1_deployment.outcome != 'success'" in h1_deployment_failure_guard
    assert "python src/supabase_preview.py cleanup" in h1_deployment_failure_guard


def test_workflow_malformed_verify_h0_remains_cleanup_eligible():
    text = WORKFLOW.read_text(encoding="utf-8")
    identity = text[
        text.index("name: Resolve and validate pull request identity"):
        text.index("name: Check out exact current PR head as inert input")
    ]
    open_pr_rejection = identity.index(
        "core.setFailed(`Cannot ${operation} closed PR #${prNumber}`)"
    )
    cleanup_safe_outputs = [
        identity.index("core.setOutput('number', String(prNumber))"),
        identity.index("core.setOutput('head_ref', pr.head.ref)"),
        identity.index("core.setOutput('head_sha', pr.head.sha)"),
    ]
    malformed_h0_rejection = identity.index(
        "bootstrap and verify-types require a full lowercase H0 SHA"
    )
    assert open_pr_rejection < min(cleanup_safe_outputs)
    assert max(cleanup_safe_outputs) < malformed_h0_rejection

    verify_cleanup = text[
        text.index("name: Remove retained Preview after any verify failure"):
        text.index("name: Bind verify-types result to exact H1")
    ]
    assert "always() && env.PREVIEW_OPERATION == 'verify-types'" in verify_cleanup
    assert "steps.pr.outputs.head_ref != ''" in verify_cleanup
    assert "PREVIEW_PR_NUMBER: ${{ steps.pr.outputs.number }}" in verify_cleanup
    assert "PREVIEW_GIT_BRANCH: ${{ steps.pr.outputs.head_ref }}" in verify_cleanup
    assert "python src/supabase_preview.py cleanup" in verify_cleanup


def test_expiry_workflow_is_trusted_bounded_and_actionable():
    text = EXPIRY_WORKFLOW.read_text(encoding="utf-8")
    assert "cron: '*/5 * * * *'" in text
    assert "ref: main" in text
    assert "persist-credentials: false" in text
    assert "permissions:\n  contents: read" in text
    assert "python src/supabase_preview.py sweep-expired" in text
    assert "--max-age-seconds 5400" in text
    assert "--max-branches 10" in text
    assert "group: supabase-preview-control-plane" in text
    assert "queue: max" in text
    assert "cancel-in-progress: false" in text
    assert "github.event_name == 'schedule'" in text
    assert "github.event_name == 'repository_dispatch'" in text
    assert "github.event.action == 'supabase-preview-expiry'" in text
    assert "types: [supabase-preview-expiry]" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "  workflow_dispatch:" not in text
    assert "ACTION:" in text
    assert "pull_request" not in text


def test_watchdog_workflow_is_trusted_independent_bounded_and_actionable():
    text = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")
    identity = text.index("name: Validate exact completed bootstrap run and PR identity")
    trusted_checkout = text.index("name: Check out trusted watchdog controller")
    first_supabase_secret = text.index("SUPABASE_ACCESS_TOKEN")
    assert "workflow_run:" in text
    assert 'workflows: ["Supabase Preview"]' in text
    assert "types: [completed]" in text
    assert "action=bootstrap" in text
    assert "getWorkflowRun" in text
    assert "run.name !== title" in text
    assert "run.name !== 'Supabase Preview'" not in text
    assert "run.event !== 'repository_dispatch'" in text
    assert "run.head_branch !== 'main'" in text
    assert "supabase-preview\\.yml" in text
    assert identity < trusted_checkout < first_supabase_secret
    assert "ref: main" in text
    assert "persist-credentials: false" in text
    assert "actions: read" in text
    assert "statuses: write" not in text
    assert "\nconcurrency:" not in text
    assert "timeout-minutes: 125" in text
    assert "timeout-minutes: 112" in text
    assert "created_epoch + 6601" in text
    assert 'if [ "$delay" -gt 6601 ]' in text
    assert "GNU date truncates fractional seconds" in text
    assert 'sleep "$delay"' in text
    assert "python src/supabase_preview.py watchdog-snapshot" in text
    assert "python src/supabase_preview.py watchdog-cleanup" in text
    assert "steps.snapshot.outputs.branch_id" in text
    assert "steps.snapshot.outputs.project_ref" in text
    assert "steps.snapshot.outputs.created_at" in text
    assert "ACTION:" in text


def test_watchdog_accepts_real_dynamic_workflow_run_name_semantics():
    run = json.loads(WATCHDOG_REAL_RUN_FIXTURE.read_text(encoding="utf-8"))
    title = "Supabase Preview | action=bootstrap | pr=136"

    # Sanitized from GitHub REST run 32793118575. GitHub replaces the static
    # workflow name with the dynamic run-name in both fields.
    assert run["id"] == 32793118575
    assert run["name"] == title
    assert run["display_title"] == title
    assert run["name"] != "Supabase Preview"
    assert re.fullmatch(
        r"Supabase Preview \| action=bootstrap \| pr=([1-9][0-9]*)",
        title,
    ).group(1) == "136"
    assert run["event"] == "repository_dispatch"
    assert run["path"] == ".github/workflows/supabase-preview.yml"
    assert run["head_branch"] == "main"
    assert run["repository"]["full_name"] == "pjfront/richmond-common"
    assert run["head_repository"]["full_name"] == "pjfront/richmond-common"
    assert re.fullmatch(r"[a-f0-9]{40}", run["head_sha"])
    assert preview.parse_api_timestamp(run["run_started_at"]) < (
        preview.parse_api_timestamp(run["updated_at"])
    )


def test_schema_drift_uses_trusted_main_and_exact_head_status_gate():
    text = SCHEMA_WORKFLOW.read_text(encoding="utf-8")
    trusted_checkout = text.index("name: Check out trusted schema controller")
    inert_checkout = text.index("name: Check out exact PR head as inert input")
    ledger_gate = text.index("python src/supabase_preview.py schema-state")
    assert trusted_checkout < inert_checkout < ledger_gate
    assert "pull_request_target" in text
    assert "ref: main" in text
    assert "persist-credentials: false" in text
    assert "statuses: write" in text
    assert "steps.pr.outputs.head_sha" in text
    assert "preview-head/supabase/migrations" in text
    assert "preview-head/web/src/lib/database.types.ts" in text
    assert "must be a regular non-symlink file" in text
    assert "supabase gen types typescript" in text
    assert "npm run" not in text
    assert "DATABASE_URL" not in text


def test_vercel_controller_has_no_name_only_upsert_path():
    source = (REPO_ROOT / "src" / "supabase_preview.py").read_text(encoding="utf-8")
    assert '"upsert": "true"' not in source
    assert "create_preview_env" in source
    assert "delete_env(env_id)" in source
