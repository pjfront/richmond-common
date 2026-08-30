"""Bounded, review-gated repair for three July 2026 transcript recaps.

Reads fresh official Granicus transcript PDFs and their extracted clean text.
Does NOT read ``meetings.transcript_recap`` or another derivative to generate
the candidate. Generation writes a private local candidate artifact only.
Publication is a separate, cohort-atomic operation that requires independent
source-review receipts bound to the exact candidate and source hashes.

This is intentionally a one-off operator tool, not a generic backfill path.
Its hardcoded allowlist, durable paid-attempt check, all-null compare-and-swap,
and lack of force/replay/cascade flags are part of the safety contract.

Usage (one fresh process per paid call)::

    python src/reviewed_july_recap_repair.py status
    python src/reviewed_july_recap_repair.py generate --meeting-date 2026-07-07
    python src/reviewed_july_recap_repair.py apply-reviewed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

from db import get_connection
from granicus_transcripts import (
    _pdf_to_clean_text,
    _resolve_pdf_url,
    discover_granicus_meetings,
)
from llm_client import LLMClient
from post_meeting_recap import (
    MAX_TOKENS_TRANSCRIPT_RECAP,
    _load_canonical_names,
    _load_prompt,
)


APPROVAL_ID = "reviewed-july-recap-repair-v2"
SCHEMA_VERSION = 1
MODEL = "deepseek-v4-pro"
CITY_FIPS = "0660620"
MEETING_TYPE = "regular"
BODY_ID = "0fbda6b0-b0c7-46f4-8453-97aeaa305c47"
BODY_NAME = "City Council"
MAX_CALL_COST_USD = 0.15
MAX_MONTHLY_CAP_USD = 5.00
GENERATOR = "reviewed_july_recap_repair.py"
CALLER = "reviewed_july_recap_repair"

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / "data" / "reviewed_july_recap_v2"
SOURCE_DIR = ARTIFACT_DIR / "sources"

RECAP_FIELDS = (
    "transcript_recap",
    "transcript_recap_source",
    "transcript_recap_provenance",
    "transcript_recap_generated_at",
)

REVIEW_CHECKS = (
    "claim_inventory_complete",
    "numbers_and_amounts_supported",
    "names_roles_and_affiliations_supported",
    "votes_motions_outcomes_and_dates_supported",
    "attributions_and_stances_supported",
    "later_corrections_honored",
    "completed_speaker_turns_not_registrations",
    "quantitative_hierarchies_kept_separate",
    "uncertainty_preserved",
    "no_material_contradictions_or_ambiguities",
)


@dataclass(frozen=True)
class RepairTarget:
    meeting_date: str
    meeting_id: str
    clip_id: str
    doc_id: str

    @property
    def source_url(self) -> str:
        return (
            "https://richmond.granicus.com/MinutesViewer.php?view_id=30"
            f"&clip_id={self.clip_id}&doc_id={self.doc_id}"
        )


TARGETS: dict[str, RepairTarget] = {
    "2026-07-07": RepairTarget(
        meeting_date="2026-07-07",
        meeting_id="c11d635f-b74f-4208-8fad-376a3791905b",
        clip_id="6020",
        doc_id="a6f2bc6d-7aed-11f1-9494-005056a89546",
    ),
    "2026-07-21": RepairTarget(
        meeting_date="2026-07-21",
        meeting_id="a166af80-e456-4db2-9b74-215a378956a4",
        clip_id="6025",
        doc_id="892134f4-85f3-11f1-bb61-005056a89546",
    ),
    "2026-07-28": RepairTarget(
        meeting_date="2026-07-28",
        meeting_id="3de0bb26-8f30-4836-a5bd-a01b6640b676",
        clip_id="6028",
        doc_id="15999ea7-8b71-11f1-bb61-005056a89546",
    ),
}


class RepairBlocked(RuntimeError):
    """Fail-closed stop that never authorizes a retry or broader repair."""


def _blocked(reason: str, action: str) -> RepairBlocked:
    return RepairBlocked(f"{reason}\nACTION: {action}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _candidate_path(meeting_date: str) -> Path:
    return ARTIFACT_DIR / f"{meeting_date}.candidate.json"


def _review_path(meeting_date: str) -> Path:
    return ARTIFACT_DIR / f"{meeting_date}.review.json"


def _failed_attempt_path(meeting_date: str) -> Path:
    return ARTIFACT_DIR / f"{meeting_date}.failed-attempt.json"


def _source_paths(meeting_date: str) -> tuple[Path, Path, Path]:
    bundle_dir = SOURCE_DIR / meeting_date
    return (
        bundle_dir / "granicus.pdf",
        bundle_dir / "clean.txt",
        bundle_dir / "source.json",
    )


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    """Create an artifact exactly once; never overwrite review evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise _blocked(
            f"Artifact already exists: {path}",
            "Do not delete or overwrite it. Give this output to the project "
            "maintainer; this approval does not permit replay.",
        ) from exc


def _read_json_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw_bytes = path.read_bytes()
        payload = json.loads(raw_bytes.decode("utf-8"))
    except FileNotFoundError as exc:
        raise _blocked(
            f"Required artifact is missing: {path}",
            "Complete the missing candidate or independent source review. Do "
            "not publish a partial cohort.",
        ) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _blocked(
            f"Required artifact is unreadable: {path}",
            "Give the file and this error to a coding assistant. Do not edit "
            "the evidence by hand or retry the paid call.",
        ) from exc
    if not isinstance(payload, dict):
        raise _blocked(
            f"Artifact must contain one JSON object: {path}",
            "Give the file to a coding assistant; do not publish it.",
        )
    return payload, raw_bytes


def _read_json(path: Path) -> dict[str, Any]:
    return _read_json_snapshot(path)[0]


def _normalized_row(row: Iterable[Any]) -> dict[str, Any]:
    values = list(row)
    if len(values) != 10:
        raise _blocked(
            "The cohort query returned an unexpected database shape.",
            "Stop and give this error to a coding assistant; do not run any "
            "broader repair.",
        )
    return {
        "meeting_id": str(values[0]),
        "meeting_date": str(values[1]),
        "city_fips": values[2],
        "meeting_type": values[3],
        "body_id": str(values[4]),
        "body_name": values[5],
        "transcript_recap": values[6],
        "transcript_recap_source": values[7],
        "transcript_recap_provenance": values[8],
        "transcript_recap_generated_at": values[9],
    }


def _load_cohort_rows(conn: Any, *, for_update: bool = False) -> list[dict[str, Any]]:
    lock_clause = " FOR UPDATE OF m" if for_update else ""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT m.id, m.meeting_date, m.city_fips, m.meeting_type,
                      m.body_id, b.name,
                      m.transcript_recap, m.transcript_recap_source,
                      m.transcript_recap_provenance,
                      m.transcript_recap_generated_at
               FROM meetings m
               JOIN bodies b ON b.id = m.body_id
               WHERE m.city_fips = %s
                 AND m.meeting_type = %s
                 AND m.body_id = %s
                 AND m.meeting_date = ANY(%s::date[])
               ORDER BY m.meeting_date""" + lock_clause,
            (CITY_FIPS, MEETING_TYPE, BODY_ID, sorted(TARGETS)),
        )
        return [_normalized_row(row) for row in cur.fetchall()]


def _validate_cohort_null(rows: list[dict[str, Any]]) -> None:
    expected_ids = {target.meeting_id for target in TARGETS.values()}
    actual_ids = {row["meeting_id"] for row in rows}
    if len(rows) != len(TARGETS) or actual_ids != expected_ids:
        raise _blocked(
            "The exact three-row July cohort could not be proven.",
            "Stop and give the cohort status to a coding assistant. Do not "
            "substitute another meeting or use a date-only writer.",
        )

    for row in rows:
        target = TARGETS.get(row["meeting_date"])
        identity_ok = bool(
            target
            and row["meeting_id"] == target.meeting_id
            and row["city_fips"] == CITY_FIPS
            and row["meeting_type"] == MEETING_TYPE
            and row["body_id"] == BODY_ID
            and row["body_name"] == BODY_NAME
        )
        if not identity_ok:
            raise _blocked(
                f"Meeting identity drifted for {row['meeting_date']}.",
                "Stop and give this row to a coding assistant. Do not guess "
                "which meeting should be repaired.",
            )
        non_null = [field for field in RECAP_FIELDS if row[field] is not None]
        if non_null:
            raise _blocked(
                f"{row['meeting_date']} no longer has an all-null review gate; "
                f"non-null fields: {', '.join(non_null)}.",
                "Stop. Do not force, overwrite, replay, or compensate. Have a "
                "coding assistant reconcile the exact row state.",
            )


def _event_type(meeting_date: str) -> str:
    return f"{APPROVAL_ID}:{meeting_date}"


def _parse_cap(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise _blocked(
            f"{name} is not a valid dollar amount.",
            "Correct the environment setting; do not bypass the cost guard.",
        ) from exc
    if not math.isfinite(value) or value < 0:
        raise _blocked(
            f"{name} must be finite and non-negative.",
            "Correct the environment setting; do not bypass the cost guard.",
        )
    return value


def _configure_cost_guards(meeting_date: str) -> None:
    if os.environ.get("RICHMOND_API_BUDGET_LOCK", "").strip().lower() in {
        "1", "true", "yes", "on"
    }:
        raise _blocked(
            "RICHMOND_API_BUDGET_LOCK is active.",
            "Leave the lock in place and stop. A later explicit approval is "
            "required after the lock is intentionally cleared.",
        )

    monthly_cap = _parse_cap("RICHMOND_API_MONTHLY_CAP_USD", MAX_MONTHLY_CAP_USD)
    if monthly_cap > MAX_MONTHLY_CAP_USD:
        raise _blocked(
            f"The configured monthly cap ${monthly_cap:.2f} exceeds the "
            f"preserved ${MAX_MONTHLY_CAP_USD:.2f} boundary.",
            "Set RICHMOND_API_MONTHLY_CAP_USD to 5.00 or lower; do not run "
            "with a wider cap.",
        )
    os.environ["RICHMOND_API_MONTHLY_CAP_USD"] = f"{monthly_cap:.2f}"

    event_cap = _parse_cap("RICHMOND_EVENT_BUDGET_USD", MAX_CALL_COST_USD)
    if event_cap > MAX_CALL_COST_USD:
        event_cap = MAX_CALL_COST_USD
    os.environ["RICHMOND_EVENT_BUDGET_USD"] = f"{event_cap:.2f}"
    os.environ["RICHMOND_EVENT_TYPE"] = _event_type(meeting_date)

    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise _blocked(
            "DEEPSEEK_API_KEY is unavailable.",
            "Provide the existing DeepSeek credential to this one process; do "
            "not add a fallback provider or place the key in a tracked file.",
        )


def _assert_no_paid_attempt(conn: Any, meeting_date: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, status, projected_cost, actual_cost
               FROM llm_cost_reservations
               WHERE event_type = %s
               ORDER BY created_at""",
            (_event_type(meeting_date),),
        )
        attempts = cur.fetchall()
    if attempts:
        raise _blocked(
            f"A paid V2 attempt already exists for {meeting_date}.",
            "Do not retry, even if the earlier request timed out or its local "
            "artifact is missing. Give the reservation row to a coding assistant.",
        )


def _acquire_generation_lock(conn: Any, meeting_date: str) -> None:
    """Serialize the entire check/call/artifact sequence for one approved date."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{APPROVAL_ID}:generate:{meeting_date}",),
        )
        row = cur.fetchone()
    if row is None or row[0] is not True:
        raise _blocked(
            f"Another V2 generation process holds the lock for {meeting_date}.",
            "Stop this process. Do not start another one or retry the paid call; "
            "wait for the existing process and inspect its candidate or cost receipt.",
        )


def _discover_exact_source(target: RepairTarget) -> dict[str, Any]:
    matches = [
        meeting
        for meeting in discover_granicus_meetings()
        if meeting.get("meeting_date") == target.meeting_date
    ]
    if len(matches) != 1:
        raise _blocked(
            f"Expected one Granicus transcript for {target.meeting_date}; "
            f"found {len(matches)}.",
            "Stop and give the Granicus discovery result to a coding assistant; "
            "do not select a source by guesswork.",
        )
    match = matches[0]
    if (
        str(match.get("clip_id")) != target.clip_id
        or str(match.get("doc_id", "")).lower() != target.doc_id.lower()
    ):
        raise _blocked(
            f"The official source identity changed for {target.meeting_date}.",
            "Stop and independently verify the clip and document IDs before "
            "changing the checked-in allowlist.",
        )
    return match


def _validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "richmond.granicus.com"
        or parsed.path != "/DocumentViewer.php"
    ):
        raise _blocked(
            f"Granicus resolved an unexpected transcript URL: {url}",
            "Stop and verify the official archive path; do not download from "
            "an unapproved host.",
        )


def _validate_existing_source(target: RepairTarget) -> dict[str, Any] | None:
    pdf_path, transcript_path, identity_path = _source_paths(target.meeting_date)
    existence = (pdf_path.exists(), transcript_path.exists(), identity_path.exists())
    if not any(existence):
        return None
    if not all(existence):
        raise _blocked(
            f"The V2 source artifact set is incomplete for {target.meeting_date}.",
            "Do not delete, refill, or reuse a partial set. Give the artifact "
            "directory to a coding assistant.",
        )
    identity = _read_json(identity_path)
    expected = {
        "schema_version": SCHEMA_VERSION,
        "approval_id": APPROVAL_ID,
        "meeting_date": target.meeting_date,
        "meeting_id": target.meeting_id,
        "clip_id": target.clip_id,
        "doc_id": target.doc_id,
        "source": "granicus",
        "source_url": target.source_url,
        "pdf_path": str(pdf_path),
        "transcript_path": str(transcript_path),
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise _blocked(
            f"The V2 source sidecar does not match {target.meeting_date}.",
            "Stop and have a coding assistant inspect the source artifacts; "
            "do not relabel them.",
        )
    resolved_pdf_url = identity.get("resolved_pdf_url")
    if not isinstance(resolved_pdf_url, str):
        raise _blocked(
            f"The V2 source URL is missing for {target.meeting_date}.",
            "Stop and have a coding assistant inspect the source artifacts.",
        )
    _validate_source_url(resolved_pdf_url)
    fetched_at = identity.get("fetched_at")
    try:
        parsed_fetched_at = datetime.fromisoformat(str(fetched_at))
    except ValueError as exc:
        raise _blocked(
            f"The V2 source timestamp is invalid for {target.meeting_date}.",
            "Stop and have a coding assistant inspect the source artifacts.",
        ) from exc
    if parsed_fetched_at.tzinfo is None:
        raise _blocked(
            f"The V2 source timestamp lacks a timezone for {target.meeting_date}.",
            "Stop and have a coding assistant inspect the source artifacts.",
        )
    transcript_bytes = transcript_path.read_bytes()
    try:
        transcript = transcript_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _blocked(
            f"The V2 transcript is not UTF-8 for {target.meeting_date}.",
            "Stop and have a coding assistant inspect the source artifact.",
        ) from exc
    if (
        identity.get("pdf_sha256") != _sha256_file(pdf_path)
        or identity.get("transcript_sha256") != _sha256_bytes(transcript_bytes)
        or identity.get("transcript_char_count") != len(transcript)
    ):
        raise _blocked(
            f"The V2 source hash changed for {target.meeting_date}.",
            "Stop. Do not generate from or repair a changed source artifact.",
        )
    return identity


def _fetch_or_validate_source(target: RepairTarget) -> dict[str, Any]:
    _discover_exact_source(target)
    existing = _validate_existing_source(target)
    if existing is not None:
        return existing

    pdf_path, transcript_path, identity_path = _source_paths(target.meeting_date)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    bundle_dir = pdf_path.parent
    staging_dir = SOURCE_DIR / (
        f".{target.meeting_date}.staging-{uuid.uuid4().hex}"
    )
    staging_dir.mkdir(parents=False, exist_ok=False)
    staging_pdf_path = staging_dir / pdf_path.name
    staging_transcript_path = staging_dir / transcript_path.name
    staging_identity_path = staging_dir / identity_path.name
    resolved_url = _resolve_pdf_url(target.clip_id, target.doc_id)
    if not resolved_url:
        raise _blocked(
            f"Could not resolve the official transcript PDF for {target.meeting_date}.",
            "Stop and give the exact date, clip ID, and document ID to a coding "
            "assistant. Do not substitute another source.",
        )
    _validate_source_url(resolved_url)

    try:
        response = requests.get(resolved_url, timeout=60)
        response.raise_for_status()
        pdf_bytes = response.content
    except requests.RequestException as exc:
        raise _blocked(
            f"The official transcript download failed for {target.meeting_date}: {exc}",
            "Stop and give the date plus this error to a coding assistant. This "
            "did not authorize substituting another source.",
        ) from exc
    if not pdf_bytes.startswith(b"%PDF-"):
        raise _blocked(
            f"The official source response was not a PDF for {target.meeting_date}.",
            "Stop and have a coding assistant inspect the Granicus response.",
        )
    staging_pdf_path.write_bytes(pdf_bytes)
    try:
        transcript = _pdf_to_clean_text(staging_pdf_path)
    except Exception as exc:
        raise _blocked(
            f"The official PDF could not be extracted for {target.meeting_date}: {exc}",
            "Stop and give the fresh PDF plus this error to a coding assistant. "
            "Do not make the paid call.",
        ) from exc
    if len(transcript.strip()) < 1_000:
        raise _blocked(
            f"The extracted transcript is unexpectedly short for {target.meeting_date}.",
            "Stop and inspect the official PDF extraction; do not call the LLM.",
        )
    staging_transcript_path.write_text(
        transcript, encoding="utf-8", newline="\n"
    )

    identity = {
        "schema_version": SCHEMA_VERSION,
        "approval_id": APPROVAL_ID,
        "meeting_date": target.meeting_date,
        "meeting_id": target.meeting_id,
        "clip_id": target.clip_id,
        "doc_id": target.doc_id,
        "source": "granicus",
        "source_url": target.source_url,
        "resolved_pdf_url": resolved_url,
        "fetched_at": _utc_now(),
        "pdf_path": str(pdf_path),
        "pdf_sha256": _sha256_file(staging_pdf_path),
        "transcript_path": str(transcript_path),
        "transcript_sha256": _sha256_file(staging_transcript_path),
        "transcript_char_count": len(transcript),
    }
    _write_new_json(staging_identity_path, identity)
    try:
        staging_dir.replace(bundle_dir)
    except OSError as exc:
        raise _blocked(
            f"The complete source bundle could not be published atomically for "
            f"{target.meeting_date}: {exc}",
            "Stop before the paid call. Give the staging and source directory "
            "paths to a coding assistant; do not move files individually.",
        ) from exc
    return identity


def _build_system_prompt() -> str:
    prompt = _load_prompt("transcript_recap_system.txt")
    canonical = _load_canonical_names()
    if canonical:
        prompt += "\n\n---\n\nCANONICAL NAMES\n\n" + canonical
    prompt += """

---

BOUNDED REVIEW CANDIDATE RULES

This is a draft for independent source review, not a publication decision.
Use only the supplied official City of Richmond Granicus transcript. Omit any
name, affiliation, number, amount, date, vote, outcome, or attributed stance
that is not explicitly supported by the transcript. Prefer a later correction
over an earlier announcement. Count completed speaker turns, not registrations,
and keep totals, subsets, and separately reported series distinct. Do not infer
unanimity. If a public speaker's name or affiliation is unclear, use a role
description or omit it. Never repair ambiguity with outside knowledge.
"""
    return prompt.strip()


def _parse_recap_response(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _blocked(
            "DeepSeek returned malformed candidate JSON.",
            "Do not retry the paid call. Preserve the generated artifact and "
            "give it to a coding assistant for a bounded review decision.",
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {"transcript_recap"}:
        raise _blocked(
            "DeepSeek returned an unexpected candidate shape.",
            "Do not retry the paid call. Preserve the generated artifact and "
            "give it to a coding assistant.",
        )
    recap = payload.get("transcript_recap")
    if not isinstance(recap, str) or not recap.strip():
        raise _blocked(
            "DeepSeek returned an empty transcript recap.",
            "Do not retry the paid call; leave the cohort null.",
        )
    return recap.strip()


def _load_cost_receipt(conn: Any, meeting_date: str) -> dict[str, Any]:
    event_type = _event_type(meeting_date)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, model, caller, event_type, projected_cost,
                      actual_cost, status, created_at, settled_at, metadata
               FROM llm_cost_reservations
               WHERE event_type = %s
               ORDER BY created_at""",
            (event_type,),
        )
        reservations = cur.fetchall()
    if len(reservations) != 1:
        raise _blocked(
            f"Expected one cost reservation for {meeting_date}; found "
            f"{len(reservations)}.",
            "Do not retry or accept the candidate. Give the cost ledger state "
            "to a coding assistant.",
        )
    row = reservations[0]
    reservation = {
        "reservation_id": str(row[0]),
        "model": row[1],
        "caller": row[2],
        "event_type": row[3],
        "projected_cost": float(row[4]),
        "actual_cost": float(row[5]) if row[5] is not None else None,
        "status": row[6],
        "created_at": row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7]),
        "settled_at": row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8]),
        "metadata": row[9] if isinstance(row[9], dict) else {},
    }
    if (
        reservation["model"] != MODEL
        or reservation["caller"] != CALLER
        or reservation["event_type"] != event_type
        or reservation["status"] != "settled"
        or reservation["actual_cost"] is None
        or reservation["actual_cost"] > MAX_CALL_COST_USD
    ):
        raise _blocked(
            f"The cost receipt is not an exact settled DeepSeek Pro call under "
            f"${MAX_CALL_COST_USD:.2f} for {meeting_date}.",
            "Do not retry or accept the candidate. Give the receipt to a coding "
            "assistant.",
        )

    with conn.cursor() as cur:
        cur.execute(
            """SELECT id
               FROM pipeline_journal
               WHERE entry_type = 'api_cost'
                 AND metrics->>'reservation_id' = %s
                 AND target_artifact = %s""",
            (reservation["reservation_id"], CALLER),
        )
        journal_rows = cur.fetchall()
    if len(journal_rows) != 1:
        raise _blocked(
            f"The API cost journal is incomplete for {meeting_date}.",
            "Do not retry or accept the candidate. Give the reservation ID to "
            "a coding assistant.",
        )
    reservation["journal_id"] = str(journal_rows[0][0])
    return reservation


def _run_deepseek_candidate(
    target: RepairTarget,
    transcript: str,
    system_prompt: str,
) -> tuple[str, dict[str, Any]]:
    client = LLMClient(timeout=120.0)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_TRANSCRIPT_RECAP,
        temperature=0,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": (
                "Write a source-review candidate recap from this official City "
                "of Richmond Granicus transcript for the regular City Council "
                f"meeting on {target.meeting_date}. Return only the required "
                f"JSON object.\n\nTRANSCRIPT:\n{transcript}"
            ),
        }],
    )
    raw_text = response.content[0].text
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_read_input_tokens": response.usage.cache_read_input_tokens,
        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
        "provider_model": response.model,
    }
    return raw_text, usage


def generate_candidate(meeting_date: str) -> Path:
    target = TARGETS.get(meeting_date)
    if target is None:
        raise _blocked(
            f"{meeting_date} is outside the three-date V2 allowlist.",
            "Use exactly 2026-07-07, 2026-07-21, or 2026-07-28. Do not expand "
            "the repair scope.",
        )
    candidate_path = _candidate_path(meeting_date)
    failed_attempt_path = _failed_attempt_path(meeting_date)
    if candidate_path.exists() or failed_attempt_path.exists():
        raise _blocked(
            f"A V2 candidate or failed-attempt artifact already exists for "
            f"{meeting_date}.",
            "Do not overwrite or regenerate it. Continue to independent source "
            "review only for a valid candidate; otherwise leave the cohort null.",
        )
    _configure_cost_guards(meeting_date)

    conn = get_connection()
    try:
        # Keep one bounded transaction open so the advisory lock survives the
        # source fetch, paid call, ledger verification, and artifact write even
        # when DATABASE_URL uses a transaction-pooling endpoint. This connection
        # performs read-only queries; the provider's cost writes use separate
        # connections and remain visible under PostgreSQL READ COMMITTED.
        _acquire_generation_lock(conn, meeting_date)
        _validate_cohort_null(_load_cohort_rows(conn))
        _assert_no_paid_attempt(conn, meeting_date)
        source = _fetch_or_validate_source(target)
        _, transcript_path, _ = _source_paths(target.meeting_date)
        transcript_bytes = transcript_path.read_bytes()
        if _sha256_bytes(transcript_bytes) != source.get("transcript_sha256"):
            raise _blocked(
                f"The prompt transcript hash changed for {target.meeting_date}.",
                "Stop before the paid call and have a coding assistant inspect "
                "the fixed V2 source path.",
            )
        transcript = transcript_bytes.decode("utf-8")
        system_prompt = _build_system_prompt()

        raw_response, usage = _run_deepseek_candidate(
            target, transcript, system_prompt
        )

        postflight_error: RepairBlocked | None = None
        cost: dict[str, Any] | None = None
        try:
            _validate_cohort_null(_load_cohort_rows(conn))
            cost = _load_cost_receipt(conn, meeting_date)
        except RepairBlocked as exc:
            postflight_error = exc

        try:
            recap = _parse_recap_response(raw_response)
        except RepairBlocked as exc:
            postflight_error = postflight_error or exc

        if postflight_error is not None or cost is None:
            failure_payload = {
                "schema_version": SCHEMA_VERSION,
                "approval_id": APPROVAL_ID,
                "generation_status": "failed",
                "target": asdict(target),
                "source": source,
                "model_requested": MODEL,
                "prompt_sha256": _sha256_text(system_prompt),
                "recorded_at": _utc_now(),
                "usage": usage,
                "cost": cost,
                "raw_response": raw_response,
                "raw_response_sha256": _sha256_text(raw_response),
                "failure": str(postflight_error),
            }
            _write_new_json(failed_attempt_path, failure_payload)
            raise postflight_error

        generated_at = _utc_now()
        provenance = {
            "kind": "meeting_recording",
            "channel": "granicus",
            "as_of": generated_at,
            "generator": GENERATOR,
        }
        payload = {
            "schema_version": SCHEMA_VERSION,
            "approval_id": APPROVAL_ID,
            "generation_status": "candidate",
            "target": asdict(target),
            "source": source,
            "model_requested": MODEL,
            "prompt_sha256": _sha256_text(system_prompt),
            "generated_at": generated_at,
            "usage": usage,
            "cost": cost,
            "raw_response_sha256": _sha256_text(raw_response),
            "recap_sha256": _sha256_text(recap),
            "recap_fields": {
                "transcript_recap": recap,
                "transcript_recap_source": "granicus",
                "transcript_recap_provenance": provenance,
                "transcript_recap_generated_at": generated_at,
            },
        }
        _write_new_json(candidate_path, payload)
        return candidate_path
    finally:
        # Rollback releases the transaction-level generation lock. The control
        # transaction performs no writes, so there is nothing to preserve.
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


def _validate_candidate(target: RepairTarget, path: Path) -> tuple[dict[str, Any], str]:
    candidate, raw_bytes = _read_json_snapshot(path)
    candidate_sha = _sha256_bytes(raw_bytes)
    exact_target = asdict(target)
    if (
        candidate.get("schema_version") != SCHEMA_VERSION
        or candidate.get("approval_id") != APPROVAL_ID
        or candidate.get("generation_status") != "candidate"
        or candidate.get("target") != exact_target
        or candidate.get("model_requested") != MODEL
    ):
        raise _blocked(
            f"Candidate identity or model mismatch for {target.meeting_date}.",
            "Do not edit or publish the candidate. Give it to a coding assistant.",
        )
    generated_at = candidate.get("generated_at")
    try:
        parsed_generated_at = datetime.fromisoformat(str(generated_at))
    except ValueError as exc:
        raise _blocked(
            f"Candidate generation time is invalid for {target.meeting_date}.",
            "Do not publish or edit the candidate.",
        ) from exc
    if parsed_generated_at.tzinfo is None:
        raise _blocked(
            f"Candidate generation time lacks a timezone for {target.meeting_date}.",
            "Do not publish or edit the candidate.",
        )
    prompt_sha = candidate.get("prompt_sha256")
    if not isinstance(prompt_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", prompt_sha):
        raise _blocked(
            f"Candidate prompt hash is invalid for {target.meeting_date}.",
            "Do not publish or edit the candidate.",
        )
    _validate_candidate_cost(target, candidate.get("cost"))
    fields = candidate.get("recap_fields")
    if not isinstance(fields, dict) or set(fields) != set(RECAP_FIELDS):
        raise _blocked(
            f"Candidate has an invalid field set for {target.meeting_date}.",
            "Do not publish it. Only the four approved transcript-recap fields "
            "are allowed.",
        )
    recap = fields.get("transcript_recap")
    provenance = fields.get("transcript_recap_provenance")
    if (
        not isinstance(recap, str)
        or not recap.strip()
        or candidate.get("recap_sha256") != _sha256_text(recap)
        or fields.get("transcript_recap_source") != "granicus"
        or fields.get("transcript_recap_generated_at") != candidate.get("generated_at")
        or not isinstance(provenance, dict)
        or provenance != {
            "kind": "meeting_recording",
            "channel": "granicus",
            "as_of": candidate.get("generated_at"),
            "generator": GENERATOR,
        }
    ):
        raise _blocked(
            f"Candidate recap or provenance integrity failed for {target.meeting_date}.",
            "Do not repair the artifact in place or publish it.",
        )

    source = candidate.get("source")
    if not isinstance(source, dict):
        raise _blocked(
            f"Candidate source metadata is missing for {target.meeting_date}.",
            "Do not publish it.",
        )
    current_source = _validate_existing_source(target)
    if current_source is None or source != current_source:
        raise _blocked(
            f"Candidate source evidence changed for {target.meeting_date}.",
            "Do not publish it; have a coding assistant inspect the hashes.",
        )
    return candidate, candidate_sha


def _validate_candidate_cost(target: RepairTarget, cost: Any) -> None:
    if not isinstance(cost, dict):
        raise _blocked(
            f"Candidate cost evidence is missing for {target.meeting_date}.",
            "Do not publish the candidate or pass malformed values to PostgreSQL.",
        )
    try:
        reservation_id = str(uuid.UUID(str(cost.get("reservation_id"))))
        journal_id = str(uuid.UUID(str(cost.get("journal_id"))))
        projected_cost = float(cost.get("projected_cost"))
        actual_cost = float(cost.get("actual_cost"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise _blocked(
            f"Candidate cost evidence is malformed for {target.meeting_date}.",
            "Do not publish or edit it. Give the candidate to a coding assistant.",
        ) from exc
    if (
        cost.get("reservation_id") != reservation_id
        or cost.get("journal_id") != journal_id
        or cost.get("model") != MODEL
        or cost.get("caller") != CALLER
        or cost.get("event_type") != _event_type(target.meeting_date)
        or cost.get("status") != "settled"
        or not math.isfinite(projected_cost)
        or not math.isfinite(actual_cost)
        or projected_cost < 0
        or actual_cost < 0
        or projected_cost > MAX_CALL_COST_USD
        or actual_cost > MAX_CALL_COST_USD
        or actual_cost > projected_cost
    ):
        raise _blocked(
            f"Candidate cost evidence violates the approved rails for "
            f"{target.meeting_date}.",
            "Do not publish or edit it. Give the candidate and cost receipt to "
            "a coding assistant.",
        )


def _validate_review(
    target: RepairTarget,
    review_path: Path,
    candidate: dict[str, Any],
    candidate_sha: str,
) -> tuple[dict[str, Any], str]:
    review, review_bytes = _read_json_snapshot(review_path)
    source = candidate["source"]
    if (
        review.get("schema_version") != SCHEMA_VERSION
        or review.get("approval_id") != APPROVAL_ID
        or review.get("meeting_date") != target.meeting_date
        or review.get("meeting_id") != target.meeting_id
        or review.get("candidate_sha256") != candidate_sha
        or review.get("recap_sha256") != candidate.get("recap_sha256")
        or review.get("transcript_sha256") != source.get("transcript_sha256")
        or review.get("pdf_sha256") != source.get("pdf_sha256")
        or review.get("decision") != "pass"
    ):
        raise _blocked(
            f"Independent review did not approve the exact candidate and "
            f"source hashes for {target.meeting_date}.",
            "Leave all three rows null. Do not edit a failed review into a pass.",
        )
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or reviewer == GENERATOR:
        raise _blocked(
            f"Independent reviewer identity is missing for {target.meeting_date}.",
            "Have a separate reviewer audit the official source; do not self-attest.",
        )
    reviewed_at = review.get("reviewed_at")
    try:
        parsed_reviewed_at = datetime.fromisoformat(str(reviewed_at))
    except ValueError as exc:
        raise _blocked(
            f"Independent review time is invalid for {target.meeting_date}.",
            "Have the independent reviewer create a complete review receipt.",
        ) from exc
    if parsed_reviewed_at.tzinfo is None:
        raise _blocked(
            f"Independent review time lacks a timezone for {target.meeting_date}.",
            "Have the independent reviewer create a complete review receipt.",
        )
    checks = review.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(REVIEW_CHECKS):
        raise _blocked(
            f"Independent review checks are incomplete for {target.meeting_date}.",
            "Complete the claim-level source review; do not publish a partial audit.",
        )
    if any(checks[name] is not True for name in REVIEW_CHECKS):
        raise _blocked(
            f"Independent review contains a failed check for {target.meeting_date}.",
            "Leave all three rows null. This approval does not permit regeneration.",
        )
    claims = review.get("claims")
    if not isinstance(claims, list) or not claims:
        raise _blocked(
            f"Claim-level evidence is missing for {target.meeting_date}.",
            "Audit every material recap claim against timestamped transcript evidence.",
        )
    for claim in claims:
        if (
            not isinstance(claim, dict)
            or not isinstance(claim.get("claim"), str)
            or claim.get("supported") is not True
            or not isinstance(claim.get("evidence"), list)
            or not claim["evidence"]
            or any(
                not isinstance(item, dict)
                or not isinstance(item.get("timestamp"), str)
                or not item["timestamp"].strip()
                or not isinstance(item.get("note"), str)
                or not item["note"].strip()
                for item in claim["evidence"]
            )
        ):
            raise _blocked(
                f"A claim lacks affirmative timestamped evidence for "
                f"{target.meeting_date}.",
                "Leave all three rows null; do not fix or reinterpret claims while applying.",
            )
    return review, _sha256_bytes(review_bytes)


def _validate_cost_receipt_against_db(conn: Any, candidate: dict[str, Any]) -> None:
    target = candidate["target"]
    cost = candidate.get("cost")
    if not isinstance(cost, dict):
        raise _blocked(
            f"Candidate cost receipt is missing for {target['meeting_date']}.",
            "Do not publish it.",
        )
    with conn.cursor() as cur:
        cur.execute(
            """SELECT model, caller, event_type, projected_cost, actual_cost, status
               FROM llm_cost_reservations
               WHERE id = %s
               FOR SHARE""",
            (cost.get("reservation_id"),),
        )
        row = cur.fetchone()
    expected_event = _event_type(target["meeting_date"])
    try:
        cost_matches = bool(
            row is not None
            and row[0] == MODEL
            and row[1] == CALLER
            and row[2] == expected_event
            and float(row[3]) == float(cost.get("projected_cost"))
            and float(row[4]) == float(cost.get("actual_cost"))
            and row[5] == "settled"
            and float(row[4]) <= MAX_CALL_COST_USD
        )
    except (TypeError, ValueError):
        cost_matches = False
    if not cost_matches:
        raise _blocked(
            f"The durable cost receipt changed for {target['meeting_date']}.",
            "Do not publish or retry. Give the reservation ID to a coding assistant.",
        )
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id
               FROM pipeline_journal
               WHERE id = %s
                 AND entry_type = 'api_cost'
                 AND target_artifact = %s
                 AND metrics->>'reservation_id' = %s
               FOR SHARE""",
            (
                cost["journal_id"],
                CALLER,
                cost["reservation_id"],
            ),
        )
        journal_row = cur.fetchone()
    if journal_row is None or str(journal_row[0]) != cost["journal_id"]:
        raise _blocked(
            f"The durable API cost journal changed for {target['meeting_date']}.",
            "Do not publish or retry. Give the journal and reservation IDs to a "
            "coding assistant.",
        )


def apply_reviewed() -> list[str]:
    if (ARTIFACT_DIR / "applied.json").exists():
        raise _blocked(
            "The cohort already has a local application receipt.",
            "Do not replay the repair. Run the read-only status check and give "
            "any mismatch to a coding assistant.",
        )
    candidates: dict[str, dict[str, Any]] = {}
    reviews: dict[str, dict[str, Any]] = {}
    candidate_hashes: dict[str, str] = {}
    review_hashes: dict[str, str] = {}
    for meeting_date, target in TARGETS.items():
        candidate, candidate_sha = _validate_candidate(
            target, _candidate_path(meeting_date)
        )
        review, review_sha = _validate_review(
            target,
            _review_path(meeting_date),
            candidate,
            candidate_sha,
        )
        candidates[meeting_date] = candidate
        reviews[meeting_date] = review
        candidate_hashes[meeting_date] = candidate_sha
        review_hashes[meeting_date] = review_sha

    conn = get_connection()
    updated_ids: list[str] = []
    try:
        _validate_cohort_null(_load_cohort_rows(conn, for_update=True))
        for candidate in candidates.values():
            _validate_cost_receipt_against_db(conn, candidate)

        with conn.cursor() as cur:
            for meeting_date, target in TARGETS.items():
                fields = candidates[meeting_date]["recap_fields"]
                cur.execute(
                    """UPDATE meetings
                       SET transcript_recap = %s,
                           transcript_recap_source = %s,
                           transcript_recap_provenance = %s::jsonb,
                           transcript_recap_generated_at = %s
                       WHERE id = %s
                         AND city_fips = %s
                         AND meeting_date = %s
                         AND meeting_type = %s
                         AND body_id = %s
                         AND transcript_recap IS NULL
                         AND transcript_recap_source IS NULL
                         AND transcript_recap_provenance IS NULL
                         AND transcript_recap_generated_at IS NULL
                       RETURNING id""",
                    (
                        fields["transcript_recap"],
                        fields["transcript_recap_source"],
                        json.dumps(fields["transcript_recap_provenance"]),
                        fields["transcript_recap_generated_at"],
                        target.meeting_id,
                        CITY_FIPS,
                        target.meeting_date,
                        MEETING_TYPE,
                        BODY_ID,
                    ),
                )
                returned = cur.fetchone()
                if returned is None or str(returned[0]) != target.meeting_id:
                    raise _blocked(
                        f"The all-null compare-and-swap failed for {meeting_date}.",
                        "The transaction was rolled back. Do not retry or apply "
                        "rows individually; inspect the exact cohort state.",
                    )
                updated_ids.append(str(returned[0]))
        if set(updated_ids) != {target.meeting_id for target in TARGETS.values()}:
            raise _blocked(
                "The transaction did not update the exact three-row cohort.",
                "The transaction was rolled back. Do not retry or compensate.",
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "approval_id": APPROVAL_ID,
        "applied_at": _utc_now(),
        "meeting_ids": updated_ids,
        "candidate_sha256": candidate_hashes,
        "review_sha256": review_hashes,
    }
    _write_new_json(ARTIFACT_DIR / "applied.json", receipt)
    return updated_ids


def cohort_status() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = _load_cohort_rows(conn)
    finally:
        conn.close()
    return rows


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review-gated repair for the exact July 2026 recap cohort."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Read-only exact cohort status")
    generate = subparsers.add_parser(
        "generate", help="Generate one local candidate without publishing"
    )
    generate.add_argument("--meeting-date", required=True, choices=tuple(TARGETS))
    subparsers.add_parser(
        "apply-reviewed",
        help="Atomically publish all three only after all independent reviews pass",
    )
    args = parser.parse_args()

    try:
        if args.command == "status":
            print(json.dumps(cohort_status(), indent=2, default=_json_default))
        elif args.command == "generate":
            path = generate_candidate(args.meeting_date)
            print(f"Candidate written without publication: {path}")
            print(
                "ACTION: Independently audit every claim against the exact "
                "official transcript and create the hash-bound review receipt."
            )
        else:
            updated = apply_reviewed()
            print(f"Applied exact reviewed cohort: {', '.join(updated)}")
            print("ACTION: No operator action is needed; run the read-only status check.")
    except RepairBlocked as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"ERROR: Unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "ACTION: Stop. Do not retry a paid call or force an apply. Give this "
            "complete error to a coding assistant with the Richmond Commons "
            "repository context.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
