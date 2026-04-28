"""Tests for dedup_contributions.py — cross-filing duplicate logic.

Pure-logic tests on the keeper-selection and pair-overlap helpers
extracted from find_cross_filing_duplicates. No DB.

The full SQL scan is integration-tested via the article-as-oracle
fixture (test_filing_period_briefing.py), which is the right place
for the join semantics. This file pins the in-memory rule logic so
tie-break behavior is locked across edits.
"""
from __future__ import annotations

from datetime import date

import pytest

from dedup_contributions import _choose_keeper, _deoverlap_pairs


# ── Keeper selection ─────────────────────────────────────────────


class TestChooseKeeperByFilingId:
    """Rule 1: prefer the higher filing_id (the canonical recipient view)."""

    def test_higher_filing_id_wins(self):
        """The Anderson RPOA case — Form 460 (216695016) beats 497 Part 1
        (216629636), because the higher filing_id is typically the
        recipient's later, more-canonical filing."""
        keep_id, drop_id, keep_d, drop_d, keep_f, drop_f = _choose_keeper(
            a_id="r1", a_date=date(2026, 4, 13), a_filing="216629636",
            b_id="r2", b_date=date(2026, 4, 13), b_filing="216695016",
        )
        assert keep_id == "r2"
        assert drop_id == "r1"
        assert keep_f == "216695016"

    def test_string_compare_is_correct_for_numeric_strings(self):
        """filing_id columns are TEXT in the DB but typically numeric.
        The string sort happens to give the right answer because all our
        FPPC IDs have the same digit count."""
        # 216618889 < 216629636 < 216695016 lexicographically AND numerically
        keep_id, *_ = _choose_keeper(
            "a", date(2026, 4, 10), "216618889",
            "b", date(2026, 4, 13), "216629636",
        )
        assert keep_id == "b"

    def test_a_higher_b_lower(self):
        """Asymmetry guard — argument order shouldn't matter for correctness."""
        keep_id, drop_id, *_ = _choose_keeper(
            "high", date(2026, 4, 10), "216695016",
            "low", date(2026, 4, 13), "216629636",
        )
        assert keep_id == "high"
        assert drop_id == "low"


class TestChooseKeeperByDate:
    """Rule 2: when filing_ids tie or are both NULL, prefer the later date."""

    def test_filing_id_tie_later_date_wins(self):
        keep_id, drop_id, keep_d, *_ = _choose_keeper(
            "early", date(2026, 4, 10), "216629636",
            "late",  date(2026, 4, 13), "216629636",
        )
        assert keep_id == "late"
        assert keep_d == date(2026, 4, 13)

    def test_both_filing_ids_null_date_wins(self):
        keep_id, *_ = _choose_keeper(
            "a", date(2026, 4, 10), None,
            "b", date(2026, 4, 13), None,
        )
        assert keep_id == "b"

    def test_one_filing_id_null_other_present(self):
        """NULL filing_id sorts as empty string (less than any present id)."""
        keep_id, drop_id, *_ = _choose_keeper(
            "null_filing", date(2026, 4, 13), None,
            "real_filing", date(2026, 4, 10), "216695016",
        )
        assert keep_id == "real_filing"
        assert drop_id == "null_filing"


class TestChooseKeeperEdgeCases:
    """Defensive shape — the function shouldn't crash on weird inputs."""

    def test_same_date_same_filing(self):
        """Same row twice — function should still return a deterministic answer.
        a_date >= b_date → keep a (the >= branch wins)."""
        keep_id, *_ = _choose_keeper(
            "a", date(2026, 4, 10), "216695016",
            "b", date(2026, 4, 10), "216695016",
        )
        assert keep_id == "a"


# ── Overlap suppression ──────────────────────────────────────────


def _pair(keep_id, drop_id, **kwargs):
    """Build a pair dict for testing."""
    return {
        "keep_id": keep_id,
        "drop_id": drop_id,
        "donor_name": kwargs.get("donor_name", "Donor"),
        "amount": kwargs.get("amount", 100.0),
        "keep_date": kwargs.get("keep_date", date(2026, 1, 1)),
        "drop_date": kwargs.get("drop_date", date(2026, 1, 1)),
        "keep_filing_id": kwargs.get("keep_filing_id", "1"),
        "drop_filing_id": kwargs.get("drop_filing_id", "2"),
        "day_gap": kwargs.get("day_gap", 0),
    }


class TestDeoverlapPairs:
    """The 3-way duplicate problem: A == B, B == C, A == C all show up
    as separate pairs in the SQL output. We need to keep one, drop two,
    NOT keep one and drop the same one in different pairs."""

    def test_no_overlap_passes_through(self):
        """Two unrelated pairs both stay."""
        pairs = [
            _pair("k1", "d1"),
            _pair("k2", "d2"),
        ]
        assert _deoverlap_pairs(pairs) == pairs

    def test_three_way_dup_collapses_to_two(self):
        """Three rows X, Y, Z all duplicates of each other:
            (X, Y): keep X, drop Y
            (Y, Z): keep Y, drop Z   ← should be skipped (Y already dropped)
            (X, Z): keep X, drop Z   ← should be kept

        Outcome: X is kept, Y and Z are both dropped — exactly one keeper
        for the cluster, no double-drop, no resurrection.
        """
        pairs = [
            _pair("X", "Y"),
            _pair("Y", "Z"),
            _pair("X", "Z"),
        ]
        result = _deoverlap_pairs(pairs)
        assert len(result) == 2
        keepers = {p["keep_id"] for p in result}
        drops = {p["drop_id"] for p in result}
        assert keepers == {"X"}
        assert drops == {"Y", "Z"}

    def test_dropped_row_cannot_become_keeper(self):
        """If a row was already dropped in an earlier pair, a later
        pair that wants to keep it must be skipped."""
        pairs = [
            _pair("a", "b"),  # b is dropped
            _pair("b", "c"),  # tries to keep b — must be skipped
        ]
        result = _deoverlap_pairs(pairs)
        assert len(result) == 1
        assert result[0]["keep_id"] == "a"

    def test_kept_row_cannot_become_dropped(self):
        """Inverse: if a row was already kept, a later pair that wants
        to drop it must be skipped."""
        pairs = [
            _pair("a", "b"),  # a is kept
            _pair("c", "a"),  # tries to drop a — must be skipped
        ]
        result = _deoverlap_pairs(pairs)
        assert len(result) == 1
        assert result[0]["keep_id"] == "a"

    def test_empty_input(self):
        assert _deoverlap_pairs([]) == []

    def test_preserves_order_of_surviving_pairs(self):
        """Greedy selection — earlier pairs win conflicts. Surviving
        pairs come out in input order so apply-pass output is stable."""
        pairs = [
            _pair("k1", "d1"),
            _pair("k2", "d2"),
            _pair("k3", "d3"),
        ]
        result = _deoverlap_pairs(pairs)
        assert [p["keep_id"] for p in result] == ["k1", "k2", "k3"]
