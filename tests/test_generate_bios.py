"""Tests for the bio generation pipeline (generate_bios.py).

Tests cover the SQL query functions and the orchestration logic.
All DB interactions are mocked with cursor/fetchone/fetchall patterns.
"""

import json
import uuid
from datetime import date
from unittest.mock import patch, MagicMock, call

import pytest

from src.generate_bios import (
    get_current_officials,
    get_vote_count,
    get_attendance_stats,
    get_top_categories,
    get_majority_alignment_rate,
    get_sole_dissent_stats,
    save_official_bios,
    generate_bio_for_official,
)


# ── Helpers ──────────────────────────────────────────────────


def make_cursor(rows=None, description=None, fetchone_val=None):
    """Build a mock cursor with fetchall/fetchone support."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    if rows is not None:
        cur.fetchall.return_value = rows
    if description is not None:
        cur.description = description
    if fetchone_val is not None:
        cur.fetchone.return_value = fetchone_val
    return cur


def make_conn(cursor):
    """Build a mock connection that yields the given cursor."""
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


# ── get_current_officials ────────────────────────────────────


def test_get_current_officials():
    oid = uuid.uuid4()
    rows = [
        (oid, "Eduardo Martinez", "mayor", None, date(2023, 1, 10), None),
    ]
    desc = [("id",), ("name",), ("role",), ("seat",), ("term_start",), ("term_end",)]
    cur = make_cursor(rows=rows, description=desc)
    conn = make_conn(cur)

    result = get_current_officials(conn, "0660620")
    assert len(result) == 1
    assert result[0]["name"] == "Eduardo Martinez"
    assert result[0]["role"] == "mayor"


def test_get_current_officials_empty():
    cur = make_cursor(rows=[], description=[("id",), ("name",), ("role",), ("seat",), ("term_start",), ("term_end",)])
    conn = make_conn(cur)

    result = get_current_officials(conn, "0660620")
    assert result == []


# ── get_vote_count ───────────────────────────────────────────


def test_get_vote_count():
    cur = make_cursor(fetchone_val=(487,))
    conn = make_conn(cur)

    assert get_vote_count(conn, "some-id") == 487


def test_get_vote_count_zero():
    cur = make_cursor(fetchone_val=(0,))
    conn = make_conn(cur)

    assert get_vote_count(conn, "some-id") == 0


# ── get_attendance_stats ─────────────────────────────────────


def test_get_attendance_stats():
    cur = make_cursor(fetchone_val=(24, 22))
    conn = make_conn(cur)

    result = get_attendance_stats(conn, "some-id")
    assert result == {"meetings_total": 24, "meetings_attended": 22}


def test_get_attendance_stats_zero():
    cur = make_cursor(fetchone_val=(0, 0))
    conn = make_conn(cur)

    result = get_attendance_stats(conn, "some-id")
    assert result == {"meetings_total": 0, "meetings_attended": 0}


# ── get_top_categories ───────────────────────────────────────


def test_get_top_categories():
    rows = [("contracts", 98), ("governance", 72), ("budget", 45)]
    cur = make_cursor(rows=rows)
    conn = make_conn(cur)

    result = get_top_categories(conn, "some-id", limit=5)
    assert len(result) == 3
    assert result[0] == {"category": "contracts", "count": 98}
    assert result[2] == {"category": "budget", "count": 45}


def test_get_top_categories_empty():
    cur = make_cursor(rows=[])
    conn = make_conn(cur)

    result = get_top_categories(conn, "some-id")
    assert result == []


# ── get_majority_alignment_rate ──────────────────────────────


def test_majority_alignment_rate():
    """89 of 100 votes with majority = 0.89."""
    cur = make_cursor(fetchone_val=(100, 89))
    conn = make_conn(cur)

    rate = get_majority_alignment_rate(conn, "some-id")
    assert rate == pytest.approx(0.89)


def test_majority_alignment_rate_zero_votes():
    cur = make_cursor(fetchone_val=(0, 0))
    conn = make_conn(cur)

    rate = get_majority_alignment_rate(conn, "some-id")
    assert rate == 0.0


def test_majority_alignment_rate_perfect():
    cur = make_cursor(fetchone_val=(50, 50))
    conn = make_conn(cur)

    rate = get_majority_alignment_rate(conn, "some-id")
    assert rate == 1.0


# ── get_sole_dissent_stats ───────────────────────────────────


def test_sole_dissent_stats():
    rows = [("budget", 5), ("infrastructure", 3)]
    cur = make_cursor(rows=rows)
    conn = make_conn(cur)

    result = get_sole_dissent_stats(conn, "some-id")
    assert result["sole_dissent_count"] == 8
    assert len(result["sole_dissent_categories"]) == 2
    assert result["sole_dissent_categories"][0] == {"category": "budget", "count": 5}


def test_sole_dissent_stats_none():
    cur = make_cursor(rows=[])
    conn = make_conn(cur)

    result = get_sole_dissent_stats(conn, "some-id")
    assert result["sole_dissent_count"] == 0
    assert result["sole_dissent_categories"] == []


# ── save_official_bios ───────────────────────────────────────


def test_save_official_bios_full():
    """Writes both factual and summary to DB."""
    cur = make_cursor()
    conn = make_conn(cur)

    factual = {"name": "Test", "vote_count": 100}
    save_official_bios(conn, "oid-123", factual, bio_summary="A summary.", bio_model="claude-test")

    cur.execute.assert_called_once()
    args = cur.execute.call_args[0]
    assert "UPDATE officials" in args[0]
    params = args[1]
    assert json.loads(params[0]) == factual  # bio_factual as JSON
    assert params[1] == "A summary."
    assert params[3] == "claude-test"
    assert params[4] == "oid-123"
    conn.commit.assert_called_once()


def test_save_official_bios_factual_only():
    """Writes factual profile with NULL summary."""
    cur = make_cursor()
    conn = make_conn(cur)

    factual = {"name": "Test", "vote_count": 0}
    save_official_bios(conn, "oid-456", factual)

    params = cur.execute.call_args[0][1]
    assert params[1] is None  # bio_summary
    assert params[3] is None  # bio_model


# ── generate_bio_for_official (orchestration) ────────────────


@patch("src.generate_bios.generate_bio_summary")
@patch("src.generate_bios.build_factual_profile")
@patch("src.generate_bios.save_official_bios")
@patch("src.generate_bios.get_sole_dissent_stats")
@patch("src.generate_bios.get_majority_alignment_rate")
@patch("src.generate_bios.get_top_categories")
@patch("src.generate_bios.get_attendance_stats")
@patch("src.generate_bios.get_vote_count")
def test_generate_bio_full_pipeline(
    mock_votes,
    mock_attendance,
    mock_cats,
    mock_alignment,
    mock_dissent,
    mock_save,
    mock_factual,
    mock_summary,
):
    """Full pipeline: queries stats, builds factual, generates summary, saves."""
    oid = uuid.uuid4()
    official = {
        "id": oid,
        "name": "Jane Doe",
        "role": "councilmember",
        "seat": "District 1",
        "term_start": date(2023, 1, 10),
        "term_end": None,
    }

    mock_votes.return_value = 487
    mock_attendance.return_value = {"meetings_attended": 22, "meetings_total": 24}
    mock_cats.return_value = [{"category": "contracts", "count": 98}]
    mock_alignment.return_value = 0.89
    mock_dissent.return_value = {"sole_dissent_count": 5, "sole_dissent_categories": [{"category": "budget", "count": 3}]}
    mock_factual.return_value = {"name": "Jane Doe", "vote_count": 487}
    mock_summary.return_value = {"summary": "Jane Doe is an active participant.", "model": "claude-test"}

    conn = MagicMock()
    result = generate_bio_for_official(conn, official)

    # Verify all stats were queried
    mock_votes.assert_called_once_with(conn, str(oid))
    mock_attendance.assert_called_once_with(conn, str(oid))
    mock_cats.assert_called_once_with(conn, str(oid))
    mock_alignment.assert_called_once_with(conn, str(oid))
    mock_dissent.assert_called_once_with(conn, str(oid))

    # Verify factual profile was built
    mock_factual.assert_called_once()

    # Verify summary was generated
    mock_summary.assert_called_once()

    # Verify saved to DB
    mock_save.assert_called_once()

    # Check result
    assert result["name"] == "Jane Doe"
    assert result["summary"] == "Jane Doe is an active participant."
    assert result["model"] == "claude-test"


@patch("src.generate_bios.generate_bio_summary")
@patch("src.generate_bios.build_factual_profile")
@patch("src.generate_bios.save_official_bios")
@patch("src.generate_bios.get_sole_dissent_stats")
@patch("src.generate_bios.get_majority_alignment_rate")
@patch("src.generate_bios.get_top_categories")
@patch("src.generate_bios.get_attendance_stats")
@patch("src.generate_bios.get_vote_count")
def test_generate_bio_dry_run_skips_save(
    mock_votes, mock_attendance, mock_cats, mock_alignment, mock_dissent,
    mock_save, mock_factual, mock_summary,
):
    """Dry run should NOT write to DB."""
    official = {
        "id": uuid.uuid4(), "name": "Test", "role": "councilmember",
        "seat": None, "term_start": None, "term_end": None,
    }
    mock_votes.return_value = 100
    mock_attendance.return_value = {"meetings_attended": 10, "meetings_total": 12}
    mock_cats.return_value = []
    mock_alignment.return_value = 0.85
    mock_dissent.return_value = {"sole_dissent_count": 0, "sole_dissent_categories": []}
    mock_factual.return_value = {"name": "Test"}
    mock_summary.return_value = {"summary": "Test bio.", "model": "claude-test"}

    conn = MagicMock()
    generate_bio_for_official(conn, official, dry_run=True)

    mock_save.assert_not_called()


@patch("src.generate_bios.generate_bio_summary")
@patch("src.generate_bios.build_factual_profile")
@patch("src.generate_bios.save_official_bios")
@patch("src.generate_bios.get_sole_dissent_stats")
@patch("src.generate_bios.get_majority_alignment_rate")
@patch("src.generate_bios.get_top_categories")
@patch("src.generate_bios.get_attendance_stats")
@patch("src.generate_bios.get_vote_count")
def test_generate_bio_factual_only_skips_api(
    mock_votes, mock_attendance, mock_cats, mock_alignment, mock_dissent,
    mock_save, mock_factual, mock_summary,
):
    """Factual-only mode should NOT call Claude API."""
    official = {
        "id": uuid.uuid4(), "name": "Test", "role": "councilmember",
        "seat": None, "term_start": None, "term_end": None,
    }
    mock_votes.return_value = 100
    mock_attendance.return_value = {"meetings_attended": 10, "meetings_total": 12}
    mock_cats.return_value = []
    mock_alignment.return_value = 0.85
    mock_dissent.return_value = {"sole_dissent_count": 0, "sole_dissent_categories": []}
    mock_factual.return_value = {"name": "Test"}

    conn = MagicMock()
    result = generate_bio_for_official(conn, official, factual_only=True)

    mock_summary.assert_not_called()
    assert result["summary"] is None
    # But factual was still saved
    mock_save.assert_called_once()


@patch("src.generate_bios.generate_bio_summary")
@patch("src.generate_bios.build_factual_profile")
@patch("src.generate_bios.save_official_bios")
@patch("src.generate_bios.get_sole_dissent_stats")
@patch("src.generate_bios.get_majority_alignment_rate")
@patch("src.generate_bios.get_top_categories")
@patch("src.generate_bios.get_attendance_stats")
@patch("src.generate_bios.get_vote_count")
def test_generate_bio_zero_votes_skips_summary(
    mock_votes, mock_attendance, mock_cats, mock_alignment, mock_dissent,
    mock_save, mock_factual, mock_summary,
):
    """Officials with no votes should get factual profile but no summary."""
    official = {
        "id": uuid.uuid4(), "name": "New Member", "role": "councilmember",
        "seat": None, "term_start": None, "term_end": None,
    }
    mock_votes.return_value = 0
    mock_attendance.return_value = {"meetings_attended": 0, "meetings_total": 0}
    mock_cats.return_value = []
    mock_alignment.return_value = 0.0
    mock_dissent.return_value = {"sole_dissent_count": 0, "sole_dissent_categories": []}
    mock_factual.return_value = {"name": "New Member", "vote_count": 0}

    conn = MagicMock()
    result = generate_bio_for_official(conn, official)

    mock_summary.assert_not_called()
    assert result["summary"] is None
    # Factual profile still saved
    mock_save.assert_called_once()
