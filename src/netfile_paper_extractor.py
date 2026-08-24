"""
NetFile paper-filing PDF extractor.

Reads paper-filed campaign finance PDFs (FPPC forms 460 and 497) downloaded
from the NetFile public portal, extracts contribution rows via PyMuPDF +
DeepSeek tool calling (with bounded local OCR for scanned Form 497 Part 1
filings and an optional Kimi vision fallback), and writes JSON
in the schema consumed by
src/load_paper_filings.py and the sync_netfile paper-filing loop in
src/data_sync.py.

Reads from: NetFile public portal PDFs at /public/image/{filing_id} (raw).
Does NOT read from: any derivative summary or pre-extracted text — every
filing is re-parsed from the source PDF on demand.

Why: paper filers (e.g., Anderson for Mayor 2026) don't appear in the
NetFile Connect2 transaction API. Without this extractor, their
contributions reach Richmond Commons only via hand-curated JSON, which
goes stale between filing periods (Q1 2026: Anderson page understated
by ~$14k as of 2026-04-27).

Usage:
  python netfile_paper_extractor.py                   # all paper filers
  python netfile_paper_extractor.py --committee "Anderson for Mayor 2026"
  python netfile_paper_extractor.py --filing-id 215523926 --committee "..."
  python netfile_paper_extractor.py --dry-run         # extract but don't write JSON
"""
from __future__ import annotations

import llm_budget_lock  # noqa: F401  # must import before LLM SDK

import argparse
import base64
import json
import math
import os
import re
import sys
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation
from numbers import Real
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import fitz  # PyMuPDF
from llm_client import (
    LLMClient,
    OPENAI_LUNA_MODEL,
    VISION_MODEL,
    get_model_route,
)

from netfile_client import (
    API_BASE,
    download_paper_filing,
    extract_filers,
    fetch_all_transactions,
    fetch_filing_rss,
    identify_paper_filers,
)

PAPER_FILINGS_DIR = Path(__file__).parent / "data" / "paper_filings"
PDF_CACHE_DIR = PAPER_FILINGS_DIR / "_pdf_cache"
DEFAULT_FIPS = "0660620"
MODEL = "deepseek-v4-pro"
MAX_VISION_PAGES = 40
MAX_SUMMARY_VISION_PAGES = 6
MAX_LUNA_SUMMARY_ATTEMPTS = 2
MAX_FORM497_LOCAL_OCR_PAGES = 4
MAX_FORM497_LOCAL_OCR_CHARS = 50_000
MIN_FORM497_LOCAL_OCR_LINE_CONFIDENCE = 0.80
FORM460_SUMMARY_VISION_CANDIDATES = (OPENAI_LUNA_MODEL, VISION_MODEL)


class OptionalVisionUnavailableError(RuntimeError):
    """Raised when an image-only filing cannot reach its optional vision route."""


class LocalOCRUnavailableError(RuntimeError):
    """Raised when bounded offline OCR cannot prove a usable Form 497 scan."""


class TextExtractionIncompleteError(RuntimeError):
    """Raised when a text response cannot prove a complete extraction."""


class VisionExtractionIncompleteError(RuntimeError):
    """Raised when a vision response cannot prove a complete extraction."""


class Form460SummaryIncompleteError(RuntimeError):
    """Raised when a paid Form 460 summary response is not provably valid."""


def _select_form460_summary_vision_model() -> str:
    """Select the cheapest explicitly configured image-summary route.

    GPT-5.6 Luna is limited to this bounded Form 460 summary path. Full filing
    contribution extraction continues to use ``VISION_MODEL`` and therefore
    cannot drift to OpenAI. Direct Kimi remains an optional second choice when
    its own credential is configured.
    """
    unavailable: list[str] = []
    for model in FORM460_SUMMARY_VISION_CANDIDATES:
        route = get_model_route(model)
        if not route.supports_vision:
            unavailable.append(f"{model} is not vision-enabled")
            continue
        if not os.environ.get(route.api_key_env, "").strip():
            unavailable.append(f"{route.api_key_env} is not set")
            continue
        return model
    raise OptionalVisionUnavailableError(
        "No configured Form 460 summary vision route is available ("
        + "; ".join(unavailable)
        + "); image-only Form 460 summary remains pending"
    )


# One data_sync process runs the NetFile source and then its reconciliation
# enrichment. Keep successes and attempts in memory across those phases so a
# freshly extracted cover summary is never paid for twice in the same run.
# Successful summaries are also persisted to the canonical DB cache after the
# source artifact write; this registry is the fallback when persistence is
# temporarily unavailable.
_FORM460_SUMMARY_RUN_CACHE: dict[str, dict] = {}
_FORM460_SUMMARY_RUN_ATTEMPTS: set[str] = set()
_FORM460_SUMMARY_RUN_FAILURES: dict[str, str] = {}


def reset_form460_summary_run_state() -> None:
    """Start a fresh process-local Form 460 summary reuse scope."""
    _FORM460_SUMMARY_RUN_CACHE.clear()
    _FORM460_SUMMARY_RUN_ATTEMPTS.clear()
    _FORM460_SUMMARY_RUN_FAILURES.clear()


def get_form460_summary_run_cache() -> dict[str, dict]:
    """Return defensive copies of summaries extracted in this run."""
    return {
        filing_id: {
            "committee": entry["committee"],
            "summary": dict(entry["summary"]),
        }
        for filing_id, entry in _FORM460_SUMMARY_RUN_CACHE.items()
    }


def get_form460_summary_run_failures() -> dict[str, str]:
    """Return paid/eligible summary attempts that failed closed this run."""
    return dict(_FORM460_SUMMARY_RUN_FAILURES)


def form460_summary_attempted_this_run(filing_id: str) -> bool:
    """Return whether this filing already consumed its run-local attempt."""
    return str(filing_id) in _FORM460_SUMMARY_RUN_ATTEMPTS


def record_form460_summary_run_failure(filing_id: str, detail: str) -> None:
    """Record an incomplete attempt so reconciliation does not pay again."""
    filing_id = str(filing_id)
    _FORM460_SUMMARY_RUN_ATTEMPTS.add(filing_id)
    _FORM460_SUMMARY_RUN_FAILURES[filing_id] = str(detail)[:500]


# Forms that carry contribution rows. Form 410 = Statement of Organization
# (no contributions). Form 460 Schedule A = itemized monetary contributions.
# Form 497 = late-contribution report (Part 1 = received by this committee,
# Part 2 = contribution made to another committee — only relevant when a
# different committee's 497 names this candidate as recipient).
EXTRACTABLE_FORMS = {"460", "497", "497_received"}

CONTRIBUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "contributions": {
            "type": "array",
            "description": "All itemized monetary contributions in this filing. Skip non-monetary, loans, and refunds.",
            "items": {
                "type": "object",
                "properties": {
                    "contributor_name": {"type": "string"},
                    "amount": {"type": "number", "description": "Dollars (e.g., 250.00). Positive = contribution received."},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "city": {"type": "string"},
                    "state": {"type": "string", "description": "Two-letter US state abbreviation."},
                    "zip": {"type": "string"},
                    "entity_code": {
                        "type": "string",
                        "enum": ["IND", "COM", "OTH", "SCC", "PTY"],
                        "description": "IND=individual, COM=committee/PAC, OTH=business, SCC=small contributor committee, PTY=political party.",
                    },
                    "occupation": {"type": "string"},
                    "contributor_employer": {"type": "string"},
                },
                "required": ["contributor_name", "amount", "date"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["contributions"],
    "additionalProperties": False,
}


def _validate_contribution_response(response, error_type, label: str) -> list[dict]:
    """Validate one contribution tool response before accepting any row."""
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "max_tokens":
        raise error_type(
            f"{label} response reached max_tokens before a complete tool result"
        )
    if stop_reason != "tool_use":
        raise error_type(
            f"{label} response did not stop on the required tool "
            f"(stop_reason={stop_reason!r})"
        )

    content = getattr(response, "content", None)
    if not isinstance(content, list):
        raise error_type(f"{label} response content must be a list")

    tool_blocks = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            if str(getattr(block, "text", "") or "").strip():
                raise error_type(
                    f"{label} response returned text instead of only the "
                    "required structured tool result"
                )
            continue
        if block_type != "tool_use":
            raise error_type(
                f"{label} response returned unsupported block type {block_type!r}"
            )
        tool_blocks.append(block)

    if len(tool_blocks) != 1:
        raise error_type(f"{label} response must contain exactly one tool result")
    tool_block = tool_blocks[0]
    if getattr(tool_block, "name", None) != "save_contributions":
        raise error_type(f"{label} response used the wrong tool")

    tool_input = getattr(tool_block, "input", None)
    if not isinstance(tool_input, dict):
        raise error_type(f"{label} tool input was not a JSON object")
    if "_raw" in tool_input:
        raise error_type(f"{label} tool arguments were not valid JSON")
    if set(tool_input) != {"contributions"}:
        raise error_type(
            f"{label} tool result must contain only the contributions field"
        )

    rows = tool_input["contributions"]
    if not isinstance(rows, list):
        raise error_type(f"{label} tool contributions must be a list")

    item_schema = CONTRIBUTION_SCHEMA["properties"]["contributions"]["items"]
    required = set(item_schema["required"])
    allowed = set(item_schema["properties"])
    validated_rows: list[dict] = []
    for index, row in enumerate(rows):
        row_label = f"{label} contribution row {index + 1}"
        if not isinstance(row, dict):
            raise error_type(f"{row_label} must be an object")
        missing = sorted(required - set(row))
        if missing:
            raise error_type(
                f"{row_label} omitted required field(s): {', '.join(missing)}"
            )
        unexpected = sorted(set(row) - allowed)
        if unexpected:
            raise error_type(
                f"{row_label} included unexpected field(s): "
                + ", ".join(unexpected)
            )

        for field, definition in item_schema["properties"].items():
            if field not in row:
                continue
            value = row[field]
            if definition["type"] == "string":
                if not isinstance(value, str):
                    raise error_type(f"{row_label} field {field} must be a string")
                if field == "date":
                    try:
                        parsed_date = date.fromisoformat(value)
                    except ValueError as exc:
                        raise error_type(
                            f"{row_label} field date is not a valid ISO date"
                        ) from exc
                    if parsed_date.isoformat() != value:
                        raise error_type(
                            f"{row_label} field date must use YYYY-MM-DD"
                        )
                if "enum" in definition and value not in definition["enum"]:
                    raise error_type(
                        f"{row_label} field {field} is outside the allowed enum"
                    )
            elif definition["type"] == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise error_type(f"{row_label} field {field} must be numeric")
                if not math.isfinite(float(value)):
                    raise error_type(f"{row_label} field {field} must be finite")

        try:
            json.dumps(row, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise error_type(f"{row_label} was not valid finite JSON") from exc
        validated_rows.append(dict(row))
    return validated_rows


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all text from a PDF using PyMuPDF. Strips NUL bytes."""
    doc = fitz.open(str(pdf_path))
    try:
        parts = [page.get_text() for page in doc]
    finally:
        doc.close()
    return "\n".join(parts).replace("\x00", "").strip()


def _normalize_ocr_text(value: str) -> str:
    """Collapse OCR punctuation/spacing for deterministic header checks."""
    return "".join(character for character in value.casefold() if character.isalnum())


def _form497_ocr_dates(text: str) -> list[date]:
    dates: list[date] = []
    for month, day, year in re.findall(
        r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})(?!\d)",
        text,
    ):
        try:
            dates.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return dates


def _form497_ocr_amounts(text: str) -> set[Decimal]:
    """Read money-shaped OCR tokens without treating IDs/dates as dollars."""
    amounts: set[Decimal] = set()
    for token in re.findall(
        r"(?<![\d/])(?:\$\s*)?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?(?![\d/])",
        text,
    ):
        try:
            amounts.add(Decimal(token.replace("$", "").replace(",", "").strip()))
        except InvalidOperation:
            continue
    return amounts


def _validate_form497_local_ocr_text(text: str) -> None:
    """Require positive Part 1 evidence before any paid text extraction."""
    normalized = _normalize_ocr_text(text)
    missing = []
    if "497contributionreport" not in normalized:
        missing.append("Form 497 title")
    if "contributionsreceived" not in normalized:
        missing.append("Part 1 contributions-received heading")
    if len(_form497_ocr_dates(text)) < 2:
        missing.append("filing and contribution dates")
    if not _form497_ocr_amounts(text):
        missing.append("comma-formatted contribution amount")
    if missing:
        raise LocalOCRUnavailableError(
            "offline OCR did not prove a readable Form 497 Part 1 (missing "
            + ", ".join(missing)
            + "); filing remains pending"
        )


def extract_form497_text_with_local_ocr(pdf_path: Path) -> str:
    """OCR a small image-only Form 497 locally, without sending images away.

    RapidOCR and ONNX Runtime are optional runtime dependencies installed only
    for NetFile jobs. The source scan is rendered into a temporary directory,
    processed offline, and deleted before return. This route is deliberately
    limited to four pages and only accepts a positively identified Part 1
    report with transaction-shaped dates and money.
    """
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise LocalOCRUnavailableError(
            "offline OCR dependency is not installed; filing remains pending"
        ) from exc

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        raise LocalOCRUnavailableError(
            f"offline OCR could not open the source PDF ({type(exc).__name__}); "
            "filing remains pending"
        ) from exc
    try:
        page_count = len(doc)
        if page_count < 1:
            raise LocalOCRUnavailableError(
                "image-only Form 497 has no pages; filing remains pending"
            )
        if page_count > MAX_FORM497_LOCAL_OCR_PAGES:
            raise LocalOCRUnavailableError(
                f"image-only Form 497 has {page_count} pages; offline OCR is "
                f"bounded to {MAX_FORM497_LOCAL_OCR_PAGES}; filing remains pending"
            )

        engine = RapidOCR()
        page_text: list[str] = []
        accepted_characters = 0
        with tempfile.TemporaryDirectory(prefix="richmond-form497-ocr-") as temp_dir:
            temp_path = Path(temp_dir)
            for page_index, page in enumerate(doc):
                image_path = temp_path / f"page-{page_index + 1}.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                pixmap.save(str(image_path))
                result = engine(str(image_path))
                texts = tuple(getattr(result, "txts", ()) or ())
                scores = tuple(getattr(result, "scores", ()) or ())
                if len(texts) != len(scores):
                    raise LocalOCRUnavailableError(
                        "offline OCR returned mismatched text/confidence output; "
                        "filing remains pending"
                    )
                accepted = [
                    str(value).strip()
                    for value, score in zip(texts, scores)
                    if str(value).strip()
                    and isinstance(score, Real)
                    and not isinstance(score, bool)
                    and math.isfinite(float(score))
                    and float(score) >= MIN_FORM497_LOCAL_OCR_LINE_CONFIDENCE
                ]
                accepted_page = "\n".join(accepted)
                accepted_characters += len(accepted_page) + (2 if page_text else 0)
                if accepted_characters > MAX_FORM497_LOCAL_OCR_CHARS:
                    raise LocalOCRUnavailableError(
                        f"offline OCR exceeded {MAX_FORM497_LOCAL_OCR_CHARS} "
                        "accepted characters; filing remains pending"
                    )
                page_text.append(accepted_page)
    except LocalOCRUnavailableError:
        raise
    except Exception as exc:
        raise LocalOCRUnavailableError(
            f"offline OCR failed safely ({type(exc).__name__}); filing remains pending"
        ) from exc
    finally:
        doc.close()

    text = "\n\n".join(page_text).replace("\x00", "").strip()
    if len(text) > MAX_FORM497_LOCAL_OCR_CHARS:
        raise LocalOCRUnavailableError(
            f"offline OCR exceeded {MAX_FORM497_LOCAL_OCR_CHARS} characters; "
            "filing remains pending"
        )
    _validate_form497_local_ocr_text(text)
    return text


def validate_form497_local_ocr_rows(rows: list[dict], ocr_text: str) -> None:
    """Fail closed when DeepSeek returns values not present in local OCR."""
    if not rows:
        raise TextExtractionIncompleteError(
            "offline OCR proved contribution-shaped data but DeepSeek returned zero rows"
        )

    normalized_lines = tuple(
        normalized
        for line in ocr_text.splitlines()
        if (normalized := _normalize_ocr_text(line))
    )
    ocr_dates = _form497_ocr_dates(ocr_text)
    ocr_amounts = _form497_ocr_amounts(ocr_text)
    for index, row in enumerate(rows, start=1):
        normalized_name = _normalize_ocr_text(str(row.get("contributor_name") or ""))
        if len(normalized_name) < 4 or not any(
            normalized_name in line for line in normalized_lines
        ):
            raise TextExtractionIncompleteError(
                f"local-OCR contribution row {index} name is not present in source OCR"
            )
        try:
            row_date = date.fromisoformat(str(row.get("date") or ""))
        except ValueError as exc:
            raise TextExtractionIncompleteError(
                f"local-OCR contribution row {index} date is invalid"
            ) from exc
        if row_date not in ocr_dates:
            raise TextExtractionIncompleteError(
                f"local-OCR contribution row {index} date is not present in source OCR"
            )
        try:
            row_amount = Decimal(str(row.get("amount")))
        except InvalidOperation as exc:
            raise TextExtractionIncompleteError(
                f"local-OCR contribution row {index} amount is invalid"
            ) from exc
        if row_amount not in ocr_amounts:
            raise TextExtractionIncompleteError(
                f"local-OCR contribution row {index} amount is not present in source OCR"
            )


def parse_filing_with_claude(
    pdf_text: str,
    form_type: str,
    filing_id: str,
    committee: str,
    client: LLMClient,
) -> list[dict]:
    """Parse a paper filing's text into structured contribution dicts.

    The legacy function name is retained for call-site compatibility. It now
    uses DeepSeek V4 Pro tool calling with temperature=0 for reproducibility.
    Returns [] if no contributions found (e.g., Form 410, or 497 Part 2
    naming a different recipient).
    """
    system = (
        "You extract itemized monetary contributions from California FPPC "
        "campaign finance forms. You are conservative and precise: only "
        "include rows you can see clearly in the input. Skip non-monetary "
        "contributions, loans, and refunds. If a column is blank, leave the "
        "corresponding field as an empty string. Dates must be YYYY-MM-DD. "
        "Amounts must be in dollars (e.g., 250.00 not 25000)."
    )
    user = (
        f"Filing ID: {filing_id}\n"
        f"Committee: {committee}\n"
        f"Form type: {form_type}\n\n"
        f"PDF TEXT:\n{pdf_text}"
    )

    tool_def = {
        "name": "save_contributions",
        "description": "Save the extracted itemized contribution rows.",
        "input_schema": CONTRIBUTION_SCHEMA,
    }

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        temperature=0,
        system=system,
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "save_contributions"},
        messages=[{"role": "user", "content": user}],
    )

    rows = _validate_contribution_response(
        response,
        TextExtractionIncompleteError,
        "text",
    )
    for row in rows:
        row["filing_id"] = filing_id
        row.setdefault("entity_code", "IND")
        row.setdefault("city", "")
        row.setdefault("state", "")
        row.setdefault("zip", "")
        row.setdefault("occupation", "")
        row.setdefault("contributor_employer", "")
    return rows


def parse_filing_with_vision(
    pdf_path: Path,
    form_type: str,
    filing_id: str,
    committee: str,
    client: LLMClient,
) -> list[dict]:
    """Kimi vision fallback for source PDFs that have no extractable text.

    The source PDF is rendered locally to bounded PNG page images; raw PDF
    bytes are never passed through an incompatible Anthropic document block.
    The optional vision credential is separate from the default DeepSeek key.
    """
    route = get_model_route(VISION_MODEL)
    if not route.supports_vision:
        raise ValueError(f"Configured model {route.model!r} does not support vision")
    if not os.environ.get(route.api_key_env):
        raise OptionalVisionUnavailableError(
            f"{route.api_key_env} is not set; image-only filing remains pending"
        )

    # The caller's client is normally pinned to DeepSeek by its explicit key.
    # Resolve a fresh provider-aware client for the Kimi vision route.
    del client
    vision_client = LLMClient()
    image_blocks = _render_pdf_path_image_blocks(pdf_path)
    tool_def = {
        "name": "save_contributions",
        "description": "Save the extracted itemized contribution rows.",
        "input_schema": CONTRIBUTION_SCHEMA,
    }
    prompt = (
        "Read the attached California FPPC filing page images. Extract only "
        "itemized monetary contributions received by the named committee; "
        "skip loans, refunds, non-monetary rows, and Form 497 Part 2 payments "
        "made to other committees. Dates must be YYYY-MM-DD and amounts must "
        f"be dollars. Filing ID: {filing_id}. Committee: {committee}. "
        f"Form type: {form_type}."
    )
    response = vision_client.messages.create(
        model=VISION_MODEL,
        max_tokens=16000,
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "save_contributions"},
        messages=[{
            "role": "user",
            "content": [{"type": "text", "text": prompt}, *image_blocks],
        }],
        thinking={"type": "disabled"},
    )
    rows = _validate_contribution_response(
        response,
        VisionExtractionIncompleteError,
        "vision",
    )
    for row in rows:
        row["filing_id"] = filing_id
        row.setdefault("entity_code", "IND")
        row.setdefault("city", "")
        row.setdefault("state", "")
        row.setdefault("zip", "")
        row.setdefault("occupation", "")
        row.setdefault("contributor_employer", "")
    return rows


def _render_pdf_path_image_blocks(
    pdf_path: Path,
    *,
    max_pages: int = MAX_VISION_PAGES,
    reject_oversized: bool = True,
) -> list[dict]:
    """Render a bounded source-page prefix as image blocks.

    Full contribution extraction rejects oversized filings because silently
    omitting later schedules would create false completeness. Form 460 summary
    extraction needs only the cover/Summary/Schedule-A opening pages, so it may
    intentionally send a small prefix through the separately billed vision
    route.
    """
    doc = fitz.open(str(pdf_path))
    try:
        if reject_oversized and len(doc) > max_pages:
            raise ValueError(
                f"Filing has {len(doc)} pages; refusing to send more than "
                f"{max_pages} pages to the paid vision route"
            )
        matrix = fitz.Matrix(2, 2)
        blocks: list[dict] = []
        for page_number in range(min(len(doc), max_pages)):
            page = doc[page_number]
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}"},
            })
        return blocks
    finally:
        doc.close()


# JSON schema for the Form 460 cover-page summary. We capture the
# canonical Line 1-5 structure plus reporting period and the unitemized
# breakdown from Schedule A. The cover page is the candidate's own
# legal certification of what they raised — it's authoritative ground
# truth for cycle-to-date totals, and the unitemized number lets us
# synthesize a single aggregate row at load time so DB totals match
# the form total exactly.
FORM460_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "period_start": {"type": "string", "description": "YYYY-MM-DD"},
        "period_end":   {"type": "string", "description": "YYYY-MM-DD"},
        "monetary_this_period":     {"type": "number", "description": "Line 1 column A"},
        "monetary_cycle_to_date":   {"type": "number", "description": "Line 1 column B (calendar year-to-date / cumulative)"},
        "loans_this_period":        {"type": "number"},
        "loans_cycle_to_date":      {"type": "number"},
        "nonmonetary_this_period":  {"type": "number"},
        "nonmonetary_cycle_to_date":{"type": "number"},
        "total_this_period":        {"type": "number", "description": "Line 5 column A — total contributions received this period"},
        "total_cycle_to_date":      {"type": "number", "description": "Line 5 column B — cumulative total (the candidate's own legal claim of what they raised)"},
        "itemized_this_period":     {"type": "number", "description": "Schedule A Line 1 itemized monetary contributions this period, including negative corrections; Line 1 + Line 2 must equal monetary_this_period"},
        "unitemized_this_period":   {"type": "number", "description": "Schedule A small donations below $100, summed; itemized + unitemized must equal monetary_this_period"},
    },
    "required": [
        "period_start", "period_end",
        "monetary_this_period", "monetary_cycle_to_date",
        "total_this_period", "total_cycle_to_date",
        "itemized_this_period", "unitemized_this_period",
    ],
    "additionalProperties": False,
}


def _validate_form460_summary_response(response) -> dict:
    """Validate the complete routed response contract without inference."""
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "max_tokens":
        raise Form460SummaryIncompleteError(
            "Form 460 summary response reached max_tokens"
        )
    if stop_reason != "tool_use":
        raise Form460SummaryIncompleteError(
            "Form 460 summary response did not stop on the required tool "
            f"(stop_reason={stop_reason!r})"
        )

    content = getattr(response, "content", None)
    if not isinstance(content, list):
        raise Form460SummaryIncompleteError(
            "Form 460 summary response content must be a list"
        )

    tool_blocks = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            if str(getattr(block, "text", "") or "").strip():
                raise Form460SummaryIncompleteError(
                    "Form 460 summary returned text instead of only the "
                    "required structured tool result"
                )
            continue
        if block_type != "tool_use":
            raise Form460SummaryIncompleteError(
                f"Form 460 summary returned unsupported block type {block_type!r}"
            )
        tool_blocks.append(block)

    if len(tool_blocks) != 1:
        raise Form460SummaryIncompleteError(
            "Form 460 summary must contain exactly one tool result"
        )
    tool_block = tool_blocks[0]
    if getattr(tool_block, "name", None) != "save_form460_summary":
        raise Form460SummaryIncompleteError(
            "Form 460 summary used the wrong tool"
        )

    tool_input = getattr(tool_block, "input", None)
    if not isinstance(tool_input, dict):
        raise Form460SummaryIncompleteError(
            "Form 460 summary tool input was not a JSON object"
        )
    if "_raw" in tool_input:
        raise Form460SummaryIncompleteError(
            "Form 460 summary tool arguments were not valid JSON"
        )

    required = set(FORM460_SUMMARY_SCHEMA["required"])
    allowed = set(FORM460_SUMMARY_SCHEMA["properties"])
    missing = sorted(required - set(tool_input))
    if missing:
        raise Form460SummaryIncompleteError(
            "Form 460 summary omitted required field(s): " + ", ".join(missing)
        )
    unexpected = sorted(set(tool_input) - allowed)
    if unexpected:
        raise Form460SummaryIncompleteError(
            "Form 460 summary included unexpected field(s): "
            + ", ".join(unexpected)
        )

    currency_quantum = Decimal("0.01")
    currency_values: dict[str, Decimal] = {}
    for field, definition in FORM460_SUMMARY_SCHEMA["properties"].items():
        if field not in tool_input:
            continue
        value = tool_input[field]
        expected_type = definition["type"]
        if expected_type == "string":
            if not isinstance(value, str):
                raise Form460SummaryIncompleteError(
                    f"Form 460 summary field {field} must be a string"
                )
            if field in {"period_start", "period_end"} and not value:
                raise Form460SummaryIncompleteError(
                    f"Form 460 summary {field} must not be empty"
                )
            if value:
                try:
                    parsed_date = date.fromisoformat(value)
                except ValueError as exc:
                    raise Form460SummaryIncompleteError(
                        f"Form 460 summary field {field} is not a valid ISO date"
                    ) from exc
                if parsed_date.isoformat() != value:
                    raise Form460SummaryIncompleteError(
                        f"Form 460 summary field {field} must use YYYY-MM-DD"
                    )
        elif expected_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise Form460SummaryIncompleteError(
                    f"Form 460 summary field {field} must be numeric"
                )
            if not math.isfinite(float(value)):
                raise Form460SummaryIncompleteError(
                    f"Form 460 summary field {field} must be finite"
                )
            try:
                amount = Decimal(str(value))
                cent_amount = amount.quantize(currency_quantum)
            except InvalidOperation as exc:
                raise Form460SummaryIncompleteError(
                    f"Form 460 summary field {field} must use cent precision"
                ) from exc
            if amount != cent_amount:
                raise Form460SummaryIncompleteError(
                    f"Form 460 summary field {field} must use cent precision"
                )
            currency_values[field] = cent_amount

    if date.fromisoformat(tool_input["period_start"]) > date.fromisoformat(
        tool_input["period_end"]
    ):
        raise Form460SummaryIncompleteError(
            "Form 460 summary period_start must not be after period_end"
        )

    arithmetic_checks = (
        (
            "Schedule A itemized + unitemized = monetary this period",
            ("itemized_this_period", "unitemized_this_period"),
            "monetary_this_period",
        ),
        (
            "Line 5 this period = monetary + loans + nonmonetary",
            (
                "monetary_this_period",
                "loans_this_period",
                "nonmonetary_this_period",
            ),
            "total_this_period",
        ),
        (
            "Line 5 cycle to date = monetary + loans + nonmonetary",
            (
                "monetary_cycle_to_date",
                "loans_cycle_to_date",
                "nonmonetary_cycle_to_date",
            ),
            "total_cycle_to_date",
        ),
    )
    zero = Decimal("0.00")
    for label, component_fields, printed_total_field in arithmetic_checks:
        components = sum(
            (currency_values.get(field, zero) for field in component_fields),
            zero,
        )
        printed_total = currency_values[printed_total_field]
        if components != printed_total:
            raise Form460SummaryIncompleteError(
                f"Form 460 summary arithmetic mismatch: {label} "
                f"({components:.2f} != {printed_total:.2f})"
            )

    try:
        json.dumps(tool_input, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise Form460SummaryIncompleteError(
            "Form 460 summary tool input was not valid finite JSON"
        ) from exc
    return dict(tool_input)


def parse_form460_summary_with_vision(
    pdf_path: Path,
    filing_id: str,
    committee: str,
    client: LLMClient,
) -> dict | None:
    """Read the Form 460 cover-page Summary + Schedule A Summary block.

    The cover page reports Lines 1-5 (monetary, loans, nonmonetary, totals)
    in two columns: A (this period) and B (calendar year-to-date / cumulative
    cycle). Schedule A Summary breaks Line 1 into itemized vs unitemized.

    These numbers ARE the candidate's own legal certification — they're
    canonical ground truth for "how much did they raise". Our extracted
    itemized rows alone can never match Line 1 column B because of
    unitemized small-donor contributions, which the loader synthesizes
    as an aggregate row using ``unitemized_this_period`` from this output.

    Uses PyMuPDF text extraction + DeepSeek when text is available. Image-only
    filings use a bounded six-page vision prefix through the same routed budget
    rails. The image route is explicit and narrow: benchmarked GPT-5.6 Luna
    first, then the existing direct Kimi route when its separate credential is
    configured. Luna gets at most one correction pass when deterministic form
    arithmetic rejects the first scan; all other failures remain retryable on
    the next run. Missing vision credentials and any truncated, ambiguous, or
    schema-invalid response leave the filing explicitly retryable.

    Returns a dict matching FORM460_SUMMARY_SCHEMA on success.
    """
    filing_id = str(filing_id)
    cached = _FORM460_SUMMARY_RUN_CACHE.get(filing_id)
    if cached:
        return dict(cached["summary"])
    if filing_id in _FORM460_SUMMARY_RUN_ATTEMPTS:
        raise Form460SummaryIncompleteError(
            f"Form 460 summary for filing {filing_id} was already attempted "
            "in this run"
        )

    pdf_text = extract_text_from_pdf(pdf_path)

    system = (
        "You read California FPPC Form 460 SUMMARY pages — the cover page "
        "with Lines 1-5 (monetary, loans, nonmonetary, totals in column A "
        "this-period and column B cumulative) AND the Schedule A summary "
        "block which breaks Line 1 into itemized (>=$100) vs unitemized "
        "(<$100). Return the exact dollar amounts. If a cell is blank or "
        "shown as a dash, return 0.0. Dates as YYYY-MM-DD. You do NOT "
        "extract individual contribution rows — those are separately "
        "extracted by the contributions parser. Just the summary numbers. "
        "Before saving, verify Schedule A Line 1 itemized (including any "
        "negative corrections) plus Line 2 unitemized equals "
        "monetary_this_period, and verify Line 5 equals monetary plus loans "
        "plus nonmonetary in each column. On Schedule A, identify all three "
        "amounts (itemized, unitemized, and total) and assign them by the "
        "identity itemized + unitemized = total = monetary_this_period. Some "
        "scanned filings have values visually shifted among Schedule A lines. "
        "When that happens, use the unique arithmetic solution among the "
        "displayed amounts; do not trust the nearest line position or call "
        "the tool with values that fail the identity. If an apparent itemized "
        "amount equals monetary_this_period while unitemized is positive, it "
        "is the Schedule A total, not itemized."
    )

    tool_def = {
        "name": "save_form460_summary",
        "description": "Save the Form 460 cover-page Summary + Schedule A Summary numbers.",
        "input_schema": FORM460_SUMMARY_SCHEMA,
    }
    instruction = (
        f"Filing ID: {filing_id}\n"
        f"Committee: {committee}\n\n"
        "Read the Form 460 SUMMARY page (Lines 1-5 in two columns) AND "
        "the Schedule A summary (which breaks Line 1 into itemized vs "
        "unitemized). Return all values via the save_form460_summary tool."
    )

    _FORM460_SUMMARY_RUN_ATTEMPTS.add(filing_id)
    try:
        summary_vision_model: str | None = None
        request_kwargs = {
            "max_tokens": 2000,
            "system": system,
            "tools": [tool_def],
            "tool_choice": {"type": "tool", "name": "save_form460_summary"},
        }
        if pdf_text:
            request_client = client
            request_kwargs.update({
                "model": MODEL,
                "temperature": 0,
                "messages": [{
                    "role": "user",
                    "content": f"{instruction}\n\nPDF TEXT:\n{pdf_text}",
                }],
            })
        else:
            summary_vision_model = _select_form460_summary_vision_model()
            request_client = LLMClient()
            image_blocks = _render_pdf_path_image_blocks(
                pdf_path,
                max_pages=MAX_SUMMARY_VISION_PAGES,
                reject_oversized=False,
            )
            if summary_vision_model == OPENAI_LUNA_MODEL:
                for block in image_blocks:
                    block["image_url"]["detail"] = "original"
            request_kwargs.update({
                "model": summary_vision_model,
                "thinking": {"type": "disabled"},
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        *image_blocks,
                    ],
                }],
            })
        response = request_client.messages.create(**request_kwargs)
        try:
            summary = _validate_form460_summary_response(response)
        except Form460SummaryIncompleteError as first_error:
            if (
                summary_vision_model != OPENAI_LUNA_MODEL
                or "arithmetic mismatch" not in str(first_error)
                or MAX_LUNA_SUMMARY_ATTEMPTS < 2
            ):
                raise

            retry_kwargs = dict(request_kwargs)
            original_message = request_kwargs["messages"][0]
            original_content = original_message["content"]
            retry_content = [dict(block) for block in original_content]
            retry_content[0] = {
                "type": "text",
                "text": (
                    f"{instruction}\n\n"
                    "CORRECTION PASS: deterministic validation rejected the "
                    f"prior scan: {first_error}. Re-read every Schedule A "
                    "summary and attached spreadsheet page. Identify all "
                    "displayed amounts, then solve the unique identity "
                    "itemized + unitemized = monetary_this_period before "
                    "calling the tool. Do not repeat the rejected mapping."
                ),
            }
            retry_kwargs["messages"] = [{
                **original_message,
                "content": retry_content,
            }]
            retry_response = request_client.messages.create(**retry_kwargs)
            summary = _validate_form460_summary_response(retry_response)
    except Exception as exc:
        record_form460_summary_run_failure(filing_id, str(exc))
        raise

    _FORM460_SUMMARY_RUN_CACHE[filing_id] = {
        "committee": str(committee),
        "summary": dict(summary),
    }
    _FORM460_SUMMARY_RUN_FAILURES.pop(filing_id, None)
    return summary


def filing_already_extracted(json_data: dict, filing_id: str) -> bool:
    """Idempotency check: True if filing_id is already in the JSON's filings list."""
    for f in json_data.get("filings", []):
        if str(f.get("filing_id")) == str(filing_id):
            return True
    return False


def db_filing_ids_extracted(
    filing_ids: list[str] | set[str],
    city_fips: str = DEFAULT_FIPS,
) -> set[str]:
    """Return filing IDs with a durable terminal DB outcome for this city.

    This is the second-tier idempotency check (after the per-committee
    JSON cache). It survives CI runner replacement: src/data/paper_filings/
    JSONs are git-committed, but updates from CI runs are discarded with
    the runner unless explicitly committed back. Non-zero results persist in
    contributions; valid zero results persist in paper_filing_zero_results.

    Rollout-safe soft fail: if the receipt table is not deployed yet, IDs
    already found in contributions are preserved. Other DB errors fall back
    to the JSON cache. Never raises because extraction is best-effort.
    """
    if not filing_ids:
        return set()
    try:
        from db import get_connection
    except Exception:
        return set()
    try:
        conn = get_connection()
    except Exception:
        return set()
    try:
        ids = [str(fid) for fid in filing_ids if fid]
        if not ids:
            return set()
        extracted: set[str] = set()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT DISTINCT filing_id
                   FROM contributions
                   WHERE city_fips = %s
                     AND filing_id = ANY(%s)
                """,
                (city_fips, ids),
            )
            extracted.update(str(row[0]) for row in cur.fetchall() if row[0])

            # Query separately rather than UNIONing so a code-before-migration
            # deploy does not discard contribution IDs already fetched.
            try:
                cur.execute(
                    """SELECT filing_id
                       FROM paper_filing_zero_results
                       WHERE city_fips = %s
                         AND filing_id = ANY(%s)
                    """,
                    (city_fips, ids),
                )
                extracted.update(
                    str(row[0]) for row in cur.fetchall() if row[0]
                )
            except Exception as exc:
                print(
                    "  paper-extractor: zero-result receipt lookup unavailable "
                    f"({exc}) - using contributions-only idempotency"
                )
                try:
                    conn.rollback()
                except Exception:
                    pass
            return extracted
    except Exception as exc:
        print(f"  paper-extractor: DB idempotency check failed ({exc}) — falling back to JSON-only cache")
        return set()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def persist_paper_filing_zero_result(
    *,
    filing_id: str,
    committee: str,
    form_type: str,
    result_kind: str,
    extraction_method: str,
    extraction_model: str,
    source_url: str,
    city_fips: str = DEFAULT_FIPS,
) -> bool:
    """Persist one completed zero-row outcome; soft-fail on DB errors.

    A receipt is written only after an explicit, structurally valid empty
    tool result (or deterministic Form 410 classification) and after the
    runner-local JSON artifact has been written. Returning False is safe: the
    next CI run may pay to retry, but no source is incorrectly suppressed.
    """
    try:
        from db import get_connection

        conn = get_connection()
    except Exception as exc:
        print(f"  paper-extractor: zero-result receipt DB unavailable ({exc})")
        return False

    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO paper_filing_zero_results
                       (city_fips, filing_id, committee, form_type,
                        result_kind, extraction_method, extraction_model,
                        source_url, source_tier, confidence_score)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 1.00)
                   ON CONFLICT (city_fips, filing_id) DO NOTHING
                """,
                (
                    city_fips,
                    filing_id,
                    committee,
                    form_type,
                    result_kind,
                    extraction_method,
                    extraction_model,
                    source_url,
                ),
            )
        conn.commit()
        return True
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"  paper-extractor: zero-result receipt write failed ({exc})")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _paper_filing_source_url(filing: dict, filing_id: str) -> str:
    """Return the source-closest direct NetFile document URL."""
    return (
        str(filing.get("document_url") or "").strip()
        or f"{API_BASE}/public/image/{filing_id}"
    )


def find_committee_json(committee: str) -> Path | None:
    """Locate the existing JSON for this committee, if any."""
    needle = committee.lower().strip()
    for p in PAPER_FILINGS_DIR.glob("*.json"):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if (data.get("committee", "").lower().strip()) == needle:
            return p
    return None


def slugify(name: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")
    while "__" in out:
        out = out.replace("__", "_")
    return out


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def classify_form(form_type_text: str) -> str:
    """Map an RSS form_type string ('Form 460 - Pre-Election Statement') to '460'/'497'/'410'/'other'."""
    s = (form_type_text or "").lower()
    if "460" in s:
        return "460"
    if "497" in s:
        return "497"
    if "410" in s:
        return "410"
    return "other"


def extract_committee(
    committee: str,
    filings: list[dict],
    client: LLMClient,
    dry_run: bool = False,
    only_filing_id: str | None = None,
    db_extracted_filing_ids: set[str] | None = None,
) -> dict:
    """Extract all unprocessed filings for one committee.

    `db_extracted_filing_ids`: optional set of filing_ids with a durable DB
    outcome (a contribution row or terminal-zero receipt). When provided,
    any filing in that set is treated as already-extracted (recorded in
    `data["filings"]` so future syncs short-circuit on the JSON cache, but
    no LLM API call is made). This
    is the cross-CI-run idempotency layer — the JSON cache lives in the
    runner filesystem and is discarded between runs unless committed back
    to git, so without this DB-side check, every successful netfile sync
    re-OCRs every paper filing on the RSS feed. See sync_netfile and the
    May 8 cost spike for the failure mode this prevents.

    Returns the updated JSON dict (whether or not it was written to disk).
    """
    db_extracted_filing_ids = db_extracted_filing_ids or set()
    json_path = find_committee_json(committee)
    if json_path:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        json_path = PAPER_FILINGS_DIR / f"{slugify(committee)}.json"
        data = {
            "committee": committee,
            "fppc_id": "",
            "candidate_name": "",
            "office_sought": "",
            "city_fips": DEFAULT_FIPS,
            "source": "fppc_paper",
            "filings": [],
            "contributions": [],
        }

    new_filings = 0
    new_contribs = 0
    pending_zero_results: list[dict] = []
    pending_form460_summaries: list[tuple[str, str, dict]] = []
    for filing in filings:
        filing_id = str(filing.get("filing_id", ""))
        if not filing_id:
            continue
        if only_filing_id and filing_id != only_filing_id:
            continue
        if filing_already_extracted(data, filing_id):
            continue

        form = classify_form(filing.get("form_type", ""))
        if form not in EXTRACTABLE_FORMS and form != "410":
            print(f"  [skip] {committee} filing {filing_id}: unknown form ({filing.get('form_type')!r})")
            continue

        # Cross-CI-run idempotency: contribution rows cover non-zero results;
        # paper_filing_zero_results covers terminal valid-zero outcomes.
        if filing_id in db_extracted_filing_ids:
            print(f"  [db-skip] {committee} filing {filing_id} ({form}): durable DB outcome exists")
            data["filings"].append({
                "filing_id": filing_id,
                "form": form,
                "date": str(date.today()),
                "source": "db_idempotency",
            })
            new_filings += 1
            continue

        print(f"  [download] {committee} filing {filing_id} (form {form})")
        try:
            pdf_path = download_paper_filing(filing_id, output_dir=PDF_CACHE_DIR)
        except Exception as exc:
            print(f"    download failed: {exc}")
            continue

        filing_entry = {"filing_id": filing_id, "form": form, "date": str(date.today())}

        if form == "410":
            data["filings"].append(filing_entry)
            new_filings += 1
            pending_zero_results.append({
                "filing_id": filing_id,
                "committee": committee,
                "form_type": form,
                "result_kind": "not_contribution_form",
                "extraction_method": "rss_classification",
                "extraction_model": "deterministic",
                "source_url": _paper_filing_source_url(filing, filing_id),
                "city_fips": str(data.get("city_fips") or DEFAULT_FIPS),
            })
            continue

        try:
            text = extract_text_from_pdf(pdf_path)
        except Exception as exc:
            print(f"    PDF text extraction failed: {exc}")
            text = ""

        text_source = "pdf_text" if text else ""
        local_ocr_text = ""
        if not text and form == "497":
            print("    PDF text empty (Type3/image fonts) - trying bounded local OCR")
            try:
                text = extract_form497_text_with_local_ocr(pdf_path)
                local_ocr_text = text
                text_source = "local_ocr"
                print("    local OCR produced a validated Form 497 Part 1 transcript")
            except LocalOCRUnavailableError as exc:
                print(f"    local OCR unavailable: {exc}")

        if text:
            try:
                rows = parse_filing_with_claude(
                    text, form, filing_id, committee, client
                )
                if text_source == "local_ocr":
                    validate_form497_local_ocr_rows(rows, text)
            except Exception as exc:
                if text_source != "local_ocr":
                    print(f"    text extraction failed; filing remains pending: {exc}")
                    continue
                print(
                    "    local-OCR DeepSeek extraction failed safely; "
                    f"trying optional Kimi vision: {exc}"
                )
                text = ""
            else:
                extraction_method = (
                    "local_ocr_text_llm" if text_source == "local_ocr" else "text_llm"
                )
                extraction_model = MODEL
                print(
                    f"    extracted {len(rows)} contribution row(s) "
                    f"[{text_source}]"
                )

        if not text:
            print("    trying optional Kimi vision")
            try:
                rows = parse_filing_with_vision(
                    pdf_path, form, filing_id, committee, client
                )
                if local_ocr_text:
                    # A positive Part 1 OCR transcript must never become a
                    # terminal zero or ungrounded result merely because the
                    # separately configured legacy vision fallback ran.
                    validate_form497_local_ocr_rows(rows, local_ocr_text)
            except OptionalVisionUnavailableError as exc:
                # Do not append filing_entry: doing so would permanently mark
                # the source PDF processed even though no extraction occurred.
                print(f"    vision unavailable: {exc}")
                continue
            except Exception as exc:
                print(f"    vision extraction failed; filing remains pending: {exc}")
                continue
            extraction_method = "vision_llm"
            extraction_model = VISION_MODEL
            print(f"    extracted {len(rows)} contribution row(s) [vision]")

        # Form 460 cover-page summary — the candidate's own legal claim of
        # what they raised this period and cycle-to-date. Stored in the
        # filing entry so the loader can synthesize an unitemized aggregate
        # row at load time, making DB cycle totals match the form exactly.
        # Only 460s have a meaningful summary (497s are single-row reports).
        if form == "460":
            try:
                summary = parse_form460_summary_with_vision(
                    pdf_path, filing_id, committee, client
                )
                if summary:
                    filing_entry["form_summary"] = summary
                    pending_form460_summaries.append(
                        (filing_id, committee, dict(summary))
                    )
                    print(
                        f"    form summary: this_period=${summary.get('total_this_period', 0):,.2f}, "
                        f"cycle=${summary.get('total_cycle_to_date', 0):,.2f}, "
                        f"unitemized=${summary.get('unitemized_this_period', 0):,.2f}"
                    )
            except Exception as exc:
                # Non-fatal — itemized rows still load without the summary.
                print(f"    form-460 summary extraction failed: {exc}")

        data["filings"].append(filing_entry)
        data["contributions"].extend(rows)
        new_filings += 1
        new_contribs += len(rows)
        if not rows:
            pending_zero_results.append({
                "filing_id": filing_id,
                "committee": committee,
                "form_type": form,
                "result_kind": "extractor_returned_zero",
                "extraction_method": extraction_method,
                "extraction_model": extraction_model,
                "source_url": _paper_filing_source_url(filing, filing_id),
                "city_fips": str(data.get("city_fips") or DEFAULT_FIPS),
            })

    print(f"  [{committee}] +{new_filings} filing(s), +{new_contribs} contribution(s)")

    if not dry_run and (new_filings or new_contribs):
        write_json_atomic(json_path, data)
        print(f"  wrote {json_path}")
        # The committee artifact is now safe. Persist newly extracted cover
        # summaries to the canonical reconciliation cache; if that write is
        # unavailable, the run-local registry still carries the exact result
        # into the downstream reconciliation phase without a second paid call.
        if pending_form460_summaries:
            from load_paper_filings import persist_form460_summary

            for filing_id, filing_committee, form_summary in pending_form460_summaries:
                persist_form460_summary(
                    filing_id=filing_id,
                    committee=filing_committee,
                    summary=form_summary,
                )
        # Persist only after the local artifact succeeds. For zero results
        # there are no contribution rows awaiting the downstream loader, so
        # this receipt cannot suppress an uncommitted non-zero payload.
        for receipt in pending_zero_results:
            persist_paper_filing_zero_result(**receipt)

    return data


def discover_paper_filers(
    transactions: list[dict] | None = None,
) -> dict[str, list[dict]]:
    """Return {committee_name: [filing_dict, ...]} for every paper filer in the RSS feed.

    Builds the API committee list from the monetary-contributions transaction
    feed (type 0). Any committee that appears in the RSS filing feed but not
    in the API transaction feed is a paper filer whose contribution data is
    only available via downloaded PDFs.

    *transactions* lets a caller (e.g., sync_netfile) reuse a transaction set
    it already fetched, avoiding a duplicate ~18-minute API pull.
    """
    rss = fetch_filing_rss()
    if transactions is None:
        transactions = fetch_all_transactions(transaction_type=0)
    api_committees = extract_filers(transactions)
    filers = identify_paper_filers(rss, api_committees)
    return {f["committee"]: f["filings"] for f in filers}


def _read_committee_extraction_state(committee: str) -> dict:
    """Read the committee artifact used by the idempotency check."""
    path = find_committee_json(committee)
    if not path:
        return {"filings": [], "contributions": []}
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {"filings": [], "contributions": []}


def _pending_paper_filing_ids(
    filings: list[dict],
    extraction_state: dict,
    db_extracted_filing_ids: set[str],
) -> set[str]:
    """Return eligible filings without an artifact or durable DB outcome."""
    pending: set[str] = set()
    for filing in filings:
        filing_id = str(filing.get("filing_id") or "").strip()
        if not filing_id:
            continue
        form = classify_form(filing.get("form_type", ""))
        if form not in EXTRACTABLE_FORMS and form != "410":
            continue
        if filing_id in db_extracted_filing_ids:
            continue
        if filing_already_extracted(extraction_state, filing_id):
            continue
        pending.add(filing_id)
    return pending


def _finalize_paper_extraction_summary(
    summary: dict,
    *,
    pending_ids: set[str],
    reasons: list[str] | None = None,
    unknown_incomplete_count: int = 0,
) -> dict:
    """Attach the shared retryable-incomplete result contract."""
    incomplete_reasons = list(reasons or [])
    if pending_ids:
        incomplete_reasons.insert(
            0,
            f"{len(pending_ids)} eligible paper filing(s) remain pending",
        )
    summary.update({
        "paper_pending_count": len(pending_ids),
        "paper_pending_filing_ids": sorted(pending_ids)[:50],
        "retryable_incomplete": bool(pending_ids or unknown_incomplete_count),
        "incomplete_count": len(pending_ids) + unknown_incomplete_count,
        "incomplete_reasons": incomplete_reasons[:10],
    })
    return summary


def auto_extract_paper_filings(
    transactions: list[dict] | None = None,
    dry_run: bool = False,
) -> dict:
    """Refresh every paper filer's JSON from the latest PDFs.

    Designed to be called from sync_netfile. Missing API keys, network
    errors, and per-committee parse failures are logged rather than raised.
    The return value explicitly reports unresolved work so a durable
    change-event can retry while scheduled/manual syncs remain best-effort.

    Returns extraction counters plus the shared retryable-incomplete fields.
    """
    summary = {
        "committees_seen": 0,
        "committees_extracted": 0,
        "filings_added": 0,
        "contributions_added": 0,
    }
    reset_form460_summary_run_state()

    try:
        by_committee = discover_paper_filers(transactions=transactions)
    except Exception as exc:
        print(f"  paper-extractor: discovery failed ({exc}) — continuing with cached JSONs")
        return _finalize_paper_extraction_summary(
            summary,
            pending_ids=set(),
            reasons=[f"paper filing discovery failed: {exc}"],
            unknown_incomplete_count=1,
        )

    summary["committees_seen"] = len(by_committee)
    if not by_committee:
        return _finalize_paper_extraction_summary(summary, pending_ids=set())

    # One DB connection for ALL filing_ids across ALL committees discovered
    # in the RSS feed. Two indexed SELECTs cover contribution rows and valid
    # zero-result receipts; both are cheap beside redundant paid extraction.
    all_filing_ids = {
        str(f.get("filing_id"))
        for filings in by_committee.values()
        for f in filings
        if f.get("filing_id")
    }
    db_extracted = db_filing_ids_extracted(all_filing_ids)
    if db_extracted:
        print(f"  paper-extractor: {len(db_extracted)} of {len(all_filing_ids)} filings already in DB — skipping OCR")
    summary["filings_db_skipped"] = len(db_extracted)

    initial_state = {
        committee: _read_committee_extraction_state(committee)
        for committee in by_committee
    }
    initially_pending: set[str] = set()
    for committee, filings in by_committee.items():
        initially_pending.update(
            _pending_paper_filing_ids(
                filings,
                initial_state[committee],
                db_extracted,
            )
        )

    if not initially_pending:
        return _finalize_paper_extraction_summary(summary, pending_ids=set())

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("  paper-extractor: DEEPSEEK_API_KEY not set — skipping PDF extraction")
        reasons = (
            ["DEEPSEEK_API_KEY is unavailable for pending paper filings"]
            if initially_pending
            else []
        )
        return _finalize_paper_extraction_summary(
            summary,
            pending_ids=initially_pending,
            reasons=reasons,
        )

    try:
        client = LLMClient(api_key=api_key)
    except Exception as exc:
        print(f"  paper-extractor: LLM client unavailable ({exc}) — using cached JSONs")
        return _finalize_paper_extraction_summary(
            summary,
            pending_ids=initially_pending,
            reasons=[f"paper filing LLM client unavailable: {exc}"],
            unknown_incomplete_count=0 if initially_pending else 1,
        )

    pending_ids: set[str] = set()
    committee_errors: list[str] = []
    unknown_error_count = 0
    for committee, filings in by_committee.items():
        before_state = initial_state[committee]
        committee_failed = False
        try:
            updated_state = extract_committee(
                committee, filings, client=client, dry_run=dry_run,
                db_extracted_filing_ids=db_extracted,
            )
            before_filing_ids = {
                str(filing.get("filing_id"))
                for filing in before_state.get("filings", [])
                if filing.get("filing_id")
            }
            after_filing_ids = {
                str(filing.get("filing_id"))
                for filing in updated_state.get("filings", [])
                if filing.get("filing_id")
            }
            filings_added = len(after_filing_ids - before_filing_ids)
            added_contribs = max(
                0,
                len(updated_state.get("contributions", []))
                - len(before_state.get("contributions", [])),
            )
            summary["filings_added"] += filings_added
            summary["contributions_added"] += added_contribs
            if filings_added:
                summary["committees_extracted"] += 1
        except Exception as exc:
            print(f"  paper-extractor: {committee} failed ({exc}) — continuing")
            updated_state = _read_committee_extraction_state(committee)
            committee_errors.append(f"{committee} extraction failed: {exc}")
            committee_failed = True

        committee_pending = _pending_paper_filing_ids(
            filings,
            # A dry run does not create a durable artifact, so report pending
            # against the pre-run state even if extraction itself succeeded.
            before_state if dry_run else updated_state,
            db_extracted,
        )
        pending_ids.update(committee_pending)
        if committee_failed and not committee_pending:
            unknown_error_count += 1

    return _finalize_paper_extraction_summary(
        summary,
        pending_ids=pending_ids,
        reasons=committee_errors,
        unknown_incomplete_count=unknown_error_count,
    )


def _count_contribs(committee: str) -> int:
    p = find_committee_json(committee)
    if not p:
        return 0
    try:
        with open(p, encoding="utf-8") as f:
            return len(json.load(f).get("contributions", []))
    except (json.JSONDecodeError, OSError):
        return 0


def backfill_form460_summaries(client: LLMClient, dry_run: bool = False) -> None:
    """Backfill ``form_summary`` blocks onto already-extracted 460 filings.

    Walks every paper_filings/*.json and, for each filing where form='460'
    and form_summary is missing, downloads/uses-cached PDF and runs
    ``parse_form460_summary_with_vision``. Idempotent: filings already
    carrying a form_summary are skipped. Contribution rows are NOT
    re-extracted — only the summary block is added.

    Used after the I125 commit to retroactively populate cycle-to-date
    totals on existing JSONs without paying re-extraction costs.
    """
    json_files = sorted(PAPER_FILINGS_DIR.glob("*.json"))
    print(f"Backfilling Form 460 summaries across {len(json_files)} JSON file(s)...")
    total_added = 0
    total_skipped = 0
    for json_path in json_files:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        committee = data.get("committee", json_path.stem)

        added = 0
        for filing in data.get("filings", []):
            if filing.get("form") != "460":
                continue
            if "form_summary" in filing:
                total_skipped += 1
                continue
            filing_id = str(filing.get("filing_id", ""))
            if not filing_id:
                continue

            print(f"  [{committee}] filing {filing_id}: extracting summary...")
            try:
                pdf_path = download_paper_filing(filing_id, output_dir=PDF_CACHE_DIR)
            except Exception as exc:
                print(f"    download failed: {exc}")
                continue
            try:
                summary = parse_form460_summary_with_vision(
                    pdf_path, filing_id, committee, client
                )
            except Exception as exc:
                print(f"    Vision extraction failed: {exc}")
                continue
            if summary:
                filing["form_summary"] = summary
                added += 1
                total_added += 1
                print(
                    f"    ok: this_period=${summary.get('total_this_period', 0):,.2f}, "
                    f"cycle=${summary.get('total_cycle_to_date', 0):,.2f}, "
                    f"unitemized=${summary.get('unitemized_this_period', 0):,.2f}"
                )

        if added and not dry_run:
            write_json_atomic(json_path, data)
            print(f"  wrote {json_path}")

    print(f"\nDone. Added {total_added} summaries, skipped {total_skipped} already-populated.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract paper-filed contributions from NetFile PDFs")
    parser.add_argument("--committee", help="Restrict to one committee name (exact match)")
    parser.add_argument("--filing-id", help="Restrict to a single filing ID (requires --committee)")
    parser.add_argument("--dry-run", action="store_true", help="Extract but do not write JSON output")
    parser.add_argument("--backfill-summaries", action="store_true",
                        help="Backfill Form 460 cover-page summaries onto existing JSONs (no contribution re-extraction).")
    args = parser.parse_args()

    if args.filing_id and not args.committee:
        parser.error("--filing-id requires --committee")

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    client = LLMClient(api_key=api_key)

    if args.backfill_summaries:
        backfill_form460_summaries(client, dry_run=args.dry_run)
        return

    print("Discovering paper filers from NetFile RSS...")
    by_committee = discover_paper_filers()
    print(f"Found {len(by_committee)} committees with paper filings")

    if args.committee:
        if args.committee not in by_committee:
            available = "\n  ".join(sorted(by_committee.keys()))
            print(f"Committee not found in RSS: {args.committee!r}\nAvailable:\n  {available}")
            sys.exit(1)
        targets: Iterable[str] = [args.committee]
    else:
        targets = sorted(by_committee.keys())

    for committee in targets:
        print(f"\n-> {committee}")
        extract_committee(
            committee,
            by_committee[committee],
            client=client,
            dry_run=args.dry_run,
            only_filing_id=args.filing_id,
        )


if __name__ == "__main__":
    main()
