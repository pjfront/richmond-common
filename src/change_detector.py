"""
Source Change Detector — near-live polling for data freshness.

Checks external data sources for changes using lightweight HTTP requests,
compares against stored fingerprints in source_watch_state, and triggers
GitHub Actions when new data is detected.

Stdlib only — no pip install needed. Runs in ~10 seconds.

Usage:
    python change_detector.py              # Check all sources
    python change_detector.py --dry-run    # Check without triggering dispatches
    python change_detector.py --source escribemeetings  # Check one source
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta


# ── Configuration ─────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "pjfront/richmond-common")

# eSCRIBE
ESCRIBE_BASE = "https://pub-richmond.escribemeetings.com"
ESCRIBE_CALENDAR = f"{ESCRIBE_BASE}/MeetingsCalendarView.aspx/GetCalendarMeetings"

# NetFile
NETFILE_API = "https://netfile.com/Connect2/api"
NETFILE_AGENCY = 163

# Socrata — only check the datasets we actually sync
SOCRATA_DOMAIN = "www.transparentrichmond.org"
SOCRATA_DATASETS = {
    "expenditures": "86qj-wgke",
    "payroll": "crbs-mam9",
    "permits": "qg2r-652v",
    "licenses": "5d4s-vbti",
    "code_cases": "jemu-q7zc",
    "service_requests": "6mmc-hvjg",
    "projects": "vp6b-mw6u",
}

# NextRequest
NEXTREQUEST_BASE = "https://cityofrichmondca.nextrequest.com"

# CAL-ACCESS
CALACCESS_URL = "https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip"

# SSL context that handles government sites with incomplete cert chains
_ssl_ctx = ssl.create_default_context()


# ── HTTP Helpers (stdlib) ─────────────────────────────────────

def _get(url: str, headers: dict | None = None, timeout: int = 15) -> bytes:
    """GET request, return response body bytes."""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
        return resp.read()


def _post_json(url: str, data: dict, headers: dict | None = None, timeout: int = 15) -> dict:
    """POST JSON, return parsed response."""
    body = json.dumps(data).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
        return json.loads(resp.read())


def _head(url: str, timeout: int = 15) -> dict[str, str]:
    """HEAD request, return response headers as dict."""
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
        return dict(resp.headers)


# ── Supabase REST Helpers ─────────────────────────────────────

def _supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def read_state(source: str) -> dict | None:
    """Read fingerprint from source_watch_state via Supabase REST."""
    url = f"{SUPABASE_URL}/rest/v1/source_watch_state?source=eq.{source}&select=fingerprint,last_checked_at"
    hdrs = _supabase_headers()
    hdrs["Accept"] = "application/json"
    try:
        data = json.loads(_get(url, headers=hdrs))
        return data[0] if data else None
    except Exception as e:
        print(f"  WARNING: Could not read state for {source}: {e}")
        return None


def write_state(source: str, fingerprint: dict, changed: bool = False) -> None:
    """Upsert fingerprint to source_watch_state via Supabase REST."""
    now = datetime.utcnow().isoformat() + "Z"
    row = {
        "source": source,
        "fingerprint": fingerprint,
        "last_checked_at": now,
        "updated_at": now,
    }
    if changed:
        row["last_changed_at"] = now

    url = f"{SUPABASE_URL}/rest/v1/source_watch_state"
    hdrs = _supabase_headers()
    hdrs["Prefer"] = "resolution=merge-duplicates,return=minimal"
    body = json.dumps(row).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10, context=_ssl_ctx)
    except Exception as e:
        print(f"  WARNING: Could not write state for {source}: {e}")


# ── GitHub Dispatch ───────────────────────────────────────────

def trigger_dispatch(source: str, dry_run: bool = False) -> None:
    """Trigger data-sync.yml via repository_dispatch."""
    if dry_run:
        print(f"  DRY RUN: would dispatch sync-data for {source}")
        return

    if not GITHUB_TOKEN:
        print(f"  WARNING: No GITHUB_TOKEN — cannot dispatch for {source}")
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    payload = {
        "event_type": "sync-data",
        "client_payload": {
            "source": source,
            "sync_type": "incremental",
            "trigger_source": "change_detector",
            "enrich": "true",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    hdrs = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        urllib.request.urlopen(req, timeout=15)
        print(f"  ✓ Dispatched sync for {source}")
    except urllib.error.HTTPError as e:
        print(f"  ERROR dispatching for {source}: {e.code} {e.reason}")


# ── Source Checkers ───────────────────────────────────────────

def check_escribemeetings() -> dict:
    """Check eSCRIBE for upcoming meetings in the next 14 days.

    Returns a fingerprint: {meeting_count, meeting_keys}.
    meeting_keys is a sorted list of "date|name" strings for dedup.
    """
    today = date.today()
    end = today + timedelta(days=14)

    # eSCRIBE requires a cookie from the calendar page first
    # Use a simple GET to warm the session, then POST
    try:
        # Get cookies
        cookie_req = urllib.request.Request(
            f"{ESCRIBE_BASE}/MeetingsCalendarView.aspx",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        opener.open(cookie_req, timeout=15)

        # Calendar API call
        payload = json.dumps({
            "calendarStartDate": today.isoformat(),
            "calendarEndDate": end.isoformat(),
        }).encode("utf-8")
        cal_req = urllib.request.Request(
            ESCRIBE_CALENDAR,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        resp = opener.open(cal_req, timeout=15)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"  ERROR checking eSCRIBE: {e}")
        return {}

    meetings = data.get("d", [])
    keys = sorted(
        f"{m.get('StartDate', '')[:10]}|{m.get('MeetingName', '')}"
        for m in meetings
        if not m.get("IsCancelled")
    )
    return {"meeting_count": len(keys), "meeting_keys": keys}


def check_netfile() -> dict:
    """Check NetFile transaction counts for types 0 (monetary) and 1 (non-monetary).

    Returns a fingerprint: {type_0_count, type_1_count}.
    """
    counts = {}
    for tx_type in [0, 1]:
        try:
            resp = _post_json(
                f"{NETFILE_API}/public/campaign/search/transaction/query?format=json",
                {
                    "Agency": NETFILE_AGENCY,
                    "PageSize": 1,
                    "CurrentPageIndex": 0,
                    "TransactionType": tx_type,
                    "SortOrder": 1,
                },
            )
            counts[f"type_{tx_type}_count"] = resp.get("totalMatchingCount", 0)
        except Exception as e:
            print(f"  ERROR checking NetFile type {tx_type}: {e}")
            return {}

    return counts


def check_socrata() -> dict:
    """Check Socrata dataset modification timestamps.

    Returns a fingerprint: {dataset_name: rows_updated_at, ...}.
    """
    timestamps = {}
    for name, dataset_id in SOCRATA_DATASETS.items():
        try:
            url = f"https://{SOCRATA_DOMAIN}/api/views/{dataset_id}.json?$$exclude_system_fields=false"
            data = json.loads(_get(url, headers={"Accept": "application/json"}))
            updated = data.get("rowsUpdatedAt", data.get("viewLastModified", 0))
            timestamps[name] = updated
        except Exception as e:
            print(f"  WARNING: Could not check Socrata {name}: {e}")

    return timestamps


def check_nextrequest() -> dict:
    """Check NextRequest total request count.

    Returns a fingerprint: {total_count}.
    """
    try:
        url = f"{NEXTREQUEST_BASE}/client/requests?page_number=1"
        data = json.loads(_get(url, headers={"Accept": "application/json"}))
        return {"total_count": data.get("total_count", 0)}
    except Exception as e:
        print(f"  ERROR checking NextRequest: {e}")
        return {}


def check_calaccess() -> dict:
    """Check CAL-ACCESS bulk file modification date via HEAD request.

    Returns a fingerprint: {last_modified}.
    """
    try:
        headers = _head(CALACCESS_URL)
        return {"last_modified": headers.get("Last-Modified", "")}
    except Exception as e:
        print(f"  ERROR checking CAL-ACCESS: {e}")
        return {}


# ── Source Registry ───────────────────────────────────────────

# Maps source name → (checker function, data_sync source name for dispatch)
WATCHERS = {
    "escribemeetings": (check_escribemeetings, "escribemeetings"),
    "netfile": (check_netfile, "netfile"),
    "socrata": (check_socrata, None),  # Socrata has 6 sub-sources; handled specially
    "nextrequest": (check_nextrequest, "nextrequest"),
    "calaccess": (check_calaccess, "calaccess"),
}

# Socrata dataset → data_sync source mapping
SOCRATA_SOURCE_MAP = {
    "expenditures": "socrata_expenditures",
    "payroll": "socrata_payroll",
    "permits": "socrata_permits",
    "licenses": "socrata_licenses",
    "code_cases": "socrata_code_cases",
    "service_requests": "socrata_service_requests",
    "projects": "socrata_projects",
}


# ── Main Loop ─────────────────────────────────────────────────

def check_all(dry_run: bool = False, only_source: str | None = None) -> dict:
    """Check all sources for changes. Returns summary."""
    summary = {"checked": 0, "changed": 0, "dispatched": 0, "errors": 0}

    sources_to_check = {only_source: WATCHERS[only_source]} if only_source else WATCHERS

    for name, (checker, dispatch_source) in sources_to_check.items():
        print(f"Checking {name}...")
        summary["checked"] += 1

        new_fingerprint = checker()
        if not new_fingerprint:
            summary["errors"] += 1
            continue

        # Special handling for Socrata: compare per-dataset
        if name == "socrata":
            old_state = read_state("socrata")
            old_fp = old_state["fingerprint"] if old_state else {}

            changed_datasets = []
            for ds_name, new_ts in new_fingerprint.items():
                old_ts = old_fp.get(ds_name)
                if old_ts is None or new_ts != old_ts:
                    changed_datasets.append(ds_name)

            if changed_datasets:
                print(f"  CHANGED: {', '.join(changed_datasets)}")
                summary["changed"] += 1
                for ds_name in changed_datasets:
                    sync_source = SOCRATA_SOURCE_MAP.get(ds_name)
                    if sync_source:
                        trigger_dispatch(sync_source, dry_run=dry_run)
                        summary["dispatched"] += 1
                write_state("socrata", new_fingerprint, changed=True)
            else:
                print(f"  No changes")
                write_state("socrata", new_fingerprint, changed=False)
            continue

        # Standard sources: compare full fingerprint
        old_state = read_state(name)
        old_fp = old_state["fingerprint"] if old_state else {}

        if old_fp and new_fingerprint == old_fp:
            print(f"  No changes")
            write_state(name, new_fingerprint, changed=False)
        else:
            if old_fp:
                print(f"  CHANGED: {_diff_summary(old_fp, new_fingerprint)}")
            else:
                print(f"  First check — seeding state")
            summary["changed"] += 1
            write_state(name, new_fingerprint, changed=True)

            # Don't dispatch on first check (seeding) — only on actual changes
            if old_fp and dispatch_source:
                trigger_dispatch(dispatch_source, dry_run=dry_run)
                summary["dispatched"] += 1

    return summary


def _diff_summary(old: dict, new: dict) -> str:
    """Human-readable summary of what changed between fingerprints."""
    diffs = []
    for key in set(list(old.keys()) + list(new.keys())):
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                delta = new_val - old_val
                diffs.append(f"{key}: {old_val} → {new_val} ({'+' if delta > 0 else ''}{delta})")
            else:
                diffs.append(f"{key} changed")
    return "; ".join(diffs) if diffs else "fingerprint changed"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Source change detector")
    parser.add_argument("--dry-run", action="store_true", help="Check without dispatching")
    parser.add_argument("--source", choices=list(WATCHERS.keys()), help="Check a single source")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        sys.exit(1)

    print(f"Source Change Detector — {datetime.utcnow().isoformat()}Z")
    print(f"{'=' * 50}")

    summary = check_all(dry_run=args.dry_run, only_source=args.source)

    print(f"\n{'=' * 50}")
    print(f"Checked: {summary['checked']} | Changed: {summary['changed']} | "
          f"Dispatched: {summary['dispatched']} | Errors: {summary['errors']}")

    if summary["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
