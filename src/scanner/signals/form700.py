"""
form700 signal detector — extracted from conflict_scanner.py (Phase 2.2).

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


def _extract_street_names(text: str) -> set[str]:
    """Extract normalized street names from text for proximity matching.

    Looks for patterns like '3816 Waller Ave', '101 S 31st Street',
    '500 Harbour Way', etc. Requires a house number prefix to avoid
    false matches on generic text containing street suffix words.
    Returns the street name portion (without the house number) in
    lowercase for comparison.
    """
    street_suffixes = (
        r"(?:ave(?:nue)?|st(?:reet)?|blvd|boulevard|dr(?:ive)?|rd|road|"
        r"ct|court|pl(?:ace)?|ln|lane|way|cir(?:cle)?|ter(?:race)?|"
        r"pkwy|parkway|hw?y|highway)"
    )
    # Require house number, then 1-3 word tokens as the street name
    pattern = rf"\b\d{{1,5}}\s+((?:[A-Za-z0-9]+\s+){{0,2}}[A-Za-z0-9]+)\s+{street_suffixes}\b"
    streets = set()
    for m in re.finditer(pattern, text.lower()):
        street_part = m.group(1).strip()
        # Filter out very short or generic matches
        if len(street_part) >= 3 and street_part not in {"the", "and", "for", "all"}:
            streets.add(street_part)
    return streets


def _extract_addresses_from_text(text: str) -> set[str]:
    """Extract full address-like patterns from agenda item text.

    Returns normalized address strings for matching against
    Form 700 property locations.
    """
    # Match street addresses: number + street name
    pattern = r"\b(\d{1,5}\s+(?:[NSEW]\.?\s+)?[\w]+(?:\s+[\w]+){0,3}\s+(?:Ave(?:nue)?|St(?:reet)?|Blvd|Boulevard|Dr(?:ive)?|Rd|Road|Ct|Court|Pl(?:ace)?|Ln|Lane|Way|Cir(?:cle)?|Ter(?:race)?|Pkwy|Parkway))\b"
    addresses = set()
    for m in re.finditer(pattern, text, re.IGNORECASE):
        addresses.add(m.group(1).lower().strip())
    return addresses


def _property_matches_item(
    interest: dict, item_text: str, item_streets: set[str], item_addresses: set[str]
) -> tuple[bool, float, str]:
    """Check if a Form 700 property interest is potentially relevant to an agenda item.

    Returns (is_match, match_strength, match_reason).

    Match levels:
    - Address match (street number + name): strength 0.6 (strong)
    - Street name match: strength 0.4 (moderate — same street, proximity plausible)
    - No match: (False, 0, "")
    """
    prop_desc = (interest.get("description") or "").lower()
    prop_location = (interest.get("location") or "").lower()
    prop_text = f"{prop_desc} {prop_location}"

    # Extract street names from the property
    prop_streets = _extract_street_names(prop_text)
    prop_addresses = _extract_addresses_from_text(prop_text)

    # Check for address-level match (number + street)
    for p_addr in prop_addresses:
        for i_addr in item_addresses:
            # Normalize and compare — allow partial match on the number+street
            p_words = p_addr.split()
            i_words = i_addr.split()
            if len(p_words) >= 2 and len(i_words) >= 2:
                # Same street number and overlapping street name words
                if p_words[0] == i_words[0]:  # same house number
                    p_street = " ".join(p_words[1:])
                    i_street = " ".join(i_words[1:])
                    if p_street in i_street or i_street in p_street:
                        return (True, 0.6, f"address match: {p_addr}")

    # Check for street-name-level match
    common_streets = prop_streets & item_streets
    if common_streets:
        return (True, 0.4, f"street match: {', '.join(common_streets)}")

    return (False, 0.0, "")


def signal_form700_property(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    form700_interests: list[dict],
) -> list[RawSignal]:
    """Detect Form 700 real property signals for a land-use agenda item.

    Only fires when a specific address or street in the agenda item matches
    a council member's Form 700 property disclosure. Generic land-use keywords
    alone are insufficient — the item must reference a location that overlaps
    with a disclosed property interest.

    This implements the principle from 2 CCR S 18702.2: real property interests
    are relevant when the subject property is within 500 feet. Without geocoding,
    we approximate with street-name and address matching.
    """
    signals: list[RawSignal] = []

    # Pre-extract streets and addresses from the agenda item
    norm_text = item_text.lower()
    item_streets = _extract_street_names(norm_text)
    item_addresses = _extract_addresses_from_text(item_text)

    # If the item doesn't mention any specific location, no property signal
    if not item_streets and not item_addresses:
        return signals

    for interest in form700_interests:
        if interest.get("interest_type") == "real_property":
            is_match, match_strength, match_reason = _property_matches_item(
                interest, item_text, item_streets, item_addresses
            )
            if not is_match:
                continue

            signals.append(RawSignal(
                signal_type="form700_real_property",
                council_member=interest["council_member"],
                agenda_item_number=item_num,
                match_strength=match_strength,
                temporal_factor=0.5,    # neutral: only have filing year
                financial_factor=0.3,   # low: property value unknown
                description=(
                    f"{interest['council_member']}'s Form 700 "
                    f"(filed {interest.get('filing_year', 'unknown')}) lists "
                    f"real property: {interest.get('description', 'N/A')}. "
                    f"Proximity match: {match_reason}."
                    + _build_connection_clause("property_match", item_num, item_title)
                ),
                evidence=[
                    f"Form 700, Schedule A-2, {interest.get('filing_year', '')}",
                    f"Source: {interest.get('source_url', 'FPPC')}",
                    f"Match basis: {match_reason}",
                ],
                legal_reference=(
                    "Gov. Code S 87100 (disqualification when official has "
                    "financial interest in decision). See also 2 CCR S 18702.2 "
                    "(real property interests within 500 feet of subject property)."
                ),
                financial_amount=financial,
                match_details={
                    "interest_type": "real_property",
                    "interest_description": interest.get("description", ""),
                    "interest_location": interest.get("location", ""),
                    "filing_year": interest.get("filing_year", ""),
                    "match_reason": match_reason,
                    "match_strength": match_strength,
                },
            ))
    return signals


def signal_form700_income(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    entities: list[str],
    form700_interests: list[dict],
) -> list[RawSignal]:
    """Detect Form 700 income/investment signals for an agenda item.

    Checks if entities in the agenda item match Form 700
    income/investment source descriptions.
    """
    signals: list[RawSignal] = []
    for interest in form700_interests:
        if interest.get("interest_type") in ("income", "investment"):
            int_desc = normalize_text(interest.get("description", ""))
            if int_desc and len(int_desc) > 4:
                for entity in entities:
                    is_match, match_type = names_match(int_desc, entity)
                    if is_match:
                        # Compute match_strength from match type
                        match_strength = _match_type_to_strength(match_type)

                        signals.append(RawSignal(
                            signal_type=f"form700_{interest['interest_type']}",
                            council_member=interest["council_member"],
                            agenda_item_number=item_num,
                            match_strength=match_strength,
                            temporal_factor=0.5,    # neutral: only have filing year
                            financial_factor=0.5,   # moderate: income/investment reported
                            description=(
                                f"{interest['council_member']}'s Form 700 "
                                f"(filed {interest.get('filing_year', 'unknown')}) lists "
                                f"{interest['interest_type']}: {interest.get('description', 'N/A')}."
                                + _build_connection_clause(
                                    match_type, item_num, item_title,
                                    donor_employer=interest.get("description", ""),
                                )
                            ),
                            evidence=[
                                f"Form 700, {interest.get('filing_year', '')}",
                                f"Source: {interest.get('source_url', 'FPPC')}",
                            ],
                            legal_reference="Gov. Code SS 87100-87105 (financial interest in governmental decision)",
                            financial_amount=financial,
                            match_details={
                                "interest_type": interest["interest_type"],
                                "interest_description": interest.get("description", ""),
                                "filing_year": interest.get("filing_year", ""),
                                "matched_entity": entity,
                                "match_type": match_type,
                            },
                        ))
                        break  # one signal per interest, same as v2
    return signals


