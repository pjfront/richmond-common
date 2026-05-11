"""
campaign_contribution signal detector — extracted from conflict_scanner.py (Phase 2.2).

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


# ── v3 Signal Detectors ──────────────────────────────────────
# Each detector analyzes one data source and returns list[RawSignal].
# Called per agenda item by scan_meeting_json.

def signal_campaign_contribution(
    item_num: str,
    item_title: str,
    item_text: str,
    original_text: str,
    financial: Optional[str],
    entities: list[str],
    text_words: set,
    contributions: list[dict],
    ctx: _ScanContext,
    contrib_word_index: dict[str, list[int]] | None = None,
) -> list[RawSignal]:
    """Detect campaign contribution signals for one agenda item.

    Checks each contribution's donor name/employer against the item text.
    Aggregates multiple contributions from the same donor to the same
    committee. Returns one RawSignal per (donor-committee, item) pair.

    Mutates ctx.seen_contributions, ctx.filter_counts, ctx.audit_logger.
    """
    signals: list[RawSignal] = []

    # Aggregate matches per donor-item pair: maps
    # (norm_donor_name, committee) -> list of matched contributions
    donor_item_matches: dict[str, list[dict]] = {}

    # O2: When word index is available, only iterate candidate contributions
    # that share at least one word with the item text.
    if contrib_word_index is not None:
        candidate_indices: set[int] = set()
        for word in text_words:
            candidate_indices.update(contrib_word_index.get(word, ()))
        contributions_to_check = [(contributions[idx], True) for idx in candidate_indices]
    else:
        contributions_to_check = [(c, False) for c in contributions]

    for contribution, skip_word_prescreen in contributions_to_check:
        donor_name = contribution.get("donor_name") or contribution.get("contributor_name", "")
        donor_employer = contribution.get("donor_employer") or contribution.get("contributor_employer", "")
        council_member = contribution.get("council_member", "")
        committee = contribution.get("committee_name") or contribution.get("committee", "")
        amount = contribution.get("amount", 0)

        # De-duplicate
        dedup_key = (donor_name, str(amount), contribution.get("date", ""), committee)
        if dedup_key in ctx.seen_contributions:
            ctx.filter_counts["filtered_dedup"] += 1
            continue

        # Use pre-cached normalized values from prefilter_contributions() (O1),
        # falling back to computing them for non-batch callers.
        norm_donor = contribution.get("_norm_donor") or normalize_text(donor_name)

        # Skip council member donors (their names appear in items naturally)
        # Also check if donor is a committee whose candidate is a council member
        is_council_member_donor = any(
            cm_name in norm_donor or norm_donor in cm_name
            for cm_name in ctx.council_member_names
            if len(cm_name) > 4
        )
        if not is_council_member_donor:
            donor_cand = extract_candidate_from_committee(donor_name)
            if donor_cand:
                norm_cand = normalize_text(donor_cand)
                is_council_member_donor = any(
                    cm_name in norm_cand or norm_cand in cm_name
                    for cm_name in ctx.council_member_names
                    if len(cm_name) > 4
                )

        # Skip government entity donors
        is_government_donor = _is_government_entity(donor_name)

        # Skip self-donations (direct name match or committee-to-committee transfer)
        norm_committee = contribution.get("_norm_committee") or normalize_text(committee)
        is_self_donation = (
            len(norm_donor) > 4
            and norm_donor in norm_committee
        )
        if not is_self_donation:
            donor_cand_name = extract_candidate_from_committee(donor_name)
            committee_cand_name = extract_candidate_from_committee(committee)
            if donor_cand_name and committee_cand_name:
                match, _ = names_match(donor_cand_name, committee_cand_name)
                is_self_donation = match

        if is_council_member_donor or is_government_donor or is_self_donation:
            if is_council_member_donor:
                ctx.filter_counts["filtered_council_member"] += 1
                ctx.audit_logger.log_decision(MatchingDecision(
                    donor_name=donor_name,
                    donor_employer=donor_employer,
                    agenda_item_number=item_num,
                    agenda_text_preview=item_text[:500],
                    match_type="suppressed_council_member",
                    confidence=0.0,
                    matched=False,
                ))
            elif is_self_donation:
                ctx.filter_counts["filtered_self_donation"] += 1
                ctx.audit_logger.log_decision(MatchingDecision(
                    donor_name=donor_name,
                    donor_employer=donor_employer,
                    agenda_item_number=item_num,
                    agenda_text_preview=item_text[:500],
                    match_type="suppressed_self_donation",
                    confidence=0.0,
                    matched=False,
                ))
            elif is_government_donor:
                ctx.filter_counts["filtered_govt_donor"] += 1
            continue

        # Word-overlap pre-screen: skip when using inverted index (O2),
        # since the index already selected candidates by word overlap.
        if not skip_word_prescreen:
            donor_words = contribution.get("_donor_words") or set(w for w in norm_donor.split() if len(w) >= 4)
            employer_words = contribution.get("_employer_words") or (
                set(w for w in normalize_text(donor_employer).split() if len(w) >= 4) if donor_employer else set()
            )
            if not (donor_words & text_words) and not (employer_words & text_words):
                continue

        # Check donor name against item text (O3: use cached version)
        _nit_cache = ctx.name_in_text_cache
        donor_match, match_type = cached_name_in_text(donor_name, original_text, _nit_cache)
        if not donor_match:
            enriched_match, enriched_type = cached_name_in_text(donor_name, item_text, _nit_cache)
            if enriched_match and enriched_type in ('exact', 'phrase'):
                donor_match = True
                match_type = enriched_type
        # Try aliases
        if not donor_match:
            for alias in ctx.alias_groups.get(norm_donor, set()):
                if alias == norm_donor:
                    continue
                alias_match, alias_type = cached_name_in_text(alias, original_text, _nit_cache)
                if alias_match:
                    donor_match = True
                    match_type = f"alias_{alias_type}"
                    break
        if not donor_match and donor_employer:
            # Skip generic government employers
            norm_employer = normalize_text(donor_employer)
            is_generic_employer = any(
                norm_employer.startswith(prefix) for prefix in [
                    "city of", "city and county", "city &", "city & county",
                    "county of", "state of", "town of",
                    "district of", "village of", "borough of",
                ]
            ) or any(
                norm_employer.endswith(suffix) for suffix in [
                    " county", " city", " state",
                ]
            ) or any(
                generic in norm_employer for generic in [
                    "unified school district", "transit district",
                    "community college", "city college",
                    "self employed", "retired",
                    "not employed", "none", "n/a", "caltrans",
                    "contra costa",
                    "alameda county", "marin county", "solano county",
                    "san francisco", "san mateo",
                    "city attorney", "city national",
                    "public defender", "district attorney",
                    "sheriff", "fire department", "police department",
                ]
            ) or norm_employer in {
                "contractor", "independent contractor", "consultant",
                "executive director", "director", "manager",
                "government", "local government", "federal government",
                "state government", "ad review",
            }

            if not is_generic_employer:
                original_entities = extract_entity_names(original_text)
                employer_match = False
                for entity in original_entities:
                    em, em_type = names_match(donor_employer, entity)
                    if em:
                        employer_match = True
                        match_type = 'employer_match'
                        break
                if not employer_match:
                    norm_orig = normalize_text(original_text)
                    if len(norm_employer) >= 15 and norm_employer in norm_orig:
                        employer_match = True
                        match_type = 'employer_substring'
                donor_match = employer_match

        if donor_match:
            ctx.seen_contributions.add(dedup_key)

            # Aggregate by resolved candidate, not committee name.
            # "Cesar Zepeda for City Council 2022" and "...2026" → same person.
            agg_candidate = extract_candidate_from_committee(committee)
            agg_official = normalize_text(agg_candidate) if agg_candidate else normalize_text(committee)
            agg_key = f"{norm_donor}||{agg_official}"
            if agg_key not in donor_item_matches:
                donor_item_matches[agg_key] = []
            donor_item_matches[agg_key].append({
                "donor_name": donor_name,
                "donor_employer": donor_employer,
                "council_member": council_member,
                "committee": committee,
                "amount": amount,
                "date": contribution.get("date", ""),
                "filing_id": contribution.get("filing_id", ""),
                "source": contribution.get("source", ""),
                "match_type": match_type,
            })

    # Create one signal per donor-official pair with aggregated totals
    for agg_key, matched_contribs in donor_item_matches.items():
        total_amount = sum(c["amount"] for c in matched_contribs)
        num_contribs = len(matched_contribs)

        # Materiality threshold
        if total_amount < 100:
            continue

        rep = matched_contribs[0]
        best_match_type = rep["match_type"]
        for c in matched_contribs:
            if c["match_type"] == "exact":
                best_match_type = "exact"
                break

        # Determine candidate and sitting status
        candidate = extract_candidate_from_committee(rep["committee"])
        sitting = is_sitting_council_member(
            candidate, ctx.current_officials, ctx.alias_groups
        ) if candidate else False
        council_member_label = rep["council_member"]
        if candidate:
            if sitting:
                council_member_label = f"{candidate} (sitting council member)"
            else:
                council_member_label = f"{candidate} (not a current council member)"
        elif not council_member_label:
            council_member_label = rep["committee"]

        # Compute v3 factor values
        donor_name_words = set(normalize_text(rep["donor_name"]).split())
        match_strength = _match_type_to_strength(best_match_type, donor_name_words)

        # Temporal: use most recent contribution date and compute direction
        dates = sorted(
            (c["date"] for c in matched_contribs if c["date"]),
            reverse=True,
        )
        most_recent_date = dates[0] if dates else ""
        temporal_factor = _compute_temporal_factor(most_recent_date, ctx.meeting_date)

        # Classify each contribution as pre-vote or post-vote
        pre_vote_contribs = []
        post_vote_contribs = []
        for c in matched_contribs:
            direction = _compute_temporal_direction(c["date"], ctx.meeting_date)
            if direction == "post_vote":
                post_vote_contribs.append(c)
            else:
                pre_vote_contribs.append(c)

        # Overall direction: "mixed" if both, else whichever is present
        if pre_vote_contribs and post_vote_contribs:
            temporal_direction = "mixed"
        elif post_vote_contribs:
            temporal_direction = "post_vote"
        else:
            temporal_direction = "pre_vote"

        financial_factor = _compute_financial_factor(total_amount)

        # Build description
        raw_employer = rep["donor_employer"] or ""
        cleaned_employer = raw_employer.strip()
        if cleaned_employer.lower() in {"", "none", "n/a", "na", "not employed", "unemployed", "-"}:
            cleaned_employer = ""
        employer_note = f" ({cleaned_employer})" if cleaned_employer else ""

        # Direction context for description
        if temporal_direction == "post_vote":
            direction_note = " (donated after this vote)"
        elif temporal_direction == "mixed":
            pre_amt = sum(c["amount"] for c in pre_vote_contribs)
            post_amt = sum(c["amount"] for c in post_vote_contribs)
            direction_note = (
                f" (${pre_amt:,.2f} before vote, ${post_amt:,.2f} after)"
            )
        else:
            direction_note = ""

        # Collect unique committees for description
        unique_committees = list(dict.fromkeys(c["committee"] for c in matched_contribs))

        # Connection clause: explains WHY this donor is flagged on this item
        connection = _build_connection_clause(
            match_type=best_match_type,
            item_num=item_num,
            item_title=item_title,
            donor_name=rep["donor_name"],
            donor_employer=rep["donor_employer"],
        )

        if num_contribs == 1:
            description = (
                f"{rep['donor_name']}{employer_note} contributed "
                f"${total_amount:,.2f} to {rep['committee']} on "
                f"{rep['date']}{direction_note}.{connection}"
            )
        else:
            all_dates = sorted(c["date"] for c in matched_contribs if c["date"])
            date_range = f"{all_dates[0]} to {all_dates[-1]}" if all_dates else "various dates"
            # Use candidate name when contributions span multiple committees
            if len(unique_committees) > 1 and candidate:
                recipient_label = candidate
            else:
                recipient_label = rep["committee"]
            description = (
                f"{rep['donor_name']}{employer_note} made {num_contribs} contributions "
                f"totaling ${total_amount:,.2f} to {recipient_label} "
                f"({date_range}){direction_note}.{connection}"
            )

        if candidate and not sitting:
            description += (
                f"\n   NOTE: {candidate} is not a current council member "
                f"and does not vote on this item. This is disclosed for "
                f"transparency but represents a weaker conflict signal."
            )

        # B.51: Compute anomaly factor from contribution baselines
        signal_anomaly = DEFAULT_ANOMALY_FACTOR
        if ctx.contribution_baselines is not None:
            signal_anomaly = compute_anomaly_factor(
                amount=total_amount,
                baselines=ctx.contribution_baselines,
                contribution_date=most_recent_date,
                meeting_date=ctx.meeting_date,
            )

        # Evidence
        most_recent = max(matched_contribs, key=lambda c: c.get("filing_id", ""))
        evidence = [
            f"Source: {most_recent['source'] or 'unknown'}, "
            f"Filing ID: {most_recent['filing_id'] or 'unknown'}"
        ]
        if num_contribs > 1:
            evidence.append(f"Aggregated from {num_contribs} contribution records")
        if len(unique_committees) > 1:
            evidence.append(f"Across {len(unique_committees)} campaign committees: {', '.join(unique_committees)}")

        signals.append(RawSignal(
            signal_type="campaign_contribution",
            council_member=council_member_label,
            agenda_item_number=item_num,
            match_strength=match_strength,
            temporal_factor=temporal_factor,
            financial_factor=financial_factor,
            description=description,
            evidence=evidence,
            legal_reference="Gov. Code SS 87100-87105, 87300 (financial interest in governmental decision)",
            financial_amount=financial,
            anomaly_factor=signal_anomaly,
            match_details={
                "donor_name": rep["donor_name"],
                "donor_employer": rep["donor_employer"],
                "committee": rep["committee"],
                "all_committees": unique_committees,
                "candidate": candidate,
                "is_sitting": sitting,
                "match_type": best_match_type,
                "total_amount": total_amount,
                "num_contributions": num_contribs,
                "most_recent_date": most_recent_date,
                "temporal_direction": temporal_direction,
                "pre_vote_count": len(pre_vote_contribs),
                "post_vote_count": len(post_vote_contribs),
                "pre_vote_total": sum(c["amount"] for c in pre_vote_contribs),
                "post_vote_total": sum(c["amount"] for c in post_vote_contribs),
                "anomaly_factor": signal_anomaly,
            },
        ))
        ctx.filter_counts["passed_to_flag"] += 1

        # Audit log
        ctx.audit_logger.log_decision(MatchingDecision(
            donor_name=rep["donor_name"],
            donor_employer=rep["donor_employer"],
            agenda_item_number=item_num,
            agenda_text_preview=item_text[:500],
            match_type=best_match_type,
            confidence=match_strength,  # v3: log match_strength as the raw confidence
            matched=True,
        ))

    return signals

