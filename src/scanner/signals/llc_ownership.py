"""
llc_ownership signal detector — extracted from conflict_scanner.py (Phase 2.2).

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


# ── B.46: Entity Resolution Signal Detectors ─────────────────

def signal_llc_ownership_chain(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    entities: list[str],
    contributions: list[dict],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect LLC/org ownership chain connections (B.45 cross-ref #3).

    For each entity mentioned in an agenda item:
    1. Check if the entity exists in the org_reverse_map (from entity registry)
    2. Look up all persons linked to that organization
    3. Check if any linked person is also a campaign donor to a sitting member
    4. Produce a signal when a donor is connected to an agenda-mentioned org

    This detector replaces fuzzy text matching with structural ID matching
    for organizations that have been resolved via external registries.
    """
    if not ctx.org_reverse_map:
        return []

    signals: list[RawSignal] = []
    norm_item = normalize_text(item_text)

    # Check each entity name mentioned in the agenda item against the org registry
    for entity in entities:
        norm_entity = normalize_text(entity)
        if len(norm_entity) < 5:
            continue

        # Look up in org reverse map (exact normalized match)
        linked_persons = ctx.org_reverse_map.get(norm_entity)

        # Also try partial matches for org names that appear as substrings
        if not linked_persons:
            for org_norm, persons in ctx.org_reverse_map.items():
                if len(org_norm) >= 10 and (org_norm in norm_entity or norm_entity in org_norm):
                    linked_persons = persons
                    break

        if not linked_persons:
            continue

        # For each person linked to this org, check if they're a campaign donor
        for person_info in linked_persons:
            person_norm = person_info["normalized_person_name"]
            person_name = person_info["person_name"]
            role = person_info["role"]
            confidence = person_info["confidence"]

            # Check contributions for this person
            for contrib in contributions:
                donor_name = contrib.get("donor_name") or contrib.get("contributor_name", "")
                norm_donor = contrib.get("_norm_donor") or normalize_text(donor_name)

                if norm_donor != person_norm:
                    # Try partial name match
                    match_result, _ = names_match(person_name, donor_name)
                    if not match_result:
                        continue

                committee = contrib.get("committee_name") or contrib.get("committee", "")
                amount = contrib.get("amount", 0)

                # Materiality threshold
                if amount < 100:
                    continue

                candidate = extract_candidate_from_committee(committee)
                sitting = is_sitting_council_member(
                    candidate, ctx.current_officials, ctx.alias_groups
                ) if candidate else False

                if not sitting:
                    continue

                council_member = candidate or committee

                # Determine match type based on role
                if role in ("officer", "director", "ceo", "cfo", "president"):
                    match_type = "registry_officer"
                elif role == "agent":
                    match_type = "registry_agent"
                else:
                    match_type = "registry_employee"

                match_strength = _match_type_to_strength(match_type)
                temporal_factor = _compute_temporal_factor(
                    contrib.get("date", ""), ctx.meeting_date
                )
                financial_factor = _compute_financial_factor(amount)
                org_name = person_info.get("org_name", entity)

                description = (
                    f"Public records show that {person_name} "
                    f"({role} of {org_name}) donated "
                    f"${amount:,.2f} to {council_member}'s campaign. "
                    f"{org_name} is mentioned in this agenda item. "
                    f"Connection identified via {person_info.get('entity_type', 'organization')} "
                    f"registry ({confidence:.0%} confidence)."
                )

                signals.append(RawSignal(
                    signal_type="llc_ownership_chain",
                    council_member=council_member,
                    agenda_item_number=item_num,
                    match_strength=match_strength,
                    temporal_factor=temporal_factor,
                    financial_factor=financial_factor,
                    description=description,
                    evidence=[
                        f"Entity registry: {person_name} is {role} of {org_name}",
                        f"Campaign contribution: ${amount:,.2f} to {committee}",
                        f"Agenda item mentions: {entity}",
                    ],
                    legal_reference="Cal. Gov. Code § 87100 (conflict of interest); Cal. Corp. Code (business entity filings)",
                    financial_amount=financial,
                    match_details={
                        "person_name": person_name,
                        "org_name": org_name,
                        "role": role,
                        "entity_type": person_info.get("entity_type"),
                        "match_type": match_type,
                        "registry_confidence": confidence,
                        "donor_name": donor_name,
                        "amount": amount,
                        "committee": committee,
                        "candidate": candidate,
                        "sitting": sitting,
                    },
                ))

    return signals
