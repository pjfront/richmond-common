"""
Richmond Common — Cloud Pipeline

Supabase-native pipeline orchestrator for cloud execution.
Replaces run_pipeline.py for production use in GitHub Actions.

Key differences from run_pipeline.py:
  - No local file I/O — all data flows through Supabase
  - Creates scan_runs rows for full audit trail
  - Supports prospective/retrospective scan modes
  - Logs to data_sync_log for observability
  - Stores audit sidecars in scan_runs.metadata (not disk)

Usage (GitHub Actions or manual):
  python cloud_pipeline.py --date 2026-03-03
  python cloud_pipeline.py --date 2026-03-03 --scan-mode retrospective
  python cloud_pipeline.py --date 2026-03-03 --triggered-by n8n
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path

from city_config import get_city_config, list_configured_cities
from db import (
    get_connection,
    load_meeting_to_db,
    create_scan_run,
    complete_scan_run,
    fail_scan_run,
    create_sync_log,
    complete_sync_log,
    ingest_document,
    save_conflict_flag,
    supersede_flags_for_meeting,
)

from pipeline_journal import PipelineJournal, check_anomalies

DEFAULT_FIPS = "0660620"  # Richmond — keep as CLI default for backward compat
from escribemeetings_scraper import (
    create_session,
    discover_meetings,
    find_meeting_by_date,
    scrape_meeting,
)
from conflict_scanner import scan_meeting_json
from comment_generator import (
    generate_comment_from_scan,
    detect_missing_documents,
)
from escribemeetings_enricher import enrich_meeting_data
from run_pipeline import convert_escribemeetings_to_scanner_format
from generate_summaries import (
    get_items_needing_summaries,
    generate_summary_for_item,
)
from generate_vote_explainers import (
    get_motions_needing_explainers,
    generate_explainer_for_motion,
)


def _get_scanner_version() -> str:
    """Get the current git SHA for scanner versioning."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _load_contributions_from_db(conn, city_fips: str, cutoff_date: date = None) -> list[dict]:
    """Load contributions from Supabase in conflict-scanner-compatible format.

    If cutoff_date is set (prospective mode), only returns contributions
    filed on or before that date.
    """
    query = """
        SELECT d.name AS contributor_name,
               d.employer AS contributor_employer,
               c.amount,
               c.contribution_date,
               cm.name AS committee,
               c.source
        FROM contributions c
        JOIN donors d ON c.donor_id = d.id
        JOIN committees cm ON c.committee_id = cm.id
        WHERE c.city_fips = %s
    """
    params: list = [city_fips]

    if cutoff_date:
        query += " AND c.contribution_date <= %s"
        params.append(cutoff_date)

    with conn.cursor() as cur:
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    contributions = []
    for row in rows:
        record = dict(zip(columns, row))
        # Format for conflict scanner compatibility
        record["date"] = str(record.pop("contribution_date", ""))
        record["amount"] = float(record["amount"])
        contributions.append(record)

    return contributions


def _contribution_source_counts(contributions: list[dict]) -> dict:
    """Count contributions by source for scan_runs metadata."""
    counts: dict[str, int] = {}
    for c in contributions:
        source = c.get("source", "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _store_raw_escribemeetings(
    conn, city_fips: str, meeting_date: str, escribemeetings_data: dict
) -> uuid.UUID:
    """Store raw eSCRIBE scrape data in Layer 1 documents table."""
    raw_bytes = json.dumps(escribemeetings_data, indent=2).encode("utf-8")
    doc_id = ingest_document(
        conn,
        city_fips=city_fips,
        source_type="escribemeetings",
        raw_content=raw_bytes,
        credibility_tier=1,
        source_url=escribemeetings_data.get("meeting_url"),
        source_identifier=f"escribemeetings_{meeting_date}",
        mime_type="application/json",
        raw_text=None,
        metadata={
            "meeting_date": meeting_date,
            "meeting_name": escribemeetings_data.get("meeting_name"),
            "item_count": len(escribemeetings_data.get("items", [])),
            "pipeline": "cloud",
        },
    )
    return doc_id


def _store_generated_comment(
    conn, city_fips: str, meeting_date: str, comment_text: str, scan_run_id: uuid.UUID
) -> uuid.UUID:
    """Store generated comment in Layer 1 documents table."""
    raw_bytes = comment_text.encode("utf-8")
    doc_id = ingest_document(
        conn,
        city_fips=city_fips,
        source_type="generated_comment",
        raw_content=raw_bytes,
        credibility_tier=1,
        source_identifier=f"comment_{meeting_date}_{scan_run_id}",
        mime_type="text/plain",
        raw_text=comment_text,
        metadata={
            "meeting_date": meeting_date,
            "scan_run_id": str(scan_run_id),
            "pipeline": "cloud",
        },
    )
    return doc_id


def _generate_meeting_summaries(
    conn, meeting_id: uuid.UUID, city_fips: str
) -> dict:
    """Generate plain language summaries for a meeting's agenda items.

    Non-critical: returns stats dict, never raises.
    """
    try:
        items = get_items_needing_summaries(
            conn, city_fips, meeting_id=str(meeting_id)
        )
        if not items:
            return {"generated": 0, "skipped": 0, "errors": 0, "total": 0}

        generated = 0
        skipped = 0
        errors = 0
        for item in items:
            try:
                result = generate_summary_for_item(conn, item)
                if result["skipped"]:
                    skipped += 1
                else:
                    generated += 1
                    time.sleep(0.3)  # Rate limit API calls
            except Exception as e:
                errors += 1
                print(f"    Summary error for {item.get('title', 'unknown')[:50]}: {e}")

        return {
            "generated": generated,
            "skipped": skipped,
            "errors": errors,
            "total": len(items),
        }
    except Exception as e:
        print(f"    Summary generation failed: {e}")
        return {"generated": 0, "skipped": 0, "errors": 1, "total": 0, "error": str(e)}


def _generate_meeting_explainers(
    conn, meeting_id: uuid.UUID, city_fips: str
) -> dict:
    """Generate vote explainers for a meeting's motions.

    Non-critical: returns stats dict, never raises.
    """
    try:
        motions = get_motions_needing_explainers(
            conn, city_fips, meeting_id=str(meeting_id)
        )
        if not motions:
            return {"generated": 0, "skipped": 0, "errors": 0, "total": 0}

        generated = 0
        skipped = 0
        errors = 0
        for motion in motions:
            try:
                result = generate_explainer_for_motion(conn, motion)
                if result["skipped"]:
                    skipped += 1
                else:
                    generated += 1
                    time.sleep(0.3)  # Rate limit API calls
            except Exception as e:
                errors += 1
                title = motion.get("item_title", "unknown")[:50]
                print(f"    Explainer error for {title}: {e}")

        return {
            "generated": generated,
            "skipped": skipped,
            "errors": errors,
            "total": len(motions),
        }
    except Exception as e:
        print(f"    Explainer generation failed: {e}")
        return {"generated": 0, "skipped": 0, "errors": 1, "total": 0, "error": str(e)}


def run_cloud_pipeline(
    date_str: str,
    scan_mode: str = "prospective",
    triggered_by: str = "manual",
    city_fips: str = DEFAULT_FIPS,
    pipeline_run_id: str = None,
    dry_run: bool = True,
    skip_generators: bool = False,
) -> dict:
    """Run the full cloud pipeline for a meeting date.

    Args:
        date_str: Meeting date YYYY-MM-DD
        scan_mode: 'prospective' (pre-meeting, date-filtered) or 'retrospective' (all data)
        triggered_by: 'scheduled', 'manual', 'n8n', 'reanalysis'
        city_fips: City FIPS code
        pipeline_run_id: GitHub Actions run ID or n8n execution ID
        dry_run: If True, don't email comment
        skip_generators: If True, skip summary and explainer generation (saves API cost)

    Returns:
        Summary dict with scan results and metadata
    """
    # Validate city is configured
    city_cfg = get_city_config(city_fips)

    start_time = time.time()
    conn = get_connection()
    scanner_version = _get_scanner_version()

    # Determine data cutoff for prospective mode
    data_cutoff = None
    if scan_mode == "prospective":
        data_cutoff = datetime.strptime(date_str, "%Y-%m-%d").date()

    print(f"\n{'='*60}")
    print(f"Transparency Project — Cloud Pipeline ({city_cfg['name']})")
    print(f"Meeting date: {date_str}")
    print(f"Scan mode:    {scan_mode}")
    print(f"Triggered by: {triggered_by}")
    print(f"{'='*60}\n")

    # ── Create scan run record ──────────────────────────────
    scan_run_id = create_scan_run(
        conn,
        city_fips=city_fips,
        scan_mode=scan_mode,
        data_cutoff_date=data_cutoff,
        triggered_by=triggered_by,
        pipeline_run_id=pipeline_run_id,
        scanner_version=scanner_version,
    )
    print(f"Scan run: {scan_run_id}")

    try:
        journal = PipelineJournal(conn, city_fips)
        journal.log_run_start("cloud_pipeline", str(scan_run_id),
            f"Pipeline for {date_str} ({scan_mode}, triggered by {triggered_by})",
            {"scan_mode": scan_mode, "triggered_by": triggered_by,
             "scanner_version": scanner_version, "pipeline_run_id": pipeline_run_id})

        # ── Step 1: Scrape eSCRIBE ──────────────────────────
        print("Step 1: Scraping eSCRIBE for meeting agenda packet...")
        step_start = time.time()
        session = create_session()
        meetings = discover_meetings(session)
        meeting = find_meeting_by_date(meetings, date_str)

        if not meeting:
            raise ValueError(f"No meeting found for {date_str}")

        escribemeetings_data = scrape_meeting(session, meeting)
        item_count = len(escribemeetings_data.get('items', []))
        step_seconds = round(time.time() - step_start, 2)
        print(f"  Found {item_count} items")

        # Store raw data in Supabase Layer 1
        doc_id = _store_raw_escribemeetings(conn, city_fips, date_str, escribemeetings_data)
        print(f"  Stored raw eSCRIBE data -> document {doc_id}")

        journal.log_step("scrape_escribemeetings", f"Scraped {item_count} agenda items", {
            "items_found": item_count, "meetings_discovered": len(meetings),
            "execution_seconds": step_seconds,
        })
        check_anomalies(journal, conn, city_fips, "scrape_escribemeetings",
                        current_count=item_count, current_seconds=step_seconds)

        # ── Step 2: Convert to scanner format ────────────────
        print("Step 2: Converting eSCRIBE data to scanner format...")
        step_start = time.time()
        meeting_data = convert_escribemeetings_to_scanner_format(escribemeetings_data)

        consent_count = len(meeting_data["consent_calendar"]["items"])
        action_count = len(meeting_data["action_items"])
        housing_count = len(meeting_data["housing_authority_items"])
        total_items = consent_count + action_count + housing_count
        print(f"  Items: {consent_count} consent, {action_count} action, {housing_count} housing")

        journal.log_step("convert_format", f"Converted to {total_items} scanner items", {
            "consent_count": consent_count, "action_count": action_count,
            "housing_count": housing_count, "total_items": total_items,
            "execution_seconds": round(time.time() - step_start, 2),
        })

        # ── Step 3: Enrich with attachment text ──────────────
        print("Step 3: Enriching with staff report text...")
        step_start = time.time()
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(escribemeetings_data, tmp, indent=2)
            tmp_path = tmp.name
        meeting_data, enriched_items = enrich_meeting_data(meeting_data, tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
        print(f"  Enriched {len(enriched_items)} items with attachment text")

        journal.log_step("enrich_attachments", f"Enriched {len(enriched_items)} items with attachment text", {
            "enriched_count": len(enriched_items),
            "execution_seconds": round(time.time() - step_start, 2),
        })

        # ── Step 4: Load contributions from Supabase ─────────
        print(f"Step 4: Loading contributions from database (cutoff={data_cutoff})...")
        step_start = time.time()
        contributions = _load_contributions_from_db(conn, city_fips, data_cutoff)
        source_counts = _contribution_source_counts(contributions)
        print(f"  Loaded {len(contributions):,} contributions {source_counts}")

        # If no contributions in DB, fall back to local file (transitional)
        used_fallback = False
        if not contributions:
            local_path = Path(__file__).parent / "data" / "combined_contributions.json"
            if local_path.exists():
                print(f"  WARNING: No contributions in DB, falling back to {local_path}")
                with open(local_path) as f:
                    contributions = json.load(f)
                source_counts = {"local_file": len(contributions)}
                used_fallback = True
                print(f"  Loaded {len(contributions):,} from local fallback")

        # Update scan run with contribution counts
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE scan_runs
                   SET contributions_count = %s, contributions_sources = %s
                   WHERE id = %s""",
                (len(contributions), json.dumps(source_counts), scan_run_id),
            )
        conn.commit()

        journal.log_step("load_contributions", f"Loaded {len(contributions):,} contributions", {
            "contribution_count": len(contributions),
            "source_counts": source_counts,
            "used_fallback": used_fallback,
            "execution_seconds": round(time.time() - step_start, 2),
        })
        check_anomalies(journal, conn, city_fips, "load_contributions",
                        current_count=len(contributions),
                        current_seconds=round(time.time() - step_start, 2),
                        count_metric_key="contribution_count")

        # ── Step 5: Conflict scan ────────────────────────────
        print("Step 5: Scanning for conflicts...")
        step_start = time.time()
        scan_result = scan_meeting_json(meeting_data, contributions, [], independent_expenditures=[])
        scan_result.enriched_items = enriched_items

        tier1 = sum(1 for f in scan_result.flags if f.publication_tier == 1)
        tier2 = sum(1 for f in scan_result.flags if f.publication_tier == 2)
        tier3 = sum(1 for f in scan_result.flags if f.publication_tier == 3)
        print(f"  Flags: {tier1} Tier1, {tier2} Tier2, {tier3} Tier3")
        print(f"  Clean items: {len(scan_result.clean_items)}")

        journal.log_step("conflict_scan", f"Found {len(scan_result.flags)} flags, {len(scan_result.clean_items)} clean", {
            "total_flags": len(scan_result.flags),
            "tier1": tier1, "tier2": tier2, "tier3": tier3,
            "clean_items": len(scan_result.clean_items),
            "execution_seconds": round(time.time() - step_start, 2),
        })
        check_anomalies(journal, conn, city_fips, "conflict_scan",
                        current_count=len(scan_result.flags),
                        current_seconds=round(time.time() - step_start, 2),
                        count_metric_key="total_flags")

        # ── Step 6: Load meeting to Layer 2 ──────────────────
        print("Step 6: Loading meeting data into database...")
        step_start = time.time()
        meeting_id = load_meeting_to_db(conn, meeting_data, document_id=doc_id, city_fips=city_fips)
        print(f"  Meeting loaded -> {meeting_id}")

        # Link scan run to meeting
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scan_runs SET meeting_id = %s WHERE id = %s",
                (meeting_id, scan_run_id),
            )
        conn.commit()

        # Supersede old flags from same scan mode
        superseded = supersede_flags_for_meeting(conn, meeting_id, scan_run_id, scan_mode)
        if superseded:
            print(f"  Superseded {superseded} previous {scan_mode} flags")

        # Save flags to database
        for flag in scan_result.flags:
            # Evidence: use the flag's own evidence list (list[str] from v3 scanner),
            # wrapped as {"text": ...} dicts for JSONB storage
            evidence_json = [{"text": e} for e in flag.evidence] if flag.evidence else []
            save_conflict_flag(
                conn,
                city_fips=city_fips,
                meeting_id=meeting_id,
                scan_run_id=scan_run_id,
                flag_type=flag.flag_type,
                description=flag.description,
                evidence=evidence_json,
                confidence=flag.confidence,
                scan_mode=scan_mode,
                data_cutoff_date=data_cutoff,
                legal_reference=flag.legal_reference,
                publication_tier=flag.publication_tier,
                confidence_factors=flag.confidence_factors,
                scanner_version=flag.scanner_version,
            )

        journal.log_step("load_meeting_db", f"Loaded meeting {meeting_id}, saved {len(scan_result.flags)} flags", {
            "meeting_id": str(meeting_id),
            "flags_saved": len(scan_result.flags),
            "superseded": superseded,
            "execution_seconds": round(time.time() - step_start, 2),
        })

        # ── Step 8: Generate plain language summaries ────────
        summary_stats = {"generated": 0, "skipped": 0, "errors": 0, "total": 0}
        explainer_stats = {"generated": 0, "skipped": 0, "errors": 0, "total": 0}

        if skip_generators:
            print("Step 8: Skipping summary generation (--skip-generators)")
            print("Step 9: Skipping explainer generation (--skip-generators)")
            journal.log_step("generate_summaries", "Skipped (--skip-generators)", {
                "skipped": True, "execution_seconds": 0,
            })
            journal.log_step("generate_explainers", "Skipped (--skip-generators)", {
                "skipped": True, "execution_seconds": 0,
            })
        else:
            print("Step 8: Generating plain language summaries...")
            step_start = time.time()
            summary_stats = _generate_meeting_summaries(conn, meeting_id, city_fips)
            print(f"  Summaries: {summary_stats['generated']} generated, "
                  f"{summary_stats['skipped']} skipped, {summary_stats['errors']} errors")

            journal.log_step("generate_summaries", f"Generated {summary_stats['generated']} summaries", {
                **summary_stats,
                "execution_seconds": round(time.time() - step_start, 2),
            })

            # ── Step 9: Generate vote explainers ──────────────────
            print("Step 9: Generating vote explainers...")
            step_start = time.time()
            explainer_stats = _generate_meeting_explainers(conn, meeting_id, city_fips)
            print(f"  Explainers: {explainer_stats['generated']} generated, "
                  f"{explainer_stats['skipped']} skipped, {explainer_stats['errors']} errors")

            journal.log_step("generate_explainers", f"Generated {explainer_stats['generated']} explainers", {
                **explainer_stats,
                "execution_seconds": round(time.time() - step_start, 2),
            })

        # ── Step 10: Generate comment ────────────────────────
        print("Step 10: Generating public comment...")
        step_start = time.time()
        missing_docs = detect_missing_documents(meeting_data)
        contribution_count = f"{len(contributions):,}" if contributions else "0"
        comment = generate_comment_from_scan(scan_result, missing_docs, contribution_count)

        # Store comment in Layer 1
        comment_doc_id = _store_generated_comment(conn, city_fips, date_str, comment, scan_run_id)
        print(f"  Comment stored -> document {comment_doc_id}")

        submitted = False
        if not dry_run:
            print("  Sending comment to city clerk...")
            from comment_generator import submit_comment_to_clerk
            submit_comment_to_clerk(comment, date_str, dry_run=False)
            submitted = True

        journal.log_step("generate_comment", f"Comment generated and stored -> {comment_doc_id}", {
            "comment_doc_id": str(comment_doc_id),
            "missing_docs": len(missing_docs),
            "submitted": submitted,
            "dry_run": dry_run,
            "execution_seconds": round(time.time() - step_start, 2),
        })

        # ── Complete scan run ────────────────────────────────
        execution_time = time.time() - start_time
        audit_metadata = {}
        if hasattr(scan_result, "audit_log") and scan_result.audit_log:
            audit_metadata = scan_result.audit_log.to_dict() if hasattr(scan_result.audit_log, "to_dict") else {}

        complete_scan_run(
            conn,
            scan_run_id=scan_run_id,
            flags_found=len(scan_result.flags),
            flags_by_tier={"tier1": tier1, "tier2": tier2, "tier3": tier3},
            clean_items_count=len(scan_result.clean_items),
            enriched_items_count=len(enriched_items),
            execution_time_seconds=round(execution_time, 2),
            metadata=audit_metadata,
        )

        summary = {
            "scan_run_id": str(scan_run_id),
            "meeting_id": str(meeting_id),
            "meeting_date": date_str,
            "scan_mode": scan_mode,
            "flags": {"tier1": tier1, "tier2": tier2, "tier3": tier3, "total": len(scan_result.flags)},
            "clean_items": len(scan_result.clean_items),
            "enriched_items": len(enriched_items),
            "contributions_scanned": len(contributions),
            "summaries": summary_stats,
            "explainers": explainer_stats,
            "execution_seconds": round(execution_time, 2),
            "status": "completed",
        }

        journal.log_run_end("cloud_pipeline", str(scan_run_id), "completed",
            f"Pipeline complete for {date_str} in {execution_time:.1f}s", {
                "total_flags": len(scan_result.flags),
                "tier1": tier1, "tier2": tier2, "tier3": tier3,
                "clean_items": len(scan_result.clean_items),
                "summaries_generated": summary_stats["generated"],
                "explainers_generated": explainer_stats["generated"],
                "temporal_flags": 0,  # temporal now integrated into v3 signal detectors
                "execution_seconds": round(execution_time, 2),
            })

        print(f"\n{'='*60}")
        print(f"Cloud pipeline complete for {date_str}")
        print(f"  Execution time: {execution_time:.1f}s")
        print(f"  Tier 1 (Potential Conflicts): {tier1}")
        print(f"  Tier 2 (Financial Connections): {tier2}")
        print(f"  Tier 3 (Internal Only): {tier3}")
        print(f"  Clean items: {len(scan_result.clean_items)}")
        print(f"  Summaries generated: {summary_stats['generated']}")
        print(f"  Explainers generated: {explainer_stats['generated']}")
        print(f"{'='*60}")

        return summary

    except Exception as e:
        execution_time = time.time() - start_time
        print(f"\nERROR: Pipeline failed after {execution_time:.1f}s: {e}")
        fail_scan_run(conn, scan_run_id, str(e))
        try:
            journal.log_run_end("cloud_pipeline", str(scan_run_id), "failed",
                f"Pipeline failed after {execution_time:.1f}s: {e}", {
                    "error": str(e),
                    "execution_seconds": round(execution_time, 2),
                })
        except Exception:
            pass  # journal is non-fatal
        return {
            "scan_run_id": str(scan_run_id),
            "meeting_date": date_str,
            "scan_mode": scan_mode,
            "status": "failed",
            "error": str(e),
            "execution_seconds": round(execution_time, 2),
        }
    finally:
        conn.close()


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Richmond Common — Cloud Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cloud_pipeline.py --date 2026-03-03
  python cloud_pipeline.py --date 2026-03-03 --scan-mode retrospective
  python cloud_pipeline.py --date 2026-03-03 --triggered-by n8n
  python cloud_pipeline.py --date 2026-03-03 --skip-generators
        """,
    )
    parser.add_argument("--date", help="Meeting date (YYYY-MM-DD)")
    parser.add_argument(
        "--scan-mode",
        choices=["prospective", "retrospective"],
        default="prospective",
        help="Scan mode (default: prospective)",
    )
    parser.add_argument(
        "--triggered-by",
        default="manual",
        help="What triggered this run (manual, n8n, scheduled, reanalysis)",
    )
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="City FIPS code")
    parser.add_argument("--pipeline-run-id", help="GitHub Actions run ID or n8n execution ID")
    parser.add_argument("--send", action="store_true", help="Actually email the comment")
    parser.add_argument("--skip-generators", action="store_true", help="Skip summary and explainer generation (saves API cost)")
    parser.add_argument("--list-cities", action="store_true", help="List configured cities and exit")
    args = parser.parse_args()

    if args.list_cities:
        for city in list_configured_cities():
            cfg = get_city_config(city["fips_code"])
            sources = ", ".join(cfg["data_sources"].keys())
            print(f"  {city['fips_code']}  {city['name']}, {city['state']}  [{sources}]")
        sys.exit(0)

    if not args.date:
        parser.error("--date is required (unless using --list-cities)")

    # Use GITHUB_RUN_ID if available and no explicit pipeline_run_id
    pipeline_run_id = args.pipeline_run_id or os.getenv("GITHUB_RUN_ID")

    result = run_cloud_pipeline(
        date_str=args.date,
        scan_mode=args.scan_mode,
        triggered_by=args.triggered_by,
        city_fips=args.city_fips,
        pipeline_run_id=pipeline_run_id,
        dry_run=not args.send,
        skip_generators=args.skip_generators,
    )

    # Output summary as JSON for GitHub Actions to parse
    print(f"\n::group::Pipeline Summary")
    print(json.dumps(result, indent=2))
    print(f"::endgroup::")

    # Exit with error code if failed
    if result.get("status") == "failed":
        sys.exit(1)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
