"""Tests for CAL-ACCESS EXPN_CD (independent expenditures) parser."""
import csv
import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ── Sample EXPN_CD data ──────────────────────────────────────

EXPN_HEADER = [
    "FILING_ID", "AMEND_ID", "LINE_ITEM", "FORM_TYPE",
    "TRAN_ID", "AMOUNT", "EXPN_DATE", "EXPN_DSCR", "EXPN_CODE",
    "CAND_NAML", "CAND_NAMF", "CAND_NAMS", "CAND_NAMT",
    "SUP_OPP_CD", "PAYEE_NAML", "PAYEE_NAMF",
]

SAMPLE_ROWS = [
    # Row 1: Chevron PAC supporting a candidate
    {
        "FILING_ID": "F001",
        "AMEND_ID": "0",
        "LINE_ITEM": "1",
        "FORM_TYPE": "F461",
        "TRAN_ID": "T001",
        "AMOUNT": "50000.00",
        "EXPN_DATE": "10/15/2014 12:00:00 AM",
        "EXPN_DSCR": "Mailer supporting candidate",
        "EXPN_CODE": "LIT",
        "CAND_NAML": "Butt",
        "CAND_NAMF": "Tom",
        "CAND_NAMS": "",
        "CAND_NAMT": "",
        "SUP_OPP_CD": "S",
        "PAYEE_NAML": "Political Printing Co",
        "PAYEE_NAMF": "",
    },
    # Row 2: Same committee opposing a different candidate
    {
        "FILING_ID": "F001",
        "AMEND_ID": "0",
        "LINE_ITEM": "2",
        "FORM_TYPE": "F461",
        "TRAN_ID": "T002",
        "AMOUNT": "75000.00",
        "EXPN_DATE": "10/20/2014 12:00:00 AM",
        "EXPN_DSCR": "TV ad opposing candidate",
        "EXPN_CODE": "TEL",
        "CAND_NAML": "Martinez",
        "CAND_NAMF": "Eduardo",
        "CAND_NAMS": "",
        "CAND_NAMT": "",
        "SUP_OPP_CD": "O",
        "PAYEE_NAML": "Bay Area Media Group",
        "PAYEE_NAMF": "",
    },
    # Row 3: Below minimum amount
    {
        "FILING_ID": "F001",
        "AMEND_ID": "0",
        "LINE_ITEM": "3",
        "FORM_TYPE": "F461",
        "TRAN_ID": "T003",
        "AMOUNT": "50.00",
        "EXPN_DATE": "10/25/2014 12:00:00 AM",
        "EXPN_DSCR": "Filing fee",
        "EXPN_CODE": "FIL",
        "CAND_NAML": "",
        "CAND_NAMF": "",
        "CAND_NAMS": "",
        "CAND_NAMT": "",
        "SUP_OPP_CD": "",
        "PAYEE_NAML": "City Clerk",
        "PAYEE_NAMF": "",
    },
    # Row 4: Non-Richmond filing (should be filtered by filing_map)
    {
        "FILING_ID": "F999",
        "AMEND_ID": "0",
        "LINE_ITEM": "1",
        "FORM_TYPE": "F461",
        "TRAN_ID": "T004",
        "AMOUNT": "100000.00",
        "EXPN_DATE": "11/01/2014 12:00:00 AM",
        "EXPN_DSCR": "Statewide campaign",
        "EXPN_CODE": "LIT",
        "CAND_NAML": "Newsom",
        "CAND_NAMF": "Gavin",
        "CAND_NAMS": "",
        "CAND_NAMT": "",
        "SUP_OPP_CD": "S",
        "PAYEE_NAML": "Statewide Printing",
        "PAYEE_NAMF": "",
    },
]

SAMPLE_FILING_MAP = {
    "F001": {
        "filer_id": "1234567",
        "name": "Coalition for Richmond's Future (Chevron)",
        "form_type": "F461",
    },
}


def _make_mock_zip(rows: list[dict]) -> Path:
    """Create an in-memory ZIP with a mock EXPN_CD.TSV."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        tsv_buf = io.StringIO()
        writer = csv.DictWriter(tsv_buf, fieldnames=EXPN_HEADER, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        zf.writestr("CalAccess/DATA/EXPN_CD.TSV", tsv_buf.getvalue())
    buf.seek(0)
    return buf


class TestGetRichmondExpenditures:
    """Tests for get_richmond_expenditures parser."""

    def test_basic_extraction(self, tmp_path):
        """Extracts expenditures matching filing_map."""
        from calaccess_client import get_richmond_expenditures

        zip_buf = _make_mock_zip(SAMPLE_ROWS)
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        results = get_richmond_expenditures(
            zip_file, min_amount=100, filing_map=SAMPLE_FILING_MAP
        )
        assert len(results) == 2  # Rows 1 and 2 (row 3 below min, row 4 wrong filing)

    def test_candidate_name_assembled(self, tmp_path):
        """Candidate name built from CAND_NAMF + CAND_NAML."""
        from calaccess_client import get_richmond_expenditures

        zip_buf = _make_mock_zip(SAMPLE_ROWS)
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        results = get_richmond_expenditures(
            zip_file, min_amount=100, filing_map=SAMPLE_FILING_MAP
        )
        names = {r["candidate_name"] for r in results}
        assert "Tom Butt" in names
        assert "Eduardo Martinez" in names

    def test_support_oppose_codes(self, tmp_path):
        """SUP_OPP_CD correctly mapped."""
        from calaccess_client import get_richmond_expenditures

        zip_buf = _make_mock_zip(SAMPLE_ROWS)
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        results = get_richmond_expenditures(
            zip_file, min_amount=100, filing_map=SAMPLE_FILING_MAP
        )
        by_candidate = {r["candidate_name"]: r for r in results}
        assert by_candidate["Tom Butt"]["support_or_oppose"] == "S"
        assert by_candidate["Eduardo Martinez"]["support_or_oppose"] == "O"

    def test_amount_filtering(self, tmp_path):
        """Expenditures below min_amount excluded."""
        from calaccess_client import get_richmond_expenditures

        zip_buf = _make_mock_zip(SAMPLE_ROWS)
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        # With min_amount=0, should also get the $50 row
        results = get_richmond_expenditures(
            zip_file, min_amount=0, filing_map=SAMPLE_FILING_MAP
        )
        assert len(results) == 3  # Rows 1, 2, and 3

    def test_filing_map_filters_non_richmond(self, tmp_path):
        """Only filings in filing_map are included."""
        from calaccess_client import get_richmond_expenditures

        zip_buf = _make_mock_zip(SAMPLE_ROWS)
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        results = get_richmond_expenditures(
            zip_file, min_amount=100, filing_map=SAMPLE_FILING_MAP
        )
        filing_ids = {r["filing_id"] for r in results}
        assert "F999" not in filing_ids

    def test_committee_name_from_filing_map(self, tmp_path):
        """Committee name sourced from filing_map, not raw TSV."""
        from calaccess_client import get_richmond_expenditures

        zip_buf = _make_mock_zip(SAMPLE_ROWS)
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        results = get_richmond_expenditures(
            zip_file, min_amount=100, filing_map=SAMPLE_FILING_MAP
        )
        for r in results:
            assert r["committee"] == "Coalition for Richmond's Future (Chevron)"

    def test_city_fips_on_records(self, tmp_path):
        """Every record gets city_fips."""
        from calaccess_client import get_richmond_expenditures

        zip_buf = _make_mock_zip(SAMPLE_ROWS)
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        results = get_richmond_expenditures(
            zip_file, min_amount=100, filing_map=SAMPLE_FILING_MAP
        )
        for r in results:
            assert r["city_fips"] == "0660620"

    def test_missing_columns_no_crash(self, tmp_path):
        """Rows with missing columns don't crash (defensive .get())."""
        from calaccess_client import get_richmond_expenditures

        # Minimal row with only required fields
        minimal_row = {
            "FILING_ID": "F001",
            "AMOUNT": "1000.00",
        }
        # Fill missing columns with empty strings
        for col in EXPN_HEADER:
            if col not in minimal_row:
                minimal_row[col] = ""

        zip_buf = _make_mock_zip([minimal_row])
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        results = get_richmond_expenditures(
            zip_file, min_amount=100, filing_map=SAMPLE_FILING_MAP
        )
        assert len(results) == 1
        assert results[0]["candidate_name"] == ""
        assert results[0]["support_or_oppose"] == ""

    def test_invalid_amount_skipped(self, tmp_path):
        """Rows with non-numeric amount are skipped."""
        from calaccess_client import get_richmond_expenditures

        bad_row = dict(SAMPLE_ROWS[0])
        bad_row["AMOUNT"] = "not_a_number"

        zip_buf = _make_mock_zip([bad_row])
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        results = get_richmond_expenditures(
            zip_file, min_amount=100, filing_map=SAMPLE_FILING_MAP
        )
        assert len(results) == 0

    def test_empty_zip_returns_empty(self, tmp_path):
        """ZIP with no matching rows returns empty list."""
        from calaccess_client import get_richmond_expenditures

        zip_buf = _make_mock_zip([])
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(zip_buf.read())

        results = get_richmond_expenditures(
            zip_file, min_amount=100, filing_map=SAMPLE_FILING_MAP
        )
        assert results == []


class TestLoadExpendituresToDb:
    """Tests for load_expenditures_to_db in db.py."""

    def test_basic_loading(self):
        """Records are inserted via cursor.execute."""
        from db import load_expenditures_to_db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        records = [
            {
                "committee": "Coalition for Richmond's Future",
                "candidate_name": "Tom Butt",
                "support_or_oppose": "S",
                "amount": 50000.0,
                "date": "2014-10-15",
                "expenditure_description": "Mailer",
                "expenditure_code": "LIT",
                "payee_name": "Printing Co",
                "filing_id": "F001",
            },
        ]

        stats = load_expenditures_to_db(mock_conn, records)
        assert stats["loaded"] == 1
        assert stats["skipped"] == 0
        assert mock_cursor.execute.call_count == 1

    def test_skips_missing_committee(self):
        """Records without committee are skipped."""
        from db import load_expenditures_to_db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        records = [
            {"committee": "", "amount": 1000, "date": "2014-10-15"},
        ]

        stats = load_expenditures_to_db(mock_conn, records)
        assert stats["loaded"] == 0
        assert stats["skipped"] == 1

    def test_skips_missing_amount(self):
        """Records without amount are skipped."""
        from db import load_expenditures_to_db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        records = [
            {"committee": "Some PAC", "amount": None, "date": "2014-10-15"},
        ]

        stats = load_expenditures_to_db(mock_conn, records)
        assert stats["loaded"] == 0
        assert stats["skipped"] == 1
