"""
City configuration registry.

Central source of truth for per-city data source URLs, agency IDs,
platform settings, and officials. All scrapers/clients import from here
instead of hardcoding Richmond-specific values.

Adding a new city: add an entry to CITY_REGISTRY below.
"""
from __future__ import annotations

import copy
from typing import Any


class CityNotConfiguredError(Exception):
    """Raised when requesting config for a city not in the registry."""
    pass


# ── Registry ─────────────────────────────────────────────────

CITY_REGISTRY: dict[str, dict[str, Any]] = {
    "0660620": {
        "fips_code": "0660620",
        "name": "Richmond",
        "state": "CA",
        "county": "Contra Costa",
        "council_size": 7,
        "meetings_per_year": 24,
        "data_sources": {
            "escribemeetings": {
                "platform": "eSCRIBE",
                "base_url": "https://pub-richmond.escribemeetings.com",
                "calendar_endpoint": "/MeetingsCalendarView.aspx/GetCalendarMeetings",
                "meeting_page": "/Meeting.aspx?Id={meeting_id}&Agenda=Agenda&lang=English",
                "document_endpoint": "/filestream.ashx?DocumentId={doc_id}",
            },
            "netfile": {
                "platform": "NetFile Connect2",
                "agency_id": 163,
                "agency_shortcut": "RICH",
                "api_base": "https://netfile.com/Connect2/api",
                "public_portal": "https://public.netfile.com/pub2/?AID=RICH",
                "adopted_year": 2018,
            },
            "nextrequest": {
                "platform": "NextRequest",
                "base_url": "https://cityofrichmondca.nextrequest.com",
                "city_slug": "cityofrichmondca",
            },
            "archive_center": {
                "platform": "CivicPlus (CivicEngage)",
                "base_url": "https://www.ci.richmond.ca.us",
                "archive_path": "/ArchiveCenter/",
                "document_path": "/Archive.aspx?ADID={adid}",
                "minutes_amid": 31,
                "tier_1_amids": [67, 66, 87, 132, 133],
                "tier_2_amids": [168, 169, 61, 77, 78, 75],
            },
            "calaccess": {
                "platform": "CAL-ACCESS",
                "search_keywords": ["richmond", "contra costa"],
                "notes": "Statewide bulk download, filtered by keyword match",
            },
            "commissions_escribemeetings": {
                # Map: canonical name → eSCRIBE MeetingName value
                # Run: python escribemeetings_scraper.py --discover-types
                # to find the exact MeetingName strings for each commission.
                "Planning Commission": "Planning Commission",
                "Rent Board": "Richmond Rent Board",
                "Design Review Board": "Design Review Board",
                "Police Commission": "Police Commission",
                "Housing Authority": "Housing Authority Board of Commissioners",
            },
            "form700": {
                "platform": "NetFile SEI + FPPC DisclosureDocs",
                "netfile_sei_url": "https://public.netfile.com/pub/?AID=RICH",
                "netfile_sei_agency_id": "RICH",
                "fppc_search_url": "https://form700search.fppc.ca.gov/Search/SearchFilerForms.aspx",
                "fppc_agency_name": "City of Richmond",
                "fppc_edisclosure_url": "https://form700.fppc.ca.gov/",
                "credibility_tier": 1,
                "adopted_year": 2018,
                "notes": "NetFile SEI for local filers (2018+). FPPC for 87200 filers. eDisclosure mandatory from 2025.",
            },
            "socrata": {
                "platform": "Socrata (OpenData)",
                "domain": "www.transparentrichmond.org",
                "datasets": {
                    "budgeted_expenses": "grq9-g484",
                    "expenditures": "86qj-wgke",
                    "vendors": "5mrn-7gkk",
                    "payroll": "crbs-mam9",
                    "budgeted_revenues": "wvkf-uk4m",
                },
            },
        },
        "council_members": {
            # Source of truth: src/ground_truth/officials.json (updated 2026-02-19)
            "current": [
                {"name": "Eduardo Martinez", "role": "Mayor"},
                {"name": "Cesar Zepeda", "role": "Vice Mayor", "district": 2},
                {"name": "Jamelia Brown", "role": "Council Member", "district": 1},
                {"name": "Doria Robinson", "role": "Council Member", "district": 3},
                {"name": "Soheila Bana", "role": "Council Member", "district": 4},
                {"name": "Sue Wilson", "role": "Council Member", "district": 5},
                {"name": "Claudia Jimenez", "role": "Council Member", "district": 6},
            ],
            "former": [
                {"name": "Tom Butt"},
                {"name": "Nat Bates"},
                {"name": "Jovanka Beckles"},
                {"name": "Ben Choi"},
                {"name": "Jael Myrick"},
                {"name": "Vinay Pimple"},
                {"name": "Corky Booze"},
                {"name": "Jim Rogers"},
                {"name": "Ahmad Anderson"},
                {"name": "Oscar Garcia"},
                {"name": "Gayle McLaughlin"},
                {"name": "Melvin Willis"},
                {"name": "Shawn Dunning"},
            ],
        },
    },
}


# ── Public API ───────────────────────────────────────────────

def get_city_config(fips_code: str) -> dict[str, Any]:
    """Get configuration for a city by FIPS code. Returns a deep copy."""
    if fips_code not in CITY_REGISTRY:
        raise CityNotConfiguredError(
            f"No configuration for FIPS code '{fips_code}'. "
            f"Configured cities: {list_configured_cities()}"
        )
    return copy.deepcopy(CITY_REGISTRY[fips_code])


def list_configured_cities() -> list[dict[str, str]]:
    """List all configured cities (fips_code, name, state)."""
    return [
        {"fips_code": cfg["fips_code"], "name": cfg["name"], "state": cfg["state"]}
        for cfg in CITY_REGISTRY.values()
    ]


def get_data_source_config(fips_code: str, source: str) -> dict[str, Any]:
    """Get config for a specific data source for a city."""
    cfg = get_city_config(fips_code)
    sources = cfg.get("data_sources", {})
    if source not in sources:
        raise CityNotConfiguredError(
            f"City '{cfg['name']}' ({fips_code}) has no '{source}' data source configured. "
            f"Available: {list(sources.keys())}"
        )
    return sources[source]


def get_council_member_names(fips_code: str) -> tuple[set[str], set[str]]:
    """Get (current_names, former_names) sets for conflict scanner filtering."""
    cfg = get_city_config(fips_code)
    members = cfg.get("council_members", {})
    current = {m["name"] for m in members.get("current", [])}
    former = {m["name"] for m in members.get("former", [])}
    return current, former
