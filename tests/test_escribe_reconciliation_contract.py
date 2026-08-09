"""Trust-and-reconciliation contracts for bounded eSCRIBE syncs."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from pipelines.escribemeetings import (
    _assert_persisted_attachment_inventory,
    _attachment_inventory,
    _bounded_full_cohort,
    _classify_escribe_observation,
    _escribe_inventory_sha256,
    sync_escribemeetings,
)


def _meeting(
    guid: str,
    *,
    start: str = "2021/07/20 09:15:00",
    has_agenda: bool = True,
    cancelled: bool = False,
) -> dict:
    return {
        "ID": guid,
        "MeetingName": "City Council",
        "StartDate": start,
        "HasAgenda": has_agenda,
        "IsCancelled": cancelled,
    }


def _revision() -> tuple[dict, str]:
    return ({
        "revision_sha256": "a" * 64,
        "agenda_sha256": "b" * 64,
        "calendar_sha256": "c" * 64,
    }, "<html>agenda</html>")


def test_tri_state_classification_keeps_portal_stubs_out_of_layer2():
    meeting = _meeting("stub")
    assert _classify_escribe_observation(
        meeting,
        {"items": [{"item_number": "", "title": "Details"}]},
    ) == "legacy_portal_stub"
    assert _classify_escribe_observation(
        _meeting("none", has_agenda=False)
    ) == "no_current_agenda"
    assert _classify_escribe_observation(
        meeting,
        {"items": [{"item_number": "VII.1", "title": "Contract"}]},
    ) == "complete_agenda"


def test_inventory_hash_is_order_independent_but_content_sensitive():
    first = _meeting("first")
    second = _meeting("second", start="2021/07/20 10:00:00")
    assert _escribe_inventory_sha256([first, second]) == (
        _escribe_inventory_sha256([second, first])
    )
    changed = dict(second, HasAgenda=False)
    assert _escribe_inventory_sha256([first, second]) != (
        _escribe_inventory_sha256([first, changed])
    )


def test_full_cohorts_are_explicit_deterministic_and_capped():
    meetings = [_meeting(str(index)) for index in range(12)]
    cohort, proof = _bounded_full_cohort(
        meetings, limit=2, offset=3, cohort_guids=None
    )
    assert cohort == meetings[3:5]
    assert proof["guids"] == ["3", "4"]

    selected, proof = _bounded_full_cohort(
        meetings, limit=None, offset=0, cohort_guids=["8", "2"]
    )
    assert [row["ID"] for row in selected] == ["8", "2"]
    assert proof["mode"] == "guids"

    with pytest.raises(ValueError, match="Unbounded"):
        _bounded_full_cohort(
            meetings, limit=None, offset=0, cohort_guids=None
        )
    with pytest.raises(ValueError, match="between 1 and 10"):
        _bounded_full_cohort(
            meetings, limit=11, offset=0, cohort_guids=None
        )


def test_attachment_inventory_requires_document_id_and_download_hash():
    scraped = {
        "items": [{
            "item_number": "VII.1",
            "attachments": [{
                "document_id": "70001",
                "content_sha256": "d" * 64,
            }],
        }],
    }
    entries, inventory_sha256 = _attachment_inventory(scraped)
    assert entries == [("VII.1", "70001", "d" * 64)]
    assert len(inventory_sha256) == 64

    scraped["items"][0]["attachments"][0]["content_sha256"] = "missing"
    with pytest.raises(RuntimeError, match="downloaded-byte proof"):
        _attachment_inventory(scraped)


def test_persisted_attachment_reconciliation_is_exact():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [
        [("VII.1",)],
        [("VII.1", "70001", "e" * 64, "r" * 64)],
    ]
    _assert_persisted_attachment_inventory(
        conn,
        city_fips="0660620",
        meeting_guid="guid",
        expected_revision_sha256="r" * 64,
        expected=[("VII.1", "70001", "e" * 64)],
    )
    query = cur.execute.call_args_list[-1].args[0]
    assert "aia.source_revision_sha256 IS NOT NULL" in query
    assert "ai.agenda_source_authority = 'agenda'" in query
    cur.fetchall.side_effect = [
        [("VII.1",)],
        [("VII.1", "70001", "e" * 64, "r" * 64)],
    ]
    with pytest.raises(RuntimeError, match="mismatch after load"):
        _assert_persisted_attachment_inventory(
            conn,
            city_fips="0660620",
            meeting_guid="guid",
            expected_revision_sha256="r" * 64,
            expected=[],
        )


def test_persisted_inventory_excludes_minutes_owned_parent():
    """Minutes packets do not become mutable agenda attachments by counting."""
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [[], []]

    _assert_persisted_attachment_inventory(
        conn,
        city_fips="0660620",
        meeting_guid="guid",
        expected_revision_sha256="r" * 64,
        expected=[("VII.1", "70001", "e" * 64)],
    )

    executed = "\n".join(call.args[0] for call in cur.execute.call_args_list)
    assert executed.count("ai.agenda_source_authority = 'agenda'") == 2


def test_unbounded_full_sync_fails_closed_before_processing():
    with patch(
        "escribemeetings_scraper.create_session", return_value=MagicMock()
    ), patch(
        "escribemeetings_scraper.discover_meetings",
        return_value=[_meeting("guid")],
    ):
        with pytest.raises(ValueError, match="Unbounded"):
            sync_escribemeetings(
                MagicMock(), "0660620", sync_type="full"
            )


def test_legacy_stub_is_persisted_but_never_loaded_to_layer2():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = None
    ingest = MagicMock(return_value=uuid.uuid4())
    load = MagicMock()
    scraped = {
        "meeting_date": "2021-07-20",
        "meeting_name": "City Council",
        "portal_url": "https://example.test/stub",
        "items": [{"item_number": "", "title": "Details"}],
        "stats": {"total_attachments": 0, "downloaded_attachments": 0},
    }
    with patch(
        "escribemeetings_scraper.create_session", return_value=MagicMock()
    ), patch(
        "escribemeetings_scraper.discover_meetings",
        return_value=[_meeting("stub")],
    ), patch(
        "escribemeetings_scraper.fetch_meeting_revision",
        return_value=_revision(),
    ), patch(
        "escribemeetings_scraper.scrape_meeting", return_value=scraped
    ), patch(
        "db.resolve_body_id", return_value=uuid.uuid4()
    ), patch(
        "db.ingest_document", ingest
    ), patch(
        "db.load_meeting_to_db", load
    ):
        result = sync_escribemeetings(
            conn, "0660620", sync_type="full", limit=1
        )

    ingest.assert_called_once()
    load.assert_not_called()
    assert result["source_observation_outcomes"] == {
        "legacy_portal_stub": 1
    }
    assert result["source_inventory_complete"] is True


def test_unchanged_legacy_stub_skips_scrape_write_and_retirement():
    meeting = _meeting("stub")
    inventory_sha256 = _escribe_inventory_sha256([meeting])
    revision_sha256 = _revision()[0]["revision_sha256"]
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (
        revision_sha256,
        False,
        False,
        False,
        None,
        "legacy_portal_stub",
        inventory_sha256,
        revision_sha256,
        uuid.uuid4(),
        False,
    )
    scrape = MagicMock()
    ingest = MagicMock()
    load = MagicMock()
    retire = MagicMock()

    with patch(
        "escribemeetings_scraper.create_session", return_value=MagicMock()
    ), patch(
        "escribemeetings_scraper.discover_meetings", return_value=[meeting]
    ), patch(
        "escribemeetings_scraper.fetch_meeting_revision",
        return_value=_revision(),
    ), patch(
        "pipelines.escribemeetings._scrape_meeting_with_timeout", scrape
    ), patch(
        "db.resolve_body_id", return_value=uuid.uuid4()
    ), patch(
        "db.ingest_document", ingest
    ), patch(
        "db.load_meeting_to_db", load
    ), patch(
        "db.retire_escribe_agenda", retire
    ):
        result = sync_escribemeetings(
            conn, "0660620", sync_type="full", limit=1
        )

    scrape.assert_not_called()
    ingest.assert_not_called()
    load.assert_not_called()
    retire.assert_not_called()
    conn.commit.assert_not_called()
    assert not any(
        "UPDATE documents" in call.args[0]
        for call in cur.execute.call_args_list
    )
    assert result["records_new"] == 0
    assert result["records_updated"] == 0
    assert result["skipped"] == 1
    assert result["source_observation_outcomes"] == {
        "legacy_portal_stub": 1
    }
    assert result["source_inventory_complete"] is True


def test_complete_observation_without_applied_revision_retries_layer2():
    meeting = _meeting("complete-after-crash")
    inventory_sha256 = _escribe_inventory_sha256([meeting])
    revision_sha256 = _revision()[0]["revision_sha256"]
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (
        "older-applied-revision",
        True,
        False,
        True,
        None,
        "complete_agenda",
        inventory_sha256,
        revision_sha256,
        uuid.uuid4(),
        False,
    )
    cur.fetchall.return_value = []
    scraped = {
        "meeting_date": "2021-07-20",
        "meeting_name": "City Council",
        "portal_url": "https://example.test/complete",
        "items": [{"item_number": "VII.1", "title": "Contract"}],
        "stats": {"total_attachments": 0, "downloaded_attachments": 0},
    }
    scrape = MagicMock(return_value=scraped)
    ingest = MagicMock(return_value=uuid.uuid4())
    load = MagicMock()

    with patch(
        "escribemeetings_scraper.create_session", return_value=MagicMock()
    ), patch(
        "escribemeetings_scraper.discover_meetings", return_value=[meeting]
    ), patch(
        "escribemeetings_scraper.fetch_meeting_revision",
        return_value=_revision(),
    ), patch(
        "pipelines.escribemeetings._scrape_meeting_with_timeout", scrape
    ), patch(
        "db.resolve_body_id", return_value=uuid.uuid4()
    ), patch(
        "db.ingest_document", ingest
    ), patch(
        "db.load_meeting_to_db", load
    ):
        result = sync_escribemeetings(
            conn, "0660620", sync_type="full", limit=1
        )

    scrape.assert_called_once()
    ingest.assert_called_once()
    load.assert_called_once()
    state_sql = " ".join(cur.execute.call_args_list[0].args[0].split())
    assert (
        "current_raw.metadata ->>'agenda_revision_applied_sha256' "
        "AS applied_revision"
    ) in state_sql
    assert result["records_updated"] == 1
    assert result["skipped"] == 0
    assert result["source_observation_outcomes"] == {
        "complete_agenda": 1
    }


def test_no_current_agenda_observation_does_not_retire_unowned_history():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (
        None, False, False, False, None, None, None, None, None, False
    )
    retire = MagicMock()
    ingest = MagicMock(return_value=uuid.uuid4())
    with patch(
        "escribemeetings_scraper.create_session", return_value=MagicMock()
    ), patch(
        "escribemeetings_scraper.discover_meetings",
        return_value=[_meeting("none", has_agenda=False)],
    ), patch(
        "escribemeetings_scraper.fetch_meeting_revision",
        return_value=_revision(),
    ), patch(
        "db.resolve_body_id", return_value=uuid.uuid4()
    ), patch(
        "db.ingest_document", ingest
    ), patch(
        "db.retire_escribe_agenda", retire
    ):
        result = sync_escribemeetings(
            conn, "0660620", sync_type="full", limit=1
        )

    ingest.assert_called_once()
    retire.assert_not_called()
    assert result["awaiting_agenda"] == 1
    assert result["source_observation_outcomes"] == {
        "no_current_agenda": 1
    }


def test_unchanged_no_current_agenda_uses_observation_not_applied_marker():
    meeting = _meeting("none", has_agenda=False)
    inventory_sha256 = _escribe_inventory_sha256([meeting])
    revision_sha256 = _revision()[0]["revision_sha256"]
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (
        None,
        False,
        False,
        False,
        None,
        "no_current_agenda",
        inventory_sha256,
        revision_sha256,
        uuid.uuid4(),
        False,
    )
    ingest = MagicMock()
    retire = MagicMock()

    with patch(
        "escribemeetings_scraper.create_session", return_value=MagicMock()
    ), patch(
        "escribemeetings_scraper.discover_meetings", return_value=[meeting]
    ), patch(
        "escribemeetings_scraper.fetch_meeting_revision",
        return_value=_revision(),
    ), patch(
        "db.resolve_body_id", return_value=uuid.uuid4()
    ), patch(
        "db.ingest_document", ingest
    ), patch(
        "db.retire_escribe_agenda", retire
    ):
        result = sync_escribemeetings(
            conn, "0660620", sync_type="full", limit=1
        )

    ingest.assert_not_called()
    retire.assert_not_called()
    conn.commit.assert_not_called()
    assert result["records_new"] == 0
    assert result["records_updated"] == 0
    assert result["skipped"] == 1
    assert result["source_observation_outcomes"] == {
        "no_current_agenda": 1
    }


def test_loader_rejects_distinct_guid_at_same_natural_key():
    from db.meetings import load_meeting_to_db

    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = ("other-guid",)
    data = {
        "meeting_date": "2021-07-20",
        "meeting_type": "regular",
        "members_present": [],
        "members_absent": [],
        "action_items": [],
    }
    with patch("db.officials._resolve_body_type", return_value="council"):
        with pytest.raises(RuntimeError, match="distinct eSCRIBE GUIDs"):
            load_meeting_to_db(
                conn,
                data,
                city_fips="0660620",
                body_id=uuid.uuid4(),
                authoritative_agenda_revision="f" * 64,
                source_meeting_guid="new-guid",
                source_observed_at="2026-08-08T12:00:00-07:00",
            )
