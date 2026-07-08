"""Tests for donor_classifier.py — entity type classification (S28.2)."""

from unittest.mock import MagicMock, patch

import pytest

from donor_classifier import (
    _CLASS_TO_ENTITY_TYPE,
    _resolve_slug,
    _slugify,
    sync_donor_classification,
)
from contributor_classifier import CORPORATE, UNION, INDIVIDUAL, PAC_IE, OTHER


# ── Slug generation ──────────────────────────────────────────────


class TestSlugify:
    def test_basic_name(self):
        assert _slugify("Chevron Corporation") == "chevron-corporation"

    def test_special_characters(self):
        assert _slugify("AT&T Inc.") == "at-t-inc"

    def test_multiple_spaces_and_hyphens(self):
        assert _slugify("  SEIU   Local  1021  ") == "seiu-local-1021"

    def test_all_special_chars(self):
        assert _slugify("!@#$%^&*()") == ""

    def test_long_name_truncation(self):
        long_name = "A" * 300
        slug = _slugify(long_name)
        assert len(slug) == 200

    def test_ampersand_and_punctuation(self):
        assert _slugify("Jones & Sons, LLC") == "jones-sons-llc"


# ── Entity type mapping ──────────────────────────────────────────


class TestEntityTypeMapping:
    def test_corporate_maps_to_corporation(self):
        assert _CLASS_TO_ENTITY_TYPE[CORPORATE] == "corporation"

    def test_union_maps_to_union(self):
        assert _CLASS_TO_ENTITY_TYPE[UNION] == "union"

    def test_individual_maps_to_person(self):
        assert _CLASS_TO_ENTITY_TYPE[INDIVIDUAL] == "person"

    def test_pac_ie_maps_to_committee(self):
        assert _CLASS_TO_ENTITY_TYPE[PAC_IE] == "committee"

    def test_other_maps_to_other_org(self):
        assert _CLASS_TO_ENTITY_TYPE[OTHER] == "other_org"

    def test_all_keys_mapped(self):
        """Every contributor_classifier type must map to an entity_type."""
        from contributor_classifier import VALID_TYPES
        for t in VALID_TYPES:
            assert t in _CLASS_TO_ENTITY_TYPE, f"{t} missing from entity_type map"


# ── Slug collision resolution ────────────────────────────────────


class TestResolveSlug:
    def test_no_collision_returns_original(self):
        cur = MagicMock()
        cur.fetchone.return_value = None  # No existing row
        result = _resolve_slug(cur, "chevron-corporation", "donor-1")
        assert result == "chevron-corporation"

    def test_collision_appends_counter(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("exists",),   # First call: slug taken
            ("exists",),   # Second call: slug-2 taken
            None,           # Third call: slug-3 free
        ]
        result = _resolve_slug(cur, "test-org", "donor-1")
        assert result == "test-org-3"

    def test_excludes_own_row(self):
        """A donor shouldn't collide with its own existing slug."""
        cur = MagicMock()
        cur.fetchone.return_value = None  # Own row excluded by id != donor_id
        result = _resolve_slug(cur, "my-slug", "donor-5")
        assert result == "my-slug"
        # Verify the WHERE clause excludes the donor's own id
        call_sql = cur.execute.call_args[0][0]
        assert "id != %s" in call_sql


# ── Full sync function ───────────────────────────────────────────


class TestSyncDonorClassification:
    """Tests for sync_donor_classification — the data_sync.py entry point."""

    def _make_conn(self, donor_rows):
        """Return (conn, cur) with cur.fetchall() returning donor_rows.

        donor_rows: list of (id, name, normalized_name) tuples.
        """
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = lambda self: cur
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = donor_rows
        cur.fetchone.return_value = None  # No slug collisions
        return conn, cur

    def test_empty_donors(self):
        """No unclassified donors = no-op, returns zero stats."""
        conn, cur = self._make_conn([])
        stats = sync_donor_classification(conn, "0660620")
        assert stats["records_fetched"] == 0
        assert stats["records_classified"] == 0
        assert stats["errors"] == 0

    def test_classifies_corporate_donor(self):
        """Corporate name pattern → entity_type = 'corporation'."""
        conn, cur = self._make_conn([
            ("d1", "Chevron U.S.A. Inc.", "chevron u s a inc"),
        ])
        stats = sync_donor_classification(conn, "0660620")
        assert stats["records_classified"] == 1
        assert stats["errors"] == 0
        # Verify UPDATE was called with correct entity_type
        # call_args_list order: [0]=SELECT for unclassified, [1]=slug SELECT,
        # [2]=UPDATE. Last call is the UPDATE.
        update_call = cur.execute.call_args_list[-1]
        args = update_call[0]
        assert args[1][0] == "corporation"  # entity_type

    def test_classifies_union_donor(self):
        """Union name pattern → entity_type = 'union'."""
        conn, cur = self._make_conn([
            ("d2", "SEIU Local 1021", "seiu local 1021"),
        ])
        stats = sync_donor_classification(conn, "0660620")
        assert stats["records_classified"] == 1

    def test_classifies_committee_donor(self):
        """PAC/committee name pattern → entity_type = 'committee'."""
        conn, cur = self._make_conn([
            ("d3", "Committee for Better Richmond", "committee for better richmond"),
        ])
        stats = sync_donor_classification(conn, "0660620")
        assert stats["records_classified"] == 1

    def test_classifies_individual_donor(self):
        """No org patterns → entity_type = 'person' (default)."""
        conn, cur = self._make_conn([
            ("d4", "Maria Garcia", "maria garcia"),
        ])
        stats = sync_donor_classification(conn, "0660620")
        assert stats["records_classified"] == 1
        update_call = cur.execute.call_args_list[-1]
        args = update_call[0]
        assert args[1][0] == "person"

    def test_sets_entity_slug(self):
        """entity_slug is populated from normalized_name."""
        conn, cur = self._make_conn([
            ("d5", "Chevron Corp.", "chevron corp"),
        ])
        sync_donor_classification(conn, "0660620")
        update_call = cur.execute.call_args_list[-1]
        args = update_call[0]
        assert args[1][1] == "chevron-corp"  # entity_slug

    def test_only_processes_null_entity_type(self):
        """The SELECT filter must be WHERE entity_type IS NULL."""
        conn, cur = self._make_conn([])
        sync_donor_classification(conn, "0660620")
        # Check the SELECT query
        select_call = cur.execute.call_args_list[0][0]
        assert "entity_type IS NULL" in select_call[0]

    def test_commits_after_classification(self):
        """conn.commit() must be called."""
        conn, cur = self._make_conn([
            ("d6", "Richmond POA", "richmond poa"),
        ])
        sync_donor_classification(conn, "0660620")
        conn.commit.assert_called_once()

    def test_error_handling_does_not_crash(self):
        """A single row error should increment errors but not stop processing."""
        conn, cur = self._make_conn([
            ("d7", "Good Donor Inc.", "good donor inc"),
            ("d8", None, None),  # This will cause an error in classify_contributor
        ])
        # classify_contributor handles empty name gracefully, so let's simulate
        # a real failure differently — patch classify_contributor to raise on d8
        with patch("donor_classifier.classify_contributor") as mock_classify:
            mock_classify.side_effect = [
                ("corporate", "inferred"),
                Exception("Boom"),
            ]
            stats = sync_donor_classification(conn, "0660620")
            assert stats["records_fetched"] == 2
            assert stats["records_classified"] == 1
            assert stats["errors"] == 1

    def test_idempotent_on_rerun(self):
        """When entity_type IS NULL returns 0 rows, no updates happen."""
        conn, cur = self._make_conn([])
        stats = sync_donor_classification(conn, "0660620")
        assert stats["records_fetched"] == 0
        assert stats["records_classified"] == 0


# ── ponytail: self-check ─────────────────────────────────────────


def test_self_check():
    """Assert the module's basic assumptions hold."""
    # Every mapping key should be from contributor_classifier constants
    assert _CLASS_TO_ENTITY_TYPE[CORPORATE] == "corporation"
    assert _CLASS_TO_ENTITY_TYPE[UNION] == "union"
    assert _CLASS_TO_ENTITY_TYPE[INDIVIDUAL] == "person"
    assert _CLASS_TO_ENTITY_TYPE[PAC_IE] == "committee"

    # slugify basic sanity
    assert _slugify("Test Name, LLC.") == "test-name-llc"
    assert _slugify("") == ""
