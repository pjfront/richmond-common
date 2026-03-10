"""Tests for v3 signal architecture: RawSignal, composite confidence, language framework.

S9.1 foundation -- no behavior change to the scanner yet. These test the
new dataclasses and scoring functions that S9.2 will wire in.
"""
import pytest
from conflict_scanner import (
    RawSignal,
    ConflictFlag,
    compute_composite_confidence,
    _confidence_to_tier,
    validate_language,
    apply_hedge_clause,
    CONFIDENCE_WEIGHTS,
    CORROBORATION_MULTIPLIERS,
    CORROBORATION_MULTIPLIER_3_PLUS,
    SITTING_MULTIPLIER,
    NON_SITTING_MULTIPLIER,
    DEFAULT_ANOMALY_FACTOR,
    V3_TIER_THRESHOLDS,
    LANGUAGE_BLOCKLIST,
    HEDGE_CLAUSE,
    LANGUAGE_TEMPLATE,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_signal(
    signal_type: str = "campaign_contribution",
    match_strength: float = 0.8,
    temporal_factor: float = 0.5,
    financial_factor: float = 0.5,
    description: str = "Test signal",
) -> RawSignal:
    """Create a RawSignal with sensible defaults for testing."""
    return RawSignal(
        signal_type=signal_type,
        match_strength=match_strength,
        temporal_factor=temporal_factor,
        financial_factor=financial_factor,
        description=description,
        evidence=["Test evidence"],
        legal_reference="Gov. Code SS 87100-87105",
    )


# ── RawSignal Dataclass ─────────────────────────────────────

class TestRawSignal:
    def test_basic_creation(self):
        sig = _make_signal()
        assert sig.signal_type == "campaign_contribution"
        assert sig.match_strength == 0.8
        assert sig.temporal_factor == 0.5
        assert sig.financial_factor == 0.5
        assert sig.match_details == {}

    def test_match_details_default_empty(self):
        sig = _make_signal()
        assert sig.match_details == {}

    def test_match_details_populated(self):
        sig = _make_signal()
        sig.match_details = {"donor_name": "Acme Corp", "match_type": "exact"}
        assert sig.match_details["donor_name"] == "Acme Corp"

    def test_all_signal_types(self):
        """All planned signal types can be created."""
        for stype in (
            "campaign_contribution",
            "form700_property",
            "form700_income",
            "donor_vendor_expenditure",
            "temporal_correlation",
        ):
            sig = _make_signal(signal_type=stype)
            assert sig.signal_type == stype

    def test_financial_amount_optional(self):
        sig = _make_signal()
        assert sig.financial_amount is None
        sig2 = RawSignal(
            signal_type="campaign_contribution",
            match_strength=0.8,
            temporal_factor=0.5,
            financial_factor=0.5,
            description="Test",
            evidence=[],
            legal_reference="test",
            financial_amount="$5,000",
        )
        assert sig2.financial_amount == "$5,000"


# ── ConflictFlag v3 Fields ───────────────────────────────────

class TestConflictFlagV3Fields:
    def test_default_scanner_version(self):
        flag = ConflictFlag(
            agenda_item_number="V.1",
            agenda_item_title="Test",
            council_member="Test Member",
            flag_type="campaign_contribution",
            description="Test",
            evidence=[],
            confidence=0.5,
            legal_reference="test",
        )
        assert flag.scanner_version == 2
        assert flag.confidence_factors is None

    def test_v3_fields_populated(self):
        factors = {
            "match_strength": 0.9,
            "temporal_factor": 0.7,
            "financial_factor": 0.6,
            "anomaly_factor": 0.5,
        }
        flag = ConflictFlag(
            agenda_item_number="V.1",
            agenda_item_title="Test",
            council_member="Test Member",
            flag_type="campaign_contribution",
            description="Test",
            evidence=[],
            confidence=0.75,
            legal_reference="test",
            confidence_factors=factors,
            scanner_version=3,
        )
        assert flag.scanner_version == 3
        assert flag.confidence_factors["match_strength"] == 0.9


# ── Composite Confidence ─────────────────────────────────────

class TestCompositeConfidence:
    def test_empty_signals(self):
        result = compute_composite_confidence([])
        assert result["confidence"] == 0.0
        assert result["signal_count"] == 0
        assert result["publication_tier"] == 4
        assert result["tier_label"] == "Internal"

    def test_single_signal_sitting(self):
        """Single signal, sitting member, default anomaly."""
        sig = _make_signal(match_strength=1.0, temporal_factor=1.0, financial_factor=1.0)
        result = compute_composite_confidence([sig], is_sitting=True)
        # weighted_avg = 1.0*0.35 + 1.0*0.25 + 1.0*0.20 + 0.5*0.20 = 0.90
        # * sitting(1.0) * corroboration(1.0) = 0.90
        assert result["confidence"] == 0.9
        assert result["signal_count"] == 1
        assert result["corroboration_boost"] == 1.0
        assert result["sitting_multiplier"] == 1.0

    def test_single_signal_non_sitting(self):
        """Non-sitting multiplier reduces confidence by 40%."""
        sig = _make_signal(match_strength=1.0, temporal_factor=1.0, financial_factor=1.0)
        result = compute_composite_confidence([sig], is_sitting=False)
        # weighted_avg = 0.90 * non_sitting(0.6) = 0.54
        assert result["confidence"] == 0.54
        assert result["sitting_multiplier"] == NON_SITTING_MULTIPLIER

    def test_weak_signal_low_confidence(self):
        """A weak match with no temporal or financial signal scores low."""
        sig = _make_signal(match_strength=0.3, temporal_factor=0.0, financial_factor=0.0)
        result = compute_composite_confidence([sig], is_sitting=True)
        # weighted_avg = 0.3*0.35 + 0.0*0.25 + 0.0*0.20 + 0.5*0.20 = 0.105 + 0.1 = 0.205
        assert result["confidence"] == 0.205
        assert result["publication_tier"] == 4  # below 0.50

    def test_two_signals_corroboration(self):
        """Two signals of different types get 1.15x corroboration boost."""
        sig1 = _make_signal(signal_type="campaign_contribution", match_strength=0.8, temporal_factor=0.6, financial_factor=0.5)
        sig2 = _make_signal(signal_type="form700_income", match_strength=0.7, temporal_factor=0.4, financial_factor=0.3)
        result = compute_composite_confidence([sig1, sig2], is_sitting=True)
        # max factors: match=0.8, temporal=0.6, financial=0.5
        # weighted_avg = 0.8*0.35 + 0.6*0.25 + 0.5*0.20 + 0.5*0.20 = 0.28+0.15+0.10+0.10 = 0.63
        # * corroboration(1.15) = 0.7245
        assert result["corroboration_boost"] == 1.15
        assert abs(result["confidence"] - 0.7245) < 0.001

    def test_three_signals_corroboration(self):
        """Three+ signals get 1.30x corroboration boost."""
        sig1 = _make_signal(signal_type="campaign_contribution", match_strength=0.9)
        sig2 = _make_signal(signal_type="form700_income", match_strength=0.7)
        sig3 = _make_signal(signal_type="donor_vendor_expenditure", match_strength=0.8)
        result = compute_composite_confidence([sig1, sig2, sig3], is_sitting=True)
        assert result["corroboration_boost"] == CORROBORATION_MULTIPLIER_3_PLUS

    def test_same_type_no_corroboration(self):
        """Multiple signals of the same type don't boost corroboration."""
        sig1 = _make_signal(signal_type="campaign_contribution", match_strength=0.9)
        sig2 = _make_signal(signal_type="campaign_contribution", match_strength=0.7)
        result = compute_composite_confidence([sig1, sig2], is_sitting=True)
        assert result["corroboration_boost"] == 1.0  # same type = 1 distinct
        assert result["signal_count"] == 2

    def test_max_factors_across_signals(self):
        """Composite uses the max of each factor across all signals."""
        sig1 = _make_signal(match_strength=0.3, temporal_factor=0.9, financial_factor=0.2)
        sig2 = _make_signal(match_strength=0.9, temporal_factor=0.1, financial_factor=0.8)
        result = compute_composite_confidence([sig1, sig2], is_sitting=True)
        assert result["factors"]["match_strength"] == 0.9
        assert result["factors"]["temporal_factor"] == 0.9
        assert result["factors"]["financial_factor"] == 0.8

    def test_confidence_capped_at_1(self):
        """Even with maximum everything + corroboration, confidence caps at 1.0."""
        signals = [
            _make_signal(signal_type="campaign_contribution", match_strength=1.0, temporal_factor=1.0, financial_factor=1.0),
            _make_signal(signal_type="form700_income", match_strength=1.0, temporal_factor=1.0, financial_factor=1.0),
            _make_signal(signal_type="donor_vendor_expenditure", match_strength=1.0, temporal_factor=1.0, financial_factor=1.0),
        ]
        result = compute_composite_confidence(signals, is_sitting=True, anomaly_factor=1.0)
        assert result["confidence"] == 1.0

    def test_custom_anomaly_factor(self):
        """Custom anomaly factor is used instead of default."""
        sig = _make_signal(match_strength=0.5, temporal_factor=0.5, financial_factor=0.5)
        result_low = compute_composite_confidence([sig], anomaly_factor=0.0)
        result_high = compute_composite_confidence([sig], anomaly_factor=1.0)
        assert result_high["confidence"] > result_low["confidence"]
        assert result_low["factors"]["anomaly_factor"] == 0.0
        assert result_high["factors"]["anomaly_factor"] == 1.0

    def test_return_structure(self):
        """Verify all expected keys are in the result."""
        sig = _make_signal()
        result = compute_composite_confidence([sig])
        expected_keys = {
            "confidence", "factors", "corroboration_boost",
            "sitting_multiplier", "signal_count",
            "publication_tier", "tier_label",
        }
        assert set(result.keys()) == expected_keys
        factor_keys = {"match_strength", "temporal_factor", "financial_factor", "anomaly_factor"}
        assert set(result["factors"].keys()) == factor_keys


# ── Confidence-to-Tier Mapping ───────────────────────────────

class TestConfidenceToTier:
    def test_high_confidence(self):
        tier, label = _confidence_to_tier(0.85)
        assert tier == 1
        assert label == "High-Confidence Pattern"

    def test_above_high_threshold(self):
        tier, label = _confidence_to_tier(0.95)
        assert tier == 1

    def test_medium_confidence(self):
        tier, label = _confidence_to_tier(0.70)
        assert tier == 2
        assert label == "Medium-Confidence Pattern"

    def test_medium_just_above(self):
        tier, label = _confidence_to_tier(0.84)
        assert tier == 2

    def test_low_confidence(self):
        tier, label = _confidence_to_tier(0.50)
        assert tier == 3
        assert label == "Low-Confidence Pattern"

    def test_low_just_above(self):
        tier, label = _confidence_to_tier(0.69)
        assert tier == 3

    def test_internal(self):
        tier, label = _confidence_to_tier(0.49)
        assert tier == 4
        assert label == "Internal"

    def test_zero(self):
        tier, label = _confidence_to_tier(0.0)
        assert tier == 4

    def test_one(self):
        tier, label = _confidence_to_tier(1.0)
        assert tier == 1


# ── Tier Threshold Scenarios ─────────────────────────────────

class TestTierThresholdScenarios:
    """Validate the plan's expected impact: v3 scoring separates signals."""

    def test_form700_only_scores_low(self):
        """Form 700 property flag with no temporal/financial signal stays low.
        Expected per plan: 0.3-0.5 range."""
        sig = _make_signal(
            signal_type="form700_property",
            match_strength=0.4,   # no entity match, just keyword proximity
            temporal_factor=0.0,  # no temporal correlation
            financial_factor=0.0, # no financial data
        )
        result = compute_composite_confidence([sig], is_sitting=True)
        # 0.4*0.35 + 0.0*0.25 + 0.0*0.20 + 0.5*0.20 = 0.14 + 0.10 = 0.24
        assert result["confidence"] < 0.50
        assert result["publication_tier"] == 4

    def test_contribution_plus_temporal_reaches_medium(self):
        """Exact name match + temporal proximity should reach medium tier.
        Expected per plan: 0.7-0.9 range."""
        sig1 = _make_signal(
            signal_type="campaign_contribution",
            match_strength=0.9,   # exact name match
            temporal_factor=0.8,  # within 6 months
            financial_factor=0.6, # $1000-5000
        )
        sig2 = _make_signal(
            signal_type="temporal_correlation",
            match_strength=0.9,
            temporal_factor=0.9,
            financial_factor=0.6,
        )
        result = compute_composite_confidence([sig1, sig2], is_sitting=True)
        assert result["confidence"] >= V3_TIER_THRESHOLDS["medium"]
        assert result["publication_tier"] in (1, 2)

    def test_cross_source_corroboration_reaches_high(self):
        """Donor + vendor + expenditure cross-reference should break 0.85.
        Expected per plan: breaks into Tier 1."""
        sig1 = _make_signal(
            signal_type="campaign_contribution",
            match_strength=1.0,
            temporal_factor=0.8,
            financial_factor=0.7,
        )
        sig2 = _make_signal(
            signal_type="donor_vendor_expenditure",
            match_strength=0.9,
            temporal_factor=0.7,
            financial_factor=0.8,
        )
        sig3 = _make_signal(
            signal_type="form700_income",
            match_strength=0.8,
            temporal_factor=0.5,
            financial_factor=0.6,
        )
        result = compute_composite_confidence([sig1, sig2, sig3], is_sitting=True)
        assert result["confidence"] >= V3_TIER_THRESHOLDS["high"]
        assert result["publication_tier"] == 1
        assert result["tier_label"] == "High-Confidence Pattern"


# ── Language Framework ───────────────────────────────────────

class TestLanguageFramework:
    def test_blocklist_words_detected(self):
        text = "This looks suspicious and may indicate corruption"
        violations = validate_language(text)
        assert "suspicious" in violations
        assert "corruption" in violations

    def test_clean_text_passes(self):
        text = "Public records show that Acme Corp contributed $5,000 to Wilson for Richmond 2024"
        violations = validate_language(text)
        assert violations == []

    def test_blocklist_case_insensitive(self):
        text = "CORRUPTION detected in SUSPICIOUS pattern"
        violations = validate_language(text)
        assert len(violations) >= 2

    def test_all_blocklist_words(self):
        """Every word in the blocklist is caught."""
        for word in LANGUAGE_BLOCKLIST:
            violations = validate_language(f"This is {word} behavior")
            assert word in violations, f"Blocklist word '{word}' not detected"

    def test_hedge_clause_below_085(self):
        desc = "Public records show a contribution"
        result = apply_hedge_clause(desc, 0.70)
        assert HEDGE_CLAUSE in result
        assert result.endswith(HEDGE_CLAUSE)

    def test_hedge_clause_at_085(self):
        desc = "Public records show a contribution"
        result = apply_hedge_clause(desc, 0.85)
        assert HEDGE_CLAUSE not in result
        assert result == desc

    def test_hedge_clause_above_085(self):
        desc = "Public records show a contribution"
        result = apply_hedge_clause(desc, 0.95)
        assert HEDGE_CLAUSE not in result

    def test_hedge_clause_not_duplicated(self):
        desc = f"Public records show a contribution\n{HEDGE_CLAUSE}"
        result = apply_hedge_clause(desc, 0.50)
        assert result.count(HEDGE_CLAUSE) == 1

    def test_language_template_exists(self):
        assert "{entity}" in LANGUAGE_TEMPLATE
        assert "{amount}" in LANGUAGE_TEMPLATE
        assert "{official}" in LANGUAGE_TEMPLATE
        assert "{committee}" in LANGUAGE_TEMPLATE
        assert "{item_number}" in LANGUAGE_TEMPLATE


# ── Weight Consistency ───────────────────────────────────────

class TestWeightConsistency:
    def test_weights_sum_to_one(self):
        total = sum(CONFIDENCE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.0001

    def test_all_four_factors(self):
        expected = {"match_strength", "temporal_factor", "financial_factor", "anomaly_factor"}
        assert set(CONFIDENCE_WEIGHTS.keys()) == expected

    def test_corroboration_multipliers_monotonic(self):
        """More signals = higher multiplier."""
        assert CORROBORATION_MULTIPLIERS[1] < CORROBORATION_MULTIPLIERS[2]
        assert CORROBORATION_MULTIPLIERS[2] < CORROBORATION_MULTIPLIER_3_PLUS

    def test_sitting_greater_than_non_sitting(self):
        assert SITTING_MULTIPLIER > NON_SITTING_MULTIPLIER

    def test_tier_thresholds_descending(self):
        assert V3_TIER_THRESHOLDS["high"] > V3_TIER_THRESHOLDS["medium"]
        assert V3_TIER_THRESHOLDS["medium"] > V3_TIER_THRESHOLDS["low"]
