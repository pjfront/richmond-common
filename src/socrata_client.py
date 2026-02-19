"""
Socrata API client for Transparent Richmond open data portal.

Portal: https://www.transparentrichmond.org/
API: SODA REST API (no auth required for public data, app token recommended)

Key datasets for transparency work:
  grq9-g484  Budgeted Expenses     — line-item budget by department/fund
  86qj-wgke  Expenditures          — actual spending with vendor, date, amount
  5mrn-7gkk  Vendors               — city vendor registry
  crbs-mam9  Payroll               — employee compensation records
  wvkf-uk4m  Budgeted Revenues     — revenue sources
  qg2r-652v  PermitTrak            — building/development permits
  jemu-q7zc  CodeTrak              — code enforcement cases
  6mmc-hvjg  CRMTrak               — constituent service requests
  vp6b-mw6u  ProjectTrak           — capital projects
  k4y4-5quj  RPD CAD Events        — police calls for service
  t3nu-7bbq  RPD Crime Incidents   — crime data
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional
from sodapy import Socrata

SOCRATA_DOMAIN = os.getenv("SOCRATA_DOMAIN", "www.transparentrichmond.org")
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN", None)

# FIPS code — always tag Richmond, CA data
CITY_FIPS = "0660620"

# Priority datasets for Phase 1
DATASETS = {
    "budgeted_expenses":  "grq9-g484",
    "expenditures":       "86qj-wgke",
    "vendors":            "5mrn-7gkk",
    "payroll":            "crbs-mam9",
    "budgeted_revenues":  "wvkf-uk4m",
    "permit_trak":        "qg2r-652v",
    "code_trak":          "jemu-q7zc",
    "crm_trak":           "6mmc-hvjg",
    "project_trak":       "vp6b-mw6u",
    "rpd_cad_events":     "k4y4-5quj",
    "rpd_crime_incidents":"t3nu-7bbq",
    "rpd_arrests":        "spqp-2m4t",
    "rpd_use_of_force":   "d62r-nicg",
    "rpd_complaints":     "wbyy-d6gi",
    "license_trak":       "5d4s-vbti",
}


def get_client() -> Socrata:
    """Create a Socrata client for Transparent Richmond."""
    return Socrata(SOCRATA_DOMAIN, SOCRATA_APP_TOKEN)


def query_dataset(
    dataset_key: str,
    where: Optional[str] = None,
    select: Optional[str] = None,
    order: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    """
    Query a Transparent Richmond dataset by friendly name.

    Args:
        dataset_key: Key from DATASETS dict (e.g., "expenditures")
        where: SoQL WHERE clause (e.g., "fiscalyear = '2025'")
        select: SoQL SELECT clause (e.g., "vendorname, SUM(actual)")
        order: SoQL ORDER BY clause (e.g., "actual DESC")
        limit: Max rows to return (default 1000, Socrata max is 50000)
        offset: Pagination offset

    Returns:
        List of result dicts
    """
    dataset_id = DATASETS.get(dataset_key)
    if not dataset_id:
        raise ValueError(
            f"Unknown dataset key '{dataset_key}'. "
            f"Available: {list(DATASETS.keys())}"
        )

    client = get_client()
    kwargs = {"limit": limit, "offset": offset}
    if where:
        kwargs["where"] = where
    if select:
        kwargs["select"] = select
    if order:
        kwargs["order"] = order

    results = client.get(dataset_id, **kwargs)
    return results


def get_dataset_metadata(dataset_key: str) -> dict:
    """Get column names, types, and description for a dataset."""
    dataset_id = DATASETS.get(dataset_key)
    if not dataset_id:
        raise ValueError(f"Unknown dataset key '{dataset_key}'")

    client = get_client()
    metadata = client.get_metadata(dataset_id)
    return metadata


def get_recent_expenditures(
    fiscal_year: str = "2026",
    min_amount: float = 10000,
    limit: int = 100,
) -> list[dict]:
    """Get large recent expenditures — useful for council meeting context."""
    return query_dataset(
        "expenditures",
        where=f"fiscalyear = '{fiscal_year}' AND actual > {min_amount}",
        select="vendorname, actual, description, organization, date, fund",
        order="actual DESC",
        limit=limit,
    )


def get_vendor_payments(vendor_name: str, limit: int = 100) -> list[dict]:
    """Get all payments to a specific vendor — useful for conflict detection."""
    return query_dataset(
        "expenditures",
        where=f"upper(vendorname) LIKE '%{vendor_name.upper()}%'",
        select="vendorname, actual, description, organization, date, fiscalyear, fund",
        order="date DESC",
        limit=limit,
    )


def get_department_budget(department: str, fiscal_year: str = "2026") -> list[dict]:
    """Get budget for a specific department."""
    return query_dataset(
        "budgeted_expenses",
        where=(
            f"fiscalyear = '{fiscal_year}' "
            f"AND upper(organization) LIKE '%{department.upper()}%'"
        ),
        select="organization, object, originalbudget, revisedbudget, actual, fund",
        order="actual DESC",
        limit=500,
    )


# ---- CLI for quick testing ----

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Query Transparent Richmond")
    parser.add_argument("dataset", help=f"Dataset key: {list(DATASETS.keys())}")
    parser.add_argument("--where", help="SoQL WHERE clause")
    parser.add_argument("--select", help="SoQL SELECT clause")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--list-columns", action="store_true", help="Show column info")
    args = parser.parse_args()

    if args.list_columns:
        meta = get_dataset_metadata(args.dataset)
        print(f"\nDataset: {meta.get('name')}")
        print(f"Description: {meta.get('description', 'N/A')}\n")
        for col in meta.get("columns", []):
            print(f"  {col['fieldName']:40s} {col['dataTypeName']:15s} {col.get('description', '')[:50]}")
    else:
        results = query_dataset(
            args.dataset,
            where=args.where,
            select=args.select,
            limit=args.limit,
        )
        print(f"\n{len(results)} results:\n")
        print(json.dumps(results, indent=2))
