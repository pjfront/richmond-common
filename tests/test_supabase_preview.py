"""Security and lifecycle regression tests for Supabase Preview branches."""
from __future__ import annotations

import base64
from datetime import timezone
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
REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "supabase-preview.yml"


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
    }
    payload.update(updates)
    return payload


def _migration(
    tmp_path: Path,
    version: str = "20260807013400",
    name: str = "example_preview_change",
    sql: str = "create table if not exists example_preview(id bigint primary key);",
) -> preview.Migration:
    path = tmp_path / f"{version}_{name}.sql"
    path.write_text(sql, encoding="utf-8")
    return preview.Migration(version, name, path, sql)


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
    loaded = preview.load_migrations(good)
    assert loaded[0].version == "20260807013400"

    alias = tmp_path / "alias"
    alias.mkdir()
    (alias / "134_example_preview_change.sql").write_text("select 1;", encoding="utf-8")
    with pytest.raises(preview.PreviewError, match="14-digit UTC timestamp"):
        preview.load_migrations(alias)

    impossible = tmp_path / "impossible"
    impossible.mkdir()
    (impossible / "20261399019999_bad_time.sql").write_text("select 1;", encoding="utf-8")
    with pytest.raises(preview.PreviewError, match="invalid UTC timestamp"):
        preview.load_migrations(impossible)


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


class FakeSupabase:
    def __init__(self, baseline: preview.Migration) -> None:
        self.branches: list[preview.BranchRecord] = []
        self.ledger: dict[str, str] = {baseline.version: baseline.name}
        self.created_payloads: list[dict[str, Any]] = []
        self.deleted_refs: list[str] = []
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
            }
        )
        branch = preview.BranchRecord.from_payload(
            _branch_payload(name=name, git_branch=git_branch)
        )
        self.branches.append(branch)
        return branch

    def delete_branch(self, project_ref: str) -> None:
        self.deleted_refs.append(project_ref)
        self.branches = [b for b in self.branches if b.project_ref != project_ref]

    def query(self, project_ref: str, sql: str, *, read_only: bool) -> Any:
        assert project_ref == BRANCH_REF
        if sql == "select 1 as ok":
            return [{"ok": 1}]
        if sql == preview._LEDGER_QUERY:
            return [
                {"version": version, "name": name}
                for version, name in sorted(self.ledger.items())
            ]
        assert read_only is False
        self.write_queries.append(sql)
        match = re.search(
            r"values \('(?P<version>\d{14})', '(?P<name>[a-z0-9_]+)'\)", sql
        )
        assert match is not None
        self.ledger[match.group("version")] = match.group("name")
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

    def list_envs(self, git_branch: str) -> list[Mapping[str, Any]]:
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
        self.deleted_ids.append(env_id)
        self.rows = [row for row in self.rows if row["id"] != env_id]


def test_bootstrap_is_data_less_exactly_migrated_and_branch_scoped(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    pending = _migration(tmp_path, "20260807013400", "pending")
    supabase = FakeSupabase(baseline)
    vercel = FakeVercel()

    result = preview.bootstrap_preview(
        supabase,
        vercel,
        parent_ref=PARENT_REF,
        pr_number=82,
        git_branch=GIT_BRANCH,
        migrations=[baseline, pending],
        replace=True,
        timeout_seconds=0.1,
        interval_seconds=0,
    )

    assert result.applied_migrations == 1
    assert result.branch.project_ref == BRANCH_REF
    assert supabase.created_payloads == [
        {
            "branch_name": "pr-82-preview",
            "git_branch": GIT_BRANCH,
            "is_default": False,
            "persistent": False,
            "with_data": False,
        }
    ]
    assert pending.version in supabase.write_queries[0]
    assert "insert into supabase_migrations.schema_migrations" in supabase.write_queries[0]
    assert set(row["key"] for row in vercel.rows) == set(preview.PREVIEW_ENV_KEYS)
    assert all(row["target"] == ["preview"] for row in vercel.rows)
    assert all(row["gitBranch"] == GIT_BRANCH for row in vercel.rows)
    assert not any("service" in row["value"] for row in vercel.rows)


def test_failed_bootstrap_rolls_back_exact_created_ref_and_partial_env(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    pending = _migration(tmp_path, "20260807013400", "pending")
    supabase = FakeSupabase(baseline)
    vercel = FakeVercel(fail_on_key="RICHMOND_PREVIEW_GIT_BRANCH")

    with pytest.raises(preview.PreviewError, match="injected Vercel failure"):
        preview.bootstrap_preview(
            supabase,
            vercel,
            parent_ref=PARENT_REF,
            pr_number=82,
            git_branch=GIT_BRANCH,
            migrations=[baseline, pending],
            replace=True,
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
        git_branch=GIT_BRANCH,
        branch=branch,
        public_key=_jwt("anon"),
    )

    assert "old-preview-url" in vercel.deleted_ids
    assert "production-url" not in vercel.deleted_ids
    assert any(row["id"] == "production-url" for row in vercel.rows)
    branch_rows = [row for row in vercel.rows if row["gitBranch"] == GIT_BRANCH]
    assert set(row["key"] for row in branch_rows) == set(preview.PREVIEW_ENV_KEYS)


def test_cleanup_deletes_only_exact_branch_scoped_preview_vars(tmp_path: Path):
    baseline = _migration(tmp_path, "20260807013300", "baseline")
    supabase = FakeSupabase(baseline)
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
    supabase = FakeSupabase(baseline)
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
        "20260807013400",
        "wrapped",
        "BEGIN;\ncreate table wrapped(id int);\nCOMMIT;",
    )
    supabase = FakeSupabase(baseline)
    branch = preview.BranchRecord.from_payload(_branch_payload())
    with pytest.raises(preview.PreviewError, match="explicit transaction control"):
        preview.apply_migration(supabase, branch, wrapped)
    assert supabase.write_queries == []


def test_workflow_keeps_executable_code_trusted_and_secret_surface_narrow():
    text = WORKFLOW.read_text(encoding="utf-8")
    trusted_checkout = text.index("name: Check out trusted lifecycle controller")
    inert_checkout = text.index("name: Check out PR migrations as inert input")
    lifecycle = text.index("python src/supabase_preview.py bootstrap")
    assert trusted_checkout < inert_checkout < lifecycle
    assert "ref: main" in text
    assert "persist-credentials: false" in text
    assert "types: [closed]" in text
    assert "pull_request_target" in text
    assert "preview-head/supabase/migrations" in text
    assert "working-directory: preview-head" not in text
    assert "DATABASE_URL:" not in text
    assert "SUPABASE_SERVICE" not in text
    assert "with_data" not in text  # enforced inside the trusted controller


def test_vercel_controller_has_no_name_only_upsert_path():
    source = (REPO_ROOT / "src" / "supabase_preview.py").read_text(encoding="utf-8")
    assert '"upsert": "true"' not in source
    assert "create_preview_env" in source
    assert "delete_env(env_id)" in source
