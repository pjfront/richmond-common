"""
socrata pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (socrata-specific) live alongside.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import psycopg2

from city_config import get_city_config, list_configured_cities
from db import (
    get_connection,
    create_sync_log,
    complete_sync_log,
    load_contributions_to_db,
    load_expenditures_to_db,
)
from pipeline_journal import PipelineJournal, check_anomalies

DEFAULT_FIPS = "0660620"


def sync_socrata_payroll(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync city employee payroll from Socrata open data portal.

    Wraps the existing payroll_ingester pipeline: fetch from Socrata,
    aggregate per-transaction rows by employee, classify hierarchy,
    and upsert into city_employees table.

    For incremental: fetches latest fiscal year only.
    For full: fetches all available fiscal years.
    """
    from payroll_ingester import fetch_payroll, parse_payroll_records, load_to_db

    # Determine which fiscal years to process
    if sync_type == "full":
        # Socrata data goes back several years; fetch recent ones
        from datetime import date
        current_fy = str(date.today().year)
        fiscal_years = [str(int(current_fy) - i) for i in range(5)]
    else:
        from datetime import date
        fiscal_years = [str(date.today().year)]

    total_fetched = 0
    total_loaded = 0

    for fy in fiscal_years:
        print(f"  Fetching payroll for FY {fy}...")
        raw_rows = fetch_payroll(fy, city_fips=city_fips)
        if not raw_rows:
            print(f"    No payroll data for FY {fy}")
            continue

        records = parse_payroll_records(raw_rows, city_fips=city_fips)
        total_fetched += len(raw_rows)
        total_loaded += len(records)

        print(f"    {len(raw_rows)} raw rows -> {len(records)} employees")

        # load_to_db manages its own connection; pass records through conn instead
        with conn.cursor() as cur:
            loaded = 0
            for rec in records:
                cur.execute(
                    """INSERT INTO city_employees
                       (city_fips, name, normalized_name, job_title, department,
                        is_department_head, hierarchy_level, annual_salary,
                        total_compensation, fiscal_year, is_current, source,
                        socrata_record_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT ON CONSTRAINT uq_city_employee
                       DO UPDATE SET
                           job_title = EXCLUDED.job_title,
                           is_department_head = EXCLUDED.is_department_head,
                           hierarchy_level = EXCLUDED.hierarchy_level,
                           annual_salary = EXCLUDED.annual_salary,
                           total_compensation = EXCLUDED.total_compensation,
                           is_current = EXCLUDED.is_current,
                           source = EXCLUDED.source,
                           socrata_record_id = EXCLUDED.socrata_record_id,
                           updated_at = NOW()""",
                    (
                        rec["city_fips"], rec["name"], rec["normalized_name"],
                        rec["job_title"], rec["department"],
                        rec["is_department_head"], rec["hierarchy_level"],
                        rec["annual_salary"], rec["total_compensation"],
                        rec["fiscal_year"], rec["is_current"], rec["source"],
                        rec.get("socrata_record_id"),
                    ),
                )
                loaded += 1
            conn.commit()
            print(f"    Loaded {loaded} records")

    print(f"  Payroll sync complete: {total_fetched} raw rows -> {total_loaded} employees")

    return {
        "records_fetched": total_fetched,
        "records_new": total_loaded,
        "records_updated": 0,
        "fiscal_years_processed": len(fiscal_years),
    }


def _normalize_vendor_name(name: str) -> str:
    """Normalize vendor name for matching: lowercase, collapse whitespace."""
    if not name:
        return ""
    return " ".join(name.lower().split())


def sync_socrata_expenditures(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync city expenditure records from Socrata open data portal.

    Fetches actual spending data (vendor, amount, department, fund) and
    upserts into city_expenditures table.

    For incremental: fetches latest fiscal year only.
    For full: fetches all available fiscal years.
    """
    from socrata_client import query_dataset

    # Determine fiscal years to process
    if sync_type == "full":
        from datetime import date
        current_fy = str(date.today().year)
        fiscal_years = [str(int(current_fy) - i) for i in range(5)]
    else:
        from datetime import date
        fiscal_years = [str(date.today().year)]

    total_fetched = 0
    total_new = 0
    total_updated = 0

    for fy in fiscal_years:
        print(f"  Fetching expenditures for FY {fy}...")

        # Paginate through all results (Socrata max 50K per call)
        offset = 0
        batch_size = 50000
        fy_rows = []

        while True:
            rows = query_dataset(
                "expenditures",
                where=f"fiscalyear = '{fy}'",
                limit=batch_size,
                offset=offset,
                city_fips=city_fips,
            )
            if not rows:
                break
            fy_rows.extend(rows)
            if len(rows) < batch_size:
                break
            offset += batch_size

        if not fy_rows:
            print(f"    No expenditure data for FY {fy}")
            continue

        total_fetched += len(fy_rows)
        print(f"    {len(fy_rows)} expenditure records")

        # Upsert into city_expenditures
        new = 0
        updated = 0
        with conn.cursor() as cur:
            for row in fy_rows:
                vendor = (row.get("vendorname") or "").strip()
                amount_raw = row.get("actual")
                amount = None
                if amount_raw is not None:
                    try:
                        amount = float(amount_raw)
                    except (ValueError, TypeError):
                        amount = None

                # Parse date (Socrata returns ISO format or floating timestamp)
                exp_date = None
                date_raw = row.get("date")
                if date_raw:
                    # Socrata dates come as ISO strings like "2025-01-15T00:00:00.000"
                    try:
                        exp_date = date_raw[:10]  # YYYY-MM-DD portion
                    except (IndexError, TypeError):
                        exp_date = None

                # Socrata rows have a ":id" field as unique row identifier
                socrata_id = row.get(":id") or row.get("rowid") or ""
                if not socrata_id:
                    # Construct a synthetic ID from key fields
                    socrata_id = f"{fy}:{vendor}:{amount}:{date_raw}"

                cur.execute(
                    """INSERT INTO city_expenditures
                       (city_fips, vendor_name, normalized_vendor, description,
                        amount, department, fund, fiscal_year, expenditure_date,
                        source, socrata_row_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT ON CONSTRAINT uq_city_expenditure
                       DO UPDATE SET
                           vendor_name = EXCLUDED.vendor_name,
                           description = EXCLUDED.description,
                           amount = EXCLUDED.amount,
                           department = EXCLUDED.department,
                           fund = EXCLUDED.fund,
                           expenditure_date = EXCLUDED.expenditure_date,
                           updated_at = NOW()
                       RETURNING (xmax = 0) AS inserted""",
                    (
                        city_fips,
                        vendor,
                        _normalize_vendor_name(vendor),
                        (row.get("description") or "").strip()[:1000],
                        amount,
                        (row.get("organization") or "").strip(),
                        (row.get("fund") or "").strip(),
                        fy,
                        exp_date,
                        "socrata_expenditures",
                        socrata_id,
                    ),
                )
                result_row = cur.fetchone()
                if result_row and result_row[0]:
                    new += 1
                else:
                    updated += 1

            conn.commit()

        total_new += new
        total_updated += updated
        print(f"    Loaded: {new} new, {updated} updated")

    print(f"  Expenditures sync complete: {total_fetched} records ({total_new} new, {total_updated} updated)")

    return {
        "records_fetched": total_fetched,
        "records_new": total_new,
        "records_updated": total_updated,
        "fiscal_years_processed": len(fiscal_years),
    }


def _parse_socrata_date(raw: str | None) -> str | None:
    """Parse Socrata date fields into YYYY-MM-DD.

    Handles two formats:
    - ISO: '2019-07-17T00:00:00.000'
    - Text: 'Jan 14 2013 12:00AM'
    Returns None for unparseable values.
    """
    if not raw:
        return None
    raw = raw.strip()
    # ISO format
    if len(raw) >= 10 and raw[4:5] == "-":
        return raw[:10]
    # Text format: 'Mon DD YYYY ...'
    from datetime import datetime
    for fmt in ("%b %d %Y %I:%M%p", "%b  %d %Y %I:%M%p", "%b %d %Y"):
        try:
            return datetime.strptime(raw.split(" 12:")[0] if " 12:" in raw else raw[:11].strip(), fmt.replace(" 12:", "")).strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            continue
    # Last resort: try dateutil-style parsing
    try:
        return raw[:10] if len(raw) >= 10 else None
    except Exception:
        return None


def _sync_socrata_paginated(
    dataset_key: str,
    city_fips: str,
    process_row,
    table_name: str,
    conn,
    insert_sql: str,
    source_label: str,
    where: str | None = None,
) -> dict:
    """Shared pagination + upsert loop for Socrata regulatory datasets.

    Args:
        dataset_key: Socrata dataset key (e.g., 'permit_trak')
        city_fips: FIPS code
        process_row: callable(row) -> tuple of values for INSERT, or None to skip
        table_name: for logging
        conn: database connection
        insert_sql: full INSERT ... ON CONFLICT SQL with %s placeholders
        source_label: for logging
        where: optional SoQL WHERE clause
    """
    from socrata_client import query_dataset

    total_fetched = 0
    total_new = 0
    total_updated = 0
    offset = 0
    batch_size = 50000

    while True:
        rows = query_dataset(
            dataset_key,
            where=where,
            limit=batch_size,
            offset=offset,
            city_fips=city_fips,
        )
        if not rows:
            break

        total_fetched += len(rows)
        batch_new = 0
        batch_updated = 0

        with conn.cursor() as cur:
            for row in rows:
                values = process_row(row)
                if values is None:
                    continue
                cur.execute(insert_sql, values)
                result_row = cur.fetchone()
                if result_row and result_row[0]:
                    batch_new += 1
                else:
                    batch_updated += 1

        conn.commit()
        total_new += batch_new
        total_updated += batch_updated
        print(f"    {table_name}: batch {offset // batch_size + 1} — {len(rows)} rows ({batch_new} new, {batch_updated} updated)")

        if len(rows) < batch_size:
            break
        offset += batch_size

    print(f"  {source_label} sync complete: {total_fetched} records ({total_new} new, {total_updated} updated)")
    return {
        "records_fetched": total_fetched,
        "records_new": total_new,
        "records_updated": total_updated,
    }


def sync_socrata_permits(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync building/development permit records from Socrata permit_trak.

    For incremental: fetches permits applied in the last 90 days.
    For full: fetches all permits (~177K records).
    """
    where = None
    if sync_type != "full":
        where = "applied > '2025-01-01T00:00:00'"  # Recent permits

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or row.get("permit_no") or ""
        return (
            city_fips,
            (row.get("permit_no") or "").strip()[:50],
            (row.get("type") or "").strip()[:100],
            (row.get("subtype") or "").strip()[:100],
            (row.get("description") or "").strip()[:2000] or None,
            (row.get("status") or "").strip()[:50],
            (row.get("situs_address") or "").strip()[:500] or None,
            (row.get("situs_apn") or "").strip()[:50] or None,
            _parse_socrata_date(row.get("applied")),
            _parse_socrata_date(row.get("approved")),
            _parse_socrata_date(row.get("issued")),
            _parse_socrata_date(row.get("finaled")),
            _parse_socrata_date(row.get("expired")),
            (row.get("applied_by") or "").strip()[:200] or None,
            _safe_numeric(row.get("fees_charged")),
            _safe_numeric(row.get("fees_paid")),
            _safe_numeric(row.get("jobvalue")),
            _safe_numeric(row.get("bldg_sf")),
            _safe_int(row.get("no_units")),
            (row.get("project_number") or "").strip()[:100] or None,
            "socrata_permits",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="permit_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_permits",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_permits
            (city_fips, permit_no, permit_type, permit_subtype, description,
             status, situs_address, situs_apn,
             applied_date, approved_date, issued_date, finaled_date, expired_date,
             applied_by, fees_charged, fees_paid, job_value, building_sqft, units,
             project_number, source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_permit
            DO UPDATE SET
                status = EXCLUDED.status,
                approved_date = EXCLUDED.approved_date,
                issued_date = EXCLUDED.issued_date,
                finaled_date = EXCLUDED.finaled_date,
                expired_date = EXCLUDED.expired_date,
                fees_paid = EXCLUDED.fees_paid,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Permits",
    )


def sync_socrata_licenses(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync business license records from Socrata license_trak.

    For incremental: fetches licenses issued in the last year.
    For full: fetches all licenses (~6K records).
    """
    where = None
    if sync_type != "full":
        where = "bus_lic_iss > '2025-01-01T00:00:00'"

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or ""
        company = (row.get("company") or "").strip()
        return (
            city_fips,
            company[:500],
            _normalize_vendor_name(company)[:500],
            (row.get("company_print_as") or "").strip()[:500] or None,
            (row.get("business_type") or "").strip()[:200] or None,
            (row.get("classification") or "").strip()[:200] or None,
            (row.get("ownership_type") or "").strip()[:100] or None,
            (row.get("status") or "").strip()[:50] or None,
            _safe_int(row.get("employees")),
            _parse_socrata_date(row.get("bus_lic_iss")),
            _parse_socrata_date(row.get("bus_lic_exp")),
            _parse_socrata_date(row.get("bus_start_date")),
            (row.get("loc_address1") or "").strip()[:500] or None,
            (row.get("loc_city") or "").strip()[:100] or None,
            (row.get("loc_zip") or "").strip()[:20] or None,
            " ".join(filter(None, [
                (row.get("site_number") or "").strip(),
                (row.get("site_streetname") or "").strip(),
                (row.get("site_unit_no") or "").strip(),
            ]))[:500] or None,
            (row.get("site_apn10") or row.get("site_apn") or "").strip()[:50] or None,
            (row.get("sic_1") or "").strip()[:50] or None,
            (row.get("nbrhd_council") or "").strip()[:100] or None,
            "socrata_licenses",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="license_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_licenses",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_licenses
            (city_fips, company, normalized_company, company_dba,
             business_type, classification, ownership_type, status, employees,
             license_issued, license_expired, business_start_date,
             loc_address, loc_city, loc_zip,
             site_address, site_apn, sic_code, neighborhood_council,
             source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_license
            DO UPDATE SET
                status = EXCLUDED.status,
                license_expired = EXCLUDED.license_expired,
                employees = EXCLUDED.employees,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Licenses",
    )


def sync_socrata_code_cases(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync code enforcement cases from Socrata code_trak.

    For incremental: fetches cases opened in the last 90 days.
    For full: fetches all cases (~37K records).
    """
    where = None
    if sync_type != "full":
        where = "opened > '2025-01-01T00:00:00'"

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or ""
        site_addr = (row.get("site_addr") or "").strip()
        if not site_addr:
            site_addr = " ".join(filter(None, [
                (row.get("site_number") or "").strip(),
                (row.get("site_streetname") or "").strip(),
                (row.get("site_unit_no") or "").strip(),
            ]))
        return (
            city_fips,
            (row.get("casetype") or "").strip()[:100] or None,
            (row.get("casesubtype") or "").strip()[:200] or None,
            (row.get("violation_type") or "").strip()[:200] or None,
            (row.get("violation") or "").strip()[:500] or None,
            (row.get("status") or "").strip()[:50] or None,
            (row.get("case_location") or "").strip()[:500] or None,
            site_addr[:500] or None,
            (row.get("site_apn10") or row.get("site_apn") or "").strip()[:50] or None,
            (row.get("site_zip") or "").strip()[:20] or None,
            _parse_socrata_date(row.get("opened")),
            _parse_socrata_date(row.get("closed")),
            _parse_socrata_date(row.get("date_observed")),
            _parse_socrata_date(row.get("date_corrected")),
            (row.get("nbrhd_council") or "").strip()[:100] or None,
            "socrata_code_cases",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="code_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_code_cases",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_code_cases
            (city_fips, case_type, case_subtype, violation_type, violation,
             status, case_location, site_address, site_apn, site_zip,
             opened_date, closed_date, date_observed, date_corrected,
             neighborhood_council, source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_code_case
            DO UPDATE SET
                status = EXCLUDED.status,
                closed_date = EXCLUDED.closed_date,
                date_corrected = EXCLUDED.date_corrected,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Code cases",
    )


def sync_socrata_service_requests(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync citizen service requests from Socrata crm_trak.

    For incremental: fetches requests created in the last 90 days.
    For full: fetches all requests (~44K records).
    """
    where = None
    if sync_type != "full":
        where = "created_datetime > '2025-01-01T00:00:00'"

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or ""
        lat = _safe_numeric(row.get("lat"))
        lon = _safe_numeric(row.get("lon"))
        return (
            city_fips,
            (row.get("issue_concern_type") or "").strip()[:300] or None,
            (row.get("department") or "").strip()[:200] or None,
            (row.get("description") or "").strip()[:2000] or None,
            (row.get("status") or "").strip()[:50] or None,
            (row.get("created_via") or "").strip()[:100] or None,
            (row.get("issue_address") or "").strip()[:500] or None,
            _parse_socrata_date(row.get("created_datetime")),
            _parse_socrata_date(row.get("due_date")),
            _parse_socrata_date(row.get("completed_date")),
            (row.get("linked_doc") or "").strip()[:500] or None,
            lat,
            lon,
            "socrata_service_requests",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="crm_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_service_requests",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_service_requests
            (city_fips, issue_type, department, description, status,
             created_via, issue_address, created_date, due_date, completed_date,
             linked_doc, latitude, longitude, source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_service_request
            DO UPDATE SET
                status = EXCLUDED.status,
                completed_date = EXCLUDED.completed_date,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Service requests",
    )


def sync_socrata_projects(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync capital/development project records from Socrata project_trak.

    For incremental: fetches projects applied in the last year.
    For full: fetches all projects (~5K records).
    """
    where = None
    if sync_type != "full":
        where = "applied > '2025-01-01T00:00:00'"

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or ""
        site_addr = (row.get("site_addr") or "").strip()
        if not site_addr:
            site_addr = " ".join(filter(None, [
                str(row.get("site_number") or "").strip(),
                (row.get("site_streetname") or "").strip(),
                (row.get("site_unit_no") or "").strip(),
            ]))
        return (
            city_fips,
            (row.get("project_no") or "").strip()[:50] or None,
            (row.get("project_name") or "").strip()[:500] or None,
            (row.get("projecttype") or "").strip()[:100] or None,
            (row.get("projectsubtype") or "").strip()[:200] or None,
            (row.get("description_of_work") or "").strip()[:2000] or None,
            (row.get("status") or "").strip()[:50] or None,
            site_addr[:500] or None,
            (row.get("site_apn10") or row.get("site_apn") or "").strip()[:50] or None,
            (row.get("site_zip") or "").strip()[:20] or None,
            (row.get("zoning_code1") or "").strip()[:50] or None,
            (row.get("land_use") or "").strip()[:200] or None,
            (row.get("occupancy_description") or "").strip()[:200] or None,
            (row.get("resolution_no") or "").strip()[:100] or None,
            (row.get("parent_project_no") or "").strip()[:50] or None,
            _parse_socrata_date(row.get("applied")),
            _parse_socrata_date(row.get("approved")),
            _parse_socrata_date(row.get("closed")),
            _parse_socrata_date(row.get("expired")),
            _parse_socrata_date(row.get("status_date")),
            (row.get("applied_by") or "").strip()[:200] or None,
            (row.get("approved_by") or "").strip()[:200] or None,
            (row.get("applied_affordability_level") or "").strip()[:100] or None,
            (row.get("approved_affordability_level") or "").strip()[:100] or None,
            (row.get("nbrhd_council") or "").strip()[:100] or None,
            _safe_numeric(row.get("latitude")),
            _safe_numeric(row.get("longitude")),
            "socrata_projects",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="project_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_projects",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_projects
            (city_fips, project_no, project_name, project_type, project_subtype,
             description, status, site_address, site_apn, site_zip,
             zoning_code, land_use, occupancy_description,
             resolution_no, parent_project_no,
             applied_date, approved_date, closed_date, expired_date, status_date,
             applied_by, approved_by,
             affordability_level_applied, affordability_level_approved,
             neighborhood_council, latitude, longitude,
             source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_project
            DO UPDATE SET
                status = EXCLUDED.status,
                approved_date = EXCLUDED.approved_date,
                closed_date = EXCLUDED.closed_date,
                expired_date = EXCLUDED.expired_date,
                status_date = EXCLUDED.status_date,
                approved_by = EXCLUDED.approved_by,
                affordability_level_approved = EXCLUDED.affordability_level_approved,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Projects",
    )


def _safe_numeric(val) -> float | None:
    """Safely parse a numeric value from Socrata."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    """Safely parse an integer value from Socrata."""
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


