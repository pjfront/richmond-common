"""Temporarily verify Next basic_public against the compact local DB, with anon only."""
from __future__ import annotations
import csv
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

spec = importlib.util.spec_from_file_location("local_runner", Path(__file__).with_name("run_local.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main():
    runtime = runner.DEFAULT_RUNTIME
    ports = (59879, 59880, 3101)
    if any(runner.port_open(port) for port in ports):
        raise RuntimeError("Temporary basic verification ports are occupied")
    # Reuse the separately verified compact DB's restricted config, not cloud env.
    config = (runtime / "config" / "postgrest-core.private.conf").read_text(encoding="utf-8").replace("http://127.0.0.1:3100,http://localhost:3100", "http://127.0.0.1:3101,http://localhost:3101")
    config_path = runtime / "config" / "postgrest-basic.private.conf"
    config_path.write_text(config, encoding="utf-8")
    proxy_path = runtime / "config" / "basic-proxy.json"
    runner.write_json(proxy_path, {"host": "127.0.0.1", "port": 59880, "upstreamHost": "127.0.0.1", "upstreamPort": 59879, "webPort": 3101, "readRpcs": ["search_site"]})
    test_runtime = runtime / "basic-public-test"
    runner.private_dirs(test_runtime)
    runner.copy_web(test_runtime, runner.REPOSITORY / "web", web_port=3101)
    secret = runner.load_secrets(runtime)
    env = runner.safe_env()
    env.update({"NODE_ENV": "development", "NEXT_TELEMETRY_DISABLED": "1", "NEXT_PUBLIC_SITE_URL": "http://127.0.0.1:3101", "NEXT_PUBLIC_SUPABASE_URL": "http://127.0.0.1:59880", "NEXT_PUBLIC_SUPABASE_ANON_KEY": secret["anon_key"], "SITE_ACCESS_REQUIRED": "false", "RICHMOND_API_BUDGET_LOCK": "true", "RICHMOND_API_MONTHLY_CAP_USD": "0", "RICHMOND_READ_ONLY_STAGE": "true", "RICHMOND_LOCAL_ARCHIVE": "false", "RICHMOND_FEATURE_PROFILE": "basic_public", "RICHMOND_BUILD_USES_PRODUCTION_DATA": "false"})
    assert "SUPABASE_SERVICE_ROLE_KEY" not in env
    binary = Path(json.loads((runtime / "config" / "tooling-verification.json").read_text())["executable"])
    node = shutil.which("node")
    next_bin = test_runtime / "web" / "node_modules" / "next" / "dist" / "bin" / "next"
    processes = []
    checks = []

    def request(path, method="GET"):
        req = urllib.request.Request("http://127.0.0.1:3101" + path, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()

    def check(name, status, passed, **metadata):
        checks.append({"name": name, "http_status": status, "passed": bool(passed), **metadata})

    try:
        pgrst_env = runner.safe_env()
        pgrst_env["PATH"] = str(runner.PG_BIN) + runner.os.pathsep + pgrst_env.get("PATH", "")
        process = runner.launch([str(binary), str(config_path)], runtime, "basic-postgrest.private.log", env=pgrst_env)
        processes.append(process); runner.wait_port(59879, process)
        process = runner.launch([node, str(Path(__file__).with_name("proxy.cjs")), str(proxy_path)], runtime, "basic-proxy.private.log")
        processes.append(process); runner.wait_port(59880, process)
        process = runner.launch([node, str(next_bin), "dev", "--webpack", "--hostname", "127.0.0.1", "--port", "3101"], runtime, "basic-web.private.log", env=env, cwd=test_runtime / "web")
        processes.append(process); runner.wait_port(3101, process, timeout=60)
        status, _, html = request("/")
        check("basic_home", status, status == 200 and b"Find the public record" in html)
        check("basic_source_status_visible", status, status == 200 and b"Source checks" in html and b"New votes await review" in html and b"Paper filings await review" in html and (b"Source last checked" in html or b"No source check has been recorded yet" in html or b"Source check time is unavailable" in html))
        status, _, html = request("/search?q=housing")
        check("basic_search_page", status, status == 200 and b"Search decisions" in html)
        status, _, raw = request("/api/commons/search?" + urllib.parse.urlencode({"q": "What housing decisions were made in 2026"}))
        data = json.loads(raw) if status == 200 else {}
        records = data.get("records", [])
        check("basic_housing_search_records", status, status == 200 and bool(records), records_returned=len(records))
        status, _, html = request("/money")
        money_text = re.sub(r"<!--.*?-->|<[^>]*>", "", html.decode("utf-8"))
        check("basic_money_page", status, status == 200 and "1424 indexed records" in money_text and "Source document 1" in money_text)
        status, _, raw = request("/api/finance/export")
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8")))) if status == 200 else []
        check("basic_finance_export", status, status == 200 and len(rows) == 1424, records_returned=len(rows))
        status, _, html = request("/meetings")
        check("basic_meeting_index", status, status == 200 and b"Meetings" in html)
        status, _, raw = request("/api/commons/search?" + urllib.parse.urlencode({"q": "Who voted on Point Molate in 2010"}))
        data = json.loads(raw) if status == 200 else {}
        records = data.get("records", [])
        ordinary = next((row for row in records if row.get("motions") and not row.get("voteSourceReview")), None)
        held = [row for row in records if row.get("id") == "9cf375c8-edc1-413c-8ee0-6485348fbc6f"]
        check("basic_vote_records_and_hold", status, status == 200 and ordinary is not None and bool(held) and all(not row.get("motions") and row.get("voteSourceReview") for row in held), records_returned=len(records))
        if ordinary:
            # Links are application-generated exact record URLs, never arbitrary remote targets.
            href = ordinary.get("url", "")
            if not href.startswith("/meetings/"):
                raise RuntimeError("Compact vote result lacks an exact item permalink")
            status, _, html = request(href)
            check("basic_ordinary_item_votes_page", status, status == 200 and b"Extracted from official minutes" in html)
            meeting_path = href.split("/items/")[0]
            status, _, html = request(meeting_path)
            check("basic_exact_meeting_page", status, status == 200 and b"Point Molate" in html)
        status, _, html = request("/meetings/5f560013-daea-499a-8ecd-ca1a089c8a0c/items/J-2")
        check("basic_held_item_page", status, status == 200 and b"held for source review" in html and b"Jovanka Beckles" not in html and b"Tom Bates" not in html)
        for name, path, method in [("basic_operator_hidden", "/api/operator/settings", "GET"), ("basic_semantic_route_hidden", "/api/search?q=housing", "GET"), ("basic_email_hidden", "/api/email/send-digest", "POST")]:
            status, _, _ = request(path, method)
            check(name, status, status in (401, 403, 404, 405))
        report = {"checked_at": int(time.time()), "database": "basic_core_measure_20261004", "profile": "basic_public", "anon_only": True, "all_passed": all(row["passed"] for row in checks), "checks": checks, "cloud_calls": False, "data_rows_modified": False, "temporary_http_services_stopped_after_test": True, "local_archive_3100_preserved": runner.port_open(3100)}
        runner.write_json(runtime / "config" / "basic-app-verification.json", report)
        print(json.dumps(report, indent=2))
        if not report["all_passed"]:
            raise SystemExit(1)
    finally:
        for process in reversed(processes):
            runner.private_run(["taskkill", "/PID", str(process.pid), "/T", "/F"], runtime, "basic-stop.private.log")
            process.wait(timeout=15)


if __name__ == "__main__":
    main()
