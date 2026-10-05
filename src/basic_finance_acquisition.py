"""Finite, read-only NetFile acquisition for the compact public refresh.

The existing deterministic eight-form parser/reconciler remains authoritative.
Only its fetch/metadata/PDF transport seams are replaced. No raw files, database
writes, provider credentials, retries, redirects or model calls are used here.
Limits reject the whole snapshot; truncated results never become empty coverage.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
import json
import math
import re
import time
from typing import Callable
from unittest.mock import patch

from finance_ledger import TYPES

API_BASE = "https://netfile.com/Connect2/api"
CITY_FIPS = "0660620"
AGENCY_ID = 163
PUBLIC_THROUGH = "2026-11-03"


class FinanceAcquisitionError(ValueError):
    """Fixed rejection reason safe for aggregate-only refresh diagnostics."""


@dataclass(frozen=True)
class AcquisitionLimits:
    """Reviewed maxima. A fixture/operator may lower them, never raise them."""

    page_size: int = 250
    transaction_pages: int = 64
    transaction_records: int = 10_000
    filing_metadata: int = 400
    pdf_downloads: int = 32
    json_response_bytes: int = 2_000_000
    metadata_response_bytes: int = 256_000
    pdf_response_bytes: int = 4_000_000
    pdf_total_bytes: int = 24_000_000
    response_total_bytes: int = 48_000_000
    http_requests: int = 512
    elapsed_seconds: int = 300


DEFAULT_LIMITS = AcquisitionLimits()


def _validate_limits(limits: AcquisitionLimits) -> None:
    if type(limits) is not AcquisitionLimits:
        raise FinanceAcquisitionError("Finance acquisition limits are not an accepted contract")
    for field in fields(limits):
        value = getattr(limits, field.name)
        if type(value) is not int or not 0 < value <= getattr(DEFAULT_LIMITS, field.name):
            raise FinanceAcquisitionError("Finance acquisition limits cannot exceed reviewed maxima")


def _source_id(value) -> str:
    if type(value) not in {str, int} or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}", str(value)):
        raise FinanceAcquisitionError("Finance source contains an invalid record identity")
    return str(value)


class _BoundedTransport:
    def __init__(self, session, limits: AcquisitionLimits, clock: Callable[[], float]):
        self.session, self.limits, self.clock = session, limits, clock
        self.started = clock()
        self.requests = self.pages = self.records = self.response_bytes = self.pdf_bytes = 0
        self.filings: set[str] = set()
        self.metadata: set[str] = set()
        self.downloads: set[str] = set()
        self.forms: set[int] = set()

    def _deadline(self) -> None:
        if self.clock() - self.started >= self.limits.elapsed_seconds:
            raise FinanceAcquisitionError("Finance acquisition exceeded its elapsed-time ceiling")

    def _read(self, method: str, url: str, maximum: int, **options) -> bytes:
        self._deadline()
        if self.requests >= self.limits.http_requests:
            raise FinanceAcquisitionError("Finance acquisition exceeded its request ceiling")
        self.requests += 1
        response = None
        try:
            response = getattr(self.session, method)(
                url, timeout=(5, 20), allow_redirects=False, stream=True, **options,
            )
            # Redirects and error bodies cannot establish a complete inventory.
            if response.status_code != 200:
                raise FinanceAcquisitionError("Finance official source did not return an accepted response")
            parts, size = [], 0
            for chunk in response.iter_content(chunk_size=64_000):
                self._deadline()
                size += len(chunk)
                self.response_bytes += len(chunk)
                if size > maximum or self.response_bytes > self.limits.response_total_bytes:
                    raise FinanceAcquisitionError("Finance official source exceeded its response-byte ceiling")
                parts.append(chunk)
            self._deadline()
            return b"".join(parts)
        except FinanceAcquisitionError:
            raise
        except Exception as exc:
            # Requests exceptions can contain full URLs or upstream text.
            raise FinanceAcquisitionError("Finance official source request failed") from exc
        finally:
            if response is not None:
                response.close()

    def _json(self, method: str, url: str, maximum: int, **options) -> dict:
        body = self._read(method, url, maximum, **options)
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise FinanceAcquisitionError("Finance official source returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise FinanceAcquisitionError("Finance official source returned an invalid inventory")
        return value

    def fetch(self, *, transaction_type: int, date_start: str, date_end: str, city_fips: str) -> list[dict]:
        if (type(transaction_type) is not int or transaction_type not in TYPES
                or transaction_type in self.forms or city_fips != CITY_FIPS
                or date_start != "2026-01-01" or not date_start <= date_end <= PUBLIC_THROUGH):
            raise FinanceAcquisitionError("Finance transaction request is outside the reviewed scope")
        self.forms.add(transaction_type)
        all_rows, seen = [], set()
        expected_total = expected_pages = None
        page = 0
        while True:
            if self.pages >= self.limits.transaction_pages:
                raise FinanceAcquisitionError("Finance acquisition exceeded its transaction-page ceiling")
            self.pages += 1
            value = self._json("post", API_BASE + "/public/campaign/search/transaction/query?format=json",
                               self.limits.json_response_bytes,
                               headers={"Content-Type": "application/json"}, json={
                                   "Agency": AGENCY_ID, "TransactionType": transaction_type,
                                   "DateStart": date_start, "DateEnd": date_end,
                                   "PageSize": self.limits.page_size, "CurrentPageIndex": page,
                                   "SortOrder": 1, "ShowSuperceded": False,
                               })
            total, pages, rows = value.get("totalMatchingCount"), value.get("totalMatchingPages"), value.get("results")
            if (type(total) is not int or total < 0 or type(pages) is not int or pages < 0
                    or not isinstance(rows, list) or len(rows) > self.limits.page_size
                    or (total == 0 and (rows or pages not in {0, 1}))
                    or (total > 0 and pages != math.ceil(total / self.limits.page_size))):
                raise FinanceAcquisitionError("Finance transaction response cannot prove complete coverage")
            parameters = value.get("searchParameters", {})
            if not isinstance(parameters, dict) or parameters.get("showSuperceded", False) is not False:
                raise FinanceAcquisitionError("Finance source did not honor current-report selection")
            for key, requested in {"agency": AGENCY_ID, "transactionType": transaction_type,
                                   "pageSize": self.limits.page_size, "currentPageIndex": page,
                                   "sortOrder": 1}.items():
                if key in parameters and (type(parameters[key]) is not int or parameters[key] != requested):
                    raise FinanceAcquisitionError("Finance source did not honor its requested page/scope")
            if expected_total is None:
                expected_total, expected_pages = total, pages
                if (self.records + total > self.limits.transaction_records
                        or self.pages + max(pages - 1, 0) > self.limits.transaction_pages):
                    raise FinanceAcquisitionError("Finance reported inventory exceeds its row/page ceiling")
            elif total != expected_total or pages != expected_pages:
                raise FinanceAcquisitionError("Finance source changed during pagination; snapshot rejected")
            expected_on_page = min(self.limits.page_size, total - page * self.limits.page_size)
            if len(rows) != expected_on_page:
                raise FinanceAcquisitionError("Finance transaction pagination is incomplete")
            for row in rows:
                if not isinstance(row, dict) or type(row.get("transactionType")) is not int or row["transactionType"] != transaction_type:
                    raise FinanceAcquisitionError("Finance source returned another transaction kind")
                identity, filing = _source_id(row.get("id")), _source_id(row.get("filingId"))
                # The canonical ledger identifies a source assertion by its
                # filing + transaction ID. The same opaque ID in a different
                # filing is not proof of a repeated page or duplicate record.
                key = (filing, identity)
                if key in seen:
                    raise FinanceAcquisitionError("Finance source repeated a transaction identity")
                seen.add(key)
                self.filings.add(filing)
                if len(self.filings) > self.limits.filing_metadata:
                    raise FinanceAcquisitionError("Finance acquisition exceeded its filing-metadata ceiling")
            all_rows.extend(rows)
            self.records += len(rows)
            self._deadline()
            page += 1
            if page >= pages:
                break
        if len(all_rows) != expected_total:
            raise FinanceAcquisitionError("Finance transaction pagination is incomplete")
        return all_rows

    def filing_info(self, filing_id: str) -> dict:
        filing_id = _source_id(filing_id)
        if (filing_id not in self.filings or filing_id in self.metadata
                or len(self.metadata) >= self.limits.filing_metadata):
            raise FinanceAcquisitionError("Finance filing request exceeds its proven bounded inventory")
        self.metadata.add(filing_id)
        value = self._json("get", API_BASE + "/public/filing/info/" + filing_id,
                           self.limits.metadata_response_bytes, params={"format": "json"})
        if _source_id(value.get("filingId")) != filing_id:
            raise FinanceAcquisitionError("Finance metadata did not identify the requested filing")
        return value

    def download(self, url: str) -> bytes:
        prefix = API_BASE + "/public/image/"
        if not isinstance(url, str) or not url.startswith(prefix):
            raise FinanceAcquisitionError("Finance PDF request is outside the official source")
        filing = _source_id(url[len(prefix):])
        if (filing not in self.metadata or filing in self.downloads
                or len(self.downloads) >= self.limits.pdf_downloads):
            raise FinanceAcquisitionError("Finance acquisition exceeded its proven PDF inventory")
        self.downloads.add(filing)
        remaining = self.limits.pdf_total_bytes - self.pdf_bytes
        if remaining <= 0:
            raise FinanceAcquisitionError("Finance acquisition exceeded its total PDF-byte ceiling")
        body = self._read("get", url, min(self.limits.pdf_response_bytes, remaining))
        self.pdf_bytes += len(body)
        if not body.startswith(b"%PDF-"):
            raise FinanceAcquisitionError("Finance official source did not return an accepted PDF")
        return body


def acquire_bounded_finance_snapshot(year: int, through: str, *, session=None,
                                     limits: AcquisitionLimits | None = None,
                                     clock: Callable[[], float] | None = None) -> dict:
    """Return the existing snapshot contract, or reject without partial results.

    Streams official HTTP bodies with finite counters before parser allocation.
    The deadline is checked between requests/chunks, not a hard process kill;
    one in-flight socket can take its bounded connect/read timeout to finish.
    PDF bytes are transient parser input and are not persisted by this adapter.
    """
    try:
        cutoff = date.fromisoformat(through)
    except (ValueError, TypeError) as exc:
        raise FinanceAcquisitionError("Finance acquisition requires a valid reviewed cutoff") from exc
    if type(year) is not int or year != 2026 or cutoff.year != year or not "2026-01-01" <= through <= PUBLIC_THROUGH:
        raise FinanceAcquisitionError("Finance acquisition is limited to the reviewed 2026 publication window")
    selected = DEFAULT_LIMITS if limits is None else limits
    _validate_limits(selected)
    owned = session is None
    if owned:
        import requests
        session = requests.Session()
        # Public endpoints require no .netrc credentials or environment proxy.
        session.trust_env = False
    transport = _BoundedTransport(session, selected, clock or time.monotonic)
    try:
        # The legacy source client imports dotenv. Never let that import load a
        # production/provider configuration as an acquisition side effect.
        with patch("dotenv.load_dotenv", return_value=False):
            from finance_sync import acquire_snapshot
        snapshot = acquire_snapshot(year, through, fetch=transport.fetch,
                                    filing_info=transport.filing_info, download=transport.download)
        transport._deadline()
        if transport.forms != set(TYPES) or len(transport.metadata) != len(transport.filings):
            raise FinanceAcquisitionError("Finance acquisition did not complete every supported form and filing")
        snapshot["acquisition_metrics"].update(
            transaction_pages=transport.pages, transaction_records=transport.records,
            http_requests=transport.requests, response_bytes=transport.response_bytes,
            bounded_acquisition=True,
        )
        return snapshot
    finally:
        if owned:
            session.close()
