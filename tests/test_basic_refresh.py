import json
import os
from copy import deepcopy

import pytest

from basic_refresh import (LOCAL_DATABASE_ENV, RefreshGuardError, apply_refresh,
                           isolated_environment, main, make_plan, validate_local_target)
from feature_policy import load_policy


@pytest.mark.parametrize("target", [
    "postgresql://user:private@db.remote.invalid/archive",
    "postgresql://user:private@localhost/postgres",
    "postgresql://user:private@localhost/archive?host=remote.invalid",
    "postgresql://user:private@localhost/archive?service=production",
    "postgresql://user:private@localhost/archive#secret",
    "postgresql://user:private@localhost:99999/archive",
    "file:///archive",
])
def test_nonlocal_or_rerouted_database_rejected_without_exposing_url(target):
    with pytest.raises(RefreshGuardError) as error:
        validate_local_target(target)
    assert "private" not in str(error.value)
    assert target not in str(error.value)


def test_default_plan_makes_no_source_or_database_requests(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Plan must not perform I/O")
    monkeypatch.setattr("socket.create_connection", forbidden)
    plan = make_plan()
    assert plan["profile"] == "basic_public"
    assert plan["modelBudgetLocked"] is True
    assert plan["monthlyModelCapUsd"] == 0
    assert "new vote extraction" in plan["disabledSteps"]


def test_production_url_is_never_a_fallback(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://private@remote.invalid/production")
    monkeypatch.delenv(LOCAL_DATABASE_ENV, raising=False)
    with pytest.raises(RefreshGuardError, match="never a fallback"):
        apply_refresh("local_archive", target="local")
    with pytest.raises(RefreshGuardError, match="arbitrary"):
        apply_refresh("local_archive", target="local", database_url_env="DATABASE_URL")


def test_missing_schema_stops_before_fetch_and_failure_is_sanitized(monkeypatch, capsys):
    monkeypatch.setenv(LOCAL_DATABASE_ENV, "postgresql://test:private@localhost/archive")
    monkeypatch.setattr("basic_refresh._preflight_local_schema", lambda *_: (_ for _ in ()).throw(RuntimeError("private connection details")))
    monkeypatch.setattr("basic_refresh._run_step", lambda *_: (_ for _ in ()).throw(AssertionError("must not fetch")))
    assert main(["--apply", "--target", "local"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["errorType"] == "RuntimeError"
    assert "private" not in json.dumps(report)


def test_features_and_capabilities_limit_execution_and_restore_parent_environment(monkeypatch):
    target = "postgresql://test:private@localhost/archive"
    monkeypatch.setenv(LOCAL_DATABASE_ENV, target)
    monkeypatch.setenv("DATABASE_URL", "production-original")
    monkeypatch.setenv("OPENAI_API_KEY", "original-key")
    monkeypatch.setenv("RICHMOND_API_BUDGET_LOCK", "false")
    policy = deepcopy(load_policy())
    policy["profiles"]["local_archive"]["features"]["campaign_finance"] = False
    policy["profiles"]["local_archive"]["capabilities"]["refresh_tags"] = False
    calls = []
    def run(step, year, through):
        import dotenv
        calls.append(step)
        assert os.environ["DATABASE_URL"] == target
        assert "OPENAI_API_KEY" not in os.environ
        assert os.environ["RICHMOND_API_BUDGET_LOCK"] == "true"
        assert os.environ["RICHMOND_API_MONTHLY_CAP_USD"] == "0"
        assert dotenv.load_dotenv("production.env", override=True) is False
        print("private legacy logs")
        return {"records_fetched": 2, "raw_personal_data": "private"}
    result = apply_refresh("local_archive", target="local", policy=policy,
                           runner=run, preflight=lambda *_: calls.append("preflight"))
    assert calls == ["preflight", "agenda"]
    assert result["modelCalls"] == 0
    assert "private" not in json.dumps(result)
    assert os.environ["DATABASE_URL"] == "production-original"
    assert os.environ["OPENAI_API_KEY"] == "original-key"
    assert os.environ["RICHMOND_API_BUDGET_LOCK"] == "false"


def test_failure_restores_environment_and_stops_remaining_steps(monkeypatch):
    monkeypatch.setenv(LOCAL_DATABASE_ENV, "postgresql://test:private@localhost/archive")
    before = dict(os.environ)
    calls = []
    def failing(step, *_):
        calls.append(step)
        return {"errors": 1}
    with pytest.raises(RefreshGuardError):
        apply_refresh("local_archive", target="local", runner=failing, preflight=lambda *_: None)
    assert calls == ["agenda"]
    assert dict(os.environ) == before


def test_isolated_environment_removes_libpq_and_provider_overrides(monkeypatch):
    monkeypatch.setenv("PGSERVICE", "production-service")
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.1")
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    with isolated_environment("postgresql://test@localhost/archive"):
        assert "PGSERVICE" not in os.environ
        assert "PGHOSTADDR" not in os.environ
        assert "RESEND_API_KEY" not in os.environ


def test_unexpected_valueerror_from_source_never_leaks_payload(monkeypatch,capsys):
    monkeypatch.setenv(LOCAL_DATABASE_ENV,"postgresql://test:private@localhost/archive")
    monkeypatch.setattr("basic_refresh._preflight_local_schema",lambda *_: None)
    monkeypatch.setattr("basic_refresh._run_step",lambda *args,**kwargs: (_ for _ in ()).throw(ValueError("private donor address / connection text")))
    assert main(["--apply","--target","local","--steps","agenda"]) == 1
    report=json.loads(capsys.readouterr().out)
    assert report["errorType"] == "ValueError"
    assert "private" not in json.dumps(report)
