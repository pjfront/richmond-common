"""Tests for the contributions content-hash gate.

Motivating bug (2026-05-13): netfile sync upserts ~24K contributions per
dispatch even when unchanged. The existing ON CONFLICT DO UPDATE WHERE
clause prevents redundant DATA changes, but Postgres still counts each
INSERT attempt as a write (lock, conflict check, WHERE evaluation),
which burns Supabase's monthly write quota.

The gate adds a pre-fetch + Python comparison BEFORE the INSERT. These
tests pin the decision logic so future edits can't accidentally let the
write amplification regress (which would silently cost real money).

These are pure-logic tests on _should_skip_contribution_insert. The full
SQL path is exercised by the live netfile sync after merge.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from db.contributions import _should_skip_contribution_insert


# Natural key shape: (norm_donor, norm_employer, amount, date, committee_name)
KEY = ("chevron usa inc", "chevron corporation", Decimal("5000.00"),
       date(2026, 3, 15), "RICHMOND PROGRESSIVE ALLIANCE")


class TestNewContribution:
    """Brand-new contribution (not in existing_contribs) must always insert."""

    def test_empty_existing_map(self):
        """First sync — nothing exists yet, every record is new."""
        assert _should_skip_contribution_insert(KEY, {}, "162345678") is False

    def test_different_key_in_existing(self):
        """The map has rows, but none matching this key."""
        existing = {("someone else", "", Decimal("100"), date(2026, 1, 1), "X"): ("162000000", "individual")}
        assert _should_skip_contribution_insert(KEY, existing, "162345678") is False


class TestUnchangedContribution:
    """Existing row with same filing_id and classified type — INSERT would be a no-op.

    These are the rows that were burning write quota.
    """

    def test_identical_filing_and_classified_type(self):
        """The pure unchanged case — same filing_id, type already set."""
        existing = {KEY: ("162345678", "corporate")}
        assert _should_skip_contribution_insert(KEY, existing, "162345678") is True

    def test_older_filing_with_classified_type(self):
        """Incoming filing_id is older than stored. WHERE clause inside the
        upsert would not fire — safe to skip."""
        existing = {KEY: ("162345999", "corporate")}
        assert _should_skip_contribution_insert(KEY, existing, "162345678") is True

    def test_no_filing_id_on_either_side(self):
        """Neither side has filing_id; type classified. Skip."""
        existing = {KEY: (None, "individual")}
        assert _should_skip_contribution_insert(KEY, existing, None) is True


class TestChangedContribution:
    """Existing row but something meaningful has changed — INSERT must run."""

    def test_newer_filing_id(self):
        """Incoming filing_id is lexicographically greater (newer)."""
        existing = {KEY: ("162345000", "corporate")}
        assert _should_skip_contribution_insert(KEY, existing, "162345678") is False

    def test_existing_has_no_filing_incoming_does(self):
        """Existing row has NULL filing_id, incoming provides one. Newer."""
        existing = {KEY: (None, "corporate")}
        assert _should_skip_contribution_insert(KEY, existing, "162345678") is False

    def test_needs_classification_backfill(self):
        """Type is NULL in existing row — incoming sync should classify."""
        existing = {KEY: ("162345678", None)}
        assert _should_skip_contribution_insert(KEY, existing, "162345678") is False

    def test_needs_classification_even_with_older_filing(self):
        """Older filing_id is fine, but null type must still trigger update."""
        existing = {KEY: ("162345999", None)}
        assert _should_skip_contribution_insert(KEY, existing, "162345678") is False


class TestEdgeCases:
    """Edges around filing_id comparison."""

    def test_empty_string_filing_id(self):
        """Empty-string filing_id treated as falsy. Should NOT count as newer."""
        existing = {KEY: ("162345678", "corporate")}
        assert _should_skip_contribution_insert(KEY, existing, "") is True

    def test_filing_id_lexicographic_comparison(self):
        """Filing IDs are compared as strings (matches the SQL semantics).

        "9" > "10" lexicographically — that's the existing behavior and we
        preserve it. In practice filing_ids are all the same length so it
        doesn't bite, but the test documents the contract."""
        existing = {KEY: ("10", "corporate")}
        # "9" > "10" lexicographically — would trigger update by string compare
        assert _should_skip_contribution_insert(KEY, existing, "9") is False
