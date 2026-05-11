"""
temporal_correlation signal detector — extracted from conflict_scanner.py (Phase 2.2).

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


def signal_temporal_correlation(
    item: dict,
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    entities: list[str],
    aye_voters: set[str],
    post_vote_contributions: list[tuple[dict, "date"]],
    committee_to_official: dict[str, str],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect post-vote donation signals for an agenda item.

    For each contribution filed AFTER the meeting where an official voted Aye,
    check if the donor/employer matches an entity in the agenda item.

    Returns list[RawSignal] for integration into the v3 composite confidence model.
    """
    from datetime import datetime

    signals: list[RawSignal] = []
    meeting_date_str = ctx.meeting_date
    if not meeting_date_str or not aye_voters or not post_vote_contributions:
        return signals

    try:
        meeting_date = datetime.strptime(meeting_date_str, "%Y-%m-%d").date()
    except ValueError:
        return signals

    seen = set()  # Deduplicate by (item_number, donor, committee)

    for contrib, c_date in post_vote_contributions:
        donor_name = contrib.get("contributor_name") or contrib.get("donor_name", "")
        donor_employer = contrib.get("contributor_employer") or contrib.get("donor_employer", "")
        committee = contrib.get("committee") or contrib.get("committee_name", "")
        amount = float(contrib.get("amount", 0))

        if not donor_name:
            continue

        # Skip government entity donors
        if _is_government_entity(donor_name):
            continue

        # Skip self-donations (official donating to their own campaign)
        norm_donor = normalize_text(donor_name)
        norm_committee = normalize_text(committee)
        if len(norm_donor) > 4 and norm_donor in norm_committee:
            continue
        donor_cand = extract_candidate_from_committee(donor_name)
        committee_cand = extract_candidate_from_committee(committee)
        if donor_cand and committee_cand:
            match_self, _ = names_match(donor_cand, committee_cand)
            if match_self:
                continue

        # Determine which official received this donation
        recipient_official = committee_to_official.get(committee, "")
        if not recipient_official:
            continue

        # Check if the recipient voted Aye on this item
        official_voted_aye = False
        for voter in aye_voters:
            voter_match, _ = names_match(recipient_official, voter)
            if voter_match:
                official_voted_aye = True
                recipient_official = voter  # Use the exact name from vote record
                break

        if not official_voted_aye:
            continue

        # Check if donor/employer matches any entity in the agenda item
        match_type = None
        matched_entity = None

        for entity in entities:
            # Check employer match — skip government entity employers
            if donor_employer and not _is_government_entity(donor_employer):
                emp_match, emp_type = names_match(donor_employer, entity)
                if emp_match:
                    match_type = f"employer_to_{emp_type}"
                    matched_entity = entity
                    break

            name_match_result, name_type = names_match(donor_name, entity)
            if name_match_result:
                match_type = f"donor_name_to_{name_type}"
                matched_entity = entity
                break

        if not match_type:
            continue

        # Deduplicate
        dedup_key = (item_num, donor_name, committee)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Compute v3 factor scores
        days_after = (c_date - meeting_date).days
        match_strength = _match_type_to_strength(match_type)

        # Temporal factor: use shared TIME_DECAY_WINDOWS via get_time_decay_multiplier
        temporal_factor = get_time_decay_multiplier(days_after)

        financial_factor = _compute_financial_factor(amount)

        # Build factual description
        description = (
            f"{recipient_official} voted Aye on Item {item_num} "
            f"({item_title}) on {meeting_date_str}. "
            f"{donor_name}"
        )
        if donor_employer:
            description += f" (employer: {donor_employer})"
        description += (
            f" contributed ${amount:,.2f} to {committee} "
            f"on {c_date}, {days_after} days after the vote."
        )

        signals.append(RawSignal(
            signal_type="temporal_correlation",
            council_member=recipient_official,
            agenda_item_number=item_num,
            match_strength=match_strength,
            temporal_factor=temporal_factor,
            financial_factor=financial_factor,
            description=description,
            evidence=[{
                "vote_date": meeting_date_str,
                "vote_choice": "aye",
                "agenda_item_number": item_num,
                "agenda_item_title": item_title,
                "donation_date": str(c_date),
                "days_after_vote": days_after,
                "donor_name": donor_name,
                "donor_employer": donor_employer,
                "donation_amount": amount,
                "recipient_official": recipient_official,
                "recipient_committee": committee,
                "match_type": match_type,
                "matched_entity": matched_entity,
            }],
            legal_reference="Gov. Code \u00a7 87100 (financial interest disclosure)",
            financial_amount=f"${amount:,.2f}",
            match_details={
                "donor_name": donor_name,
                "donor_employer": donor_employer,
                "committee": committee,
                "amount": amount,
                "days_after_vote": days_after,
                "match_type": match_type,
                "matched_entity": matched_entity,
                "is_sitting": recipient_official in ctx.current_officials,
            },
        ))

    return signals

