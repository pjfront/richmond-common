"""
independent_expenditure signal detector — extracted from conflict_scanner.py (Phase 2.2).

Shared types, scoring helpers, and text utilities are imported from
conflict_scanner. This module is re-exported from conflict_scanner so the
public import surface (`from conflict_scanner import signal_*`) is unchanged.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from bias_signals import lookup_surname_frequency_tier
from scan_audit import MatchingDecision, ScanAuditLogger

from conflict_scanner import (
    RawSignal, ConflictFlag, VendorDonorMatch, ScanResult, ContributionBaselines,
    _ScanContext,
    _parse_date, _compute_temporal_factor, _compute_temporal_direction,
    _compute_financial_factor, _match_type_to_strength,
    compute_anomaly_factor, compute_composite_confidence, _confidence_to_tier,
    apply_hedge_clause, validate_language, _build_connection_clause,
    normalize_text, normalize_business_name, _is_government_entity,
    name_in_text, cached_name_in_text, names_match,
    extract_entity_names, prefilter_contributions, build_contribution_word_index,
    _get_council_members, is_sitting_council_member,
    get_levine_act_threshold, get_time_decay_multiplier,
    extract_aye_voters, extract_backer_from_committee, extract_candidate_from_committee,
    scan_temporal_correlations,
    DEFAULT_LOOKBACK_DAYS, V3_TIER_THRESHOLDS, TIER_LABELS, TIER_THRESHOLDS_BY_NUMBER,
    CONFIDENCE_WEIGHTS, SITTING_MULTIPLIER, NON_SITTING_MULTIPLIER,
    DEFAULT_ANOMALY_FACTOR, MIN_CONTRIBUTIONS_FOR_BASELINES,
    LANGUAGE_TEMPLATE, LANGUAGE_BLOCKLIST, HEDGE_CLAUSE, TIME_DECAY_WINDOWS,
)


def signal_independent_expenditure(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    independent_expenditures: list[dict],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect independent expenditure signals.

    Surfaces connections between outside PAC spending and agenda items:
    "PAC X spent $Y supporting Councilmember Z, and PAC X's identifiable
    corporate backer appears in this agenda item."

    Only processes support (S) IEs — oppose (O) IEs don't create a financial
    interest for the candidate.

    Returns list[RawSignal] for integration into v3 composite confidence.
    """
    from datetime import datetime

    signals: list[RawSignal] = []
    if not independent_expenditures:
        return signals

    meeting_date_str = ctx.meeting_date

    # Group IEs by (committee, candidate) and aggregate amounts
    ie_groups: dict[tuple[str, str], list[dict]] = {}
    for ie in independent_expenditures:
        if (ie.get("support_or_oppose") or "").upper() != "S":
            continue
        committee = (ie.get("committee_name") or "").strip()
        candidate = (ie.get("candidate_name") or "").strip()
        if not committee or not candidate:
            continue
        ie_groups.setdefault((committee, candidate), []).append(ie)

    seen = set()  # Deduplicate by (committee, council_member, item_num)

    for (committee, candidate), ie_records in ie_groups.items():
        # Resolve candidate to a known council member
        council_member = None
        for member in ctx.current_officials | ctx.former_officials:
            m, _ = names_match(candidate, member)
            if m:
                council_member = member
                break
        if not council_member:
            # Try extract_candidate_from_committee as fallback
            extracted = extract_candidate_from_committee(committee)
            if extracted:
                for member in ctx.current_officials | ctx.former_officials:
                    m, _ = names_match(extracted, member)
                    if m:
                        council_member = member
                        break
        if not council_member:
            continue

        # Extract backer names from committee
        backers = extract_backer_from_committee(committee)

        # Try matching backer names against item text
        # name_in_text requires >= 10 chars; for shorter backer names (e.g.
        # "Chevron" = 7 chars, "SEIU" = 4 chars), use direct substring match
        # with word boundary check to avoid partial matches.
        matched_backer = None
        match_type = None
        norm_item = normalize_text(item_text)
        for backer in backers:
            is_match, mt = cached_name_in_text(backer, item_text, ctx.name_in_text_cache)
            if is_match:
                matched_backer = backer
                match_type = mt
                break
            # Fallback for short names (< 10 chars): direct substring check
            norm_backer = normalize_text(backer)
            if len(norm_backer) >= 4 and norm_backer in norm_item:
                matched_backer = backer
                match_type = "phrase"
                break

        # Also try the full committee name as fallback
        if not matched_backer:
            is_match, mt = cached_name_in_text(committee, item_text, ctx.name_in_text_cache)
            if is_match:
                matched_backer = committee
                match_type = mt

        if not matched_backer:
            continue

        # Dedup
        dedup_key = (committee, council_member, item_num)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Aggregate amounts
        total_amount = sum(
            float(ie.get("amount", 0) or 0) for ie in ie_records
        )

        # Compute factor scores
        # Match strength: backer extraction adds uncertainty vs direct name match
        base_strength = _match_type_to_strength(match_type)
        # Slight discount if matching extracted backer vs full committee name
        if matched_backer != committee:
            match_strength = min(base_strength, 0.80)
        else:
            match_strength = base_strength

        # Temporal: use most recent expenditure date
        temporal_factor = 0.5  # neutral default
        if meeting_date_str:
            exp_dates = [str(ie.get("expenditure_date") or ie.get("date", ""))[:10]
                         for ie in ie_records]
            exp_dates = [d for d in exp_dates if d and d != "None"]
            if exp_dates:
                # Use the most recent expenditure for temporal calc
                best_temporal = max(
                    _compute_temporal_factor(d, meeting_date_str)
                    for d in exp_dates
                )
                temporal_factor = best_temporal

        # Financial factor from total IE amount
        financial_factor = _compute_financial_factor(total_amount)

        # Build factual description
        total_str = f"${total_amount:,.2f}" if total_amount else "undisclosed amounts"
        ie_count = len(ie_records)
        ie_count_str = f"across {ie_count} expenditures " if ie_count > 1 else ""
        # Include agenda title for context on why this was flagged
        title_ctx = f": {item_title.strip()[:150]}" if item_title and item_title.strip() else ""
        description = (
            f"Public records show that {committee} spent {total_str} "
            f"{ie_count_str}in independent expenditures supporting "
            f"{council_member}'s campaign. {matched_backer} appears in "
            f"agenda item {item_num}{title_ctx}."
        )

        signals.append(RawSignal(
            signal_type="independent_expenditure",
            council_member=council_member,
            agenda_item_number=item_num,
            match_strength=match_strength,
            temporal_factor=temporal_factor,
            financial_factor=financial_factor,
            description=description,
            evidence=[{
                "committee": committee,
                "candidate": candidate,
                "matched_backer": matched_backer,
                "match_type": match_type,
                "total_amount": total_amount,
                "expenditure_count": ie_count,
                "council_member": council_member,
            }],
            legal_reference=(
                "Gov. Code \u00a7 82031 (independent expenditure); "
                "Gov. Code \u00a7 87100 (financial interest)"
            ),
            financial_amount=f"${total_amount:,.2f}" if total_amount else None,
            match_details={
                "committee": committee,
                "candidate": candidate,
                "matched_backer": matched_backer,
                "match_type": match_type,
                "total_amount": total_amount,
                "expenditure_count": ie_count,
                "is_sitting": council_member in ctx.current_officials,
            },
        ))

    return signals

