"""Focused contracts for authoritative City Council minutes URLs."""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_URL = "https://www.ci.richmond.ca.us/Archive.aspx?ADID=17484"


def _minimal_minutes() -> dict:
    return {
        "meeting_date": "2026-04-07",
        "meeting_type": "regular",
        "members_present": [],
        "members_absent": [],
        "action_items": [],
        "consent_calendar": {"items": []},
    }


def _mock_connection():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cursor


def test_official_minutes_existing_row_repairs_missing_or_blank_url():
    """A loaded Archive document fills a NULL, blank, or whitespace URL."""
    from db.meetings import load_meeting_to_db

    conn, cursor = _mock_connection()
    document_id = uuid.uuid4()
    meeting_id = uuid.uuid4()
    cursor.fetchone.side_effect = [
        (ARCHIVE_URL,),
        (meeting_id, False),
        (False,),
        (meeting_id,),
    ]

    with patch("db.officials._resolve_body_type", return_value="city_council"):
        result = load_meeting_to_db(
            conn,
            _minimal_minutes(),
            document_id=document_id,
            city_fips="0660620",
            body_id=uuid.uuid4(),
            official_minutes=True,
        )

    assert result == meeting_id
    source_lookup = cursor.execute.call_args_list[0]
    assert "FROM documents" in source_lookup.args[0]
    assert "source_type = 'archive_center'" in source_lookup.args[0]
    assert "credibility_tier = 1" in source_lookup.args[0]
    assert source_lookup.args[1] == (document_id, "0660620")

    meeting_update = next(
        call
        for call in cursor.execute.call_args_list
        if "UPDATE meetings" in call.args[0]
        and "RETURNING id" in call.args[0]
    )
    update_sql, update_params = meeting_update.args
    assert "NULLIF(BTRIM(minutes_url), ''), %s" in update_sql
    assert update_sql.count("%s") == len(update_params)
    assert ARCHIVE_URL in update_params


def test_official_minutes_insert_and_upsert_preserve_existing_link():
    """Insert carries the source URL; conflict fallback never replaces a link."""
    from db.meetings import load_meeting_to_db

    conn, cursor = _mock_connection()
    document_id = uuid.uuid4()
    meeting_id = uuid.uuid4()
    cursor.fetchone.side_effect = [
        (ARCHIVE_URL,),
        None,
        (meeting_id,),
    ]

    with patch("db.officials._resolve_body_type", return_value="city_council"):
        result = load_meeting_to_db(
            conn,
            _minimal_minutes(),
            document_id=document_id,
            city_fips="0660620",
            body_id=uuid.uuid4(),
            official_minutes=True,
        )

    assert result == meeting_id
    meeting_insert = next(
        call
        for call in cursor.execute.call_args_list
        if "INSERT INTO meetings" in call.args[0]
    )
    sql, params = meeting_insert.args
    assert "body_id, agenda_url, minutes_url, source_meeting_guid" in sql
    assert "NULLIF(BTRIM(meetings.minutes_url), '')" in sql
    assert "EXCLUDED.minutes_url" in sql
    assert sql.count("%s") == len(params)
    assert ARCHIVE_URL in params


def test_official_minutes_fail_closed_without_tier1_source_url():
    """An official load cannot silently create another provenance-less row."""
    from db.meetings import load_meeting_to_db

    conn, cursor = _mock_connection()
    cursor.fetchone.return_value = None

    with patch("db.officials._resolve_body_type", return_value="city_council"):
        with pytest.raises(ValueError, match="Tier 1 source_url"):
            load_meeting_to_db(
                conn,
                _minimal_minutes(),
                document_id=uuid.uuid4(),
                city_fips="0660620",
                body_id=uuid.uuid4(),
                official_minutes=True,
            )

    assert not any(
        "INSERT INTO meetings" in call.args[0]
        or "UPDATE meetings" in call.args[0]
        for call in cursor.execute.call_args_list
    )


def test_minutes_liveness_accepts_only_narrow_loaded_archive_evidence():
    """Loaded minutes count, while agenda/transcript-only meetings still fail."""
    manifest = yaml.safe_load(
        (ROOT / "docs" / "pipeline-manifest.yaml").read_text(encoding="utf-8")
    )
    expectation = next(
        item
        for item in manifest["expectations"]
        if item["id"] == "past_meetings_have_minutes_within_45_days"
    )
    check = expectation["check"]

    assert "NULLIF(BTRIM(m.minutes_url), '') IS NULL" in check
    assert "d.id = m.document_id" in check
    assert "d.source_type = 'archive_center'" in check
    assert "d.credibility_tier = 1" in check
    assert "NULLIF(BTRIM(d.source_url), '') IS NOT NULL" in check
    assert "d.metadata->>'amid' = '31'" in check
    assert "er.is_current = TRUE" in check
    assert "mo.source = 'transcript'" not in check
    assert "d.source_type = 'escribemeetings'" not in check
