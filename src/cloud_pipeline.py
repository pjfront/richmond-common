"""
Richmond Transparency Project — Cloud Pipeline

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

DEFAULT_FIPS = "0660620"  # Richmond — keep as CLI default for backward compat
from escribemeetings_scraper import (
    create_session,
    discover_meetings,
    find_meeting_by_date,
    scrape_meeting,
)
from conflict_scanner import scan_meeting_json, scan_temporal_correlations
from comment_generator import (
    generate_comment_from_scan,
    detect_missing_documents,
)
from escribemeetings_enricher import enrich_meeting_data
from run_pipeline import convert_escribemeetings_to_scanner_format


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


def run_cloud_pipeline(
    date_str: str,
    scan_mode: str = "prospective",
    triggered_by: str = "manual",
    city_fips: str = DEFAULT_FIPS,
    pipeline_run_id: str = None,
    dry_run: bool = True,
) -> dict:
    """Run the full cloud pipeline for a meeting date.

    Args:
        date_str: Meeting date YYYY-MM-DD
        scan_mode: 'prospective' (pre-meeting, date-filtered) or 'retrospective' (all data)
        triggered_by: 'scheduled', 'manual', 'n8n', 'reanalysis'
        city_fips: City FIPS code
        pipeline_run_id: GitHub Actions run ID or n8n execution ID
        dry_run: If True, don't email comment

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
        # ── Step 1: Scrape eSCRIBE ──────────────────────────
        print("Step 1: Scraping eSCRIBE for meeting agenda packet...")
        session = create_session()
        meetings = discover_meetings(session)
        meeting = find_meeting_by_date(meetings, date_str)

        if not meeting:
            raise ValueError(f"No meeting found for {date_str}")

        escribemeetings_data = scrape_meeting(session, meeting)
        print(f"  Found {len(escribemeetings_data.get('items', []))} items")

        # Store raw data in Supabase Layer 1
        doc_id = _store_raw_escribemeetings(conn, city_fips, date_str, escribemeetings_data)
        print(f"  Stored raw eSCRIBE data → document {doc_id}")

        # ── Step 2: Convert to scanner format ────────────────
        print("Step 2: Converting eSCRIBE data to scanner format...")
        meeting_data = convert_escribemeetings_to_scanner_format(escribemeetings_data)

        consent_count = len(meeting_data["consent_calendar"]["items"])
        action_count = len(meeting_data["action_items"])
        housing_count = len(meeting_data["housing_authority_items"])
        print(f"  Items: {consent_count} consent, {action_count} action, {housing_count} housing")

        # ── Step 3: Enrich with attachment text ──────────────
        print("Step 3: Enriching with staff report text...")
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(escribemeetings_data, tmp, indent=2)
            tmp_path = tmp.name
        meeting_data, enriched_items = enrich_meeting_data(meeting_data, tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
        print(f"  Enriched {len(enriched_items)} items with attachment text")

        # ── Step 4: Load contributions from Supabase ─────────
        print(f"Step 4: Loading contributions from database (cutoff={data_cutoff})...")
        contributions = _load_contributions_from_db(conn, city_fips, data_cutoff)
        source_counts = _contribution_source_counts(contributions)
        print(f"  Loaded {len(contributions):,} contributions {source_counts}")

        # If no contributions in DB, fall back to local file (transitional)
        if not contributions:
            local_path = Path(__file__).parent / "data" / "combined_contributions.json"
            if local_path.exists():
                print(f"  WARNING: No contributions in DB, falling back to {local_path}")
                with open(local_path) as f:
                    contributions = json.load(f)
                source_counts = {"local_file": len(contributions)}
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

        # ── Step 5: Conflict scan ────────────────────────────
        print("Step 5: Scanning for conflicts...")
        scan_result = scan_meeting_json(meeting_data, contributions, [])
        scan_result.enriched_items = enriched_items

        tier1 = sum(1 for f in scan_result.flags if f.publication_tier == 1)
        tier2 = sum(1 for f in scan_result.flags if f.publication_tier == 2)
        tier3 = sum(1 for f in scan_result.flags if f.publication_tier == 3)
        print(f"  Flags: {tier1} Tier1, {tier2} Tier2, {tier3} Tier3")
        print(f"  Clean items: {len(scan_result.clean_items)}")

        # ── Step 6: Load meeting to Layer 2 ──────────────────
        print("Step 6: Loading meeting data into database...")
        meeting_id = load_meeting_to_db(conn, meeting_data, document_id=doc_id, city_fips=city_fips)
        print(f"  Meeting loaded → {meeting_id}")

        # Link scan run to meeting
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scan_runs SET meeting_id = %s WHERE id = %s",
                (meeting_id, scan_run_id),
            )
        conn.commit()

        # Supersede old prospective flags if this is a new prospective scan
        if scan_mode == "prospective":
            superseded = supersede_flags_for_meeting(conn, meeting_id, scan_run_id, scan_mode)
            if superseded:
                print(f"  Superseded {superseded} previous prospective flags")

        # Save flags to database
        for flag in scan_result.flags:
            save_conflict_flag(
                conn,
                city_fips=city_fips,
                meeting_id=meeting_id,
                scan_run_id=scan_run_id,
                flag_type="campaign_contribution",
                description=flag.description,
                evidence=[{
                    "donor_name": flag.donor_name,
                    "amount": flag.amount,
                    "committee": flag.committee,
                    "match_type": flag.match_type,
                }],
                confidence=flag.confidence,
                scan_mode=scan_mode,
                data_cutoff_date=data_cutoff,
            )

        # ── Step 5b: Temporal correlation (retrospective only) ──
        temporal_flags = []
        if scan_mode == "retrospective":
            print("Step 5b: Running temporal correlation analysis...")
            temporal_flags = scan_temporal_correlations(
                meeting_data, contributions, city_fips=city_fips
            )
            print(f"  Found {len(temporal_flags)} post-vote donation flags")

            # Save temporal flags to database
            if temporal_flags and not dry_run:
                for flag in temporal_flags:
                    save_conflict_flag(
                        conn,
                        city_fips=city_fips,
                        meeting_id=meeting_id,
                        scan_run_id=scan_run_id,
                        flag_type=flag.flag_type,
                        description=flag.description,
                        evidence=flag.evidence,
                        confidence=flag.confidence,
                        scan_mode=scan_mode,
                        data_cutoff_date=data_cutoff,
                    )

        # ── Step 7: Generate comment ─────────────────────────
        print("Step 7: Generating public comment...")
        missing_docs = detect_missing_documents(meeting_data)
        contribution_count = f"{len(contributions):,}" if contributions else "0"
        comment = generate_comment_from_scan(scan_result, missing_docs, contribution_count)

        # Store comment in Layer 1
        comment_doc_id = _store_generated_comment(conn, city_fips, date_str, comment, scan_run_id)
        print(f"  Comment stored → document {comment_doc_id}")

        if not dry_run:
            print("  Sending comment to city clerk...")
            from comment_generator import submit_comment_to_clerk
            submit_comment_to_clerk(comment, date_str, dry_run=False)

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
            "execution_seconds": round(execution_time, 2),
            "status": "completed",
        }

        print(f"\n{'='*60}")
        print(f"Cloud pipeline complete for {date_str}")
        print(f"  Execution time: {execution_time:.1f}s")
        print(f"  Tier 1 (Potential Conflicts): {tier1}")
        print(f"  Tier 2 (Financial Connections): {tier2}")
        print(f"  Tier 3 (Internal Only): {tier3}")
        print(f"  Clean items: {len(scan_result.clean_items)}")
        print(f"{'='*60}")

        return summary

    except Exception as e:
        execution_time = time.time() - start_time
        print(f"\nERROR: Pipeline failed after {execution_time:.1f}s: {e}")
        fail_scan_run(conn, scan_run_id, str(e))
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
        description="Richmond Transparency Project — Cloud Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cloud_pipeline.py --date 2026-03-03
  python cloud_pipeline.py --date 2026-03-03 --scan-mode retrospective
  python cloud_pipeline.py --date 2026-03-03 --triggered-by n8n
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
