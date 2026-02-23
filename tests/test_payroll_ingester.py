# tests/test_payroll_ingester.py
"""Tests for Socrata payroll ingestion pipeline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from payroll_ingester import (
    parse_payroll_records,
    normalize_employee,
    build_employee_record,
    aggregate_by_employee,
    CITY_FIPS,
)


# ── Sample Socrata rows (real column names from pre-flight) ──

SAMPLE_ROW = {
    "employeeid": "1234",
    "firstname": "KINSHASA",
    "lastname": "CURL",
    "position": "CITY MANAGER",
    "department": "CITY MANAGER",
    "basepay": "15000.00",
    "otherpay": "500.00",
    "overtimepay": "0.00",
    "benefitsamount": "3000.00",
    "totalpay": "18500.00",
    "fiscalyear": "2025",
    "positiontype": "FULL TIME PERMANENT",
}

SAMPLE_ROW_REGULAR = {
    "employeeid": "5678",
    "firstname": "JANE",
    "lastname": "DOE",
    "position": "ADMINISTRATIVE ASSISTANT",
    "department": "FINANCE",
    "basepay": "2500.00",
    "otherpay": "0.00",
    "overtimepay": "0.00",
    "benefitsamount": "800.00",
    "totalpay": "3300.00",
    "fiscalyear": "2025",
    "positiontype": "FULL TIME PERMANENT",
}


class TestNormalizeEmployee:
    def test_basic_normalization(self):
        rec = normalize_employee(SAMPLE_ROW)
        assert rec["name"] == "Kinshasa Curl"
        assert rec["normalized_name"] == "kinshasa curl"
        assert rec["job_title"] == "CITY MANAGER"

    def test_name_from_first_last(self):
        """Names are combined from firstname + lastname, title-cased."""
        rec = normalize_employee(SAMPLE_ROW)
        assert rec["name"] == "Kinshasa Curl"

    def test_strips_whitespace(self):
        row = {**SAMPLE_ROW, "firstname": "  JOHN  ", "lastname": "  SMITH  "}
        rec = normalize_employee(row)
        assert rec["name"] == "John Smith"
        assert rec["normalized_name"] == "john smith"

    def test_salary_parsing(self):
        rec = normalize_employee(SAMPLE_ROW)
        assert rec["basepay"] == 15000.0
        assert rec["totalpay"] == 18500.0

    def test_missing_salary(self):
        row = {**SAMPLE_ROW, "basepay": None}
        rec = normalize_employee(row)
        assert rec["basepay"] is None

    def test_employee_id(self):
        rec = normalize_employee(SAMPLE_ROW)
        assert rec["employee_id"] == "1234"


class TestBuildEmployeeRecord:
    def test_city_manager_classified(self):
        rec = build_employee_record(SAMPLE_ROW, city_fips=CITY_FIPS)
        assert rec["hierarchy_level"] == 1
        assert rec["is_department_head"] is True
        assert rec["city_fips"] == CITY_FIPS

    def test_regular_employee_unclassified(self):
        rec = build_employee_record(SAMPLE_ROW_REGULAR, city_fips=CITY_FIPS)
        assert rec["hierarchy_level"] == 0
        assert rec["is_department_head"] is False

    def test_source_field(self):
        rec = build_employee_record(SAMPLE_ROW, city_fips=CITY_FIPS)
        assert rec["source"] == "socrata_payroll"


class TestAggregateByEmployee:
    def test_aggregates_multiple_transactions(self):
        """Multiple pay rows for same employee should aggregate into one."""
        row1 = {**SAMPLE_ROW, "basepay": "10000.00", "totalpay": "13000.00"}
        row2 = {**SAMPLE_ROW, "basepay": "10000.00", "totalpay": "13000.00"}
        rows = [row1, row2]
        aggregated = aggregate_by_employee(rows)
        assert len(aggregated) == 1
        assert aggregated[0]["basepay"] == 20000.0
        assert aggregated[0]["totalpay"] == 26000.0

    def test_preserves_distinct_employees(self):
        rows = [SAMPLE_ROW, SAMPLE_ROW_REGULAR]
        aggregated = aggregate_by_employee(rows)
        assert len(aggregated) == 2

    def test_keeps_latest_position(self):
        """If employee has multiple transactions, keep the position field."""
        row1 = {**SAMPLE_ROW}
        row2 = {**SAMPLE_ROW}
        aggregated = aggregate_by_employee([row1, row2])
        assert aggregated[0]["position"] == "CITY MANAGER"

    def test_empty_input(self):
        assert aggregate_by_employee([]) == []


class TestParsePayrollRecords:
    def test_batch_parsing(self):
        rows = [SAMPLE_ROW, SAMPLE_ROW_REGULAR]
        records = parse_payroll_records(rows, city_fips=CITY_FIPS)
        assert len(records) == 2
        assert records[0]["hierarchy_level"] == 1
        assert records[1]["hierarchy_level"] == 0

    def test_stats_summary(self):
        rows = [SAMPLE_ROW, SAMPLE_ROW_REGULAR]
        records = parse_payroll_records(rows, city_fips=CITY_FIPS)
        heads = [r for r in records if r["is_department_head"]]
        assert len(heads) == 1

    def test_empty_input(self):
        records = parse_payroll_records([], city_fips=CITY_FIPS)
        assert records == []

    def test_skips_empty_names(self):
        row = {**SAMPLE_ROW, "firstname": "", "lastname": ""}
        records = parse_payroll_records([row], city_fips=CITY_FIPS)
        assert len(records) == 0

    def test_annual_salary_from_basepay(self):
        """annual_salary should come from aggregated basepay."""
        records = parse_payroll_records([SAMPLE_ROW], city_fips=CITY_FIPS)
        assert records[0]["annual_salary"] == 15000.0

    def test_total_compensation_from_totalpay(self):
        """total_compensation should come from aggregated totalpay."""
        records = parse_payroll_records([SAMPLE_ROW], city_fips=CITY_FIPS)
        assert records[0]["total_compensation"] == 18500.0
