"""NetFile Campaign Finance MCP Server.

Exposes California local campaign finance data via MCP tools.
Uses the NetFile Connect2 public API — no authentication required.

Covers ~220 agencies across California including cities, counties,
and special districts that use NetFile for campaign finance e-filing.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import (
    ALL_TYPES,
    CONTRIBUTION_TYPES,
    EXPENDITURE_TYPES,
    api_post,
    deduplicate_contributions,
    extract_filers,
    fetch_all_transactions,
    get_agencies as _get_agencies_raw,
    get_transaction_types as _get_transaction_types_raw,
    normalize_transaction,
    search_transactions,
)
from .registry import load_bundled_agencies, resolve_agency_id, search_agencies

mcp = FastMCP(
    "netfile-campaign-finance",
    instructions=(
        "Query California local campaign finance data from the NetFile Connect2 API. "
        "Covers ~220 agencies (cities, counties, special districts). "
        "No authentication required — all data is public. "
        "Use lookup_city to find an agency by name, then search_contributions to query."
    ),
)


@mcp.tool()
def search_contributions(
    city: str | None = None,
    agency_id: int | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    query: str | None = None,
    transaction_type: int | None = None,
    include_expenditures: bool = False,
    limit: int = 100,
) -> dict:
    """Search campaign finance contributions filed with NetFile.

    Specify either `city` (e.g. "Richmond", "San Francisco") or `agency_id` (e.g. 163).
    Returns normalized, deduplicated contribution records with summary statistics.

    Args:
        city: City or agency name to search (resolved via built-in registry)
        agency_id: NetFile agency ID (use lookup_city to find this)
        date_start: Filter contributions on or after this date (YYYY-MM-DD)
        date_end: Filter contributions on or before this date (YYYY-MM-DD)
        amount_min: Minimum contribution amount
        amount_max: Maximum contribution amount
        query: Free-text search (searches contributor names, employers, etc.)
        transaction_type: Specific FPPC transaction type ID (0=F460A monetary, 1=F460C non-monetary, etc.)
        include_expenditures: If true, also fetch expenditure records (types 6, 11, 21)
        limit: Maximum contributions to return (default 100). Summary stats reflect the full dataset regardless.
    """
    try:
        resolved_id, agency_name = resolve_agency_id(city=city, agency_id=agency_id)
    except ValueError as e:
        return {"error": str(e)}

    # Determine which transaction types to fetch
    if transaction_type is not None:
        type_ids = [transaction_type]
    elif include_expenditures:
        type_ids = list(ALL_TYPES.keys())
    else:
        type_ids = [0, 1]  # Monetary + non-monetary contributions

    # Fetch transactions
    all_raw: list[dict] = []
    total_available = 0
    for tid in type_ids:
        results, count = fetch_all_transactions(
            agency_id=resolved_id,
            transaction_type=tid,
            date_start=date_start,
            date_end=date_end,
            amount_low=amount_min,
        )
        all_raw.extend(results)
        total_available += count

    # Normalize and deduplicate
    contributions = [normalize_transaction(tx) for tx in all_raw]
    contributions = deduplicate_contributions(contributions)

    # Apply amount_max filter (API only supports amount_low)
    if amount_max is not None:
        contributions = [c for c in contributions if c["amount"] <= amount_max]

    # Filter zero-amount records
    contributions = [c for c in contributions if c["amount"] != 0]

    # Build summary from full dataset
    total_amount = sum(c["amount"] for c in contributions)
    dates = [c["date"] for c in contributions if c["date"]]
    unique_donors = len({c["contributor_name"].lower() for c in contributions if c["contributor_name"]})
    unique_committees = len({c["committee"].lower() for c in contributions if c["committee"]})

    summary = {
        "total_amount": round(total_amount, 2),
        "unique_donors": unique_donors,
        "unique_committees": unique_committees,
        "record_count": len(contributions),
    }
    if dates:
        summary["date_range"] = [min(dates), max(dates)]

    # Strip internal IDs from output to reduce noise
    clean_contributions = [
        {k: v for k, v in c.items() if k not in ("filer_fppc_id", "filer_local_id", "filing_id", "transaction_id", "source")}
        for c in contributions[:limit]
    ]

    return {
        "agency": {"id": resolved_id, "name": agency_name},
        "total_available": len(contributions),
        "returned": len(clean_contributions),
        "summary": summary,
        "contributions": clean_contributions,
    }


@mcp.tool()
def list_agencies(state: str | None = None) -> dict:
    """List all agencies that use NetFile for campaign finance e-filing.

    Returns the full list of ~220 agencies. Optionally filter by state
    (though most are California agencies).

    Args:
        state: Optional state abbreviation to filter by (e.g. "CA")
    """
    agencies = _get_agencies_raw()

    # Filter out the meta "All Agencies" entry
    agencies = [a for a in agencies if a.get("shortcut") != "SUPER"]

    if state:
        state_upper = state.upper()
        # NetFile doesn't have a state field, but some agency names include it
        # For now, return all (nearly all are CA)
        pass

    return {
        "count": len(agencies),
        "agencies": [
            {"id": a["id"], "shortcut": a.get("shortcut", ""), "name": a.get("name", "")}
            for a in agencies
        ],
    }


@mcp.tool()
def list_transaction_types() -> dict:
    """List all valid transaction type codes for NetFile searches.

    Returns the FPPC schedule codes used in campaign finance filings.
    Use these type IDs with the transaction_type parameter in search_contributions.
    """
    return {
        "contribution_types": {
            str(k): v for k, v in CONTRIBUTION_TYPES.items()
        },
        "expenditure_types": {
            str(k): v for k, v in EXPENDITURE_TYPES.items()
        },
        "descriptions": {
            "0": "F460A — Monetary Contributions Received (Schedule A)",
            "1": "F460C — Non-Monetary Contributions (Schedule C)",
            "6": "F460E — Payments Made (Schedule E)",
            "11": "F460F — Accrued Expenses (Unpaid Bills)",
            "20": "F497P1 — Late Contribution Report: Received",
            "21": "F497P2 — Late Contribution Report: Made",
        },
    }


@mcp.tool()
def get_committee_info(
    city: str | None = None,
    agency_id: int | None = None,
) -> dict:
    """Get campaign committees (filers) registered with a NetFile agency.

    Returns committee names, FPPC IDs, and local filing IDs.
    Specify either `city` or `agency_id`.

    Args:
        city: City or agency name (e.g. "Richmond", "Oakland")
        agency_id: NetFile agency ID
    """
    try:
        resolved_id, agency_name = resolve_agency_id(city=city, agency_id=agency_id)
    except ValueError as e:
        return {"error": str(e)}

    # Fetch a sample of recent transactions to extract filer metadata
    # Use type 0 (monetary contributions) as it has the most filings
    results, total = fetch_all_transactions(
        agency_id=resolved_id,
        transaction_type=0,
        page_size=1000,
    )

    normalized = [normalize_transaction(tx) for tx in results]
    filers = extract_filers(normalized)

    return {
        "agency": {"id": resolved_id, "name": agency_name},
        "committee_count": len(filers),
        "committees": sorted(filers, key=lambda f: f.get("name", "")),
    }


@mcp.tool()
def lookup_city(query: str) -> dict:
    """Look up a city or agency in the NetFile registry.

    Searches the bundled registry of ~220 agencies by name or shortcut code.
    Use this to find the correct agency_id before searching contributions.

    Args:
        query: City name, county name, or agency shortcut (e.g. "Richmond", "RICH", "San Francisco")
    """
    matches = search_agencies(query)

    if not matches:
        return {
            "matches": 0,
            "message": f"No agencies found matching '{query}'. Try a broader search or use list_agencies to see all.",
            "results": [],
        }

    return {
        "matches": len(matches),
        "results": [
            {"id": a["id"], "shortcut": a.get("shortcut", ""), "name": a.get("name", "")}
            for a in matches
        ],
    }


def main():
    """Entry point for the MCP server (stdio transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
