"""NetFile SEI public-portal JSON API client (Form 700 / Statement of Economic Interests).

Reads from the JSON API behind the portal SPA at https://netfile.com/public/RICH/sei
(base https://netfile.com/api/public/sites/api/, no auth). The previous ASP.NET
WebForms portal (public.netfile.com/pub/?AID=RICH) was decommissioned ~2026-06 —
it now redirects to the SPA, so form700_scraper.discover_filings() finds no
__VIEWSTATE and returns []. Discovered by reverse-engineering the SPA bundle
(index-D8zvRQef.js), same approach as the NextRequest client API (src/CLAUDE.md).

Reads from the API's structured schedule transactions (source-closest artifact —
richer than PDF re-extraction). Does NOT read from filing PDFs or any Claude
extraction; interests load with confidence 1.0 because the line items are the
filer's own structured entries, not model output. Raw per-filing JSON is
preserved in the Document Lake by the sync (pipelines/form700.py).

Key endpoints (POST, JSON body, shared request model):
  api/searchfilings      — filing headers (filerName "Last, First", formName
                           fppc700_YYYY, periodStart/End, isSuperceded, ...)
  api/searchtransactions — per-schedule line items; content is a JSON string.
                           searchSchedules filters: A1 A2 B C D E Cover Comment.

Privacy note: Schedule B line items include property street addresses
(ParcelOrAddress) exactly as published by the portal — public record under
Gov. Code §81008. Display roll-up (street vs city level) is a framing decision
at the UI layer, not here.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://netfile.com/api/public/sites/api/"
AID = "RICH"
PORTAL_URL = "https://netfile.com/public/RICH/sei"
SCHEDULE_FILTERS = ["A1", "A2", "B", "C", "D", "E"]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (RichmondCommons civic-data pipeline)",
    "Content-Type": "application/json",
}

# NetFile template name -> FPPC schedule code used in economic_interests.schedule
TEMPLATE_TO_SCHEDULE = {
    "ScheduleA1": "A-1",
    "ScheduleA2": "A-2",
    "ScheduleB": "B",
    "ScheduleC": "C",
    "ScheduleD": "D",
    "ScheduleE": "E",
}

SCHEDULE_TO_INTEREST_TYPE = {
    "A-1": "investment",
    "A-2": "investment",
    "B": "real_property",
    "C": "income",
    "D": "gift",
    "E": "travel",
}

# FPPC fair-market-value tiers (Schedules A-1/A-2/B). Verified against the
# portal's own AsString rendering (e.g. 3 -> "$100,001 - $1,000,000").
FMV_RANGES = {
    1: "$2,000 - $10,000",
    2: "$10,001 - $100,000",
    3: "$100,001 - $1,000,000",
    4: "Over $1,000,000",
}


def _post(endpoint: str, body: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    resp = requests.post(BASE_URL + endpoint, json=body, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _paginate(endpoint: str, body: dict[str, Any], page_size: int = 100,
              max_pages: int = 200) -> list[dict[str, Any]]:
    """Fetch all pages of a search endpoint. Stops on empty page or totalCount."""
    items: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        data = _post(endpoint, {**body, "currentPage": page, "pageSize": page_size})
        page_items = data.get("items") or []
        items.extend(page_items)
        total = data.get("totalCount") or 0
        if not page_items or len(items) >= total:
            break
    else:
        logger.warning("%s: hit max_pages=%d with %d items — result may be truncated",
                       endpoint, max_pages, len(items))
    return items


def search_filings(department: Optional[str] = None,
                   filer_name: Optional[str] = None) -> list[dict[str, Any]]:
    """All SEI filing headers for the agency, optionally scoped by department/filer."""
    body: dict[str, Any] = {"aid": AID}
    if department:
        body["searchDepartment"] = department
    if filer_name:
        body["searchFilerName"] = filer_name
    return _paginate("searchfilings", body)


def search_transactions(schedules: Optional[list[str]] = None,
                        department: Optional[str] = None,
                        filer_name: Optional[str] = None) -> list[dict[str, Any]]:
    """Schedule line items (and/or covers) across filings."""
    body: dict[str, Any] = {"aid": AID, "searchSchedules": schedules or SCHEDULE_FILTERS}
    if department:
        body["searchDepartment"] = department
    if filer_name:
        body["searchFilerName"] = filer_name
    return _paginate("searchtransactions", body)


def _parse_content(txn: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(txn.get("content") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _fmv(value: Any) -> Optional[str]:
    try:
        return FMV_RANGES.get(int(value))
    except (TypeError, ValueError):
        return None


def _dollars(amount: Any) -> Optional[str]:
    try:
        return f"${float(amount):,.2f}"
    except (TypeError, ValueError):
        return None


def _date_part(value: Any) -> str:
    return str(value)[:10] if value else ""


def transaction_to_interests(txn: dict[str, Any]) -> list[dict[str, Any]]:
    """Map one API transaction to loader-shaped interest dicts.

    Returns a list because Schedule D nests multiple gifts per source.
    Shapes match form700_extractor's schema keys consumed by
    db.form700.load_form700_to_db: schedule, interest_type, description,
    value_range, location.
    """
    schedule = TEMPLATE_TO_SCHEDULE.get(txn.get("templateName") or "")
    if not schedule:
        return []
    c = _parse_content(txn)
    interest_type = SCHEDULE_TO_INTEREST_TYPE[schedule]

    if schedule == "A-1":
        entity = c.get("NameOfBusinessEntity") or "Business entity"
        detail = c.get("DescriptionAsString") or c.get("Description") or ""
        nature = c.get("NatureOfInvestmentAsString") or ""
        desc = " — ".join(p for p in [entity, detail, nature] if p)
        return [{
            "schedule": schedule, "interest_type": interest_type,
            "description": desc, "value_range": _fmv(c.get("FairMarketValue")),
            "location": None,
        }]

    if schedule == "A-2":
        entity = c.get("EntityName") or "Business entity"
        detail = c.get("Description") or ""
        position = c.get("BusinessPosition") or ""
        parts = [entity, detail]
        if position:
            parts.append(f"position: {position}")
        addr = c.get("Address") or {}
        city = addr.get("City") or None
        return [{
            "schedule": schedule, "interest_type": interest_type,
            "description": " — ".join(p for p in parts if p),
            "value_range": _fmv(c.get("FairMarketValueScheduleA2")),
            "location": city,
        }]

    if schedule == "B":
        nature = c.get("NatureOfInterestAsString") or "Real property"
        parcel = c.get("ParcelOrAddress") or ""
        desc = " — ".join(p for p in [f"Real property ({nature})", parcel] if p)
        return [{
            "schedule": schedule, "interest_type": interest_type,
            "description": desc,
            "value_range": c.get("FairMarketValueAsString") or _fmv(c.get("FairMarketValue")),
            "location": c.get("City") or None,
        }]

    if schedule == "C":
        source = c.get("NameOfIncomeSource") or "Income source"
        activity = c.get("BusinessActivity") or ""
        position = c.get("BusinessPosition") or ""
        reason = c.get("ReasonForIncomeAsString") or ""
        parts = [source]
        if activity:
            parts.append(activity)
        if position:
            parts.append(f"position: {position}")
        if reason:
            parts.append(f"income type: {reason}")
        addr = c.get("Address") or {}
        # Income enum tiers (GrossIncomeReceivedScheduleC1) are not rendered by
        # the portal; omit value_range rather than guess the mapping.
        return [{
            "schedule": schedule, "interest_type": interest_type,
            "description": " — ".join(parts),
            "value_range": None,
            "location": addr.get("City") or None,
        }]

    if schedule == "D":
        source = c.get("NameOfSource") or "Gift source"
        addr = c.get("Address") or {}
        out = []
        for gift in c.get("Gifts") or [{}]:
            what = gift.get("Description") or "Gift"
            when = _date_part(gift.get("GiftDate"))
            desc = f"{what} — {source}" + (f" ({when})" if when else "")
            out.append({
                "schedule": schedule, "interest_type": interest_type,
                "description": desc,
                "value_range": _dollars(gift.get("Amount")),
                "location": addr.get("City") or None,
            })
        return out

    if schedule == "E":
        source = c.get("NameOfSource") or "Travel payment source"
        travel = c.get("TravelDescription") or ""
        kind = c.get("TypeOfPaymentAsString") or ""
        when = _date_part(c.get("StartDate"))
        parts = [f"Travel/payment — {source}"]
        if travel:
            parts.append(f"destination: {travel}")
        if kind:
            parts.append(kind)
        if when:
            parts.append(when)
        addr = c.get("Address") or {}
        return [{
            "schedule": schedule, "interest_type": interest_type,
            "description": " — ".join(parts),
            "value_range": _dollars(c.get("Amount")),
            "location": addr.get("City") or None,
        }]

    return []


def _statement_type_from_cover(cover_content: dict[str, Any]) -> Optional[str]:
    st = cover_content.get("StatementType") or {}
    if st.get("IsAnnual"):
        return "annual"
    if st.get("IsAssuming"):
        return "assuming_office"
    if st.get("IsLeaving"):
        return "leaving_office"
    if st.get("IsCandidate"):
        return "candidate"
    return None


def _filing_year(filing: dict[str, Any]) -> int:
    """Form year from formName ('fppc700_2026' -> 2026), falling back to filingDate."""
    form_name = filing.get("formName") or ""
    if "_" in form_name:
        tail = form_name.rsplit("_", 1)[-1]
        if tail.isdigit():
            return int(tail)
    return int(_date_part(filing.get("filingDate"))[:4] or 0)


JOIN_TOLERANCE_DAYS = 45


def _start_date(obj: dict[str, Any]) -> Optional["_dt.date"]:
    raw = _date_part(obj.get("periodStart"))
    try:
        return _dt.date.fromisoformat(raw)
    except ValueError:
        return None


def _match_groups_to_filings(
    filings: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, dict[str, Any]]]:
    """Attach transaction groups to filings by filer + nearest period start.

    The two search endpoints expose DIFFERENT id spaces (searchfilings.filingId
    is a GUID, searchtransactions.filingId is a numeric local id, and the hex
    `id` fields don't correspond either) — filer name + reporting period is the
    only shared linkage, and it is fuzzy on BOTH ends: transaction timestamps
    are UTC ("2025-01-01T08:00:00Z") vs naive Pacific on filings, and some
    filing headers say the period starts Jan 1 while their line items carry the
    filer's assumption date days later (observed: Bana 2023-01-01 vs
    2023-01-11). So: group transactions by (filer, exact start), then attach
    each group to the operative filing of that filer whose periodStart is
    NEAREST, within JOIN_TOLERANCE_DAYS. One group joins at most one filing.

    Returns ({filing_index: [txns]}, {filing_index: cover_content}).
    """
    filing_starts: dict[str, list[tuple[int, "_dt.date"]]] = {}
    for idx, filing in enumerate(filings):
        start = _start_date(filing)
        if start is not None:
            filing_starts.setdefault(filing.get("filerName") or "", []).append((idx, start))

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for txn in transactions:
        if txn.get("isSuperceded"):
            continue
        key = (txn.get("filerName") or "", _date_part(txn.get("periodStart")))
        groups.setdefault(key, []).append(txn)

    txns_by_filing: dict[int, list[dict[str, Any]]] = {}
    covers_by_filing: dict[int, dict[str, Any]] = {}
    for (filer, start_raw), group in groups.items():
        try:
            group_start = _dt.date.fromisoformat(start_raw)
        except ValueError:
            continue
        candidates = filing_starts.get(filer, [])
        best: Optional[tuple[int, int]] = None  # (delta_days, filing_index)
        for idx, start in candidates:
            delta = abs((start - group_start).days)
            if delta <= JOIN_TOLERANCE_DAYS and (best is None or delta < best[0]):
                best = (delta, idx)
        if best is None:
            schedules = sorted({t.get("templateName") or "?" for t in group})
            logger.warning(
                "No filing within %dd for txn group filer=%r start=%s (%d items: %s)",
                JOIN_TOLERANCE_DAYS, filer, start_raw, len(group), ",".join(schedules))
            continue
        idx = best[1]
        for txn in group:
            if txn.get("templateName") == "Cover":
                # Prefer the non-archived cover of an amendment chain.
                if idx not in covers_by_filing or not txn.get("isArchived"):
                    covers_by_filing[idx] = _parse_content(txn)
            else:
                txns_by_filing.setdefault(idx, []).append(txn)
    return txns_by_filing, covers_by_filing


def build_filing_records(filings: list[dict[str, Any]],
                         transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join filing headers with their schedule transactions and covers.

    Returns loader-ready records:
      {"extraction": {...}, "filing_metadata": {...}, "raw": {...}}
    Superseded filings/transactions are skipped (amendment chains keep only
    the operative version — mirrors the netfile campaign dedup lesson).
    """
    # NB: isPubliclyVisible is False on every filing the portal displays —
    # it does not gate portal visibility; do not filter on it.
    operative = [f for f in filings if not f.get("isSuperceded")]
    txns_by_filing, covers_by_filing = _match_groups_to_filings(operative, transactions)

    records = []
    for idx, filing in enumerate(operative):
        interests: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for txn in txns_by_filing.get(idx, []):
            for interest in transaction_to_interests(txn):
                dedup = (interest["schedule"], interest["description"],
                         interest["value_range"], interest["location"])
                if dedup in seen:
                    continue
                seen.add(dedup)
                interests.append(interest)

        cover = covers_by_filing.get(idx, {})
        statement_type = _statement_type_from_cover(cover) or "annual"

        extraction = {
            "filer_name": filing.get("filerName") or "",
            "filer_agency": "City of Richmond",
            "filer_position": (filing.get("positionName") or "").split(",")[0],
            "statement_type": statement_type,
            "period_start": _date_part(filing.get("periodStart")) or None,
            "period_end": _date_part(filing.get("periodEnd")) or None,
            "no_interests_declared": len(interests) == 0,
            "interests": interests,
            # Structured portal line items, not model output.
            "extraction_confidence": 1.0,
            "extraction_notes": "netfile_sei_api structured transactions (no LLM extraction)",
        }
        filing_metadata = {
            "filer_name": filing.get("filerName") or "",
            "agency": "City of Richmond",
            "position": (filing.get("positionName") or "").split(",")[0],
            "statement_type": statement_type,
            "filing_year": _filing_year(filing),
            "source": "netfile_sei",
            "source_url": PORTAL_URL,
            "document_id": None,  # sync fills after Document Lake ingest
        }
        records.append({
            "extraction": extraction,
            "filing_metadata": filing_metadata,
            "raw": {"filing": filing, "transactions": txns_by_filing.get(idx, []), "cover": cover},
        })
    return records


def fetch_filing_records(department: Optional[str] = None) -> list[dict[str, Any]]:
    """One-call discovery: filings + schedule/cover transactions, joined."""
    filings = search_filings(department=department)
    transactions = search_transactions(
        schedules=SCHEDULE_FILTERS + ["Cover"], department=department
    )
    logger.info("NetFile SEI API: %d filings, %d transactions (department=%s)",
                len(filings), len(transactions), department or "ALL")
    return build_filing_records(filings, transactions)
