"""Tests for S8.5: Meeting body type context in pipeline.

Covers:
- _default_role_for_body_type() mapping
- _resolve_body_type() DB lookup
- resolve_body_id() DB lookup
- load_meeting_to_db() uses correct default role based on body_type
- body_id flows through to meetings and meeting_attendance INSERTs
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from db import (
    _default_role_for_body_type,
    _resolve_body_type,
    resolve_body_id,
)


# ── _default_role_for_body_type ──────────────────────────────


class TestDefaultRoleForBodyType:
    """Verify body_type → role mapping covers all body types."""

    def test_city_council_maps_to_councilmember(self):
        assert _default_role_for_body_type("city_council") == "councilmember"

    def test_commission_maps_to_commissioner(self):
        assert _default_role_for_body_type("commission") == "commissioner"

    def test_board_maps_to_board_member(self):
        assert _default_role_for_body_type("board") == "board_member"

    def test_authority_maps_to_board_member(self):
        assert _default_role_for_body_type("authority") == "board_member"

    def test_committee_maps_to_committee_member(self):
        assert _default_role_for_body_type("committee") == "committee_member"

    def test_joint_maps_to_member(self):
        assert _default_role_for_body_type("joint") == "member"

    def test_none_defaults_to_councilmember(self):
        """When no body_type is known, default to councilmember (backward compat)."""
        assert _default_role_for_body_type(None) == "councilmember"

    def test_empty_string_defaults_to_councilmember(self):
        assert _default_role_for_body_type("") == "councilmember"

    def test_unknown_type_defaults_to_councilmember(self):
        assert _default_role_for_body_type("task_force") == "councilmember"


# ── _resolve_body_type ───────────────────────────────────────


class TestResolveBodyType:
    """Verify body_type lookup from body_id."""

    def test_returns_body_type_when_found(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = ("commission",)
        body_id = uuid.uuid4()

        result = _resolve_body_type(conn, body_id)
        assert result == "commission"
        cur.execute.assert_called_once()

    def test_returns_none_when_not_found(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None
        body_id = uuid.uuid4()

        result = _resolve_body_type(conn, body_id)
        assert result is None

    def test_returns_none_when_body_id_is_none(self):
        conn = MagicMock()
        result = _resolve_body_type(conn, None)
        assert result is None
        # Should not query DB at all
        conn.cursor.assert_not_called()


# ── resolve_body_id ──────────────────────────────────────────


class TestResolveBodyId:
    """Verify body_id lookup from city_fips + body name."""

    def test_returns_body_id_when_found(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        expected_id = uuid.uuid4()
        cur.fetchone.return_value = (expected_id,)

        result = resolve_body_id(conn, "0660620", "Planning Commission")
        assert result == expected_id

    def test_returns_none_when_not_found(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None

        result = resolve_body_id(conn, "0660620", "Nonexistent Board")
        assert result is None


# ── load_meeting_to_db body_id integration ───────────────────


class TestLoadMeetingBodyIdIntegration:
    """Verify that load_meeting_to_db uses body_id to derive roles."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection with cursor context manager."""
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        # The meeting INSERT returns a meeting_id
        meeting_id = uuid.uuid4()
        cur.fetchone.return_value = (meeting_id,)
        return conn, cur

    @pytest.fixture
    def minimal_meeting_data(self):
        return {
            "meeting_date": "2026-03-15",
            "meeting_type": "regular",
            "members_present": [
                {"name": "Alice Smith"},
                {"name": "Bob Jones"},
            ],
            "members_absent": [],
            "action_items": [],
        }

    def test_no_body_id_defaults_to_councilmember(self, mock_conn, minimal_meeting_data):
        """Without body_id, role should default to 'councilmember'."""
        conn, cur = mock_conn
        from db import load_meeting_to_db

        # Patch ensure_official to capture what role is passed
        with patch("db.ensure_official") as mock_ensure:
            mock_ensure.return_value = uuid.uuid4()
            load_meeting_to_db(conn, minimal_meeting_data, city_fips="0660620")

        # Check that ensure_official was called with "councilmember" default
        for c in mock_ensure.call_args_list:
            assert c[0][3] == "councilmember", (
                f"Expected role 'councilmember', got '{c[0][3]}'"
            )

    def test_commission_body_id_uses_commissioner_role(self, mock_conn, minimal_meeting_data):
        """With a commission body_id, role should default to 'commissioner'."""
        conn, cur = mock_conn
        body_id = uuid.uuid4()

        from db import load_meeting_to_db

        # _resolve_body_type needs to return "commission"
        with patch("db._resolve_body_type", return_value="commission"), \
             patch("db.ensure_official") as mock_ensure:
            mock_ensure.return_value = uuid.uuid4()
            load_meeting_to_db(
                conn, minimal_meeting_data,
                city_fips="0660620", body_id=body_id,
            )

        for c in mock_ensure.call_args_list:
            assert c[0][3] == "commissioner", (
                f"Expected role 'commissioner', got '{c[0][3]}'"
            )

    def test_board_body_id_uses_board_member_role(self, mock_conn, minimal_meeting_data):
        """With a board body_id, role should default to 'board_member'."""
        conn, cur = mock_conn
        body_id = uuid.uuid4()

        from db import load_meeting_to_db

        with patch("db._resolve_body_type", return_value="board"), \
             patch("db.ensure_official") as mock_ensure:
            mock_ensure.return_value = uuid.uuid4()
            load_meeting_to_db(
                conn, minimal_meeting_data,
                city_fips="0660620", body_id=body_id,
            )

        for c in mock_ensure.call_args_list:
            assert c[0][3] == "board_member"

    def test_explicit_role_overrides_body_default(self, mock_conn):
        """When extraction data includes explicit role, it takes precedence."""
        conn, cur = mock_conn
        body_id = uuid.uuid4()
        data = {
            "meeting_date": "2026-03-15",
            "meeting_type": "regular",
            "members_present": [
                {"name": "Chair Person", "role": "chair"},
            ],
            "members_absent": [],
            "action_items": [],
        }

        from db import load_meeting_to_db

        with patch("db._resolve_body_type", return_value="commission"), \
             patch("db.ensure_official") as mock_ensure:
            mock_ensure.return_value = uuid.uuid4()
            load_meeting_to_db(
                conn, data,
                city_fips="0660620", body_id=body_id,
            )

        # "chair" from the data should win over "commissioner" default
        mock_ensure.assert_called_once()
        assert mock_ensure.call_args[0][3] == "chair"

    def test_body_id_included_in_meeting_insert(self, mock_conn, minimal_meeting_data):
        """body_id should appear in the meetings INSERT when provided."""
        conn, cur = mock_conn
        body_id = uuid.uuid4()

        from db import load_meeting_to_db

        with patch("db._resolve_body_type", return_value="commission"), \
             patch("db.ensure_official", return_value=uuid.uuid4()):
            load_meeting_to_db(
                conn, minimal_meeting_data,
                city_fips="0660620", body_id=body_id,
            )

        # Find the meeting INSERT call (first execute call)
        first_call = cur.execute.call_args_list[0]
        sql = first_call[0][0]
        params = first_call[0][1]

        assert "body_id" in sql, "body_id column should appear in INSERT SQL"
        assert str(body_id) in params, "body_id value should appear in params"

    def test_body_id_included_in_attendance_insert(self, mock_conn, minimal_meeting_data):
        """body_id should appear in meeting_attendance INSERTs when provided."""
        conn, cur = mock_conn
        body_id = uuid.uuid4()

        from db import load_meeting_to_db

        with patch("db._resolve_body_type", return_value="commission"), \
             patch("db.ensure_official", return_value=uuid.uuid4()):
            load_meeting_to_db(
                conn, minimal_meeting_data,
                city_fips="0660620", body_id=body_id,
            )

        # Find attendance INSERT calls (contain "meeting_attendance")
        attendance_calls = [
            c for c in cur.execute.call_args_list
            if "meeting_attendance" in str(c[0][0])
        ]
        assert len(attendance_calls) == 2, "Should have 2 attendance inserts"

        for ac in attendance_calls:
            sql = ac[0][0]
            params = ac[0][1]
            assert "body_id" in sql
            assert str(body_id) in params

    def test_no_body_id_auto_resolves_city_council(self, mock_conn, minimal_meeting_data):
        """Without body_id, should auto-resolve to City Council body."""
        conn, cur = mock_conn
        cc_body_id = uuid.uuid4()

        from db import load_meeting_to_db

        with patch("db.resolve_body_id", return_value=cc_body_id), \
             patch("db.ensure_official", return_value=uuid.uuid4()):
            load_meeting_to_db(
                conn, minimal_meeting_data,
                city_fips="0660620",
            )

        attendance_calls = [
            c for c in cur.execute.call_args_list
            if "meeting_attendance" in str(c[0][0])
        ]

        for ac in attendance_calls:
            params = ac[0][1]
            # Last param should be the auto-resolved City Council body_id
            assert str(cc_body_id) in str(params[-1])

    def test_vote_role_uses_body_default(self, mock_conn):
        """Votes in action items should also use body-derived role."""
        conn, cur = mock_conn
        body_id = uuid.uuid4()
        data = {
            "meeting_date": "2026-03-15",
            "meeting_type": "regular",
            "members_present": [],
            "members_absent": [],
            "action_items": [
                {
                    "item_number": "A-1",
                    "title": "Test item",
                    "motions": [
                        {
                            "motion_type": "original",
                            "motion_text": "Approve",
                            "result": "passed",
                            "votes": [
                                {"council_member": "Alice Smith", "vote": "aye"},
                            ],
                        },
                    ],
                },
            ],
        }

        from db import load_meeting_to_db

        with patch("db._resolve_body_type", return_value="board"), \
             patch("db.ensure_official") as mock_ensure:
            mock_ensure.return_value = uuid.uuid4()
            load_meeting_to_db(
                conn, data,
                city_fips="0660620", body_id=body_id,
            )

        # The vote's ensure_official call should use "board_member"
        assert mock_ensure.call_args[0][3] == "board_member"


# ── Housing authority items loaded into agenda_items ─────────


class TestHousingAuthorityItemsLoaded:
    """Verify that housing_authority_items are inserted into agenda_items."""

    def test_housing_authority_items_inserted(self):
        """M.* items from housing_authority_items are loaded as agenda_items."""
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        meeting_id = uuid.uuid4()
        cur.fetchone.return_value = (meeting_id,)

        data = {
            "meeting_date": "2026-03-03",
            "meeting_type": "regular",
            "members_present": [],
            "members_absent": [],
            "consent_calendar": {"items": []},
            "action_items": [],
            "housing_authority_items": [
                {
                    "item_number": "M.1.a",
                    "title": "Housing Authority Contract",
                    "description": "Approve housing contract amendment",
                    "category": "housing",
                },
                {
                    "item_number": "M.2.a",
                    "title": "Housing Authority Budget",
                    "description": "Approve housing budget",
                    "category": "budget",
                },
            ],
        }

        from db import load_meeting_to_db

        with patch("db.ensure_official") as mock_ensure:
            mock_ensure.return_value = uuid.uuid4()
            load_meeting_to_db(conn, data, city_fips="0660620")

        # Find INSERT INTO agenda_items calls
        agenda_inserts = [
            c for c in cur.execute.call_args_list
            if "INSERT INTO agenda_items" in str(c)
        ]
        assert len(agenda_inserts) == 2, (
            f"Expected 2 agenda_items inserts for housing authority items, got {len(agenda_inserts)}"
        )

    def test_meeting_with_only_housing_items_has_nonzero_count(self):
        """A meeting with only M.* items should still get agenda_items rows."""
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        meeting_id = uuid.uuid4()
        cur.fetchone.return_value = (meeting_id,)

        data = {
            "meeting_date": "2026-03-03",
            "meeting_type": "regular",
            "members_present": [],
            "members_absent": [],
            "consent_calendar": {},
            "action_items": [],
            "housing_authority_items": [
                {"item_number": "M.1.a", "title": "Test", "description": "Test desc"},
            ],
        }

        from db import load_meeting_to_db

        with patch("db.ensure_official"):
            load_meeting_to_db(conn, data, city_fips="0660620")

        agenda_inserts = [
            c for c in cur.execute.call_args_list
            if "INSERT INTO agenda_items" in str(c)
        ]
        assert len(agenda_inserts) >= 1
