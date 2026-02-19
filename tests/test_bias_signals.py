"""Tests for bias audit instrumentation — structural risk signals."""
import pytest
from bias_signals import compute_bias_risk_signals, lookup_surname_frequency_tier


class TestComputeBiasRiskSignals:
    """compute_bias_risk_signals() returns structural string properties."""

    def test_simple_western_name(self):
        result = compute_bias_risk_signals("John Smith")
        assert result["has_compound_surname"] is False
        assert result["has_diacritics"] is False
        assert result["token_count"] == 2
        assert result["char_count"] == 10

    def test_hyphenated_surname(self):
        result = compute_bias_risk_signals("Maria Garcia-Lopez")
        assert result["has_compound_surname"] is True

    def test_long_compound_name(self):
        """More than 3 tokens counts as compound."""
        result = compute_bias_risk_signals("Maria de la Cruz")
        assert result["has_compound_surname"] is True
        assert result["token_count"] == 4

    def test_diacritics_detected(self):
        result = compute_bias_risk_signals("Nguyễn Văn")
        assert result["has_diacritics"] is True

    def test_no_diacritics_ascii_only(self):
        result = compute_bias_risk_signals("Nguyen Van")
        assert result["has_diacritics"] is False

    def test_short_name(self):
        result = compute_bias_risk_signals("Li Wu")
        assert result["char_count"] == 5
        assert result["token_count"] == 2

    def test_empty_name(self):
        result = compute_bias_risk_signals("")
        assert result["token_count"] == 0
        assert result["char_count"] == 0
        assert result["has_compound_surname"] is False

    def test_surname_frequency_tier_included(self):
        """Result includes a surname_frequency_tier key (may be None if no census data)."""
        result = compute_bias_risk_signals("John Smith")
        assert "surname_frequency_tier" in result
        # Value depends on whether census data is loaded
        assert result["surname_frequency_tier"] is None or isinstance(
            result["surname_frequency_tier"], int
        )


class TestLookupSurnameFrequencyTier:
    """Surname frequency lookup from Census 2010 data."""

    def test_returns_none_when_no_data(self):
        """When census data not loaded, returns None."""
        result = lookup_surname_frequency_tier("Smith")
        # Should not crash — returns None if data not available
        assert result is None or isinstance(result, int)

    def test_case_insensitive(self):
        """Lookup normalizes to lowercase."""
        r1 = lookup_surname_frequency_tier("SMITH")
        r2 = lookup_surname_frequency_tier("smith")
        assert r1 == r2

    def test_strips_whitespace(self):
        """Lookup strips whitespace."""
        r1 = lookup_surname_frequency_tier("Smith")
        r2 = lookup_surname_frequency_tier("  Smith  ")
        assert r1 == r2

    def test_empty_string_returns_none(self):
        assert lookup_surname_frequency_tier("") is None
