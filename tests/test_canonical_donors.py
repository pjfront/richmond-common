"""Tests for canonical_donors.py — donor-name alias resolution.

Pure-logic tests against the alias map parsed from
``src/prompts/canonical_donors.md``. No DB, no Anthropic API.

The point of this module is to collapse OCR/alias drift on Vision-
extracted paper-filing donor names. Without these tests, a future
edit to the markdown file or the parser could silently regress —
e.g. a missing pipe in an alias list breaks one entity's lookup
without breaking any others, so end-to-end tests wouldn't catch it.
"""
from __future__ import annotations

import pytest

from canonical_donors import (
    _normalize_for_lookup,
    canonicalize_donor_name,
    reload_alias_map,
)


@pytest.fixture(autouse=True)
def _fresh_map():
    """Each test gets a freshly-parsed alias map.

    The map is process-cached via ``lru_cache`` for production speed,
    but tests need to be order-independent in case future tests modify
    the markdown for fixtures.
    """
    reload_alias_map()
    yield
    reload_alias_map()


# ── Normalization helper ─────────────────────────────────────────


class TestNormalizeForLookup:
    """The lookup key normalizer collapses OCR-noise punctuation."""

    @pytest.mark.parametrize("input_name,expected", [
        ("SEIU Local 1021", "seiu local 1021"),
        ("S.E.I.U. Local 1021", "seiu local 1021"),
        ("SEIU  Local  1021", "seiu local 1021"),  # Doubled whitespace
        ("RPOA*", "rpoa"),
        ("Chevron, Inc.", "chevron inc"),
        ("(California) State Assembly", "california state assembly"),
        ("Chevron's", "chevrons"),
        ('"Chevron"', "chevron"),
    ])
    def test_punctuation_and_case_collapsed(self, input_name, expected):
        assert _normalize_for_lookup(input_name) == expected

    def test_internal_spaces_preserved_as_word_boundaries(self):
        """Whitespace is authoritative — only punctuation is collapsed.

        "S. E. I. U." (with spaces between letters) becomes "s e i u",
        not "seiu", because the spaces are real word boundaries. This
        is fine in practice — Vision OCR returns "S.E.I.U." without
        internal spaces, which collapses correctly.
        """
        assert _normalize_for_lookup("S. E. I. U.") == "s e i u"

    def test_empty_input(self):
        assert _normalize_for_lookup("") == ""

    def test_none_safe(self):
        # Defensive: callers may hand us None for unset employer fields.
        assert _normalize_for_lookup(None) == ""  # type: ignore[arg-type]


# ── Canonical lookup ─────────────────────────────────────────────


class TestRPOAAliases:
    """Richmond Police Officers Association — the I124 motivating case."""

    CANONICAL = "Richmond Police Officers Association PAC"

    @pytest.mark.parametrize("alias", [
        "Richmond Police Officers Association",
        "Richmond Police Officers Association PAC",  # canonical itself
        "Richmond P.O.A.",
        "Richmond POA",
        "RPOA",
        "RPOA PAC",
        "Richmond City Police",  # Vision OCR drift
        "Richmond Police Officers Assoc",
        "richmond police officers association",  # lowercase
        "RICHMOND POLICE OFFICERS ASSOCIATION",  # uppercase
    ])
    def test_alias_resolves_to_canonical(self, alias):
        assert canonicalize_donor_name(alias) == self.CANONICAL


class TestIAFFAliases:
    """International Association of Firefighters Local 188 — multi-word PAC."""

    CANONICAL = "International Association of Firefighters Local 188"

    @pytest.mark.parametrize("alias", [
        "IAFF Local 188",
        "Firefighters Local 188",
        "Independent PAC Local 188 International Association of Firefighters",
        "Independent PAC Local 188 IAFF",
    ])
    def test_alias_resolves_to_canonical(self, alias):
        assert canonicalize_donor_name(alias) == self.CANONICAL


class TestSEIUAliases:
    """SEIU 1021 — case for periods, abbreviations, and full-name variants."""

    CANONICAL = "SEIU Local 1021 Candidate PAC"

    @pytest.mark.parametrize("alias", [
        "SEIU 1021",
        "SEIU Local 1021",
        "S.E.I.U. Local 1021",
        "Service Employees International Union Local 1021",
    ])
    def test_alias_resolves_to_canonical(self, alias):
        assert canonicalize_donor_name(alias) == self.CANONICAL


class TestChevronAliases:
    """Chevron — the largest political spender in Richmond."""

    CANONICAL = "Chevron Richmond"

    @pytest.mark.parametrize("alias", [
        "Chevron",
        "Chevron Corporation",
        "Chevron USA",
        "Chevron U.S.A. Inc.",
        "ChevronTexaco",  # 2001-2005 corporate name; donations under that label exist
        "CHEVRON",
    ])
    def test_alias_resolves_to_canonical(self, alias):
        assert canonicalize_donor_name(alias) == self.CANONICAL


# ── Non-matching paths ───────────────────────────────────────────


class TestNonAliases:
    """Names that should pass through unchanged."""

    @pytest.mark.parametrize("name", [
        "John Smith",
        "M. Quinn Delaney",
        "Buffy Wicks",       # individual donor — handled by employer-merge, not canonical
        "Tom Butt",
        "Some Random LLC",
        "Andrew Butt",
        "Emp. Consulting",
        "Stanford Health",
    ])
    def test_unknown_name_unchanged(self, name):
        assert canonicalize_donor_name(name) == name


class TestEdgeCases:
    """Defensive behavior on weird inputs."""

    def test_empty_string_returns_empty(self):
        assert canonicalize_donor_name("") == ""

    def test_none_returns_none(self):
        # The loader pipeline can hand us None for missing contributor_name.
        # The function should not crash.
        assert canonicalize_donor_name(None) is None  # type: ignore[arg-type]

    def test_whitespace_only(self):
        # Pure whitespace doesn't match any alias — preserved unchanged so
        # the caller's existing strip()/skip-empty logic still runs.
        assert canonicalize_donor_name("   ") == "   "

    def test_canonical_round_trip(self):
        """The canonical surface form maps to itself.

        This is the contract that lets the load path apply
        canonicalize_donor_name() unconditionally — already-canonical
        rows don't get rewritten.
        """
        assert canonicalize_donor_name("Chevron Richmond") == "Chevron Richmond"
        assert canonicalize_donor_name("SEIU Local 1021 Candidate PAC") == "SEIU Local 1021 Candidate PAC"


class TestReloadAliasMap:
    """The cache-clearing escape hatch for tests and prompt edits."""

    def test_reload_does_not_break_subsequent_lookup(self):
        before = canonicalize_donor_name("RPOA")
        reload_alias_map()
        after = canonicalize_donor_name("RPOA")
        assert before == after == "Richmond Police Officers Association PAC"
