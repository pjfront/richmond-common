"""
permit_donor signal detector — extracted from conflict_scanner.py (Phase 2.2).

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


def signal_permit_donor(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    permits: list[dict],
    contributions: list[dict],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect permit-applicant → campaign-donor cross-reference signals.

    Cross-references permit applicants (from city_permits) against campaign
    contributors. When a permit applicant also donated to a council member's
    campaign, and that applicant or their permit appears in an agenda item,
    this is a signal worth surfacing.

    This is cross-reference #5 from the political influence research
    (scored 11/15): Donor → Permit applicant → Favorable decision.

    California AB 571 / Gov. Code § 84308 (Levine Act) prohibits officials from
    participating in decisions involving permit applicants who contributed above a
    threshold: $250 pre-2025, $500 post-2025 (SB 1243). Uses date-aware threshold
    via get_levine_act_threshold().

    Returns list[RawSignal] for integration into v3 composite confidence.
    """
    from datetime import datetime

    signals: list[RawSignal] = []
    if not permits or not contributions:
        return signals

    meeting_date_str = ctx.meeting_date

    # Build applicant gazetteer: distinct applicant names from permits
    # Each applicant maps to their permits for evidence
    applicant_permits: dict[str, list[dict]] = {}
    for permit in permits:
        applicant = (permit.get("applied_by") or "").strip()
        if not applicant or len(applicant) < 10:
            continue
        norm_applicant = normalize_text(applicant)
        applicant_permits.setdefault(norm_applicant, []).append(permit)

    if not applicant_permits:
        return signals

    # Step 1: Check which applicants appear in the agenda item text
    matched_applicants: dict[str, tuple[str, list[dict]]] = {}  # norm_name -> (match_type, permits)
    for norm_applicant, applicant_permit_list in applicant_permits.items():
        original_name = (applicant_permit_list[0].get("applied_by") or "").strip()
        is_match, match_type = cached_name_in_text(
            original_name, item_text, ctx.name_in_text_cache
        )
        if is_match:
            matched_applicants[norm_applicant] = (match_type, applicant_permit_list)

    if not matched_applicants:
        return signals

    # Step 2: Cross-reference matched applicants against campaign contributions
    seen = set()  # Deduplicate by (applicant, council_member, item_num)
    for norm_applicant, (text_match_type, applicant_permit_list) in matched_applicants.items():
        original_name = (applicant_permit_list[0].get("applied_by") or "").strip()

        for contrib in contributions:
            donor_name = contrib.get("donor_name") or contrib.get("contributor_name", "")
            donor_employer = contrib.get("donor_employer") or contrib.get("contributor_employer", "")
            committee = contrib.get("committee_name") or contrib.get("committee", "")
            amount = float(contrib.get("amount", 0) or 0)
            council_member = contrib.get("council_member", "")

            if not donor_name:
                continue

            # Skip below materiality threshold
            if amount < 100:
                continue

            # Match applicant against donor name or employer
            donor_match = False
            contrib_match_type = None
            name_result, name_type = names_match(original_name, donor_name)
            if name_result:
                donor_match = True
                contrib_match_type = f"applicant_to_donor_{name_type}"
            elif donor_employer:
                emp_result, emp_type = names_match(original_name, donor_employer)
                if emp_result:
                    donor_match = True
                    contrib_match_type = f"applicant_to_employer_{emp_type}"

            if not donor_match:
                continue

            # Resolve council member from committee if needed
            if not council_member and committee:
                candidate = extract_candidate_from_committee(committee)
                if candidate:
                    for member in ctx.current_officials | ctx.former_officials:
                        m, _ = names_match(candidate, member)
                        if m:
                            council_member = member
                            break
                    if not council_member:
                        council_member = candidate

            if not council_member:
                continue

            # Deduplicate
            dedup_key = (norm_applicant, council_member, item_num)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Compute v3 factor scores
            # Match strength: conservative (weaker of text match + donor match)
            base_match = _match_type_to_strength(
                contrib_match_type,
                donor_name_words=set(normalize_text(donor_name).split()),
            )
            text_strength = _match_type_to_strength(text_match_type)
            match_strength = min(base_match, text_strength)

            # Temporal: contribution proximity to meeting date
            temporal_factor = 0.5
            contrib_date_str = str(
                contrib.get("date") or contrib.get("contribution_date", "")
            )[:10]
            if contrib_date_str and meeting_date_str:
                temporal_factor = _compute_temporal_factor(
                    contrib_date_str, meeting_date_str
                )

            # Financial factor: use max of contribution vs permit job_value
            max_job_value = max(
                (float(p.get("job_value", 0) or 0) for p in applicant_permit_list),
                default=0.0,
            )
            combined_amount = max(amount, max_job_value)
            financial_factor = _compute_financial_factor(combined_amount)

            # Count permits for this applicant
            permit_count = len(applicant_permit_list)
            permit_types = list({
                p.get("permit_type", "unknown") for p in applicant_permit_list
            })

            # Build factual description
            title_ctx = (
                f": {item_title.strip()[:150]}"
                if item_title and item_title.strip()
                else ""
            )
            job_value_str = (
                f" (total job value: ${max_job_value:,.0f})"
                if max_job_value > 0
                else ""
            )
            description = (
                f"Public records show that {original_name} applied for "
                f"{permit_count} city permit(s){job_value_str} and contributed "
                f"${amount:,.2f} to {council_member}'s campaign committee "
                f"({committee}). {original_name} appears in agenda item "
                f"{item_num}{title_ctx}."
            )

            signals.append(RawSignal(
                signal_type="permit_donor",
                council_member=council_member,
                agenda_item_number=item_num,
                match_strength=match_strength,
                temporal_factor=temporal_factor,
                financial_factor=financial_factor,
                description=description,
                evidence=[{
                    "applicant": original_name,
                    "text_match_type": text_match_type,
                    "donor_match_type": contrib_match_type,
                    "contribution_amount": amount,
                    "permit_count": permit_count,
                    "permit_types": permit_types,
                    "max_job_value": max_job_value,
                    "council_member": council_member,
                    "committee": committee,
                    "contribution_date": contrib_date_str,
                }],
                legal_reference=(
                    f"Gov. Code § 84308 (Levine Act, threshold "
                    f"${get_levine_act_threshold(meeting_date_str)} per SB 1243); "
                    f"Gov. Code § 87100 (financial interest)"
                ),
                financial_amount=f"${combined_amount:,.2f}",
                match_details={
                    "applicant": original_name,
                    "text_match_type": text_match_type,
                    "donor_match_type": contrib_match_type,
                    "contribution_amount": amount,
                    "permit_count": permit_count,
                    "permit_types": permit_types,
                    "max_job_value": max_job_value,
                    "committee": committee,
                    "is_sitting": council_member in ctx.current_officials,
                    "levine_act_threshold": get_levine_act_threshold(meeting_date_str),
                    "exceeds_levine_threshold": amount >= get_levine_act_threshold(meeting_date_str),
                },
            ))

    return signals

