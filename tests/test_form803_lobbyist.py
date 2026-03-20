"""Tests for FPPC Form 803 (behested payments) and lobbyist registration pipelines.

Sprint 13.1 (Form 803) and Sprint 13.3 (Lobbyist Registrations).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest


# ══════════════════════════════════════════════════════════════
# FPPC Form 803 Client Tests
# ══════════════════════════════════════════════════════════════


class TestForm803NormalizeApiRecord:
    """Test normalization of FPPC API responses."""

    def test_normalizes_standard_record(self):
        from fppc_form803_client import _normalize_api_record

        record = {
            "filerName": "Eduardo Martinez",
            "payorName": "Chevron Corporation",
            "payeeName": "Richmond Promise",
            "amount": 50000,
            "paymentDate": "01/15/2026",
            "filingDate": "02/10/2026",
            "agency": "City of Richmond",
            "filingId": "803-2026-001",
        }
        result = _normalize_api_record(record)

        assert result is not None
        assert result["official_name"] == "Eduardo Martinez"
        assert result["payor_name"] == "Chevron Corporation"
        assert result["payee_name"] == "Richmond Promise"
        assert result["amount"] == 50000.0
        assert result["payment_date"] == "2026-01-15"
        assert result["filing_date"] == "2026-02-10"
        assert result["filing_id"] == "803-2026-001"

    def test_handles_alternative_field_names(self):
        from fppc_form803_client import _normalize_api_record

        record = {
            "officialName": "Tom Butt",
            "sourceOfPayment": "ABC Corp",
            "payeeOrganization": "Local Nonprofit",
            "paymentAmount": "25000.50",
            "dateOfPayment": "2025-06-15",
            "id": "12345",
        }
        result = _normalize_api_record(record)

        assert result["official_name"] == "Tom Butt"
        assert result["payor_name"] == "ABC Corp"
        assert result["payee_name"] == "Local Nonprofit"
        assert result["amount"] == 25000.50

    def test_returns_none_for_no_official(self):
        from fppc_form803_client import _normalize_api_record

        assert _normalize_api_record({}) is None
        assert _normalize_api_record({"filerName": ""}) is None

    def test_returns_none_for_no_payor_or_payee(self):
        from fppc_form803_client import _normalize_api_record

        result = _normalize_api_record({"filerName": "Test Official"})
        assert result is None

    def test_handles_dollar_sign_and_commas_in_amount(self):
        from fppc_form803_client import _normalize_api_record

        record = {
            "filerName": "Test",
            "payorName": "Corp",
            "payeeName": "Org",
            "amount": "$1,250,000.00",
        }
        result = _normalize_api_record(record)
        assert result["amount"] == 1250000.0

    def test_preserves_metadata(self):
        from fppc_form803_client import _normalize_api_record

        record = {
            "filerName": "Test",
            "payorName": "Corp",
            "payeeName": "Org",
            "agency": "City of Richmond",
            "position": "Mayor",
        }
        result = _normalize_api_record(record)
        assert result["metadata"]["agency"] == "City of Richmond"
        assert result["metadata"]["position"] == "Mayor"


class TestForm803ParseDate:
    """Test date parsing for various FPPC formats."""

    def test_mm_dd_yyyy(self):
        from fppc_form803_client import _parse_date
        assert _parse_date("01/15/2026") == "2026-01-15"

    def test_yyyy_mm_dd(self):
        from fppc_form803_client import _parse_date
        assert _parse_date("2026-01-15") == "2026-01-15"

    def test_full_month_name(self):
        from fppc_form803_client import _parse_date
        assert _parse_date("January 15, 2026") == "2026-01-15"

    def test_returns_none_for_empty(self):
        from fppc_form803_client import _parse_date
        assert _parse_date(None) is None
        assert _parse_date("") is None

    def test_returns_none_for_unparseable(self):
        from fppc_form803_client import _parse_date
        assert _parse_date("not a date") is None


class TestForm803FetchApi:
    """Test the API fetch with mocked responses."""

    @patch("fppc_form803_client._make_request")
    def test_returns_normalized_records(self, mock_request):
        from fppc_form803_client import fetch_behested_payments_api

        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "filerName": "Eduardo Martinez",
                "payorName": "Chevron",
                "payeeName": "Richmond Promise",
                "amount": 50000,
                "paymentDate": "01/15/2026",
                "filingId": "001",
            },
        ]
        mock_request.return_value = mock_resp

        result = fetch_behested_payments_api(agency_name="City of Richmond")
        assert len(result) == 1
        assert result[0]["official_name"] == "Eduardo Martinez"

    @patch("fppc_form803_client._make_request")
    def test_returns_empty_on_api_failure(self, mock_request):
        from fppc_form803_client import fetch_behested_payments_api
        import requests

        mock_request.side_effect = requests.RequestException("API down")
        result = fetch_behested_payments_api(agency_name="City of Richmond")
        assert result == []

    @patch("fppc_form803_client._make_request")
    def test_handles_nested_results_key(self, mock_request):
        from fppc_form803_client import fetch_behested_payments_api

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {
                    "filerName": "Tom Butt",
                    "payorName": "Developer LLC",
                    "payeeName": "Youth Program",
                    "amount": 10000,
                    "filingId": "002",
                },
            ],
        }
        mock_request.return_value = mock_resp

        result = fetch_behested_payments_api()
        assert len(result) == 1
        assert result[0]["official_name"] == "Tom Butt"


class TestForm803FetchMain:
    """Test the main fetch_behested_payments orchestrator."""

    @patch("fppc_form803_client.fetch_behested_payments_api")
    def test_deduplicates_across_agency_names(self, mock_api):
        from fppc_form803_client import fetch_behested_payments

        mock_api.return_value = [
            {
                "official_name": "Test",
                "payor_name": "Corp",
                "payee_name": "Org",
                "source_identifier": "dup-001",
            },
        ]

        # Called once per agency name, but dedup removes duplicates
        result = fetch_behested_payments(city_fips="0660620")
        assert len(result) == 1

    @patch("fppc_form803_client.fetch_behested_payments_api")
    @patch("fppc_form803_client.fetch_behested_payments_html")
    def test_falls_back_to_html_when_api_empty(self, mock_html, mock_api):
        from fppc_form803_client import fetch_behested_payments

        mock_api.return_value = []
        mock_html.return_value = [
            {
                "official_name": "HTML Official",
                "payor_name": "Corp",
                "payee_name": "Org",
                "source_identifier": "html-001",
            },
        ]

        result = fetch_behested_payments(city_fips="0660620")
        assert len(result) >= 1
        mock_html.assert_called()


# ══════════════════════════════════════════════════════════════
# Lobbyist Client Tests
# ══════════════════════════════════════════════════════════════


class TestLobbyistNormalizeTableRecord:
    """Test normalization of HTML table rows."""

    def test_normalizes_standard_record(self):
        from lobbyist_client import _normalize_table_record

        record = {
            "lobbyist": "John Doe",
            "client": "Acme Corp",
            "firm": "Doe Lobbying LLC",
            "registration date": "01/15/2026",
            "topics": "Land Use, Zoning",
            "status": "active",
        }
        result = _normalize_table_record(record, "https://example.com")

        assert result is not None
        assert result["lobbyist_name"] == "John Doe"
        assert result["client_name"] == "Acme Corp"
        assert result["lobbyist_firm"] == "Doe Lobbying LLC"
        assert result["registration_date"] == "2026-01-15"
        assert result["topics"] == "Land Use, Zoning"

    def test_returns_none_for_empty_name(self):
        from lobbyist_client import _normalize_table_record

        assert _normalize_table_record({}, "https://example.com") is None
        assert _normalize_table_record({"lobbyist": ""}, "https://example.com") is None

    def test_handles_alternative_field_names(self):
        from lobbyist_client import _normalize_table_record

        record = {
            "name": "Jane Smith",
            "employer": "Tech Co",
        }
        result = _normalize_table_record(record, "https://example.com")
        assert result["lobbyist_name"] == "Jane Smith"
        assert result["client_name"] == "Tech Co"


class TestLobbyistParseTextSection:
    """Test free-text section parsing."""

    def test_parses_labeled_fields(self):
        from lobbyist_client import _parse_text_section

        text = """
Lobbyist: John Doe
Client: Acme Corporation
Firm: Doe Consulting
Date: 03/15/2026
Topics: Land Use
Phone: 510-555-1234
Email: jdoe@example.com
"""
        result = _parse_text_section(text, "https://example.com")

        assert result is not None
        assert result["lobbyist_name"] == "John Doe"
        assert result["client_name"] == "Acme Corporation"
        assert result["lobbyist_firm"] == "Doe Consulting"
        assert result["lobbyist_phone"] == "510-555-1234"
        assert result["lobbyist_email"] == "jdoe@example.com"

    def test_returns_none_for_no_name(self):
        from lobbyist_client import _parse_text_section

        result = _parse_text_section("Just some random text", "https://example.com")
        assert result is None


class TestLobbyistFetchMain:
    """Test the main fetch orchestrator."""

    @patch("lobbyist_client.fetch_lobbyist_registrations_html")
    @patch("lobbyist_client.fetch_ca_sos_lobbyists")
    def test_combines_local_and_state(self, mock_sos, mock_html):
        from lobbyist_client import fetch_lobbyist_registrations

        mock_html.return_value = [
            {
                "lobbyist_name": "Local Lobbyist",
                "client_name": "Client A",
                "source_identifier": "local-001",
            },
        ]
        mock_sos.return_value = [
            {
                "lobbyist_name": "State Lobbyist",
                "client_name": "Client B",
                "source_identifier": "state-001",
            },
        ]

        result = fetch_lobbyist_registrations(city_fips="0660620")
        assert len(result) == 2

    @patch("lobbyist_client.fetch_lobbyist_registrations_html")
    @patch("lobbyist_client.fetch_ca_sos_lobbyists")
    def test_skips_state_when_disabled(self, mock_sos, mock_html):
        from lobbyist_client import fetch_lobbyist_registrations

        mock_html.return_value = []
        mock_sos.return_value = []

        fetch_lobbyist_registrations(city_fips="0660620", include_state=False)
        mock_sos.assert_not_called()

    @patch("lobbyist_client.fetch_lobbyist_registrations_html")
    @patch("lobbyist_client.fetch_ca_sos_lobbyists")
    def test_deduplicates(self, mock_sos, mock_html):
        from lobbyist_client import fetch_lobbyist_registrations

        dup_record = {
            "lobbyist_name": "Same Person",
            "client_name": "Same Client",
            "source_identifier": "dup-001",
        }
        mock_html.return_value = [dup_record]
        mock_sos.return_value = [{**dup_record, "source": "ca_sos_lobbying"}]

        result = fetch_lobbyist_registrations(city_fips="0660620")
        assert len(result) == 1


# ══════════════════════════════════════════════════════════════
# Database Loading Tests
# ══════════════════════════════════════════════════════════════


class TestLoadBehestedToDb:
    """Test behested payment DB loading."""

    def test_loads_valid_payment(self):
        from db import load_behested_to_db

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        payments = [
            {
                "official_name": "Eduardo Martinez",
                "payor_name": "Chevron",
                "payee_name": "Richmond Promise",
                "amount": 50000,
                "payment_date": "2026-01-15",
                "source_identifier": "803-001",
                "metadata": {},
            },
        ]

        with patch("db.ensure_official", return_value=uuid.uuid4()):
            stats = load_behested_to_db(conn, payments)

        assert stats["loaded"] == 1
        assert stats["skipped"] == 0
        cur.execute.assert_called_once()

    def test_skips_without_source_identifier(self):
        from db import load_behested_to_db

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        payments = [{"official_name": "Test", "source_identifier": ""}]
        stats = load_behested_to_db(conn, payments)
        assert stats["skipped"] == 1
        assert stats["loaded"] == 0

    def test_skips_without_official_name(self):
        from db import load_behested_to_db

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        payments = [{"official_name": "", "source_identifier": "test-001"}]
        stats = load_behested_to_db(conn, payments)
        assert stats["skipped"] == 1

    def test_handles_official_match_failure_gracefully(self):
        from db import load_behested_to_db

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        payments = [
            {
                "official_name": "Unknown Person",
                "payor_name": "Corp",
                "payee_name": "Org",
                "source_identifier": "test-002",
                "metadata": {},
            },
        ]

        with patch("db.ensure_official", side_effect=Exception("Not found")):
            stats = load_behested_to_db(conn, payments)

        # Should still load even if official match fails
        assert stats["loaded"] == 1


class TestLoadLobbyistsToDb:
    """Test lobbyist registration DB loading."""

    def test_loads_valid_registration(self):
        from db import load_lobbyists_to_db

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        registrations = [
            {
                "lobbyist_name": "John Doe",
                "client_name": "Acme Corp",
                "lobbyist_firm": "Doe Consulting",
                "source_identifier": "lobby-001",
                "status": "active",
                "metadata": {},
            },
        ]

        stats = load_lobbyists_to_db(conn, registrations)
        assert stats["loaded"] == 1
        assert stats["skipped"] == 0

    def test_skips_without_source_identifier(self):
        from db import load_lobbyists_to_db

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        registrations = [{"lobbyist_name": "Test", "source_identifier": ""}]
        stats = load_lobbyists_to_db(conn, registrations)
        assert stats["skipped"] == 1

    def test_skips_without_lobbyist_name(self):
        from db import load_lobbyists_to_db

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        registrations = [{"lobbyist_name": "", "source_identifier": "test-001"}]
        stats = load_lobbyists_to_db(conn, registrations)
        assert stats["skipped"] == 1


# ══════════════════════════════════════════════════════════════
# Data Sync Integration Tests
# ══════════════════════════════════════════════════════════════


class TestSyncForm803:
    """Test Form 803 sync function."""

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_form803_registered_in_sync_sources(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import SYNC_SOURCES
        assert "form803_behested" in SYNC_SOURCES

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_form803_sync_via_run_sync(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()

        fake_sync = MagicMock(return_value={
            "records_fetched": 5,
            "records_new": 3,
            "records_updated": 1,
            "records_skipped": 1,
        })

        with patch.dict(SYNC_SOURCES, {"form803_behested": fake_sync}):
            result = run_sync(source="form803_behested", sync_type="full")

        assert result["status"] == "completed"
        assert result["records_fetched"] == 5


class TestSyncLobbyist:
    """Test lobbyist registration sync function."""

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_lobbyist_registered_in_sync_sources(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import SYNC_SOURCES
        assert "lobbyist_registrations" in SYNC_SOURCES

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_lobbyist_sync_via_run_sync(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()

        fake_sync = MagicMock(return_value={
            "records_fetched": 3,
            "records_new": 2,
            "records_updated": 0,
            "records_skipped": 1,
        })

        with patch.dict(SYNC_SOURCES, {"lobbyist_registrations": fake_sync}):
            result = run_sync(source="lobbyist_registrations", sync_type="full")

        assert result["status"] == "completed"
        assert result["records_fetched"] == 3


# ══════════════════════════════════════════════════════════════
# City Config Tests
# ══════════════════════════════════════════════════════════════


class TestCityConfig:
    """Test that new data sources are registered in city config."""

    def test_form803_in_richmond_config(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        assert "form803_behested" in cfg["data_sources"]
        assert cfg["data_sources"]["form803_behested"]["credibility_tier"] == 1

    def test_lobbyist_in_richmond_config(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        assert "lobbyist_registrations" in cfg["data_sources"]
        assert cfg["data_sources"]["lobbyist_registrations"]["credibility_tier"] == 1


# ══════════════════════════════════════════════════════════════
# Staleness Monitor Tests
# ══════════════════════════════════════════════════════════════


class TestStalenessMonitor:
    """Test that new sources are monitored."""

    def test_form803_in_freshness_thresholds(self):
        from staleness_monitor import FRESHNESS_THRESHOLDS
        assert "form803_behested" in FRESHNESS_THRESHOLDS
        assert FRESHNESS_THRESHOLDS["form803_behested"] == 90

    def test_lobbyist_in_freshness_thresholds(self):
        from staleness_monitor import FRESHNESS_THRESHOLDS
        assert "lobbyist_registrations" in FRESHNESS_THRESHOLDS
        assert FRESHNESS_THRESHOLDS["lobbyist_registrations"] == 90

    def test_tables_in_schema_health(self):
        from staleness_monitor import EXPECTED_TABLES
        assert "044_behested_payments_lobbyists" in EXPECTED_TABLES
        tables = EXPECTED_TABLES["044_behested_payments_lobbyists"]
        assert "behested_payments" in tables
        assert "lobbyist_registrations" in tables
