"""
behested_payment signal detector — extracted from conflict_scanner.py (Phase 2.2).

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


# ── S13: Influence Transparency Signal Detectors ─────────────


def signal_behested_payment(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    entities: list[str],
    behested_payments: list[dict],
    contributions: list[dict],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect behested payment connections (S13.1 — FPPC Form 803).

    When a payor in a behested payment disclosure (someone who made a payment
    at an official's request) is mentioned in an agenda item, that's a
    triangulation signal: the payor has a financial relationship with the
    official that goes beyond campaign contributions.

    Cross-references with campaign contributions for corroboration: if the
    same entity is both a behested payment payor AND a campaign donor, that
    strengthens the signal.
    """
    if not behested_payments:
        return []

    signals: list[RawSignal] = []
    norm_item = normalize_text(item_text)

    for payment in behested_payments:
        payor = payment.get("payor_name", "")
        payee = payment.get("payee_name", "")
        official = payment.get("official_name", "")
        amount = payment.get("amount", 0) or 0

        if not payor or len(payor) < 5:
            continue

        # Check if payor name appears in agenda item text
        payor_in_text, _ = cached_name_in_text(
            normalize_text(payor), norm_item, ctx.name_in_text_cache,
        )
        # Also check payee — if the beneficiary org is in the agenda text
        payee_in_text = False
        if payee and len(payee) >= 5:
            payee_in_text, _ = cached_name_in_text(
                normalize_text(payee), norm_item, ctx.name_in_text_cache,
            )

        if not payor_in_text and not payee_in_text:
            continue

        # Skip if official isn't a current/former member
        norm_official = normalize_text(official)
        is_sitting = norm_official in ctx.current_officials or any(
            names_match(official, m)[0] for m in ctx.current_officials
        )
        is_former = norm_official in ctx.former_officials or any(
            names_match(official, m)[0] for m in ctx.former_officials
        )
        if not is_sitting and not is_former:
            continue

        # Financial factor based on behested payment amount
        if amount >= 100000:
            fin_factor = 1.0
        elif amount >= 10000:
            fin_factor = 0.8
        elif amount >= 1000:
            fin_factor = 0.6
        else:
            fin_factor = 0.4

        # Match strength: payor in text is stronger than payee in text
        match_strength = 0.85 if payor_in_text else 0.70

        # Temporal factor: how recent is the behested payment?
        temporal = _compute_temporal_factor(
            payment.get("payment_date", ""),
            ctx.meeting_date,
        )

        matched_entity = payor if payor_in_text else payee
        direction = "payor" if payor_in_text else "payee (beneficiary)"

        signals.append(RawSignal(
            signal_type="behested_payment",
            council_member=official,
            agenda_item_number=item_num,
            match_strength=match_strength,
            temporal_factor=temporal,
            financial_factor=fin_factor,
            description=(
                f"Behested payment connection: {official} requested ${amount:,.2f} "
                f"payment from {payor} to {payee}. "
                f"The {direction} ({matched_entity}) appears in this agenda item."
            ),
            evidence=[
                f"FPPC Form 803: {payor} paid ${amount:,.2f} to {payee} "
                f"at request of {official}",
                f"Payment date: {payment.get('payment_date', 'unknown')}",
                f"Agenda item mentions: {matched_entity}",
            ],
            legal_reference="Cal. Gov. Code § 82015 (behested payments); FPPC Form 803",
            financial_amount=financial,
            match_details={
                "payor_name": payor,
                "payee_name": payee,
                "official_name": official,
                "amount": amount,
                "payment_date": payment.get("payment_date"),
                "matched_entity": matched_entity,
                "match_direction": direction,
                "payor_in_text": payor_in_text,
                "payee_in_text": payee_in_text,
                "sitting": is_sitting,
            },
        ))

    return signals

def signal_behested_payment_loop(
    item_num: str,
    item_title: str,
    item_text: str,
    financial: Optional[str],
    entities: list[str],
    behested_payments: list[dict],
    lobbyist_registrations: list[dict],
    contributions: list[dict],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect behested payment loops (S13.5 — influence cycle detection).

    A behested payment loop is a multi-hop influence cycle:
      1. Entity V contributes to Official X's campaign
      2. Official X behests a payment involving V (as payor or payee)
      3. V (or a connected entity) appears in an agenda item X votes on

    Each hop alone is legitimate. The *closed cycle* across three independent
    data sources is the signal — it suggests reciprocal influence.

    Optionally strengthened when V is also a registered lobbyist client,
    adding a fourth independent source.
    """
    if not behested_payments or not contributions:
        return []

    signals: list[RawSignal] = []
    norm_item = normalize_text(item_text)

    # Index contributions by normalized donor/employer for fast lookup
    contrib_by_entity: dict[str, list[dict]] = {}
    for contrib in contributions:
        for field_name in ("donor_name", "contributor_name", "donor_employer", "contributor_employer"):
            val = (contrib.get(field_name) or "").strip()
            if val and len(val) >= 5:
                norm_val = normalize_text(val)
                contrib_by_entity.setdefault(norm_val, []).append(contrib)

    # Index lobbyist clients for corroboration (optional 4th source)
    lobbyist_clients: dict[str, dict] = {}
    for reg in lobbyist_registrations:
        client = normalize_text(reg.get("client_name", ""))
        if client and len(client) >= 5:
            lobbyist_clients[client] = reg

    for payment in behested_payments:
        payor = (payment.get("payor_name") or "").strip()
        payee = (payment.get("payee_name") or "").strip()
        official = (payment.get("official_name") or "").strip()
        amount = payment.get("amount", 0) or 0

        if not official or (not payor and not payee):
            continue

        # Resolve official to a known council member
        norm_official = normalize_text(official)
        is_sitting = norm_official in ctx.current_officials or any(
            names_match(official, m)[0] for m in ctx.current_officials
        )
        is_former = norm_official in ctx.former_officials or any(
            names_match(official, m)[0] for m in ctx.former_officials
        )
        if not is_sitting and not is_former:
            continue

        resolved_official = norm_official
        for m in ctx.current_officials | ctx.former_officials:
            if names_match(official, m)[0]:
                resolved_official = m
                break

        # Check both payor and payee as potential loop entities
        for entity, role in [(payor, "payor"), (payee, "payee")]:
            if not entity or len(entity) < 5:
                continue

            norm_entity = normalize_text(entity)

            # Hop 3: Does this entity appear in the agenda item text?
            entity_in_text, _ = cached_name_in_text(
                norm_entity, norm_item, ctx.name_in_text_cache,
            )
            if not entity_in_text:
                continue

            # Hop 1: Does this entity (or related donor/employer) contribute
            # to this official's campaign?
            matching_contribs = []
            for norm_key, contribs in contrib_by_entity.items():
                if norm_key == norm_entity or (
                    len(norm_key) >= 10
                    and (norm_key in norm_entity or norm_entity in norm_key)
                ):
                    for c in contribs:
                        # Resolve contribution recipient to official
                        candidate = (
                            c.get("council_member")
                            or c.get("committee_name")
                            or ""
                        )
                        if not candidate:
                            continue
                        candidate_name = (
                            extract_candidate_from_committee(candidate)
                            if "committee" in candidate.lower()
                            else candidate
                        )
                        if candidate_name and names_match(
                            candidate_name, resolved_official
                        )[0]:
                            matching_contribs.append(c)

            if not matching_contribs:
                continue

            # ── Full loop confirmed: contribution → behested → agenda ──

            total_contrib = sum(
                (c.get("amount", 0) or 0) for c in matching_contribs
            )

            # Financial factor: combine behested amount + contribution total
            combined = amount + total_contrib
            if combined >= 100000:
                fin_factor = 1.0
            elif combined >= 25000:
                fin_factor = 0.85
            elif combined >= 5000:
                fin_factor = 0.7
            elif combined >= 1000:
                fin_factor = 0.55
            else:
                fin_factor = 0.4

            # Match strength: loop is inherently high-confidence because
            # three independent sources corroborate
            match_strength = 0.90

            # Temporal factor: use behested payment date
            temporal = _compute_temporal_factor(
                payment.get("payment_date", ""),
                ctx.meeting_date,
            )

            # Corroboration: check if entity is also a lobbyist client
            lobbyist_match = None
            for client_norm, reg in lobbyist_clients.items():
                if client_norm == norm_entity or (
                    len(client_norm) >= 10
                    and (client_norm in norm_entity or norm_entity in client_norm)
                ):
                    lobbyist_match = reg
                    break

            # Build evidence chain
            evidence = [
                f"Campaign contribution: {entity} contributed "
                f"${total_contrib:,.2f} ({len(matching_contribs)} contribution(s)) "
                f"to {resolved_official}",
                f"Behested payment: {resolved_official} requested ${amount:,.2f} "
                f"payment — {payor} → {payee} (FPPC Form 803)",
                f"Agenda item: {entity} appears in item {item_num}",
            ]

            if lobbyist_match:
                evidence.append(
                    f"Lobbyist registration: {entity} is a client of "
                    f"{lobbyist_match.get('lobbyist_name', 'unknown')} "
                    f"(4th independent source)"
                )
                # Boost match strength for 4-source corroboration
                match_strength = 0.95

            description = (
                f"Influence loop: {entity} contributed ${total_contrib:,.2f} to "
                f"{resolved_official}'s campaign. {resolved_official} then "
                f"requested a ${amount:,.2f} behested payment "
                f"({'from' if role == 'payor' else 'to'} {entity}). "
                f"{entity} now appears in this agenda item."
            )
            if lobbyist_match:
                description += (
                    f" {entity} is also a registered lobbyist client of "
                    f"{lobbyist_match.get('lobbyist_name', 'unknown')}."
                )

            signals.append(RawSignal(
                signal_type="behested_payment_loop",
                council_member=resolved_official,
                agenda_item_number=item_num,
                match_strength=match_strength,
                temporal_factor=temporal,
                financial_factor=fin_factor,
                description=description,
                evidence=evidence,
                legal_reference=(
                    "Cal. Gov. Code § 82015 (behested payments); "
                    "Cal. Gov. Code § 84308 (campaign contributions); "
                    "FPPC Form 803"
                ),
                financial_amount=financial,
                match_details={
                    "loop_entity": entity,
                    "loop_role": role,
                    "payor_name": payor,
                    "payee_name": payee,
                    "official_name": resolved_official,
                    "behested_amount": amount,
                    "contribution_total": total_contrib,
                    "contribution_count": len(matching_contribs),
                    "combined_financial": combined,
                    "lobbyist_corroboration": lobbyist_match is not None,
                    "lobbyist_name": (
                        lobbyist_match.get("lobbyist_name")
                        if lobbyist_match else None
                    ),
                    "sitting": is_sitting,
                    "payment_date": payment.get("payment_date"),
                },
            ))

    return signals
