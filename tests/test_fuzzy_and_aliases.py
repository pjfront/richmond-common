"""Tests for fuzzy duplicate detection and alias wiring.

Covers:
- ensure_official() fuzzy matching (db.py)
- ensure_official() alias resolution (db.py)
- Conflict scanner alias expansion (conflict_scanner.py)
- is_sitting_council_member alias support
"""
from __future__ import annotations

import json
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from conflict_scanner import (
    is_sitting_council_member,
    normalize_text,
    scan_meeting_json,
)
from db import (
    FUZZY_MATCH_THRESHOLD,
    _fuzzy_find_official,
    _normalize_name,
    ensure_official,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_meeting(items, members_present=None):
    """Build minimal meeting JSON."""
    return {
        "meeting_date": "2026-03-04",
        "meeting_type": "regular",
        "city_fips": "0660620",
        "members_present": members_present or [],
        "consent_calendar": {"items": items},
        "action_items": [],
        "housing_authority_items": [],
    }


def _make_contribution(**kwargs):
    defaults = {
        "donor_name": "", "donor_employer": "", "council_member": "",
        "committee_name": "", "amount": 500, "date": "2024-01-01",
        "filing_id": "TEST-001", "source": "netfile",
    }
    defaults.update(kwargs)
    return defaults


OFFICIALS_WITH_ALIASES = {
    "city_fips": "0660620",
    "city_name": "Richmond, California",
    "current_council_members": [
        {"name": "Eduardo Martinez", "role": "Mayor"},
        {"name": "Jamelia Brown", "role": "Council Member", "district": 1},
    ],
    "former_council_members": [],
    "city_leadership": [
        {
            "name": "Shasa Curl",
            "title": "City Manager",
            "aliases": ["Kinshasa Curl"],
        },
        {
            "name": "Shannon Moore",
            "title": "City Attorney",
        },
    ],
}


def _load_aliases_from_data(data: dict, city_fips: str) -> dict:
    """Helper to test alias loading logic without file I/O.

    Mirrors db._load_alias_map's logic: normalized_alias -> canonical_name.
    """
    if data.get("city_fips") != city_fips:
        return {}
    alias_map = {}
    for section in ("current_council_members", "former_council_members", "city_leadership"):
        for official in data.get(section, []):
            canonical = official.get("name", "")
            for alias in official.get("aliases", []):
                alias_map[_normalize_name(alias)] = canonical
    return alias_map


def _build_alias_groups(data: dict, city_fips: str) -> dict[str, set[str]]:
    """Helper to test alias group building without file I/O.

    Mirrors conflict_scanner._load_alias_map's logic: name -> set of all variants.
    """
    if data.get("city_fips") != city_fips:
        return {}
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
            for name in group:
                name_groups[name] = group
    return name_groups


# ── db.py: alias map logic ──────────────────────────────────

class TestDbAliasMapLogic:
    def test_loads_aliases(self):
        alias_map = _load_aliases_from_data(OFFICIALS_WITH_ALIASES, "0660620")
        assert alias_map.get("kinshasa curl") == "Shasa Curl"

    def test_wrong_fips_returns_empty(self):
        alias_map = _load_aliases_from_data(OFFICIALS_WITH_ALIASES, "9999999")
        assert alias_map == {}

    def test_no_aliases_returns_empty(self):
        data = {
            "city_fips": "0660620",
            "current_council_members": [{"name": "Test Person"}],
            "former_council_members": [],
            "city_leadership": [],
        }
        alias_map = _load_aliases_from_data(data, "0660620")
        assert alias_map == {}

    def test_multiple_aliases(self):
        data = {
            "city_fips": "0660620",
            "current_council_members": [],
            "former_council_members": [],
            "city_leadership": [{
                "name": "Bob Smith",
                "aliases": ["Robert Smith", "Bobby Smith"],
            }],
        }
        alias_map = _load_aliases_from_data(data, "0660620")
        assert alias_map["robert smith"] == "Bob Smith"
        assert alias_map["bobby smith"] == "Bob Smith"


# ── db.py: _fuzzy_find_official ──────────────────────────────

class TestFuzzyFindOfficial:
    def test_catches_single_typo(self):
        """'Jamalia Brown' should fuzzy-match 'jamelia brown'."""
        cur = MagicMock()
        cur.fetchall.return_value = [
            (uuid.uuid4(), "jamelia brown"),
            (uuid.uuid4(), "eduardo martinez"),
        ]
        match_id, match_name, score = _fuzzy_find_official(
            cur, "0660620", "jamalia brown"
        )
        assert match_id is not None
        assert match_name == "jamelia brown"
        assert score >= FUZZY_MATCH_THRESHOLD

    def test_rejects_different_names(self):
        """'Sue Wilson' should NOT fuzzy-match 'Sue Walton'."""
        cur = MagicMock()
        cur.fetchall.return_value = [
            (uuid.uuid4(), "sue wilson"),
        ]
        match_id, match_name, score = _fuzzy_find_official(
            cur, "0660620", "sue walton"
        )
        assert match_id is None

    def test_picks_best_match(self):
        """When multiple candidates exceed threshold, pick the highest score."""
        id_martinez = uuid.uuid4()
        id_jimenez = uuid.uuid4()
        cur = MagicMock()
        cur.fetchall.return_value = [
            (id_martinez, "eduardo martinez"),
            (id_jimenez, "claudia jimenez"),
        ]
        # "eduardo martinex" is a single-char typo of "eduardo martinez"
        match_id, match_name, score = _fuzzy_find_official(
            cur, "0660620", "eduardo martinex"
        )
        assert match_id == id_martinez
        assert match_name == "eduardo martinez"

    def test_empty_db_returns_none(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        match_id, match_name, score = _fuzzy_find_official(
            cur, "0660620", "someone new"
        )
        assert match_id is None
        assert match_name is None
        assert score == 0.0

    def test_exact_match_exceeds_threshold(self):
        """Exact same name should score 1.0, well above threshold."""
        the_id = uuid.uuid4()
        cur = MagicMock()
        cur.fetchall.return_value = [(the_id, "doria robinson")]
        match_id, match_name, score = _fuzzy_find_official(
            cur, "0660620", "doria robinson"
        )
        assert match_id == the_id
        assert score == 1.0


# ── db.py: ensure_official integration ───────────────────────

class TestEnsureOfficialFuzzy:
    def _make_conn(self, existing_officials=None):
        """Build a mock connection that simulates the officials table."""
        existing = existing_officials or []
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        def execute_side_effect(query, params=None):
            if "SELECT id FROM officials" in query and "normalized_name = %s" in query:
                target_name = params[1] if params else None
                for off in existing:
                    if off["normalized_name"] == target_name:
                        cur.fetchone.return_value = (off["id"],)
                        return
                cur.fetchone.return_value = None
            elif "SELECT id, normalized_name FROM officials" in query:
                cur.fetchall.return_value = [
                    (off["id"], off["normalized_name"]) for off in existing
                ]
            elif "INSERT" in query:
                pass

        cur.execute.side_effect = execute_side_effect
        return conn, cur

    def test_exact_match_returns_existing(self):
        existing_id = uuid.uuid4()
        conn, _ = self._make_conn([
            {"id": existing_id, "normalized_name": "jamelia brown"},
        ])
        result = ensure_official(conn, "0660620", "Jamelia Brown", "Council Member")
        assert result == existing_id

    def test_fuzzy_match_returns_existing(self):
        existing_id = uuid.uuid4()
        conn, _ = self._make_conn([
            {"id": existing_id, "normalized_name": "jamelia brown"},
        ])
        with patch("db._load_alias_map", return_value={}):
            result = ensure_official(conn, "0660620", "Jamalia Brown", "Council Member")
        assert result == existing_id

    def test_alias_match_returns_existing(self):
        existing_id = uuid.uuid4()
        conn, _ = self._make_conn([
            {"id": existing_id, "normalized_name": "shasa curl"},
        ])
        alias_map = {"kinshasa curl": "Shasa Curl"}
        with patch("db._load_alias_map", return_value=alias_map):
            result = ensure_official(conn, "0660620", "Kinshasa Curl", "City Manager")
        assert result == existing_id

    def test_no_match_creates_new(self):
        conn, cur = self._make_conn([
            {"id": uuid.uuid4(), "normalized_name": "jamelia brown"},
        ])
        with patch("db._load_alias_map", return_value={}):
            result = ensure_official(conn, "0660620", "John Smith", "Guest")
        insert_calls = [
            c for c in cur.execute.call_args_list
            if c[0][0] and "INSERT" in c[0][0]
        ]
        assert len(insert_calls) == 1


# ── Fuzzy threshold validation ───────────────────────────────

class TestFuzzyThreshold:
    """Verify the threshold catches known typos and rejects false positives."""

    @pytest.mark.parametrize("name1,name2,should_match", [
        # Known bug: Jamelia Brown misspelling (single vowel swap)
        ("jamelia brown", "jamalia brown", True),
        # Common typo: doubled letter
        ("soheila bana", "soheilla bana", True),
        # Swapped vowel in last name
        ("cesar zepeda", "cesar zapeda", True),
        # Completely different names — should NOT match
        ("sue wilson", "sue walton", False),
        ("eduardo martinez", "edward martin", False),
        # Similar last names, different first names
        ("jamelia brown", "james brown", False),
        # Short names that are very different
        ("sue wilson", "tom butt", False),
    ])
    def test_threshold_cases(self, name1, name2, should_match):
        score = SequenceMatcher(None, name1, name2).ratio()
        matches = score >= FUZZY_MATCH_THRESHOLD
        assert matches == should_match, (
            f"'{name1}' vs '{name2}': score={score:.3f}, "
            f"threshold={FUZZY_MATCH_THRESHOLD}, expected match={should_match}"
        )


# ── conflict_scanner.py: alias group logic ───────────────────

class TestScannerAliasGroupLogic:
    def test_returns_bidirectional_groups(self):
        groups = _build_alias_groups(OFFICIALS_WITH_ALIASES, "0660620")
        assert "kinshasa curl" in groups.get("shasa curl", set())
        assert "shasa curl" in groups.get("kinshasa curl", set())

    def test_no_aliases_returns_empty(self):
        data = {
            "city_fips": "0660620",
            "current_council_members": [{"name": "Test Person"}],
            "former_council_members": [],
            "city_leadership": [],
        }
        groups = _build_alias_groups(data, "0660620")
        assert groups == {}

    def test_wrong_fips_returns_empty(self):
        groups = _build_alias_groups(OFFICIALS_WITH_ALIASES, "9999999")
        assert groups == {}


# ── conflict_scanner.py: is_sitting_council_member with aliases ──

class TestIsSittingWithAliases:
    def test_alias_matches_sitting_member(self):
        """Kinshasa Curl should match as sitting if Shasa Curl is current."""
        current = {"Shasa Curl"}
        alias_groups = {
            "kinshasa curl": {"shasa curl", "kinshasa curl"},
            "shasa curl": {"shasa curl", "kinshasa curl"},
        }
        assert is_sitting_council_member("Kinshasa Curl", current, alias_groups) is True

    def test_no_alias_still_works(self):
        current = {"Eduardo Martinez"}
        assert is_sitting_council_member("Eduardo Martinez", current, {}) is True

    def test_alias_groups_none_defaults_empty(self):
        current = {"Eduardo Martinez"}
        assert is_sitting_council_member("Eduardo Martinez", current) is True

    def test_unknown_alias_does_not_match(self):
        current = {"Eduardo Martinez"}
        alias_groups = {
            "kinshasa curl": {"shasa curl", "kinshasa curl"},
        }
        assert is_sitting_council_member("Kinshasa Curl", current, alias_groups) is False


# ── conflict_scanner.py: scan_meeting_json with aliases ──────

class TestScanWithAliases:
    def test_alias_donor_matches_agenda_item(self):
        """Donor 'Kinshasa Curl' should match agenda item mentioning 'Shasa Curl'."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "City Manager Shasa Curl report on infrastructure",
            "description": "Report by City Manager on ongoing projects",
        }])
        contributions = [_make_contribution(
            donor_name="Kinshasa Curl",
            committee_name="Some PAC for Good Government 2024",
            amount=5000,
        )]
        alias_groups = {
            "kinshasa curl": {"shasa curl", "kinshasa curl"},
            "shasa curl": {"shasa curl", "kinshasa curl"},
        }
        with patch("conflict_scanner._load_alias_map", return_value=alias_groups):
            result = scan_meeting_json(meeting, contributions)
        # Should find a match via alias — check vendor_matches
        assert len(result.vendor_matches) > 0
        vm = result.vendor_matches[0]
        assert "alias" in vm.match_type

    def test_council_member_alias_excluded(self):
        """Council member's alias in donors should be filtered out."""
        meeting = _make_meeting(
            [{
                "item_number": "V.1.a",
                "title": "Approve contract with ACME Corp for services",
                "description": "Standard maintenance contract",
            }],
            members_present=[{"name": "Shasa Curl", "role": "City Manager"}],
        )
        contributions = [_make_contribution(
            donor_name="Kinshasa Curl",
            committee_name="Shasa Curl for City Manager 2024",
            amount=5000,
        )]
        alias_groups = {
            "kinshasa curl": {"shasa curl", "kinshasa curl"},
            "shasa curl": {"shasa curl", "kinshasa curl"},
        }
        with patch("conflict_scanner._load_alias_map", return_value=alias_groups):
            result = scan_meeting_json(meeting, contributions)
        # Council member exclusion should have filtered "Kinshasa Curl"
        # since it's an alias of "Shasa Curl" who is in members_present.
        # Check via audit log summary.
        assert result.audit_log.summary.filtered_council_member > 0

    def test_scan_without_aliases_still_works(self):
        """Scanning should work fine when no aliases exist."""
        meeting = _make_meeting([{
            "item_number": "V.1.a",
            "title": "Approve contract with ACME Corp for services",
            "description": "Standard maintenance contract",
        }])
        contributions = [_make_contribution(
            donor_name="John Smith",
            committee_name="Friends of Test 2024",
            amount=500,
        )]
        with patch("conflict_scanner._load_alias_map", return_value={}):
            result = scan_meeting_json(meeting, contributions)
        assert result is not None
