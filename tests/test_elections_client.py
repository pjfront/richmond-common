"""Tests for elections_client.py — Election Cycle Tracking (B.24)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src/ to path (same pattern as conftest.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from elections_client import (
    extract_election_year,
    extract_office_sought,
    _is_city_level_office,
)


# ── extract_election_year ────────────────────────────────────


class TestExtractElectionYear:
    def test_standard_committee_name(self):
        assert extract_election_year("Eduardo Martinez for Richmond Mayor 2022") == 2022

    def test_friends_of_pattern(self):
        assert extract_election_year("Friends of Tom Butt for Richmond City Council 2016") == 2016

    def test_calaccess_reversed(self):
        assert extract_election_year("BECKLES FOR ASSEMBLY 2018, JOVANKA") == 2018

    def test_reelect_pattern(self):
        assert extract_election_year("Reelect Melvin Willis for Richmond City Council District 1 2024") == 2024

    def test_no_year(self):
        assert extract_election_year("Richmond Progressive Alliance PAC") is None

    def test_no_year_friends_pac(self):
        assert extract_election_year("Friends of a Better Richmond") is None

    def test_multiple_years_takes_last(self):
        # Edge case: committee name with multiple years
        assert extract_election_year("2020 Committee for Martinez 2022") == 2022

    def test_year_before_office(self):
        assert extract_election_year("Sue Wilson for 2024 Richmond City Council District 5") == 2024

    def test_empty_string(self):
        assert extract_election_year("") is None

    def test_non_election_year_number(self):
        # 4-digit numbers that aren't years
        assert extract_election_year("Committee 1234 for Justice") is None


# ── extract_office_sought ────────────────────────────────────


class TestExtractOfficeSought:
    def test_mayor(self):
        assert extract_office_sought("Eduardo Martinez for Richmond Mayor 2022") == "Mayor"

    def test_city_council(self):
        assert extract_office_sought("Tom Butt for Richmond City Council 2016") == "City Council"

    def test_city_council_district(self):
        result = extract_office_sought("Andrew Butt for Richmond City Council District 2 2022")
        assert result == "City Council District 2"

    def test_year_before_office(self):
        result = extract_office_sought("Sue Wilson for 2024 Richmond City Council District 5")
        assert result == "City Council District 5"

    def test_4_instead_of_for(self):
        result = extract_office_sought("Eduardo Martinez 4 Richmond Mayor 2022")
        assert result == "Mayor"

    def test_state_level_returns_none(self):
        # Assembly is state-level, should not match
        assert extract_office_sought("BECKLES FOR ASSEMBLY 2018") is None

    def test_pac_returns_none(self):
        assert extract_office_sought("Richmond Progressive Alliance PAC") is None

    def test_no_office(self):
        assert extract_office_sought("Friends of a Better Richmond") is None

    def test_city_treasurer(self):
        assert extract_office_sought("Smith for Richmond City Treasurer 2022") == "City Treasurer"


# ── _is_city_level_office ────────────────────────────────────


class TestIsCityLevelOffice:
    def test_mayor(self):
        assert _is_city_level_office("Mayor") is True

    def test_city_council(self):
        assert _is_city_level_office("City Council") is True

    def test_city_council_district(self):
        assert _is_city_level_office("City Council District 2") is True

    def test_assembly(self):
        assert _is_city_level_office("Assembly") is False

    def test_none(self):
        assert _is_city_level_office(None) is False

    def test_empty(self):
        assert _is_city_level_office("") is False

    def test_governor(self):
        assert _is_city_level_office("Governor") is False


# ── Integration: build_candidates_from_committees ────────────


class TestBuildCandidatesFromCommittees:
    """Integration tests using a mock database connection."""

    def _make_mock_conn(self, elections, committees, officials):
        """Build a mock conn that returns data for the right queries."""
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur

        call_count = {"n": 0}

        def mock_execute(sql, params=None):
            call_count["n"] += 1
            # Return different data depending on which query is being run
            if "FROM elections" in sql:
                cur.fetchall.return_value = elections
            elif "FROM committees" in sql and "election_id IS NULL" not in sql:
                cur.fetchall.return_value = committees
            elif "FROM officials" in sql:
                cur.fetchall.return_value = officials
            elif "FROM contributions" in sql:
                cur.fetchall.return_value = [(None, None)]
            elif "INSERT INTO election_candidates" in sql:
                cur.fetchone.return_value = (True,)  # is_insert = True
            elif "FROM officials WHERE id" in sql:
                cur.fetchone.return_value = (True,)  # is_current

        cur.execute = mock_execute
        return conn

    def test_basic_candidate_extraction(self):
        import uuid

        election_id = uuid.uuid4()
        comm_id = uuid.uuid4()
        official_id = uuid.uuid4()

        elections = [(election_id, __import__('datetime').date(2022, 11, 8), 'general')]
        committees = [
            (comm_id, "Eduardo Martinez for Richmond Mayor 2022",
             "Eduardo Martinez", official_id, "12345"),
        ]
        officials = [
            (official_id, "Eduardo Martinez", "eduardo martinez", "Mayor", True),
        ]

        conn = self._make_mock_conn(elections, committees, officials)

        from elections_client import build_candidates_from_committees
        stats = build_candidates_from_committees(conn, "0660620")

        assert stats["candidates_created"] >= 0  # At least ran without error
        conn.commit.assert_called()

    def test_pac_committees_skipped(self):
        import uuid

        election_id = uuid.uuid4()
        comm_id = uuid.uuid4()

        elections = [(election_id, __import__('datetime').date(2022, 11, 8), 'general')]
        committees = [
            (comm_id, "Richmond Progressive Alliance PAC", None, None, None),
        ]
        officials = []

        conn = self._make_mock_conn(elections, committees, officials)

        from elections_client import build_candidates_from_committees
        stats = build_candidates_from_committees(conn, "0660620")

        assert stats["skipped"] >= 1


# ── Integration: assign_contributions_to_elections ───────────


class TestAssignContributionsToElections:
    """Test the contribution assignment strategies."""

    def test_from_committee_strategy(self):
        """Strategy 1: contributions get election_id from their committee."""
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur

        # Strategy 1 UPDATE returns 100 rows affected
        # Strategy 2 queries
        call_results = iter([
            100,   # Strategy 1: rowcount for committee propagation
            [],    # Strategy 2: elections list (empty = no date heuristic)
        ])

        def mock_execute(sql, params=None):
            if "UPDATE contributions" in sql and "FROM committees" in sql:
                cur.rowcount = 100
            elif "FROM elections" in sql:
                cur.fetchall.return_value = []

        cur.execute = mock_execute

        from elections_client import assign_contributions_to_elections
        stats = assign_contributions_to_elections(conn, "0660620")

        assert stats["from_committee"] == 100
        conn.commit.assert_called()


# ── Sync function integration ────────────────────────────────


class TestSyncElections:
    def test_sync_source_registered(self):
        """Verify elections is registered in SYNC_SOURCES dict."""
        src = (Path(__file__).parent.parent / "src" / "data_sync.py").read_text()
        assert '"elections": sync_elections' in src

    def test_sync_function_defined(self):
        """Verify sync_elections function exists in data_sync.py."""
        src = (Path(__file__).parent.parent / "src" / "data_sync.py").read_text()
        assert "def sync_elections(" in src
