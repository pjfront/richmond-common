"""Bounded Anderson paper-source refresh and private review packets; no paid API.

The checked-in snapshot is the publication contract. This producer never edits
it, synthesizes donors, publishes a brief, or writes either finance ledger.
Unchanged evidence skips OCR; changed scans retain their exact PDF and local
Tesseract transcript before a resolve-only engineering packet is recorded.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable

import requests

from civic_review_packets import Packet, persist_packet

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "web/src/data/anderson-reported-finance.json"
PRODUCER = "paper_finance_review"
COMMITTEE = {"fppc_id": "1481105", "portal_filer_id": "214395297", "name": "Anderson for Mayor 2026"}
CONNECT = "https://netfile.com/Connect2/api/public"
INVENTORY = "https://netfile.com/api/public/sites/api/filings/byFiler?agencyCode=RICH&filerId=214395297&isArchived=false"
FORM_IDS = {"460": "f2a7917d-12a4-47ba-a0fb-6052cb544509", "497": "f875be6b-dacd-443e-b408-2175a56417ba"}
MAX_SOURCES = 100
MAX_PDF_READS = 16
MAX_PDF_BYTES = 6 * 1024 * 1024
MAX_RUN_BYTES = 32 * 1024 * 1024
MAX_OCR_PAGES = 8
MAX_CHANGED = 4
MAX_TEXT = 512 * 1024
RECHECK_DAYS = 7
HASH = re.compile(r"[0-9a-f]{64}")
ID = re.compile(r"[0-9]{6,12}")
MONEY = re.compile(r"(?<![\w/])(?:\$\s*)?-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}(?![\w/])")
DATE = re.compile(r"(?<!\d)(?:0?[1-9]|1[0-2])[/.-](?:0?[1-9]|[12]\d|3[01])[/.-](?:20\d{2}|\d{2})(?!\d)")
LABELS = (
    "monetary contributions", "loans received", "nonmonetary contributions", "total contributions",
    "payments made", "total expenditures", "beginning cash balance", "ending cash balance",
    "outstanding debts", "unitemized", "itemized", "contributions received",
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def dated(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Missing source date")
    return date.fromisoformat(value[:10]).isoformat()


def validate_snapshot(value: dict) -> dict[str, dict]:
    if value.get("schema_version") != 1 or value.get("committee") != COMMITTEE:
        raise ValueError("Unexpected paper snapshot identity or version")
    datetime.fromisoformat(value["reviewed_at"].replace("Z", "+00:00"))
    sources = value.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SOURCES:
        raise ValueError("Source snapshot must be bounded and nonempty")
    by_id = {}
    for source in sources:
        fid = source.get("filing_id")
        if not isinstance(fid, str) or not ID.fullmatch(fid) or fid in by_id:
            raise ValueError("Duplicate or invalid snapshot filing")
        if source.get("form") not in FORM_IDS or source.get("source_url") != f"{CONNECT}/image/{fid}":
            raise ValueError("Snapshot source must be the exact official filing URL")
        if any(not isinstance(source.get(key), str) or not HASH.fullmatch(source[key]) for key in ("pdf_sha256", "metadata_sha256")):
            raise ValueError("Snapshot requires exact PDF and metadata hashes")
        pages = source.get("reviewed_pages")
        if not isinstance(pages, list) or not pages or any(type(p) is not int or p < 1 or p > 200 for p in pages):
            raise ValueError("Snapshot requires reviewed source pages")
        filed = dated(source["filed_at"])
        if source["form"] == "460":
            if not dated(source["period_start"]) <= dated(source["period_end"]) <= filed:
                raise ValueError("Invalid snapshot reporting period")
        elif source.get("period_start") is not None or source.get("period_end") is not None:
            raise ValueError("Rapid reports do not establish a reporting period")
        by_id[fid] = source
    latest = value.get("periodic", {}).get("filing_id")
    if latest not in by_id or by_id[latest]["form"] != "460":
        raise ValueError("Snapshot latest periodic filing must have pinned evidence")
    return by_id


def select_inventory(value: dict, snapshot: dict, today: date) -> dict[str, dict]:
    baseline = validate_snapshot(snapshot)
    rows = value.get("filings")
    count = value.get("totalCount")
    # The official portal returns totalCount=0 alongside its nonempty array.
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100 or type(count) is not int or count < 0 or (count and count != len(rows)):
        raise ValueError("Official inventory is empty, truncated, or malformed")
    seen, supported = set(), {}
    for row in rows:
        fid = row.get("id")
        if not isinstance(fid, str) or not ID.fullmatch(fid) or fid in seen or row.get("filerName") != COMMITTEE["name"]:
            raise ValueError("Official inventory has an ambiguous filing identity")
        seen.add(fid)
        form = {"FPPC 460": "460", "FPPC Form 497": "497"}.get(row.get("formName"))
        if not form:
            continue
        filed = dated(row["filingDate"])
        if filed > today.isoformat() or row.get("formId") != FORM_IDS[form]:
            raise ValueError("Unexpected filing date or form identity")
        item = {"filing_id": fid, "form": form, "filed_at": filed,
                "period_start": dated(row["periodStart"]) if form == "460" else None,
                "period_end": dated(row["periodEnd"]) if form == "460" else None}
        if form == "460" and not item["period_start"] <= item["period_end"] <= filed:
            raise ValueError("Invalid official reporting period")
        supported[fid] = item
    if not set(baseline) <= set(supported):
        # Removal is a failure for investigation, never a silent replacement
        # with an empty or smaller source set.
        raise ValueError("A reviewed source disappeared from the official inventory")
    year_start = "2026-01-01"
    cutoff = baseline[snapshot["periodic"]["filing_id"]]["period_end"]
    selected = {fid: row for fid, row in supported.items() if fid in baseline
                or (row["form"] == "460" and (row["period_end"] >= year_start or row["filed_at"] >= year_start))
                or (row["form"] == "497" and row["filed_at"] > cutoff)}
    return selected


def metadata_core(raw: dict, source: dict) -> dict:
    fid, form = source["filing_id"], source["form"]
    if (str(raw.get("filingId")) != fid or raw.get("sosFilerId") != COMMITTEE["fppc_id"]
            or raw.get("agency") != "RICH" or raw.get("filerName") != COMMITTEE["name"]
            or raw.get("formId") != FORM_IDS[form] or type(raw.get("isEfiled")) is not bool):
        raise ValueError("Independent filing metadata does not match the exact candidate")
    core = {**source, "is_efiled": raw["isEfiled"], "amends": raw.get("amends"), "amended_by": raw.get("amendedBy")}
    if dated(raw["filingDate"]) != source["filed_at"] or (form == "460" and
            (dated(raw["dateStart"]) != source["period_start"] or dated(raw["dateEnd"]) != source["period_end"])):
        raise ValueError("Independent filing metadata disagrees with inventory dates")
    return core


class Acquisition:
    def __init__(self, source_dir: Path | None = None):
        self.source_dir = source_dir
        self.bytes = 0
        self.requests = 0
        self.pdf_downloads = 0

    def get(self, url: str, cap: int, local_name: str | None = None) -> bytes:
        if self.source_dir and local_name and (self.source_dir / local_name).is_file():
            raw = (self.source_dir / local_name).read_bytes()
        else:
            self.requests += 1
            start = time.monotonic()
            with requests.get(url, timeout=(5, 10), stream=True, allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError("Official source request did not return HTTP200")
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > cap or time.monotonic() - start > 30:
                        raise ValueError("Official source exceeded its read bound")
                raw = bytes(raw)
            if local_name and local_name.endswith(".pdf"):
                self.pdf_downloads += 1
        self.bytes += len(raw)
        if len(raw) > cap or self.bytes > MAX_RUN_BYTES:
            raise ValueError("Official acquisition byte cap exceeded")
        return raw


def tesseract_page(image: Path) -> list[dict]:
    binary = shutil.which("tesseract")
    if not binary:
        raise RuntimeError("Local Tesseract is unavailable")
    result = subprocess.run([binary, str(image), "stdout", "-l", "eng", "--psm", "11", "tsv"],
                            capture_output=True, timeout=30, check=True)
    if len(result.stdout) > 2 * 1024 * 1024:
        raise ValueError("OCR output cap exceeded")
    tokens = []
    for row in csv.DictReader(io.StringIO(result.stdout.decode("utf-8", errors="strict")), delimiter="\t"):
        if not {"text", "conf", "left", "top", "width", "height"} <= row.keys():
            raise ValueError("Malformed OCR columns")
        confidence = float(row["conf"])
        if row["text"].strip() and 80 <= confidence <= 100:
            tokens.append({"text": row["text"].strip(), "confidence": confidence,
                           "x": int(row["left"]), "y": int(row["top"]), "width": int(row["width"]), "height": int(row["height"])})
    return tokens


def safe_candidates(tokens: list[dict], page: int) -> dict:
    """Amounts and dates are candidate tokens, never asserted row associations.

    Return allowlisted labels rather than raw lines: OCR transcripts can contain
    personal street addresses, so they stay in the private document record.
    """
    text = " ".join(token["text"] for token in tokens)
    amounts, dates = sorted(set(MONEY.findall(text))), sorted(set(DATE.findall(text)))
    return {"page": page, "labels": [label for label in LABELS if label in text.casefold()],
            "amount_tokens": amounts[:32], "amount_tokens_omitted": max(0, len(amounts) - 32),
            "date_tokens": dates[:16], "date_tokens_omitted": max(0, len(dates) - 16),
            "status": "Unverified OCR/text candidates; no donor/date/amount pairing is inferred."}


def prepare_pages(pdf: bytes, ocr: Callable = tesseract_page) -> dict:
    import pymupdf
    pages, transcript = [], []
    with pymupdf.open(stream=pdf, filetype="pdf") as document, tempfile.TemporaryDirectory(prefix="paper-finance-") as folder:
        if not 1 <= len(document) <= 200 or document.is_encrypted:
            raise ValueError("Unsupported source PDF")
        for index in range(min(len(document), MAX_OCR_PAGES)):
            page = document[index]
            words = page.get_text("words")
            tokens = [{"text": word[4], "confidence": 100, "x": word[0], "y": word[1], "width": word[2]-word[0], "height": word[3]-word[1]} for word in words]
            method = "pdf_text"
            if not tokens:
                image = Path(folder) / f"page-{index+1}.png"
                # Bound rendering even for unusual source page dimensions.
                scale = min(2.0, 1800 / max(page.rect.width, page.rect.height))
                page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(image)
                try:
                    tokens = ocr(image)
                    method = "local_tesseract"
                except (RuntimeError, ValueError, subprocess.SubprocessError):
                    tokens, method = [], "ocr_unavailable"
            transcript.append({"page": index + 1, "method": method, "tokens": tokens})
            pages.append({**safe_candidates(tokens, index + 1), "method": method})
            if len(canonical(transcript)) > MAX_TEXT:
                raise ValueError("OCR transcript cap exceeded")
        return {"page_count": len(document), "prepared_pages": pages, "private_transcript": transcript,
                "omitted_pages": max(0, len(document) - MAX_OCR_PAGES)}


def baseline_matches(source: dict, core: dict, pdf_hash: str, metadata_hash: str) -> bool:
    return (source["pdf_sha256"] == pdf_hash and source["metadata_sha256"] == metadata_hash
        and core["is_efiled"] is False and all(source.get(key) == core.get(key) for key in
        ("filing_id", "form", "filed_at", "period_start", "period_end"))
        and core["amends"] is None and core["amended_by"] is None)


def prepare_packet(record: dict, baseline: dict | None, snapshot: dict) -> Packet:
    core = record["core"]
    fid = core["filing_id"]
    cutoff = next(s for s in snapshot["sources"] if s["filing_id"] == snapshot["periodic"]["filing_id"])["period_end"]
    sources = [{"url": f"{CONNECT}/image/{fid}#page={page['page']}", "title": f"Original Form {core['form']} filing {fid}, page {page['page']}"}
               for page in record["pages"]["prepared_pages"]]
    return Packet(identity=f"paper-finance:1481105:{fid}", subject="2026-general",
        title=f"Check Anderson Form {core['form']} filing {fid}",
        description="Prepare the changed reported-finance snapshot from this original source. Approving this engineering packet records a judgment only; it does not publish numbers or repair any finance row.",
        evidence={"question": "Which printed figures and receipt dates should replace or extend the dated Anderson snapshot?",
          "recommendation": "Check the prepared page candidates against the PDF, preserve blank/conflicting cells, then update the source-pinned JSON and its tests in a reviewed PR.",
          "proposed_change": {"snapshot": "web/src/data/anderson-reported-finance.json", "filing": core,
                              "previous_source": baseline, "unverified_page_candidates": record["pages"]["prepared_pages"]},
          "alternatives": ["Retain current figures and record the specific missing source evidence.", "Correct the proposed transcript using the linked original pages before updating the JSON."],
          "source_versions": [[fid, record["pdf_sha256"], record["core_sha256"], record["metadata_sha256"]]],
          "sources": sources, "source_pdf_sha256": record["pdf_sha256"],
          "latest_reviewed_period_end": cutoff,
          "comparison_rule": "A 497 filing date is not its receipt date. Never add overlapping 460/497 disclosures, cumulative columns, loans, or noncash to monetary receipts.",
          "ocr_limit": {"prepared_pages": len(sources), "omitted_pages": record["pages"]["omitted_pages"]},
          "affected_pages": ["/elections/2026-general", "/elections/2026-general/money", "/elections/2026-general/money/ahmad-anderson"],
          "publication_effect": "None. A tested source-checked JSON change and deployment publishes a new snapshot."})


def acquire(snapshot: dict, acquisition: Acquisition, existing: dict[str, dict], now: datetime,
            ocr: Callable = tesseract_page) -> list[dict]:
    baseline = validate_snapshot(snapshot)
    selected = select_inventory(json.loads(acquisition.get(INVENTORY, 256 * 1024, "inventory.json")), snapshot, now.date())
    records, prepared, pdf_reads = [], 0, 0
    acquisition.deferred_filings = []
    acquisition.selected_count = len(selected)
    # Read all bounded metadata before spending the PDF byte allowance. This
    # keeps every current filing discoverable while permitting partial PDF work.
    metadata_by_id = {}
    for fid, source in sorted(selected.items()):
        metadata_bytes = acquisition.get(f"{CONNECT}/filing/info/{fid}?format=json", 128 * 1024, f"{fid}.metadata.json")
        metadata = json.loads(metadata_bytes)
        core = metadata_core(metadata, source)
        metadata_by_id[fid] = (metadata, core, sha(canonical(core)), sha(metadata_bytes))
    # Unknown sources first, then the oldest successful check. A broken OCR
    # dependency cannot monopolize every poll ahead of unseen source evidence.
    order = sorted(selected.items(), key=lambda item: (item[0] in existing,
        existing.get(item[0], {}).get("last_checked_at", ""), item[0]))
    for fid, source in order:
        metadata, core, core_hash, metadata_hash = metadata_by_id[fid]
        cached = existing.get(fid)
        reviewed = bool(cached and fid in baseline and baseline_matches(baseline[fid], core, cached["pdf_sha256"], metadata_hash))
        incomplete_ocr = bool(cached and any(page.get("method") == "ocr_unavailable" for page in cached["pages"]["prepared_pages"]))
        metadata_same = bool(cached and cached["core_sha256"] == core_hash and cached["metadata_sha256"] == metadata_hash)
        if metadata_same and (reviewed or (not incomplete_ocr and cached["pages"]["prepared_pages"])) and datetime.fromisoformat(cached["last_checked_at"]) > now - timedelta(days=RECHECK_DAYS):
            records.append({**cached, "needs_packet": not reviewed, "write_needed": False})
            continue
        # Do not fetch a known outstanding preparation beyond this run's bound.
        # Baseline hash checks and expired unchanged prepared sources can still
        # proceed without consuming the preparation allowance.
        may_need_preparation = (not cached and fid not in baseline) or (cached and not reviewed and (not metadata_same or incomplete_ocr))
        if may_need_preparation and prepared >= MAX_CHANGED:
            acquisition.deferred_filings.append(fid)
            continue
        # Reserve a full permitted PDF before a read. Conservative unused room
        # is preferable to aborting the already prepared sources at the byte cap.
        if pdf_reads >= MAX_PDF_READS or MAX_RUN_BYTES - getattr(acquisition, "bytes", 0) < MAX_PDF_BYTES:
            acquisition.deferred_filings.append(fid)
            continue
        pdf_reads += 1
        pdf = acquisition.get(f"{CONNECT}/image/{fid}", MAX_PDF_BYTES, f"{fid}.pdf")
        if not pdf.startswith(b"%PDF-"):
            raise ValueError("Official source did not return a PDF")
        pdf_hash = sha(pdf)
        is_reviewed = fid in baseline and baseline_matches(baseline[fid], core, pdf_hash, metadata_hash)
        needs_packet = not is_reviewed
        same_pdf = bool(cached and cached["pdf_sha256"] == pdf_hash)
        requires_preparation = needs_packet and (not same_pdf or incomplete_ocr or not cached["pages"]["prepared_pages"])
        if requires_preparation and prepared >= MAX_CHANGED:
            acquisition.deferred_filings.append(fid)
            continue
        if requires_preparation:
            prepared += 1
        pages = prepare_pages(pdf, ocr) if requires_preparation else cached["pages"] if same_pdf and needs_packet else {
            "page_count": None, "prepared_pages": [], "private_transcript": [], "omitted_pages": 0}
        records.append({"core": core, "core_sha256": core_hash, "pdf_sha256": pdf_hash,
                        "metadata_sha256": metadata_hash, "raw_metadata": metadata,
                        "pages": pages, "last_checked_at": now.isoformat(), "pdf": pdf,
                        "needs_packet": needs_packet, "write_needed": True})
    acquisition.prepared_count = prepared
    acquisition.pdf_reads = pdf_reads
    return records


def read_existing(conn: Any) -> dict[str, dict]:
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT DISTINCT ON (source_identifier) source_identifier,metadata
            FROM documents WHERE source_type='netfile_transaction' AND metadata->>'producer'=%s
            AND metadata->>'artifact_kind'='paper_filing_review'
            ORDER BY source_identifier,metadata->>'last_checked_at' DESC LIMIT 201""", (PRODUCER,))
        rows = cur.fetchall()
        if len(rows) > 200:
            raise ValueError("Private source cache cap exceeded")
        return {row["source_identifier"]: row["metadata"]["record"] | {"last_checked_at": row["metadata"]["last_checked_at"]} for row in rows}


def persist_record(conn: Any, record: dict, snapshot: dict) -> str:
    """One source's raw evidence and queue change commit together; caller holds no public write contract."""
    from psycopg2.extras import Json, RealDictCursor
    if not record["write_needed"]:
        return "unchanged"
    fid = record["core"]["filing_id"]
    stable = {key: value for key, value in record.items() if key not in {"pdf", "last_checked_at", "write_needed", "needs_packet"}}
    payloads = [(record["pdf"], "application/pdf", "paper_filing_pdf"), (canonical(stable), "application/json", "paper_filing_review")]
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (PRODUCER + fid,))
            for payload, mime, kind in payloads:
                content_hash = sha(payload)
                metadata = {"producer": PRODUCER, "artifact_kind": kind, "filing_id": fid,
                            "pdf_sha256": record["pdf_sha256"], "last_checked_at": record["last_checked_at"]}
                if kind == "paper_filing_review":
                    metadata["record"] = stable
                cur.execute("""INSERT INTO documents(city_fips,source_type,source_url,source_identifier,raw_content,
                    content_hash,mime_type,credibility_tier,metadata)
                    VALUES('0660620','netfile_transaction',%s,%s,decode(%s,'hex'),%s,%s,1,%s)
                    ON CONFLICT(city_fips,content_hash) DO NOTHING""", (f"{CONNECT}/image/{fid}", fid, payload.hex(), content_hash, mime, Json(metadata)))
                cur.execute("SELECT id,source_type,metadata FROM documents WHERE city_fips='0660620' AND content_hash=%s", (content_hash,))
                stored = cur.fetchone()
                if not stored or stored["source_type"] not in {"netfile_transaction", "netfile_496"}:
                    raise ValueError("Identical source bytes are not in the private finance document boundary")
                if kind == "paper_filing_review" and stored["metadata"].get("last_checked_at") != record["last_checked_at"]:
                    cur.execute("UPDATE documents SET metadata=jsonb_set(metadata,'{last_checked_at}',%s) WHERE id=%s", (Json(record["last_checked_at"]), stored["id"]))
        if record["needs_packet"]:
            packet = prepare_packet(record, validate_snapshot(snapshot).get(fid), snapshot)
            # A repaired OCR dependency can improve the same source packet.
            # Refresh only still-open evidence; rejected/closed identical sources
            # stay suppressed. The existing trigger advances review_version.
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""UPDATE pending_decisions SET evidence=%s WHERE source='civic_review_packets'
                    AND entity_id=%s AND dedup_key=%s AND action_kind='resolve_only'
                    AND status IN ('pending','deferred') AND evidence IS DISTINCT FROM %s RETURNING id""",
                    (Json(packet.evidence), packet.identity, packet.dedup_key, Json(packet.evidence)))
                prepared_refreshed = cur.fetchone() is not None
            result = persist_packet(conn, packet)
            return "refreshed" if result == "unchanged" and prepared_refreshed else result
        conn.commit()
        return "source_retained"
    except Exception:
        conn.rollback()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--source-dir", type=Path, help="Use exact retained PDF/metadata files when present; no duplicate downloads")
    parser.add_argument("--apply", action="store_true", help="Persist private evidence and resolve-only packets; never publish numbers")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    validate_snapshot(snapshot)
    from db import get_connection
    conn = get_connection()
    try:
        conn.set_session(readonly=not args.apply)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout='15s'")
        existing = read_existing(conn)
        conn.commit()
        acquisition = Acquisition(args.source_dir)
        records = acquire(snapshot, acquisition, existing, datetime.now(timezone.utc))
        counts: dict[str, int] = {}
        if args.apply:
            for record in records:
                result = persist_record(conn, record, snapshot)
                counts[result] = counts.get(result, 0) + 1
        summary = {"mode": "apply" if args.apply else "dry_run", "filings_checked": len(records),
                   "selected_filings": acquisition.selected_count, "deferred_filings": len(acquisition.deferred_filings),
                   "prepared_sources": acquisition.prepared_count,
                   "pdf_reads": acquisition.pdf_reads,
                   "changed_sources": sum(record["needs_packet"] for record in records),
                   "http_requests": acquisition.requests, "pdf_downloads": acquisition.pdf_downloads,
                   "source_bytes_read": acquisition.bytes, "llm_calls": 0, "published": 0, **counts}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, sort_keys=True))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
