# Commissions & Board Members — Design

**Date:** 2026-02-22
**Status:** Approved
**Scope:** Data pipeline only (schema + seed data + website roster scraping + appointment extraction + commission meeting discovery/scraping). No frontend, scanner integration, or comment generator changes.
**Branch:** Will be assigned during implementation planning
**Parallel with:** City Leadership & Top Employees feature

## Goal

Build the data foundation for commission transparency: who sits on which commission, who appointed them, when their terms expire, and what those commissions discuss. Use council meeting minutes as source of truth for appointments. Scrape city website rosters as a baseline and detect when the website falls out of date relative to the minutes record. Discover and scrape commission meetings from eSCRIBE.

## Approach

**Minutes as SoT, website as snapshot.** Council meeting minutes are Tier 1 (official records). The city website roster is a point-in-time snapshot (Tier 3) used for seeding. When an appointment passes in minutes but the website roster doesn't reflect it, a staleness flag is generated. Monthly re-scraping of the website (cron wired later) detects when the website catches up, auto-resolving staleness flags.

## Sub-Phases

### B1: Schema + Seed Data + Website Roster Scraping

Create tables, seed reference data for Richmond's ~20 commissions, scrape current rosters from the city website.

### B2: Appointment Extraction from Council Minutes

Use Claude API to mine the 21 already-extracted council meeting JSONs for appointment/reappointment/resignation actions. These become the authoritative record. Flag discrepancies against website roster.

### B3: Commission Meeting Discovery + Scraping from eSCRIBE

Extend eSCRIBE scraper to discover all commission meeting types, catalog what's available, and scrape/extract content for high-priority commissions.

---

## Data Model

### New table: `commissions`

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | |
| `city_fips` | VARCHAR(7) NOT NULL | Multi-city scaling |
| `name` | VARCHAR(300) | "Planning Commission" |
| `commission_type` | VARCHAR(50) | `quasi_judicial` / `advisory` |
| `num_seats` | SMALLINT | Authorized number of seats |
| `appointment_authority` | VARCHAR(100) | `mayor` / `council` / `mayor_council` |
| `form700_required` | BOOLEAN | Economic interest disclosure required |
| `term_length_years` | SMALLINT | Standard term duration |
| `meeting_schedule` | VARCHAR(200) | Human-readable ("2nd Thursday monthly") |
| `escribemeetings_type` | VARCHAR(200) | eSCRIBE meeting type name for discovery |
| `archive_center_amid` | INTEGER (nullable) | Archive Center module ID |
| `website_roster_url` | VARCHAR(500) | URL for roster scraping |
| `last_website_scrape` | TIMESTAMP (nullable) | When we last scraped the roster |
| `created_at` | TIMESTAMP | |

### New table: `commission_members`

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | |
| `city_fips` | VARCHAR(7) NOT NULL | |
| `commission_id` | UUID FK → commissions | |
| `name` | VARCHAR(300) | |
| `normalized_name` | VARCHAR(300) | For matching |
| `role` | VARCHAR(50) | `chair` / `vice_chair` / `member` |
| `appointed_by` | VARCHAR(300) | Council member name or "Mayor" |
| `appointed_by_official_id` | UUID FK → officials (nullable) | Links to appointing council member |
| `term_start` | DATE (nullable) | |
| `term_end` | DATE (nullable) | |
| `is_current` | BOOLEAN | |
| `source` | VARCHAR(50) | `council_minutes` / `city_website` / `manual` |
| `source_meeting_id` | UUID FK → meetings (nullable) | Which meeting confirmed this appointment |
| `website_stale_since` | DATE (nullable) | Set when minutes show change website doesn't reflect |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

### New view: `v_commission_staleness`

Compares minutes-derived roster against latest website-scraped roster per commission. Returns commissions where discrepancies exist, with days-stale count and details of which members are mismatched.

### New view: `v_appointment_network`

Joins `commission_members` → `officials` via `appointed_by_official_id`. Maps which council members appointed which commissioners — reveals political appointment networks.

## Pipeline Modules

### New: `src/commission_roster_scraper.py` (Sub-phase B1)

Scrapes commission roster pages from richmond.ca.gov. For each commission:
1. Fetches the roster URL (stored in `commissions.website_roster_url`)
2. Parses member names, roles (chair/member), and any listed term dates
3. Stores with `source = 'city_website'`
4. Updates `commissions.last_website_scrape` timestamp

**CLI:**
```bash
python commission_roster_scraper.py --all                          # Scrape all commissions
python commission_roster_scraper.py --commission "Planning Commission"  # One commission
python commission_roster_scraper.py --output FILE                  # Save JSON
python commission_roster_scraper.py --load                         # Load to DB
```

### New: `src/appointment_extractor.py` (Sub-phase B2)

Uses Claude API to extract appointment actions from already-extracted council meeting JSONs:
1. Reads meeting JSONs from `src/data/extracted/`
2. Sends targeted extraction prompt per meeting: "Extract all commission/board appointment actions: person name, commission name, action type (appoint/reappoint/resign/remove), appointing official, term dates if mentioned"
3. Normalizes and matches commission names against `commissions` table
4. Stores with `source = 'council_minutes'` and `source_meeting_id` FK
5. After extraction, compares against website roster and sets `website_stale_since` on mismatches

**CLI:**
```bash
python appointment_extractor.py --meetings-dir src/data/extracted/   # All 21 meetings
python appointment_extractor.py --meeting src/data/extracted/FILE    # One meeting
python appointment_extractor.py --output FILE                       # Save JSON
python appointment_extractor.py --compare-website                   # Run staleness check
```

**Cost:** ~$0.50 total (21 meetings x ~$0.02 each, small focused prompt).

### Extended: `src/escribemeetings_scraper.py` (Sub-phase B3)

Add commission meeting support:
1. **New flag `--discover-types`:** Lists all unique meeting type names with counts and date ranges
2. **Commission type registry in city config:** Mapping from canonical commission name → eSCRIBE meeting type name
3. Commission meetings stored in existing `meetings` + `agenda_items` tables with appropriate `meeting_type`

**New city config field:**
```python
"commissions_escribemeetings": {
    "Planning Commission": "Planning Commission",
    "Rent Board": "Richmond Rent Board",
    # canonical name → eSCRIBE meeting type name
}
```

**New CLI usage:**
```bash
python escribemeetings_scraper.py --discover-types                              # What types exist?
python escribemeetings_scraper.py --meeting-type "Planning Commission" --list   # List all meetings
python escribemeetings_scraper.py --meeting-type "Planning Commission" --date 2026-02-01  # Scrape one
```

Commission meeting extraction reuses the existing Claude extraction pipeline (`extract_agenda.py`). Commission meetings may need a slightly adjusted prompt for commission-specific language patterns, but the schema output is identical.

## Seed Data

### `officials.json` extension

Add a `commissions` section with Richmond's commissions. High-priority quasi-judicial commissions fully populated; advisory commissions cataloged with minimal data:

```json
{
  "commissions": [
    {
      "name": "Planning Commission",
      "type": "quasi_judicial",
      "num_seats": 7,
      "appointment_authority": "mayor_council",
      "form700_required": true,
      "term_length_years": 4,
      "meeting_schedule": "1st and 3rd Thursday monthly",
      "website_roster_url": "https://www.ci.richmond.ca.us/...",
      "current_members": [
        {
          "name": "...",
          "role": "chair",
          "appointed_by": "Mayor Martinez"
        }
      ]
    }
  ]
}
```

### High-priority commissions (quasi-judicial, Form 700 required)

1. Planning Commission (7 seats)
2. Rent Board (5 seats)
3. Personnel Board (5 seats)
4. Design Review Board (5 seats)
5. Housing Authority (7 seats)
6. Police Commission (7 seats)

### Advisory commissions (catalog, minimal seeding)

Arts & Culture, Economic Development, Environment & Climate, Human Rights, Parks & Recreation, Youth Council, etc. (~15 additional commissions).

## Staleness Detection

**Flow:**
1. Website scrape creates baseline roster (`source = 'city_website'`)
2. Appointment extraction from minutes creates authoritative roster (`source = 'council_minutes'`)
3. Comparison logic identifies mismatches:
   - Person in minutes but not on website → `website_stale_since = appointment_date`
   - Person on website but resigned per minutes → same flag
   - All matching → clear any existing staleness flag (set `website_stale_since = NULL`)
4. Future monthly re-scrape (cron, wired later) re-runs comparison and auto-resolves when website catches up

**Key principle:** Staleness is an observation, not a bug. "The Planning Commission website hasn't reflected Commissioner X's appointment from 47 days ago" is a transparency finding. Factual, not judgmental.

## Migration

`src/migrations/004_commissions.sql` — idempotent. Creates both tables, indexes, both views. Shares migration number with city employees (or uses 005 if city employees takes 004 — implementation planning will assign).

## Cost

- Website scraping: $0 (HTML parsing, no API)
- Claude API for appointment extraction: ~$0.50 (21 meetings)
- eSCRIBE scraping: $0 (existing infrastructure)
- Claude API for commission meeting extraction: ~$0.07 per meeting
- Storage: Negligible

## What's NOT in this round

- Conflict scanner extensions (appointment chain checking, commissioner-donor matching)
- Form 700 cross-reference (separate feature)
- Frontend pages (commission directory, commissioner profiles, appointment network visualization)
- Comment generator integration for commission meetings
- Archive Center commission minutes (discovery only if time permits, not extraction)
- Cron job for monthly website re-scraping (schema + scraper built, cron wired later)

## Multi-City Scaling

Every US city has commissions/boards. The data model is generic (commission types, appointment authority, term structures are universal patterns). City config registry holds per-city commission metadata. eSCRIBE commission discovery works identically across all eSCRIBE cities. Website scraping is city-specific (HTML varies) but the schema and staleness logic are portable.

## Monetization Alignment

- **Path A (Freemium):** Citizens learn who oversees their city beyond just the council
- **Path B (Scaling):** All cities have commissions; eSCRIBE handles discovery automatically
- **Path C (Data):** Appointment network data is unique — no existing dataset maps council → commissioner → commission vote chains
