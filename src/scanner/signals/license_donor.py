"""
license_donor signal detector — extracted from conflict_scanner.py (Phase 2.2).

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


def signal_license_donor(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    licenses: list[dict],
    contributions: list[dict],
    expenditures: list[dict],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect business-license-holder → campaign-donor/vendor cross-reference.

    Cross-references business license holders (from city_licenses) against
    both campaign contributors AND city expenditure vendors. A licensed
    business that also donates to council campaigns and/or receives city
    payments represents a three-way connection worth surfacing.

    This extends cross-reference #1 (donor → contract recipient) with
    business registration data — adding licensing as a corroborating
    data source for entity presence in the city.

    Returns list[RawSignal] for integration into v3 composite confidence.
    """
    signals: list[RawSignal] = []
    if not licenses or (not contributions and not expenditures):
        return signals

    meeting_date_str = ctx.meeting_date
    expenditures = expenditures or []

    # Build company gazetteer from licenses
    company_licenses: dict[str, list[dict]] = {}
    for lic in licenses:
        company = (
            lic.get("normalized_company")
            or lic.get("company", "")
        ).strip()
        if not company or len(company) < 10:
            continue
        norm_company = normalize_text(company)
        company_licenses.setdefault(norm_company, []).append(lic)

    if not company_licenses:
        return signals

    # Step 1: Check which licensed companies appear in the agenda item text
    matched_companies: dict[str, tuple[str, list[dict]]] = {}
    for norm_company, lic_list in company_licenses.items():
        original_name = (
            lic_list[0].get("company") or lic_list[0].get("normalized_company", "")
        ).strip()
        is_match, match_type = cached_name_in_text(
            original_name, item_text, ctx.name_in_text_cache
        )
        if is_match:
            matched_companies[norm_company] = (match_type, lic_list)
            continue
        # Also try DBA name
        dba = (lic_list[0].get("company_dba") or "").strip()
        if dba and len(dba) >= 10:
            is_match, match_type = cached_name_in_text(
                dba, item_text, ctx.name_in_text_cache
            )
            if is_match:
                matched_companies[norm_company] = (match_type, lic_list)

    if not matched_companies:
        return signals

    # Step 2: Cross-reference matched companies against contributions + expenditures
    seen = set()
    for norm_company, (text_match_type, lic_list) in matched_companies.items():
        original_name = (
            lic_list[0].get("company") or lic_list[0].get("normalized_company", "")
        ).strip()
        dba_name = (lic_list[0].get("company_dba") or "").strip()
        # Collect all name variants to match against contributions
        match_names = [original_name]
        if dba_name and len(dba_name) >= 10:
            match_names.append(dba_name)

        # Check if this company is also an expenditure vendor
        vendor_match = False
        total_expenditure = 0.0
        for exp in expenditures:
            exp_vendor = (
                exp.get("normalized_vendor") or exp.get("vendor_name", "")
            )
            if not exp_vendor:
                continue
            for match_name in match_names:
                m, _ = names_match(match_name, exp_vendor)
                if m:
                    vendor_match = True
                    total_expenditure += float(exp.get("amount", 0) or 0)
                    break

        # Check if this company is also a campaign donor
        for contrib in contributions:
            donor_name = contrib.get("donor_name") or contrib.get("contributor_name", "")
            donor_employer = (
                contrib.get("donor_employer") or contrib.get("contributor_employer", "")
            )
            committee = contrib.get("committee_name") or contrib.get("committee", "")
            amount = float(contrib.get("amount", 0) or 0)
            council_member = contrib.get("council_member", "")

            if not donor_name:
                continue
            if amount < 100:
                continue

            # Match license holder (or DBA) against donor name or employer
            donor_match = False
            contrib_match_type = None
            for match_name in match_names:
                name_result, name_type = names_match(match_name, donor_name)
                if name_result:
                    donor_match = True
                    contrib_match_type = f"licensee_to_donor_{name_type}"
                    break
            if not donor_match:
                for match_name in match_names:
                    if donor_employer:
                        emp_result, emp_type = names_match(match_name, donor_employer)
                        if emp_result:
                            donor_match = True
                            contrib_match_type = f"licensee_to_employer_{emp_type}"
                            break

            if not donor_match:
                continue

            # Resolve council member
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
            dedup_key = (norm_company, council_member, item_num)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Compute v3 factor scores
            base_match = _match_type_to_strength(
                contrib_match_type,
                donor_name_words=set(normalize_text(donor_name).split()),
            )
            text_strength = _match_type_to_strength(text_match_type)
            match_strength = min(base_match, text_strength)

            # Boost match strength slightly if also a vendor (corroborating evidence)
            if vendor_match:
                match_strength = min(match_strength * 1.1, 1.0)

            # Temporal factor
            temporal_factor = 0.5
            contrib_date_str = str(
                contrib.get("date") or contrib.get("contribution_date", "")
            )[:10]
            if contrib_date_str and meeting_date_str:
                temporal_factor = _compute_temporal_factor(
                    contrib_date_str, meeting_date_str
                )

            # Financial factor: max of contribution, expenditure, or zero
            combined_amount = max(amount, total_expenditure) if vendor_match else amount
            financial_factor = _compute_financial_factor(combined_amount)

            # License metadata
            license_count = len(lic_list)
            business_types = list({
                lic.get("business_type", "unknown")
                for lic in lic_list
                if lic.get("business_type")
            })

            # Build factual description
            title_ctx = (
                f": {item_title.strip()[:150]}"
                if item_title and item_title.strip()
                else ""
            )
            vendor_clause = (
                f" and received ${total_expenditure:,.2f} in city expenditures"
                if vendor_match and total_expenditure > 0
                else ""
            )
            description = (
                f"Public records show that {original_name} holds "
                f"{license_count} Richmond business license(s)"
                f"{vendor_clause} and contributed ${amount:,.2f} to "
                f"{council_member}'s campaign committee ({committee}). "
                f"{original_name} appears in agenda item "
                f"{item_num}{title_ctx}."
            )

            signals.append(RawSignal(
                signal_type="license_donor",
                council_member=council_member,
                agenda_item_number=item_num,
                match_strength=match_strength,
                temporal_factor=temporal_factor,
                financial_factor=financial_factor,
                description=description,
                evidence=[{
                    "company": original_name,
                    "text_match_type": text_match_type,
                    "donor_match_type": contrib_match_type,
                    "contribution_amount": amount,
                    "license_count": license_count,
                    "business_types": business_types,
                    "vendor_match": vendor_match,
                    "total_expenditure": total_expenditure,
                    "council_member": council_member,
                    "committee": committee,
                    "contribution_date": contrib_date_str,
                }],
                legal_reference=(
                    "Gov. Code § 87100 (financial interest in governmental decision)"
                ),
                financial_amount=f"${combined_amount:,.2f}",
                match_details={
                    "company": original_name,
                    "text_match_type": text_match_type,
                    "donor_match_type": contrib_match_type,
                    "contribution_amount": amount,
                    "license_count": license_count,
                    "business_types": business_types,
                    "vendor_match": vendor_match,
                    "total_expenditure": total_expenditure,
                    "committee": committee,
                    "is_sitting": council_member in ctx.current_officials,
                },
            ))

    return signals

