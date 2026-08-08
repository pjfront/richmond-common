"""Tests for FPPC Form 803 (behested payments) and lobbyist registration pipelines.

Sprint 13.1 (Form 803) and Sprint 13.3 (Lobbyist Registrations).
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════
# FPPC Form 803 Client Tests
# ══════════════════════════════════════════════════════════════


class TestForm803NormalizeApiRecord:
    """Test normalization of FPPC records (API-style dicts and XLS rows)."""

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

    def test_handles_xls_field_names(self):
        """XLS rows use Official, payor, payee, payorcity etc."""
        from fppc_form803_client import _normalize_api_record

        record = {
            "Official": "Buffy Wicks",
            "payor": "AT&T",
            "payee": "Richmond District Neighborhood Center",
            "payorcity": "Sacramento",
            "payeecity": "San Francisco",
            "payeestate": "CA",
            "amount": 5000.0,
            "OfficialType": "Assembly",
            "LgcPurpose": "Charitable",
            "PaymentYear": 2019.0,
            "_date_from_serial": "2019-07-10",
        }
        result = _normalize_api_record(record)

        assert result["official_name"] == "Buffy Wicks"
        assert result["payor_name"] == "AT&T"
        assert result["payee_name"] == "Richmond District Neighborhood Center"
        assert result["payor_city"] == "Sacramento"
        assert result["amount"] == 5000.0
        assert result["payment_date"] == "2019-07-10"
        assert result["metadata"]["position"] == "Assembly"
        assert result["metadata"]["lgc_purpose"] == "Charitable"

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


class TestForm803ExcelDate:
    """Test Excel serial date conversion."""

    def test_converts_known_date(self):
        from fppc_form803_client import _excel_serial_to_date

        # 42774 = 2017-02-08 (verified from XLS data)
        result = _excel_serial_to_date(42774)
        assert result == "2017-02-08"

    def test_converts_recent_date(self):
        from fppc_form803_client import _excel_serial_to_date

        # 45135 = 2023-07-18 (approx)
        result = _excel_serial_to_date(45135)
        assert result is not None
        assert result.startswith("2023-")

    def test_returns_none_for_zero(self):
        from fppc_form803_client import _excel_serial_to_date
        assert _excel_serial_to_date(0) is None
        assert _excel_serial_to_date(None) is None

    def test_handles_float_serial(self):
        from fppc_form803_client import _excel_serial_to_date
        result = _excel_serial_to_date(42774.0)
        assert result == "2017-02-08"


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


class TestForm803FetchXls:
    """Test the XLS download and parse with mocked responses."""

    @patch("fppc_form803_client._make_request")
    def test_filters_by_city_name(self, mock_request):
        """Mock an XLS workbook and verify city filtering."""
        import xlrd as real_xlrd
        from fppc_form803_client import fetch_behested_payments_xls

        mock_resp = MagicMock()
        mock_resp.content = b"fake xls data"
        mock_request.return_value = mock_resp

        mock_ws = MagicMock()
        mock_ws.nrows = 3  # header + 2 data rows
        mock_ws.ncols = 12
        headers = [
            "Official", "OfficialType", "DateOFPayment", "payor",
            "payorcity", "payee", "payeecity", "payeestate",
            "amount", "description", "LgcPurpose", "PaymentYear",
        ]

        def cell_value(r, c):
            if r == 0:
                return headers[c]
            elif r == 1:
                # Richmond CA match (payeecity = Richmond, payeestate = CA)
                return [
                    "Wicks, Buffy", "Assembly", 43837.0,
                    "Women in California Leadership", "Sacramento",
                    "Girls, Inc. WCCC", "Richmond", "CA",
                    2500.0, "Donation to nonprofit", "Charitable", 2020.0,
                ][c]
            else:
                # Non-Richmond row (payeecity = Sacramento)
                return [
                    "Smith, John", "Senate", 42900.0,
                    "Some Corp", "Sacramento",
                    "Some Org", "Sacramento", "CA",
                    10000.0, "Event", "Legislative", 2017.0,
                ][c]

        mock_ws.cell_value = cell_value

        mock_wb = MagicMock()
        mock_wb.sheet_by_index.return_value = mock_ws

        # xlrd is installed, so patch open_workbook directly
        with patch("xlrd.open_workbook", return_value=mock_wb):
            results = fetch_behested_payments_xls(city_names=["richmond"])

        assert len(results) == 1
        assert results[0]["official_name"] == "Wicks, Buffy"
        assert results[0]["payee_name"] == "Girls, Inc. WCCC"
        assert results[0]["amount"] == 2500.0

    @patch("fppc_form803_client._make_request")
    def test_returns_empty_on_download_failure(self, mock_request):
        from fppc_form803_client import fetch_behested_payments_xls
        import requests

        mock_request.side_effect = requests.RequestException("Download failed")
        result = fetch_behested_payments_xls()
        assert result == []


class TestForm803FetchMain:
    """Test the main fetch_behested_payments orchestrator."""

    @patch("fppc_form803_client.fetch_behested_payments_xls")
    def test_deduplicates(self, mock_xls):
        from fppc_form803_client import fetch_behested_payments

        mock_xls.return_value = [
            {
                "official_name": "Test",
                "payor_name": "Corp",
                "payee_name": "Org",
                "source_identifier": "dup-001",
                "payment_date": "2024-01-01",
            },
            {
                "official_name": "Test",
                "payor_name": "Corp",
                "payee_name": "Org",
                "source_identifier": "dup-001",
                "payment_date": "2024-01-01",
            },
        ]

        result = fetch_behested_payments(city_fips="0660620")
        assert len(result) == 1

    @patch("fppc_form803_client.fetch_behested_payments_xls")
    def test_filters_by_official_name(self, mock_xls):
        from fppc_form803_client import fetch_behested_payments

        mock_xls.return_value = [
            {
                "official_name": "Buffy Wicks",
                "payor_name": "Corp",
                "payee_name": "Org",
                "source_identifier": "001",
                "payment_date": "2024-01-01",
            },
            {
                "official_name": "Nancy Skinner",
                "payor_name": "Corp2",
                "payee_name": "Org2",
                "source_identifier": "002",
                "payment_date": "2024-06-01",
            },
        ]

        result = fetch_behested_payments(
            city_fips="0660620", official_name="Wicks",
        )
        assert len(result) == 1
        assert result[0]["official_name"] == "Buffy Wicks"

    @patch("fppc_form803_client.fetch_behested_payments_xls")
    def test_filters_by_date_range(self, mock_xls):
        from fppc_form803_client import fetch_behested_payments

        mock_xls.return_value = [
            {
                "official_name": "Test",
                "payor_name": "Corp",
                "payee_name": "Org",
                "source_identifier": "001",
                "payment_date": "2023-01-01",
            },
            {
                "official_name": "Test",
                "payor_name": "Corp",
                "payee_name": "Org",
                "source_identifier": "002",
                "payment_date": "2024-06-01",
            },
        ]

        result = fetch_behested_payments(
            city_fips="0660620", start_date="2024-01-01",
        )
        assert len(result) == 1
        assert result[0]["payment_date"] == "2024-06-01"


# ══════════════════════════════════════════════════════════════
# Lobbyist Client Tests
# ══════════════════════════════════════════════════════════════


class TestLobbyistFetchMain:
    """Test the main fetch orchestrator."""

    @patch("lobbyist_client.fetch_lobbyist_registrations_pdf")
    @patch("lobbyist_client.fetch_ca_sos_lobbyists")
    def test_combines_local_and_state(self, mock_sos, mock_pdf):
        from lobbyist_client import fetch_lobbyist_registrations

        mock_pdf.return_value = (
            [
                {
                    "lobbyist_name": "Local Lobbyist",
                    "client_name": "Client A",
                    "source_identifier": "doc_75427_Local Lobbyist",
                },
            ],
            {
                "retryable_incomplete": False,
                "required_source_incomplete": False,
                "incomplete_reasons": [],
            },
        )
        mock_sos.return_value = [
            {
                "lobbyist_name": "State Lobbyist",
                "client_name": "Client B",
                "source_identifier": "ca_sos_State Lobbyist_Client B",
            },
        ]

        result = fetch_lobbyist_registrations(city_fips="0660620")
        assert len(result) == 2

    @patch("lobbyist_client.fetch_lobbyist_registrations_pdf")
    @patch("lobbyist_client.fetch_ca_sos_lobbyists")
    def test_skips_state_when_disabled(self, mock_sos, mock_pdf):
        from lobbyist_client import fetch_lobbyist_registrations

        mock_pdf.return_value = (
            [],
            {
                "retryable_incomplete": False,
                "required_source_incomplete": False,
                "incomplete_reasons": [],
            },
        )
        mock_sos.return_value = []

        fetch_lobbyist_registrations(city_fips="0660620", include_state=False)
        mock_sos.assert_not_called()

    @patch("lobbyist_client.fetch_lobbyist_registrations_pdf")
    @patch("lobbyist_client.fetch_ca_sos_lobbyists")
    def test_deduplicates(self, mock_sos, mock_pdf):
        from lobbyist_client import fetch_lobbyist_registrations

        dup_record = {
            "lobbyist_name": "Same Person",
            "client_name": "Same Client",
            "source_identifier": "dup-001",
        }
        mock_pdf.return_value = (
            [dup_record],
            {
                "retryable_incomplete": False,
                "required_source_incomplete": False,
                "incomplete_reasons": [],
            },
        )
        mock_sos.return_value = [{**dup_record, "source": "ca_sos_lobbying"}]

        result = fetch_lobbyist_registrations(city_fips="0660620")
        assert len(result) == 1


# ══════════════════════════════════════════════════════════════
# Database Loading Tests
# ══════════════════════════════════════════════════════════════


class TestLoadBehestedToDb:
    """Test behested payment DB loading."""

    def _make_mock(self, fetchone_results=None):
        """Mock conn + cursor; fetchone returns (True,) by default (insert path)."""
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        if fetchone_results is not None:
            cur.fetchone.side_effect = fetchone_results
        else:
            cur.fetchone.return_value = (True,)
        return conn, cur

    def test_loads_valid_payment(self):
        from db import load_behested_to_db

        conn, cur = self._make_mock()

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

        with patch("db.officials.ensure_official", return_value=uuid.uuid4()):
            stats = load_behested_to_db(conn, payments)

        assert stats["inserted"] == 1
        assert stats["updated"] == 0
        assert stats["skipped"] == 0
        cur.execute.assert_called_once()

    def test_on_conflict_path_increments_updated(self):
        """Same payment loaded twice → second hits ON CONFLICT → updated += 1."""
        from db import load_behested_to_db

        conn, _ = self._make_mock(fetchone_results=[(True,), (False,)])

        payments = [
            {
                "official_name": "Eduardo Martinez",
                "payor_name": "Chevron",
                "amount": 50000,
                "source_identifier": "803-001",
                "metadata": {},
            },
            {
                "official_name": "Eduardo Martinez",
                "payor_name": "Chevron",
                "amount": 50000,
                "source_identifier": "803-001",  # same key
                "metadata": {},
            },
        ]

        with patch("db.officials.ensure_official", return_value=uuid.uuid4()):
            stats = load_behested_to_db(conn, payments)

        assert stats["inserted"] == 1
        assert stats["updated"] == 1
        assert stats["skipped"] == 0
        # Counter invariant
        assert stats["inserted"] + stats["updated"] + stats["skipped"] == len(payments)

    def test_skips_without_source_identifier(self):
        from db import load_behested_to_db

        conn, _ = self._make_mock()

        payments = [{"official_name": "Test", "source_identifier": ""}]
        stats = load_behested_to_db(conn, payments)
        assert stats["skipped"] == 1
        assert stats["inserted"] == 0
        assert stats["updated"] == 0

    def test_skips_without_official_name(self):
        from db import load_behested_to_db

        conn, _ = self._make_mock()

        payments = [{"official_name": "", "source_identifier": "test-001"}]
        stats = load_behested_to_db(conn, payments)
        assert stats["skipped"] == 1

    def test_handles_official_match_failure_gracefully(self):
        from db import load_behested_to_db

        conn, _ = self._make_mock()

        payments = [
            {
                "official_name": "Unknown Person",
                "payor_name": "Corp",
                "payee_name": "Org",
                "source_identifier": "test-002",
                "metadata": {},
            },
        ]

        with patch("db.officials.ensure_official", side_effect=Exception("Not found")):
            stats = load_behested_to_db(conn, payments)

        # Should still load even if official match fails
        assert stats["inserted"] == 1


class TestLobbyistPdfPipeline:
    """Test PDF download + Vision extraction pipeline for lobbyist registrations."""

    @staticmethod
    def _sample_pdf_bytes() -> bytes:
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Lobbyist registration grid")
        data = doc.tobytes()
        doc.close()
        return data

    def test_extraction_prompt_is_file_backed_and_content_versioned(self):
        import hashlib
        from lobbyist_client import (
            EXTRACTION_PROMPT,
            EXTRACTION_PROMPT_VERSION,
            _EXTRACTION_PROMPT_PATH,
        )

        assert EXTRACTION_PROMPT == _EXTRACTION_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()
        assert EXTRACTION_PROMPT_VERSION == hashlib.sha256(
            EXTRACTION_PROMPT.encode("utf-8")
        ).hexdigest()

    def test_renders_pdf_as_openai_image_blocks(self):
        from lobbyist_client import _render_pdf_image_blocks

        blocks = _render_pdf_image_blocks(self._sample_pdf_bytes())

        assert len(blocks) == 1
        assert blocks[0]["type"] == "image_url"
        assert blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_vision_extraction_uses_optional_kimi_route(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import extract_lobbyists_from_pdf

        monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [
            MagicMock(
                type="text",
                text='[{"name":"Test Firm","years":[2025]}]',
            )
        ]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 20

        with patch("lobbyist_client.LLMClient") as mock_client_cls:
            mock_client_cls.return_value.messages.create.return_value = mock_response
            result = extract_lobbyists_from_pdf(
                self._sample_pdf_bytes(), doc_id=75427
            )

        assert result == [{"name": "Test Firm", "years": [2025]}]
        kwargs = mock_client_cls.return_value.messages.create.call_args.kwargs
        assert kwargs["model"] == VISION_MODEL
        assert kwargs["thinking"] == {"type": "disabled"}
        assert "temperature" not in kwargs
        assert any(
            block.get("type") == "image_url"
            for block in kwargs["messages"][0]["content"]
        )

    def test_vision_extraction_skips_when_optional_key_is_absent(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import extract_lobbyists_from_pdf

        monkeypatch.delenv(get_model_route(VISION_MODEL).api_key_env, raising=False)
        with patch("lobbyist_client.LLMClient") as mock_client_cls:
            assert extract_lobbyists_from_pdf(b"not opened", doc_id=75427) == []
        mock_client_cls.assert_not_called()

    def test_vision_extraction_rejects_truncated_response(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import (
            LobbyistVisionOutputError,
            extract_lobbyists_from_pdf,
        )

        monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
        response = MagicMock(
            stop_reason="max_tokens",
            content=[MagicMock(type="text", text="[]")],
        )
        with patch("lobbyist_client.LLMClient") as client_cls:
            client_cls.return_value.messages.create.return_value = response
            with pytest.raises(LobbyistVisionOutputError, match="max_tokens"):
                extract_lobbyists_from_pdf(self._sample_pdf_bytes(), 75427)

    def test_vision_extraction_rejects_nontext_result(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import (
            LobbyistVisionOutputError,
            extract_lobbyists_from_pdf,
        )

        monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
        response = MagicMock(
            stop_reason="end_turn",
            content=[MagicMock(type="tool_use", text=None)],
        )
        with patch("lobbyist_client.LLMClient") as client_cls:
            client_cls.return_value.messages.create.return_value = response
            with pytest.raises(LobbyistVisionOutputError, match="exclusive text"):
                extract_lobbyists_from_pdf(self._sample_pdf_bytes(), 75427)

    def test_parse_vision_response_valid_json(self):
        from lobbyist_client import _parse_vision_response

        response = '[{"name": "Chevron U.S.A", "years": [2014, 2015, 2020]}, {"name": "Zell & Associates", "years": [2014, 2015, 2016]}]'
        result = _parse_vision_response(response, doc_id=75427)

        assert len(result) == 2
        assert result[0]["name"] == "Chevron U.S.A"
        assert result[0]["years"] == [2014, 2015, 2020]
        assert result[1]["name"] == "Zell & Associates"
        assert result[1]["years"] == [2014, 2015, 2016]

    def test_parse_vision_response_strips_markdown_fences(self):
        from lobbyist_client import _parse_vision_response

        response = '```json\n[{"name": "PG&E", "years": [2022]}]\n```'
        result = _parse_vision_response(response, doc_id=75427)

        assert len(result) == 1
        assert result[0]["name"] == "PG&E"

    def test_parse_vision_response_empty_array(self):
        from lobbyist_client import _parse_vision_response

        result = _parse_vision_response("[]", doc_id=75427)
        assert result == []

    def test_parse_vision_response_invalid_json(self):
        from lobbyist_client import LobbyistVisionOutputError, _parse_vision_response

        with pytest.raises(LobbyistVisionOutputError, match="not valid JSON"):
            _parse_vision_response("not valid json", doc_id=75427)

    def test_parse_vision_response_skips_empty_names(self):
        from lobbyist_client import LobbyistVisionOutputError, _parse_vision_response

        response = '[{"name": "", "years": [2020]}, {"name": "Valid Corp", "years": [2020]}]'
        with pytest.raises(LobbyistVisionOutputError, match="empty name"):
            _parse_vision_response(response, doc_id=75427)

    def test_parse_vision_response_filters_invalid_years(self):
        from lobbyist_client import LobbyistVisionOutputError, _parse_vision_response

        response = '[{"name": "Test", "years": [2020, -1, 9999, "bad", 2021]}]'
        with pytest.raises(LobbyistVisionOutputError, match="invalid year"):
            _parse_vision_response(response, doc_id=75427)

    @pytest.mark.parametrize(
        "response",
        [
            "{}",
            '["not-an-object"]',
            '[{"name": 7, "years": [2020]}]',
            '[{"name": "Firm", "years": "2020"}]',
            '[{"name": "Firm", "years": []}]',
            '[{"name": "Firm", "years": [true]}]',
        ],
    )
    def test_parse_vision_response_rejects_malformed_rows(self, response):
        from lobbyist_client import LobbyistVisionOutputError, _parse_vision_response

        with pytest.raises(LobbyistVisionOutputError):
            _parse_vision_response(response, doc_id=75427)

    def test_parse_vision_response_merges_duplicate_names(self):
        from lobbyist_client import _parse_vision_response

        result = _parse_vision_response(
            '[{"name":"Firm A","years":[2020]},'
            '{"name":"Firm A","years":[2021,2020]}]',
            doc_id=75427,
        )
        assert result == [{"name": "Firm A", "years": [2020, 2021]}]

    def test_vision_records_to_registrations_active(self):
        from lobbyist_client import _vision_records_to_registrations
        from datetime import datetime

        current_year = datetime.now().year
        records = [{"name": "Council of Industries", "years": [2020, 2021, current_year]}]

        result = _vision_records_to_registrations(records, doc_id=75427, source_url="https://example.com/doc")

        assert len(result) == 1
        reg = result[0]
        assert reg["lobbyist_name"] == "Council of Industries"
        assert reg["status"] == "active"
        assert reg["source_identifier"] == "doc_75427_Council of Industries"
        assert reg["metadata"]["years_registered"] == [2020, 2021, current_year]
        assert reg["registration_date"] == "2020-01-01"
        assert reg["expiration_date"] is None  # Still active

    def test_vision_records_to_registrations_expired(self):
        from lobbyist_client import _vision_records_to_registrations

        records = [{"name": "Old Firm LLC", "years": [2010, 2011]}]

        result = _vision_records_to_registrations(records, doc_id=27460, source_url="https://example.com/doc")

        assert len(result) == 1
        reg = result[0]
        assert reg["status"] == "expired"
        assert reg["expiration_date"] == "2011-12-31"

    def test_vision_records_to_registrations_has_required_fields(self):
        from lobbyist_client import _vision_records_to_registrations

        records = [{"name": "Test Lobbyist", "years": [2024]}]
        result = _vision_records_to_registrations(records, doc_id=75427, source_url="https://example.com")

        reg = result[0]
        # Required by load_lobbyists_to_db
        assert reg["lobbyist_name"]
        assert reg["source_identifier"]
        assert reg["client_name"]

    def test_download_lobbyist_pdf_validates_pdf(self):
        from lobbyist_client import download_lobbyist_pdf

        with patch("lobbyist_client._make_request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.content = b"not a pdf"
            mock_resp.headers = {"content-type": "text/html"}
            mock_req.return_value = mock_resp

            with pytest.raises(ValueError, match="not a PDF"):
                download_lobbyist_pdf(75427)

    def test_download_lobbyist_pdf_accepts_valid_pdf(self):
        from lobbyist_client import download_lobbyist_pdf

        with patch("lobbyist_client._make_request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.content = b"%PDF-1.4 fake pdf content"
            mock_resp.headers = {"content-type": "application/pdf"}
            mock_req.return_value = mock_resp

            result = download_lobbyist_pdf(75427)
            assert result == b"%PDF-1.4 fake pdf content"

    @patch("lobbyist_client.extract_lobbyists_from_pdf")
    @patch("lobbyist_client.download_lobbyist_pdf")
    def test_fetch_lobbyist_registrations_pdf_end_to_end(
        self, mock_download, mock_extract, monkeypatch
    ):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import fetch_lobbyist_registrations_pdf

        monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
        mock_download.return_value = b"%PDF-1.4 fake"
        mock_extract.return_value = [
            {"name": "Chevron U.S.A", "years": [2014, 2015]},
            {"name": "PG&E", "years": [2020]},
        ]

        with patch(
            "lobbyist_client._load_extraction_receipt", return_value=None
        ), patch("lobbyist_client._persist_extraction_receipt"):
            result = fetch_lobbyist_registrations_pdf(conn=MagicMock())

        # Should call download + extract for each doc ID in config
        assert mock_download.call_count >= 1
        assert mock_extract.call_count >= 1
        assert len(result) >= 2

        # Check registration structure
        names = [r["lobbyist_name"] for r in result]
        assert "Chevron U.S.A" in names
        assert "PG&E" in names

    def test_cached_receipt_avoids_repeat_paid_extraction(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import fetch_lobbyist_registrations_pdf

        monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
        records = [{"name": "Cached Firm", "years": [2024]}]
        with patch(
            "lobbyist_client._resolve_config",
            return_value=({"document_ids": [75427]}, "0660620"),
        ), patch(
            "lobbyist_client.download_lobbyist_pdf",
            return_value=b"%PDF-cached",
        ), patch(
            "lobbyist_client._load_extraction_receipt",
            return_value=records,
        ) as load_receipt, patch(
            "lobbyist_client.extract_lobbyists_from_pdf"
        ) as extract, patch(
            "lobbyist_client._persist_extraction_receipt"
        ) as persist:
            result = fetch_lobbyist_registrations_pdf(conn=MagicMock())

        assert result[0]["lobbyist_name"] == "Cached Firm"
        assert load_receipt.call_args.kwargs["content_sha256"]
        extract.assert_not_called()
        persist.assert_not_called()

    def test_prompt_version_change_invalidates_cached_contract(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        import lobbyist_client

        monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
        monkeypatch.setattr(
            lobbyist_client,
            "EXTRACTION_PROMPT_VERSION",
            "lobbyist-grid-next-version",
        )

        def load_for_contract(_conn, **kwargs):
            assert kwargs["prompt_version"] == "lobbyist-grid-next-version"
            return None

        with patch(
            "lobbyist_client._resolve_config",
            return_value=({"document_ids": [75427]}, "0660620"),
        ), patch(
            "lobbyist_client.download_lobbyist_pdf", return_value=b"%PDF-same-hash"
        ), patch(
            "lobbyist_client._load_extraction_receipt",
            side_effect=load_for_contract,
        ), patch(
            "lobbyist_client.extract_lobbyists_from_pdf",
            return_value=[{"name": "Fresh Firm", "years": [2025]}],
        ) as extract, patch("lobbyist_client._persist_extraction_receipt") as persist:
            result = lobbyist_client.fetch_lobbyist_registrations_pdf(
                conn=MagicMock()
            )

        assert result[0]["lobbyist_name"] == "Fresh Firm"
        extract.assert_called_once()
        assert (
            persist.call_args.kwargs["prompt_version"]
            == "lobbyist-grid-next-version"
        )

    def test_valid_empty_result_is_durably_receipted(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import fetch_lobbyist_registrations_pdf

        monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
        with patch(
            "lobbyist_client._resolve_config",
            return_value=({"document_ids": [75427]}, "0660620"),
        ), patch(
            "lobbyist_client.download_lobbyist_pdf", return_value=b"%PDF-empty"
        ), patch(
            "lobbyist_client._load_extraction_receipt", return_value=None
        ), patch(
            "lobbyist_client.extract_lobbyists_from_pdf", return_value=[]
        ) as extract, patch(
            "lobbyist_client._persist_extraction_receipt"
        ) as persist:
            assert fetch_lobbyist_registrations_pdf(conn=MagicMock()) == []

        extract.assert_called_once()
        assert persist.call_args.kwargs["records"] == []

    def test_receipt_read_failure_prevents_paid_extraction(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import (
            LobbyistExtractionReceiptError,
            fetch_lobbyist_registrations_pdf,
        )

        monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
        with patch(
            "lobbyist_client._resolve_config",
            return_value=({"document_ids": [75427]}, "0660620"),
        ), patch(
            "lobbyist_client.download_lobbyist_pdf", return_value=b"%PDF-new"
        ), patch(
            "lobbyist_client._load_extraction_receipt",
            side_effect=LobbyistExtractionReceiptError("migration missing"),
        ), patch(
            "lobbyist_client.extract_lobbyists_from_pdf"
        ) as extract:
            with pytest.raises(LobbyistExtractionReceiptError):
                fetch_lobbyist_registrations_pdf(conn=MagicMock())
        extract.assert_not_called()

    def test_lobbyist_receipt_migration_is_private_and_provenanced(self):
        from pathlib import Path

        root = Path(__file__).parent.parent
        source = (
            root / "src" / "migrations" / "131_lobbyist_document_extractions.sql"
        ).read_text(encoding="utf-8")
        mirror = (
            root
            / "supabase"
            / "migrations"
            / "20260807013100_lobbyist_document_extractions.sql"
        ).read_text(encoding="utf-8")
        assert source == mirror
        for field in (
            "source_url",
            "extracted_at",
            "source_tier",
            "confidence_score",
            "ai_generated",
        ):
            assert field in source
        assert "TO service_role" in source
        assert "TO anon" not in source
        assert "prompt_version" in source
        assert "extraction_model" in source
        assert "extraction_provider" in source

    def test_missing_key_is_explicitly_incomplete_not_valid_zero(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import fetch_lobbyist_registrations_pdf

        monkeypatch.delenv(get_model_route(VISION_MODEL).api_key_env, raising=False)
        records, status = fetch_lobbyist_registrations_pdf(include_status=True)
        assert records == []
        assert status["retryable_incomplete"] is True
        assert status["required_source_incomplete"] is True
        assert "not configured" in status["incomplete_reasons"][0]

    def test_download_failure_is_explicitly_incomplete(self, monkeypatch):
        from llm_client import VISION_MODEL, get_model_route
        from lobbyist_client import fetch_lobbyist_registrations_pdf

        monkeypatch.setenv(get_model_route(VISION_MODEL).api_key_env, "test-key")
        with patch(
            "lobbyist_client._resolve_config",
            return_value=({"document_ids": [75427]}, "0660620"),
        ), patch(
            "lobbyist_client.download_lobbyist_pdf",
            side_effect=ValueError("bad PDF"),
        ):
            records, status = fetch_lobbyist_registrations_pdf(
                conn=MagicMock(), include_status=True
            )
        assert records == []
        assert status["required_source_incomplete"] is True
        assert "75427" in status["incomplete_reasons"][0]

    def test_resolve_config_uses_city_config(self):
        from lobbyist_client import _resolve_config

        config, fips = _resolve_config("0660620")
        assert fips == "0660620"
        assert "document_ids" in config
        assert 75427 in config["document_ids"]

    def test_resolve_config_falls_back_to_defaults(self):
        from lobbyist_client import _resolve_config, RICHMOND_LOBBYIST_DOCS

        config, fips = _resolve_config(None)
        assert fips == "0660620"
        assert "document_ids" in config
        assert set(config["document_ids"]) == set(RICHMOND_LOBBYIST_DOCS.keys())


class TestLoadLobbyistsToDb:
    """Test lobbyist registration DB loading."""

    def _make_mock(self, fetchone_results=None):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        if fetchone_results is not None:
            cur.fetchone.side_effect = fetchone_results
        else:
            cur.fetchone.return_value = (True,)
        return conn, cur

    def test_loads_valid_registration(self):
        from db import load_lobbyists_to_db

        conn, _ = self._make_mock()

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
        assert stats["inserted"] == 1
        assert stats["updated"] == 0
        assert stats["skipped"] == 0

    def test_on_conflict_path_increments_updated(self):
        """Same registration loaded twice → second hits ON CONFLICT → updated += 1."""
        from db import load_lobbyists_to_db

        conn, _ = self._make_mock(fetchone_results=[(True,), (False,)])

        registrations = [
            {
                "lobbyist_name": "John Doe",
                "client_name": "Acme Corp",
                "source_identifier": "lobby-001",
                "metadata": {},
            },
            {
                "lobbyist_name": "John Doe",
                "client_name": "Acme Corp Updated",  # new client name
                "source_identifier": "lobby-001",  # same key
                "metadata": {},
            },
        ]

        stats = load_lobbyists_to_db(conn, registrations)
        assert stats["inserted"] == 1
        assert stats["updated"] == 1
        # Counter invariant
        assert stats["inserted"] + stats["updated"] + stats["skipped"] == len(registrations)

    def test_skips_without_source_identifier(self):
        from db import load_lobbyists_to_db

        conn, _ = self._make_mock()

        registrations = [{"lobbyist_name": "Test", "source_identifier": ""}]
        stats = load_lobbyists_to_db(conn, registrations)
        assert stats["skipped"] == 1
        assert stats["inserted"] == 0

    def test_skips_without_lobbyist_name(self):
        from db import load_lobbyists_to_db

        conn, _ = self._make_mock()

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

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_required_city_clerk_gap_cannot_report_green_completion(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import SYNC_SOURCES, run_sync

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(
            return_value={
                # State-level records may have loaded, but the primary local
                # source is still incomplete and must keep the sync red.
                "records_fetched": 2,
                "records_new": 2,
                "records_updated": 0,
                "retryable_incomplete": True,
                "required_source_incomplete": True,
                "incomplete_reasons": ["City Clerk document download failed"],
            }
        )

        with patch.dict(SYNC_SOURCES, {"lobbyist_registrations": fake_sync}):
            result = run_sync(source="lobbyist_registrations", sync_type="full")

        assert result["status"] == "failed"
        assert "Required source sync is incomplete" in result["error"]


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
        assert "document_ids" in cfg["data_sources"]["lobbyist_registrations"]
        assert 75427 in cfg["data_sources"]["lobbyist_registrations"]["document_ids"]


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
