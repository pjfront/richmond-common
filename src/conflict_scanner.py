"""
Richmond Transparency Project — Conflict of Interest Scanner

Cross-references three data sources to detect potential conflicts:
  1. Campaign contributions (CAL-ACCESS / City Clerk Form 460)
  2. Economic interests (FPPC Form 700)
  3. Agenda items (vendor names, dollar amounts, categories)

The scanner works in two modes:
  - Database mode: queries Layer 2 tables for cross-references
  - JSON mode: works directly with extracted JSON + contribution lists
    (for pre-database use and testing)

This is NOT a legal determination. All flags include the relevant
Government Code sections and are labeled as informational.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from scan_audit import MatchingDecision, ScanAuditSummary, ScanAuditLogger


# ── Data Types ───────────────────────────────────────────────

@dataclass
class ConflictFlag:
    """A potential conflict of interest detected by the scanner."""
    agenda_item_number: str
    agenda_item_title: str
    council_member: str
    flag_type: str           # 'campaign_contribution', 'vendor_donor_match', 'form700_real_property', 'form700_income'
    description: str
    evidence: list[str]
    confidence: float        # 0.0-1.0
    legal_reference: str
    financial_amount: Optional[str] = None  # from the agenda item
    publication_tier: int = 3  # 1=Potential Conflict, 2=Financial Connection, 3=internal only


@dataclass
class VendorDonorMatch:
    """A match between a vendor in an agenda item and a campaign donor."""
    vendor_name: str         # from agenda item
    donor_name: str          # from contributions
    donor_employer: str      # from contributions
    match_type: str          # 'exact_name', 'employer_match', 'fuzzy_name'
    council_member: str
    committee_name: str
    contribution_amount: float
    contribution_date: str
    filing_id: str
    source: str


@dataclass
class ScanResult:
    """Complete scan result for one meeting's agenda."""
    meeting_date: str
    meeting_type: str
    total_items_scanned: int
    flags: list[ConflictFlag]
    vendor_matches: list[VendorDonorMatch]
    clean_items: list[str]   # item numbers with no flags
    enriched_items: list[str] = field(default_factory=list)  # items with eSCRIBE attachment text
    scan_run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    audit_log: ScanAuditLogger = field(default=None)


# ── Text Matching Utilities ──────────────────────────────────

# Richmond City Council — current and recent members.
# Used as fallback when members_present is empty (e.g., eSCRIBE agendas
# which don't include attendance data).  Also includes former members
# whose names appear in contribution data.
#
# IMPORTANT: keep CURRENT_COUNCIL_MEMBERS accurate — it determines
# whether a campaign contribution flag indicates a *sitting official*
# (who can vote on the agenda item) vs. a non-sitting candidate.
CURRENT_COUNCIL_MEMBERS = {
    # Verified from ci.richmond.ca.us/29/City-Council and
    # Sept 23, 2025 meeting minutes attendance roll.
    "Eduardo Martinez",   # Mayor
    "Cesar Zepeda",       # Vice Mayor, District 2
    "Jamelia Brown",      # District 1
    "Doria Robinson",     # District 3
    "Soheila Bana",       # District 4
    "Sue Wilson",         # District 5
    "Claudia Jimenez",    # District 6
}
FORMER_COUNCIL_MEMBERS = {
    # Recent / former — names appear in contribution data but these
    # people are NOT current officials.  Donations to their campaigns
    # are a weaker signal than donations to sitting members.
    "Tom Butt", "Nat Bates", "Jovanka Beckles", "Ben Choi",
    "Jael Myrick", "Vinay Pimple", "Corky Booze", "Jim Rogers",
    "Ahmad Anderson", "Oscar Garcia",
    "Gayle McLaughlin", "Melvin Willis", "Shawn Dunning",
}
RICHMOND_COUNCIL_MEMBERS = CURRENT_COUNCIL_MEMBERS | FORMER_COUNCIL_MEMBERS


def extract_candidate_from_committee(committee_name: str) -> Optional[str]:
    """Extract candidate name from a campaign committee name.

    California committee names typically follow patterns like:
      "Shawn Dunning for City Council 2024"
      "Oscar Garcia for Richmond City Council 2022"
      "Doria Robinson for Richmond City Council 2026"
      "Friends of Tom Butt for Richmond City Council 2016"
      "Independent PAC Local 188 International Association of Firefighters"

    Returns the candidate name if extractable, else None.
    """
    norm = committee_name.strip()
    # Pattern: "[Name] for [Office]"
    m = re.match(r'^(.+?)\s+for\s+', norm, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        # Strip "Friends of", "Committee to Elect", etc.
        candidate = re.sub(
            r'^(friends of|committee to elect|elect|re-elect|reelect)\s+',
            '', candidate, flags=re.IGNORECASE,
        ).strip()
        if candidate and len(candidate) > 2:
            return candidate
    return None


def is_sitting_council_member(candidate_name: str) -> bool:
    """Check if a candidate name matches a current sitting council member."""
    norm = normalize_text(candidate_name)
    for member in CURRENT_COUNCIL_MEMBERS:
        norm_member = normalize_text(member)
        # Check full name match or one contains the other
        if norm == norm_member:
            return True
        if len(norm) >= 8 and len(norm_member) >= 8:
            if norm in norm_member or norm_member in norm:
                return True
        # Last-name + first-initial match for common variations
        parts_cand = norm.split()
        parts_member = norm_member.split()
        if len(parts_cand) >= 2 and len(parts_member) >= 2:
            if parts_cand[-1] == parts_member[-1] and parts_cand[0][0] == parts_member[0][0]:
                return True
    return False


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace, strip punctuation."""
    text = text.lower().strip()
    text = re.sub(r'[,.\'"!?;:()\[\]{}]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_entity_names(text: str) -> list[str]:
    """Extract potential company/person names from agenda item text.

    Looks for patterns like:
    - "contract with XYZ Company"
    - "purchase from ABC Inc."
    - "agreement with Some Organization"
    - Capitalized multi-word names
    """
    entities = []

    # Pattern: "with/from/to [Company Name]"
    preposition_patterns = [
        r'(?:contract|agreement|purchase|payment|amendment)\s+(?:with|from|to)\s+([A-Z][A-Za-z\s&,.\'-]+?)(?:\s+for\s|\s+in\s|\s+to\s|,|\.|$)',
        r'(?:from|with|to)\s+([A-Z][A-Za-z\s&,.\'-]{3,}?)(?:\s+for\s|\s+in\s|,|\.|$)',
    ]

    for pattern in preposition_patterns:
        for match in re.finditer(pattern, text):
            name = match.group(1).strip().rstrip(',.')
            if len(name) > 3 and name not in ('City', 'County', 'State', 'The'):
                entities.append(name)

    # Pattern: "Inc.", "LLC", "Corp.", "Co.", "Group", "Services"
    corp_pattern = r'([A-Z][A-Za-z\s&,.\'-]+?(?:Inc|LLC|Corp|Co|Group|Services|Solutions|Associates|Consulting|Partners|Company|Foundation)\.?)'
    for match in re.finditer(corp_pattern, text):
        name = match.group(1).strip().rstrip(',.')
        if name not in entities:
            entities.append(name)

    return entities


def names_match(name1: str, name2: str, threshold: float = 0.8) -> tuple[bool, str]:
    """Check if two names match. Returns (is_match, match_type).

    Match types:
    - 'exact': normalized strings are identical
    - 'contains': one name contains the other
    - 'no_match': names don't match
    """
    n1 = normalize_text(name1)
    n2 = normalize_text(name2)

    if not n1 or not n2:
        return False, 'no_match'

    if n1 == n2:
        return True, 'exact'

    # One contains the other (handles "National Auto Fleet Group" matching "National Auto Fleet")
    # Require minimum length of 10 chars for substring match to avoid
    # false positives from short names like "martinez" matching in long text.
    # 10 chars covers typical "first last" names (e.g., "cheryl maier" = 12).
    if len(n1) >= 10 and len(n2) >= 10:
        if n1 in n2 or n2 in n1:
            return True, 'contains'

    # Check if all words of the shorter name appear in the longer
    words1 = set(n1.split())
    words2 = set(n2.split())
    if len(words1) >= 2 and len(words2) >= 2:
        shorter, longer = (words1, words2) if len(words1) <= len(words2) else (words2, words1)
        # Remove common words — includes generic business suffixes and
        # geographic terms that produce false positives when scattered
        # across long text
        stop_words = {'the', 'of', 'and', 'inc', 'llc', 'corp', 'co', 'a', 'an', 'for',
                      'city', 'county', 'state', 'district', 'department',
                      'company', 'group', 'services', 'solutions', 'associates',
                      'consulting', 'partners', 'foundation', 'international',
                      'national', 'american', 'united', 'general', 'first'}
        shorter_meaningful = shorter - stop_words
        longer_meaningful = longer - stop_words
        if len(shorter_meaningful) >= 2 and shorter_meaningful.issubset(longer_meaningful):
            # When matching a short name against a long text, require at
            # least 3 meaningful words to match — 2 common words like
            # "richmond" + "development" co-occurring in a long document
            # produce false positives.
            is_long_text = len(longer) > 20
            min_meaningful = 3 if is_long_text else 2
            if len(shorter_meaningful) >= min_meaningful:
                return True, 'contains'

    return False, 'no_match'


# ── JSON Mode Scanner (pre-database) ─────────────────────────

def scan_meeting_json(
    meeting_data: dict,
    contributions: list[dict],
    form700_interests: list[dict] = None,
    city_fips: str = "0660620",
) -> ScanResult:
    """Scan a meeting's extracted JSON against contribution and interest data.

    This is the pre-database version that works directly with JSON.
    Use this when testing or when the database isn't set up yet.

    Args:
        meeting_data: Extracted meeting JSON (from pipeline.py)
        contributions: List of dicts with keys:
            donor_name, donor_employer, council_member, committee_name,
            amount, date, filing_id, source
        form700_interests: List of dicts with keys:
            council_member, interest_type, description, location, filing_year, source_url
        city_fips: FIPS code (default: Richmond CA)

    Returns:
        ScanResult with all detected flags
    """
    form700_interests = form700_interests or []
    flags = []
    vendor_matches = []
    flagged_items = set()
    skipped_headers = set()  # section-header items skipped from scanning

    # ── Bias Audit Logger ──
    audit_logger = ScanAuditLogger()
    filter_counts = {
        "filtered_council_member": 0,
        "filtered_govt_employer": 0,
        "filtered_govt_donor": 0,
        "filtered_dedup": 0,
        "filtered_short_name": 0,
        "passed_to_flag": 0,
        "suppressed_near_miss": 0,
    }

    # Build set of council member names — their names naturally appear
    # in agenda items (as movers/seconders) and should not trigger
    # false positive "donor name matches item text" flags
    council_member_names = set()
    for member in meeting_data.get("members_present", []):
        name = normalize_text(member.get("name", ""))
        if name:
            council_member_names.add(name)
            # Also add last name alone (most common match pattern)
            parts = name.split()
            if len(parts) >= 2:
                council_member_names.add(parts[-1])  # last name

    # Fallback: when members_present is empty (eSCRIBE agendas, pre-meeting
    # extraction), use hardcoded list of Richmond council members
    if not council_member_names:
        for name in RICHMOND_COUNCIL_MEMBERS:
            norm = normalize_text(name)
            council_member_names.add(norm)
            parts = norm.split()
            if len(parts) >= 2:
                council_member_names.add(parts[-1])

    # De-duplicate contributions to avoid flagging the same donation
    # multiple times (CAL-ACCESS has duplicate filing records)
    seen_contributions = set()

    # Collect all agenda items (consent + action + housing authority)
    all_items = []
    consent = meeting_data.get("consent_calendar", {})
    for item in consent.get("items", []):
        all_items.append(item)

    for item in meeting_data.get("action_items", []):
        all_items.append(item)

    for item in meeting_data.get("housing_authority_items", []):
        all_items.append(item)

    for item in all_items:
        item_num = item.get("item_number", "")
        item_title = item.get("title", "")
        item_desc = item.get("description", "")
        item_text = f"{item_title} {item_desc}"
        financial = item.get("financial_amount")

        # Skip section-header items that are just department groupings
        # (e.g., "V.5: Fire Department", "V.7: Mayor's Office").
        # These have no description, no financial amount, and their titles
        # are just city department names that match too many donors/employers.
        # The actual actionable items are the sub-items (V.5.a, V.6.a, etc.).
        is_section_header = (
            not item_desc.strip()
            and not financial
            and re.match(r'^[A-Z]+\.\d+$', item_num)  # "V.5" but not "V.5.a"
        )
        if is_section_header:
            skipped_headers.add(item_num)
            continue

        # Separate original agenda text from eSCRIBE enrichment.
        # Employer matching is only reliable against the original
        # agenda text — enriched text contains contract boilerplate,
        # committee names, and other incidental organization names
        # that produce false employer matches.
        escribe_marker = "[eSCRIBE Staff Report/Attachment Text]"
        if escribe_marker in item_desc:
            original_text = f"{item_title} {item_desc.split(escribe_marker)[0]}"
        else:
            original_text = item_text

        # ── Campaign Finance Cross-Reference ──
        # Extract entity names from the agenda item
        entities = extract_entity_names(item_text)

        # Aggregate matches per donor-item pair: maps
        # (norm_donor_name, item_num) -> list of matched contributions
        # This prevents 80+ flags from a single donor with many small
        # payroll deductions to the same union PAC.
        donor_item_matches: dict[str, list[dict]] = {}

        for contribution in contributions:
            # Support both test format (donor_name) and CAL-ACCESS format (contributor_name)
            donor_name = contribution.get("donor_name") or contribution.get("contributor_name", "")
            donor_employer = contribution.get("donor_employer") or contribution.get("contributor_employer", "")
            council_member = contribution.get("council_member", "")
            committee = contribution.get("committee_name") or contribution.get("committee", "")
            amount = contribution.get("amount", 0)

            # De-duplicate: skip if we've already flagged this exact contribution
            dedup_key = (donor_name, str(amount), contribution.get("date", ""), committee)
            if dedup_key in seen_contributions:
                filter_counts["filtered_dedup"] += 1
                continue

            # Skip donor name matches where the donor IS a sitting council member
            # Their names appear naturally in agenda items as movers/seconders
            norm_donor = normalize_text(donor_name)
            is_council_member_donor = any(
                cm_name in norm_donor or norm_donor in cm_name
                for cm_name in council_member_names
                if len(cm_name) > 4
            )

            # Skip donors that are government entities — these are typically
            # public financing disbursements or refunds, not private contributions.
            # Their names (e.g., "City of Richmond Finance Department") match
            # nearly every agenda item and produce false positives.
            is_government_donor = any(
                norm_donor.startswith(prefix) for prefix in [
                    "city of", "city and county", "county of", "state of",
                    "town of", "district of", "village of", "borough of",
                ]
            ) or any(
                norm_donor.endswith(suffix) for suffix in [
                    " county", " city", " department", " finance department",
                ]
            )

            # Skip self-donations — a person contributing to their own
            # campaign committee is not a conflict of interest.
            # e.g., "Claudia Jimenez" donating to "Claudia Jimenez for
            # Richmond City Council District 6 in 2020"
            norm_committee = normalize_text(committee)
            is_self_donation = (
                len(norm_donor) > 4
                and norm_donor in norm_committee
            )

            if is_council_member_donor or is_government_donor or is_self_donation:
                if is_council_member_donor:
                    filter_counts["filtered_council_member"] += 1
                    audit_logger.log_decision(MatchingDecision(
                        donor_name=donor_name,
                        donor_employer=donor_employer,
                        agenda_item_number=item_num,
                        agenda_text_preview=item_text[:500],
                        match_type="suppressed_council_member",
                        confidence=0.0,
                        matched=False,
                    ))
                elif is_government_donor:
                    filter_counts["filtered_govt_donor"] += 1
                continue

            # Check donor name against item text.
            # First try the original agenda text (title + original description).
            # Only use the full enriched text for exact matches — word-overlap
            # ('contains') matches against 10KB of enriched text produce false
            # positives when common words like "services", "development",
            # "company" co-occur with geographic names in staff reports.
            donor_match, match_type = names_match(donor_name, original_text)
            if not donor_match:
                # Try full enriched text, but only accept exact matches
                enriched_match, enriched_type = names_match(donor_name, item_text)
                if enriched_match and enriched_type == 'exact':
                    donor_match = True
                    match_type = enriched_type
            if not donor_match and donor_employer:
                # Skip employer matching for generic government employers —
                # these produce massive false positives because "City of Richmond"
                # or "Contra Costa County" appears in nearly every agenda item.
                # Also skip very common institution names that match geographic
                # terms in agenda items (e.g., "Contra Costa College" matches
                # any item mentioning "Contra Costa").
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
                        "contra costa",  # geographic match, not a specific business
                        "alameda county", "marin county", "solano county",
                        "san francisco", "san mateo",
                        "city attorney", "city national",
                        "public defender", "district attorney",
                        "sheriff", "fire department", "police department",
                    ]
                ) or norm_employer in {
                    # Generic job titles / roles that appear in contract
                    # boilerplate and signature blocks — not business names.
                    # eSCRIBE enrichment loads contract text containing
                    # "Contractor", "Executive Director" etc. which would
                    # false-match donors whose employer field is a title.
                    "contractor", "independent contractor", "consultant",
                    "executive director", "director", "manager",
                    "government", "local government", "federal government",
                    "state government", "ad review",
                }

                if not is_generic_employer:
                    # Check employer name against extracted entity names
                    # from the ORIGINAL agenda text only — enriched text
                    # contains committee names, contract boilerplate, and
                    # organization names that aren't financial beneficiaries.
                    original_entities = extract_entity_names(original_text)
                    employer_match = False
                    for entity in original_entities:
                        em, em_type = names_match(donor_employer, entity)
                        if em:
                            employer_match = True
                            match_type = 'employer_match'
                            break
                    if not employer_match:
                        # Fallback: substring check against original text
                        norm_orig = normalize_text(original_text)
                        if len(norm_employer) > 8 and norm_employer in norm_orig:
                            employer_match = True
                            match_type = 'employer_match'
                    donor_match = employer_match

            if donor_match:
                match = VendorDonorMatch(
                    vendor_name=item_title,
                    donor_name=donor_name,
                    donor_employer=donor_employer,
                    match_type=match_type,
                    council_member=council_member,
                    committee_name=committee,
                    contribution_amount=amount,
                    contribution_date=contribution.get("date", ""),
                    filing_id=contribution.get("filing_id", ""),
                    source=contribution.get("source", ""),
                )
                vendor_matches.append(match)
                seen_contributions.add(dedup_key)

                # Aggregate by (donor_name, committee) for this item
                agg_key = f"{norm_donor}||{normalize_text(committee)}"
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

        # Now create ONE flag per donor-committee pair per item
        # with aggregated totals
        for agg_key, matched_contribs in donor_item_matches.items():
            total_amount = sum(c["amount"] for c in matched_contribs)
            num_contribs = len(matched_contribs)

            # Skip donors whose total contributions are below the
            # materiality threshold. Small payroll deductions ($15/pay
            # period) to union PACs are not meaningful conflict signals.
            if total_amount < 100:
                continue

            # Use the first contribution's details as representative
            rep = matched_contribs[0]
            best_match_type = rep["match_type"]
            # Upgrade match type if any contribution had a better match
            for c in matched_contribs:
                if c["match_type"] == "exact":
                    best_match_type = "exact"
                    break

            # Determine the candidate who received the contribution
            # and whether they currently sit on the council
            candidate = extract_candidate_from_committee(rep["committee"])
            sitting = is_sitting_council_member(candidate) if candidate else False
            council_member_label = rep["council_member"]  # may be empty
            if candidate:
                if sitting:
                    council_member_label = f"{candidate} (sitting council member)"
                else:
                    council_member_label = f"{candidate} (not a current council member)"
            elif not council_member_label:
                # PAC/IE committee with no extractable candidate name —
                # use the committee name itself so the field isn't blank
                council_member_label = rep["committee"]

            # Determine confidence based on match type and total amount.
            # Contributions to non-sitting candidates are a weaker signal —
            # the recipient has no vote on the agenda item.
            if sitting:
                confidence = 0.7 if best_match_type == 'exact' else 0.5
            else:
                confidence = 0.4 if best_match_type == 'exact' else 0.3

            if total_amount >= 1000:
                confidence += 0.1
            if total_amount >= 5000:
                confidence += 0.1

            # Filter out meaningless employer values before display
            raw_employer = rep["donor_employer"] or ""
            cleaned_employer = raw_employer.strip()
            if cleaned_employer.lower() in {"", "none", "n/a", "na", "not employed", "unemployed", "-"}:
                cleaned_employer = ""
            employer_note = f" ({cleaned_employer})" if cleaned_employer else ""

            if num_contribs == 1:
                description = (
                    f"{rep['donor_name']}{employer_note} contributed "
                    f"${total_amount:,.2f} to {rep['committee']} on "
                    f"{rep['date']}"
                )
            else:
                # Sort by date to get range
                dates = sorted(c["date"] for c in matched_contribs if c["date"])
                date_range = f"{dates[0]} to {dates[-1]}" if dates else "various dates"
                description = (
                    f"{rep['donor_name']}{employer_note} made {num_contribs} contributions "
                    f"totaling ${total_amount:,.2f} to {rep['committee']} "
                    f"({date_range})"
                )

            # Add context note for non-sitting candidates
            if candidate and not sitting:
                description += (
                    f"\n   NOTE: {candidate} is not a current council member "
                    f"and does not vote on this item. This is disclosed for "
                    f"transparency but represents a weaker conflict signal."
                )

            # Build evidence: reference the most recent filing
            most_recent = max(matched_contribs, key=lambda c: c.get("filing_id", ""))
            evidence = [
                f"Source: {most_recent['source'] or 'unknown'}, "
                f"Filing ID: {most_recent['filing_id'] or 'unknown'}"
            ]
            if num_contribs > 1:
                evidence.append(f"Aggregated from {num_contribs} contribution records")

            # Assign publication tier based on confidence and sitting status.
            # Tier 1: Potential Conflict — sitting member, high confidence
            # Tier 2: Financial Connection — sitting member, lower confidence
            # Tier 3: Internal only — non-sitting recipient, suppressed from comment
            if sitting and confidence >= 0.6:
                tier = 1
            elif sitting and confidence >= 0.4:
                tier = 2
            else:
                tier = 3

            flags.append(ConflictFlag(
                agenda_item_number=item_num,
                agenda_item_title=item_title,
                council_member=council_member_label,
                flag_type="campaign_contribution",
                description=description,
                evidence=evidence,
                confidence=min(confidence, 1.0),
                legal_reference="Gov. Code SS 87100-87105, 87300 (financial interest in governmental decision)",
                financial_amount=financial,
                publication_tier=tier,
            ))
            flagged_items.add(item_num)
            filter_counts["passed_to_flag"] += 1

            # Log the matched decision for bias audit
            audit_logger.log_decision(MatchingDecision(
                donor_name=rep["donor_name"],
                donor_employer=rep["donor_employer"],
                agenda_item_number=item_num,
                agenda_text_preview=item_text[:500],
                match_type=best_match_type,
                confidence=min(confidence, 1.0),
                matched=True,
            ))

        # ── Form 700 Property Cross-Reference ──
        # Flag if a zoning/development item may involve property near
        # a council member's declared real property interest
        zoning_keywords = [
            "rezone", "rezoning", "zoning", "conditional use",
            "subdivision", "variance", "design review",
            "land use", "general plan", "specific plan", "entitlement",
            "development project", "development agreement", "development permit",
            "housing development", "real property", "parcel",
        ]
        # Exclude commission/board appointments that contain "development"
        # in the body name (e.g., "Economic Development Commission")
        appointment_keywords = [
            "appointment", "reappointment", "commission", "board",
            "task force", "committee", "advisory",
        ]
        norm_item = normalize_text(item_text)
        is_land_use = any(kw in norm_item for kw in zoning_keywords)
        is_appointment = any(kw in norm_item for kw in appointment_keywords)
        if is_appointment:
            is_land_use = False  # Don't flag appointments/commissions as land-use

        if is_land_use:
            for interest in form700_interests:
                if interest.get("interest_type") == "real_property":
                    flags.append(ConflictFlag(
                        agenda_item_number=item_num,
                        agenda_item_title=item_title,
                        council_member=interest["council_member"],
                        flag_type="form700_real_property",
                        description=(
                            f"{interest['council_member']}'s Form 700 "
                            f"(filed {interest.get('filing_year', 'unknown')}) lists "
                            f"real property: {interest.get('description', 'N/A')}"
                        ),
                        evidence=[
                            f"Form 700, Schedule A-2, {interest.get('filing_year', '')}",
                            f"Source: {interest.get('source_url', 'FPPC')}"
                        ],
                        confidence=0.4,  # Lower confidence — needs geocoding to confirm proximity
                        legal_reference=(
                            "Gov. Code S 87100 (disqualification when official has "
                            "financial interest in decision). See also 2 CCR S 18702.2 "
                            "(real property interests within 500 feet of subject property)."
                        ),
                        financial_amount=financial,
                    ))
                    flagged_items.add(item_num)

        # ── Form 700 Income/Investment Cross-Reference ──
        for interest in form700_interests:
            if interest.get("interest_type") in ("income", "investment"):
                int_desc = normalize_text(interest.get("description", ""))
                if int_desc and len(int_desc) > 4:
                    for entity in entities:
                        is_match, _ = names_match(int_desc, entity)
                        if is_match:
                            flags.append(ConflictFlag(
                                agenda_item_number=item_num,
                                agenda_item_title=item_title,
                                council_member=interest["council_member"],
                                flag_type=f"form700_{interest['interest_type']}",
                                description=(
                                    f"{interest['council_member']}'s Form 700 "
                                    f"(filed {interest.get('filing_year', 'unknown')}) lists "
                                    f"{interest['interest_type']}: {interest.get('description', 'N/A')}"
                                ),
                                evidence=[
                                    f"Form 700, {interest.get('filing_year', '')}",
                                    f"Source: {interest.get('source_url', 'FPPC')}"
                                ],
                                confidence=0.5,
                                legal_reference="Gov. Code SS 87100-87105 (financial interest in governmental decision)",
                                financial_amount=financial,
                            ))
                            flagged_items.add(item_num)
                            break

    # Identify clean items (unflagged items + skipped section headers)
    all_item_nums = [item.get("item_number", "") for item in all_items]
    clean_items = [n for n in all_item_nums if n not in flagged_items]
    # Skipped headers are also clean (they were excluded from scanning)
    for h in skipped_headers:
        if h not in clean_items:
            clean_items.append(h)

    # Build audit summary with filter funnel statistics
    audit_logger.summary = ScanAuditSummary(
        scan_run_id=audit_logger.scan_run_id,
        city_fips=city_fips,
        meeting_date=meeting_data.get("meeting_date", "unknown"),
        total_agenda_items=len(all_items),
        total_contributions_compared=len(contributions),
        filtered_council_member=filter_counts["filtered_council_member"],
        filtered_govt_donor=filter_counts["filtered_govt_donor"],
        filtered_govt_employer=filter_counts["filtered_govt_employer"],
        filtered_dedup=filter_counts["filtered_dedup"],
        filtered_short_name=filter_counts["filtered_short_name"],
        passed_to_flag=filter_counts["passed_to_flag"],
        suppressed_near_miss=filter_counts.get("suppressed_near_miss", 0),
    )

    return ScanResult(
        meeting_date=meeting_data.get("meeting_date", "unknown"),
        meeting_type=meeting_data.get("meeting_type", "unknown"),
        total_items_scanned=len(all_items),
        flags=flags,
        vendor_matches=vendor_matches,
        clean_items=clean_items,
        scan_run_id=audit_logger.scan_run_id,
        audit_log=audit_logger,
    )


# ── Database Mode Scanner ────────────────────────────────────

def scan_meeting_db(conn, meeting_id: str, city_fips: str = "0660620") -> ScanResult:
    """Scan a meeting using database queries for cross-referencing.

    Requires Layer 2 tables to be populated with both meeting data
    and campaign finance data.

    This is the production version that scales with data.
    """
    flags = []
    vendor_matches = []
    flagged_items = set()

    with conn.cursor() as cur:
        # Get meeting info
        cur.execute(
            "SELECT meeting_date, meeting_type FROM meetings WHERE id = %s AND city_fips = %s",
            (meeting_id, city_fips),
        )
        meeting_row = cur.fetchone()
        if not meeting_row:
            raise ValueError(f"Meeting {meeting_id} not found for city {city_fips}")
        meeting_date, meeting_type = meeting_row

        # Get all agenda items for this meeting
        cur.execute(
            """SELECT id, item_number, title, description, category,
                      financial_amount, is_consent_calendar
               FROM agenda_items WHERE meeting_id = %s""",
            (meeting_id,),
        )
        items = cur.fetchall()

        for item_id, item_num, title, desc, category, financial, is_consent in items:
            item_text = f"{title or ''} {desc or ''}"
            entities = extract_entity_names(item_text)

            # Cross-reference against contributions via the v_donor_vote_crossref view
            # For each entity found in the item, search for matching donors/employers
            for entity in entities:
                norm_entity = normalize_text(entity)
                if len(norm_entity) < 4:
                    continue

                cur.execute(
                    """SELECT DISTINCT
                           d.name AS donor_name,
                           d.employer AS donor_employer,
                           co.amount,
                           co.contribution_date,
                           co.filing_id,
                           co.source,
                           cm.name AS committee_name,
                           o.name AS official_name
                       FROM contributions co
                       JOIN donors d ON co.donor_id = d.id
                       JOIN committees cm ON co.committee_id = cm.id
                       LEFT JOIN officials o ON cm.official_id = o.id
                       WHERE co.city_fips = %s
                         AND (d.normalized_name LIKE %s OR d.normalized_employer LIKE %s)""",
                    (city_fips, f"%{norm_entity}%", f"%{norm_entity}%"),
                )

                for row in cur.fetchall():
                    donor_name, donor_employer, amount, cont_date, filing_id, source, committee, official = row
                    if official is None:
                        continue

                    vm = VendorDonorMatch(
                        vendor_name=entity,
                        donor_name=donor_name,
                        donor_employer=donor_employer or "",
                        match_type="db_search",
                        council_member=official,
                        committee_name=committee,
                        contribution_amount=float(amount),
                        contribution_date=str(cont_date),
                        filing_id=filing_id or "",
                        source=source,
                    )
                    vendor_matches.append(vm)

                    confidence = 0.6
                    if float(amount) >= 1000:
                        confidence += 0.1
                    if float(amount) >= 5000:
                        confidence += 0.1

                    employer_note = f" ({donor_employer})" if donor_employer else ""
                    flags.append(ConflictFlag(
                        agenda_item_number=item_num,
                        agenda_item_title=title,
                        council_member=official,
                        flag_type="campaign_contribution",
                        description=(
                            f"{donor_name}{employer_note} contributed "
                            f"${float(amount):,.2f} to {committee} on {cont_date}"
                        ),
                        evidence=[f"Source: {source}, Filing ID: {filing_id}"],
                        confidence=min(confidence, 1.0),
                        legal_reference="Gov. Code SS 87100-87105, 87300",
                        financial_amount=financial,
                    ))
                    flagged_items.add(item_num)

            # Form 700 cross-reference for land-use items
            zoning_keywords = [
                "rezone", "rezoning", "zoning", "conditional use",
                "subdivision", "variance", "design review",
                "land use", "general plan", "specific plan",
                "development project", "development agreement",
                "development permit", "housing development",
                "real property", "parcel",
            ]
            appointment_keywords = [
                "appointment", "reappointment", "commission", "board",
                "task force", "committee", "advisory",
            ]
            norm_item_text = normalize_text(item_text)
            is_land_use_item = any(kw in norm_item_text for kw in zoning_keywords)
            is_appointment_item = any(kw in norm_item_text for kw in appointment_keywords)
            if is_land_use_item and not is_appointment_item:
                cur.execute(
                    """SELECT o.name, ei.description, ei.filing_year, ei.location
                       FROM economic_interests ei
                       JOIN officials o ON ei.official_id = o.id
                       WHERE ei.city_fips = %s AND ei.interest_type = 'real_property'""",
                    (city_fips,),
                )
                for official_name, ei_desc, year, location in cur.fetchall():
                    flags.append(ConflictFlag(
                        agenda_item_number=item_num,
                        agenda_item_title=title,
                        council_member=official_name,
                        flag_type="form700_real_property",
                        description=(
                            f"{official_name}'s Form 700 (filed {year}) "
                            f"lists real property: {ei_desc}"
                        ),
                        evidence=[f"Form 700, Schedule A-2, {year}"],
                        confidence=0.4,
                        legal_reference=(
                            "Gov. Code S 87100; 2 CCR S 18702.2 "
                            "(real property within 500 feet)"
                        ),
                        financial_amount=financial,
                    ))
                    flagged_items.add(item_num)

    all_item_nums = [row[1] for row in items]
    clean_items = [n for n in all_item_nums if n not in flagged_items]

    return ScanResult(
        meeting_date=str(meeting_date),
        meeting_type=meeting_type,
        total_items_scanned=len(items),
        flags=flags,
        vendor_matches=vendor_matches,
        clean_items=clean_items,
    )


# ── Report Generation ────────────────────────────────────────

def format_scan_report(result: ScanResult) -> str:
    """Format a ScanResult into a human-readable report."""
    lines = []
    lines.append(f"CONFLICT SCAN REPORT — {result.meeting_type.title()} Meeting, {result.meeting_date}")
    lines.append("=" * 70)
    lines.append(f"Items scanned: {result.total_items_scanned}")
    lines.append(f"Flags raised: {len(result.flags)}")
    lines.append(f"Vendor/donor matches: {len(result.vendor_matches)}")
    lines.append(f"Clean items: {len(result.clean_items)}")
    lines.append("")

    if result.flags:
        lines.append("POTENTIAL CONFLICTS")
        lines.append("-" * 70)
        for i, flag in enumerate(result.flags, 1):
            lines.append(f"\n  [{i}] Item {flag.agenda_item_number}: {flag.agenda_item_title}")
            lines.append(f"      Type: {flag.flag_type}")
            lines.append(f"      Council Member: {flag.council_member}")
            lines.append(f"      Confidence: {flag.confidence:.0%}")
            if flag.financial_amount:
                lines.append(f"      Agenda Amount: {flag.financial_amount}")
            lines.append(f"      {flag.description}")
            for ev in flag.evidence:
                lines.append(f"      Evidence: {ev}")
            lines.append(f"      Legal ref: {flag.legal_reference}")

    if result.enriched_items:
        lines.append(f"\nEnhanced scanning (eSCRIBE attachments): {', '.join(result.enriched_items)}")

    if result.clean_items:
        lines.append(f"\nCLEAN ITEMS (no flags): {', '.join(result.clean_items)}")

    lines.append("\n" + "=" * 70)
    lines.append("NOTE: This is informational only. Not a legal determination.")

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Richmond Transparency Project — Conflict Scanner")
    parser.add_argument("meeting_json", help="Path to extracted meeting JSON file")
    parser.add_argument("--contributions", help="Path to contributions JSON file")
    parser.add_argument("--form700", help="Path to Form 700 interests JSON file")
    parser.add_argument("--output", help="Save report to file")

    args = parser.parse_args()

    with open(args.meeting_json) as f:
        meeting_data = json.load(f)

    contributions = []
    if args.contributions:
        with open(args.contributions) as f:
            contributions = json.load(f)

    form700 = []
    if args.form700:
        with open(args.form700) as f:
            form700 = json.load(f)

    result = scan_meeting_json(meeting_data, contributions, form700)
    report = format_scan_report(result)

    # Save audit sidecar
    audit_dir = Path(__file__).parent / "data" / "audit_runs"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"{result.scan_run_id}.json"
    result.audit_log.save(audit_path)
    print(f"Audit sidecar saved to {audit_path}")

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
