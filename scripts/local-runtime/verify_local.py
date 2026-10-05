"""Check local read flows; output only status/counts, never rows or credentials."""
from __future__ import annotations
import argparse
import http.cookiejar
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

RUNTIME = Path(__file__).resolve().parents[2].parent / "local-runtime"
HELD_ITEM = "9cf375c8-edc1-413c-8ee0-6485348fbc6f"
HELD_MEETING = "5f560013-daea-499a-8ecd-ca1a089c8a0c"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infrastructure-only", action="store_true")
    args = parser.parse_args()
    secrets = json.loads((RUNTIME / "config" / "secrets.json").read_text(encoding="utf-8"))
    checks = []
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def request(base, path, *, method="GET", body=None, headers=None):
        merged = dict(headers or {})
        if body is not None:
            body = json.dumps(body).encode()
            merged["Content-Type"] = "application/json"
        req = urllib.request.Request(base + path, data=body, headers=merged, method=method)
        try:
            with opener.open(req, timeout=120) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()

    def check(name, passed, **metadata):
        checks.append({"name": name, "passed": bool(passed), **metadata})

    api = "http://127.0.0.1:59878"
    auth = {"Authorization": "Bearer " + secrets["anon_key"], "apikey": secrets["anon_key"], "Prefer": "count=exact"}
    status, headers, raw = request(api, "/rest/v1/rpc/search_site", method="POST", body={"p_query": "Point Molate", "p_city_fips": "0660620", "p_result_type": "agenda_item", "p_limit": 10, "p_offset": 0}, headers=auth)
    hits = json.loads(raw) if status == 200 else []
    check("keyword_search_rpc", status == 200 and isinstance(hits, list) and len(hits) > 0, http_status=status, records=len(hits))
    status, headers, raw = request(api, "/rest/v1/finance_public_events?select=event_key,activity_date,source_url&scope_key=eq.0660620:calendar-2026&order=event_key&limit=1000", headers=auth)
    events = json.loads(raw) if status in (200, 206) else []
    count = int(headers.get("Content-Range", "0-0/0").split("/")[-1]) if headers.get("Content-Range", "").split("/")[-1].isdigit() else None
    check("published_finance_projection", status in (200, 206) and count == 1424 and len(events) == 1000 and all(row.get("source_url") for row in events), http_status=status, exact_snapshot_count=count, returned=len(events))
    status, headers, raw = request(api, "/rest/v1/finance_public_coverage?select=source,status,limitations&scope_key=eq.0660620:calendar-2026", headers=auth)
    coverage = json.loads(raw) if status == 200 else []
    check("finance_coverage", status == 200 and len(coverage) == 8 and all(row["status"] == "partial" for row in coverage), http_status=status, records=len(coverage))

    ordinary = None
    ordinary_votes = 0
    for hit in hits:
        if hit.get("id") == HELD_ITEM:
            continue
        path = "/rest/v1/agenda_items?" + urllib.parse.urlencode({"select": "id,meeting_id,item_number,meetings!inner(id,meeting_date,agenda_url,minutes_url,city_fips,source_cancelled_at)", "id": "eq." + hit["id"]})
        status, _, raw = request(api, path, headers=auth)
        items = json.loads(raw) if status == 200 else []
        if not items:
            continue
        item = items[0]
        status, _, raw = request(api, "/rest/v1/motions?" + urllib.parse.urlencode({"select": "id,agenda_item_id,motion_text,result,source", "agenda_item_id": "eq." + item["id"]}), headers=auth)
        motions = json.loads(raw) if status == 200 else []
        if not motions:
            continue
        ids = ",".join(row["id"] for row in motions)
        status, _, raw = request(api, "/rest/v1/votes?" + urllib.parse.urlencode({"select": "id,motion_id,vote_choice,source", "motion_id": "in.(" + ids + ")"}), headers=auth)
        votes = json.loads(raw) if status == 200 else []
        ordinary_votes = len(votes)
        ordinary = item
        check("ordinary_item_motion_vote_projection", status == 200 and all(row["agenda_item_id"] == item["id"] for row in motions) and all(row["motion_id"] in {motion["id"] for motion in motions} for row in votes) and len(votes) > 0, motion_records=len(motions), vote_records=len(votes))
        break
    if ordinary is None:
        check("ordinary_item_motion_vote_projection", False)
    for label, path, method, body, extra in [
        ("proxy_rejects_mutation", "/rest/v1/agenda_items?id=eq.00000000-0000-0000-0000-000000000000", "PATCH", {"title": "BLOCKED TEST"}, {}),
        ("proxy_rejects_write_rpc", "/rest/v1/rpc/review_decision", "POST", {}, {}),
        ("proxy_rejects_foreign_origin", "/rest/v1/meetings?select=id&limit=1", "GET", None, {"Origin": "https://unrelated.example"}),
        ("proxy_rejects_unrelated_prefix", "/auth/v1/token", "POST", {}, {}),
    ]:
        status, _, _ = request(api, path, method=method, body=body, headers={**auth, **extra})
        check(label, status == 403, http_status=status)
    # A direct request cannot bypass the database's second read-only boundary.
    status, _, _ = request("http://127.0.0.1:59877", "/rpc/review_decision", method="POST", body={}, headers=auth)
    check("direct_postgrest_rejects_write_rpc", status in (401, 403, 404), http_status=status)
    status, _, _ = request("http://127.0.0.1:59877", "/agenda_items?id=eq.00000000-0000-0000-0000-000000000000", method="PATCH", body={"title": "BLOCKED TEST"}, headers={"Authorization": "Bearer " + secrets["service_role_key"]})
    check("direct_postgrest_rejects_service_role_mutation", status == 403, http_status=status)

    if not args.infrastructure_only:
        web = "http://127.0.0.1:3100"
        for name, path in [("home", "/"), ("archive_library", "/library"), ("finance_page", "/money"), ("held_item_page", f"/meetings/{HELD_MEETING}/items/J-2")]:
            status, _, html = request(web, path)
            passed = status == 200
            if name == "held_item_page":
                passed = passed and b"held for source review" in html and b"Jovanka Beckles" not in html and b"Tom Bates" not in html
            check(name, passed, http_status=status)
        if ordinary:
            status, _, _ = request(web, f"/meetings/{ordinary['meeting_id']}/items/{urllib.parse.quote(ordinary['item_number'], safe='')}")
            check("ordinary_item_page", status == 200, http_status=status)
        for name, question in [("vote_question", "Who voted on Point Molate in 2010"), ("finance_question", "Who donated to Ahmad Anderson in 2026"), ("agenda_question", "What housing decisions were made in 2026")]:
            status, _, raw = request(web, "/api/commons/search?" + urllib.parse.urlencode({"q": question}))
            data = json.loads(raw) if status == 200 else {}
            records = data.get("records", [])
            held = [row for row in records if row.get("id") == HELD_ITEM]
            passed = status == 200 and isinstance(records, list)
            if name == "vote_question":
                passed = passed and bool(held) and all(not row.get("motions") and row.get("voteSourceReview") for row in held)
            check(name, passed, http_status=status, records=len(records), known_hold_preserved=bool(held) if name == "vote_question" else None)
        status, _, raw = request(web, "/api/search?q=housing")
        search = json.loads(raw) if status == 200 else {}
        legacy_results = search.get("results", [])
        check("legacy_search_uses_keyword_results", status == 200 and bool(legacy_results) and all(row.get("match_type") == "keyword" for row in legacy_results), http_status=status, records=len(legacy_results))
        status, _, _ = request(web, "/api/operator/login", method="POST", body={"password": secrets["operator_password"]}, headers={"Origin": web})
        check("local_operator_cookie_login", status == 200, http_status=status)
        if status == 200:
            status, _, raw = request(web, "/api/operator/session")
            state = json.loads(raw) if status == 200 else {}
            check("local_operator_session", status == 200 and state.get("isOperator") is True, http_status=status)
            for name, path in [("operator_settings_read", "/api/operator/settings"), ("operator_sync_read", "/api/operator/sync-health"), ("operator_recap_read", "/api/operator/recap-state")]:
                status, _, _ = request(web, path)
                check(name, status == 200, http_status=status)
        for name, path, method, extra in [
            ("app_rejects_record_mutation", "/api/operator/settings", "PUT", {}),
            ("app_rejects_email", "/api/email/send-digest", "POST", {}),
            ("app_rejects_foreign_origin", "/api/operator/login", "POST", {"Origin": "https://unrelated.example"}),
        ]:
            status, _, _ = request(web, path, method=method, body={} if method != "GET" else None, headers=extra)
            check(name, status in (400, 401, 403, 404, 405), http_status=status)
    report = {"checked_at": int(time.time()), "all_passed": all(row["passed"] for row in checks), "infrastructure_only": args.infrastructure_only, "checks": checks, "record_payloads_printed": False, "cloud_calls": False}
    (RUNTIME / "config" / ("infrastructure-verification.json" if args.infrastructure_only else "app-verification.json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
