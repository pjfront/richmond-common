"""
elections pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (elections-specific) live alongside.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import psycopg2

from city_config import get_city_config, list_configured_cities
from db import (
    get_connection,
    create_sync_log,
    complete_sync_log,
    load_contributions_to_db,
    load_expenditures_to_db,
)
from pipeline_journal import PipelineJournal, check_anomalies

DEFAULT_FIPS = "0660620"


def sync_elections(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync election cycle data by analyzing existing committee/contribution data.

    This is a derived/enrichment sync — it processes data already in the
    database from netfile and calaccess syncs. Should run after those sources.

    Pipeline:
    1. build_candidates_from_committees — extract candidate info from committee names
    2. assign_committees_to_elections — link committees to election cycles
    3. assign_contributions_to_elections — link contributions to election cycles
    """
    from elections_client import run_election_pipeline

    print("  Running election cycle tracking pipeline...")
    stats = run_election_pipeline(conn, city_fips)

    candidates = stats.get("candidates", {})
    contributions = stats.get("contributions", {})

    return {
        "records_fetched": candidates.get("candidates_created", 0) + candidates.get("candidates_updated", 0),
        "records_new": candidates.get("candidates_created", 0),
        "records_updated": candidates.get("candidates_updated", 0),
        "contributions_assigned": contributions.get("total_assigned", 0),
    }



def sync_filing_period_briefings(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Regenerate filing-period briefings for any currently-active period.

    "Active" = today is within the period's window OR up to 60 days after
    period_end, so post-deadline 497 amendments and paper-filing OCRs
    keep flowing into the briefing JSONB. See filing_period_briefing.
    KNOWN_PERIODS for the period dictionary.

    Runs LAST in the netfile enrichment cascade (after donor_employer_merge,
    donor_dedup, paper_filing_reconciliation) so the briefing reflects the
    fully-cleaned, fully-reconciled DB state.

    Idempotency: gated on sync_type. Incremental runs respect the existing
    is_current briefing — if one exists for the period, the call is a no-op
    (DB write avoided, no wasted compute, no Supabase write-traffic burn).
    Full sync (sync_type="full") supersedes the prior briefing. The prior
    hardcoded force=True caused 3-4 unconditional regenerations per day
    during election season from the change-detector dispatch cascade —
    technically idempotent in DB outcome but every run rewrote the
    filing_period_briefings JSONB blob (helped push Supabase I/O quota past
    80%/mo, see PR description on branch claude/fix-api-billing-gFC3C).

    Without this hook, the FilingPeriodBriefingSection on candidate detail
    pages stays stale until someone runs filing_period_briefing.py
    manually. Cycle totals on candidate cards (which read from
    `contributions` directly) update independently — only the narrative
    F1-F4 section depends on this regeneration.
    """
    from filing_period_briefing import current_period_labels, generate_briefing

    labels = current_period_labels()
    if not labels:
        return {
            "records_fetched": 0,
            "records_new": 0,
            "records_updated": 0,
            "note": "no active filing periods today",
        }

    total_candidates = 0
    total_contributions = 0
    per_period: list[dict] = []
    force_regen = sync_type == "full"
    for label in labels:
        try:
            stats = generate_briefing(
                label,
                city_fips=city_fips,
                force=force_regen,
            )
        except Exception as exc:
            per_period.append({"period_label": label, "error": str(exc)})
            continue
        total_candidates += stats.get("candidates", 0) or 0
        total_contributions += stats.get("contributions", 0) or 0
        per_period.append(stats)

    return {
        "records_fetched": len(labels),
        "records_new": sum(1 for p in per_period if p.get("briefing_id")),
        "records_updated": 0,
        "candidates_total": total_candidates,
        "contributions_total": total_contributions,
        "per_period": per_period,
    }


