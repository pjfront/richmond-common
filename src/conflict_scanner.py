"""
Richmond Common — Conflict of Interest Scanner

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

import sys as _sys
# When run as a script (`python src/conflict_scanner.py`), Python registers the
# module as `__main__`. The scanner.signals.* modules import names from
# `conflict_scanner` at load time; without this alias, Python would re-execute
# this file as a fresh module and hit a circular import. Registering __main__
# under both names lets the signals see the partially-loaded module that has
# already bound RawSignal/_ScanContext/etc. by the time the re-export at the
# bottom of this file triggers their load. No-op when imported normally.
if __name__ == "__main__":
    _sys.modules.setdefault("conflict_scanner", _sys.modules["__main__"])

import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from bias_signals import lookup_surname_frequency_tier
from scan_audit import MatchingDecision, ScanAuditSummary, ScanAuditLogger


def _load_alias_map(city_fips: str) -> dict[str, list[str]]:
    """Load name aliases from officials.json for a city.

    Returns a dict mapping each normalized canonical name to its list
    of normalized aliases. Also maps each alias back to the canonical name.
    This enables bidirectional lookup: given any name variant, find all
    names that should be treated as the same person.
    """
    gt_path = Path(__file__).parent / "ground_truth" / "officials.json"
    if not gt_path.exists():
        return {}

    try:
        data = json.loads(gt_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    if data.get("city_fips") != city_fips:
        return {}

    # Build name_group: normalized_name -> set of all normalized variants
    name_groups: dict[str, set[str]] = {}
    for section in ("current_council_members", "former_council_members", "city_leadership"):
        for official in data.get(section, []):
            canonical = official.get("name", "")
            if not canonical:
                continue
            norm_canonical = normalize_text(canonical)
            aliases = official.get("aliases", [])
            if not aliases:
                continue
            group = {norm_canonical}
            for alias in aliases:
                group.add(normalize_text(alias))
            # Map every name in the group to the full group
            for name in group:
                name_groups[name] = group

    return name_groups


# Default anomaly factor — declared early so RawSignal can use it as default.
# Full anomaly detection system (B.51) is defined after the data types.
_DEFAULT_ANOMALY = 0.5

# ── Data Types ───────────────────────────────────────────────

@dataclass
class RawSignal:
    """A single detection signal from an independent detector.

    Signal detectors each produce a list of RawSignal objects.
    The composite confidence calculator (compute_composite_confidence)
    combines signals from multiple independent sources into a final
    ConflictFlag with multi-factor confidence scoring.
    """
    signal_type: str           # 'campaign_contribution', 'form700_property',
                               # 'form700_income', 'donor_vendor_expenditure',
                               # 'temporal_correlation'
    council_member: str        # Official this signal is about
    agenda_item_number: str    # Which item this signal is for
    match_strength: float      # 0.0-1.0, precision of entity/name match
    temporal_factor: float     # 0.0-1.0, time proximity (1.0 = within 90 days)
    financial_factor: float    # 0.0-1.0, materiality of amounts
    description: str           # Factual language description
    evidence: list[str]        # Source citations
    legal_reference: str
    financial_amount: Optional[str] = None
    anomaly_factor: float = _DEFAULT_ANOMALY  # B.51: per-signal anomaly score
    match_details: dict = field(default_factory=dict)  # Signal-specific metadata for audit


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
    confidence_factors: Optional[dict] = None  # v3: breakdown of composite confidence scoring
    scanner_version: int = 2  # 2=current monolithic, 3=signal-based
    match_details: Optional[dict] = None  # v3: structured metadata (donor_name, committee, amounts, etc.)


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


# ── v3 Signal Architecture: Composite Confidence ────────────

# Factor weights for multi-factor confidence scoring.
# Sum to 1.0. match_strength weighted highest because entity matching
# precision is the single biggest driver of false positives.
CONFIDENCE_WEIGHTS = {
    "match_strength": 0.35,
    "temporal_factor": 0.25,
    "financial_factor": 0.20,
    "anomaly_factor": 0.20,
}

# Corroboration boost: independent signals from different sources
# increase confidence that a pattern is real, not coincidental.
CORROBORATION_MULTIPLIERS = {
    1: 1.0,    # single signal, no boost
    2: 1.15,   # two independent signals
}
CORROBORATION_MULTIPLIER_3_PLUS = 1.30  # three or more independent signals

# Sitting multiplier: a sitting member who can vote on the item
# is a stronger conflict signal than a former/non-sitting official.
SITTING_MULTIPLIER = 1.0
NON_SITTING_MULTIPLIER = 0.6

# Default anomaly factor: fallback when insufficient data for baselines.
DEFAULT_ANOMALY_FACTOR = 0.5

# Minimum contributions required to compute meaningful baselines.
# Below this threshold, fall back to DEFAULT_ANOMALY_FACTOR.
MIN_CONTRIBUTIONS_FOR_BASELINES = 50


# ── B.51: Anomaly Detection ──────────────────────────────────

@dataclass
class ContributionBaselines:
    """Statistical baselines for anomaly detection.

    Computed from the full contribution dataset for a city.
    Used to score how unusual a particular contribution amount is.
    """
    mean: float
    median: float
    stddev: float
    p75: float        # 75th percentile
    p90: float        # 90th percentile
    p95: float        # 95th percentile
    p99: float        # 99th percentile
    count: int
    has_baselines: bool = True


def build_contribution_baselines(
    contributions: list[dict],
) -> ContributionBaselines:
    """Build statistical baselines from contribution amounts.

    Returns baselines with has_baselines=False if insufficient data
    (fewer than MIN_CONTRIBUTIONS_FOR_BASELINES contributions).
    """
    import math

    amounts = []
    for c in contributions:
        try:
            amt = float(c.get("amount", 0))
            if amt > 0:
                amounts.append(amt)
        except (TypeError, ValueError):
            continue

    if len(amounts) < MIN_CONTRIBUTIONS_FOR_BASELINES:
        return ContributionBaselines(
            mean=0.0, median=0.0, stddev=0.0,
            p75=0.0, p90=0.0, p95=0.0, p99=0.0,
            count=len(amounts), has_baselines=False,
        )

    amounts.sort()
    n = len(amounts)
    mean = sum(amounts) / n
    variance = sum((x - mean) ** 2 for x in amounts) / n
    stddev = math.sqrt(variance) if variance > 0 else 0.0

    def _percentile(sorted_data: list[float], pct: float) -> float:
        """Compute percentile using nearest-rank method."""
        k = int(pct / 100 * len(sorted_data))
        return sorted_data[min(k, len(sorted_data) - 1)]

    return ContributionBaselines(
        mean=mean,
        median=_percentile(amounts, 50),
        stddev=stddev,
        p75=_percentile(amounts, 75),
        p90=_percentile(amounts, 90),
        p95=_percentile(amounts, 95),
        p99=_percentile(amounts, 99),
        count=n,
        has_baselines=True,
    )


def compute_anomaly_factor(
    amount: float,
    baselines: ContributionBaselines,
    contribution_date: str = "",
    meeting_date: str = "",
) -> float:
    """Compute anomaly factor (0.0-1.0) for a contribution amount.

    B.51: Scores how unusual a contribution is relative to city baselines.

    Amount anomaly (z-score based):
      - Within 1 stddev of mean: 0.3 (common, low anomaly)
      - 1-2 stddev: 0.5 (moderately unusual)
      - 2-3 stddev: 0.7 (unusual)
      - >3 stddev: 0.9-1.0 (highly unusual)

    Temporal anomaly boost: donations within 30 days of a vote
    get +0.1 boost (capped at 1.0).

    Falls back to DEFAULT_ANOMALY_FACTOR when baselines unavailable.
    """
    from operator_config import get_scan_config
    cfg = get_scan_config()

    if not baselines.has_baselines:
        return cfg.quality.get("default_anomaly", DEFAULT_ANOMALY_FACTOR)

    # Amount anomaly via z-score
    if baselines.stddev > 0:
        z_score = abs(amount - baselines.mean) / baselines.stddev
    else:
        # All contributions are the same amount — any different amount is anomalous
        z_score = 0.0 if amount == baselines.mean else 3.0

    if z_score <= 1.0:
        anomaly = 0.3
    elif z_score <= 2.0:
        anomaly = 0.5
    elif z_score <= 3.0:
        anomaly = 0.7
    else:
        # Scale from 0.9 to 1.0 for extreme outliers
        anomaly = min(0.9 + (z_score - 3.0) * 0.02, 1.0)

    # Percentile-based boost: contributions above 95th percentile
    # are inherently unusual regardless of z-score
    if amount >= baselines.p99:
        anomaly = max(anomaly, 0.9)
    elif amount >= baselines.p95:
        anomaly = max(anomaly, 0.7)
    elif amount >= baselines.p90:
        anomaly = max(anomaly, 0.5)

    # B.51: Temporal anomaly boost — donations near a vote
    boost_days = cfg.temporal.get("anomaly_boost_days", 30)
    boost_amount = cfg.temporal.get("anomaly_boost_amount", 0.10)
    if contribution_date and meeting_date:
        try:
            contrib_dt = _parse_date(contribution_date)
            meeting_dt = _parse_date(meeting_date)
            if contrib_dt and meeting_dt:
                days_apart = abs((meeting_dt - contrib_dt).days)
                if days_apart <= boost_days:
                    anomaly = min(anomaly + boost_amount, 1.0)
        except (TypeError, AttributeError):
            pass

    return round(anomaly, 2)

# Publication tier thresholds (v3).
# Judgment call resolved 2026-03-09: all tiers public.
# This is the SINGLE SOURCE OF TRUTH for tier boundaries.
# All other modules (batch_scan, data_quality_checks) import from here.
V3_TIER_THRESHOLDS = {
    "high": 0.85,    # "High-Confidence Pattern"
    "medium": 0.70,  # "Medium-Confidence Pattern"
    "low": 0.50,     # "Low-Confidence Pattern"
}

# Numbered-key version for modules that reference tiers by number.
# Derived from V3_TIER_THRESHOLDS — do not edit independently.
TIER_THRESHOLDS_BY_NUMBER = {
    1: V3_TIER_THRESHOLDS["high"],    # Tier 1: >= 0.85
    2: V3_TIER_THRESHOLDS["medium"],  # Tier 2: >= 0.70
    3: V3_TIER_THRESHOLDS["low"],     # Tier 3: >= 0.50
}

# Human-readable tier labels (used by batch_scan validation reports and frontend)
TIER_LABELS = {
    1: "High-Confidence Pattern",
    2: "Medium-Confidence Pattern",
    3: "Low-Confidence Pattern",
    4: "Internal",
}


def compute_composite_confidence(
    signals: list[RawSignal],
    is_sitting: bool = True,
    anomaly_factor: float | None = None,
) -> dict:
    """Combine multiple RawSignals into a composite confidence score.

    Returns a dict with:
        - confidence: float (0.0-1.0), the final composite score
        - factors: dict of individual factor values used
        - corroboration_boost: float multiplier applied
        - sitting_multiplier: float multiplier applied
        - signal_count: int number of signals combined
        - publication_tier: int (1=high, 2=medium, 3=low, 4=internal)
        - tier_label: str human-readable label

    B.51: anomaly_factor is now taken from per-signal values by default
    (max across signals). Pass anomaly_factor explicitly to override.

    The model uses four weighted factors plus corroboration:
        composite = sitting_multiplier * weighted_avg(
            match_strength    * 0.35,
            temporal_factor   * 0.25,
            financial_factor  * 0.20,
            anomaly_factor    * 0.20
        ) * corroboration_boost
    """
    from operator_config import get_scan_config
    cfg = get_scan_config()
    ev = cfg.evidence

    sitting_m = ev.get("sitting_mult", SITTING_MULTIPLIER)
    non_sitting_m = ev.get("non_sitting_mult", NON_SITTING_MULTIPLIER)

    if not signals:
        return {
            "confidence": 0.0,
            "factors": {},
            "corroboration_boost": 1.0,
            "sitting_multiplier": sitting_m if is_sitting else non_sitting_m,
            "signal_count": 0,
            "publication_tier": 4,
            "tier_label": "Internal",
        }

    # Aggregate factor values across signals: take the max of each factor
    # since we want the strongest signal to drive the score, not the average.
    max_match = max(s.match_strength for s in signals)
    max_temporal = max(s.temporal_factor for s in signals)
    max_financial = max(s.financial_factor for s in signals)

    # B.51: Use per-signal anomaly factors (take max) unless explicitly overridden
    if anomaly_factor is None:
        max_anomaly = max(s.anomaly_factor for s in signals)
    else:
        max_anomaly = anomaly_factor

    # Weighted average of the four factors (weights from config)
    w_match = ev.get("match_strength", CONFIDENCE_WEIGHTS["match_strength"])
    w_temporal = ev.get("temporal_factor", CONFIDENCE_WEIGHTS["temporal_factor"])
    w_financial = ev.get("financial_factor", CONFIDENCE_WEIGHTS["financial_factor"])
    w_anomaly = ev.get("anomaly_factor", CONFIDENCE_WEIGHTS["anomaly_factor"])

    weighted_avg = (
        max_match * w_match
        + max_temporal * w_temporal
        + max_financial * w_financial
        + max_anomaly * w_anomaly
    )

    # Corroboration boost: count distinct signal types
    corr_2 = ev.get("corroboration_2", CORROBORATION_MULTIPLIERS.get(2, 1.15))
    corr_3plus = ev.get("corroboration_3plus", CORROBORATION_MULTIPLIER_3_PLUS)
    distinct_types = len(set(s.signal_type for s in signals))
    if distinct_types >= 3:
        corroboration = corr_3plus
    elif distinct_types == 2:
        corroboration = corr_2
    else:
        corroboration = 1.0

    # Sitting multiplier
    sitting_mult = sitting_m if is_sitting else non_sitting_m

    # Final composite (capped at 1.0)
    confidence = round(min(sitting_mult * weighted_avg * corroboration, 1.0), 4)

    # Map to publication tier
    tier, label = _confidence_to_tier(confidence)

    # Determine temporal direction from campaign_contribution signals
    temporal_directions = set()
    for s in signals:
        if s.signal_type == "campaign_contribution" and s.match_details:
            td = s.match_details.get("temporal_direction")
            if td:
                temporal_directions.add(td)
    if len(temporal_directions) > 1 or "mixed" in temporal_directions:
        temporal_direction = "mixed"
    elif temporal_directions:
        temporal_direction = temporal_directions.pop()
    else:
        temporal_direction = None  # no campaign_contribution signals

    return {
        "confidence": confidence,
        "factors": {
            "match_strength": round(max_match, 4),
            "temporal_factor": round(max_temporal, 4),
            "financial_factor": round(max_financial, 4),
            "anomaly_factor": round(max_anomaly, 4),
            **({"temporal_direction": temporal_direction} if temporal_direction else {}),
        },
        "corroboration_boost": corroboration,
        "sitting_multiplier": sitting_mult,
        "signal_count": len(signals),
        "publication_tier": tier,
        "tier_label": label,
    }


def _confidence_to_tier(confidence: float) -> tuple[int, str]:
    """Map a confidence score to publication tier and label.

    Returns (tier_number, label_string).
    """
    from operator_config import get_scan_config
    pub = get_scan_config().publication

    high = pub.get("tier_high", V3_TIER_THRESHOLDS["high"])
    medium = pub.get("tier_medium", V3_TIER_THRESHOLDS["medium"])
    low = pub.get("tier_low", V3_TIER_THRESHOLDS["low"])

    if confidence >= high:
        return 1, "High-Confidence Pattern"
    elif confidence >= medium:
        return 2, "Medium-Confidence Pattern"
    elif confidence >= low:
        return 3, "Low-Confidence Pattern"
    else:
        return 4, "Internal"


# ── v3 Language Framework ────────────────────────────────────

# Standardized factual language for all flag descriptions.
# Research Tier 1 (factual) only. No inference, no advocacy.
LANGUAGE_TEMPLATE = (
    "Public records show that {entity} contributed ${amount} to "
    "{official}'s campaign committee ({committee}) {temporal_context}. "
    "{entity} {action_context} in agenda item {item_number}."
)

# Words that must NEVER appear in any flag description or generated text.
LANGUAGE_BLOCKLIST = frozenset({
    "corruption", "corrupt",
    "illegal", "illegally",
    "bribery", "bribe",
    "kickback",
    "scandal", "scandalous",
    "suspicious", "suspiciously",
})

# Appended to all flag descriptions when confidence < 0.85.
HEDGE_CLAUSE = "Other explanations may exist."


def validate_language(text: str) -> list[str]:
    """Check text against the language blocklist.

    Returns list of blocklisted words found (empty = clean).
    """
    from operator_config import get_scan_config
    blocklist = get_scan_config().publication.get("blocklist", list(LANGUAGE_BLOCKLIST))

    text_lower = text.lower()
    return [word for word in blocklist if word in text_lower]


def apply_hedge_clause(description: str, confidence: float) -> str:
    """Append hedge clause to description when confidence is below the high tier.

    Returns the description unchanged if confidence >= high threshold or
    hedge is disabled.
    """
    from operator_config import get_scan_config
    pub = get_scan_config().publication

    if not pub.get("hedge_enabled", True):
        return description

    high_threshold = pub.get("tier_high", V3_TIER_THRESHOLDS["high"])
    hedge_text = pub.get("hedge_text", HEDGE_CLAUSE)

    if confidence < high_threshold and hedge_text not in description:
        return f"{description}\n{hedge_text}"
    return description


def _build_connection_clause(
    match_type: str,
    item_num: str,
    item_title: str,
    donor_name: str = "",
    donor_employer: str = "",
) -> str:
    """Build a human-readable clause explaining WHY a signal was flagged.

    Translates the match_type + agenda item context into a sentence like:
    "Gliksohn is named in this agenda item: Reappoint members to Economic
    Development Board."

    Returns empty string if item_title is empty (graceful degradation).
    """
    if not item_title or not item_title.strip():
        return ""

    # Truncate very long titles
    title = item_title.strip()
    if len(title) > 150:
        title = title[:147] + "..."

    # Determine what matched and build the subject
    if match_type in ("exact", "phrase", "alias_exact", "alias_phrase"):
        # Donor's name was found in the agenda text
        # Use last name for brevity if available
        parts = donor_name.strip().split() if donor_name else []
        subject = parts[-1] if parts else "This donor"
        return f" {subject} is named in this agenda item: {title}."
    elif match_type in ("employer_match", "employer_substring"):
        employer = (donor_employer or "").strip()
        if employer:
            return f" {employer} is referenced in this agenda item: {title}."
        return f" Employer is referenced in this agenda item: {title}."
    else:
        # Fallback for unknown match types — still provide the agenda context
        return f" Related to agenda item: {title}."


# ── v3 Signal Architecture: Factor Computation Helpers ───────

@dataclass
class _ScanContext:
    """Shared context for signal detectors within a single scan run."""
    council_member_names: set
    alias_groups: dict
    current_officials: set
    former_officials: set
    seen_contributions: set
    audit_logger: ScanAuditLogger
    filter_counts: dict
    meeting_date: str
    city_fips: str
    name_in_text_cache: dict = field(default_factory=dict)
    contribution_baselines: ContributionBaselines | None = None  # B.51
    entity_graph: dict = field(default_factory=dict)       # B.46: person -> org connections
    org_reverse_map: dict = field(default_factory=dict)    # B.46: org -> person connections
    behested_payments: list = field(default_factory=list)   # S13.1: FPPC Form 803
    lobbyist_registrations: list = field(default_factory=list)  # S13.3: lobbyist registry


def _parse_date(date_str: str):
    """Parse a date string in common formats. Returns datetime or None."""
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _compute_temporal_factor(contribution_date: str, meeting_date: str) -> float:
    """Compute temporal proximity factor between contribution and meeting.

    Returns 0.0-1.0: higher values mean closer in time.
    Pre-vote donations score higher than post-vote (influence vs. reward).
    Band thresholds and factors are read from operator config.
    """
    from operator_config import get_scan_config
    cfg_temporal = get_scan_config().temporal

    try:
        contrib_dt = _parse_date(contribution_date)
        meeting_dt = _parse_date(meeting_date)
        if not contrib_dt or not meeting_dt:
            return 0.5  # unparseable date, neutral

        days_diff = (meeting_dt - contrib_dt).days  # positive = pre-vote
        days_apart = abs(days_diff)
        is_pre_vote = days_diff >= 0
    except (TypeError, AttributeError):
        return 0.5  # neutral if anything goes wrong

    # Base factor from proximity using configurable bands
    bands = cfg_temporal.get("bands", [
        {"days": 90, "factor": 1.0},
        {"days": 180, "factor": 0.8},
        {"days": 365, "factor": 0.6},
        {"days": 730, "factor": 0.4},
    ])
    beyond_factor = cfg_temporal.get("beyond_factor", 0.2)

    base = beyond_factor  # default if beyond all bands
    for band in bands:
        if days_apart <= band["days"]:
            base = band["factor"]
            break

    # Post-vote donations are weaker influence signals
    post_vote_penalty = cfg_temporal.get("post_vote_penalty", 0.70)
    if not is_pre_vote:
        base *= post_vote_penalty

    return round(base, 2)


def _compute_temporal_direction(contribution_date: str, meeting_date: str) -> str:
    """Determine whether a contribution was made before or after a meeting.

    Returns 'pre_vote', 'post_vote', or 'unknown'.
    """
    try:
        contrib_dt = _parse_date(contribution_date)
        meeting_dt = _parse_date(meeting_date)
        if not contrib_dt or not meeting_dt:
            return "unknown"
        return "pre_vote" if contrib_dt <= meeting_dt else "post_vote"
    except (TypeError, AttributeError):
        return "unknown"


def _compute_financial_factor(amount: float) -> float:
    """Compute financial materiality factor.

    Returns 0.0-1.0: higher values mean larger/more material amounts.
    Band thresholds read from operator config.
    """
    from operator_config import get_scan_config
    bands = get_scan_config().financial

    if not bands:
        # Fallback to hardcoded defaults
        bands = [
            {"min": 5000, "factor": 1.0},
            {"min": 1000, "factor": 0.7},
            {"min": 500, "factor": 0.5},
            {"min": 100, "factor": 0.3},
            {"min": 0, "factor": 0.1},
        ]

    # Bands are ordered highest-min first
    for band in bands:
        if amount >= band["min"]:
            return band["factor"]

    # Below all bands
    return 0.1


# Business suffixes to normalize before matching.
# "ABC Construction Inc." and "ABC Construction LLC" should match.
_BUSINESS_SUFFIX_RE = re.compile(
    r'\b(?:inc\.?|incorporated|llc|l\.l\.c\.?|corp\.?|corporation|ltd\.?|'
    r'limited|co\.?|lp|l\.p\.?|llp|l\.l\.p\.?|associates|group|'
    r'holdings|enterprises),?\s*$',
    re.IGNORECASE,
)


def normalize_business_name(name: str) -> str:
    """Normalize a business/entity name by stripping common suffixes.

    Strips Inc, LLC, Corp, Ltd, Co, LP, LLP, Associates, Group,
    Holdings, Enterprises (and their punctuated variants) from the end.
    Also strips trailing commas and whitespace.

    Used before matching so "ABC Construction Inc." and
    "ABC Construction LLC" compare as the same entity.
    """
    result = _BUSINESS_SUFFIX_RE.sub('', name.strip()).strip().rstrip(',. ')
    return result if result else name.strip()


# Words that are common in business names but not distinctive.
# Used by _match_type_to_strength for specificity penalty.
_GENERIC_BUSINESS_WORDS = frozenset({
    'services', 'development', 'pacific', 'management', 'construction',
    'consulting', 'solutions', 'associates', 'partners', 'enterprises',
    'properties', 'investments', 'holdings', 'resources', 'systems',
    'technologies', 'environmental', 'engineering', 'design', 'group',
    'international', 'national', 'american', 'western', 'bay', 'east',
    'west', 'north', 'south', 'central', 'general', 'first', 'united',
    'golden', 'state', 'california', 'richmond', 'contra', 'costa',
    'inc', 'llc', 'corp', 'co', 'company', 'the', 'of', 'and', 'a',
})

# Stop words for name matching — broader than _GENERIC_BUSINESS_WORDS,
# includes geographic terms and common articles/prepositions.
# Used by names_match() for word-overlap filtering and B.52
# suffix-stripped substring guard.
_NAME_MATCH_STOP_WORDS = frozenset({
    'the', 'of', 'and', 'inc', 'llc', 'corp', 'co', 'a', 'an', 'for',
    'city', 'county', 'state', 'district', 'department',
    'company', 'group', 'services', 'solutions', 'associates',
    'consulting', 'partners', 'foundation', 'international',
    'national', 'american', 'united', 'general', 'first',
})


_GOVERNMENT_ENTITY_PREFIXES = (
    "city of", "city and county", "city &", "city & county",
    "county of", "state of", "town of",
    "district of", "village of", "borough of",
)

_GOVERNMENT_ENTITY_SUFFIXES = (
    " county", " city", " state", " department", " finance department",
)


def _is_government_entity(name: str) -> bool:
    """Check if a normalized name looks like a government entity.

    Used to filter false positives from vendor gazetteers and employer
    matching — 'city of richmond' as an employer or vendor is civic
    noise, not a conflict signal.
    """
    norm = normalize_text(name) if name else ""
    if not norm:
        return False
    return (
        any(norm.startswith(p) for p in _GOVERNMENT_ENTITY_PREFIXES)
        or any(norm.endswith(s) for s in _GOVERNMENT_ENTITY_SUFFIXES)
    )


def _match_type_to_strength(match_type: str, donor_name_words: set = None) -> float:
    """Convert name match type to match_strength factor (0.0-1.0).

    Incorporates proportional specificity scoring: match_strength is
    weighted by the ratio of distinctive words to total words in the
    donor name. A name that is 100% distinctive gets no penalty; one
    that is 100% generic gets a 0.5x penalty (floor).

    B.52: Replaces the previous binary 0.7x threshold.
    """
    base_strengths = {
        'exact': 1.0,
        'registry_match': 0.95,      # B.46: structural ID match via entity registry
        'registry_officer': 0.90,    # B.46: person is officer/director of matched org
        'registry_agent': 0.85,      # B.46: person is registered agent of matched org
        'registry_employee': 0.80,   # B.46: person is employee of matched org
        'phrase': 0.85,
        'alias_exact': 0.9,
        'alias_phrase': 0.8,
        'alias_contains': 0.7,
        'contains': 0.7,
        'employer_match': 0.6,
        'employer_substring': 0.5,
    }
    strength = base_strengths.get(match_type, 0.5)

    # Proportional specificity scoring (B.52): weight by ratio of distinctive
    # words to total words. All-distinctive = 1.0x (no penalty),
    # all-generic = 0.5x (floor). Intermediate values scale linearly.
    if donor_name_words:
        meaningful = donor_name_words - _GENERIC_BUSINESS_WORDS
        distinctive_ratio = len(meaningful) / len(donor_name_words)
        # Scale from 0.5 (all generic) to 1.0 (all distinctive)
        specificity_multiplier = 0.5 + 0.5 * distinctive_ratio
        strength *= specificity_multiplier

    return min(strength, 1.0)


# ── Text Matching Utilities ──────────────────────────────────

# Richmond City Council — current and recent members.
# Used as fallback when members_present is empty (e.g., eSCRIBE agendas
# which don't include attendance data).  Also includes former members
# whose names appear in contribution data.
#
# IMPORTANT: keep CURRENT_COUNCIL_MEMBERS accurate — it determines
# whether a campaign contribution flag indicates a *sitting official*
# (who can vote on the agenda item) vs. a non-sitting candidate.
# Richmond defaults — used as fallback when city_config is unavailable.
_DEFAULT_CURRENT_COUNCIL = {
    "Eduardo Martinez", "Cesar Zepeda", "Jamelia Brown",
    "Doria Robinson", "Soheila Bana", "Sue Wilson", "Claudia Jimenez",
}
_DEFAULT_FORMER_COUNCIL = {
    "Tom Butt", "Nat Bates", "Jovanka Beckles", "Ben Choi",
    "Jael Myrick", "Vinay Pimple", "Corky Booze", "Jim Rogers",
    "Ahmad Anderson", "Oscar Garcia",
    "Gayle McLaughlin", "Melvin Willis", "Shawn Dunning",
}


def _get_council_members(
    city_fips: str | None = None,
) -> tuple[set[str], set[str]]:
    """Load (current, former) council member name sets.

    Tries city_config registry first; falls back to hardcoded Richmond
    defaults so existing call-sites keep working without a registry.
    """
    if city_fips is not None:
        try:
            from city_config import get_council_member_names

            return get_council_member_names(city_fips)
        except Exception:
            pass
    return _DEFAULT_CURRENT_COUNCIL, _DEFAULT_FORMER_COUNCIL

# --- Temporal correlation configuration ---

# Default lookback window: 5 years (covers longest commission term)
DEFAULT_LOOKBACK_DAYS = 1825


def get_levine_act_threshold(meeting_date_str: str) -> int:
    """Return the Levine Act contribution threshold for a given meeting date.

    SB 1243 raised the threshold from $250 to $500 effective January 1, 2025.
    This affects Government Code § 84308 (the Levine Act), which prohibits
    officials from participating in decisions involving recent contributors
    above the threshold.

    AB 571 mirrors this threshold for permit-related contributions.
    """
    from datetime import datetime

    try:
        meeting_date = datetime.strptime(str(meeting_date_str)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 500  # Default to current law

    # SB 1243 effective date
    if meeting_date.year >= 2025:
        return 500
    return 250

# Time-decay confidence multipliers by days-after-vote
TIME_DECAY_WINDOWS = [
    (90, 1.0),     # 0-90 days: immediate reward
    (180, 0.85),   # 91-180 days: election cycle timing
    (365, 0.7),    # 181-365 days: annual pattern
    (730, 0.5),    # 1-2 years: re-election cycle
    (1825, 0.3),   # 2-5 years: long-term relationship
]


def get_time_decay_multiplier(days_after_vote: int, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> float:
    """Return confidence multiplier based on days between vote and donation.

    Closer donations get higher multipliers (stronger signal).
    Returns 0.0 if beyond the lookback window.
    """
    if days_after_vote > lookback_days:
        return 0.0
    for max_days, multiplier in TIME_DECAY_WINDOWS:
        if days_after_vote <= max_days:
            return multiplier
    return 0.0


def extract_aye_voters(item: dict, consent_votes: list[dict] | None = None) -> set[str]:
    """Extract names of officials who voted Aye on a passed item.

    For action items: reads from item["motions"][*]["votes"].
    For consent items: uses the consent_votes parameter (from consent_calendar level).
    Only considers passed motions.
    """
    voters = set()

    # Action items have their own motions
    for motion in item.get("motions", []):
        if motion.get("result", "").lower() != "passed":
            continue
        for vote in motion.get("votes", []):
            if vote.get("vote", "").lower() == "aye":
                voters.add(vote.get("council_member", ""))

    # Consent items inherit the consent calendar's vote
    if not item.get("motions") and consent_votes:
        for vote in consent_votes:
            if vote.get("vote", "").lower() == "aye":
                voters.add(vote.get("council_member", ""))

    voters.discard("")  # Remove empty strings
    return voters


def scan_temporal_correlations(
    meeting_data: dict,
    contributions: list[dict],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    city_fips: str = "0660620",
) -> list[ConflictFlag]:
    """Scan for donations filed AFTER officials voted favorably on related items.

    For each agenda item with a recorded vote:
    1. Identify officials who voted Aye
    2. Search contributions dated after the meeting
    3. Match donor name/employer to entities in the agenda item
    4. Apply time-decay confidence scoring

    Returns list of ConflictFlag with flag_type='post_vote_donation'.
    """
    from datetime import datetime, timedelta

    meeting_date_str = meeting_data.get("meeting_date", "")
    if not meeting_date_str:
        return []

    try:
        meeting_date = datetime.strptime(meeting_date_str, "%Y-%m-%d").date()
    except ValueError:
        return []

    max_date = meeting_date + timedelta(days=lookback_days)
    flags = []

    # Build council member set for committee-to-official matching
    current, former = _get_council_members(city_fips)
    council_names = current | former

    # Collect items with their vote records
    items_with_votes = []

    # Consent calendar: all items share the same vote record
    consent = meeting_data.get("consent_calendar", {})
    consent_votes = consent.get("votes", [])
    for item in consent.get("items", []):
        aye_voters = extract_aye_voters(item, consent_votes=consent_votes)
        if aye_voters:
            items_with_votes.append((item, aye_voters))

    # Action items: each has its own motions/votes
    for item in meeting_data.get("action_items", []):
        aye_voters = extract_aye_voters(item)
        if aye_voters:
            items_with_votes.append((item, aye_voters))

    # Housing authority items
    for item in meeting_data.get("housing_authority_items", []):
        aye_voters = extract_aye_voters(item)
        if aye_voters:
            items_with_votes.append((item, aye_voters))

    if not items_with_votes:
        return []

    # Filter contributions to only those AFTER the meeting date and within window
    post_vote_contributions = []
    for c in contributions:
        c_date_str = c.get("date") or c.get("contribution_date", "")
        if not c_date_str:
            continue
        try:
            c_date = datetime.strptime(str(c_date_str)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if meeting_date < c_date <= max_date:
            post_vote_contributions.append((c, c_date))

    if not post_vote_contributions:
        return []

    # Map committee names to candidate/official names.
    # extract_candidate_from_committee often returns only a last name
    # (e.g., "Jimenez" from "Jimenez for Richmond 2026"), so we resolve
    # against the known council member set to get the full name.
    committee_to_official = {}
    for c, _ in post_vote_contributions:
        committee = c.get("committee", "")
        if committee and committee not in committee_to_official:
            candidate = extract_candidate_from_committee(committee)
            if candidate:
                # Try to resolve partial name against known council members
                candidate_lower = normalize_text(candidate)
                resolved = None
                for member in council_names:
                    member_lower = normalize_text(member)
                    # Last name match (e.g., "jimenez" in "claudia jimenez")
                    if candidate_lower in member_lower.split() or member_lower in candidate_lower.split():
                        resolved = member
                        break
                    # Full/partial name match via names_match
                    m, _ = names_match(candidate, member)
                    if m:
                        resolved = member
                        break
                committee_to_official[committee] = resolved or candidate

    # For each item, check for post-vote donations from related entities
    seen_flags = set()  # Deduplicate by (item_number, donor, committee)

    for item, aye_voters in items_with_votes:
        item_num = item.get("item_number", "")
        item_title = item.get("title", "")
        item_desc = item.get("description", "")
        item_text = f"{item_title} {item_desc}"

        # Extract entity names from the agenda item
        entities = extract_entity_names(item_text)
        if not entities:
            continue

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
                # (e.g. "city of richmond" as employer matches every agenda item)
                if donor_employer and not _is_government_entity(donor_employer):
                    emp_match, emp_type = names_match(donor_employer, entity)
                    if emp_match:
                        match_type = f"employer_to_{emp_type}"
                        matched_entity = entity
                        break

                # Check direct name match
                name_match_result, name_type = names_match(donor_name, entity)
                if name_match_result:
                    match_type = f"donor_name_to_{name_type}"
                    matched_entity = entity
                    break

            if not match_type:
                continue

            # Deduplicate
            dedup_key = (item_num, donor_name, committee)
            if dedup_key in seen_flags:
                continue
            seen_flags.add(dedup_key)

            # Calculate confidence with time decay
            days_after = (c_date - meeting_date).days
            decay = get_time_decay_multiplier(days_after, lookback_days)

            # Base confidence from match quality and amount
            base_confidence = 0.4
            if "exact" in match_type:
                base_confidence = 0.6
            if amount >= 1000:
                base_confidence += 0.1
            if amount >= 5000:
                base_confidence += 0.1

            confidence = round(min(base_confidence * decay, 1.0), 2)

            # Publication tier — use canonical mapping (single source of truth)
            tier, _label = _confidence_to_tier(confidence)

            # Build evidence
            evidence_entry = {
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
                "lookback_window_days": lookback_days,
                "time_decay_multiplier": decay,
                "match_type": match_type,
            }

            # Build description (purely factual, no judgment)
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

            flags.append(ConflictFlag(
                agenda_item_number=item_num,
                agenda_item_title=item_title,
                council_member=recipient_official,
                flag_type="post_vote_donation",
                description=description,
                evidence=[evidence_entry],
                confidence=confidence,
                legal_reference="Gov. Code \u00a7 87100 (financial interest disclosure)",
                financial_amount=f"${amount:,.2f}",
                publication_tier=tier,
            ))

    return flags


def extract_backer_from_committee(committee_name: str) -> list[str]:
    """Extract identifiable corporate/organizational backer from a PAC name.

    PAC names encode their backers in varied formats:
      "Chevron Richmond PAC" -> ["Chevron"]
      "SEIU Local 1021 PAC for Good Government" -> ["SEIU Local 1021"]
      "Richmond Police Officers Association PAC" -> ["Richmond Police Officers Association"]
      "Independent PAC for Good Government" -> []  (no identifiable backer)

    Conservative: returns empty list if only generic words remain.
    """
    norm = committee_name.strip()
    if not norm:
        return []

    # Strip common PAC/political suffixes (order matters — longest first)
    _pac_suffixes = [
        r'\s+independent\s+expenditure\s+committee',
        r'\s+political\s+action\s+committee',
        r'\s+ie\s+committee',
        r'\s+pac\s+for\s+good\s+government',
        r'\s+for\s+good\s+government',
        r'\s+pac',
        r'\s+committee',
    ]
    cleaned = norm
    for suffix_re in _pac_suffixes:
        cleaned = re.sub(suffix_re + r'$', '', cleaned, flags=re.IGNORECASE).strip()

    # Strip "Independent" prefix (common in IE committee names)
    cleaned = re.sub(r'^independent\s+', '', cleaned, flags=re.IGNORECASE).strip()

    # Strip geographic qualifiers that aren't part of the org identity
    _geo_words = frozenset({
        'richmond', 'california', 'contra costa', 'east bay',
        'bay area', 'west contra costa',
    })
    cleaned_lower = cleaned.lower()
    for geo in sorted(_geo_words, key=len, reverse=True):
        cleaned_lower = re.sub(r'\b' + re.escape(geo) + r'\b', '', cleaned_lower).strip()
    # Reconstruct with original casing by position-matching
    # Simpler approach: just strip from the original cleaned string
    for geo in sorted(_geo_words, key=len, reverse=True):
        cleaned = re.sub(r'\b' + re.escape(geo) + r'\b', '', cleaned, flags=re.IGNORECASE).strip()

    # Clean up multiple spaces and leading/trailing punctuation
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' -,')

    if not cleaned or len(cleaned) < 3:
        return []

    # Filter out results that are purely generic words
    _generic_pac_words = frozenset({
        'local', 'association', 'council', 'coalition', 'alliance',
        'citizens', 'voters', 'people', 'community', 'neighborhood',
        'united', 'action', 'fund', 'campaign', 'political',
        'independent', 'pac', 'committee',
    })
    remaining_words = [w for w in cleaned.lower().split()
                       if w not in _generic_pac_words and len(w) > 1]
    if not remaining_words:
        return []

    return [cleaned]


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


def is_sitting_council_member(
    candidate_name: str,
    current_members: set[str] | None = None,
    alias_groups: dict[str, set[str]] | None = None,
) -> bool:
    """Check if a candidate name matches a current sitting council member.

    Also checks known aliases: if a candidate's legal name differs from
    their public name (e.g., "Kinshasa Curl" vs "Shasa Curl"), the alias
    lookup catches it.
    """
    if current_members is None:
        current_members = _DEFAULT_CURRENT_COUNCIL
    alias_groups = alias_groups or {}
    norm = normalize_text(candidate_name)

    # Build expanded name set: candidate name + any aliases
    names_to_check = {norm}
    names_to_check.update(alias_groups.get(norm, set()))

    for check_name in names_to_check:
        for member in current_members:
            norm_member = normalize_text(member)
            # Check full name match or one contains the other
            if check_name == norm_member:
                return True
            if len(check_name) >= 8 and len(norm_member) >= 8:
                if check_name in norm_member or norm_member in check_name:
                    return True
            # Last-name + first-initial match for common variations
            parts_cand = check_name.split()
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

    # Blocklist: department names and geographic terms that regex captures
    # but aren't vendor/contractor entities
    _entity_blocklist = {
        'city', 'county', 'state', 'the', 'department', 'division',
        'bureau', 'office', 'agency', 'commission', 'committee',
        'board', 'council', 'authority', 'richmond', 'california',
        'contra costa', 'east bay', 'west county', 'san francisco',
        'san pablo', 'el cerrito', 'point richmond',
        'public works', 'community development', 'planning department',
        'finance department', 'police department', 'fire department',
        'human resources', 'city manager', 'city attorney', 'city clerk',
    }

    def _is_valid_entity(name: str) -> bool:
        """Filter extracted entity names for quality."""
        stripped = name.strip().rstrip(',.')
        if len(stripped) <= 3:
            return False
        # Require at least 2 words (single words are too generic)
        if len(stripped.split()) < 2:
            return False
        # Block known non-entity terms
        if stripped.lower() in _entity_blocklist:
            return False
        return True

    # Pattern: "with/from/to [Company Name]"
    preposition_patterns = [
        r'(?:contract|agreement|purchase|payment|amendment)\s+(?:with|from|to)\s+([A-Z][A-Za-z\s&,.\'-]+?)(?:\s+for\s|\s+in\s|\s+to\s|,|\.|$)',
        # Broader pattern: require 8+ chars (was 3+) to reduce noise
        r'(?:from|with|to)\s+([A-Z][A-Za-z\s&,.\'-]{8,}?)(?:\s+for\s|\s+in\s|,|\.|$)',
    ]

    for pattern in preposition_patterns:
        for match in re.finditer(pattern, text):
            name = match.group(1).strip().rstrip(',.')
            if _is_valid_entity(name):
                entities.append(name)

    # Pattern: "Inc.", "LLC", "Corp.", "Co.", "Group", "Services"
    corp_pattern = r'([A-Z][A-Za-z\s&,.\'-]+?(?:Inc|LLC|Corp|Co|Group|Services|Solutions|Associates|Consulting|Partners|Company|Foundation)\.?)'
    for match in re.finditer(corp_pattern, text):
        name = match.group(1).strip().rstrip(',.')
        if _is_valid_entity(name) and name not in entities:
            entities.append(name)

    return entities


def name_in_text(name: str, text: str) -> tuple[bool, str]:
    """Check if a name appears as a contiguous phrase in text.

    Purpose-built for name-to-text matching. Unlike names_match() which uses
    scattered word-overlap (appropriate for name-to-name), this requires the
    name's words to appear adjacent in the text.

    B.52: Also tries matching after stripping business suffixes so
    "ABC Construction Inc." matches text containing "ABC Construction".

    Returns (is_match, match_type):
    - 'exact': normalized name equals normalized text (unlikely for text)
    - 'phrase': name appears as a contiguous substring in text
    - 'no_match': name not found as a phrase
    """
    norm_name = normalize_text(name)
    norm_text = normalize_text(text)

    if not norm_name or not norm_text:
        return False, 'no_match'

    if norm_name == norm_text:
        return True, 'exact'

    # Require minimum 10 chars to avoid matching short common words
    if len(norm_name) >= 10 and norm_name in norm_text:
        return True, 'phrase'

    # B.52: Try again with business suffix stripped, but only when
    # the stripped name has at least one distinctive word to avoid
    # false positives from generic names like "City Services Group".
    norm_stripped = normalize_text(normalize_business_name(name))
    if norm_stripped != norm_name and len(norm_stripped) >= 10:
        stripped_words = set(norm_stripped.split())
        if (stripped_words - _GENERIC_BUSINESS_WORDS) and norm_stripped in norm_text:
            return True, 'phrase'

    return False, 'no_match'


def cached_name_in_text(name: str, text: str, cache: dict) -> tuple[bool, str]:
    """Memoized wrapper around name_in_text (O3 optimization).

    Cache is scoped per scan_meeting_json() call via _ScanContext to avoid
    cross-meeting state leakage. Text key is truncated to 200 chars to
    bound memory usage.
    """
    key = (name, text[:200])
    if key in cache:
        return cache[key]
    result = name_in_text(name, text)
    cache[key] = result
    return result


def names_match(name1: str, name2: str, threshold: float = 0.8) -> tuple[bool, str]:
    """Check if two names match. Returns (is_match, match_type).

    B.52: Also tries matching after normalizing business suffixes so
    "ABC Inc." and "ABC LLC" compare as the same entity.

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

    # B.52: Try suffix-normalized comparison before substring checks
    n1_stripped = normalize_text(normalize_business_name(name1))
    n2_stripped = normalize_text(normalize_business_name(name2))
    if n1_stripped and n2_stripped and n1_stripped == n2_stripped:
        return True, 'exact'

    # One contains the other (handles "National Auto Fleet Group" matching "National Auto Fleet")
    # Require minimum length of 10 chars for substring match to avoid
    # false positives from short names like "martinez" matching in long text.
    # 10 chars covers typical "first last" names (e.g., "cheryl maier" = 12).
    if len(n1) >= 10 and len(n2) >= 10:
        if n1 in n2 or n2 in n1:
            return True, 'contains'

    # B.52: Also try suffix-stripped substring match, but only when the
    # stripped name has at least one distinctive word. Without this guard,
    # generic names like "City Services Group" → "city services" would
    # false-positive match any text containing those common words.
    if len(n1_stripped) >= 10 and len(n2_stripped) >= 10:
        # Check that the shorter stripped name has distinctive content.
        # Use stop_words (broader than _GENERIC_BUSINESS_WORDS, includes
        # geographic terms like 'city', 'county', 'state').
        shorter_stripped = n1_stripped if len(n1_stripped) <= len(n2_stripped) else n2_stripped
        stripped_words = set(shorter_stripped.split())
        has_distinctive = bool(stripped_words - _NAME_MATCH_STOP_WORDS - _GENERIC_BUSINESS_WORDS)
        if has_distinctive and (n1_stripped in n2_stripped or n2_stripped in n1_stripped):
            return True, 'contains'

    # Check if all words of the shorter name appear in the longer
    words1 = set(n1.split())
    words2 = set(n2.split())
    if len(words1) >= 2 and len(words2) >= 2:
        shorter, longer = (words1, words2) if len(words1) <= len(words2) else (words2, words1)
        # Remove common words — includes generic business suffixes and
        # geographic terms that produce false positives when scattered
        # across long text
        shorter_meaningful = shorter - _NAME_MATCH_STOP_WORDS
        longer_meaningful = longer - _NAME_MATCH_STOP_WORDS
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


def prefilter_contributions(contributions: list[dict]) -> list[dict]:
    """Pre-filter contributions to remove entries that will always be filtered.

    Removes government donors, self-donations, and deduplicates. These
    filters don't depend on agenda item text, so they can be applied once
    for batch operations instead of 110K times per agenda item.

    Returns a smaller list suitable for passing to scan_meeting_json().
    """
    seen = set()
    filtered = []
    for c in contributions:
        donor_name = c.get("donor_name") or c.get("contributor_name", "")
        donor_employer = c.get("donor_employer") or c.get("contributor_employer", "")
        committee = c.get("committee_name") or c.get("committee", "")
        amount = c.get("amount", 0)

        # Dedup
        dedup_key = (donor_name, str(amount), c.get("date", ""), committee)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Government donor filter
        norm_donor = normalize_text(donor_name)
        if len(norm_donor) < 4:
            continue
        if _is_government_entity(donor_name):
            continue

        # Self-donation filter (direct substring match)
        norm_committee = normalize_text(committee)
        if len(norm_donor) > 4 and norm_donor in norm_committee:
            continue

        # Self-donation filter (committee-to-committee transfers)
        # Catches e.g. "Claudia Jimenez for District 6 2020" donating to
        # "Claudia Jimenez for District 6 2024" — same candidate, different cycles.
        donor_candidate = extract_candidate_from_committee(donor_name)
        committee_candidate = extract_candidate_from_committee(committee)
        if donor_candidate and committee_candidate:
            match, _ = names_match(donor_candidate, committee_candidate)
            if match:
                continue

        # O1: Pre-compute normalized values to avoid redundant normalize_text()
        # calls in signal_campaign_contribution(). These are read by the signal
        # detector with fallback for non-batch callers.
        c["_norm_donor"] = norm_donor
        c["_norm_employer"] = normalize_text(donor_employer) if donor_employer else ""
        c["_norm_committee"] = norm_committee
        c["_donor_words"] = set(w for w in norm_donor.split() if len(w) >= 4)
        c["_employer_words"] = set(w for w in c["_norm_employer"].split() if len(w) >= 4)

        filtered.append(c)
    return filtered


def build_contribution_word_index(contributions: list[dict]) -> dict[str, list[int]]:
    """Map each 4+ char word from donor names and employers to contribution indices.

    Used by signal_campaign_contribution() in batch mode to replace
    the linear word-overlap pre-screen with an inverted index lookup.
    Works with both pre-processed (O1) and raw contribution dicts.
    """
    index: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(contributions):
        # Use pre-computed word sets from O1 (prefilter_contributions),
        # falling back to computing on the fly for non-batch callers (tests, single-meeting).
        donor_words = c.get("_donor_words")
        if donor_words is None:
            dn = c.get("donor_name") or c.get("contributor_name", "")
            donor_words = set(w for w in normalize_text(dn).split() if len(w) >= 4)
        employer_words = c.get("_employer_words")
        if employer_words is None:
            de = c.get("donor_employer") or c.get("contributor_employer", "")
            employer_words = set(w for w in normalize_text(de).split() if len(w) >= 4) if de else set()
        for word in donor_words | employer_words:
            index[word].append(i)
    return index








# ── v3 Signal-to-Flag Conversion ─────────────────────────────

def _signals_to_flags(
    signals: list[RawSignal],
    item_num: str,
    item_title: str,
    financial: Optional[str],
    current_officials: set,
    alias_groups: dict,
) -> list[ConflictFlag]:
    """Convert RawSignals to ConflictFlags using v3 composite confidence.

    Groups signals by council_member so that multiple independent signal types
    for the same official on the same item produce corroboration boosts.
    Each signal still produces its own ConflictFlag, but the confidence score
    benefits from corroboration when sibling signals exist.
    """
    from collections import defaultdict

    flags: list[ConflictFlag] = []
    if not signals:
        return flags

    # Group signals by council_member for corroboration
    by_official: dict[str, list[RawSignal]] = defaultdict(list)
    for signal in signals:
        by_official[signal.council_member].append(signal)

    # B.52: Define independent source categories for confirmed match detection.
    # Signals from 3+ distinct categories confirm the entity match.
    _SOURCE_CATEGORIES = {
        "campaign_contribution": "contributions",
        "donor_vendor_expenditure": "expenditures",
        "form700_real_property": "form700",
        "form700_income": "form700",
        "form700_investment": "form700",
        "temporal_correlation": "contributions",
        "independent_expenditure": "contributions",
        "permit_donor": "permits",
        "license_donor": "licenses",
    }

    for official, official_signals in by_official.items():
        # Determine sitting status (consistent for all signals for this official)
        is_sitting = official_signals[0].match_details.get("is_sitting", None)
        if is_sitting is None:
            is_sitting = is_sitting_council_member(
                official, current_officials, alias_groups
            )

        # B.52: Confirmed match detection — when the same entity appears
        # in 3+ independent source categories, set match_strength to 1.0
        source_categories = {
            _SOURCE_CATEGORIES.get(s.signal_type, s.signal_type)
            for s in official_signals
        }
        is_confirmed = len(source_categories) >= 3

        # If confirmed, boost match_strength on all signals for this official
        if is_confirmed:
            for signal in official_signals:
                signal.match_strength = 1.0
                signal.match_details["confirmed_match"] = True
                signal.match_details["confirming_sources"] = sorted(source_categories)

        # Compute composite confidence using ALL signals for corroboration
        group_result = compute_composite_confidence(official_signals, is_sitting=is_sitting)

        # Each signal still produces its own flag, but with the corroborated confidence
        for signal in official_signals:
            description = apply_hedge_clause(signal.description, group_result["confidence"])

            # B.52: Add match_confidence explaining the score to match_details
            signal.match_details["match_confidence"] = {
                "match_strength": round(signal.match_strength, 4),
                "specificity_basis": "confirmed_multi_source" if is_confirmed else "text_match",
                "composite_confidence": group_result["confidence"],
                "publication_tier": group_result["publication_tier"],
                "tier_label": group_result["tier_label"],
            }

            flags.append(ConflictFlag(
                agenda_item_number=signal.agenda_item_number,
                agenda_item_title=item_title,
                council_member=signal.council_member,
                flag_type=signal.signal_type,
                description=description,
                evidence=signal.evidence,
                confidence=group_result["confidence"],
                legal_reference=signal.legal_reference,
                financial_amount=signal.financial_amount,
                publication_tier=group_result["publication_tier"],
                confidence_factors=group_result["factors"],
                scanner_version=3,
                match_details=signal.match_details if signal.match_details else None,
            ))
    return flags










# ── JSON Mode Scanner (pre-database) ─────────────────────────

def scan_meeting_json(
    meeting_data: dict,
    contributions: list[dict],
    form700_interests: list[dict] = None,
    city_fips: str = "0660620",
    expenditures: list[dict] = None,
    independent_expenditures: list[dict] = None,
    permits: list[dict] = None,
    licenses: list[dict] = None,
    entity_graph: dict = None,
    org_reverse_map: dict = None,
    behested_payments: list[dict] = None,
    lobbyist_registrations: list[dict] = None,
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
        expenditures: List of dicts with keys (from city_expenditures):
            normalized_vendor, vendor_name, amount, fiscal_year, department
        permits: List of dicts with keys (from city_permits):
            applied_by, permit_type, permit_no, job_value, applied_date, status
        licenses: List of dicts with keys (from city_licenses):
            company, normalized_company, company_dba, business_type, status
        entity_graph: B.46 entity graph: {normalized_person_name -> [{org connections}]}
        org_reverse_map: B.46 reverse map: {normalized_org_name -> [{person connections}]}

    Returns:
        ScanResult with all detected flags
    """
    form700_interests = form700_interests or []
    expenditures = expenditures or []
    independent_expenditures = independent_expenditures or []
    permits = permits or []
    licenses = licenses or []
    entity_graph = entity_graph or {}
    org_reverse_map = org_reverse_map or {}
    behested_payments = behested_payments or []
    lobbyist_registrations = lobbyist_registrations or []
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
        "filtered_self_donation": 0,
        "filtered_dedup": 0,
        "filtered_short_name": 0,
        "passed_to_flag": 0,
        "suppressed_near_miss": 0,
    }

    # Load council members from city config (used for false-positive
    # suppression and sitting-member detection)
    current_officials, former_officials = _get_council_members(city_fips)

    # Load aliases from officials.json (e.g., "Kinshasa Curl" -> "Shasa Curl")
    alias_groups = _load_alias_map(city_fips)

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
            # Add known aliases for this name
            for alias in alias_groups.get(name, set()):
                council_member_names.add(alias)

    # Fallback: when members_present is empty (eSCRIBE agendas, pre-meeting
    # extraction), use council members from city config registry
    if not council_member_names:
        for name in current_officials | former_officials:
            norm = normalize_text(name)
            council_member_names.add(norm)
            parts = norm.split()
            if len(parts) >= 2:
                council_member_names.add(parts[-1])
            # Add known aliases
            for alias in alias_groups.get(norm, set()):
                council_member_names.add(alias)

    # De-duplicate contributions to avoid flagging the same donation
    # multiple times (CAL-ACCESS has duplicate filing records)
    seen_contributions = set()

    # B.51: Build contribution baselines for anomaly detection
    contribution_baselines = build_contribution_baselines(contributions)

    # Build shared scan context for signal detectors
    ctx = _ScanContext(
        council_member_names=council_member_names,
        alias_groups=alias_groups,
        current_officials=current_officials,
        former_officials=former_officials,
        seen_contributions=seen_contributions,
        audit_logger=audit_logger,
        filter_counts=filter_counts,
        meeting_date=meeting_data.get("meeting_date", ""),
        city_fips=city_fips,
        name_in_text_cache={},
        contribution_baselines=contribution_baselines,
        entity_graph=entity_graph,
        org_reverse_map=org_reverse_map,
        behested_payments=behested_payments,
        lobbyist_registrations=lobbyist_registrations,
    )

    # O2: Build inverted word index for contribution pre-screening
    contrib_word_index = build_contribution_word_index(contributions)

    # Build vendor gazetteer from expenditures (distinct vendor names >= 10 chars)
    # Filter out government entities — "city of richmond" as a vendor is civic noise
    vendor_gazetteer = list({
        v for exp in expenditures
        if len((v := (exp.get("normalized_vendor") or exp.get("vendor_name", "")).strip())) >= 10
        and not _is_government_entity(v)
    })

    # O4: Pre-filter Form 700 interests to present council members only.
    # Non-present members can never produce valid flags (no vote record).
    present_members_raw = [m.get("name", "") for m in meeting_data.get("members_present", [])]
    present_members_norm = {normalize_text(name) for name in present_members_raw if name}
    if present_members_norm and form700_interests:
        relevant_interests = [
            interest for interest in form700_interests
            if normalize_text(interest.get("council_member", "")) in present_members_norm
            or any(
                names_match(interest.get("council_member", ""), raw_name)[0]
                for raw_name in present_members_raw if raw_name
            )
        ]
    else:
        relevant_interests = form700_interests  # fallback: check all (e.g., eSCRIBE agendas)

    # ── Temporal correlation prep ──
    # Pre-filter contributions to those AFTER the meeting date for temporal analysis
    from datetime import datetime, timedelta
    post_vote_contributions = []
    meeting_date_str = meeting_data.get("meeting_date", "")
    meeting_date_obj = None
    if meeting_date_str:
        try:
            meeting_date_obj = datetime.strptime(meeting_date_str, "%Y-%m-%d").date()
            max_temporal_date = meeting_date_obj + timedelta(days=DEFAULT_LOOKBACK_DAYS)
            for c in contributions:
                c_date_str = c.get("date") or c.get("contribution_date", "")
                if not c_date_str:
                    continue
                try:
                    c_date = datetime.strptime(str(c_date_str)[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
                if meeting_date_obj < c_date <= max_temporal_date:
                    post_vote_contributions.append((c, c_date))
        except ValueError:
            pass

    # Map committee names to officials for temporal correlation
    council_names = current_officials | former_officials
    committee_to_official: dict[str, str] = {}
    for c, _ in post_vote_contributions:
        committee = c.get("committee") or c.get("committee_name", "")
        if committee and committee not in committee_to_official:
            candidate = extract_candidate_from_committee(committee)
            if candidate:
                candidate_lower = normalize_text(candidate)
                resolved = None
                for member in council_names:
                    member_lower = normalize_text(member)
                    if candidate_lower in member_lower.split() or member_lower in candidate_lower.split():
                        resolved = member
                        break
                    m, _ = names_match(candidate, member)
                    if m:
                        resolved = member
                        break
                committee_to_official[committee] = resolved or candidate

    # Collect all agenda items (consent + action + housing authority)
    all_items = []
    consent = meeting_data.get("consent_calendar", {})
    consent_votes = consent.get("votes", [])
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

        # Skip top-level section headers (bare letters/roman numerals like
        # "V", "M", "C", "III"). These are containers like "CITY COUNCIL
        # CONSENT CALENDAR" or "CLOSED SESSION" with no actionable content.
        # Defense-in-depth: the eSCRIBE converter should already filter these,
        # but minutes extraction may produce them.
        # Note: only match pure letter sequences — items like "H-1" from
        # minutes extraction are legitimate action items.
        if item_num and re.match(r'^[A-Z]+$', item_num):
            skipped_headers.add(item_num)
            continue

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

        # ── v3 Signal-Based Detection ──
        # Extract entity names and build word sets for the item
        entities = extract_entity_names(item_text)
        norm_item_words = set(
            w for w in normalize_text(item_text).split() if len(w) >= 4
        )
        norm_original_words = set(
            w for w in normalize_text(original_text).split() if len(w) >= 4
        )
        text_words = norm_item_words | norm_original_words

        # Collect all signals for this item
        item_signals: list[RawSignal] = []

        # 1. Campaign contribution signals
        campaign_signals = signal_campaign_contribution(
            item_num=item_num,
            item_title=item_title,
            item_text=item_text,
            original_text=original_text,
            financial=financial,
            entities=entities,
            text_words=text_words,
            contributions=contributions,
            ctx=ctx,
            contrib_word_index=contrib_word_index,
        )
        item_signals.extend(campaign_signals)

        # Build VendorDonorMatch objects from campaign signal metadata
        # (preserves compatibility with ScanResult.vendor_matches)
        for sig in campaign_signals:
            md = sig.match_details
            vendor_matches.append(VendorDonorMatch(
                vendor_name=item_title,
                donor_name=md.get("donor_name", ""),
                donor_employer=md.get("donor_employer", ""),
                match_type=md.get("match_type", ""),
                council_member=md.get("candidate", md.get("council_member", "")),
                committee_name=md.get("committee", ""),
                contribution_amount=md.get("total_amount", 0),
                contribution_date=md.get("contribution_dates", [""])[0] if md.get("contribution_dates") else "",
                filing_id=md.get("filing_id", ""),
                source=md.get("source", ""),
            ))

        # 2. Form 700 property signals (only for land-use items)
        # Keywords that indicate an item involves real property / zoning decisions
        zoning_keywords = [
            "rezone", "rezoning", "zoning", "conditional use",
            "subdivision", "variance", "design review",
            "land use", "general plan", "specific plan", "entitlement",
            "development project", "development agreement", "development permit",
            "housing development", "real property", "parcel",
        ]
        appointment_keywords = [
            "appointment", "reappointment", "commission", "board",
            "task force", "committee", "advisory",
        ]
        norm_item = normalize_text(item_text)
        is_land_use = any(kw in norm_item for kw in zoning_keywords)
        is_appointment = any(kw in norm_item for kw in appointment_keywords)
        if is_appointment:
            is_land_use = False

        # Filter out statutory "subdivision" matches — Gov Code section
        # references like "subdivision (d) of Government Code Section 54956.9"
        # appear in every closed session item and are not land subdivisions.
        if is_land_use and "subdivision" in norm_item:
            # Check if "subdivision" only appears in legal code citations
            # Pattern: "subdivision" followed by parenthetical letter/number
            statute_pattern = r"subdivision\s*\([a-z0-9]\)"
            real_subdivision_refs = re.sub(statute_pattern, "", norm_item)
            if "subdivision" not in real_subdivision_refs:
                is_land_use = any(
                    kw in norm_item for kw in zoning_keywords if kw != "subdivision"
                )

        if is_land_use:
            property_signals = signal_form700_property(
                item_num=item_num,
                item_title=item_title,
                item_text=item_text,
                financial=financial,
                form700_interests=relevant_interests,
            )
            item_signals.extend(property_signals)

        # 3. Form 700 income/investment signals
        income_signals = signal_form700_income(
            item_num=item_num,
            item_title=item_title,
            item_text=item_text,
            financial=financial,
            entities=entities,
            form700_interests=relevant_interests,
        )
        item_signals.extend(income_signals)

        # 4. Temporal correlation signals (post-vote donations)
        if post_vote_contributions:
            # Determine consent_votes for this item
            item_consent_votes = consent_votes if item in consent.get("items", []) else []
            aye_voters = extract_aye_voters(item, consent_votes=item_consent_votes)
            if aye_voters:
                temporal_signals = signal_temporal_correlation(
                    item=item,
                    item_num=item_num,
                    item_title=item_title,
                    item_text=item_text,
                    financial=financial,
                    entities=entities,
                    aye_voters=aye_voters,
                    post_vote_contributions=post_vote_contributions,
                    committee_to_official=committee_to_official,
                    ctx=ctx,
                )
                item_signals.extend(temporal_signals)

        # 5. Donor-vendor-expenditure cross-reference signals
        if expenditures and vendor_gazetteer:
            vendor_expenditure_signals = signal_donor_vendor_expenditure(
                item_num=item_num,
                item_title=item_title,
                item_text=item_text,
                financial=financial,
                vendor_gazetteer=vendor_gazetteer,
                contributions=contributions,
                expenditures=expenditures,
                ctx=ctx,
            )
            item_signals.extend(vendor_expenditure_signals)

        # 6. Independent expenditure signals (PAC spending for/against candidates)
        if independent_expenditures:
            ie_signals = signal_independent_expenditure(
                item_num=item_num,
                item_title=item_title,
                item_text=item_text,
                financial=financial,
                independent_expenditures=independent_expenditures,
                ctx=ctx,
            )
            item_signals.extend(ie_signals)

        # 7. Permit-donor cross-reference signals (B.45 / B.53)
        if permits:
            permit_signals = signal_permit_donor(
                item_num=item_num,
                item_title=item_title,
                item_text=item_text,
                financial=financial,
                permits=permits,
                contributions=contributions,
                ctx=ctx,
            )
            item_signals.extend(permit_signals)

        # 8. License-donor cross-reference signals (B.45 / B.53)
        if licenses:
            license_signals = signal_license_donor(
                item_num=item_num,
                item_title=item_title,
                item_text=item_text,
                financial=financial,
                licenses=licenses,
                contributions=contributions,
                expenditures=expenditures,
                ctx=ctx,
            )
            item_signals.extend(license_signals)

        # 9. LLC ownership chain signals (B.46 entity resolution)
        if ctx.org_reverse_map:
            llc_signals = signal_llc_ownership_chain(
                item_num=item_num,
                item_title=item_title,
                item_text=item_text,
                financial=financial,
                entities=entities,
                contributions=contributions,
                ctx=ctx,
            )
            item_signals.extend(llc_signals)

        # 10. Behested payment signals (S13.1 — FPPC Form 803)
        if behested_payments:
            behested_signals = signal_behested_payment(
                item_num=item_num,
                item_title=item_title,
                item_text=item_text,
                financial=financial,
                entities=entities,
                behested_payments=behested_payments,
                contributions=contributions,
                ctx=ctx,
            )
            item_signals.extend(behested_signals)

        # 11. Lobbyist-client-donor signals (S13.3)
        if lobbyist_registrations:
            lobbyist_signals = signal_unregistered_lobbyist(
                item_num=item_num,
                item_title=item_title,
                item_text=item_text,
                financial=financial,
                entities=entities,
                lobbyist_registrations=lobbyist_registrations,
                contributions=contributions,
                ctx=ctx,
            )
            item_signals.extend(lobbyist_signals)

        # 12. Behested payment loop signals (S13.5 — influence cycle)
        if behested_payments and contributions:
            loop_signals = signal_behested_payment_loop(
                item_num=item_num,
                item_title=item_title,
                item_text=item_text,
                financial=financial,
                entities=entities,
                behested_payments=behested_payments,
                lobbyist_registrations=lobbyist_registrations,
                contributions=contributions,
                ctx=ctx,
            )
            item_signals.extend(loop_signals)

        # Convert signals to flags via v3 composite confidence
        if item_signals:
            v3_flags = _signals_to_flags(
                signals=item_signals,
                item_num=item_num,
                item_title=item_title,
                financial=financial,
                current_officials=current_officials,
                alias_groups=alias_groups,
            )
            flags.extend(v3_flags)
            for f in v3_flags:
                flagged_items.add(f.agenda_item_number)
                filter_counts["passed_to_flag"] += 1

    # Identify clean items (unflagged items + skipped section headers)
    all_item_nums = [item.get("item_number", "") for item in all_items]
    clean_items = [n for n in all_item_nums if n not in flagged_items]
    # Skipped headers are also clean (they were excluded from scanning)
    for h in skipped_headers:
        if h not in clean_items:
            clean_items.append(h)

    # Tally surname frequency tiers across all contributions compared
    donor_tier_counts = {1: 0, 2: 0, 3: 0, 4: 0, None: 0}
    for contribution in contributions:
        dname = contribution.get("donor_name") or contribution.get("contributor_name") or ""
        tokens = dname.strip().split()
        surname = tokens[-1] if tokens else ""
        tier = lookup_surname_frequency_tier(surname)
        donor_tier_counts[tier] = donor_tier_counts.get(tier, 0) + 1

    # Tally surname tiers for flagged donors only
    flagged_tier_counts = {1: 0, 2: 0, 3: 0, 4: 0, None: 0}
    for decision in audit_logger.decisions:
        if decision.matched:
            tier = decision.bias_signals.get("surname_frequency_tier") if decision.bias_signals else None
            flagged_tier_counts[tier] = flagged_tier_counts.get(tier, 0) + 1

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
        donors_surname_tier_1=donor_tier_counts.get(1, 0),
        donors_surname_tier_2=donor_tier_counts.get(2, 0),
        donors_surname_tier_3=donor_tier_counts.get(3, 0),
        donors_surname_tier_4=donor_tier_counts.get(4, 0),
        donors_surname_unknown=donor_tier_counts.get(None, 0),
        flagged_surname_tier_1=flagged_tier_counts.get(1, 0),
        flagged_surname_tier_2=flagged_tier_counts.get(2, 0),
        flagged_surname_tier_3=flagged_tier_counts.get(3, 0),
        flagged_surname_tier_4=flagged_tier_counts.get(4, 0),
        flagged_surname_unknown=flagged_tier_counts.get(None, 0),
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

def _fetch_meeting_data_from_db(conn, meeting_id: str, city_fips: str) -> dict:
    """Fetch meeting data from Layer 2 tables and format for scan_meeting_json().

    Constructs a meeting_data dict matching the JSON extraction format:
    - meeting_date, meeting_type
    - members_present (from meeting_attendance — who was actually at the meeting)
    - consent_calendar.items, action_items, housing_authority_items
    """
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

        # Get members present from attendance records (ground truth for who was sitting)
        cur.execute(
            """SELECT o.name
               FROM meeting_attendance ma
               JOIN officials o ON ma.official_id = o.id
               WHERE ma.meeting_id = %s AND ma.status IN ('present', 'late')""",
            (meeting_id,),
        )
        members_present = [{"name": row[0]} for row in cur.fetchall()]

        # Get all agenda items for this meeting
        cur.execute(
            """SELECT item_number, title, description, financial_amount,
                      is_consent_calendar
               FROM agenda_items
               WHERE meeting_id = %s
                 AND agenda_source_retired_at IS NULL
               ORDER BY item_number""",
            (meeting_id,),
        )
        items = cur.fetchall()

        consent_items = []
        action_items = []
        for item_num, title, desc, financial, is_consent in items:
            item_dict = {
                "item_number": item_num or "",
                "title": title or "",
                "description": desc or "",
                "financial_amount": financial or "",
            }
            if is_consent:
                consent_items.append(item_dict)
            else:
                action_items.append(item_dict)

    return {
        "meeting_date": str(meeting_date),
        "meeting_type": meeting_type or "unknown",
        "members_present": members_present,
        "consent_calendar": {"items": consent_items},
        "action_items": action_items,
        "housing_authority_items": [],  # HA items are in action_items in DB schema
    }


def _fetch_contributions_from_db(conn, city_fips: str) -> list[dict]:
    """Fetch all contributions from Layer 2 in scan_meeting_json() format.

    Returns list of dicts with keys matching what scan_meeting_json expects:
    donor_name, donor_employer, council_member, committee_name, amount, date,
    filing_id, source.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.name, d.employer,
                      COALESCE(o.name, '') AS official_name,
                      cm.name AS committee_name,
                      co.amount, co.contribution_date, co.filing_id, co.source
               FROM contributions co
               JOIN donors d ON co.donor_id = d.id
               JOIN committees cm ON co.committee_id = cm.id
               LEFT JOIN officials o ON cm.official_id = o.id
               WHERE co.city_fips = %s""",
            (city_fips,),
        )
        return [
            {
                "donor_name": row[0] or "",
                "donor_employer": row[1] or "",
                "council_member": row[2],
                "committee_name": row[3] or "",
                "amount": float(row[4]),
                "date": str(row[5]) if row[5] else "",
                "filing_id": row[6] or "",
                "source": row[7] or "",
            }
            for row in cur.fetchall()
        ]


def _fetch_form700_interests_from_db(
    conn, city_fips: str, meeting_date: str | None = None,
) -> list[dict]:
    """Fetch Form 700 economic interests from Layer 2.

    Returns interests for ALL officials who have filings — not just
    is_current=TRUE. For historical meetings, the relevant official
    may no longer be sitting. The scanner's own sitting-member logic
    (via meeting_attendance) handles determining relevance.

    If meeting_date is provided, filters to filings whose period
    overlaps the meeting date (when period data is available).
    """
    with conn.cursor() as cur:
        query = """
            SELECT o.name, ei.interest_type, ei.description,
                   ei.filing_year, ei.location,
                   f.source_url
            FROM economic_interests ei
            JOIN officials o ON ei.official_id = o.id
            LEFT JOIN form700_filings f ON ei.filing_id = f.id
            WHERE ei.city_fips = %s
        """
        params: list = [city_fips]

        # If we have a meeting date, prefer filings temporally relevant
        # to that meeting. But include all filings — the scanner determines
        # relevance via attendance-based sitting detection.
        cur.execute(query, params)

        return [
            {
                "council_member": row[0] or "",
                "interest_type": row[1] or "",
                "description": row[2] or "",
                "filing_year": row[3],
                "location": row[4] or "",
                "source_url": row[5] or "",
            }
            for row in cur.fetchall()
        ]


def _fetch_expenditures_from_db(conn, city_fips: str) -> list[dict]:
    """Fetch city expenditures from Layer 2 for donor-vendor cross-reference.

    Returns dicts with keys matching signal_donor_vendor_expenditure() expectations:
    vendor_name, normalized_vendor, amount, fiscal_year, department, expenditure_date.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT vendor_name, normalized_vendor, amount,
                   fiscal_year, department, expenditure_date
            FROM city_expenditures
            WHERE city_fips = %s
            """,
            (city_fips,),
        )
        return [
            {
                "vendor_name": row[0] or "",
                "normalized_vendor": row[1] or "",
                "amount": float(row[2]) if row[2] else 0.0,
                "fiscal_year": row[3] or "",
                "department": row[4] or "",
                "expenditure_date": str(row[5]) if row[5] else "",
            }
            for row in cur.fetchall()
        ]


def _fetch_independent_expenditures_from_db(conn, city_fips: str) -> list[dict]:
    """Fetch independent expenditures from Layer 2 for IE signal detector.

    Returns dicts with keys matching signal_independent_expenditure() expectations:
    committee_name, candidate_name, support_or_oppose, amount, expenditure_date,
    description, payee_name, filing_id, source.

    Only fetches support (S) records — oppose IEs don't create financial
    interest signals for the candidate.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT committee_name, candidate_name, support_or_oppose,
                   amount, expenditure_date, description, payee_name,
                   filing_id, source
            FROM independent_expenditures
            WHERE city_fips = %s AND support_or_oppose = 'S'
            """,
            (city_fips,),
        )
        return [
            {
                "committee_name": row[0] or "",
                "candidate_name": row[1] or "",
                "support_or_oppose": row[2] or "",
                "amount": float(row[3]) if row[3] else 0.0,
                "expenditure_date": str(row[4]) if row[4] else "",
                "description": row[5] or "",
                "payee_name": row[6] or "",
                "filing_id": row[7] or "",
                "source": row[8] or "",
            }
            for row in cur.fetchall()
        ]


def _fetch_permits_from_db(conn, city_fips: str) -> list[dict]:
    """Fetch city permits from Layer 2 for permit-donor cross-reference.

    Returns dicts with keys matching signal_permit_donor() expectations:
    applied_by, permit_type, permit_no, job_value, applied_date, status.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT applied_by, permit_type, permit_no,
                   job_value, applied_date, status, description
            FROM city_permits
            WHERE city_fips = %s AND applied_by IS NOT NULL
              AND applied_by != ''
            """,
            (city_fips,),
        )
        return [
            {
                "applied_by": row[0] or "",
                "permit_type": row[1] or "",
                "permit_no": row[2] or "",
                "job_value": float(row[3]) if row[3] else 0.0,
                "applied_date": str(row[4]) if row[4] else "",
                "status": row[5] or "",
                "description": row[6] or "",
            }
            for row in cur.fetchall()
        ]


def _fetch_licenses_from_db(conn, city_fips: str) -> list[dict]:
    """Fetch business licenses from Layer 2 for license-donor cross-reference.

    Returns dicts with keys matching signal_license_donor() expectations:
    company, normalized_company, company_dba, business_type, status.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT company, normalized_company, company_dba,
                   business_type, status, license_issued
            FROM city_licenses
            WHERE city_fips = %s AND (company IS NOT NULL AND company != '')
            """,
            (city_fips,),
        )
        return [
            {
                "company": row[0] or "",
                "normalized_company": row[1] or "",
                "company_dba": row[2] or "",
                "business_type": row[3] or "",
                "status": row[4] or "",
                "license_issued": str(row[5]) if row[5] else "",
            }
            for row in cur.fetchall()
        ]


def _fetch_behested_from_db(conn, city_fips: str) -> list[dict]:
    """Fetch behested payments for scanner cross-referencing."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT official_name, payor_name, payee_name, amount,
                      payment_date, filing_date, description, source_url
               FROM behested_payments
               WHERE city_fips = %s""",
            (city_fips,),
        )
        return [
            {
                "official_name": row[0] or "",
                "payor_name": row[1] or "",
                "payee_name": row[2] or "",
                "amount": float(row[3]) if row[3] else 0,
                "payment_date": str(row[4]) if row[4] else "",
                "filing_date": str(row[5]) if row[5] else "",
                "description": row[6] or "",
                "source_url": row[7] or "",
            }
            for row in cur.fetchall()
        ]


def _fetch_lobbyists_from_db(conn, city_fips: str) -> list[dict]:
    """Fetch lobbyist registrations for scanner cross-referencing."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT lobbyist_name, lobbyist_firm, client_name,
                      registration_date, topics, status
               FROM lobbyist_registrations
               WHERE city_fips = %s
                 AND (status = 'active' OR expiration_date IS NULL
                      OR expiration_date >= CURRENT_DATE)""",
            (city_fips,),
        )
        return [
            {
                "lobbyist_name": row[0] or "",
                "lobbyist_firm": row[1] or "",
                "client_name": row[2] or "",
                "registration_date": str(row[3]) if row[3] else "",
                "topics": row[4] or "",
                "status": row[5] or "active",
            }
            for row in cur.fetchall()
        ]


def scan_meeting_db(
    conn,
    meeting_id: str,
    city_fips: str = "0660620",
    contributions: list[dict] | None = None,
    form700_interests: list[dict] | None = None,
    expenditures: list[dict] | None = None,
    independent_expenditures: list[dict] | None = None,
    permits: list[dict] | None = None,
    licenses: list[dict] | None = None,
    entity_graph: dict | None = None,
    org_reverse_map: dict | None = None,
    behested_payments: list[dict] | None = None,
    lobbyist_registrations: list[dict] | None = None,
) -> ScanResult:
    """Scan a meeting using database queries for cross-referencing.

    Fetches meeting data, contributions, Form 700 interests, city
    expenditures, permits, and licenses from Layer 2 tables, then delegates
    to scan_meeting_json() for the actual scanning logic. This ensures DB
    mode uses the full v3 signal architecture:
    - Eight independent signal detectors (campaign, form700_property,
      form700_income, temporal_correlation, donor_vendor_expenditure,
      independent_expenditure, permit_donor, license_donor)
    - Composite confidence with corroboration boost
    - Council member name suppression (via meeting_attendance)
    - Government entity donor/employer filtering
    - Self-donation filtering
    - Section header skipping
    - name_in_text() contiguous phrase matching
    - Specificity scoring penalty for generic-word donors
    - Contribution deduplication and per-donor aggregation
    - $100 materiality threshold
    - Publication tier assignment
    - Bias audit logging

    Uses meeting_attendance records (ground truth from minutes) to
    determine who was sitting at the meeting, not officials.is_current.
    This correctly handles historical meetings with different council
    compositions.

    For batch operations, pass pre-loaded contributions, form700_interests,
    expenditures, independent_expenditures, permits, and licenses to avoid
    re-fetching the same data for every meeting.
    """
    # Load operator config for this city into context (once per scan)
    from operator_config import load_from_db, set_scan_config
    set_scan_config(load_from_db(conn, city_fips))

    meeting_data = _fetch_meeting_data_from_db(conn, meeting_id, city_fips)
    if contributions is None:
        contributions = _fetch_contributions_from_db(conn, city_fips)
    if form700_interests is None:
        form700_interests = _fetch_form700_interests_from_db(
            conn, city_fips, meeting_data.get("meeting_date"),
        )
    if expenditures is None:
        expenditures = _fetch_expenditures_from_db(conn, city_fips)
    if independent_expenditures is None:
        independent_expenditures = _fetch_independent_expenditures_from_db(conn, city_fips)
    if permits is None:
        permits = _fetch_permits_from_db(conn, city_fips)
    if licenses is None:
        licenses = _fetch_licenses_from_db(conn, city_fips)

    # B.46: Load entity graph for LLC ownership chain detection
    if entity_graph is None or org_reverse_map is None:
        from db import (
            load_entity_graph as _load_eg,
            load_org_reverse_map as _load_orm,
        )
        if entity_graph is None:
            entity_graph = _load_eg(conn, city_fips)
        if org_reverse_map is None:
            org_reverse_map = _load_orm(conn, city_fips)

    # S13: Load behested payments and lobbyist registrations
    if behested_payments is None:
        behested_payments = _fetch_behested_from_db(conn, city_fips)
    if lobbyist_registrations is None:
        lobbyist_registrations = _fetch_lobbyists_from_db(conn, city_fips)

    return scan_meeting_json(
        meeting_data=meeting_data,
        contributions=contributions,
        form700_interests=form700_interests,
        city_fips=city_fips,
        expenditures=expenditures,
        independent_expenditures=independent_expenditures,
        permits=permits,
        licenses=licenses,
        entity_graph=entity_graph,
        org_reverse_map=org_reverse_map,
        behested_payments=behested_payments,
        lobbyist_registrations=lobbyist_registrations,
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


# ── Ground Truth Review ──────────────────────────────────────

def load_audit_sidecar(path: Path) -> dict | None:
    """Load an audit sidecar JSON file. Returns None if file missing."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def apply_verdict(decision: dict, verdict: str, notes: str | None):
    """Apply a ground truth verdict to an audit decision dict.

    Args:
        decision: Dict from sidecar's decisions list (mutated in place).
        verdict: 'T' for true positive, 'F' for false positive.
        notes: Optional reviewer notes.
    """
    from datetime import datetime, timezone
    decision["ground_truth"] = verdict == "T"
    decision["ground_truth_source"] = f"manual_review_{datetime.now(timezone.utc).isoformat()}"
    if notes:
        decision["audit_notes"] = notes


def find_latest_audit_sidecar(audit_dir: Path) -> Path | None:
    """Find the most recently created audit sidecar file."""
    if not audit_dir.exists():
        return None
    files = sorted(audit_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Skip files that start with "bias_audit_report" (those are audit reports, not sidecars)
    for f in files:
        if not f.name.startswith("bias_audit_report"):
            return f
    return None


def run_review(audit_path: Path):
    """Interactive ground truth review of an audit sidecar."""
    data = load_audit_sidecar(audit_path)
    if data is None:
        print(f"ERROR: Audit sidecar not found at {audit_path}")
        return

    decisions = data.get("decisions", [])
    unreviewed = [d for d in decisions if d.get("ground_truth") is None and d.get("matched")]
    if not unreviewed:
        print("All matched decisions already have ground truth verdicts.")
        return

    print(f"\nGround Truth Review -- {audit_path.name}")
    print(f"Scan run: {data.get('scan_run_id', 'unknown')}")
    print(f"Unreviewed matched decisions: {len(unreviewed)}")
    print("=" * 60)

    reviewed = 0
    true_pos = 0
    false_pos = 0

    for i, d in enumerate(unreviewed, 1):
        print(f"\n--- Decision {i} of {len(unreviewed)} ---")
        print(f"  Donor: {d['donor_name']}")
        print(f"  Employer: {d.get('donor_employer', '')}")
        print(f"  Agenda item: {d['agenda_item_number']}")
        print(f"  Text preview: {d.get('agenda_text_preview', '')[:200]}")
        print(f"  Match type: {d['match_type']}")
        print(f"  Confidence: {d['confidence']:.0%}")
        signals = d.get("bias_signals", {})
        if signals:
            print(f"  Bias signals: compound={signals.get('has_compound_surname')}, "
                  f"diacritics={signals.get('has_diacritics')}, "
                  f"tokens={signals.get('token_count')}, "
                  f"tier={signals.get('surname_frequency_tier')}")

        while True:
            choice = input("\n  [T]rue positive / [F]alse positive / [S]kip / [N]otes then verdict: ").strip().upper()
            if choice == "T":
                apply_verdict(d, "T", None)
                reviewed += 1
                true_pos += 1
                break
            elif choice == "F":
                apply_verdict(d, "F", None)
                reviewed += 1
                false_pos += 1
                break
            elif choice == "S":
                break
            elif choice == "N":
                notes = input("  Notes: ").strip()
                choice2 = input("  Now: [T]rue / [F]alse / [S]kip: ").strip().upper()
                if choice2 == "T":
                    apply_verdict(d, "T", notes)
                    reviewed += 1
                    true_pos += 1
                    break
                elif choice2 == "F":
                    apply_verdict(d, "F", notes)
                    reviewed += 1
                    false_pos += 1
                    break
                else:
                    break
            else:
                print("  Invalid choice. Use T, F, S, or N.")

    # Save updated sidecar
    with open(audit_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n{'=' * 60}")
    print(f"Review complete. Reviewed {reviewed} of {len(unreviewed)} decisions.")
    print(f"  True positives: {true_pos}")
    print(f"  False positives: {false_pos}")
    print(f"  Skipped: {len(unreviewed) - reviewed}")
    print(f"Updated sidecar saved to {audit_path}")


# ── v3 Signal Detector Re-exports (Phase 2.2) ────────────────
# Signal detectors live in scanner/signals/. Re-imported here so the public
# import surface of conflict_scanner is unchanged for existing callers.
from scanner.signals import (  # noqa: E402
    signal_campaign_contribution,
    signal_form700_property,
    signal_form700_income,
    signal_temporal_correlation,
    signal_donor_vendor_expenditure,
    signal_independent_expenditure,
    signal_permit_donor,
    signal_license_donor,
    signal_llc_ownership_chain,
    signal_behested_payment,
    signal_behested_payment_loop,
    signal_unregistered_lobbyist,
)


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Richmond Common — Conflict Scanner")
    parser.add_argument("meeting_json", nargs="?", help="Path to extracted meeting JSON file")
    parser.add_argument("--contributions", help="Path to contributions JSON file")
    parser.add_argument("--form700", help="Path to Form 700 interests JSON file")
    parser.add_argument("--output", help="Save report to file")

    # Temporal correlation
    parser.add_argument("--temporal-correlation", action="store_true",
                        help="Run temporal correlation analysis (detect post-vote donations)")

    # Review mode
    parser.add_argument("--review", action="store_true", help="Enter ground truth review mode")
    parser.add_argument("--scan-run", help="Review a specific scan run by UUID")
    parser.add_argument("--latest", action="store_true", help="Review the most recent scan run")

    args = parser.parse_args()

    audit_dir = Path(__file__).parent / "data" / "audit_runs"

    if args.review:
        if args.scan_run:
            audit_path = audit_dir / f"{args.scan_run}.json"
        elif args.latest:
            audit_path = find_latest_audit_sidecar(audit_dir)
            if audit_path is None:
                print("ERROR: No audit sidecars found in", audit_dir)
                return
        else:
            print("ERROR: --review requires --latest or --scan-run <uuid>")
            return
        run_review(audit_path)
        return

    # Normal scan mode
    if not args.meeting_json:
        parser.error("meeting_json is required for scan mode")

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
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"{result.scan_run_id}.json"
    result.audit_log.save(audit_path)
    print(f"Audit sidecar saved to {audit_path}")

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output}")
    else:
        print(report)

    if args.temporal_correlation:
        print("\n--- Post-Vote Donation Analysis ---")
        temporal_flags = scan_temporal_correlations(meeting_data, contributions)
        if temporal_flags:
            for flag in temporal_flags:
                print(f"\n[POST-VOTE] {flag.agenda_item_number}: {flag.council_member}")
                print(f"  {flag.description}")
                print(f"  Confidence: {flag.confidence:.0%} (Tier {flag.publication_tier})")
                if flag.evidence:
                    ev = flag.evidence[0] if isinstance(flag.evidence[0], dict) else {}
                    print(f"  Days after vote: {ev.get('days_after_vote', '?')}")
        else:
            print("  No post-vote donation patterns detected.")


if __name__ == "__main__":
    main()
