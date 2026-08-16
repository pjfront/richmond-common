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

import hashlib
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from source_fingerprints import escribe_meeting_revision


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
NEXTREQUEST_MAX_CHANGE_ATTEMPTS = 3
OUTBOX_RETRY_DRAIN_LIMIT = 1

# CAL-ACCESS
CALACCESS_URL = "https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip"

# SSL context that handles government sites with incomplete cert chains
_ssl_ctx = ssl.create_default_context()


class StateStoreError(RuntimeError):
    """Raised when watcher state cannot be read or persisted safely."""


class OutboxStoreError(RuntimeError):
    """Raised when durable source-change work cannot be persisted or leased."""


def _max_change_attempts(source: str) -> int:
    """Return the durable automated attempt budget for a source."""
    if source == "nextrequest":
        return NEXTREQUEST_MAX_CHANGE_ATTEMPTS
    return 5


# ── HTTP Helpers (stdlib) ─────────────────────────────────────

_DEFAULT_UA = "RichmondCommons/1.0 (+https://richmondcommons.org)"


def _get(url: str, headers: dict | None = None, timeout: int = 15) -> bytes:
    """GET request, return response body bytes."""
    hdrs = {"User-Agent": _DEFAULT_UA, **(headers or {})}
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
        return resp.read()


def _post_json(url: str, data: dict, headers: dict | None = None, timeout: int = 15) -> dict:
    """POST JSON, return parsed response."""
    body = json.dumps(data).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "User-Agent": _DEFAULT_UA, **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
        return json.loads(resp.read())


def _head(url: str, timeout: int = 15) -> dict[str, str]:
    """HEAD request, return response headers as dict."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _DEFAULT_UA})
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
        raise StateStoreError(f"Could not read state for {source}: {e}") from e


def write_state(source: str, fingerprint: dict, changed: bool = False) -> None:
    """Upsert fingerprint to source_watch_state via Supabase REST."""
    now = datetime.now(timezone.utc).isoformat()
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
        with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx):
            pass
    except Exception as e:
        raise StateStoreError(f"Could not write state for {source}: {e}") from e


def enqueue_change_job(
    *,
    change_id: str,
    source: str,
    watcher_source: str,
    fingerprint: dict,
) -> None:
    """Persist an idempotent source-change obligation before dispatching it."""
    row = {
        "change_id": change_id,
        "city_fips": "0660620",
        "source": source,
        "watcher_source": watcher_source,
        "fingerprint": fingerprint,
        # NextRequest failures are commonly portal-rate or pagination-state
        # failures. A smaller durable budget prevents one observation from
        # repeatedly replaying a third-party portal while keeping the row for
        # manual reconciliation after exhaustion.
        "max_attempts": _max_change_attempts(source),
    }
    url = (
        f"{SUPABASE_URL}/rest/v1/source_change_jobs"
        "?on_conflict=change_id"
    )
    headers = _supabase_headers()
    headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"
    req = urllib.request.Request(
        url,
        data=json.dumps(row).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx):
            pass
    except Exception as exc:
        raise OutboxStoreError(
            f"Could not enqueue source change {change_id}: {exc}"
        ) from exc


def _outbox_rpc(function_name: str, payload: dict) -> list[dict]:
    """Call a private source-change RPC through PostgREST."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/{function_name}"
    headers = _supabase_headers()
    headers["Accept"] = "application/json"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else []
    except Exception as exc:
        raise OutboxStoreError(
            f"Could not call outbox RPC {function_name}: {exc}"
        ) from exc


def claim_due_change_jobs(
    change_id: str | None = None,
    *,
    limit: int = OUTBOX_RETRY_DRAIN_LIMIT,
) -> list[dict]:
    """Lease due/stale jobs for dispatch and increment their attempt count.

    Backlog draining is deliberately one-at-a-time. New observations still
    claim their exact row immediately, while a detector poll cannot fan a
    retry backlog into another repository_dispatch wave.
    """
    return _outbox_rpc(
        "claim_due_source_change_jobs",
        {
            "p_change_id": change_id,
            "p_limit": limit,
            "p_lease_minutes": 360,
        },
    )


def release_change_job_for_retry(
    change_id: str,
    error: str,
    dispatch_generation: int,
) -> dict | None:
    """Release an ambiguous/failed dispatch to bounded backoff."""
    rows = _outbox_rpc(
        "retry_source_change_job",
        {
            "p_change_id": change_id,
            "p_error": error,
            "p_pipeline_run_id": None,
            "p_dispatch_generation": dispatch_generation,
        },
    )
    return rows[0] if rows else None


# ── GitHub Dispatch ───────────────────────────────────────────

_EVENT_BUDGET_USD = {
    "netfile": "0.50",
    "escribemeetings": "0.30",
    "nextrequest": "0.10",
    "calaccess": "0.10",
    "socrata_expenditures": "0.10",
    "socrata_payroll": "0.10",
    "socrata_permits": "0.10",
    "socrata_licenses": "0.10",
    "socrata_code_cases": "0.10",
    "socrata_service_requests": "0.10",
    "socrata_projects": "0.10",
}
_DEFAULT_EVENT_BUDGET_USD = "0.50"


def make_change_id(
    source: str,
    fingerprint: dict,
    generation: str | None = None,
) -> str:
    """Return an idempotency key stable only until watcher state advances.

    Fingerprints can legitimately oscillate (A -> B -> A -> B). Including the
    prior state's ``last_checked_at`` prevents a later B from colliding with an
    already-succeeded historical B, while remaining stable if the state write
    fails and the same observation is retried.
    """
    canonical = json.dumps(
        {"fingerprint": fingerprint, "generation": generation},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(f"{source}\0{canonical}".encode("utf-8")).hexdigest()


def trigger_dispatch(
    source: str,
    dry_run: bool = False,
    change_id: str | None = None,
    dispatch_generation: int | None = None,
) -> bool:
    """Trigger data-sync.yml via ``repository_dispatch``.

    Return ``True`` only when GitHub accepted the dispatch (or when a dry
    run confirms what would be dispatched). A missing token or network
    failure returns ``False`` so callers cannot report a false success.
    """
    if dry_run:
        print(f"  DRY RUN: would dispatch sync-data for {source}")
        return True

    if not GITHUB_TOKEN:
        print(f"  WARNING: No GITHUB_TOKEN — cannot dispatch for {source}")
        return False
    if change_id and (
        dispatch_generation is None or dispatch_generation < 1
    ):
        print("  ERROR: durable dispatch is missing a positive generation")
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    client_payload = {
        "source": source,
        "sync_type": "incremental",
        "trigger_source": "change_detector",
        "enrich": "true",
        "event_budget_usd": _EVENT_BUDGET_USD.get(source, _DEFAULT_EVENT_BUDGET_USD),
    }
    if change_id:
        client_payload["change_id"] = change_id
        client_payload["dispatch_generation"] = dispatch_generation
    payload = {
        "event_type": "sync-data",
        "client_payload": client_payload,
    }
    body = json.dumps(payload).encode("utf-8")
    hdrs = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
        print(f"  ✓ Dispatched sync for {source}")
        return True
    except urllib.error.HTTPError as e:
        print(f"  ERROR dispatching for {source}: {e.code} {e.reason}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"  ERROR dispatching for {source}: {e}")
    return False


def _dispatch_claimed_jobs(jobs: list[dict], summary: dict) -> None:
    """Dispatch leased jobs and release failures without losing the obligation."""
    for job in jobs:
        change_id = job.get("change_id")
        source = job.get("source")
        dispatch_generation = job.get("dispatch_generation")
        if job.get("status") == "dead_letter":
            print(
                f"  ERROR: source change {change_id} for {source} exhausted "
                f"{job.get('attempt_count')} attempts; dead-lettered"
            )
            summary["dead_lettered"] += 1
            summary["errors"] += 1
            continue

        if (
            not change_id
            or not source
            or not isinstance(dispatch_generation, int)
            or dispatch_generation < 1
        ):
            print(
                "  ERROR: claimed outbox row is missing change_id, source, "
                "or dispatch_generation"
            )
            summary["outbox_errors"] += 1
            summary["errors"] += 1
            continue

        if trigger_dispatch(
            source,
            change_id=change_id,
            dispatch_generation=dispatch_generation,
        ):
            summary["dispatched"] += 1
            continue

        summary["dispatch_errors"] += 1
        summary["errors"] += 1
        try:
            released = release_change_job_for_retry(
                change_id,
                "GitHub repository_dispatch was not acknowledged",
                dispatch_generation,
            )
            if released and released.get("status") == "dead_letter":
                print(
                    f"  ERROR: source change {change_id} exhausted attempts "
                    "after dispatch failure; dead-lettered"
                )
                summary["dead_lettered"] += 1
        except OutboxStoreError as exc:
            # The dispatch lease remains durable and will expire into another
            # retry even when this immediate release cannot be persisted.
            print(f"  ERROR: {exc}")
            summary["outbox_errors"] += 1
            summary["errors"] += 1


def _claim_and_dispatch_due(summary: dict, change_id: str | None = None) -> None:
    """Lease and dispatch either one new job or the detector's retry backlog."""
    try:
        jobs = claim_due_change_jobs(change_id)
    except OutboxStoreError as exc:
        print(f"  ERROR: {exc}")
        summary["outbox_errors"] += 1
        summary["errors"] += 1
        return
    _dispatch_claimed_jobs(jobs, summary)


def _queue_source_change(
    *,
    source: str,
    watcher_source: str,
    fingerprint: dict,
    generation: str | None,
    summary: dict,
    dry_run: bool,
) -> bool:
    """Persist before dispatch; return whether watcher state may advance."""
    change_id = make_change_id(source, fingerprint, generation)
    if dry_run:
        if trigger_dispatch(source, dry_run=True, change_id=change_id):
            summary["dispatched"] += 1
        return True

    try:
        enqueue_change_job(
            change_id=change_id,
            source=source,
            watcher_source=watcher_source,
            fingerprint=fingerprint,
        )
    except OutboxStoreError as exc:
        print(f"  ERROR: {exc}")
        summary["outbox_errors"] += 1
        summary["errors"] += 1
        return False

    # The durable row is now the acknowledgement boundary. Even if GitHub is
    # unavailable, advancing source_watch_state is safe because the next poll
    # drains this same job from retry_wait or its expired dispatch lease.
    _claim_and_dispatch_due(summary, change_id)
    return True


# ── Source Checkers ───────────────────────────────────────────

def check_escribemeetings() -> dict:
    """Check eSCRIBE meeting identity plus published agenda revisions.

    Calendar document links detect agenda publication/replacement. For each
    published agenda, a normalized HTML hash also detects in-place amendments
    that retain the same eSCRIBE document ID.
    """
    today = date.today()
    # The daily/weekly agenda sync owns historical reconciliation. Keep the
    # 15-minute watcher bounded to the imminent publication window so it does
    # not download two months of agenda HTML on every poll.
    start = today
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
            "calendarStartDate": start.isoformat(),
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
    if not isinstance(meetings, list):
        print("  ERROR checking eSCRIBE: calendar response is malformed")
        return {}
    meetings = [meeting for meeting in meetings if isinstance(meeting, dict)]
    keys = sorted(
        f"{m.get('StartDate', '')[:10]}|{m.get('MeetingName', '')}"
        for m in meetings
    )
    revisions = []
    try:
        for meeting in meetings:
            agenda_html = None
            if (
                meeting.get("HasAgenda") is True
                and meeting.get("IsCancelled") is not True
            ):
                meeting_id = str(meeting.get("ID") or "").strip()
                if not meeting_id:
                    raise ValueError("published eSCRIBE agenda is missing ID")
                page_req = urllib.request.Request(
                    (
                        f"{ESCRIBE_BASE}/Meeting.aspx?Id={meeting_id}"
                        "&Agenda=Agenda&lang=English"
                    ),
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with opener.open(page_req, timeout=15) as page_resp:
                    agenda_html = page_resp.read().decode("utf-8", errors="replace")
            revision = escribe_meeting_revision(
                meeting,
                agenda_html=agenda_html,
            )
            revisions.append({
                "id": meeting.get("ID"),
                "revision_sha256": revision["revision_sha256"],
            })
    except Exception as exc:
        # Never advance to a partial agenda revision set. The next 15-minute
        # poll retries the complete observation.
        print(f"  ERROR checking eSCRIBE agenda revisions: {exc}")
        return {}
    revisions.sort(key=lambda revision: str(revision.get("id") or ""))
    return {
        "meeting_count": len(keys),
        "meeting_keys": keys,
        "meeting_revisions": revisions,
    }


def check_netfile() -> dict:
    """Check NetFile state across BOTH electronic transactions and paper filings.

    The transaction counts (types 0 and 1) cover e-filed contributions
    that NetFile exposes via its API. Paper-filed forms (460s, 497s as
    PDFs) live separately in the rolling filing RSS feed — covered by
    a hash of the latest 50 filing IDs. During election season 497s
    arrive sometimes daily; without RSS coverage here, paper-filed
    gifts wait for the next scheduled sync (up to 24h delay).

    Returns a fingerprint:
      {type_0_count, type_1_count, paper_filing_count, paper_filing_hash}
    """
    counts: dict = {}
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

    # Paper-filing RSS — a rolling window of recent filings (max 1000,
    # typically updated to ~15 days back). We hash the most recent
    # filing IDs so a new 460/497 changes the fingerprint immediately.
    try:
        import hashlib
        import xml.etree.ElementTree as ET

        rss_url = f"{NETFILE_API}/public/list/filing/rss/RICH/campaign.xml"
        rss_xml = _get(rss_url)
        root = ET.fromstring(rss_xml)
        filing_ids = []
        for item in root.iter("item"):
            link = (item.findtext("link") or "").strip()
            if link:
                fid = link.rsplit("/", 1)[-1]
                if fid:
                    filing_ids.append(fid)

        # Take the 50 most recent filing IDs (they're date-sorted in
        # the RSS feed) and hash them. New filings push old ones out
        # of the window, but since we always hash the same window
        # size, *any* new arrival changes the hash deterministically.
        recent_ids = filing_ids[:50]
        joined = ",".join(recent_ids).encode("utf-8")
        counts["paper_filing_count"] = len(filing_ids)
        counts["paper_filing_hash"] = hashlib.sha256(joined).hexdigest()[:16]
    except Exception as e:
        print(f"  WARNING: Could not check NetFile filing RSS: {e}")
        # Don't return {} — we still have transaction-count signal.

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
    """Check NextRequest request revisions and newest public documents.

    The request list has no global updated-at field, so hash its newest page to
    catch status/due-date/detail changes there. A separately sorted public
    document page catches releases attached to older requests. The full sync
    complements this watcher with bounded database-backed open-request detail
    reconciliation.
    """
    try:
        url = f"{NEXTREQUEST_BASE}/client/requests?page_number=1"
        data = json.loads(_get(url, headers={"Accept": "application/json"}))
        total_count = data.get("total_count")
        requests = data.get("requests")
        if (
            isinstance(total_count, bool)
            or not isinstance(total_count, int)
            or total_count < 0
            or not isinstance(requests, list)
        ):
            raise ValueError("request-list response is malformed")
        recent_requests = []
        for request in requests:
            if not isinstance(request, dict):
                raise ValueError("request-list row is malformed")
            recent_requests.append({
                "department_names": request.get("department_names"),
                "due_date": request.get("due_date"),
                "id": request.get("id"),
                "request_date": request.get("request_date"),
                "request_state": request.get("request_state"),
                "request_text": request.get("request_text"),
                "visibility": request.get("visibility"),
            })
        fingerprint = {
            "total_count": total_count,
            "recent_requests_hash": hashlib.sha256(
                json.dumps(
                    recent_requests,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest(),
        }
    except Exception as e:
        print(f"  ERROR checking NextRequest: {e}")
        return {}

    try:
        docs_url = (
            f"{NEXTREQUEST_BASE}/client/documents?sort_field=created_at"
            "&sort_order=desc&page_size=50&page_number=1"
        )
        docs_data = json.loads(
            _get(docs_url, headers={"Accept": "application/json"})
        )
        document_count = docs_data.get("total_count")
        documents = docs_data.get("documents")
        if (
            isinstance(document_count, bool)
            or not isinstance(document_count, int)
            or document_count < 0
            or not isinstance(documents, list)
        ):
            raise ValueError("public-document response is malformed")
        recent_documents = []
        for document in documents[:50]:
            if not isinstance(document, dict):
                raise ValueError("public-document row is malformed")
            recent_documents.append({
                "created_at": document.get("created_at"),
                "doc_date": document.get("doc_date"),
                "id": document.get("id"),
                "pretty_id": document.get("pretty_id"),
                "redacted_at": document.get("redacted_at"),
                "state": document.get("state"),
                "title": document.get("title"),
            })
        fingerprint.update({
            "public_document_count": document_count,
            "recent_documents_hash": hashlib.sha256(
                json.dumps(
                    recent_documents,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest(),
        })
    except Exception as exc:
        # Preserve the stored document keys through check_all's partial-key
        # merge and still retain the independently valid request signal.
        print(f"  WARNING: Could not check NextRequest documents: {exc}")
    return fingerprint


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

def _read_state_safely(source: str, summary: dict) -> tuple[bool, dict | None]:
    """Read state while keeping storage failures distinct from a missing row."""
    try:
        return True, read_state(source)
    except StateStoreError as exc:
        print(f"  ERROR: {exc}")
        summary["state_errors"] += 1
        summary["errors"] += 1
        return False, None


def _write_state_safely(
    source: str,
    fingerprint: dict,
    *,
    changed: bool,
    summary: dict,
) -> bool:
    """Persist state and make every failed acknowledgement actionable."""
    try:
        write_state(source, fingerprint, changed=changed)
        return True
    except StateStoreError as exc:
        print(f"  ERROR: {exc}")
        summary["state_errors"] += 1
        summary["errors"] += 1
        return False


def check_all(dry_run: bool = False, only_source: str | None = None) -> dict:
    """Check all sources for changes. Returns summary."""
    summary = {
        "checked": 0,
        "changed": 0,
        "dispatched": 0,
        "errors": 0,
        "check_errors": 0,
        "dispatch_errors": 0,
        "state_errors": 0,
        "outbox_errors": 0,
        "dead_lettered": 0,
    }

    # Delivery failures must be retried independently of later source changes.
    if not dry_run:
        _claim_and_dispatch_due(summary)

    sources_to_check = {only_source: WATCHERS[only_source]} if only_source else WATCHERS

    for name, (checker, dispatch_source) in sources_to_check.items():
        print(f"Checking {name}...")
        summary["checked"] += 1

        new_fingerprint = checker()
        if not new_fingerprint:
            summary["check_errors"] += 1
            summary["errors"] += 1
            continue

        # Special handling for Socrata: compare and dispatch per dataset.
        if name == "socrata":
            state_ok, old_state = _read_state_safely("socrata", summary)
            if not state_ok:
                continue
            old_fp = (old_state or {}).get("fingerprint") or {}
            effective_fingerprint = {**old_fp, **new_fingerprint}

            changed_datasets = [
                ds_name
                for ds_name, new_ts in new_fingerprint.items()
                if old_fp.get(ds_name) is None or new_ts != old_fp.get(ds_name)
            ]

            if changed_datasets:
                print(f"  CHANGED: {', '.join(changed_datasets)}")
                summary["changed"] += 1
                persisted_fingerprint = dict(effective_fingerprint)
                any_queued = False
                for ds_name in changed_datasets:
                    sync_source = SOCRATA_SOURCE_MAP.get(ds_name)
                    if not sync_source:
                        continue
                    event_fingerprint = {
                        "dataset": ds_name,
                        "observed_value": new_fingerprint[ds_name],
                    }
                    if _queue_source_change(
                        source=sync_source,
                        watcher_source="socrata",
                        fingerprint=event_fingerprint,
                        generation=(old_state or {}).get("last_checked_at"),
                        summary=summary,
                        dry_run=dry_run,
                    ):
                        any_queued = True
                    else:
                        # Without a durable obligation, retain the old value so
                        # the next detector run observes this dataset again.
                        if ds_name in old_fp:
                            persisted_fingerprint[ds_name] = old_fp[ds_name]
                        else:
                            persisted_fingerprint.pop(ds_name, None)
                if not dry_run:
                    _write_state_safely(
                        "socrata",
                        persisted_fingerprint,
                        changed=any_queued,
                        summary=summary,
                    )
            else:
                print("  No changes")
                if not dry_run:
                    _write_state_safely(
                        "socrata",
                        effective_fingerprint,
                        changed=False,
                        summary=summary,
                    )
            continue

        # Standard sources compare only keys observed in both snapshots. New
        # keys are a schema upgrade, not a source change. Missing new keys are
        # treated as a partial observation and preserved from the old state.
        state_ok, old_state = _read_state_safely(name, summary)
        if not state_ok:
            continue
        old_fp = (old_state or {}).get("fingerprint") or {}
        effective_fingerprint = {**old_fp, **new_fingerprint}

        if old_fp:
            shared_keys = set(old_fp) & set(new_fingerprint)
            real_change = any(
                old_fp.get(key) != new_fingerprint.get(key) for key in shared_keys
            )
            schema_upgrade = bool(set(new_fingerprint) - set(old_fp))
        else:
            real_change = False
            schema_upgrade = False

        if old_fp and not real_change:
            if schema_upgrade:
                print("  No real changes (fingerprint schema upgraded — saving silently)")
            else:
                print("  No changes")
            if not dry_run:
                _write_state_safely(
                    name,
                    effective_fingerprint,
                    changed=False,
                    summary=summary,
                )
            continue

        if old_fp:
            print(f"  CHANGED: {_diff_summary(old_fp, effective_fingerprint)}")
        else:
            print("  First check — seeding state")
        summary["changed"] += 1

        # Don't dispatch on first check (seeding) — only on actual changes.
        if old_fp and dispatch_source:
            if _queue_source_change(
                source=dispatch_source,
                watcher_source=name,
                fingerprint=effective_fingerprint,
                generation=(old_state or {}).get("last_checked_at"),
                summary=summary,
                dry_run=dry_run,
            ):
                if not dry_run:
                    _write_state_safely(
                        name,
                        effective_fingerprint,
                        changed=True,
                        summary=summary,
                    )
        elif not dry_run:
            _write_state_safely(
                name,
                effective_fingerprint,
                changed=True,
                summary=summary,
            )

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

    print(f"Source Change Detector — {datetime.now(timezone.utc).isoformat()}")
    print(f"{'=' * 50}")

    summary = check_all(dry_run=args.dry_run, only_source=args.source)

    print(f"\n{'=' * 50}")
    print(f"Checked: {summary['checked']} | Changed: {summary['changed']} | "
          f"Dispatched: {summary['dispatched']} | Errors: {summary['errors']}")

    # Delivery/outbox failures and new dead letters are always actionable.
    # Source-check timeouts remain actionable only when every checker failed.
    all_checks_failed = (
        summary["check_errors"] > 0
        and summary["check_errors"] == summary["checked"]
    )
    if (
        summary["dispatch_errors"] > 0
        or summary["state_errors"] > 0
        or summary["outbox_errors"] > 0
        or summary["dead_lettered"] > 0
        or all_checks_failed
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
