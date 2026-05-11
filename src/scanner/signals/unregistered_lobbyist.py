"""
unregistered_lobbyist signal detector — extracted from conflict_scanner.py (Phase 2.2).

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


def signal_unregistered_lobbyist(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    entities: list[str],
    lobbyist_registrations: list[dict],
    contributions: list[dict],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect potential unregistered lobbying activity (S13.3).

    Cross-references entities mentioned in agenda items against registered
    lobbyist client lists. When a known donor's employer or a vendor appears
    in agenda text AND is a registered lobbyist client, that's a transparency
    signal worth noting.

    The *absence* signal (vendor representatives who AREN'T registered) is
    tracked separately as metadata in the match_details — the scanner flags
    the entity regardless, and the absence of registration is noted as an
    aggravating factor.
    """
    if not lobbyist_registrations:
        return []

    signals: list[RawSignal] = []
    norm_item = normalize_text(item_text)

    # Build quick lookup of registered lobbyist clients
    registered_clients = {}
    for reg in lobbyist_registrations:
        client = normalize_text(reg.get("client_name", ""))
        if client and len(client) >= 5:
            registered_clients[client] = reg

    # Check contributions — when a donor's employer is a registered lobbyist client
    for contrib in contributions:
        employer = (contrib.get("donor_employer") or contrib.get("contributor_employer") or "").strip()
        if not employer or len(employer) < 5:
            continue

        norm_employer = normalize_text(employer)

        # Is this employer a registered lobbyist client?
        matching_reg = None
        for client_norm, reg in registered_clients.items():
            if client_norm == norm_employer or (
                len(client_norm) >= 10
                and (client_norm in norm_employer or norm_employer in client_norm)
            ):
                matching_reg = reg
                break

        if not matching_reg:
            continue

        # Does this employer/client appear in the agenda item?
        employer_in_text, _ = cached_name_in_text(norm_employer, norm_item, ctx.name_in_text_cache)
        if not employer_in_text:
            continue

        donor = contrib.get("donor_name") or contrib.get("contributor_name", "")
        candidate = contrib.get("council_member") or contrib.get("committee_name", "")
        amount = contrib.get("amount", 0) or 0

        # Resolve candidate to official name
        resolved_official = None
        if candidate:
            candidate_name = extract_candidate_from_committee(candidate) if "committee" in candidate.lower() else candidate
            if candidate_name:
                norm_candidate = normalize_text(candidate_name)
                for member in ctx.current_officials | ctx.former_officials:
                    if names_match(candidate_name, member)[0]:
                        resolved_official = member
                        break
                if not resolved_official and norm_candidate in ctx.current_officials:
                    resolved_official = norm_candidate

        if not resolved_official:
            continue

        is_sitting = resolved_official in ctx.current_officials

        signals.append(RawSignal(
            signal_type="lobbyist_client_donor",
            council_member=resolved_official,
            agenda_item_number=item_num,
            match_strength=0.75,
            temporal_factor=_compute_temporal_factor(
                contrib.get("date") or contrib.get("contribution_date", ""),
                ctx.meeting_date,
            ),
            financial_factor=min(1.0, amount / 10000) if amount else 0.4,
            description=(
                f"Registered lobbyist connection: {employer} is a client of "
                f"lobbyist {matching_reg.get('lobbyist_name', 'unknown')}, "
                f"and an employee ({donor}) donated ${amount:,.2f} to {resolved_official}'s campaign. "
                f"{employer} appears in this agenda item."
            ),
            evidence=[
                f"Lobbyist registration: {matching_reg.get('lobbyist_name', 'unknown')} "
                f"represents {employer}",
                f"Campaign contribution: {donor} (employer: {employer}) "
                f"donated ${amount:,.2f}",
                f"Agenda item mentions: {employer}",
            ],
            legal_reference="Richmond Municipal Code Ch. 2.54 (lobbyist registration); Cal. Gov. Code § 87100",
            financial_amount=financial,
            match_details={
                "employer": employer,
                "donor_name": donor,
                "lobbyist_name": matching_reg.get("lobbyist_name"),
                "lobbyist_firm": matching_reg.get("lobbyist_firm"),
                "client_name": matching_reg.get("client_name"),
                "amount": amount,
                "official": resolved_official,
                "sitting": is_sitting,
                "registration_date": matching_reg.get("registration_date"),
            },
        ))

    return signals
