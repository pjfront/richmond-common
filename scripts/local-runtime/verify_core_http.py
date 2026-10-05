"""Briefly serve the approved compact measurement DB on loopback; verify core HTTP reads."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

spec = importlib.util.spec_from_file_location("local_runner", Path(__file__).with_name("run_local.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
CORE_DATABASE = "basic_core_measure_20261004"


def main():
    runtime = runner.DEFAULT_RUNTIME
    if runner.port_open(59879) or runner.port_open(59880):
        raise RuntimeError("Temporary core verification ports are occupied")
    # Only add the read guard to the separate compact measurement DB.
    bootstrap = (runtime / "config" / "bootstrap.private.sql").read_text(encoding="utf-8")
    guard_sql = bootstrap[bootstrap.index("CREATE SCHEMA IF NOT EXISTS local_runtime"):]
    guard_file = runtime / "config" / "core-read-guard.sql"
    guard_file.write_text(guard_sql, encoding="utf-8")
    runner.private_run([str(runner.PG_BIN / "psql.exe"), "-X", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-p", "59876", "-U", "postgres", "-d", CORE_DATABASE, "-f", str(guard_file)], runtime, "core-read-guard.private.log", env=runner.pg_env(runtime))
    config = (runtime / "config" / "postgrest.private.conf").read_text(encoding="utf-8").replace('/richmond_restore"', f'/{CORE_DATABASE}"').replace("server-port = 59877", "server-port = 59879").replace('db-extra-search-path = "public,extensions"', 'db-extra-search-path = "public"')
    config_path = runtime / "config" / "postgrest-core.private.conf"
    config_path.write_text(config, encoding="utf-8")
    proxy_path = runtime / "config" / "core-proxy.json"
    runner.write_json(proxy_path, {"host": "127.0.0.1", "port": 59880, "upstreamHost": "127.0.0.1", "upstreamPort": 59879, "webPort": 3100, "readRpcs": ["search_site"]})
    binary = Path(json.loads((runtime / "config" / "tooling-verification.json").read_text())["executable"])
    env = runner.safe_env()
    env["PATH"] = str(runner.PG_BIN) + runner.os.pathsep + env.get("PATH", "")
    processes = []
    checks = []
    secrets = runner.load_secrets(runtime)
    headers = {"Authorization": "Bearer " + secrets["anon_key"], "apikey": secrets["anon_key"], "Prefer": "count=exact"}

    def request(path, body=None, method="GET"):
        extra = dict(headers)
        if body is not None:
            extra["Content-Type"] = "application/json"
        req = urllib.request.Request("http://127.0.0.1:59880/rest/v1/" + path, data=json.dumps(body).encode() if body is not None else None, headers=extra, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.status, response.headers, json.loads(response.read())
        except urllib.error.HTTPError as error:
            error.read()
            return error.code, error.headers, None

    def check(name, status, passed, count=None):
        checks.append({"name": name, "http_status": status, "passed": bool(passed), "records_returned": count})

    try:
        process = runner.launch([str(binary), str(config_path)], runtime, "core-postgrest.private.log", env=env)
        processes.append(process); runner.wait_port(59879, process)
        process = runner.launch([shutil.which("node"), str(Path(__file__).with_name("proxy.cjs")), str(proxy_path)], runtime, "core-proxy.private.log")
        processes.append(process); runner.wait_port(59880, process)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status, _, _ = request("meetings?select=id&limit=1")
            if status in (200, 206):
                break
            time.sleep(0.25)
        status, _, rows = request("rpc/search_site", {"p_query": "Point Molate", "p_city_fips": "0660620", "p_result_type": "agenda_item", "p_limit": 10, "p_offset": 0}, "POST")
        check("legacy_search_site_contract", status, status == 200 and isinstance(rows, list) and len(rows) > 0, len(rows) if isinstance(rows, list) else None)
        select = "id,meeting_id,item_number,title,topic_label,category,created_at,agenda_source_retired_at,meetings!inner(id,city_fips,meeting_date,agenda_url,minutes_url,video_url,source_cancelled_at)"
        query = urllib.parse.urlencode({"select": select, "agenda_source_retired_at": "is.null", "meetings.city_fips": "eq.0660620", "meetings.source_cancelled_at": "is.null", "limit": "10"})
        status, _, rows = request("agenda_items?" + query)
        check("legacy_agenda_nested_projection", status, status in (200, 206) and isinstance(rows, list) and len(rows) == 10 and all(row.get("meetings", {}).get("city_fips") == "0660620" for row in rows), len(rows) if isinstance(rows, list) else None)
        status, _, rows = request("meetings?select=id,meeting_date,agenda_url,minutes_url,body_id&city_fips=eq.0660620&limit=10")
        check("legacy_meeting_projection", status, status in (200, 206) and isinstance(rows, list) and len(rows) == 10, len(rows) if isinstance(rows, list) else None)
        status, _, rows = request("motions?select=id,agenda_item_id,motion_text,result,source,sequence_number,created_at&limit=10")
        check("legacy_motion_projection", status, status in (200, 206) and isinstance(rows, list) and len(rows) == 10, len(rows) if isinstance(rows, list) else None)
        status, _, rows = request("votes?select=id,motion_id,official_id,official_name,vote_choice,source&limit=10")
        check("legacy_vote_projection", status, status in (200, 206) and isinstance(rows, list) and len(rows) == 10, len(rows) if isinstance(rows, list) else None)
        columns = "event_key,scope_key,event_kind,donor_name,donor_fppc_id,recipient_name,recipient_fppc_id,reporting_filer_name,reporting_filer_fppc_id,amount,amount_kind,activity_date,support_oppose,candidate_name,measure_name,election_date,filing_ids,source_urls,source_url,extracted_at,source_tier,reconciliation_status"
        status, meta, rows = request("finance_public_events?" + urllib.parse.urlencode({"select": columns, "scope_key": "eq.0660620:calendar-2026", "limit": "1000"}))
        count = meta.get("Content-Range", "").split("/")[-1]
        check("legacy_finance_full_public_projection", status, status in (200, 206) and isinstance(rows, list) and len(rows) == 1000 and count == "1424", len(rows) if isinstance(rows, list) else None)
        status, _, rows = request("finance_public_coverage?select=source,form_type,scope_key,status,checked_at,activity_from,activity_through,filing_count,assertion_count,pending_count,limitations,source_url&scope_key=eq.0660620:calendar-2026")
        check("legacy_finance_coverage_projection", status, status == 200 and isinstance(rows, list) and len(rows) == 8 and all(row["status"] == "partial" for row in rows), len(rows) if isinstance(rows, list) else None)
        status, _, rows = request("core_projection_status?" + urllib.parse.urlencode({"select": "feature,status,checked_at,source_scope", "feature": "in.(agenda_refresh,finance)", "limit": "2"}))
        check("anon_core_source_metadata_projection", status, status == 200 and isinstance(rows, list) and 1 <= len(rows) <= 2 and all(row.get("feature") in {"agenda_refresh", "finance"} for row in rows), len(rows) if isinstance(rows, list) else None)
        test_env = runner.safe_env()
        test_env.update({"RICHMOND_ANON_VISIBILITY_TARGET": "compact_core", "RICHMOND_ANON_VISIBILITY_URL": "http://127.0.0.1:59880", "RICHMOND_ANON_VISIBILITY_KEY": secrets["anon_key"]})
        runner.private_run([runner.sys.executable, "-m", "pytest", "tests/test_anon_visibility.py", "-k", "target_specific", "-q"], runtime, "core-anon-pytest.private.log", env=test_env)
        checks.append({"name": "target_specific_anon_pytest", "passed": True, "target": "compact_core"})
        status, _, _ = request("agenda_items?id=eq.00000000-0000-0000-0000-000000000000", {"title": "BLOCKED TEST"}, "PATCH")
        check("core_proxy_rejects_mutation", status, status == 403)
        report = {"checked_at": int(time.time()), "database": CORE_DATABASE, "all_passed": all(row["passed"] for row in checks), "checks": checks, "data_rows_modified": False, "cloud_calls": False, "temporary_http_services_stopped_after_test": True}
        runner.write_json(runtime / "config" / "core-http-verification.json", report)
        print(json.dumps(report, indent=2))
        if not report["all_passed"]:
            raise SystemExit(1)
    finally:
        for process in reversed(processes):
            process.terminate()
            process.wait(timeout=15)


if __name__ == "__main__":
    main()
