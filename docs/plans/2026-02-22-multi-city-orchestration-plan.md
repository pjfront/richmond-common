# Multi-City Orchestration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract all Richmond-specific configuration into a city registry so the pipeline can run for any city given a FIPS code and data source config.

**Architecture:** Create a single `city_config.py` module that maps FIPS codes to per-city configuration (URLs, agency IDs, council members, platform settings). All existing scrapers/clients accept a city config dict instead of reading module-level constants. The cloud pipeline, data sync, and staleness monitor route to the correct config by FIPS code. Richmond is the first (and currently only) entry, but adding a second city means adding a dict entry — not touching scraper code.

**Tech Stack:** Python (existing), JSON config, no new dependencies.

**Worktree:** `.worktrees/cloud-e-multi-city` (branch: `cloud-e/multi-city`)

**Merge order:** Merge AFTER `cloud-e/retire-local` branch. Rebase if needed.

**Estimated vibe-coding time:** 60–90 min across all tasks.

---

## Inventory: What's Hardcoded Today

32 Richmond-specific locations across 13 files. Key ones:

| File | What | Value |
|------|------|-------|
| `src/db.py:31` | `RICHMOND_FIPS` | `"0660620"` |
| `src/escribemeetings_scraper.py:57` | `BASE_URL` | `"https://pub-richmond.escribemeetings.com"` |
| `src/netfile_client.py:58-59` | `RICHMOND_AGENCY_ID` / `RICHMOND_AGENCY_SHORTCUT` | `163` / `"RICH"` |
| `src/nextrequest_scraper.py:38-39` | `BASE_URL` / `CITY_FIPS` | NextRequest URL |
| `src/archive_center_discovery.py:41,63-64` | `CIVICPLUS_BASE_URL`, `TIER_1_AMIDS`, `TIER_2_AMIDS` | Richmond URLs and AMIDs |
| `src/calaccess_client.py:46` | `CITY_FIPS` | `"0660620"` |
| `src/socrata_client.py:28,32` | `SOCRATA_DOMAIN` / `CITY_FIPS` | transparentrichmond.org |
| `src/conflict_scanner.py:89-105` | `CURRENT_COUNCIL_MEMBERS` / `FORMER_COUNCIL_MEMBERS` | 18 hardcoded names |
| `src/cloud_pipeline.py:41` | Imports `RICHMOND_FIPS` | Default city |
| `src/data_sync.py:34` | Imports `RICHMOND_FIPS` | Default city |
| `src/staleness_monitor.py:38` | Imports `RICHMOND_FIPS` | Default city |

---

## Task 1: Create City Config Registry

**Files:**
- Create: `src/city_config.py`
- Create: `tests/test_city_config.py`

The central registry. Every per-city value lives here. Scrapers import what they need from this module.

**Step 1: Write the failing tests**

```python
# tests/test_city_config.py
"""Tests for city configuration registry."""
import pytest
from city_config import (
    get_city_config,
    list_configured_cities,
    CityNotConfiguredError,
)


def test_get_richmond_config():
    cfg = get_city_config("0660620")
    assert cfg["fips_code"] == "0660620"
    assert cfg["name"] == "Richmond"
    assert cfg["state"] == "CA"
    assert "escribemeetings" in cfg["data_sources"]


def test_get_richmond_escribemeetings_url():
    cfg = get_city_config("0660620")
    assert cfg["data_sources"]["escribemeetings"]["base_url"] == "https://pub-richmond.escribemeetings.com"


def test_get_richmond_netfile_agency_id():
    cfg = get_city_config("0660620")
    nf = cfg["data_sources"]["netfile"]
    assert nf["agency_id"] == 163
    assert nf["agency_shortcut"] == "RICH"


def test_get_richmond_nextrequest_url():
    cfg = get_city_config("0660620")
    assert "nextrequest" in cfg["data_sources"]
    assert "cityofrichmondca" in cfg["data_sources"]["nextrequest"]["base_url"]


def test_get_richmond_archive_center():
    cfg = get_city_config("0660620")
    ac = cfg["data_sources"]["archive_center"]
    assert ac["base_url"] == "https://www.ci.richmond.ca.us"
    assert 31 in ac["tier_1_amids"] or 67 in ac["tier_1_amids"]


def test_get_richmond_calaccess():
    cfg = get_city_config("0660620")
    assert "calaccess" in cfg["data_sources"]


def test_get_richmond_socrata():
    cfg = get_city_config("0660620")
    assert cfg["data_sources"]["socrata"]["domain"] == "www.transparentrichmond.org"


def test_get_richmond_council_members():
    cfg = get_city_config("0660620")
    assert "council_members" in cfg
    current = cfg["council_members"]["current"]
    assert len(current) >= 7
    # Spot check a known member
    names = {m["name"] for m in current}
    assert "Eduardo Martinez" in names


def test_unknown_city_raises():
    with pytest.raises(CityNotConfiguredError):
        get_city_config("9999999")


def test_list_configured_cities():
    cities = list_configured_cities()
    assert len(cities) >= 1
    assert any(c["fips_code"] == "0660620" for c in cities)


def test_config_is_deep_copy():
    """Ensure callers can't mutate the registry."""
    cfg1 = get_city_config("0660620")
    cfg1["name"] = "MUTATED"
    cfg2 = get_city_config("0660620")
    assert cfg2["name"] == "Richmond"
```

**Step 2: Run tests to verify they fail**

Run: `cd /path/to/worktree && python3 -m pytest tests/test_city_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'city_config'`

**Step 3: Implement city_config.py**

```python
# src/city_config.py
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
            "socrata": {
                "platform": "Socrata (OpenData)",
                "domain": "www.transparentrichmond.org",
                "datasets": {
                    "expenditures": "resource_id_here",
                    "payroll": "resource_id_here",
                    "vendors": "resource_id_here",
                },
            },
        },
        "council_members": {
            "current": [
                {"name": "Eduardo Martinez", "role": "Mayor"},
                {"name": "Claudia Jimenez", "role": "Council Member"},
                {"name": "Gayle McLaughlin", "role": "Council Member"},
                {"name": "Soheila Bana", "role": "Council Member"},
                {"name": "Melvin Willis", "role": "Council Member"},
                {"name": "Doria Robinson", "role": "Council Member"},
                {"name": "Mark Wassberg", "role": "Council Member"},
            ],
            "former": [
                {"name": "Tom Butt"},
                {"name": "Nathaniel Bates"},
                {"name": "Ben Choi"},
                {"name": "Jovanka Beckles"},
                {"name": "Jael Myrick"},
                {"name": "Vinay Pimple"},
                {"name": "Corky Boozé"},
                {"name": "Ada Recinos"},
                {"name": "Ahmad Anderson"},
                {"name": "Cesar Zepeda"},
                {"name": "Sue Wilson"},
                {"name": "Demnlus Johnson"},
                {"name": "Nat Bates"},
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /path/to/worktree && python3 -m pytest tests/test_city_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/city_config.py tests/test_city_config.py
git commit -m "Phase 2: add city configuration registry with Richmond config"
```

---

## Task 2: Refactor eSCRIBE Scraper to Use City Config

**Files:**
- Modify: `src/escribemeetings_scraper.py` (lines 57-60, ~83)
- Modify: `tests/test_escribemeetings_scraper.py` (add config-aware test)

**Goal:** Replace hardcoded `BASE_URL` and `CITY_FIPS` with values from city config. The scraper still works exactly the same — it just gets its config from the registry instead of module constants.

**Step 1: Write the failing test**

```python
# Add to tests/test_escribemeetings_scraper.py
def test_scraper_accepts_city_config():
    """Scraper should accept city_fips and derive config from registry."""
    from city_config import get_data_source_config
    cfg = get_data_source_config("0660620", "escribemeetings")
    assert cfg["base_url"] == "https://pub-richmond.escribemeetings.com"
```

**Step 2: Modify escribemeetings_scraper.py**

Key changes:
- Keep `BASE_URL` and `CITY_FIPS` as module defaults (backward compat)
- Add optional `city_fips` parameter to key functions (`scrape_meeting`, `list_meetings`, etc.)
- When `city_fips` is provided, load config from registry; otherwise use module defaults
- Pattern: `def scrape_meeting(date, city_fips=None): cfg = _resolve_config(city_fips)`

```python
# Add near top of escribemeetings_scraper.py, after existing constants
def _resolve_config(city_fips: str | None = None) -> tuple[str, str]:
    """Resolve base_url and city_fips from registry or module defaults."""
    if city_fips is not None:
        from city_config import get_data_source_config
        cfg = get_data_source_config(city_fips, "escribemeetings")
        return cfg["base_url"], city_fips
    return BASE_URL, CITY_FIPS
```

Then thread `city_fips` parameter through `list_meetings()`, `scrape_meeting()`, and `create_session()`.

**Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -q --tb=short`
Expected: All 255+ tests PASS (no regressions)

**Step 4: Commit**

```bash
git add src/escribemeetings_scraper.py tests/test_escribemeetings_scraper.py
git commit -m "Phase 2: refactor eSCRIBE scraper to accept city config"
```

---

## Task 3: Refactor NetFile Client to Use City Config

**Files:**
- Modify: `src/netfile_client.py` (lines 58-60)
- Modify: `tests/test_netfile_client.py`

Same pattern as Task 2. Replace `RICHMOND_AGENCY_ID`, `RICHMOND_AGENCY_SHORTCUT`, `CITY_FIPS` with config-derived values. Add `city_fips` parameter to `fetch_contributions()`.

**Step 1: Add `_resolve_config` helper**

```python
def _resolve_config(city_fips: str | None = None) -> tuple[int, str, str]:
    """Resolve agency_id, agency_shortcut, city_fips from registry or defaults."""
    if city_fips is not None:
        from city_config import get_data_source_config
        cfg = get_data_source_config(city_fips, "netfile")
        return cfg["agency_id"], cfg["agency_shortcut"], city_fips
    return RICHMOND_AGENCY_ID, RICHMOND_AGENCY_SHORTCUT, CITY_FIPS
```

**Step 2: Thread `city_fips` through `fetch_contributions()`**

**Step 3: Run tests, commit**

```bash
git commit -m "Phase 2: refactor NetFile client to accept city config"
```

---

## Task 4: Refactor NextRequest Scraper to Use City Config

**Files:**
- Modify: `src/nextrequest_scraper.py` (lines 38-39)

Same pattern. Replace `BASE_URL` and `CITY_FIPS` with config-derived values.

```bash
git commit -m "Phase 2: refactor NextRequest scraper to accept city config"
```

---

## Task 5: Refactor Archive Center Discovery to Use City Config

**Files:**
- Modify: `src/archive_center_discovery.py` (lines 41, 63-64)

Replace `CIVICPLUS_BASE_URL`, `TIER_1_AMIDS`, `TIER_2_AMIDS`, `CITY_FIPS`.

```bash
git commit -m "Phase 2: refactor Archive Center discovery to accept city config"
```

---

## Task 6: Refactor CAL-ACCESS and Socrata Clients

**Files:**
- Modify: `src/calaccess_client.py` (line 46)
- Modify: `src/socrata_client.py` (lines 28, 32)

Same pattern for both. These are simpler — just `CITY_FIPS` and `SOCRATA_DOMAIN`.

```bash
git commit -m "Phase 2: refactor CAL-ACCESS and Socrata clients to accept city config"
```

---

## Task 7: Refactor Conflict Scanner Council Member Filter

**Files:**
- Modify: `src/conflict_scanner.py` (lines 89-105)
- Modify: `tests/test_conflict_scanner.py`

Replace hardcoded `CURRENT_COUNCIL_MEMBERS` and `FORMER_COUNCIL_MEMBERS` sets with a call to `get_council_member_names(city_fips)`. The scanner already receives `city_fips` in its config — just need to use it.

**Step 1: Write failing test**

```python
def test_scanner_loads_council_members_from_config():
    """Scanner should use city config for council member exclusion, not hardcoded sets."""
    from city_config import get_council_member_names
    current, former = get_council_member_names("0660620")
    assert "Eduardo Martinez" in current
    assert "Tom Butt" in former
```

**Step 2: Replace hardcoded sets**

```python
# In conflict_scanner.py, replace the hardcoded sets with:
def _get_council_members(city_fips: str) -> tuple[set, set]:
    """Get council member names for false positive filtering."""
    try:
        from city_config import get_council_member_names
        return get_council_member_names(city_fips)
    except Exception:
        # Fallback for backward compat (e.g., tests without full config)
        return set(), set()
```

**Step 3: Run full suite, commit**

```bash
git commit -m "Phase 2: refactor conflict scanner to load council members from city config"
```

---

## Task 8: Wire City Config into Cloud Pipeline and Data Sync

**Files:**
- Modify: `src/cloud_pipeline.py` (line 41, ~171, ~426)
- Modify: `src/data_sync.py` (line 34, ~333, ~419)
- Modify: `src/staleness_monitor.py` (line 38, ~136, ~245-246)

**Goal:** Replace `RICHMOND_FIPS` imports with city config lookups. The `--city-fips` CLI argument now validates against the registry.

**Step 1: Update cloud_pipeline.py**

```python
# Replace: from db import RICHMOND_FIPS
# With:
from city_config import get_city_config, list_configured_cities

DEFAULT_FIPS = "0660620"  # Richmond — keep as CLI default for backward compat
```

Add validation at pipeline entry:
```python
def run_cloud_pipeline(city_fips, ...):
    city_cfg = get_city_config(city_fips)  # Raises if not configured
    logger.info(f"Running pipeline for {city_cfg['name']} ({city_fips})")
    ...
```

**Step 2: Same pattern for data_sync.py and staleness_monitor.py**

**Step 3: Run full suite, commit**

```bash
git commit -m "Phase 2: wire city config into cloud pipeline, data sync, and staleness monitor"
```

---

## Task 9: Add `--list-cities` CLI Flag

**Files:**
- Modify: `src/cloud_pipeline.py`
- Modify: `src/data_sync.py`

Add a `--list-cities` flag that prints all configured cities and their available data sources, then exits. Useful for operators running the pipeline.

```python
if args.list_cities:
    for city in list_configured_cities():
        cfg = get_city_config(city["fips_code"])
        sources = ", ".join(cfg["data_sources"].keys())
        print(f"  {city['fips_code']}  {city['name']}, {city['state']}  [{sources}]")
    sys.exit(0)
```

```bash
git commit -m "Phase 2: add --list-cities CLI flag to pipeline and data sync"
```

---

## Task 10: Integration Test — Full Pipeline with City Config

**Files:**
- Create: `tests/test_city_config_integration.py`

End-to-end test verifying the pipeline can resolve config, build URLs, and pass them through without error.

```python
def test_full_pipeline_config_resolution():
    """Cloud pipeline should resolve all Richmond data sources from config."""
    from city_config import get_city_config
    cfg = get_city_config("0660620")

    # Verify all pipeline-required sources are present
    required = ["escribemeetings", "netfile", "calaccess", "archive_center"]
    for source in required:
        assert source in cfg["data_sources"], f"Missing required source: {source}"

    # Verify URLs are well-formed
    assert cfg["data_sources"]["escribemeetings"]["base_url"].startswith("https://")
    assert cfg["data_sources"]["netfile"]["agency_id"] > 0
    assert cfg["data_sources"]["archive_center"]["minutes_amid"] > 0


def test_config_default_fips_matches_richmond():
    """CLI defaults should still resolve to Richmond."""
    from city_config import get_city_config
    cfg = get_city_config("0660620")
    assert cfg["name"] == "Richmond"
```

```bash
git commit -m "Phase 2: add integration tests for city config pipeline resolution"
```

---

## Task 11: Update CLAUDE.md with Multi-City Architecture

Add a section documenting:
- The city config registry pattern
- How to add a new city
- Which data sources are per-city vs. shared
- The refactoring approach taken

```bash
git commit -m "Phase 2: document multi-city config architecture in CLAUDE.md"
```

---

## Files Changed Summary

| File | Change Type | Task |
|------|------------|------|
| `src/city_config.py` | **CREATE** | 1 |
| `tests/test_city_config.py` | **CREATE** | 1 |
| `tests/test_city_config_integration.py` | **CREATE** | 10 |
| `src/escribemeetings_scraper.py` | Modify | 2 |
| `src/netfile_client.py` | Modify | 3 |
| `src/nextrequest_scraper.py` | Modify | 4 |
| `src/archive_center_discovery.py` | Modify | 5 |
| `src/calaccess_client.py` | Modify | 6 |
| `src/socrata_client.py` | Modify | 6 |
| `src/conflict_scanner.py` | Modify | 7 |
| `src/cloud_pipeline.py` | Modify | 8, 9 |
| `src/data_sync.py` | Modify | 8, 9 |
| `src/staleness_monitor.py` | Modify | 8 |
| `CLAUDE.md` | Modify | 11 |

## Conflict Risk with Session A (`cloud-e/retire-local`)

**Low risk.** Session A touches:
- `.github/workflows/sync-pipeline.yml` (Session B doesn't touch workflows)
- `web/src/app/api/health/route.ts` (already done)
- `CLAUDE.md` (both sessions modify — merge Session A first, then rebase B)

**Only shared file:** `CLAUDE.md` — merge A first to avoid conflicts.

**`staleness_monitor.py`:** Session A already committed its changes (health check). Session B modifies different lines (RICHMOND_FIPS import → city_config import). Low conflict risk.
