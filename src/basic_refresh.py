"""Plan or explicitly apply deterministic refreshes to an isolated local DB.

Reads official eSCRIBE agenda records and NetFile electronic assertions;
keyword tags read agenda titles/descriptions. It never regenerates saved AI
content. Hosted refresh uses only a compact/source-link writer and dedicated target.
No production dotenv file, generic enrichment DAG, email or paid API is used.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import date
import io
import json
import os
import re
from typing import Any, Callable, Iterator
from unittest.mock import patch
from urllib.parse import parse_qsl, unquote, urlsplit

from feature_policy import LOCAL_PROFILES, FeaturePolicyError, is_capability_enabled, is_feature_enabled, load_policy, resolve_profile
from basic_core_refresh import CompactRefreshError
from finance_public_projection import FinanceProjectionError
from basic_finance_acquisition import FinanceAcquisitionError

LOCAL_DATABASE_ENV = "RICHMOND_LOCAL_DATABASE_URL"
BASIC_DATABASE_ENV = "RICHMOND_BASIC_DATABASE_URL"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
COMPACT_WRITER_IMPLEMENTED = True
PRODUCTION_PROJECT_REF = "ahrwvmizzykyyfavdvfv"
STEPS = (
    ("agenda", "refresh_agenda", "agenda_items"),
    ("tags", "refresh_tags", "tags"),
    ("finance", "refresh_finance", "campaign_finance"),
)
DISABLED_STEPS = [
    "new vote extraction", "transcript extraction/windowing", "paper numeric extraction",
    "LLM summaries/recaps/explainers", "embeddings", "OCR", "email", "accounts",
    "bulk replay", "generic --enrich/--enrich-only", "source-change dispatch",
]
PRIVILEGED_ENV_NAMES = frozenset({
    "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY", "AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY", "APIFY_API_TOKEN", "OPENCORPORATES_API_TOKEN", "RESEND_API_KEY",
    "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY",
    "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY", "VERCEL_TOKEN",
    "API_SECRET", "CRON_SECRET", "SITE_ACCESS_PASSWORD", "OPERATOR_PASSWORD",
    "OPERATOR_SESSION_SECRET",
})


class RefreshGuardError(ValueError):
    """Rejected before source fetching or writes; messages contain no URL."""


def validate_local_target(database_url: str) -> None:
    try:
        parsed = urlsplit(database_url)
        port = parsed.port
        parameters = parse_qsl(parsed.query, strict_parsing=True)
    except ValueError as exc:
        raise RefreshGuardError("Invalid isolated database target") from exc
    if (parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in LOOPBACK_HOSTS
            or parsed.fragment or port is not None and not 1 <= port <= 65535):
        raise RefreshGuardError("Refresh requires an explicit loopback PostgreSQL target")
    name = unquote(parsed.path.removeprefix("/"))
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,62}", name) or name in {"postgres", "template0", "template1"}:
        raise RefreshGuardError("Use a dedicated local archive database")
    if any(key != "sslmode" or value not in {"disable", "prefer", "require"} for key, value in parameters):
        raise RefreshGuardError("Database routing/service overrides are forbidden")


def validate_public_target(database_url: str, project_ref: str, pooler_host: str | None = None) -> None:
    """Exact direct target or explicitly declared session pooler; no guessed route."""
    if not re.fullmatch(r"[a-z]{20}", project_ref) or project_ref == PRODUCTION_PROJECT_REF:
        raise RefreshGuardError("A dedicated basic project identity is required; the original paid project is forbidden")
    try:
        parsed = urlsplit(database_url)
        port = parsed.port
        parameters = parse_qsl(parsed.query, strict_parsing=True)
    except ValueError as exc:
        raise RefreshGuardError("Invalid dedicated basic database target") from exc
    direct = parsed.hostname == f"db.{project_ref}.supabase.co"
    pooler = bool(pooler_host and re.fullmatch(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com", pooler_host)
                  and parsed.hostname == pooler_host and unquote(parsed.username or "") == f"postgres.{project_ref}"
                  and port == 5432)
    if (parsed.scheme not in {"postgres", "postgresql"}
            or not (direct or pooler) or port not in {None, 5432}
            or unquote(parsed.path) != "/postgres" or parsed.fragment
            or not parsed.username or not parsed.password
            or PRODUCTION_PROJECT_REF in unquote(database_url).lower()):
        raise RefreshGuardError("Basic refresh requires an exact dedicated project database target")
    if not parameters or any(key != "sslmode" or value not in {"require", "verify-full"} for key, value in parameters):
        raise RefreshGuardError("Basic database connection requires TLS and forbids routing overrides")


def make_plan(profile: str | None = None, *, target: str = "public", steps: list[str] | None = None,
              policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if target not in {"local", "public"}:
        raise RefreshGuardError("Unknown refresh target")
    current = policy or load_policy()
    selected = resolve_profile(profile, local=target == "local", policy=current)
    if target == "local" and selected not in LOCAL_PROFILES:
        raise RefreshGuardError("A local refresh requires a local archive/AI profile")
    enabled = [step for step, capability, feature in STEPS
               if is_capability_enabled(capability, selected, local=target == "local", policy=current)
               and is_feature_enabled(feature, selected, local=target == "local", policy=current)]
    if steps is not None:
        if not steps or len(steps) != len(set(steps)) or any(step not in {name for name, _, _ in STEPS} for step in steps):
            raise RefreshGuardError("Refresh steps must be a unique explicit allowlist subset")
        enabled = [step for step in enabled if step in steps]
    storage = current["storage"][selected]
    blocked = None
    if target == "public" and (storage["mode"] != "compact_public" or storage["writerReady"] is not True or not COMPACT_WRITER_IMPLEMENTED):
        blocked = "Compact public/source-link writer is not ready; the full document-lake writer must not target a Free database."
    elif target == "local" and (storage["mode"] != "full_archive" or storage["writerReady"] is not True):
        blocked = "The selected local archive writer is not ready."
    return {
        "profile": selected, "target": target, "status": "blocked" if blocked else "plan",
        "blockedReason": blocked, "steps": enabled,
        "databaseUrlEnvironment": LOCAL_DATABASE_ENV if target == "local" else BASIC_DATABASE_ENV,
        "requirements": (["RICHMOND_BASIC_READY=true only after dedicated target verification", "Exact RICHMOND_BASIC_PROJECT_REF and RICHMOND_BASIC_DATABASE_URL with TLS", "Declared session RICHMOND_BASIC_POOLER_HOST for IPv4-only runners", "Imported compact public-core schema and Richmond seed rows"] if target == "public" else ["Explicit RICHMOND_LOCAL_DATABASE_URL loopback restore", "Restored current local schema and Richmond seed rows", "Local disk capacity for retained originals"]) + ["Python requirements.txt", "Reachable official source APIs", "Model budget locked at zero"],
        "operations": {
            "agenda": "Bounded official calendar/HTML -> compact source-link meetings/items; no binary/document-lake storage" if target == "public" else "Explicit local source-links mode, or full archive incremental writer requiring every declared PDF; no enrichment cascade",
            "tags": "Reconcile keyword-owned projections; preserve manual tags and un-attributed saved labels",
            "finance": "Bounded all-eight-form electronic acquisition -> validated complete public projection -> atomic scope replacement; no stored PDFs/raw assertions" if target == "public" else "Bounded all-eight-form electronic acquisition then archive save_snapshot; model_calls=0",
        },
        "disabledSteps": list(DISABLED_STEPS), "modelBudgetLocked": True,
        "monthlyModelCapUsd": 0, "maxPublicDatabaseBytes": current["storage"]["basic_public"]["maxDatabaseBytes"],
        "limitations": ["Existing votes remain available; new structured votes require review or optional extraction", "Paper figures retain their reviewed snapshot; electronic acquisition does not supply all paper transactions", "Feature switches never delete saved records"],
    }


@contextmanager
def isolated_environment(database_url: str) -> Iterator[None]:
    """Suppress legacy dotenv imports and remove provider credentials in-process."""
    import dotenv

    before = dict(os.environ)
    try:
        for key in PRIVILEGED_ENV_NAMES | {"DATABASE_URL", "PGSERVICE", "PGSERVICEFILE", "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGOPTIONS", "PGPASSFILE"}:
            os.environ.pop(key, None)
        os.environ.update({"DATABASE_URL": database_url, "RICHMOND_API_BUDGET_LOCK": "true", "RICHMOND_API_MONTHLY_CAP_USD": "0", "RICHMOND_EVENT_BUDGET_USD": "0"})
        with patch.object(dotenv, "load_dotenv", return_value=False):
            yield
    finally:
        os.environ.clear()
        os.environ.update(before)


def _preflight_local_schema(database_url: str, steps: list[str]) -> None:
    import psycopg2

    tables = {"documents", "meetings", "agenda_items", "bodies"}
    if "agenda" in steps:
        tables.add("agenda_item_attachments")
    if "tags" in steps:
        tables.update({"topics", "item_topics"})
    if "finance" in steps:
        tables.update({"finance_assertions", "finance_events", "finance_source_coverage"})
    conn = psycopg2.connect(database_url, connect_timeout=5)
    try:
        if conn.info.host not in LOOPBACK_HOSTS:
            raise RefreshGuardError("Connected database is not a local archive")
        with conn.cursor() as cur:
            for table in sorted(tables):
                cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cur.fetchone()[0] is None:
                    raise RefreshGuardError("Local archive schema is incomplete; restore before refreshing")
    finally:
        conn.close()


def _prepare_local_metadata(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS public.core_projection_status (
                       feature text PRIMARY KEY,status text NOT NULL,detail text NOT NULL,
                       checked_at timestamptz,source_url text,revision_sha256 text,source_scope text,
                       updated_at timestamptz NOT NULL DEFAULT now())""")
    conn.commit()


def _run_step(step: str, year: int, through: str, *, agenda_limit: int = 10, tag_limit: int = 2000,
              agenda_mode: str = "archive-full") -> dict[str, Any]:
    if step not in {name for name, _, _ in STEPS}:
        raise RefreshGuardError("Refresh step is not allowlisted")
    from db import get_connection

    conn = get_connection()
    try:
        if step == "agenda":
            if agenda_mode == "source-links":
                from basic_core_refresh import acquire_agendas, write_agendas
                _prepare_local_metadata(conn)
                observations = acquire_agendas(limit=agenda_limit)
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('richmond-local-source-refresh',0))")
                        result = write_agendas(cur, observations, tag=False)
                return {"records_fetched": result["meetings_observed"], "records_updated": result["items_written"],
                        "records_pending": result["awaiting_agenda"] + result["unmapped_bodies"], "items_retired": result["items_retired"], "minutes_preserved": result["minutes_preserved"]}
            from pipelines.escribemeetings import sync_escribemeetings
            return sync_escribemeetings(conn, "0660620", sync_type="incremental", limit=agenda_limit)
        if step == "tags":
            from basic_core_refresh import reconcile_keyword_tags
            _prepare_local_metadata(conn)
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT slug,id,name FROM topics WHERE city_fips='0660620' AND status='active'")
                    topics = {slug:(str(identity),name) for slug,identity,name in cur.fetchall()}
                    cur.execute("""SELECT ai.id,coalesce(ai.title,'') || ' ' || coalesce(ai.description,'')
                                   FROM agenda_items ai JOIN meetings m ON m.id=ai.meeting_id
                                   WHERE m.city_fips='0660620' AND m.source_cancelled_at IS NULL
                                     AND ai.agenda_source_retired_at IS NULL
                                   ORDER BY m.meeting_date DESC,ai.item_number LIMIT %s""", (tag_limit,))
                    items = cur.fetchall()
                    writes = sum(reconcile_keyword_tags(cur,str(identity),text,topics) for identity,text in items)
            return {"items_scanned":len(items),"assignments_created":writes}
        from finance_sync import public_summary, save_snapshot
        from basic_finance_acquisition import acquire_bounded_finance_snapshot
        snapshot = acquire_bounded_finance_snapshot(year, through)
        if snapshot.get("acquisition_metrics", {}).get("model_calls") != 0:
            raise RefreshGuardError("Finance acquisition did not prove zero model calls")
        with conn:
            return {**public_summary(snapshot), **save_snapshot(conn, snapshot)}
    finally:
        conn.close()


def apply_refresh(profile: str, *, target: str, database_url_env: str | None = None,
                  year: int | None = None, through: str | None = None,
                  policy: dict[str, Any] | None = None,
                  steps: list[str] | None = None, agenda_limit: int = 10, tag_limit: int = 2000,
                  agenda_mode: str = "archive-full",
                  runner: Callable[[str, int, str], dict[str, Any]] | None = None,
                  preflight: Callable[[str, list[str]], None] | None = None) -> dict[str, Any]:
    plan = make_plan(profile, target=target, steps=steps, policy=policy)
    if plan["blockedReason"]:
        raise RefreshGuardError(plan["blockedReason"] or "Hosted refresh is not implemented")
    if type(agenda_limit) is not int or not 1 <= agenda_limit <= 20 or type(tag_limit) is not int or not 1 <= tag_limit <= 10000:
        raise RefreshGuardError("Local/compact refresh limits are outside the bounded allowlist")
    if agenda_mode not in {"archive-full","source-links"}:
        raise RefreshGuardError("Unknown local agenda storage mode")
    expected_environment = LOCAL_DATABASE_ENV if target == "local" else BASIC_DATABASE_ENV
    if database_url_env not in {None, expected_environment}:
        raise RefreshGuardError("Legacy or arbitrary database environment names are forbidden")
    database_url = os.environ.get(expected_environment, "")
    if not database_url:
        raise RefreshGuardError(f"{expected_environment} is required; production DATABASE_URL is never a fallback")
    if target == "local":
        validate_local_target(database_url)
    else:
        if os.environ.get("RICHMOND_BASIC_READY") != "true":
            raise RefreshGuardError("Dedicated basic target readiness is not explicitly confirmed")
        validate_public_target(database_url, os.environ.get("RICHMOND_BASIC_PROJECT_REF", ""), os.environ.get("RICHMOND_BASIC_POOLER_HOST"))
    today = date.today()
    # Public defaults keep the explicitly reviewed publication scope. They
    # never stop agendas because the calendar advanced, nor open a new cycle.
    selected_year = year if year is not None else 2026 if target == "public" else today.year
    selected_through = through or ("2026-11-03" if target == "public" else today.isoformat())
    if date.fromisoformat(selected_through).year != selected_year:
        raise RefreshGuardError("Finance through-date must fall in the selected calendar year")
    results = []
    # Suppress legacy writer logs, which can contain source/person details;
    # report only fixed aggregate fields and never database URLs or secrets.
    with isolated_environment(database_url), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        if target == "public":
            import psycopg2
            from basic_core_refresh import refresh_compact
            conn = psycopg2.connect(database_url, connect_timeout=5)
            try:
                return {"profile": plan["profile"], "target": target,
                        **refresh_compact(conn, plan["steps"], year=selected_year, through=selected_through,
                                          ceiling=plan["maxPublicDatabaseBytes"], agenda_limit=agenda_limit)}
            finally:
                conn.close()
        (preflight or _preflight_local_schema)(database_url, plan["steps"])
        for step in plan["steps"]:
            result = runner(step, selected_year, selected_through) if runner else _run_step(step, selected_year, selected_through, agenda_limit=agenda_limit, tag_limit=tag_limit, agenda_mode=agenda_mode)
            if result.get("errors", 0) or result.get("status") in {"failed", "skipped"}:
                raise RefreshGuardError("A deterministic refresh step did not complete; subsequent steps were stopped")
            aggregates = {key: value for key, value in result.items()
                          if key in {"records_fetched", "records_new", "records_updated", "records_pending", "items_retired", "minutes_preserved", "items_scanned", "items_tagged", "items_updated", "assignments_created", "assertions", "events", "pdfs"}
                          and type(value) is int}
            results.append({"step": step, "status": "completed", **aggregates})
    return {"profile": plan["profile"], "target": "local", "status": "completed", "modelCalls": 0,
            "coverage": {"agendaWindow": "past-60/next-14 days", "agendaLimit": agenda_limit, "tagLimit": tag_limit, "financeThrough": selected_through if "finance" in plan["steps"] else None}, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", "--dry-run", action="store_true", help="List requirements and disabled steps without imports, network or database access (default)")
    mode.add_argument("--apply", action="store_true", help="Explicitly refresh an isolated local archive or dedicated compact project")
    parser.add_argument("--profile", choices=["basic_public", "local_archive", "local_ai", "cloud_ai"])
    parser.add_argument("--target", choices=["local", "public"], default="public")
    parser.add_argument("--database-url-env", help="Only the named isolated local/basic database variable is accepted")
    parser.add_argument("--steps", nargs="+", choices=["agenda", "tags", "finance"], help="Optional explicit subset; all enabled steps is the default")
    parser.add_argument("--agenda-limit", type=int, default=10)
    parser.add_argument("--tag-limit", type=int, default=2000)
    parser.add_argument("--agenda-mode", choices=["archive-full","source-links"], default="archive-full", help="Local agenda originals or bounded source-link records; archived originals are retained in either mode")
    parser.add_argument("--year", type=int)
    parser.add_argument("--through")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            selected = resolve_profile(args.profile, local=args.target == "local")
            result = apply_refresh(selected, target=args.target, database_url_env=args.database_url_env, year=args.year, through=args.through,
                                   steps=args.steps, agenda_limit=args.agenda_limit, tag_limit=args.tag_limit, agenda_mode=args.agenda_mode)
        else:
            result = make_plan(args.profile, target=args.target, steps=args.steps)
    except (RefreshGuardError, FeaturePolicyError, CompactRefreshError, FinanceProjectionError, FinanceAcquisitionError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "failed", "errorType": type(exc).__name__, "reason": "Refresh failed; no credential or source details are printed"}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
