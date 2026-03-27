# OpenCorporates Integration Spec

**Date:** 2026-03-21
**Status:** Ready for implementation
**Publication Tier:** Graduated (operator-only → public after validation)
**Path Scoring:** A (entity transparency for citizens) + B (works for any city via jurisdiction codes) + C (structured entity data in core DB)

## Problem Statement

The LLC ownership chain detector and several conflict scanner signals (donor-vendor cross-reference, permit-donor, license-donor) need business entity resolution — given a name from campaign finance or permit records, determine whether it's an LLC/corporation, who the registered agent is, who the officers are, and whether the entity is active.

CA SOS has a RESTful API that provides this data, but API key approval has stalled indefinitely. The conflict scanner's entity resolution capability is blocked on this dependency.

## Proposed Solution

Integrate OpenCorporates API as the primary business entity resolution service. OpenCorporates aggregates data from CA SOS (and 144 other jurisdictions), provides it via a well-documented REST API, and offers free access for open data projects — which Richmond Commons qualifies for.

This replaces CA SOS API as the entity lookup layer. If CA SOS API access is eventually granted, it can be added as a secondary source behind the same abstraction.

### Why OpenCorporates over other alternatives

| Alternative | Verdict |
|---|---|
| CA SOS Master Unload ($100 bulk file) | Good for local cache later; doesn't solve on-demand lookup. Flat files need significant parsing. Consider as Phase 2 enhancement. |
| BizFile Online scraping | Fragile, maintenance-heavy, ToS risk. Avoid. |
| ProPublica Nonprofit Explorer | Already integrated. Covers nonprofits only — no LLCs, corps, LPs. Complementary, not a substitute. |
| OpenCorporates | Free for open data, REST API, covers all CA entity types, includes officer data, fully provenanced. Winner. |

## Data Source Profile

- **Source tier:** Tier 1 (OpenCorporates aggregates from official government registries; CA data sourced from CA SOS)
- **API base:** `https://api.opencorporates.com/v0.4/`
- **Auth:** API token as query parameter (`?api_token=TOKEN`)
- **Format:** JSON
- **Rate limits (free/open data tier):** 200 requests/month, 50 requests/day
- **License:** Share-alike attribution (ODbL). Attribution to OpenCorporates required. Compatible with Richmond Commons' transparency mission.
- **California jurisdiction code:** `us_ca`
- **Provenance:** Every response includes `source.publisher`, `source.url`, `retrieved_at` timestamps

## API Endpoints to Integrate

### 1. Company Search

```
GET /v0.4/companies/search?q={name}&jurisdiction_code=us_ca&api_token={token}
```

Use case: Conflict scanner has a contributor/vendor name — is it a registered business entity?

Key response fields:
- `company.name` — registered entity name
- `company.company_number` — CA SOS entity number (e.g., `C3268102`)
- `company.jurisdiction_code` — always `us_ca` when filtered
- `company.company_type` — "Domestic Stock", "Domestic LLC", "Foreign Stock", etc.
- `company.incorporation_date`
- `company.dissolution_date` (null if active)
- `company.current_status` — "Active", "Dissolved", "Suspended", etc.
- `company.registered_address_in_full`
- `company.opencorporates_url` — link to OC page (use as provenance URL)
- `company.source.publisher` — "California Secretary of State"
- `company.source.retrieved_at` — freshness timestamp

Search behavior: Case-insensitive, normalizes common company type abbreviations (Corp/Inc/Ltd), removes stop words. Returns paginated results ordered alphabetically (or by `order=score`).

### 2. Company Detail

```
GET /v0.4/companies/us_ca/{company_number}?api_token={token}
```

Use case: Enrich an entity match with full details — officers, filings, registered agent.

Additional fields beyond search:
- `company.officers` — array of officers with name, position, start/end dates
- `company.agent_name` — registered agent
- `company.agent_address`
- `company.previous_names` — array of prior entity names with date ranges
- `company.filings` — array of statutory filings
- `company.data` — additional data items (addresses, government supplier status, etc.)

Pass `sparse=true` to skip filings/data sections when only core entity info is needed (faster, smaller response).

### 3. Officer Search

```
GET /v0.4/officers/search?q={name}&jurisdiction_code=us_ca&api_token={token}
```

Use case: Reverse lookup — given a person's name, find what entities they're associated with.

Key response fields:
- `officer.name`
- `officer.position` — "director", "chief executive officer", "agent", "secretary", etc.
- `officer.start_date`, `officer.end_date`
- `officer.inactive` — boolean
- `officer.company.name`, `officer.company.company_number`, `officer.company.jurisdiction_code`

Search behavior: Loose matching — all searched words must appear but order doesn't matter. Case-insensitive.

**Important caveat:** Officer data completeness varies. Many fields (start_date, end_date, occupation) are frequently null. Do not treat absence of officer data as evidence of absence — CA SOS underlying data has up to 24-month reporting lag for LLCs.

## Database Schema

### Document Lake (Layer 1)

Store raw API responses for re-extraction:

```sql
-- Uses existing document_lake pattern
-- document_type: 'opencorporates_company' or 'opencorporates_officer_search'
-- source_url: OpenCorporates API URL called
-- raw_content: Full JSON response body
-- metadata JSONB: {company_number, jurisdiction_code, query_name, request_type}
```

### Structured Core (Layer 2)

New table for resolved business entities:

```sql
CREATE TABLE business_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    entity_number TEXT,                    -- CA SOS number (e.g., C3268102)
    jurisdiction_code TEXT NOT NULL,        -- e.g., us_ca
    entity_type TEXT,                       -- Domestic LLC, Domestic Stock, Foreign Stock, etc.
    current_status TEXT,                    -- Active, Dissolved, Suspended
    incorporation_date DATE,
    dissolution_date DATE,
    registered_address TEXT,
    agent_name TEXT,
    agent_address TEXT,
    opencorporates_url TEXT,
    source_url TEXT NOT NULL,
    source_publisher TEXT NOT NULL,         -- "California Secretary of State" (via OpenCorporates)
    source_tier INTEGER NOT NULL DEFAULT 1,
    retrieved_at TIMESTAMPTZ NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confidence_score NUMERIC(3,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_business_entities_city_fips ON business_entities(city_fips);
CREATE INDEX idx_business_entities_name ON business_entities(entity_name);
CREATE INDEX idx_business_entities_number ON business_entities(entity_number);
```

New table for entity officers (supports ownership chain and reverse lookups):

```sql
CREATE TABLE business_entity_officers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_entity_id UUID NOT NULL REFERENCES business_entities(id),
    officer_name TEXT NOT NULL,
    position TEXT,
    start_date DATE,
    end_date DATE,
    is_inactive BOOLEAN DEFAULT FALSE,
    opencorporates_officer_id BIGINT,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_entity_officers_entity ON business_entity_officers(business_entity_id);
CREATE INDEX idx_entity_officers_name ON business_entity_officers(officer_name);
```

### Entity-Name Linking Table

Bridge between names appearing in campaign finance / permits / contracts and resolved entities:

```sql
CREATE TABLE entity_name_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,             -- Name as it appears in source record
    source_table TEXT NOT NULL,            -- e.g., 'campaign_contributions', 'permits'
    source_record_id UUID NOT NULL,
    business_entity_id UUID REFERENCES business_entities(id),
    match_confidence NUMERIC(3,2) NOT NULL,
    match_method TEXT NOT NULL,            -- 'exact', 'normalized', 'fuzzy'
    reviewed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_name_matches_source ON entity_name_matches(source_name);
CREATE INDEX idx_name_matches_entity ON entity_name_matches(business_entity_id);
```

## Integration Architecture

### civic_sdk Module

Create `civic_sdk/sources/opencorporates.py`:

- `OpenCorporatesClient` class wrapping the API
- Rate limiter: enforce 50/day, 200/month limits locally before hitting API
- Response caching: check `business_entities` table before making API calls. Entity data changes slowly (LLC filings are biennial) — cache TTL of 90 days is reasonable.
- All methods accept `city_fips` parameter even though OpenCorporates doesn't use it — we tag every record we store with FIPS.

Key methods:
- `search_company(name: str, jurisdiction: str = "us_ca") -> list[CompanySearchResult]`
- `get_company(company_number: str, jurisdiction: str = "us_ca", sparse: bool = False) -> CompanyDetail`
- `search_officers(name: str, jurisdiction: str = "us_ca") -> list[OfficerSearchResult]`
- `resolve_entity(name: str, city_fips: str) -> EntityResolution` — high-level method that searches, fuzzy-matches, caches, and returns best match with confidence score

### Conflict Scanner Integration

The `resolve_entity` method plugs into existing conflict scanner signals:

1. **LLC ownership chain detector** — When a campaign contributor name looks like a business entity (contains LLC, Inc, Corp, LP, etc.), call `resolve_entity` → `get_company` (with officers). Cross-reference officer names against other contributor names, city officials, permit applicants.

2. **Donor-vendor cross-reference** — Resolve vendor names from contracts/expenditures to business entities. Resolve donor names from campaign contributions. Match on `entity_number` for definitive links or `officer_name` for indirect connections.

3. **Permit-donor / License-donor signals** — Resolve permit applicant business names to entities, then cross-reference officers against donor lists.

### Rate Limit Strategy

With 50 calls/day and 200/month, every API call is precious:

1. **Cache-first:** Always check local DB before calling API. Entity data is slow-moving.
2. **Batch during pipeline runs:** Don't resolve entities in real-time on the frontend. Run entity resolution as a pipeline step after new campaign finance or permit data is ingested.
3. **Prioritize by signal strength:** Only resolve names that pattern-match as business entities (regex for LLC/Inc/Corp/LP/LLP/Ltd suffixes) or that appear in multiple signal contexts.
4. **Track API budget:** Log every API call with timestamp. Surface remaining monthly/daily budget in pipeline status output.
5. **Degrade gracefully:** If budget is exhausted, queue unresolved entities for next day/month. Never block the pipeline on entity resolution.

### Name Matching

Campaign finance records use inconsistent entity naming. The resolution pipeline needs:

1. **Normalization:** Strip punctuation, normalize whitespace, uppercase, remove common suffixes (LLC, Inc, Corp, etc.) for comparison.
2. **Exact match:** Normalized source name == normalized OC entity name → confidence 0.95+
3. **Fuzzy match:** Use token-based similarity (not edit distance — entity names have variable-length components). Threshold at 0.80 for auto-match, 0.60–0.80 for operator review queue.
4. **Entity number anchoring:** If we ever get an entity number from another source (e.g., a permit application includes a CA SOS number), store it and use it for definitive matching bypassing name comparison entirely.

## Provenance & Attribution

Per D1 (every API response includes provenance metadata):

- `source_url`: The OpenCorporates API endpoint called
- `source_publisher`: "California Secretary of State" (the underlying data source, not OpenCorporates itself — but note OpenCorporates as the aggregator in methodology docs)
- `source_tier`: 1 (official government registry data, accessed via aggregator)
- `retrieved_at`: OpenCorporates' `retrieved_at` timestamp (when OC last pulled from CA SOS)
- `extracted_at`: When our pipeline processed the response
- `confidence_score`: Match confidence from the name resolution step

### Attribution requirement

OpenCorporates' open data license requires share-alike attribution. Add to the platform's data source methodology page:

> Business entity data sourced from OpenCorporates (opencorporates.com), which aggregates from official government registries including the California Secretary of State. Data licensed under the Open Database License (ODbL).

## Configuration

Environment variables:
- `OPENCORPORATES_API_TOKEN` — API token from open data application
- `OPENCORPORATES_DAILY_LIMIT` — default 50
- `OPENCORPORATES_MONTHLY_LIMIT` — default 200

## Acceptance Criteria

1. `OpenCorporatesClient` class in `civic_sdk/sources/` with search, detail, and officer methods
2. Rate limiter tracks daily/monthly usage, refuses calls when budget exhausted
3. Local caching: second lookup for same entity within TTL does not make an API call
4. `business_entities` and `business_entity_officers` tables created with all required provenance fields
5. `entity_name_matches` bridge table links source records to resolved entities with confidence scores
6. `resolve_entity()` high-level method handles normalization, search, matching, caching in one call
7. All records tagged with `city_fips`
8. Raw API responses stored in document lake for re-extraction
9. Pipeline logs remaining API budget after each call
10. Unit tests with mocked API responses covering: exact match, fuzzy match, no match, rate limit exceeded, API error

## Future Enhancements (Not In Scope)

- **CA SOS Master Unload bulk cache** — If rate limits become a real bottleneck, purchase the $100 bulk data file, parse flat files into `business_entities` table as a local cache. OpenCorporates then only needed for freshness checks on stale records.
- **CA SOS API integration** — If API key is ever granted, add as a `CASosClient` behind the same entity resolution interface. OpenCorporates remains the fallback.
- **Cross-jurisdiction resolution** — For Path B scaling, the `jurisdiction_code` parameter is already abstracted. Other cities just pass their state's jurisdiction code (e.g., `us_tx` for Texas).
- **MCP server for entity resolution** — Expose `resolve_entity` as an MCP tool for third-party civic tools.
