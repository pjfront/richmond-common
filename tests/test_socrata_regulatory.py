"""Tests for Socrata regulatory dataset sync functions (B.44).

Tests sync_socrata_permits, sync_socrata_licenses, sync_socrata_code_cases,
sync_socrata_service_requests, sync_socrata_projects, and shared helpers.
"""
from unittest.mock import patch, MagicMock

import pytest


# ── Helper fixtures ──────────────────────────────────────────


def _mock_conn():
    """Create a mock DB connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    # Default: all inserts are new rows
    cursor.fetchone.return_value = (True,)
    return conn, cursor


# ── _parse_socrata_date ──────────────────────────────────────


class TestParseSocrataDate:
    """Test the shared date parser for Socrata fields."""

    def test_iso_format(self):
        from data_sync import _parse_socrata_date
        assert _parse_socrata_date("2019-07-17T00:00:00.000") == "2019-07-17"

    def test_iso_date_only(self):
        from data_sync import _parse_socrata_date
        assert _parse_socrata_date("2025-01-15") == "2025-01-15"

    def test_text_format(self):
        from data_sync import _parse_socrata_date
        result = _parse_socrata_date("Jan 14 2013 12:00AM")
        assert result == "2013-01-14"

    def test_text_format_double_space(self):
        from data_sync import _parse_socrata_date
        result = _parse_socrata_date("Aug  5 2020 12:00AM")
        # Should handle double-space before single-digit day
        assert result is not None
        assert "2020" in result

    def test_none_returns_none(self):
        from data_sync import _parse_socrata_date
        assert _parse_socrata_date(None) is None

    def test_empty_string_returns_none(self):
        from data_sync import _parse_socrata_date
        assert _parse_socrata_date("") is None


class TestSafeNumeric:
    """Test numeric parsing helpers."""

    def test_valid_float(self):
        from data_sync import _safe_numeric
        assert _safe_numeric("1234.56") == 1234.56

    def test_valid_int_string(self):
        from data_sync import _safe_numeric
        assert _safe_numeric("499") == 499.0

    def test_none_returns_none(self):
        from data_sync import _safe_numeric
        assert _safe_numeric(None) is None

    def test_invalid_returns_none(self):
        from data_sync import _safe_numeric
        assert _safe_numeric("not a number") is None

    def test_safe_int_valid(self):
        from data_sync import _safe_int
        assert _safe_int("5") == 5

    def test_safe_int_float_string(self):
        from data_sync import _safe_int
        assert _safe_int("3.7") == 3

    def test_safe_int_none(self):
        from data_sync import _safe_int
        assert _safe_int(None) is None


# ── SYNC_SOURCES registration ────────────────────────────────


class TestRegistration:
    """Verify all 5 regulatory sync functions are registered."""

    def test_all_registered(self):
        from data_sync import SYNC_SOURCES
        assert "socrata_permits" in SYNC_SOURCES
        assert "socrata_licenses" in SYNC_SOURCES
        assert "socrata_code_cases" in SYNC_SOURCES
        assert "socrata_service_requests" in SYNC_SOURCES
        assert "socrata_projects" in SYNC_SOURCES

    def test_all_callable(self):
        from data_sync import SYNC_SOURCES
        for name in ["socrata_permits", "socrata_licenses", "socrata_code_cases",
                      "socrata_service_requests", "socrata_projects"]:
            assert callable(SYNC_SOURCES[name])


# ── sync_socrata_permits ─────────────────────────────────────


class TestSyncSocrataPermits:
    """Test building permit sync from Socrata permit_trak."""

    SAMPLE_ROW = {
        ":id": "row-abc123",
        "permit_no": "BP22-12345",
        "type": "BUILDING",
        "subtype": "RESIDENTIAL",
        "description": "New single family dwelling",
        "status": "ISSUED",
        "situs_address": "123 MAIN ST",
        "situs_apn": "123-456-789",
        "applied": "2022-03-15T00:00:00.000",
        "approved": "2022-04-01T00:00:00.000",
        "issued": "2022-04-15T00:00:00.000",
        "finaled": None,
        "expired": "Aug 16 2023 12:00AM",
        "applied_by": "JD",
        "fees_charged": "2500",
        "fees_paid": "2500",
        "jobvalue": "350000",
        "bldg_sf": "1800",
        "no_units": "1",
        "project_number": "PRJ-001",
    }

    def test_basic_sync(self):
        from data_sync import sync_socrata_permits
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            result = sync_socrata_permits(conn, "0660620", "full")

        assert result["records_fetched"] == 1
        assert result["records_new"] == 1

    def test_insert_sql_contains_correct_table(self):
        from data_sync import sync_socrata_permits
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            sync_socrata_permits(conn, "0660620", "full")

        insert_sql = cursor.execute.call_args[0][0]
        assert "city_permits" in insert_sql
        assert "ON CONFLICT ON CONSTRAINT uq_city_permit" in insert_sql

    def test_date_parsing_mixed_formats(self):
        """permit_trak uses text dates for some fields and ISO for others."""
        from data_sync import sync_socrata_permits
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            sync_socrata_permits(conn, "0660620", "full")

        params = cursor.execute.call_args[0][1]
        # applied_date (ISO) should be parsed
        assert params[8] == "2022-03-15"  # applied_date
        # socrata_row_id should be the :id
        assert params[-1] == "row-abc123"

    def test_empty_results(self):
        from data_sync import sync_socrata_permits
        conn, _ = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[]):
            result = sync_socrata_permits(conn, "0660620", "full")

        assert result["records_fetched"] == 0
        assert result["records_new"] == 0

    def test_incremental_passes_where_clause(self):
        from data_sync import sync_socrata_permits
        conn, _ = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[]) as mock_query:
            sync_socrata_permits(conn, "0660620", "incremental")

        call_kwargs = mock_query.call_args
        assert call_kwargs[1].get("where") is not None or (len(call_kwargs[0]) > 1 and call_kwargs[0][1])

    def test_pagination(self):
        """Large dataset triggers pagination loop."""
        from data_sync import sync_socrata_permits
        conn, cursor = _mock_conn()

        # First call returns 50000 rows, second returns 1
        batch_1 = [{"permit_no": f"P{i}", ":id": f"id-{i}", "type": "BUILDING",
                     "subtype": "", "description": "", "status": "ISSUED",
                     "situs_address": "", "applied": None, "approved": None,
                     "issued": None, "finaled": None, "expired": None,
                     "applied_by": "", "fees_charged": "0", "fees_paid": "0",
                     "jobvalue": "0", "bldg_sf": "0", "no_units": "0",
                     "project_number": ""} for i in range(50000)]
        batch_2 = [batch_1[0].copy()]
        batch_2[0][":id"] = "id-last"

        with patch("socrata_client.query_dataset", side_effect=[batch_1, batch_2]):
            result = sync_socrata_permits(conn, "0660620", "full")

        assert result["records_fetched"] == 50001


# ── sync_socrata_licenses ────────────────────────────────────


class TestSyncSocrataLicenses:
    """Test business license sync from Socrata license_trak."""

    SAMPLE_ROW = {
        ":id": "row-lic-001",
        "company": "FORD MOTOR COMPANY",
        "company_print_as": "Ford Motor Co.",
        "business_type": "ANNUAL LICENSE",
        "classification": "DISTRIBUTOR",
        "ownership_type": "CORPORATION",
        "status": "ACTIVE",
        "employees": "25",
        "bus_lic_iss": "2024-01-15T00:00:00.000",
        "bus_lic_exp": "2025-01-15T00:00:00.000",
        "bus_start_date": "2020-06-01T00:00:00.000",
        "loc_address1": "700 NATIONAL CT",
        "loc_city": "RICHMOND",
        "loc_zip": "94804",
        "site_number": "700",
        "site_streetname": "NATIONAL CT",
        "site_unit_no": "",
        "site_apn10": "550-020-029",
        "sic_1": "5012",
        "nbrhd_council": "District 5",
    }

    def test_basic_sync(self):
        from data_sync import sync_socrata_licenses
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            result = sync_socrata_licenses(conn, "0660620", "full")

        assert result["records_fetched"] == 1
        assert result["records_new"] == 1

    def test_company_normalization(self):
        """Company name should be normalized for cross-referencing."""
        from data_sync import sync_socrata_licenses
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            sync_socrata_licenses(conn, "0660620", "full")

        params = cursor.execute.call_args[0][1]
        # normalized_company should be lowercase
        assert params[2] == "ford motor company"

    def test_site_address_assembled(self):
        """Site address is assembled from number + streetname + unit."""
        from data_sync import sync_socrata_licenses
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            sync_socrata_licenses(conn, "0660620", "full")

        params = cursor.execute.call_args[0][1]
        # site_address field (index 15)
        assert "700" in params[15]
        assert "NATIONAL CT" in params[15]


# ── sync_socrata_code_cases ──────────────────────────────────


class TestSyncSocrataCodeCases:
    """Test code enforcement case sync from Socrata code_trak."""

    SAMPLE_ROW = {
        ":id": "row-code-001",
        "casetype": "FIRE SAFETY",
        "casesubtype": "CFC MERCANTILE INSPECTION",
        "violation_type": "Fire Code Violation",
        "violation": "FIRE Signage General",
        "status": "CLOSED",
        "case_location": "1085 ESSEX AVE RICHMOND CA.",
        "site_addr": "1085 ESSEX AVE",
        "site_apn": "",
        "site_zip": "94801",
        "opened": "2024-03-06T00:00:00.000",
        "closed": "2024-04-20T00:00:00.000",
        "date_observed": "Mar  5 2024 12:00AM",
        "date_corrected": "Apr 20 2024 12:00AM",
        "nbrhd_council": "District 1",
    }

    def test_basic_sync(self):
        from data_sync import sync_socrata_code_cases
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            result = sync_socrata_code_cases(conn, "0660620", "full")

        assert result["records_fetched"] == 1
        assert result["records_new"] == 1

    def test_date_fields_parsed(self):
        from data_sync import sync_socrata_code_cases
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            sync_socrata_code_cases(conn, "0660620", "full")

        params = cursor.execute.call_args[0][1]
        # opened_date (ISO)
        assert params[10] == "2024-03-06"
        # closed_date (ISO)
        assert params[11] == "2024-04-20"

    def test_site_address_fallback(self):
        """When site_addr is empty, assembles from components."""
        from data_sync import sync_socrata_code_cases
        conn, cursor = _mock_conn()

        row = dict(self.SAMPLE_ROW)
        row["site_addr"] = ""
        row["site_number"] = "500"
        row["site_streetname"] = "HARBOUR WAY"
        row["site_unit_no"] = "B"

        with patch("socrata_client.query_dataset", return_value=[row]):
            sync_socrata_code_cases(conn, "0660620", "full")

        params = cursor.execute.call_args[0][1]
        assert "500" in params[7]
        assert "HARBOUR WAY" in params[7]


# ── sync_socrata_service_requests ────────────────────────────


class TestSyncSocrataServiceRequests:
    """Test citizen service request sync from Socrata crm_trak."""

    SAMPLE_ROW = {
        ":id": "row-crm-001",
        "issue_concern_type": "Potholes",
        "department": "Public Works",
        "description": "Pothole at 13th and Potrero",
        "status": "Closed",
        "created_via": "Web Report",
        "issue_address": "13th and Potrero",
        "created_datetime": "2024-01-08T00:00:00.000",
        "due_date": "2024-01-15T00:00:00.000",
        "completed_date": "2024-01-11T00:00:00.000",
        "linked_doc": None,
        "lat": "37.9486",
        "lon": "-122.3671",
    }

    def test_basic_sync(self):
        from data_sync import sync_socrata_service_requests
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            result = sync_socrata_service_requests(conn, "0660620", "full")

        assert result["records_fetched"] == 1
        assert result["records_new"] == 1

    def test_lat_lon_parsed(self):
        from data_sync import sync_socrata_service_requests
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            sync_socrata_service_requests(conn, "0660620", "full")

        params = cursor.execute.call_args[0][1]
        # lat (index 11), lon (index 12)
        assert params[11] == pytest.approx(37.9486)
        assert params[12] == pytest.approx(-122.3671)

    def test_handles_missing_coordinates(self):
        from data_sync import sync_socrata_service_requests
        conn, cursor = _mock_conn()

        row = dict(self.SAMPLE_ROW)
        row["lat"] = None
        row["lon"] = None

        with patch("socrata_client.query_dataset", return_value=[row]):
            result = sync_socrata_service_requests(conn, "0660620", "full")

        assert result["records_new"] == 1
        params = cursor.execute.call_args[0][1]
        assert params[11] is None
        assert params[12] is None


# ── sync_socrata_projects ────────────────────────────────────


class TestSyncSocrataProjects:
    """Test capital/development project sync from Socrata project_trak."""

    SAMPLE_ROW = {
        ":id": "row-prj-001",
        "project_no": "PLN19-244",
        "project_name": "NEW MIXED USE DEVELOPMENT",
        "projecttype": "PLN",
        "projectsubtype": "DESIGN REVIEW",
        "description_of_work": "4-story mixed use with 20 units and ground floor retail",
        "status": "APPROVED",
        "site_addr": "2995 ATLAS RD",
        "site_apn10": "405-030-055-9",
        "site_zip": "94806",
        "zoning_code1": "C-2",
        "land_use": "COMMERCIAL",
        "occupancy_description": "MIXED USE",
        "resolution_no": "RES-2020-045",
        "parent_project_no": None,
        "applied": "2019-07-17T00:00:00.000",
        "approved": "2020-01-15T00:00:00.000",
        "closed": "2020-01-15T00:00:00.000",
        "expired": None,
        "status_date": "2020-01-15T00:00:00.000",
        "applied_by": "ECI",
        "approved_by": "DRB",
        "applied_affordability_level": None,
        "approved_affordability_level": "MODERATE",
        "nbrhd_council": "District 3",
        "latitude": "37.92827",
        "longitude": "-122.37614",
    }

    def test_basic_sync(self):
        from data_sync import sync_socrata_projects
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            result = sync_socrata_projects(conn, "0660620", "full")

        assert result["records_fetched"] == 1
        assert result["records_new"] == 1

    def test_resolution_no_captured(self):
        """Resolution number is key for linking to council votes."""
        from data_sync import sync_socrata_projects
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            sync_socrata_projects(conn, "0660620", "full")

        params = cursor.execute.call_args[0][1]
        # resolution_no is at index 13
        assert params[13] == "RES-2020-045"

    def test_affordability_level_captured(self):
        """Affordability levels tracked for housing policy analysis."""
        from data_sync import sync_socrata_projects
        conn, cursor = _mock_conn()

        with patch("socrata_client.query_dataset", return_value=[self.SAMPLE_ROW]):
            sync_socrata_projects(conn, "0660620", "full")

        params = cursor.execute.call_args[0][1]
        # affordability_level_approved at index 23
        assert params[23] == "MODERATE"

    def test_site_address_fallback(self):
        """When site_addr is empty, assembles from components."""
        from data_sync import sync_socrata_projects
        conn, cursor = _mock_conn()

        row = dict(self.SAMPLE_ROW)
        row["site_addr"] = ""
        row["site_number"] = "100"
        row["site_streetname"] = "BARRETT AVE"
        row["site_unit_no"] = ""

        with patch("socrata_client.query_dataset", return_value=[row]):
            sync_socrata_projects(conn, "0660620", "full")

        params = cursor.execute.call_args[0][1]
        assert "100" in params[7]
        assert "BARRETT AVE" in params[7]


# ── City config registration ─────────────────────────────────


class TestCityConfigRegistration:
    """Verify all 5 datasets are in the city config registry."""

    def test_datasets_in_richmond_config(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        datasets = cfg["data_sources"]["socrata"]["datasets"]
        assert "permit_trak" in datasets
        assert "license_trak" in datasets
        assert "code_trak" in datasets
        assert "crm_trak" in datasets
        assert "project_trak" in datasets


# ── Staleness monitor registration ───────────────────────────


class TestStalenessRegistration:
    """Verify all 5 sources have staleness thresholds."""

    def test_thresholds_registered(self):
        from staleness_monitor import FRESHNESS_THRESHOLDS
        assert "socrata_permits" in FRESHNESS_THRESHOLDS
        assert "socrata_licenses" in FRESHNESS_THRESHOLDS
        assert "socrata_code_cases" in FRESHNESS_THRESHOLDS
        assert "socrata_service_requests" in FRESHNESS_THRESHOLDS
        assert "socrata_projects" in FRESHNESS_THRESHOLDS

    def test_thresholds_are_reasonable(self):
        from staleness_monitor import FRESHNESS_THRESHOLDS
        for key in ["socrata_permits", "socrata_licenses", "socrata_code_cases",
                     "socrata_service_requests", "socrata_projects"]:
            assert 7 <= FRESHNESS_THRESHOLDS[key] <= 90


# ── Staleness monitor schema health ──────────────────────────


class TestSchemaHealth:
    """Verify new tables are in the expected tables list."""

    def test_regulatory_tables_in_expected(self):
        from staleness_monitor import EXPECTED_TABLES
        regulatory = EXPECTED_TABLES.get("039_socrata_regulatory", [])
        assert "city_permits" in regulatory
        assert "city_licenses" in regulatory
        assert "city_code_cases" in regulatory
        assert "city_service_requests" in regulatory
        assert "city_projects" in regulatory
