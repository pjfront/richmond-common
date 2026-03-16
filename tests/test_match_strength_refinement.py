"""Tests for B.52 match strength refinement.

Covers: normalize_business_name, proportional specificity scoring,
confirmed match tier, and match_confidence tracking.
"""
from __future__ import annotations

import pytest
from conflict_scanner import (
    normalize_business_name,
    normalize_text,
    name_in_text,
    names_match,
    _match_type_to_strength,
    _GENERIC_BUSINESS_WORDS,
    RawSignal,
    compute_composite_confidence,
    scan_meeting_json,
)


# ── normalize_business_name ──────────────────────────────────

class TestNormalizeBusinessName:
    """B.52: Business suffix normalization before matching."""

    def test_strips_inc(self):
        assert normalize_business_name("ABC Construction Inc.") == "ABC Construction"

    def test_strips_inc_no_period(self):
        assert normalize_business_name("ABC Construction Inc") == "ABC Construction"

    def test_strips_llc(self):
        assert normalize_business_name("Pacific Services LLC") == "Pacific Services"

    def test_strips_corp(self):
        assert normalize_business_name("Maier Consulting Corp.") == "Maier Consulting"

    def test_strips_ltd(self):
        assert normalize_business_name("Richmond Holdings Ltd") == "Richmond Holdings"

    def test_strips_co(self):
        assert normalize_business_name("Golden State Co.") == "Golden State"

    def test_strips_lp(self):
        assert normalize_business_name("Bay Investment LP") == "Bay Investment"

    def test_strips_llp(self):
        assert normalize_business_name("Wilson & Associates LLP") == "Wilson & Associates"

    def test_strips_associates(self):
        assert normalize_business_name("Maier Associates") == "Maier"

    def test_strips_group(self):
        assert normalize_business_name("National Auto Fleet Group") == "National Auto Fleet"

    def test_strips_holdings(self):
        assert normalize_business_name("Chevron Holdings") == "Chevron"

    def test_strips_enterprises(self):
        assert normalize_business_name("Bay Area Enterprises") == "Bay Area"

    def test_strips_incorporated(self):
        assert normalize_business_name("Pacific Environmental Incorporated") == "Pacific Environmental"

    def test_strips_comma_before_suffix(self):
        assert normalize_business_name("ABC Construction, Inc.") == "ABC Construction"

    def test_strips_llc_dotted(self):
        assert normalize_business_name("Pacific Services L.L.C.") == "Pacific Services"

    def test_preserves_non_suffix_names(self):
        assert normalize_business_name("Chevron Richmond") == "Chevron Richmond"

    def test_preserves_person_names(self):
        assert normalize_business_name("Cheryl Maier") == "Cheryl Maier"

    def test_empty_string(self):
        assert normalize_business_name("") == ""

    def test_only_suffix_returns_original(self):
        assert normalize_business_name("Inc.") == "Inc."

    def test_case_insensitive(self):
        assert normalize_business_name("Pacific Services llc") == "Pacific Services"


# ── Business suffix matching integration ──────────────────────

class TestSuffixMatchingIntegration:
    """B.52: Inc/LLC/Corp variants should match each other."""

    def test_names_match_inc_vs_llc(self):
        """Same base name with different suffixes should match as exact."""
        result, match_type = names_match(
            "ABC Construction Inc.", "ABC Construction LLC"
        )
        assert result is True
        assert match_type == "exact"

    def test_names_match_corp_vs_ltd(self):
        result, match_type = names_match(
            "Pacific Environmental Corp.", "Pacific Environmental Ltd."
        )
        assert result is True
        assert match_type == "exact"

    def test_names_match_with_vs_without_suffix(self):
        result, match_type = names_match(
            "National Auto Fleet Group", "National Auto Fleet"
        )
        # Should match as contains (shorter is substring of longer)
        assert result is True

    def test_name_in_text_with_suffix_in_name(self):
        """Donor 'ABC Construction Inc.' should match text mentioning 'ABC Construction'."""
        result, match_type = name_in_text(
            "ABC Construction Inc.",
            "Approve contract with ABC Construction for road repairs",
        )
        assert result is True
        assert match_type == "phrase"

    def test_name_in_text_suffix_stripped_from_text(self):
        """Text with suffix should match donor without suffix."""
        result, match_type = name_in_text(
            "Pacific Environmental Services",
            "Contract awarded to Pacific Environmental Services LLC for cleanup",
        )
        assert result is True
        assert match_type == "phrase"


# ── Proportional specificity scoring ──────────────────────────

class TestProportionalSpecificity:
    """B.52: Proportional scoring replaces binary 0.7x threshold."""

    def test_all_distinctive_words_no_penalty(self):
        """Name with all distinctive words gets no penalty."""
        words = {"chevron", "texaco", "petroleum"}  # none in _GENERIC_BUSINESS_WORDS
        strength = _match_type_to_strength("phrase", words)
        # 0.85 * 1.0 = 0.85
        assert strength == pytest.approx(0.85, abs=0.01)

    def test_all_generic_words_max_penalty(self):
        """Name with all generic words gets 0.5x penalty."""
        words = {"pacific", "services", "group"}  # all in _GENERIC_BUSINESS_WORDS
        strength = _match_type_to_strength("phrase", words)
        # 0.85 * 0.5 = 0.425
        assert strength == pytest.approx(0.425, abs=0.01)

    def test_half_distinctive_moderate_penalty(self):
        """50% distinctive words gets 0.75x multiplier."""
        words = {"chevron", "services"}  # 1 of 2 distinctive
        strength = _match_type_to_strength("phrase", words)
        # 0.85 * (0.5 + 0.5 * 0.5) = 0.85 * 0.75 = 0.6375
        assert strength == pytest.approx(0.6375, abs=0.01)

    def test_no_words_no_penalty(self):
        """No donor_name_words means no specificity adjustment."""
        strength_none = _match_type_to_strength("phrase", None)
        strength_empty = _match_type_to_strength("phrase", set())
        assert strength_none == 0.85
        assert strength_empty == 0.85

    def test_proportional_vs_old_binary(self):
        """Verify improvement: old binary was harsh on borderline names."""
        # 2 of 3 words distinctive = 67% ratio
        # Old: < 50% threshold → no penalty → 0.85
        # New: 0.5 + 0.5 * 0.67 = 0.833 multiplier → 0.85 * 0.833 = 0.708
        words = {"chevron", "texaco", "services"}  # 2 of 3 distinctive
        strength = _match_type_to_strength("phrase", words)
        # 0.85 * (0.5 + 0.5 * 2/3) = 0.85 * 0.833 ≈ 0.708
        assert 0.70 < strength < 0.72

    def test_single_distinctive_word_in_mixed(self):
        """1 of 4 words distinctive = 25% ratio."""
        words = {"chevron", "pacific", "services", "group"}  # 1 of 4 distinctive
        strength = _match_type_to_strength("exact", words)
        # 1.0 * (0.5 + 0.5 * 0.25) = 1.0 * 0.625 = 0.625
        assert strength == pytest.approx(0.625, abs=0.01)


# ── Confirmed match tier ──────────────────────────────────────

class TestConfirmedMatchTier:
    """B.52: Multi-source confirmation sets match_strength to 1.0."""

    def _make_signal(self, signal_type, match_strength=0.7):
        return RawSignal(
            signal_type=signal_type,
            council_member="Sue Wilson (sitting council member)",
            agenda_item_number="V.6.a",
            match_strength=match_strength,
            temporal_factor=0.8,
            financial_factor=0.7,
            description="Test signal",
            evidence=["test"],
            legal_reference="Gov. Code SS 87100",
            match_details={"is_sitting": True},
        )

    def test_three_source_categories_confirmed(self):
        """Signals from contributions + expenditures + form700 = confirmed."""
        from conflict_scanner import _signals_to_flags

        signals = [
            self._make_signal("campaign_contribution", 0.7),
            self._make_signal("donor_vendor_expenditure", 0.6),
            self._make_signal("form700_income", 0.5),
        ]
        flags = _signals_to_flags(
            signals, "V.6.a", "Test Item", None,
            {"Sue Wilson"}, {},
        )
        # All flags should have match_strength boosted to 1.0 in factors
        for flag in flags:
            assert flag.confidence_factors["match_strength"] == 1.0

    def test_two_source_categories_not_confirmed(self):
        """Only 2 categories = not confirmed, original match_strength preserved."""
        from conflict_scanner import _signals_to_flags

        signals = [
            self._make_signal("campaign_contribution", 0.7),
            self._make_signal("donor_vendor_expenditure", 0.6),
        ]
        flags = _signals_to_flags(
            signals, "V.6.a", "Test Item", None,
            {"Sue Wilson"}, {},
        )
        # match_strength should be max of original values (0.7), not 1.0
        assert flags[0].confidence_factors["match_strength"] == 0.7

    def test_same_category_signals_not_confirmed(self):
        """Multiple signals from same category don't count as confirmed."""
        from conflict_scanner import _signals_to_flags

        signals = [
            self._make_signal("campaign_contribution", 0.7),
            self._make_signal("temporal_correlation", 0.6),
            # Both map to "contributions" category
        ]
        flags = _signals_to_flags(
            signals, "V.6.a", "Test Item", None,
            {"Sue Wilson"}, {},
        )
        # Not confirmed — only 1 distinct category
        assert flags[0].confidence_factors["match_strength"] == 0.7


# ── match_confidence tracking ─────────────────────────────────

class TestMatchConfidenceTracking:
    """B.52: match_confidence field in match_details for audit trail."""

    def test_match_confidence_present_in_flags(self):
        """After _signals_to_flags, each signal's match_details has match_confidence."""
        from conflict_scanner import _signals_to_flags

        signal = RawSignal(
            signal_type="campaign_contribution",
            council_member="Sue Wilson (sitting council member)",
            agenda_item_number="V.6.a",
            match_strength=0.85,
            temporal_factor=0.8,
            financial_factor=0.7,
            description="Test signal",
            evidence=["test"],
            legal_reference="Gov. Code SS 87100",
            match_details={"is_sitting": True, "donor_name": "Test Donor"},
        )
        _signals_to_flags(
            [signal], "V.6.a", "Test Item", None,
            {"Sue Wilson"}, {},
        )
        # After _signals_to_flags, the signal's match_details should have match_confidence
        mc = signal.match_details.get("match_confidence")
        assert mc is not None
        assert "match_strength" in mc
        assert "composite_confidence" in mc
        assert "publication_tier" in mc
        assert "tier_label" in mc
        assert "specificity_basis" in mc
        assert mc["specificity_basis"] == "text_match"

    def test_confirmed_match_confidence_basis(self):
        """Confirmed match has specificity_basis = 'confirmed_multi_source'."""
        from conflict_scanner import _signals_to_flags

        signals = [
            RawSignal(
                signal_type=st,
                council_member="Sue Wilson (sitting council member)",
                agenda_item_number="V.6.a",
                match_strength=0.7,
                temporal_factor=0.8,
                financial_factor=0.7,
                description="Test",
                evidence=["test"],
                legal_reference="Gov. Code SS 87100",
                match_details={"is_sitting": True},
            )
            for st in ("campaign_contribution", "donor_vendor_expenditure", "form700_income")
        ]
        _signals_to_flags(
            signals, "V.6.a", "Test Item", None,
            {"Sue Wilson"}, {},
        )
        for signal in signals:
            mc = signal.match_details["match_confidence"]
            assert mc["specificity_basis"] == "confirmed_multi_source"
            assert mc["match_strength"] == 1.0


# ── Integration: full scan with suffix normalization ──────────

class TestSuffixNormalizationInScan:
    """B.52: Full scan picks up matches that differ only in business suffix."""

    def test_scan_matches_inc_vs_no_suffix(self):
        """Donor 'Maier Consulting Inc.' matches item text 'Maier Consulting'."""
        meeting = {
            "meeting_date": "2026-03-04",
            "meeting_type": "regular",
            "members_present": [{"name": "Sue Wilson"}],
            "consent_calendar": {
                "items": [{
                    "item_number": "V.6.a",
                    "title": "Approve Contract with Maier Consulting",
                    "description": "Contract with Maier Consulting for environmental review.",
                    "financial_amount": "$50,000",
                }]
            },
            "action_items": [],
            "housing_authority_items": [],
        }
        contributions = [{
            "donor_name": "Maier Consulting Inc.",
            "donor_employer": "",
            "council_member": "",
            "committee_name": "Wilson for Richmond 2024",
            "amount": 1000,
            "date": "2025-06-01",
            "filing_id": "TEST-001",
            "source": "netfile",
        }]
        result = scan_meeting_json(meeting, contributions)
        # Should flag — suffix normalization makes "Maier Consulting Inc." match
        assert len(result.flags) > 0
        flag_donors = [
            f.description for f in result.flags
            if "Maier Consulting" in f.description
        ]
        assert len(flag_donors) > 0
