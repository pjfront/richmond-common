"""Richmond Lobbyist Registration Client.

Fetches lobbyist registration records per Richmond Municipal Code Chapter 2.54
("Regulation of Lobbyists"). Three lobbyist types: Contract ($1K/month or
$3K/year or 10+ contacts), Business/Organization (compensated employees with
10+ contacts), and Expenditure ($3K+/year direct spending).

The *absence* of registration by vendor representatives who are influencing
procurement is itself a finding — this is one of S13's key transparency signals.

Data access strategy:
1. Download PDF registration lists from City Clerk Document Center (FID=389)
   via direct Document ID URLs (no JavaScript rendering needed)
2. Render source PDF pages locally and extract the lobbyist-year grid with the
   optional Kimi vision tier
3. Optionally cross-reference with CA Secretary of State lobbyist portal

The Document Center folder loads its file list via JavaScript, so HTML scraping
returns nothing. Direct PDF download by Document ID bypasses this entirely.

Tier 1 source (official government records).

Usage:
    from lobbyist_client import fetch_lobbyist_registrations
    registrations = fetch_lobbyist_registrations()
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from llm_client import LLMClient, VISION_MODEL, get_model_route

logger = logging.getLogger(__name__)

DEFAULT_FIPS = "0660620"

# CivicPlus Document Center base URL for Richmond
DOCUMENT_CENTER_BASE = "https://www.ci.richmond.ca.us/DocumentCenter/View"

# Known PDF Document IDs containing lobbyist registration lists.
# These are stable CivicPlus identifiers — each new upload gets a new ID.
# Updated 2026-03-21: discovered via browser rendering of FID=389 folder.
RICHMOND_LOBBYIST_DOCS = {
    75427: {
        "title": "List of Registered Lobbyists from 2014-2025",
        "year_range": (2014, 2025),
        "uploaded": "2025-06-25",
    },
    27460: {
        "title": "List of Registered Lobbyists from 2000-2013",
        "year_range": (2000, 2013),
        "uploaded": "2013-08-12",
    },
}

# California Secretary of State lobbyist portal (state-level cross-reference)
CA_SOS_LOBBYIST_URL = "https://cal-access.sos.ca.gov/Lobbying/"
CA_SOS_LOBBYIST_SEARCH = "https://cal-access.sos.ca.gov/Lobbying/Employers/list.aspx"

REQUEST_TIMEOUT = 30
RETRY_COUNT = 3
RETRY_BACKOFF = 2.0
MAX_VISION_PAGES = 40


class LobbyistVisionOutputError(ValueError):
    """A paid vision response did not prove a structurally valid result."""


class LobbyistExtractionReceiptError(RuntimeError):
    """Durable extraction-cache access failed before or after a paid call."""

# Prompts are version-controlled configuration. The exact content hash is part
# of the durable receipt key, so editing the prompt automatically invalidates
# stale cached model output for the same PDF/model.
_EXTRACTION_PROMPT_PATH = (
    Path(__file__).parent / "prompts" / "lobbyist_pdf_extraction.txt"
)
EXTRACTION_PROMPT = _EXTRACTION_PROMPT_PATH.read_text(encoding="utf-8").strip()
EXTRACTION_PROMPT_VERSION = hashlib.sha256(
    EXTRACTION_PROMPT.encode("utf-8")
).hexdigest()


def _resolve_config(city_fips: str | None = None) -> tuple[dict, str]:
    """Resolve lobbyist config from city registry or use defaults."""
    if city_fips is not None:
        from city_config import get_data_source_config

        try:
            cfg = get_data_source_config(city_fips, "lobbyist_registrations")
            return cfg, city_fips
        except Exception:
            pass
    return {
        "platform": "City Clerk",
        "document_ids": list(RICHMOND_LOBBYIST_DOCS.keys()),
        "agency_name": "City of Richmond",
    }, DEFAULT_FIPS


def _make_request(url: str, *, timeout: int = REQUEST_TIMEOUT) -> requests.Response:
    """Make HTTP GET request with retry logic."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Richmond Common Transparency Project)",
        "Accept": "text/html, application/pdf, application/json",
    }

    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < RETRY_COUNT - 1:
                wait = RETRY_BACKOFF ** (attempt + 1)
                logger.warning(
                    "Request to %s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    url, attempt + 1, RETRY_COUNT, e, wait,
                )
                time.sleep(wait)
            else:
                raise


def _normalize_name(name: str) -> str:
    """Normalize a person/org name."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip())


# ── PDF Download + Vision Extraction ──────────────────────────


def download_lobbyist_pdf(doc_id: int) -> bytes:
    """Download a lobbyist registration PDF by CivicPlus Document ID.

    Args:
        doc_id: CivicPlus Document Center document ID.

    Returns:
        Raw PDF bytes.

    Raises:
        requests.RequestException: If download fails after retries.
    """
    url = f"{DOCUMENT_CENTER_BASE}/{doc_id}"
    logger.info("Downloading lobbyist PDF: doc_id=%d from %s", doc_id, url)
    resp = _make_request(url, timeout=60)

    if not resp.content[:5] == b"%PDF-":
        raise ValueError(f"Document {doc_id} is not a PDF (got {resp.headers.get('content-type', 'unknown')})")

    logger.info("Downloaded %d bytes for doc_id=%d", len(resp.content), doc_id)
    return resp.content


def extract_lobbyists_from_pdf(
    pdf_bytes: bytes,
    doc_id: int,
    *,
    model: str = VISION_MODEL,
) -> list[dict]:
    """Extract lobbyist registration data from the source PDF with Kimi vision.

    Each source page is rendered locally with PyMuPDF and sent as an
    OpenAI-compatible ``image_url`` block. This avoids the previous broken path
    that passed an Anthropic ``document`` block to DeepSeek's text-only API.

    Args:
        pdf_bytes: Raw PDF file content.
        doc_id: Document ID (for logging/source tracking).
        model: Explicit configured vision route. Defaults to Kimi K2.6.

    Returns:
        List of {"name": str, "years": list[int]} dicts.
    """
    route = get_model_route(model)
    if not route.supports_vision:
        raise ValueError(f"Configured model {route.model!r} does not support vision")
    if not os.environ.get(route.api_key_env):
        logger.error(
            "%s not set — cannot run optional lobbyist PDF vision extraction",
            route.api_key_env,
        )
        return []

    image_blocks = _render_pdf_image_blocks(pdf_bytes)
    client = LLMClient()

    logger.info("Sending doc_id=%d to LLM for extraction...", doc_id)

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    *image_blocks,
                ],
            }
        ],
        thinking={"type": "disabled"},
    )

    if message.stop_reason == "max_tokens":
        raise LobbyistVisionOutputError(
            f"Vision extraction for doc_id={doc_id} reached max_tokens"
        )
    text_blocks = [
        block.text
        for block in message.content
        if getattr(block, "type", "text") == "text"
        and isinstance(getattr(block, "text", None), str)
        and block.text.strip()
    ]
    unexpected_blocks = [
        block
        for block in message.content
        if getattr(block, "type", "text") != "text"
    ]
    if unexpected_blocks or not text_blocks:
        raise LobbyistVisionOutputError(
            f"Vision extraction for doc_id={doc_id} returned no exclusive text result"
        )
    response_text = "\n".join(text_blocks)
    logger.info(
        "Vision extraction for doc_id=%d: %d input tokens, %d output tokens",
        doc_id, message.usage.input_tokens, message.usage.output_tokens,
    )

    return _parse_vision_response(response_text, doc_id)


def _render_pdf_image_blocks(pdf_bytes: bytes) -> list[dict]:
    """Render every source PDF page to a bounded list of image input blocks."""
    import fitz  # PyMuPDF; project-standard parser for government PDFs

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if len(doc) > MAX_VISION_PAGES:
            raise ValueError(
                f"Lobbyist PDF has {len(doc)} pages; refusing to send more than "
                f"{MAX_VISION_PAGES} pages to the paid vision route"
            )
        blocks: list[dict] = []
        matrix = fitz.Matrix(2, 2)
        for page in doc:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}"},
            })
        return blocks
    finally:
        doc.close()


def _parse_vision_response(response_text: str, doc_id: int) -> list[dict]:
    """Parse LLM response into lobbyist records.

    Args:
        response_text: Raw text response from the LLM.
        doc_id: Document ID for error context.

    Returns:
        List of {"name": str, "years": list[int]} dicts.
    """
    text = response_text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LobbyistVisionOutputError(
            f"Vision response for doc_id={doc_id} is not valid JSON"
        ) from exc

    return _validate_vision_records(data, doc_id)


def _validate_vision_records(data, doc_id: int) -> list[dict]:
    """Validate an LLM response or cached receipt without silently dropping rows."""
    if not isinstance(data, list):
        raise LobbyistVisionOutputError(
            f"Vision response for doc_id={doc_id} must be a JSON list"
        )

    merged: dict[str, set[int]] = {}
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise LobbyistVisionOutputError(
                f"Vision row {index} for doc_id={doc_id} must be an object"
            )
        raw_name = item.get("name")
        if not isinstance(raw_name, str):
            raise LobbyistVisionOutputError(
                f"Vision row {index} for doc_id={doc_id} has a non-string name"
            )
        name = _normalize_name(raw_name)
        if not name:
            raise LobbyistVisionOutputError(
                f"Vision row {index} for doc_id={doc_id} has an empty name"
            )
        years = item.get("years")
        if not isinstance(years, list) or not years:
            raise LobbyistVisionOutputError(
                f"Vision row {index} for doc_id={doc_id} must have a non-empty years list"
            )
        for year in years:
            if (
                isinstance(year, bool)
                or not isinstance(year, int)
                or not 1990 <= year <= 2050
            ):
                raise LobbyistVisionOutputError(
                    f"Vision row {index} for doc_id={doc_id} has invalid year {year!r}"
                )
        merged.setdefault(name, set()).update(years)

    results = [
        {"name": name, "years": sorted(years)}
        for name, years in merged.items()
    ]

    logger.info("Parsed %d lobbyist entities from doc_id=%d", len(results), doc_id)
    return results


def _vision_records_to_registrations(
    records: list[dict],
    doc_id: int,
    source_url: str,
) -> list[dict]:
    """Convert Vision extraction records to registration dicts for DB loader.

    Each Vision record is {"name": str, "years": [int, ...]}.
    We produce one registration dict per lobbyist (not per year).
    Years go into metadata; earliest year becomes registration_date.

    Args:
        records: Output from extract_lobbyists_from_pdf() or _parse_vision_response().
        doc_id: Document ID for source tracking.
        source_url: Full URL of the source PDF.

    Returns:
        List of registration dicts compatible with load_lobbyists_to_db().
    """
    current_year = datetime.now().year
    registrations = []

    for record in records:
        name = record["name"]
        years = record["years"]
        earliest = min(years)
        latest = max(years)
        is_current = current_year in years

        registrations.append({
            "lobbyist_name": name,
            "lobbyist_firm": None,
            "client_name": "See registration filing",
            "registration_date": f"{earliest}-01-01",
            "expiration_date": f"{latest}-12-31" if not is_current else None,
            "topics": None,
            "city_agencies": None,
            "lobbyist_address": None,
            "lobbyist_phone": None,
            "lobbyist_email": None,
            "status": "active" if is_current else "expired",
            "source": "city_clerk",
            "source_identifier": f"doc_{doc_id}_{name}",
            "source_url": source_url,
            "metadata": {
                "source_method": "pdf_vision_extraction",
                "document_id": doc_id,
                "years_registered": years,
                "earliest_year": earliest,
                "latest_year": latest,
            },
        })

    return registrations


def _load_extraction_receipt(
    conn,
    *,
    city_fips: str,
    doc_id: int,
    content_sha256: str,
    provider: str,
    model: str,
    prompt_version: str,
) -> list[dict] | None:
    """Return a structurally revalidated cached extraction, including ``[]``."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT records
                   FROM lobbyist_document_extractions
                   WHERE city_fips = %s
                     AND document_id = %s
                     AND content_sha256 = %s
                     AND extraction_provider = %s
                     AND extraction_model = %s
                     AND prompt_version = %s""",
                (
                    city_fips,
                    doc_id,
                    content_sha256,
                    provider,
                    model,
                    prompt_version,
                ),
            )
            row = cur.fetchone()
        # Do not hold an idle transaction open across a potentially long paid
        # vision request. The source sync has no pending data writes here.
        conn.commit()
    except Exception as exc:
        raise LobbyistExtractionReceiptError(
            "Cannot read lobbyist extraction receipts; apply migration 131 "
            "before enabling paid lobbyist vision extraction."
        ) from exc
    if not row:
        return None
    data = row[0]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise LobbyistExtractionReceiptError(
                f"Cached extraction for doc_id={doc_id} contains invalid JSON"
            ) from exc
    try:
        return _validate_vision_records(data, doc_id)
    except LobbyistVisionOutputError as exc:
        raise LobbyistExtractionReceiptError(
            f"Cached extraction for doc_id={doc_id} failed structural validation"
        ) from exc


def _persist_extraction_receipt(
    conn,
    *,
    city_fips: str,
    doc_id: int,
    content_sha256: str,
    records: list[dict],
    provider: str,
    model: str,
    prompt_version: str,
    source_url: str,
) -> None:
    """Persist a validated result before allowing a later run to skip spend."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO lobbyist_document_extractions (
                     city_fips, document_id, content_sha256, records,
                     extraction_provider, extraction_model, prompt_version, source_url,
                     source_tier, confidence_score, ai_generated
                   ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, 1, 0.90, TRUE)
                   ON CONFLICT (
                     city_fips, document_id, content_sha256,
                     extraction_provider, extraction_model, prompt_version
                   )
                   DO NOTHING""",
                (
                    city_fips,
                    doc_id,
                    content_sha256,
                    json.dumps(records),
                    provider,
                    model,
                    prompt_version,
                    source_url,
                ),
            )
        # The receipt is a source-closest durable cache. Commit it before the
        # downstream loader so a crash can reconstruct and retry the load
        # without purchasing the same extraction again.
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        raise LobbyistExtractionReceiptError(
            "Paid lobbyist extraction completed but its durable receipt could "
            "not be stored; refusing a green sync."
        ) from exc


def fetch_lobbyist_registrations_pdf(
    *,
    city_fips: str | None = None,
    conn=None,
    include_status: bool = False,
):
    """Fetch lobbyist registrations by downloading and extracting PDF lists.

    Downloads known registration list PDFs from the City Clerk Document Center
    and extracts structured data using Claude Vision API.

    Returns:
        List of normalized registration dicts.
    """
    config, fips = _resolve_config(city_fips)
    doc_ids = config.get("document_ids", list(RICHMOND_LOBBYIST_DOCS.keys()))

    route = get_model_route(VISION_MODEL)
    incomplete_reasons: list[str] = []
    if not os.environ.get(route.api_key_env):
        logger.warning(
            "%s is not configured; skipping the optional City Clerk PDF "
            "vision tier without recording a terminal-zero receipt",
            route.api_key_env,
        )
        result = []
        status = {
            "retryable_incomplete": True,
            "required_source_incomplete": True,
            "incomplete_reasons": [
                f"City Clerk PDF extraction unavailable: {route.api_key_env} is not configured"
            ],
        }
        return (result, status) if include_status else result

    owned_conn = False
    if conn is None:
        try:
            from db import get_connection

            conn = get_connection()
            owned_conn = True
        except Exception as exc:
            raise LobbyistExtractionReceiptError(
                "Cannot connect to the extraction receipt database; refusing "
                "a paid lobbyist vision call."
            ) from exc

    all_registrations = []
    try:
        for doc_id in doc_ids:
            doc_meta = RICHMOND_LOBBYIST_DOCS.get(doc_id, {})
            source_url = f"{DOCUMENT_CENTER_BASE}/{doc_id}"

            try:
                pdf_bytes = download_lobbyist_pdf(doc_id)
            except (requests.RequestException, ValueError) as e:
                logger.warning("Failed to download doc_id=%d: %s", doc_id, e)
                incomplete_reasons.append(
                    f"City Clerk lobbyist document {doc_id} download failed: {e}"
                )
                continue

            content_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            records = _load_extraction_receipt(
                conn,
                city_fips=fips,
                doc_id=doc_id,
                content_sha256=content_sha256,
                provider=route.provider,
                model=route.model,
                prompt_version=EXTRACTION_PROMPT_VERSION,
            )
            cache_hit = records is not None
            if records is None:
                records = extract_lobbyists_from_pdf(
                    pdf_bytes,
                    doc_id,
                    model=VISION_MODEL,
                )
                # ``extract_lobbyists_from_pdf`` returns [] only for a valid
                # explicit empty list when the key is configured. Cache that
                # terminal result as well as non-empty records.
                _persist_extraction_receipt(
                    conn,
                    city_fips=fips,
                    doc_id=doc_id,
                    content_sha256=content_sha256,
                    records=records,
                    provider=route.provider,
                    model=route.model,
                    prompt_version=EXTRACTION_PROMPT_VERSION,
                    source_url=source_url,
                )

            if not records:
                logger.info(
                    "Validated empty lobbyist extraction for doc_id=%d (%s)%s",
                    doc_id,
                    doc_meta.get("title", "unknown"),
                    " [cached]" if cache_hit else "",
                )
                continue

            registrations = _vision_records_to_registrations(
                records, doc_id, source_url
            )
            logger.info(
                "%s %d registrations from doc_id=%d (%s)",
                "Loaded cached" if cache_hit else "Extracted",
                len(registrations), doc_id, doc_meta.get("title", "unknown"),
            )
            all_registrations.extend(registrations)
        status = {
            "retryable_incomplete": bool(incomplete_reasons),
            "required_source_incomplete": bool(incomplete_reasons),
            "incomplete_reasons": incomplete_reasons,
        }
        return (all_registrations, status) if include_status else all_registrations
    finally:
        if owned_conn:
            try:
                conn.close()
            except Exception:
                pass


# ── CA Secretary of State (State-Level Cross-Reference) ───────


def fetch_ca_sos_lobbyists(
    *,
    employer_name: str = "City of Richmond",
) -> list[dict]:
    """Fetch lobbyist registrations from CA Secretary of State.

    State-level lobbyist data cross-references with local registrations.
    State lobbyists are registered under the Political Reform Act (Gov Code
    §82039), separate from local ordinances.

    This is supplementary data — the primary source is the City Clerk.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 required")
        return []

    try:
        resp = _make_request(
            CA_SOS_LOBBYIST_SEARCH,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning("CA SOS lobbyist search failed: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if not cells:
                continue
            row_text = " ".join(cells).lower()
            if "richmond" not in row_text:
                continue

            link = row.find("a", href=True)
            detail_url = link["href"] if link else None
            if detail_url and not detail_url.startswith("http"):
                detail_url = f"https://cal-access.sos.ca.gov{detail_url}"

            results.append({
                "lobbyist_name": cells[0] if cells else "Unknown",
                "lobbyist_firm": None,
                "client_name": cells[1] if len(cells) > 1 else "Unknown",
                "registration_date": None,
                "expiration_date": None,
                "topics": None,
                "city_agencies": None,
                "lobbyist_address": None,
                "lobbyist_phone": None,
                "lobbyist_email": None,
                "status": "active",
                "source_identifier": f"ca_sos_{cells[0]}_{cells[1] if len(cells) > 1 else ''}",
                "source_url": detail_url,
                "metadata": {"source_method": "ca_sos_search", "raw_cells": cells},
            })

    logger.info("CA SOS returned %d Richmond-related lobbyist records", len(results))
    return results


# ── Main Entry Point ──────────────────────────────────────────


def fetch_lobbyist_registrations(
    *,
    city_fips: str | None = None,
    include_state: bool = True,
    conn=None,
    include_status: bool = False,
):
    """Fetch all lobbyist registrations for a city.

    Combines local City Clerk PDF data with optional state-level cross-reference.

    Args:
        city_fips: FIPS code (default: Richmond CA).
        include_state: Also search CA SOS lobbyist portal.

    Returns:
        List of normalized registration dicts ready for load_lobbyists_to_db().
    """
    config, fips = _resolve_config(city_fips)

    # Primary: City Clerk PDF registration lists
    pdf_result = fetch_lobbyist_registrations_pdf(
        city_fips=city_fips,
        conn=conn,
        include_status=True,
    )
    registrations, source_status = pdf_result

    # Secondary: CA Secretary of State (state-level lobbyists)
    if include_state:
        state_records = fetch_ca_sos_lobbyists(
            employer_name=config.get("agency_name", "City of Richmond"),
        )
        for record in state_records:
            record["source"] = "ca_sos_lobbying"
        registrations.extend(state_records)

    # Deduplicate by source_identifier
    seen: set[str] = set()
    unique = []
    for r in registrations:
        key = r.get("source_identifier", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    logger.info(
        "Total lobbyist registrations for FIPS %s: %d (after dedup from %d)",
        fips, len(unique), len(registrations),
    )
    return (unique, source_status) if include_status else unique


# ── CLI ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch lobbyist registrations")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="FIPS code")
    parser.add_argument("--no-state", action="store_true", help="Skip CA SOS search")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    records = fetch_lobbyist_registrations(
        city_fips=args.city_fips,
        include_state=not args.no_state,
    )

    print(f"\nFound {len(records)} lobbyist registration(s):")
    for r in records:
        years = (r.get("metadata") or {}).get("years_registered", [])
        status = r.get("status", "unknown")
        years_str = f" ({', '.join(str(y) for y in years)})" if years else ""
        print(f"  [{status}] {r['lobbyist_name']}{years_str}")
        if r.get("lobbyist_firm"):
            print(f"    Firm: {r['lobbyist_firm']}")
        if r.get("client_name") and r["client_name"] != "See registration filing":
            print(f"    Client: {r['client_name']}")
