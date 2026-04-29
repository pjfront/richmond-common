"""Tests for merge_donor_employers.py — donor-employer merge rule logic.

Pure-logic tests on the rule engine. No DB. The merge rules are
intentionally conservative — same-name-different-employer can be two
genuinely different people sharing a name (the John Smith problem),
so the rules only fire when the employer relationship is unambiguous:

  Rule 1 (all-empty)   — every row's employer is in EMPTY_EQUIVALENTS
  Rule 2 (empty+spec)  — empties merge into specifics
  Rule 3 (substring)   — one normalized employer is a substring of
                         another (>= 4 chars), or word-subset

If these tests pass, the conservative-merge contract is preserved
across edits to the script.
"""
from __future__ import annotations

import pytest

from merge_donor_employers import (
    EMPTY_EQUIVALENTS,
    MIN_SUBSTRING_LEN,
    _is_empty_eq,
    _normalize_emp,
    _pick_canonical,
    _plan_cluster,
    _substring_match,
)


# ── Helpers for building cluster rows ────────────────────────────


def _row(id_, employer):
    """Build a minimal donor-cluster row dict."""
    return {"id": id_, "name": "Test Donor", "normalized_name": "test donor", "employer": employer}


# ── Empty-equivalent classification ──────────────────────────────


class TestIsEmptyEq:
    """The empty-equivalent set is the foundation for Rules 1 and 2."""

    @pytest.mark.parametrize("emp", [
        None, "", "  ", "n/a", "N/A", "NA", "None", "none", "NULL",
        "Not employed", "not employed", "Not Employed",
        "Not Empoloyed",  # OCR typo
        "unemployed", "no employer",
        "self", "Self", "self employed", "Self-Employed",
        "retired", "Retired",
    ])
    def test_known_empty_variants(self, emp):
        assert _is_empty_eq(emp), f"{emp!r} should be empty-equivalent"

    @pytest.mark.parametrize("emp", [
        "Chevron",
        "Mission National Bank",
        "California State Assembly",
        "Stanford Health",
        "ILWU",
        "T.R.F.",
        "Developer",
        "Government",
    ])
    def test_real_employers_not_empty(self, emp):
        assert not _is_empty_eq(emp)


class TestNormalizeEmp:
    """Normalization is what makes Rules 2 and 3 robust to formatting."""

    @pytest.mark.parametrize("input_,expected", [
        ("California", "california"),
        ("CALIFORNIA", "california"),
        (" California ", "california"),
        ("California, Inc.", "california inc"),
        ("California  State", "california state"),
        ("CalTrans", "caltrans"),
        ("Cal Trans", "cal trans"),  # Spaces preserved as word boundaries
        (None, ""),
        ("", ""),
    ])
    def test_basic_normalization(self, input_, expected):
        assert _normalize_emp(input_) == expected


# ── Substring matching ───────────────────────────────────────────


class TestSubstringMatch:
    """Rule 3's core predicate. Conservative on purpose — short
    tokens and unrelated words must NOT match."""

    @pytest.mark.parametrize("a,b", [
        # The I124-named substring case.
        ("California", "California State Assembly"),
        # Word-subset extension catches reordering.
        ("Stanford Health", "Stanford Health Care"),
        ("Stanford Health", "Stanford Health Center"),
        # Case + punctuation insensitivity (>= 4 chars).
        ("ilwu", "ILWU Local 10"),
        # Short PAC abbreviations like "CNA" intentionally do NOT match
        # by substring (below MIN_SUBSTRING_LEN). Handled instead via
        # canonical_donors.md aliases — see canonical_donors test file.
    ])
    def test_clear_substring_pairs(self, a, b):
        assert _substring_match(a, b)
        # Symmetry: the function should not depend on argument order.
        assert _substring_match(b, a)

    @pytest.mark.parametrize("a,b", [
        # Below the MIN_SUBSTRING_LEN threshold — short tokens are noisy.
        ("M", "Mike Johnson"),
        ("CA", "California"),
        ("Inc", "Mission Inc."),  # 3 chars
        # Genuinely distinct employers that happen to share short tokens.
        ("Stanford Health", "Stanford Hospital"),
        ("Children's Hospital", "Stanford Hospital"),
        ("Mission National Bank", "Mission Bay Realty"),  # share "mission"
        # Empty inputs — never match.
        ("", "Chevron"),
        ("Chevron", ""),
        (None, "Chevron"),
    ])
    def test_no_match(self, a, b):
        assert not _substring_match(a, b)
        if a is not None and b is not None:
            assert not _substring_match(b, a)

    @pytest.mark.parametrize("a,b", [
        # Case-only variations — same employer, different capitalization.
        ("Friends of the Earth", "Friends Of The Earth"),
        ("CHEVRON", "Chevron"),
        ("california state assembly", "CALIFORNIA STATE ASSEMBLY"),
        # Punctuation that the normalizer collapses to whitespace.
        ("Stanford Univ.", "Stanford Univ"),
        ("Acme, Inc.", "Acme Inc"),
    ])
    def test_case_equivalent_strings_match(self, a, b):
        """Case-only and punctuation-only differences MUST merge.
        Caught in production: Michelle Chan with Friends of the Earth
        vs Friends Of The Earth produced two donor rows and a $250
        within-filing duplicate that the old (na == nb returns False)
        rule excluded from merging.

        Note: hyphens are NOT collapsed by _normalize_emp, so 'Self-
        Employed' vs 'Self Employed' would NOT match here — but those
        cases are caught by Rule 1 (all-empty) since both are in the
        EMPTY_EQUIVALENTS set."""
        assert _substring_match(a, b)
        assert _substring_match(b, a)

    def test_min_substring_len_constant(self):
        """Locks the threshold so a future relaxation requires explicit
        intent + a test bump."""
        assert MIN_SUBSTRING_LEN == 4


# ── Cluster planning (Rules 1, 2, 3) ─────────────────────────────


class TestPlanClusterRule1:
    """Rule 1 — all-empty cluster collapses into one row."""

    def test_all_empty_two_rows(self):
        rows = [
            _row("a", "N/A"),
            _row("b", ""),
        ]
        plan = _plan_cluster(rows)
        assert len(plan) == 1
        drop_id, keep_id, reason = plan[0]
        assert reason == "all-empty"
        assert {drop_id, keep_id} == {"a", "b"}

    def test_all_empty_many_rows(self):
        """The Adolphus Beckles pattern — 4 empty-equivalent variants."""
        rows = [
            _row("a", "n/a"),
            _row("b", "None"),
            _row("c", "Not Employed"),
            _row("d", "Retired"),
        ]
        plan = _plan_cluster(rows)
        assert len(plan) == 3, "All-empty cluster of 4 should collapse to 1 keeper, 3 drops"
        keepers = {keep_id for _, keep_id, _ in plan}
        assert len(keepers) == 1, "All drops should re-point to the single keeper"

    def test_single_row_no_op(self):
        plan = _plan_cluster([_row("a", "")])
        assert plan == []


class TestPlanClusterRule2:
    """Rule 2 — empties merge INTO the specific employer row."""

    def test_one_empty_one_specific(self):
        """The Carl Adams case: 'Developer' + ''."""
        rows = [
            _row("a", "Developer"),
            _row("b", ""),
        ]
        plan = _plan_cluster(rows)
        assert len(plan) == 1
        drop_id, keep_id, reason = plan[0]
        assert reason == "empty→specific"
        assert keep_id == "a", "The specific-employer row keeps the contributions"
        assert drop_id == "b"

    def test_many_empties_one_specific(self):
        """Amy Worth: 'City of Orinda' + 'N/A' + 'self employed'."""
        rows = [
            _row("a", "City of Orinda"),
            _row("b", "N/A"),
            _row("c", "self employed"),
        ]
        plan = _plan_cluster(rows)
        assert len(plan) == 2
        for drop_id, keep_id, reason in plan:
            assert keep_id == "a"
            assert reason == "empty→specific"


class TestPlanClusterRule3:
    """Rule 3 — substring/word-subset employers collapse to the more-specific row."""

    def test_substring_pair(self):
        """The Buffy Wicks case: 'California' subset of 'California State Assembly'."""
        rows = [
            _row("a", "California State Assembly"),
            _row("b", "California"),
        ]
        plan = _plan_cluster(rows)
        assert len(plan) == 1
        drop_id, keep_id, reason = plan[0]
        assert reason == "substring-of"
        assert keep_id == "a", "More-specific employer wins"
        assert drop_id == "b"

    def test_substring_chain(self):
        """The Stanford Health Care chain — multiple substrings, transitive closure."""
        rows = [
            _row("a", "Stanford Health"),
            _row("b", "Stanford Health Care"),
            _row("c", "Stanford Health Center"),
        ]
        plan = _plan_cluster(rows)
        # All three should end up in the same group, with one keeper.
        assert len(plan) == 2
        keepers = {keep_id for _, keep_id, _ in plan}
        assert len(keepers) == 1

    def test_substring_does_not_pull_in_distinct_employer(self):
        """Stanford Health vs Stanford Hospital — different orgs, no collapse."""
        rows = [
            _row("a", "Stanford Health"),
            _row("b", "Stanford Health Care"),
            _row("c", "Stanford Hospital"),
        ]
        plan = _plan_cluster(rows)
        # Only a + b should merge; c stays separate.
        assert len(plan) == 1
        drop_id, _, reason = plan[0]
        assert reason == "substring-of"
        assert drop_id in {"a", "b"}, "Hospital should not be involved"


class TestPlanClusterMixed:
    """Combinations of rules. The keeper is always the most-specific row."""

    def test_empties_plus_substring_pair(self):
        """Buffy Wicks reality: California + California State Assembly + N/A."""
        rows = [
            _row("a", "California State Assembly"),
            _row("b", "California"),
            _row("c", "N/A"),
        ]
        plan = _plan_cluster(rows)
        # All three eventually collapse onto 'a'.
        assert len(plan) == 2
        keepers = {keep_id for _, keep_id, _ in plan}
        assert keepers == {"a"}
        reasons = {reason for _, _, reason in plan}
        assert "empty→specific" in reasons
        assert "substring-of" in reasons


class TestPlanClusterNoMerge:
    """The conservative cases — distinct employers stay separate."""

    def test_two_distinct_specific_employers_no_merge(self):
        """The John Smith case — same name, two genuinely different people.

        Conservative rules MUST leave this alone. B.46 entity resolution
        is the long-term home for cases like this.
        """
        rows = [
            _row("a", "Chevron"),
            _row("b", "SEIU Local 1021"),
        ]
        plan = _plan_cluster(rows)
        assert plan == [], "Distinct non-substring employers should not merge"

    def test_short_token_overlap_no_merge(self):
        """Mission National Bank vs Mission Bay Realty — share 'mission' but
        not enough to be the same employer."""
        rows = [
            _row("a", "Mission National Bank"),
            _row("b", "Mission Bay Realty"),
        ]
        plan = _plan_cluster(rows)
        assert plan == []


# ── Canonical-row picker ─────────────────────────────────────────


class TestPickCanonical:
    """The canonical-row picker decides which row keeps the contributions
    when a merge fires. The rule: prefer specific over empty, longer over
    shorter, lower id over higher id (deterministic on ties)."""

    def test_specific_beats_empty(self):
        rows = [
            _row("empty", "N/A"),
            _row("specific", "Chevron"),
        ]
        winner = _pick_canonical(rows)
        assert winner["id"] == "specific"

    def test_longer_specific_wins(self):
        rows = [
            _row("short", "California"),
            _row("long", "California State Assembly"),
        ]
        winner = _pick_canonical(rows)
        assert winner["id"] == "long"

    def test_all_empty_picks_one_deterministically(self):
        rows = [
            _row("a", "N/A"),
            _row("b", "None"),
        ]
        # The longest empty-eq string is "None" (4) vs "N/A" (3 normalized to "n/a").
        # Picker is allowed to use len of normalized; just verify it returns one
        # of the inputs deterministically (not None).
        winner = _pick_canonical(rows)
        assert winner is not None
        assert winner["id"] in {"a", "b"}
