"""Agency registry for NetFile MCP server.

Provides name-based lookup against a bundled list of ~220 NetFile agencies,
so users can query by city name instead of agency ID.
"""
from __future__ import annotations

import json
from pathlib import Path

_AGENCIES_PATH = Path(__file__).parent / "agencies.json"
_cached_agencies: list[dict] | None = None


def load_bundled_agencies() -> list[dict]:
    """Load the bundled agencies.json file. Cached after first call."""
    global _cached_agencies
    if _cached_agencies is None:
        with open(_AGENCIES_PATH, encoding="utf-8") as f:
            _cached_agencies = json.load(f)
    return _cached_agencies


def search_agencies(
    query: str,
    agencies: list[dict] | None = None,
    state: str | None = None,
) -> list[dict]:
    """Search agencies by name or shortcut (case-insensitive substring match).

    Args:
        query: Search string (e.g. "Richmond", "RICH", "San Francisco")
        agencies: Agency list to search (defaults to bundled registry)
        state: Optional state filter (not in NetFile data, but some names include it)

    Returns:
        Matching agencies sorted by relevance (exact shortcut first, then name matches).
    """
    if agencies is None:
        agencies = load_bundled_agencies()

    query_lower = query.lower().strip()
    if not query_lower:
        return agencies

    # Skip the "All Agencies" meta-entry
    candidates = [a for a in agencies if a.get("shortcut", "") != "SUPER"]

    exact_shortcut: list[dict] = []
    name_matches: list[dict] = []

    for agency in candidates:
        shortcut = (agency.get("shortcut") or "").lower()
        name = (agency.get("name") or "").lower()

        if shortcut == query_lower:
            exact_shortcut.append(agency)
        elif query_lower in name:
            name_matches.append(agency)

    return exact_shortcut + name_matches


def resolve_agency(query: str, agencies: list[dict] | None = None) -> dict | None:
    """Resolve a query to a single agency.

    Returns the agency dict if exactly one match, None if zero or ambiguous.
    For ambiguous queries, callers should use search_agencies() and present options.
    """
    matches = search_agencies(query, agencies)
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_agency_id(
    city: str | None = None,
    agency_id: int | None = None,
) -> tuple[int, str | None]:
    """Resolve city name or agency_id to a confirmed (agency_id, agency_name).

    Raises ValueError with a helpful message if resolution fails.
    """
    if agency_id is not None:
        # Validate it exists in the registry
        agencies = load_bundled_agencies()
        for a in agencies:
            if a["id"] == agency_id:
                return agency_id, a.get("name")
        # Not in registry but may still be valid — let the API decide
        return agency_id, None

    if city is None:
        raise ValueError("Provide either 'city' (name) or 'agency_id' (integer).")

    matches = search_agencies(city)
    if len(matches) == 0:
        raise ValueError(
            f"No NetFile agency found matching '{city}'. "
            f"Use the lookup_city tool to search, or list_agencies to see all agencies."
        )
    if len(matches) == 1:
        return matches[0]["id"], matches[0].get("name")

    # Multiple matches — build helpful error
    options = "\n".join(
        f"  - {a['name']} (agency_id={a['id']}, shortcut={a.get('shortcut', '?')})"
        for a in matches[:10]
    )
    raise ValueError(
        f"Multiple agencies match '{city}':\n{options}\n\n"
        f"Use a more specific name or pass agency_id directly."
    )
