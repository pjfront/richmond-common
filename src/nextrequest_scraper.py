"""
Richmond Common — NextRequest/CPRA Scraper

Uses NextRequest's public client JSON API to fetch CPRA request
metadata, documents, and status for compliance tracking and
cross-referencing. No Playwright or browser required.

API endpoints (discovered from SPA network calls):
  - GET /client/requests?page_number=N       → paginated list (100/page)
  - GET /client/requests/{id}                → request detail
  - GET /client/requests/{id}/timeline       → request timeline/history
  - GET /client/request_documents?request_id={id}  → documents for a request (25/page, S3 URLs)

Architecture:
  - Fetch layer: _fetch_request_list, _fetch_request_detail (HTTP JSON)
  - Transform layer: _transform_list_item, _transform_detail
  - Document handling: download_document, extract_document_text
  - Orchestration: scrape_all, save_to_db
  - DB operations: save_to_db (upsert)

Usage:
  python nextrequest_scraper.py --list
  python nextrequest_scraper.py --since 2026-01-01
  python nextrequest_scraper.py --request 26-414
  python nextrequest_scraper.py --stats
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path

import requests as http_client
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

BASE_URL = "https://cityofrichmondca.nextrequest.com"
CLIENT_API = "/client/requests"
CITY_FIPS = "0660620"
DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw" / "nextrequest"
PAGE_SIZE = 100  # NextRequest returns 100 per page

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RichmondCommon/1.0",
    "Accept": "application/json",
}

RATE_LIMIT_MS = 500  # ms between API calls
MAX_AUTHORITATIVE_SHRINK_FRACTION = 0.25

NEXTREQUEST_PLATFORM_PROFILE = {
    "platform": "NextRequest (CivicPlus)",
    "url_pattern": "https://{city_slug}.nextrequest.com",
    "client_api": "/client/requests",
    "detail_api": "/client/requests/{request_id}",
    "timeline_api": "/client/requests/{request_id}/timeline",
    "documents_api": "/client/request_documents",
    "public_documents_api": "/client/documents",
    "document_download_url": "/documents/{document_id}/download",
    "spa": True,
    "api_v2_exists": True,
    "api_v2_base": "/api/v2/",
    "notes": (
        "SaaS platform — public client JSON API discovered from SPA. "
        "Identical across all cities. Documents API discovered April 2026 "
        "by reverse-engineering Vue.js SPA bundle (api-CqnnFGtv.js). "
        "Documents endpoint returns S3 direct download URLs (asset_url field)."
    ),
}


# ── Config resolution ────────────────────────────────────────

def _resolve_nextrequest_config(
    city_fips: str | None = None,
) -> tuple[str, str]:
    """Resolve base_url and city_fips from registry or module defaults.

    Returns (base_url, city_fips).
    """
    if city_fips is not None:
        from city_config import get_data_source_config
        cfg = get_data_source_config(city_fips, "nextrequest")
        return cfg["base_url"], city_fips
    return BASE_URL, CITY_FIPS


# ── Date parsing ──────────────────────────────────────────────

def _parse_date(date_str: str | None) -> str | None:
    """Parse MM/DD/YYYY or other formats to YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning(f"Could not parse date: {date_str!r}")
    return None


def _compute_days_to_close(submitted: str | None, closed: str | None) -> int | None:
    """Compute days between submitted and closed dates."""
    if not submitted or not closed:
        return None
    try:
        d1 = datetime.strptime(submitted, "%Y-%m-%d").date()
        d2 = datetime.strptime(closed, "%Y-%m-%d").date()
        return (d2 - d1).days
    except ValueError:
        return None


def _strip_html(html_str: str | None) -> str:
    """Strip HTML tags from a string, returning plain text."""
    if not html_str:
        return ""
    return BeautifulSoup(html_str, "html.parser").get_text(separator=" ", strip=True)


def _is_public_visibility(value: object) -> bool:
    """Allow only observed, explicit NextRequest public states."""
    return _visibility_state(value) == "public"


def _visibility_state(value: object) -> str:
    """Classify visibility without conflating schema drift with retraction."""
    normalized = str(value or "").strip().lower().replace("_", " ")
    if normalized in {
        "published",
        "public",
        # Richmond, California's public request-list endpoint exposes three
        # rows as "Published - department only"; the corresponding public
        # detail endpoint reports visibility="department_published" plus
        # request_visibility="Published". Both shapes were observed in a
        # complete 3,005-row public listing on 2026-08-10.
        "published - department only",
        "department published",
    }:
        return "public"
    if normalized in {"private", "unpublished", "hidden", "staff only"}:
        return "private"
    return "unknown"


def _combined_visibility_state(*values: object) -> str:
    """Resolve duplicated visibility fields, failing closed on disagreement."""
    present = [
        value for value in values
        if value is not None and str(value).strip()
    ]
    if not present:
        return "unknown"
    states = {_visibility_state(value) for value in present}
    if "unknown" in states or len(states) != 1:
        return "unknown"
    return states.pop()


def _assert_conservative_authoritative_size(
    *,
    label: str,
    observed_unique: int,
    live_unique_baseline: int,
) -> None:
    """Reject destructive snapshots that collapse against live DB state.

    Source-reported totals prove only that pagination matched the current API
    response.  They cannot prove that a 200-empty response, a server-side
    filter change, or an enum drift did not hide records.  The active local
    corpus is therefore an independent safety rail for every database size,
    including small test/new-city corpora where a fixed minimum would fail.
    """
    if live_unique_baseline <= 0:
        return
    minimum_safe = math.ceil(
        live_unique_baseline * (1 - MAX_AUTHORITATIVE_SHRINK_FRACTION)
    )
    if observed_unique < minimum_safe:
        raise RuntimeError(
            f"Refusing implausible authoritative NextRequest {label} shrink "
            f"({observed_unique} observed vs {live_unique_baseline} active)"
        )


def _validated_live_overlap_counts(
    row: object,
    *,
    label: str,
) -> tuple[int, int]:
    """Validate the database cardinality/overlap proof used before deletes."""
    if (
        not isinstance(row, (tuple, list))
        or len(row) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in row
        )
    ):
        raise RuntimeError(
            f"Could not validate live NextRequest {label} reconciliation baseline"
        )
    baseline, overlap = row
    if overlap > baseline:
        raise RuntimeError(
            f"Invalid live NextRequest {label} reconciliation overlap"
        )
    return baseline, overlap


# ── JSON API fetch layer ─────────────────────────────────────

def _fetch_request_list(
    page_number: int = 1,
    *,
    base_url: str | None = None,
) -> dict:
    """Fetch paginated request list from client API.

    Returns raw JSON: {"total_count": N, "requests": [...]}.
    """
    _base = base_url or BASE_URL
    url = f"{_base}{CLIENT_API}"
    params = {}
    if page_number > 1:
        params["page_number"] = page_number

    resp = http_client.get(url, headers=HTTP_HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _fetch_request_detail(
    request_id: str,
    *,
    base_url: str | None = None,
) -> dict:
    """Fetch single request detail from client API.

    Returns raw JSON with full request fields.
    """
    _base = base_url or BASE_URL
    url = f"{_base}{CLIENT_API}/{request_id}"
    resp = http_client.get(url, headers=HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _fetch_request_timeline(
    request_id: str,
    *,
    base_url: str | None = None,
) -> dict:
    """Fetch request timeline (status history) from client API.

    Returns raw JSON: {"total_count": N, "timeline": [...], "pinned": [...]}.
    """
    _base = base_url or BASE_URL
    url = f"{_base}{CLIENT_API}/{request_id}/timeline"
    resp = http_client.get(url, headers=HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _fetch_public_document_list(
    *,
    base_url: str | None = None,
    limit: int = 50,
    page_number: int = 1,
) -> dict:
    """Fetch the newest public documents across all requests.

    The public all-documents page supports these sort parameters (confirmed
    from NextRequest's own SPA bundle).  This is the cheap bridge from a newly
    released document to an old request whose submission date is outside the
    incremental request-list window.
    """
    _base = base_url or BASE_URL
    resp = http_client.get(
        f"{_base}/client/documents",
        headers=HTTP_HEADERS,
        params={
            "sort_field": "created_at",
            "sort_order": "desc",
            "page_size": max(1, min(int(limit), 100)),
            "page_number": max(1, int(page_number)),
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
        raise ValueError("NextRequest public documents response is malformed")
    return data


def list_recent_document_request_ids(
    *,
    city_fips: str | None = None,
    limit: int = 50,
) -> list[str]:
    """Return request IDs associated with the newest public documents."""
    base_url, _fips = _resolve_nextrequest_config(city_fips)
    data = _fetch_public_document_list(base_url=base_url, limit=limit)
    request_ids = []
    seen = set()
    for document in data["documents"][:limit]:
        if not isinstance(document, dict):
            raise ValueError("NextRequest public document row is malformed")
        request_id = str(document.get("pretty_id") or "").strip()
        if request_id and request_id not in seen:
            seen.add(request_id)
            request_ids.append(request_id)
    return request_ids


def list_all_public_document_ids(
    *,
    city_fips: str | None = None,
) -> list[int]:
    """Return every current public document ID after complete pagination.

    This is the bounded global proof needed to detect a file removed from an
    old closed request, which cannot be discovered from the newest-doc page or
    a submitted-date cursor. Any malformed/partial page raises, so callers
    never advance tombstones from a partial observation.
    """
    base_url, _fips = _resolve_nextrequest_config(city_fips)
    page_size = 100
    page = 1
    max_pages = 500
    expected_total: int | None = None
    fetched_raw_count = 0
    public_ids: list[int] = []
    seen_raw_ids: set[int] = set()

    while page <= max_pages:
        data = _fetch_public_document_list(
            base_url=base_url,
            limit=page_size,
            page_number=page,
        )
        total = data.get("total_count", data.get("total_documents_count"))
        documents = data.get("documents")
        if (
            isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
            or not isinstance(documents, list)
        ):
            raise ValueError("NextRequest public-document listing is malformed")
        if expected_total is None:
            expected_total = total
            if expected_total == 0:
                raise RuntimeError(
                    "NextRequest public-document listing unexpectedly returned zero"
                )
        elif total != expected_total:
            raise RuntimeError(
                "NextRequest public-document total changed during pagination"
            )
        if not documents:
            if fetched_raw_count < total:
                raise RuntimeError(
                    "NextRequest public-document pagination ended early"
                )
            break

        for document in documents:
            if not isinstance(document, dict):
                raise ValueError("NextRequest public-document row is malformed")
            source_id = document.get("id")
            if (
                isinstance(source_id, bool)
                or not isinstance(source_id, int)
                or source_id <= 0
            ):
                raise ValueError(
                    "NextRequest public document is missing a positive source ID"
                )
            if source_id in seen_raw_ids:
                raise RuntimeError(
                    "NextRequest public-document pagination repeated a source ID"
                )
            seen_raw_ids.add(source_id)
            visibility = _combined_visibility_state(
                document.get("visibility"), document.get("state")
            )
            if visibility == "unknown":
                raise ValueError(
                    "NextRequest public-document visibility enum is unknown"
                )
            if visibility == "private":
                continue
            public_ids.append(source_id)
        fetched_raw_count += len(documents)
        if fetched_raw_count >= total:
            break
        page += 1
        time.sleep(RATE_LIMIT_MS / 1000)

    if expected_total is None or fetched_raw_count < expected_total:
        raise RuntimeError(
            "NextRequest public-document listing exceeded pagination bound"
        )
    if len(seen_raw_ids) != expected_total:
        raise RuntimeError(
            "NextRequest public-document unique coverage did not match total"
        )
    if len(public_ids) < max(1, expected_total // 2):
        raise RuntimeError(
            "NextRequest public-document visibility set shrank implausibly"
        )
    return sorted(public_ids)


def _fetch_request_documents_with_state(
    request_id: str,
    *,
    base_url: str | None = None,
) -> tuple[list[dict], int | None]:
    """Fetch all documents for a request via /client/request_documents.

    Discovered April 2026 from Vue.js SPA bundle. Returns paginated
    results (25/page) with S3 asset_url for direct download.

    Returns list of document dicts with keys: id, title, file_extension,
    asset_url, visibility, upload_date, request_id, folder_name, etc.
    """
    _base = base_url or BASE_URL
    url = f"{_base}/client/request_documents"
    all_docs: list[dict] = []
    documents_state_timestamp = None
    expected_total: int | None = None
    seen_document_ids: set[int] = set()
    state_timestamp_initialized = False
    page = 1
    max_pages = 500

    while page <= max_pages:
        params = {"request_id": request_id, "page_number": page}
        resp = http_client.get(url, headers=HTTP_HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
            raise ValueError(
                f"NextRequest documents response for {request_id} is malformed"
            )
        total = data.get("total_documents_count")
        if (
            isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
        ):
            raise ValueError(
                f"NextRequest documents total for {request_id} is malformed"
            )
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise RuntimeError(
                f"NextRequest documents total changed for {request_id}"
            )

        raw_timestamp = data.get("documents_state_timestamp")
        if raw_timestamp is not None:
            if isinstance(raw_timestamp, bool):
                raise ValueError(
                    f"NextRequest documents state for {request_id} is malformed"
                )
            try:
                page_state_timestamp = int(raw_timestamp)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"NextRequest documents state for {request_id} is malformed"
                ) from exc
        else:
            page_state_timestamp = None
        if not state_timestamp_initialized:
            documents_state_timestamp = page_state_timestamp
            state_timestamp_initialized = True
        elif page_state_timestamp != documents_state_timestamp:
            raise RuntimeError(
                f"NextRequest documents changed during pagination for {request_id}"
            )

        docs = data.get("documents", [])
        if not docs:
            if len(all_docs) < total:
                raise RuntimeError(
                    f"NextRequest documents pagination ended early for {request_id}"
                )
            break
        for document in docs:
            if not isinstance(document, dict):
                raise ValueError(
                    f"NextRequest document row for {request_id} is malformed"
                )
            document_id = document.get("id")
            if (
                isinstance(document_id, bool)
                or not isinstance(document_id, int)
                or document_id <= 0
            ):
                raise ValueError(
                    f"NextRequest document for {request_id} has no source ID"
                )
            if document_id in seen_document_ids:
                raise RuntimeError(
                    f"NextRequest documents repeated an ID for {request_id}"
                )
            seen_document_ids.add(document_id)
            all_docs.append(document)

        if len(all_docs) > total:
            raise RuntimeError(
                f"NextRequest documents exceeded total for {request_id}"
            )
        if len(all_docs) == total:
            break
        page += 1
        time.sleep(RATE_LIMIT_MS / 1000)

    if expected_total is None or len(all_docs) != expected_total:
        raise RuntimeError(
            f"NextRequest documents exceeded pagination bound for {request_id}"
        )
    if len(seen_document_ids) != expected_total:
        raise RuntimeError(
            f"NextRequest document unique coverage failed for {request_id}"
        )
    return all_docs, documents_state_timestamp


def _fetch_request_documents(
    request_id: str,
    *,
    base_url: str | None = None,
) -> list[dict]:
    """Compatibility wrapper returning only the complete document list."""
    documents, _state = _fetch_request_documents_with_state(
        request_id,
        base_url=base_url,
    )
    return documents


def _transform_document(doc: dict, *, base_url: str | None = None) -> dict:
    """Transform a document API response into our internal format.

    Extracts download URL from S3 asset_url, falling back to
    /documents/{id}/download path.
    """
    _base = base_url or BASE_URL
    doc_id = doc.get("id")
    if isinstance(doc_id, bool) or not isinstance(doc_id, int) or doc_id <= 0:
        raise ValueError("NextRequest document is missing a positive source ID")

    asset_url = doc.get("asset_url", "")
    if asset_url and asset_url.startswith("//"):
        asset_url = f"https:{asset_url}"

    download_url = asset_url or f"{_base}/documents/{doc_id}/download"

    scan = doc.get("document_scan") or {}
    upload_date_str = scan.get("upload_date") or ""
    # Parse ISO date from upload_date (e.g. "2024-05-20T11:15:27.207-07:00")
    upload_date = upload_date_str[:10] if upload_date_str else None

    return {
        "source_document_id": doc_id,
        "filename": doc.get("title", ""),
        "file_type": doc.get("file_extension", ""),
        "download_url": download_url,
        "visibility": doc.get("visibility", ""),
        "released_date": upload_date,
        "folder_name": doc.get("folder_name") or None,
    }


# ── Transform layer (JSON → internal format) ─────────────────

def _transform_list_item(item: dict, *, base_url: str | None = None) -> dict:
    """Transform a list API item into our internal RequestSummary format.

    API fields: id, request_state, request_text, department_names,
    poc_name, request_date, due_date, staff_cost, visibility, request_path.
    """
    _base = base_url or BASE_URL
    submitted_date = _parse_date(item.get("request_date"))

    return {
        "request_number": item.get("id", "unknown"),
        "request_text": (item.get("request_text") or "").strip(),
        "status": item.get("request_state", "unknown"),
        "department": (item.get("department_names") or "").strip() or None,
        "submitted_date": submitted_date,
        "due_date": _parse_date(item.get("due_date")),
        "poc_name": item.get("poc_name"),
        "portal_url": f"{_base}{item['request_path']}" if item.get("request_path") else None,
    }


def _transform_detail(detail: dict, *, base_url: str | None = None) -> dict:
    """Transform a detail API response into our internal RequestDetail format.

    Extracts closed_date from timeline if available. The detail API
    returns HTML in request_text, so we strip tags for plain text.
    """
    _base = base_url or BASE_URL
    request_id = detail.get("pretty_id", "unknown")
    submitted_date = _parse_date(detail.get("request_date"))
    due_date = _parse_date(detail.get("request_due_date"))

    # Department: detail API returns "None assigned" for empty
    dept = (detail.get("department_names") or "").strip()
    if dept.lower() in ("none assigned", ""):
        dept = None

    # Requester info
    requester = detail.get("requester") or {}
    requester_name = requester.get("name")

    # Point of contact
    poc = detail.get("poc") or {}
    poc_name = poc.get("email_or_name")

    # Request text is HTML in detail view
    request_text = _strip_html(detail.get("request_text"))

    return {
        "request_number": request_id,
        "request_text": request_text,
        "status": detail.get("request_state", "unknown"),
        "department": dept,
        "requester_name": requester_name,
        "poc_name": poc_name,
        "submitted_date": submitted_date,
        "due_date": due_date,
        "closed_date": None,  # Populated from timeline
        "days_to_close": None,  # Computed after closed_date is known
        "portal_url": f"{_base}/requests/{request_id}",
        "documents": [],
        "metadata": {
            "visibility": detail.get("visibility"),
            "staff_hours": detail.get("request_staff_hours"),
            "staff_cost": detail.get("request_staff_cost"),
            "field_values": [
                {
                    "name": fv.get("display_name"),
                    "value": fv.get("value"),
                }
                for fv in (detail.get("request_field_values") or [])
                if fv.get("value")
            ],
        },
    }


def _extract_closed_date_from_timeline(timeline_data: dict) -> str | None:
    """Extract closed date from timeline entries.

    Looks for "Request Closed" event and parses its date.
    """
    for entry in timeline_data.get("timeline", []):
        if entry.get("timeline_name") == "Request Closed":
            byline = entry.get("timeline_byline", "")
            # Format: "March 16, 2026,  2:12pm by Staff"
            # Extract just the date part before the comma+time
            match = re.match(r"(\w+ \d+, \d{4})", byline)
            if match:
                return _parse_date(match.group(1))
    return None


# ── Document handling ─────────────────────────────────────────

def download_document(url: str, dest_dir: Path) -> Path | None:
    """Download a document PDF from NextRequest.

    Returns the local file path, or None if download failed.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Extract filename from URL or use a default
    filename = url.rsplit("/", 1)[-1] if "/" in url else "document.pdf"
    if not filename or filename == "download":
        filename = f"doc_{int(time.time())}.pdf"

    dest_path = dest_dir / filename

    try:
        resp = http_client.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"Downloaded {filename} ({dest_path.stat().st_size:,} bytes)")
        return dest_path
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return None


def extract_document_text(filepath: Path) -> str | None:
    """Extract text from a PDF using PyMuPDF (fitz).

    Same pattern as batch_extract.py — handles Type3 font warnings.
    Returns extracted text or None on failure.
    """
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed — skipping text extraction")
        return None

    try:
        doc = fitz.open(str(filepath))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        text = "\n".join(text_parts).strip()
        return text if text else None
    except Exception as e:
        logger.error(f"Failed to extract text from {filepath}: {e}")
        return None


# ── Database operations ───────────────────────────────────────

def save_to_db(conn, results: dict, city_fips: str) -> dict:
    """Save scraped NextRequest data to database.

    Upserts requests and their documents into nextrequest_requests
    and nextrequest_documents tables.

    Counter Contract (Phase D-2/D-3, 2026-05-16): returns
    `requests_inserted`/`requests_updated` from RETURNING (xmax = 0).
    `documents_inserted` tracks new upstream document IDs; collisions are
    metadata-refresh upserts and count as `documents_skipped_existing` for
    backward compatibility.

    Returns stats dict with:
      - requests_inserted: new request rows
      - requests_updated: existing rows refreshed via ON CONFLICT
      - documents_inserted: new upstream document rows
      - documents_skipped_existing: existing upstream IDs refreshed in place
    Invariant: requests_inserted + requests_updated == len(results["requests"])
    """
    requests_inserted = 0
    requests_updated = 0
    documents_inserted = 0
    documents_skipped_existing = 0
    documents_tombstoned = 0
    requests_tombstoned = 0

    request_listing_complete = results.get("request_listing_complete") is True
    document_listing_complete = (
        results.get("public_document_listing_complete") is True
    )
    authoritative_request_numbers: list[str] = []
    if request_listing_complete:
        raw_numbers = results.get("authoritative_request_numbers")
        if not isinstance(raw_numbers, (list, tuple, set)):
            raise ValueError(
                "Authoritative NextRequest request set is malformed"
            )
        if any(
            not isinstance(number, str) or not number.strip()
            for number in raw_numbers
        ):
            raise ValueError(
                "Authoritative NextRequest request set contains an invalid ID"
            )
        authoritative_request_numbers = sorted({
            number.strip() for number in raw_numbers
        })
        if not authoritative_request_numbers:
            raise ValueError(
                "Refusing empty authoritative NextRequest request set"
            )

    authoritative_public_document_ids: list[int] = []
    if document_listing_complete:
        raw_document_ids = results.get("authoritative_public_document_ids")
        if not isinstance(raw_document_ids, (list, tuple, set)):
            raise ValueError(
                "Authoritative NextRequest document set is malformed"
            )
        if any(
            isinstance(source_id, bool)
            or not isinstance(source_id, int)
            or source_id <= 0
            for source_id in raw_document_ids
        ):
            raise ValueError(
                "Authoritative NextRequest document set contains an invalid ID"
            )
        authoritative_public_document_ids = sorted(set(raw_document_ids))
        if not authoritative_public_document_ids:
            raise ValueError(
                "Refusing empty authoritative NextRequest document set"
            )

    with conn.cursor() as cur:
        if request_listing_complete:
            cur.execute(
                """SELECT
                     COUNT(DISTINCT request_number),
                     COUNT(DISTINCT request_number) FILTER (
                       WHERE request_number = ANY(%s)
                     )
                   FROM nextrequest_requests
                   WHERE city_fips = %s AND source_removed_at IS NULL""",
                (authoritative_request_numbers, city_fips),
            )
            baseline, overlap = _validated_live_overlap_counts(
                cur.fetchone(),
                label="request",
            )
            _assert_conservative_authoritative_size(
                label="request",
                observed_unique=overlap,
                live_unique_baseline=baseline,
            )
        if document_listing_complete:
            cur.execute(
                """SELECT
                     COUNT(DISTINCT d.source_document_id),
                     COUNT(DISTINCT d.source_document_id) FILTER (
                       WHERE d.source_document_id = ANY(%s)
                     )
                   FROM nextrequest_documents d
                   JOIN nextrequest_requests r ON r.id = d.request_id
                   WHERE r.city_fips = %s
                     AND r.source_removed_at IS NULL
                     AND d.source_removed_at IS NULL
                     AND d.source_document_id IS NOT NULL""",
                (authoritative_public_document_ids, city_fips),
            )
            baseline, overlap = _validated_live_overlap_counts(
                cur.fetchone(),
                label="document",
            )
            _assert_conservative_authoritative_size(
                label="document",
                observed_unique=overlap,
                live_unique_baseline=baseline,
            )
        for req in results.get("requests", []):
            if req.get("_source_nonpublic") is True:
                cur.execute(
                    """UPDATE nextrequest_requests
                       SET source_removed_at = COALESCE(
                         source_removed_at, NOW()
                       )
                       WHERE city_fips = %s AND request_number = %s
                       RETURNING id""",
                    (city_fips, req["request_number"]),
                )
                removed_row = cur.fetchone()
                if removed_row:
                    requests_updated += 1
                    requests_tombstoned += 1
                    cur.execute(
                        """UPDATE nextrequest_documents
                           SET source_removed_at = COALESCE(
                             source_removed_at, NOW()
                           )
                           WHERE request_id = %s
                             AND source_removed_at IS NULL""",
                        (removed_row[0],),
                    )
                    if isinstance(cur.rowcount, int) and not isinstance(
                        cur.rowcount, bool
                    ):
                        documents_tombstoned += max(0, cur.rowcount)
                continue

            # Truncate department to fit VARCHAR(200) column
            # (multi-department strings can exceed 200 chars)
            dept = req.get("department")
            if dept and len(dept) > 200:
                dept = dept[:197] + "..."

            incomplete_stages = set(req.get("_incomplete_stages") or [])
            raw_documents = req.get("documents", [])
            if not isinstance(raw_documents, list):
                raise ValueError(
                    f"NextRequest {req['request_number']} documents are malformed"
                )
            request_documents_complete = (
                req.get("_documents_listing_complete") is True
            )
            request_documents_observed = (
                req.get("_documents_listing_observed") is True
            )
            if request_documents_complete and not request_documents_observed:
                raise ValueError(
                    f"NextRequest {req['request_number']} has contradictory "
                    "document observation state"
                )
            if request_documents_complete and incomplete_stages.intersection({
                "detail", "documents", "documents_not_requested",
            }):
                raise ValueError(
                    f"NextRequest {req['request_number']} has contradictory "
                    "document completeness state"
                )
            if request_documents_complete and not raw_documents:
                raise ValueError(
                    f"Refusing empty authoritative document set for "
                    f"NextRequest {req['request_number']}"
                )

            active_source_document_ids: list[int] = []
            for doc in raw_documents:
                if not isinstance(doc, dict):
                    raise ValueError(
                        f"NextRequest {req['request_number']} document is malformed"
                    )
                source_document_id = doc.get("source_document_id")
                if (
                    isinstance(source_document_id, bool)
                    or not isinstance(source_document_id, int)
                    or source_document_id <= 0
                ):
                    raise ValueError(
                        f"NextRequest {req['request_number']} document is missing "
                        "a positive source_document_id"
                    )
                active_source_document_ids.append(source_document_id)
            if (
                request_documents_complete
                and len(set(active_source_document_ids))
                != len(active_source_document_ids)
            ):
                raise ValueError(
                    f"NextRequest {req['request_number']} complete document set "
                    "contains duplicate source IDs"
                )

            raw_private_document_ids = req.get(
                "_private_document_source_ids", []
            )
            if not isinstance(raw_private_document_ids, list) or any(
                isinstance(source_id, bool)
                or not isinstance(source_id, int)
                or source_id <= 0
                for source_id in raw_private_document_ids
            ):
                raise ValueError(
                    f"NextRequest {req['request_number']} private document "
                    "identities are malformed"
                )
            private_document_source_ids = sorted(set(raw_private_document_ids))
            if private_document_source_ids and not request_documents_observed:
                raise ValueError(
                    f"NextRequest {req['request_number']} has uncorroborated "
                    "private document identities"
                )

            preserve_detail = "detail" in incomplete_stages
            preserve_timeline = bool(
                incomplete_stages.intersection({"detail", "timeline"})
            )
            preserve_documents = not request_documents_complete
            preserve_metadata = "detail" in incomplete_stages
            reconciliation_complete = (
                not incomplete_stages and request_documents_observed
            )

            # Upsert request — RETURNING both id (needed for documents
            # insert below) and the xmax-derived `inserted` flag so we
            # can distinguish new rows from refreshed ones.
            cur.execute(
                """INSERT INTO nextrequest_requests
                   (city_fips, request_number, request_text, requester_name,
                    department, status, submitted_date, due_date, closed_date,
                    days_to_close, document_count, portal_url, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (city_fips, request_number)
                   DO UPDATE SET
                     request_text = CASE WHEN %s
                       THEN nextrequest_requests.request_text
                       ELSE EXCLUDED.request_text END,
                     requester_name = CASE WHEN %s
                       THEN nextrequest_requests.requester_name
                       ELSE EXCLUDED.requester_name END,
                     department = CASE WHEN %s
                       THEN nextrequest_requests.department
                       ELSE EXCLUDED.department END,
                     submitted_date = CASE WHEN %s
                       THEN nextrequest_requests.submitted_date
                       ELSE EXCLUDED.submitted_date END,
                     due_date = CASE WHEN %s
                       THEN nextrequest_requests.due_date
                       ELSE EXCLUDED.due_date END,
                     portal_url = CASE WHEN %s
                       THEN nextrequest_requests.portal_url
                       ELSE EXCLUDED.portal_url END,
                     status = EXCLUDED.status,
                     closed_date = CASE WHEN %s
                       THEN nextrequest_requests.closed_date
                       ELSE EXCLUDED.closed_date END,
                     days_to_close = CASE WHEN %s
                       THEN nextrequest_requests.days_to_close
                       ELSE EXCLUDED.days_to_close END,
                     document_count = CASE WHEN %s
                       THEN nextrequest_requests.document_count
                       ELSE EXCLUDED.document_count END,
                     metadata = CASE WHEN %s
                       THEN nextrequest_requests.metadata
                       ELSE EXCLUDED.metadata END,
                     source_removed_at = NULL,
                     updated_at = CASE WHEN %s
                       THEN NOW()
                       ELSE nextrequest_requests.updated_at END
                   RETURNING id, (xmax = 0) AS inserted""",
                (
                    city_fips,
                    req["request_number"],
                    req.get("request_text", ""),
                    req.get("requester_name"),
                    dept,
                    req["status"],
                    req.get("submitted_date"),
                    req.get("due_date"),
                    req.get("closed_date"),
                    req.get("days_to_close"),
                    len(raw_documents),
                    req.get("portal_url"),
                    json.dumps(req.get("metadata", {})),
                    preserve_detail,
                    preserve_detail,
                    preserve_detail,
                    preserve_detail,
                    preserve_detail,
                    preserve_detail,
                    preserve_timeline,
                    preserve_timeline,
                    preserve_documents,
                    preserve_metadata,
                    reconciliation_complete,
                ),
            )
            row = cur.fetchone()
            request_id = row[0]
            if row[1]:
                requests_inserted += 1
            else:
                requests_updated += 1

            # Source document IDs make periodic reconciliation idempotent.
            # Complete per-request pagination is required before absent rows
            # may be tombstoned below.
            for doc in raw_documents:
                source_document_id = doc.get("source_document_id")
                cur.execute(
                    """INSERT INTO nextrequest_documents
                       (request_id, source_document_id, filename, file_type,
                        download_url, released_date, extracted_text,
                        extraction_status, extraction_metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (request_id, source_document_id)
                         WHERE source_document_id IS NOT NULL
                       DO UPDATE SET
                         filename = EXCLUDED.filename,
                         file_type = EXCLUDED.file_type,
                         download_url = EXCLUDED.download_url,
                         released_date = EXCLUDED.released_date,
                         extracted_text = COALESCE(
                           EXCLUDED.extracted_text,
                           nextrequest_documents.extracted_text
                         ),
                         extraction_status = CASE
                           WHEN EXCLUDED.extracted_text IS NOT NULL
                             THEN EXCLUDED.extraction_status
                           ELSE nextrequest_documents.extraction_status
                         END,
                         extraction_metadata =
                           nextrequest_documents.extraction_metadata
                           || EXCLUDED.extraction_metadata,
                         source_removed_at = NULL
                       RETURNING (xmax = 0) AS inserted""",
                    (
                        request_id,
                        source_document_id,
                        doc.get("filename"),
                        doc.get("file_type"),
                        doc.get("download_url"),
                        doc.get("released_date"),
                        doc.get("extracted_text"),
                        "extracted" if doc.get("extracted_text") else "pending",
                        json.dumps({
                            "source_visibility": doc.get("visibility"),
                            "source_folder_name": doc.get("folder_name"),
                        }),
                    ),
                )
                doc_row = cur.fetchone()
                if doc_row and bool(doc_row[0]):
                    documents_inserted += 1
                else:
                    documents_skipped_existing += 1

            if private_document_source_ids:
                # Explicit private visibility is affirmative only for these
                # exact stable IDs. Do not extrapolate an all-private public
                # projection to absent or legacy rows.
                cur.execute(
                    """UPDATE nextrequest_documents
                       SET source_removed_at = COALESCE(
                         source_removed_at, NOW()
                       )
                       WHERE request_id = %s
                         AND source_removed_at IS NULL
                         AND source_document_id = ANY(%s)""",
                    (request_id, private_document_source_ids),
                )
                if isinstance(cur.rowcount, int) and not isinstance(
                    cur.rowcount, bool
                ):
                    documents_tombstoned += max(0, cur.rowcount)

            if not preserve_documents:
                # This is a complete public per-request document listing.
                # Retire legacy rows without source IDs too: current documents
                # were just reinserted with stable upstream IDs, so keeping the
                # unidentifiable legacy URL active would defeat retraction.
                cur.execute(
                    """UPDATE nextrequest_documents
                       SET source_removed_at = NOW()
                       WHERE request_id = %s
                         AND source_removed_at IS NULL
                         AND (
                           source_document_id IS NULL
                           OR NOT (source_document_id = ANY(%s))
                         )""",
                    (request_id, sorted(set(active_source_document_ids))),
                )
                if isinstance(cur.rowcount, int) and not isinstance(
                    cur.rowcount, bool
                ):
                    documents_tombstoned += max(0, cur.rowcount)

        if document_listing_complete:
            cur.execute(
                """UPDATE nextrequest_documents d
                   SET source_removed_at = NOW()
                   FROM nextrequest_requests r
                   WHERE r.id = d.request_id
                     AND r.city_fips = %s
                     AND r.source_removed_at IS NULL
                     AND d.source_removed_at IS NULL
                     AND d.source_document_id IS NOT NULL
                     AND NOT (d.source_document_id = ANY(%s))""",
                (city_fips, authoritative_public_document_ids),
            )
            if isinstance(cur.rowcount, int) and not isinstance(
                cur.rowcount, bool
            ):
                documents_tombstoned += max(0, cur.rowcount)

        if request_listing_complete:
            cur.execute(
                """UPDATE nextrequest_requests
                   SET source_removed_at = NOW()
                   WHERE city_fips = %s
                     AND source_removed_at IS NULL
                     AND NOT (request_number = ANY(%s))""",
                (city_fips, authoritative_request_numbers),
            )
            if isinstance(cur.rowcount, int) and not isinstance(
                cur.rowcount, bool
            ):
                requests_tombstoned += max(0, cur.rowcount)
            # Privacy is transitive: a direct query of the child table must
            # not expose files belonging to a now-unpublished request.
            cur.execute(
                """UPDATE nextrequest_documents d
                   SET source_removed_at = COALESCE(
                     d.source_removed_at, NOW()
                   )
                   FROM nextrequest_requests r
                   WHERE r.id = d.request_id
                     AND r.city_fips = %s
                     AND r.source_removed_at IS NOT NULL
                     AND d.source_removed_at IS NULL""",
                (city_fips,),
            )
            if isinstance(cur.rowcount, int) and not isinstance(
                cur.rowcount, bool
            ):
                documents_tombstoned += max(0, cur.rowcount)

    conn.commit()
    return {
        "requests_inserted": requests_inserted,
        "requests_updated": requests_updated,
        "documents_inserted": documents_inserted,
        "documents_skipped_existing": documents_skipped_existing,
        "documents_tombstoned": documents_tombstoned,
        "requests_tombstoned": requests_tombstoned,
        # Backward-compat aliases — sum of new + updated is the old
        # "requests_saved" semantic. Will be removed in a follow-up
        # once all callers migrate.
        "requests_saved": requests_inserted + requests_updated,
        "documents_saved": documents_inserted,
    }


# ── High-level orchestration ──────────────────────────────────

def list_all_requests(
    since_date: str | None = None,
    city_fips: str | None = None,
    *,
    return_state: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """List all requests via client API, paginated.

    Returns list of RequestSummary dicts.
    """
    base_url, _fips = _resolve_nextrequest_config(city_fips)
    all_requests: list[dict] = []
    fetched_raw_count = 0
    expected_total: int | None = None
    stopped_for_since_date = False
    seen_raw_request_ids: set[str] = set()
    page_num = 1
    # The live Richmond, California portal already exceeds 2,300 requests
    # (about 96 pages at NextRequest's default 25/page). Keep a generous hard
    # safety bound, then validate the first page's total against its observed
    # page size so oversized/schema-drift responses fail closed.
    max_pages = 1000

    while page_num <= max_pages:
        data = _fetch_request_list(page_num, base_url=base_url)
        total_count = data.get("total_count")
        items = data.get("requests", [])

        if (
            isinstance(total_count, bool)
            or not isinstance(total_count, int)
            or total_count < 0
            or not isinstance(items, list)
        ):
            raise ValueError("NextRequest request-list response is malformed")
        if expected_total is None:
            expected_total = total_count
            if since_date is None and expected_total == 0:
                raise RuntimeError(
                    "NextRequest authoritative request listing returned zero"
                )
            if items:
                required_pages = (
                    total_count + len(items) - 1
                ) // len(items)
                if required_pages > max_pages:
                    raise RuntimeError(
                        "NextRequest request-list exceeds safe pagination bound"
                    )
        elif total_count != expected_total:
            raise RuntimeError(
                "NextRequest request-list total changed during pagination"
            )

        if not items:
            if fetched_raw_count < total_count:
                raise RuntimeError(
                    "NextRequest request-list pagination ended before total_count"
                )
            break

        for item in items:
            if not isinstance(item, dict):
                raise ValueError("NextRequest request-list row is malformed")
            raw_request_id = str(item.get("id") or "").strip()
            if not raw_request_id:
                raise ValueError(
                    "NextRequest request-list row has no stable request ID"
                )
            if raw_request_id in seen_raw_request_ids:
                raise RuntimeError(
                    "NextRequest request pagination repeated a source ID"
                )
            seen_raw_request_ids.add(raw_request_id)
            visibility = _combined_visibility_state(
                item.get("visibility"), item.get("request_visibility")
            )
            if visibility == "unknown":
                raise ValueError(
                    "NextRequest request visibility enum is unknown"
                )
            if visibility == "public":
                transformed = _transform_list_item(item, base_url=base_url)
                all_requests.append(transformed)
        fetched_raw_count += len(items)

        logger.info(
            f"Page {page_num}: {len(items)} requests "
            f"({fetched_raw_count}/{total_count} total)"
        )

        # Check if we've fetched all pages
        if fetched_raw_count >= total_count:
            break

        # Early stop if we've gone past since_date
        if since_date and items:
            oldest_date = _parse_date(items[-1].get("request_date"))
            if oldest_date and oldest_date < since_date:
                stopped_for_since_date = True
                break

        page_num += 1
        time.sleep(RATE_LIMIT_MS / 1000)

    if (
        not stopped_for_since_date
        and expected_total is not None
        and fetched_raw_count < expected_total
    ):
        raise RuntimeError(
            "NextRequest request-list exceeded pagination bound before completion"
        )
    if since_date is None and expected_total is not None:
        if len(seen_raw_request_ids) != expected_total:
            raise RuntimeError(
                "NextRequest request-list unique coverage did not match total"
            )
        if len(all_requests) < max(1, expected_total // 2):
            raise RuntimeError(
                "NextRequest visible request set shrank implausibly"
            )

    # Filter by since_date
    if since_date:
        all_requests = [
            r for r in all_requests
            if not r.get("submitted_date") or r["submitted_date"] >= since_date
        ]

    state = {
        "complete": (
            since_date is None
            and not stopped_for_since_date
            and expected_total is not None
            and fetched_raw_count >= expected_total
        ),
        "expected_total": expected_total,
        "fetched_raw_count": fetched_raw_count,
    }
    if return_state:
        return all_requests, state
    return all_requests


def get_request_detail(
    request_id: str,
    *,
    city_fips: str | None = None,
    include_timeline: bool = True,
    include_documents: bool = False,
    failure_sink: list[dict] | None = None,
) -> dict:
    """Fetch full detail for a single request via client API.

    Returns RequestDetail dict. If include_timeline is True,
    also fetches timeline to extract closed_date. If include_documents
    is True, fetches document list via /client/request_documents.
    """
    base_url, _fips = _resolve_nextrequest_config(city_fips)
    raw_detail = _fetch_request_detail(request_id, base_url=base_url)
    detail_visibility_state = _combined_visibility_state(
        raw_detail.get("visibility"), raw_detail.get("request_visibility")
    )
    if detail_visibility_state == "unknown":
        raise ValueError(
            f"NextRequest detail visibility for {request_id} is unknown"
        )
    if detail_visibility_state == "private":
        # A successful non-public detail response is authoritative negative
        # evidence. Carry only identity to persistence, never private fields.
        return {
            "request_number": str(raw_detail.get("pretty_id") or request_id),
            "_source_nonpublic": True,
            "_incomplete_stages": [],
            "documents": [],
        }
    detail = _transform_detail(raw_detail, base_url=base_url)
    # Persistence requires positive proof of a complete, non-empty document
    # enumeration before it may retire absent or legacy rows.  Absence of a
    # fetch error is not itself that proof.
    detail["_documents_listing_complete"] = False
    detail["_documents_listing_observed"] = False

    # Get closed_date from timeline
    if include_timeline and detail["status"] == "Closed":
        try:
            timeline = _fetch_request_timeline(request_id, base_url=base_url)
            timeline_ids = [
                entry.get("timeline_id")
                for entry in timeline.get("timeline", [])
                if isinstance(entry, dict)
                and isinstance(entry.get("timeline_id"), int)
            ]
            detail["metadata"]["timeline_revision"] = (
                max(timeline_ids) if timeline_ids else None
            )
            closed_date = _extract_closed_date_from_timeline(timeline)
            if closed_date:
                detail["closed_date"] = closed_date
                detail["days_to_close"] = _compute_days_to_close(
                    detail["submitted_date"], closed_date
                )
        except Exception as e:
            logger.warning(f"Could not fetch timeline for {request_id}: {e}")
            if failure_sink is not None:
                failure_sink.append({
                    "request_id": request_id,
                    "stage": "timeline",
                    "error": f"{type(e).__name__}: {e}"[:500],
                })

    # Get documents via /client/request_documents
    if include_documents:
        try:
            raw_docs, documents_state = _fetch_request_documents_with_state(
                request_id,
                base_url=base_url,
            )
            document_states = [
                _combined_visibility_state(
                    document.get("visibility"), document.get("state")
                )
                for document in raw_docs
            ]
            if any(state == "unknown" for state in document_states):
                raise ValueError(
                    f"NextRequest document visibility for {request_id} is unknown"
                )
            detail["_documents_listing_observed"] = True
            detail["_private_document_source_ids"] = [
                document["id"]
                for document, state in zip(raw_docs, document_states)
                if state == "private"
            ]
            public_documents = [
                _transform_document(d, base_url=base_url)
                for d, state in zip(raw_docs, document_states)
                if state == "public"
            ]
            detail["documents"] = public_documents
            detail["metadata"]["documents_state_timestamp"] = documents_state
            # A 200-empty or all-private/filtered response is a successful
            # non-destructive observation, not proof that stored files were
            # removed.  It may advance request freshness without retiring any
            # document rows.  At least one reinsertable public source ID is
            # required for destructive per-request reconciliation.
            detail["_documents_listing_complete"] = bool(public_documents)
            if not public_documents:
                logger.warning(
                    "NextRequest documents for %s contained no visible rows; "
                    "preserving current files",
                    request_id,
                )
            logger.info(f"  Found {len(detail['documents'])} documents for {request_id}")
        except Exception as e:
            logger.warning(f"Could not fetch documents for {request_id}: {e}")
            if failure_sink is not None:
                failure_sink.append({
                    "request_id": request_id,
                    "stage": "documents",
                    "error": f"{type(e).__name__}: {e}"[:500],
                })

    return detail


def scrape_all(
    since_date: str | None = None,
    download_docs: bool = False,
    extract_text: bool = False,
    city_fips: str | None = None,
    skip_details: bool = False,
    include_documents: bool = False,
) -> dict:
    """Full scrape: list requests, optionally get details and download docs.

    ``include_documents`` fetches authoritative document metadata without
    downloading large response files. ``download_docs`` implies it. When
    ``skip_details=True``, list data is used directly for initial backfills.

    Returns result dict with city_fips, source, scraped_at, requests, stats.
    """
    base_url, resolved_fips = _resolve_nextrequest_config(city_fips)

    # Step 1: Get all request summaries
    listed = list_all_requests(
        since_date=since_date,
        city_fips=city_fips,
        return_state=True,
    )
    if isinstance(listed, tuple):
        summaries, listing_state = listed
    else:
        # Compatibility for integrations/tests that replace this helper.
        summaries = listed
        listing_state = {"complete": False}
    logger.info(f"Found {len(summaries)} requests")
    listing_contract = {
        "request_listing_complete": bool(listing_state.get("complete")),
        "authoritative_request_numbers": [
            str(summary["request_number"])
            for summary in summaries
            if summary.get("request_number")
        ],
    }

    if skip_details:
        # Use list data directly — no per-request detail calls. Internal
        # stage markers keep conflict updates from erasing previously-fetched
        # detail fields while still allowing genuinely new summaries to load.
        summary_only_requests = [
            {
                **summary,
                "_incomplete_stages": ["detail", "timeline", "documents"],
            }
            for summary in summaries
        ]
        return {
            "city_fips": resolved_fips,
            "source": "nextrequest",
            "scraped_at": datetime.now().isoformat(),
            "requests": summary_only_requests,
            **listing_contract,
            "stats": {
                "total_found": len(summaries),
                "details_scraped": 0,
                "documents_found": 0,
                "failure_count": 0,
                "failed_request_ids": [],
                "failure_counts": {},
                "failures": [],
            },
        }

    # Step 2: Get details for each request
    detailed_requests: list[dict] = []
    failures: list[dict] = []
    details_scraped = 0
    should_fetch_documents = include_documents or download_docs
    for i, summary in enumerate(summaries):
        req_id = summary["request_number"]
        logger.info(f"  [{i+1}/{len(summaries)}] Fetching detail for {req_id}")
        try:
            failure_start = len(failures)
            detail = get_request_detail(
                req_id,
                city_fips=city_fips,
                include_documents=should_fetch_documents,
                failure_sink=failures,
            )
            details_scraped += 1
            incomplete_stages = {
                failure.get("stage")
                for failure in failures[failure_start:]
            }
            if not should_fetch_documents:
                incomplete_stages.add("documents_not_requested")
            detail["_incomplete_stages"] = sorted(incomplete_stages)

            # Step 3: Optionally download documents
            if download_docs and detail.get("documents"):
                dest_dir = RAW_DIR / req_id
                for doc in detail["documents"]:
                    if doc.get("download_url"):
                        filepath = download_document(doc["download_url"], dest_dir)
                        if filepath is None:
                            failures.append({
                                "request_id": req_id,
                                "stage": "document_download",
                                "error": "download returned no local artifact",
                            })
                        if filepath and extract_text:
                            extracted = extract_document_text(filepath)
                            doc["extracted_text"] = extracted
                            if extracted is None:
                                failures.append({
                                    "request_id": req_id,
                                    "stage": "document_text",
                                    "error": "text extraction returned no text",
                                })

            detailed_requests.append(detail)
        except Exception as e:
            logger.error(f"  Error fetching {req_id}: {e}")
            failures.append({
                "request_id": req_id,
                "stage": "detail",
                "error": f"{type(e).__name__}: {e}"[:500],
            })
            # The list response is still authoritative enough to preserve the
            # request itself.  Save that summary now, but keep the run
            # explicitly incomplete so timeline/detail fields are retried.
            fallback = dict(summary)
            fallback["_incomplete_stages"] = [
                "detail", "timeline", "documents",
            ]
            detailed_requests.append(fallback)

        time.sleep(RATE_LIMIT_MS / 1000)

    failed_request_ids = sorted({
        str(failure["request_id"])
        for failure in failures
        if failure.get("request_id")
    })
    failure_counts = {
        stage: sum(1 for failure in failures if failure.get("stage") == stage)
        for stage in (
            "detail", "timeline", "documents", "document_download",
            "document_text",
        )
    }
    return {
        "city_fips": resolved_fips,
        "source": "nextrequest",
        "scraped_at": datetime.now().isoformat(),
        "requests": detailed_requests,
        **listing_contract,
        "stats": {
            "total_found": len(summaries),
            "details_scraped": details_scraped,
            "documents_found": sum(
                len(r.get("documents", [])) for r in detailed_requests
            ),
            "failure_count": len(failures),
            "failed_request_ids": failed_request_ids,
            "failure_counts": failure_counts,
            "failures": failures,
        },
    }


def scrape_request_ids(
    request_ids: list[str],
    *,
    city_fips: str | None = None,
    include_documents: bool = True,
) -> dict:
    """Reconcile a bounded set of known requests independent of submit date.

    Unlike ``scrape_all``, this path has no list-summary fallback.  A failed
    detail/timeline/document request is omitted, surfaced in ``failures``, and
    therefore cannot advance that row's database reconciliation timestamp.
    """
    _base, resolved_fips = _resolve_nextrequest_config(city_fips)
    ordered_ids = list(dict.fromkeys(
        str(request_id).strip()
        for request_id in request_ids
        if str(request_id).strip()
    ))
    requests = []
    failures: list[dict] = []
    for index, request_id in enumerate(ordered_ids, 1):
        logger.info(
            f"  [{index}/{len(ordered_ids)}] Reconciling detail for {request_id}"
        )
        try:
            failure_start = len(failures)
            detail = get_request_detail(
                request_id,
                city_fips=city_fips,
                include_documents=include_documents,
                failure_sink=failures,
            )
            detail["_incomplete_stages"] = sorted({
                failure.get("stage")
                for failure in failures[failure_start:]
                if failure.get("stage")
            })
            requests.append(detail)
        except Exception as exc:
            failures.append({
                "request_id": request_id,
                "stage": "detail",
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })
        if index < len(ordered_ids):
            time.sleep(RATE_LIMIT_MS / 1000)

    failed_request_ids = sorted({
        str(failure["request_id"])
        for failure in failures
        if failure.get("request_id")
    })
    failure_counts = {
        stage: sum(1 for failure in failures if failure.get("stage") == stage)
        for stage in ("detail", "timeline", "documents")
    }
    return {
        "city_fips": resolved_fips,
        "source": "nextrequest",
        "scraped_at": datetime.now().isoformat(),
        "requests": requests,
        "stats": {
            "total_found": len(ordered_ids),
            "details_scraped": len(requests),
            "documents_found": sum(
                len(request.get("documents", [])) for request in requests
            ),
            "failure_count": len(failures),
            "failed_request_ids": failed_request_ids,
            "failure_counts": failure_counts,
            "failures": failures,
        },
    }


# ── CLI ───────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Richmond Common — NextRequest/CPRA Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true", help="List all requests")
    parser.add_argument("--request", type=str, help="Fetch single request by ID (e.g., 26-414)")
    parser.add_argument("--since", type=str, help="Only requests since YYYY-MM-DD")
    parser.add_argument("--download", action="store_true", help="Download PDFs")
    parser.add_argument("--extract", action="store_true", help="Extract text from PDFs")
    parser.add_argument("--stats", action="store_true", help="Print portal statistics")
    parser.add_argument("--skip-details", action="store_true", help="List-only mode (no per-request detail calls)")
    parser.add_argument("--output", type=str, help="Save JSON output to file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.list:
        results = list_all_requests(since_date=args.since)
        for r in results:
            dept = (r.get("department") or "")[:20]
            text = (r.get("request_text") or "")[:60]
            print(f"  {r['request_number']:12s} {r['status']:15s} {dept:20s} {text}")
        print(f"\nTotal: {len(results)} requests")

    elif args.request:
        detail = get_request_detail(args.request)
        print(json.dumps(detail, indent=2, default=str))

    else:
        results = scrape_all(
            since_date=args.since,
            download_docs=args.download,
            extract_text=args.extract,
            skip_details=args.skip_details,
        )

        if args.output:
            Path(args.output).write_text(
                json.dumps(results, indent=2, default=str), encoding="utf-8"
            )
            print(f"Saved to {args.output}")
        else:
            print(json.dumps(results.get("stats", {}), indent=2))

        if args.stats:
            s = results.get("stats", {})
            print(f"\n{'='*50}")
            print(f"NextRequest Portal Statistics")
            print(f"  Requests found:    {s.get('total_found', 0)}")
            print(f"  Details scraped:   {s.get('details_scraped', 0)}")
            print(f"  Documents found:   {s.get('documents_found', 0)}")
            print(f"{'='*50}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
