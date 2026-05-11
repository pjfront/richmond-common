"""
donor_vendor signal detector — extracted from conflict_scanner.py (Phase 2.2).

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


def signal_donor_vendor_expenditure(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    vendor_gazetteer: list[str],
    contributions: list[dict],
    expenditures: list[dict],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect donor-vendor-expenditure cross-reference signals.

    Uses gazetteer-based matching: checks each known vendor name directly
    against item text using cached_name_in_text() (contiguous phrase matching).
    Then cross-references matched vendors against campaign contributions.

    This cross-reference is a strong corroboration signal: the same entity
    is receiving public money AND donating to officials who vote on items
    mentioning that entity.

    Returns list[RawSignal] for integration into v3 composite confidence.
    """
    from datetime import datetime

    signals: list[RawSignal] = []
    if not vendor_gazetteer or (not contributions and not expenditures):
        return signals

    meeting_date_str = ctx.meeting_date
    meeting_date = None
    if meeting_date_str:
        try:
            meeting_date = datetime.strptime(meeting_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Gazetteer match: check each vendor name against item text
    vendor_matches: dict[str, list[dict]] = {}
    for vendor_name in vendor_gazetteer:
        is_match, match_type = cached_name_in_text(vendor_name, item_text, ctx.name_in_text_cache)
        if not is_match:
            continue
        # Find all expenditure records for this vendor
        for exp in expenditures:
            exp_vendor = exp.get("normalized_vendor") or exp.get("vendor_name", "")
            if not exp_vendor:
                continue
            if normalize_text(exp_vendor) == normalize_text(vendor_name):
                vendor_matches.setdefault(vendor_name, []).append({
                    **exp,
                    "match_type": match_type,
                })

    if not vendor_matches:
        return signals

    # For each vendor found in item text, check if the vendor also appears
    # as a campaign donor. Match vendor name against donor name/employer.
    seen = set()  # Deduplicate by (vendor_name, council_member)
    for vendor, matched_expenditures in vendor_matches.items():
        # Sum expenditure amounts for this vendor
        total_expenditure = sum(
            float(e.get("amount", 0) or 0) for e in matched_expenditures
        )

        # Check contributions for the same vendor
        for contrib in contributions:
            donor_name = contrib.get("donor_name") or contrib.get("contributor_name", "")
            donor_employer = contrib.get("donor_employer") or contrib.get("contributor_employer", "")
            committee = contrib.get("committee_name") or contrib.get("committee", "")
            amount = float(contrib.get("amount", 0))
            council_member = contrib.get("council_member", "")

            if not donor_name:
                continue

            # Match vendor name against donor name or employer
            donor_match = False
            contrib_match_type = None
            name_result, name_type = names_match(vendor, donor_name)
            if name_result:
                donor_match = True
                contrib_match_type = f"vendor_to_donor_{name_type}"
            elif donor_employer and not _is_government_entity(donor_employer):
                emp_result, emp_type = names_match(vendor, donor_employer)
                if emp_result:
                    donor_match = True
                    contrib_match_type = f"vendor_to_employer_{emp_type}"

            if not donor_match:
                continue

            # Resolve council member from committee name if not directly available
            if not council_member and committee:
                candidate = extract_candidate_from_committee(committee)
                if candidate:
                    # Resolve against known officials
                    candidate_lower = normalize_text(candidate)
                    for member in ctx.current_officials | ctx.former_officials:
                        member_lower = normalize_text(member)
                        if candidate_lower in member_lower.split() or member_lower in candidate_lower.split():
                            council_member = member
                            break
                        m, _ = names_match(candidate, member)
                        if m:
                            council_member = member
                            break
                    if not council_member:
                        council_member = candidate

            if not council_member:
                continue

            # Deduplicate
            dedup_key = (vendor, council_member)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Compute v3 factor scores
            # Match strength: use text match type from gazetteer + donor match type
            text_match_type = matched_expenditures[0].get("match_type", "")
            base_match = _match_type_to_strength(contrib_match_type)
            vendor_strength = _match_type_to_strength(text_match_type)
            # Use the weaker of the two matches (conservative)
            match_strength = min(base_match, vendor_strength)

            # Temporal factor: check if contribution is within 24 months of expenditure
            temporal_factor = 0.5  # neutral default
            contrib_date_str = str(contrib.get("date") or contrib.get("contribution_date", ""))[:10]
            if contrib_date_str and meeting_date:
                temporal_factor = _compute_temporal_factor(contrib_date_str, meeting_date_str)

            # Financial factor: use the larger of contribution or expenditure
            combined_amount = max(amount, total_expenditure)
            financial_factor = _compute_financial_factor(combined_amount)

            # Build factual description
            exp_total_str = f"${total_expenditure:,.2f}" if total_expenditure else "undisclosed amount"
            # Include agenda title for context on why this was flagged
            title_ctx = f": {item_title.strip()[:150]}" if item_title and item_title.strip() else ""
            description = (
                f"Public records show that {vendor} received {exp_total_str} in "
                f"city expenditures and contributed ${amount:,.2f} to "
                f"{council_member}'s campaign committee ({committee}). "
                f"{vendor} appears in agenda item {item_num}{title_ctx}."
            )

            signals.append(RawSignal(
                signal_type="donor_vendor_expenditure",
                council_member=council_member,
                agenda_item_number=item_num,
                match_strength=match_strength,
                temporal_factor=temporal_factor,
                financial_factor=financial_factor,
                description=description,
                evidence=[{
                    "vendor": vendor,
                    "text_match_type": text_match_type,
                    "donor_match_type": contrib_match_type,
                    "total_expenditure": total_expenditure,
                    "contribution_amount": amount,
                    "council_member": council_member,
                    "committee": committee,
                    "contribution_date": contrib_date_str,
                    "expenditure_count": len(matched_expenditures),
                }],
                legal_reference="Gov. Code \u00a7 87100 (financial interest in governmental decision)",
                financial_amount=f"${combined_amount:,.2f}",
                match_details={
                    "vendor": vendor,
                    "text_match_type": text_match_type,
                    "donor_match_type": contrib_match_type,
                    "total_expenditure": total_expenditure,
                    "contribution_amount": amount,
                    "committee": committee,
                    "expenditure_count": len(matched_expenditures),
                    "is_sitting": council_member in ctx.current_officials,
                },
            ))

    return signals

