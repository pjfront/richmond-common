"""Rollout guards for source cancellation and eSCRIBE identity cutover."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = {
    "meeting_guid": "00711755-eda3-4813-a8e9-5f5bdc8b2f2f",
    "agenda_revision_sha256": "a" * 64,
    "observed_at": "2026-08-07T12:00:00-07:00",
}


def _meeting_payload(*, with_identity: bool = True) -> dict:
    data = {
        "meeting_date": "2026-08-18",
        "meeting_type": "regular",
        "city_fips": "0660620",
        "consent_calendar": {"items": []},
        "action_items": [],
        "housing_authority_items": [],
    }
    if with_identity:
        data["_authoritative_escribe_source"] = dict(IDENTITY)
    return data


def test_orientation_service_role_queries_both_exclude_cancelled_meetings():
    route = (
        ROOT
        / "web"
        / "src"
        / "app"
        / "api"
        / "email"
        / "send-orientation"
        / "route.ts"
    ).read_text(encoding="utf-8")

    targeted_start = route.index("if (meetingId)")
    discovery_start = route.index("} else {", targeted_start)
    query_end = route.index("if (candidates.length === 0)", discovery_start)
    targeted_query = route[targeted_start:discovery_start]
    discovery_query = route[discovery_start:query_end]

    assert ".from('meetings')" in targeted_query
    assert ".is('source_cancelled_at', null)" in targeted_query
    assert "COUNCIL_ORIENTATION_SOURCE_COLUMNS" in targeted_query
    assert ".eq('city_fips', RICHMOND_FIPS)" in targeted_query
    assert ".eq('meeting_type', 'regular')" in targeted_query
    assert (
        ".eq('bodies.body_type', RICHMOND_COUNCIL_BODY_TYPE)"
        in targeted_query
    )
    assert ".gte('meeting_date', today)" in targeted_query
    assert ".from('meetings')" in discovery_query
    assert ".is('source_cancelled_at', null)" in discovery_query
    assert "COUNCIL_ORIENTATION_SOURCE_COLUMNS" in discovery_query
    assert ".eq('city_fips', RICHMOND_FIPS)" in discovery_query
    assert ".eq('meeting_type', 'regular')" in discovery_query
    assert (
        ".eq('bodies.body_type', RICHMOND_COUNCIL_BODY_TYPE)"
        in discovery_query
    )
    assert ".gte('meeting_date', today)" in discovery_query


def test_legacy_escribe_identity_missing_fails_closed():
    from db import (
        AuthoritativeEscribeIdentityError,
        require_authoritative_escribe_identity,
    )

    with pytest.raises(
        AuthoritativeEscribeIdentityError,
        match="disabled without authoritative source identity",
    ):
        require_authoritative_escribe_identity(_meeting_payload(with_identity=False))


@pytest.mark.parametrize(
    "identity_patch",
    [
        {"agenda_revision_sha256": "not-a-sha256"},
        {"observed_at": "2026-08-07T12:00:00"},
    ],
)
def test_malformed_escribe_identity_fails_closed(identity_patch):
    from db import (
        AuthoritativeEscribeIdentityError,
        require_authoritative_escribe_identity,
    )

    data = _meeting_payload()
    data["_authoritative_escribe_source"].update(identity_patch)
    with pytest.raises(AuthoritativeEscribeIdentityError):
        require_authoritative_escribe_identity(data)


def test_conflicting_explicit_and_embedded_identity_fails_closed():
    from db import (
        AuthoritativeEscribeIdentityError,
        require_authoritative_escribe_identity,
    )

    with pytest.raises(AuthoritativeEscribeIdentityError, match="Conflicting"):
        require_authoritative_escribe_identity(
            _meeting_payload(),
            source_meeting_guid="different-guid",
        )


def test_authoritative_wrapper_forwards_exact_identity(monkeypatch):
    import db

    raw_loader = MagicMock(return_value="meeting-id")
    monkeypatch.setattr(db, "_load_meeting_to_db", raw_loader)
    conn = object()
    data = _meeting_payload()

    result = db.load_authoritative_escribe_agenda(
        conn,
        data,
        agenda_url="https://example.test/agenda",
        commit=False,
    )

    assert result == "meeting-id"
    raw_loader.assert_called_once_with(
        conn,
        data,
        document_id=None,
        city_fips="0660620",
        body_id=None,
        agenda_url="https://example.test/agenda",
        authoritative_agenda_revision="a" * 64,
        source_meeting_guid=IDENTITY["meeting_guid"],
        source_observed_at=IDENTITY["observed_at"],
        commit=False,
    )


@pytest.mark.parametrize("command", ["load", "load-all"])
def test_documented_legacy_cli_preflights_before_database_connection(
    command,
    tmp_path,
    monkeypatch,
):
    import db

    legacy_file = tmp_path / "legacy.json"
    legacy_file.write_text(
        json.dumps(_meeting_payload(with_identity=False)),
        encoding="utf-8",
    )
    connection_factory = MagicMock()
    monkeypatch.setattr(db, "get_connection", connection_factory)
    argv = ["db", command]
    argv.append(str(legacy_file if command == "load" else tmp_path))
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(db.AuthoritativeEscribeIdentityError):
        db.main()

    connection_factory.assert_not_called()


def test_converter_carries_only_supplied_complete_source_identity():
    from run_pipeline import convert_escribemeetings_to_scanner_format

    raw = {
        "meeting_date": "2026-08-18",
        "meeting_name": "City Council",
        "city_fips": "0660620",
        "guid": IDENTITY["meeting_guid"],
        "items": [],
    }
    without_revision = convert_escribemeetings_to_scanner_format(raw)
    assert "_authoritative_escribe_source" not in without_revision

    raw.update({
        "agenda_revision_sha256": IDENTITY["agenda_revision_sha256"],
        "agenda_revision_observed_at": IDENTITY["observed_at"],
    })
    with_revision = convert_escribemeetings_to_scanner_format(raw)
    assert with_revision["_authoritative_escribe_source"] == IDENTITY


def test_pipeline_loader_validates_before_database_connection(monkeypatch):
    import db
    from run_pipeline import load_authoritative_pipeline_meeting

    connection_factory = MagicMock()
    monkeypatch.setattr(db, "get_connection", connection_factory)

    with pytest.raises(db.AuthoritativeEscribeIdentityError):
        load_authoritative_pipeline_meeting(_meeting_payload(with_identity=False))

    connection_factory.assert_not_called()


def test_run_pipeline_load_db_fails_before_scanning_without_identity(tmp_path):
    import db
    from run_pipeline import run_pipeline

    meeting_file = tmp_path / "legacy-meeting.json"
    meeting_file.write_text(
        json.dumps(_meeting_payload(with_identity=False)),
        encoding="utf-8",
    )
    scanner = MagicMock()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("run_pipeline.scan_meeting_json", scanner)
        with pytest.raises(db.AuthoritativeEscribeIdentityError):
            run_pipeline(
                date="2026-08-18",
                skip_escribemeetings=True,
                meeting_json_path=str(meeting_file),
                load_db=True,
            )

    scanner.assert_not_called()


def test_pipeline_loader_uses_gated_entrypoint_and_single_transaction(monkeypatch):
    import db
    from run_pipeline import load_authoritative_pipeline_meeting

    conn = MagicMock()
    monkeypatch.setattr(db, "get_connection", MagicMock(return_value=conn))
    gated_loader = MagicMock(return_value="meeting-id")
    monkeypatch.setattr(db, "load_authoritative_escribe_agenda", gated_loader)
    data = _meeting_payload()

    result = load_authoritative_pipeline_meeting(data)

    assert result == "meeting-id"
    gated_loader.assert_called_once_with(
        conn,
        data,
        city_fips="0660620",
        agenda_url=None,
        commit=False,
    )
    conn.commit.assert_called_once_with()
    conn.rollback.assert_not_called()
    conn.close.assert_called_once_with()
