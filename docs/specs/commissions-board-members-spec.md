# Commissions & Board Members Spec

*Created: 2026-02-20*
*Status: Draft — awaiting review before implementation*

---

## 1. Motivation

Richmond has **20+ boards and commissions** that make real decisions with minimal public scrutiny. The Planning Commission approves developments. The Personnel Board oversees city employment practices. The Rent Board adjudicates tenant-landlord disputes. The Police Commission provides civilian oversight.

These bodies share three characteristics:

1. **Decision-making authority.** Some are advisory, but many have binding power (Planning Commission, Rent Board).
2. **Form 700 filing requirements.** Commissioners with decision-making authority must file annual Statements of Economic Interests — the same filings that make conflict detection possible for council members.
3. **Near-zero public visibility.** No local journalist covers commission meetings. Residents don't know who sits on their Planning Commission, who appointed them, or what financial interests they've disclosed.

The conflict scanner we built for council meetings works for commission meetings too — same logic, same contribution data, different meeting body. The marginal effort to cover commissions is low; the marginal transparency value is high.

### What this enables

1. **Commission conflict detection:** Cross-reference commissioner Form 700 interests against items on their commission's agenda. "Commissioner [X] owns property within 500ft of the project under review."
2. **Appointment tracking:** Which council members appoint which commissioners? This reveals political networks — a progressive council member's appointees may vote differently than a business-aligned member's appointees.
3. **Commissioner profiles:** Voting records, attendance, appointment history, term expiration — the same information we build for council members, extended to 100+ commissioners.
4. **Document completeness:** "The Planning Commission has not published minutes for 3 of the last 5 meetings" — surfacing institutional accountability gaps.
5. **Cross-body influence mapping:** When a developer who donated to a council member's campaign appears before the Planning Commission, and that commissioner was appointed by that same council member — that's a connection worth surfacing.

### Monetization filter

- **Path A (Freemium):** Citizens can see who sits on their commissions, who appointed them, and what interests they've disclosed — ✓
- **Path B (Horizontal):** Every city has boards and commissions with similar structures — ✓
- **Path C (Data Infrastructure):** Structured commissioner data with appointment chains and Form 700 cross-references — ✓

All three. High priority.

---

## 2. Data Sources

### 2.1 Commission Rosters: Council Meeting Minutes (Already Extracted)

Council meetings include agenda items for commissioner appointments, reappointments, and resignations. We've already extracted 21 meetings — appointment data is embedded in that extraction output. Examples:

- "Mayor Martinez appointed [Name] to the Planning Commission"
- "Council accepted the resignation of [Name] from the Rent Board"
- "Reappointment of [Name] to the Design Review Board for a term ending [date]"

**Extraction approach:** Search existing extracted meeting JSONs for appointment-related agenda items (categories: `appointments_confirmations`, or title keywords: "appoint", "reappoint", "commission", "board", "resign").

### 2.2 Commission Meeting Agendas: eSCRIBE

The eSCRIBE portal (`pub-richmond.escribemeetings.com`) hosts commission meeting agendas alongside council meetings. The existing `escribemeetings_scraper.py` discovers meetings by type — we just need to expand beyond "Regular Meeting" to include commission meetings.

When we discovered 240 meetings in eSCRIBE (2020-2026), that included 217 regular council + 21 special + 2 swearing in. Commission meetings are separate meeting types in eSCRIBE.

### 2.3 Commission Meeting Minutes: Archive Center

Planning Commission minutes are available through the same Archive Center system as council minutes (different AMID). The `DATA-SOURCES.md` already identifies these:

- **Planning Commission Minutes** — same system, low difficulty
- **Rent Board Minutes** — same system, low difficulty

The `batch_extract.py` scraper works for any AMID — we just change the archive ID.

### 2.4 Form 700 Filings: FPPC + City Clerk

Commissioners with decision-making authority file Form 700s. These are available from:
- **FPPC website** (fppc.ca.gov) — statewide filings, PDF format
- **City Clerk** — local filings, may be on city website or available via CPRA request

Form 700 ingestion is already listed as a Phase 2 feature in PROJECT-SPEC.md. The commission spec benefits from that work but doesn't depend on it — we can track commissioners now and add Form 700 cross-referencing when that pipeline is built.

### 2.5 City Website: Commission Directory

Richmond's website lists current commission members at `ci.richmond.ca.us/Boards`. This provides a snapshot for seeding, though it may not be kept perfectly up-to-date.

### 2.6 Appointment Authority: City Charter / Municipal Code

Richmond's charter defines which commissions exist, how members are appointed (mayor vs. council vs. mixed), term lengths, and quorum requirements. This is reference data we seed once and update rarely.

---

## 3. Data Model

### 3.1 New Table: `commissions`

```sql
CREATE TABLE commissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),

    name VARCHAR(200) NOT NULL,
    normalized_name VARCHAR(200) NOT NULL,          -- lowercase, for matching
    short_name VARCHAR(50),                          -- 'Planning', 'Rent Board', etc.
    commission_type VARCHAR(50) NOT NULL,             -- 'administrative', 'quasi_judicial', 'advisory', 'oversight'
    established_by VARCHAR(200),                      -- 'City Charter Section X', 'Municipal Code Chapter Y', 'State Law'

    -- Composition
    num_seats SMALLINT,
    appointment_authority VARCHAR(100),               -- 'mayor', 'council', 'mixed', 'mayor_with_council_approval'
    term_length_years SMALLINT,
    term_limit SMALLINT,                              -- max consecutive terms, NULL if none

    -- Scheduling
    regular_meeting_schedule VARCHAR(200),             -- 'First Thursday of each month at 6:30 PM'
    meeting_location VARCHAR(300),

    -- Form 700
    form700_required BOOLEAN NOT NULL DEFAULT FALSE,  -- do members file economic interest statements?
    form700_disclosure_category VARCHAR(50),           -- FPPC disclosure category code

    -- Metadata
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    website_url TEXT,
    escribemeetings_meeting_type VARCHAR(100),         -- eSCRIBE meeting type name for scraper targeting
    archive_center_amid INTEGER,                       -- Archive Center AMID for minutes, NULL if none
    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_commission UNIQUE (city_fips, normalized_name)
);

CREATE INDEX idx_commissions_city ON commissions(city_fips);
CREATE INDEX idx_commissions_type ON commissions(commission_type);
CREATE INDEX idx_commissions_active ON commissions(city_fips) WHERE is_active = TRUE;
```

### 3.2 New Table: `commission_members`

```sql
CREATE TABLE commission_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    commission_id UUID NOT NULL REFERENCES commissions(id),

    -- Identity
    name VARCHAR(300) NOT NULL,
    normalized_name VARCHAR(300) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'member',       -- 'chair', 'vice_chair', 'member', 'alternate'

    -- Appointment
    appointed_by VARCHAR(200),                         -- 'Mayor Martinez', 'Council Member Brown', 'Council (at-large)'
    appointed_by_official_id UUID REFERENCES officials(id),  -- link to appointing council member
    appointment_date DATE,
    term_start DATE,
    term_end DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,

    -- Cross-references
    official_id UUID REFERENCES officials(id),         -- if this person is also an elected official
    employee_id UUID,                                  -- if this person is also a city employee (FK added after city_employees table exists)

    -- Source tracking
    source VARCHAR(50) NOT NULL,                       -- 'council_minutes', 'city_website', 'manual'
    source_meeting_date DATE,                          -- which council meeting recorded the appointment
    source_agenda_item VARCHAR(20),                    -- item number of the appointment action
    document_id UUID REFERENCES documents(id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_commission_member UNIQUE (commission_id, normalized_name, term_start)
);

CREATE INDEX idx_comm_members_city ON commission_members(city_fips);
CREATE INDEX idx_comm_members_commission ON commission_members(commission_id);
CREATE INDEX idx_comm_members_current ON commission_members(commission_id) WHERE is_current = TRUE;
CREATE INDEX idx_comm_members_appointed_by ON commission_members(appointed_by_official_id);
CREATE INDEX idx_comm_members_normalized ON commission_members(normalized_name);
```

### 3.3 Extension: `officials` Table

The existing `officials` table has `role VARCHAR(50)` currently limited to `'mayor', 'vice_mayor', 'councilmember'`. For commissioners who vote, we have two options:

**Option A (recommended):** Keep commissioners in `commission_members`, use `official_id` foreign key when a commissioner is also a council member. This maintains clean separation — commissioners aren't elected officials.

**Option B:** Extend `officials.role` to include `'commissioner'`, `'board_member'`. Simpler queries but muddies the semantics.

We go with **Option A.** The `commission_members` table is purpose-built. Votes on commission agendas get their own extraction and don't mix with council votes.

### 3.4 Ground Truth Extension: `officials.json`

```json
{
  "city_fips": "0660620",
  "current_council_members": [ ... ],
  "former_council_members": [ ... ],
  "city_leadership": [ ... ],
  "commissions": [
    {
      "name": "Planning Commission",
      "type": "quasi_judicial",
      "num_seats": 7,
      "appointment_authority": "mayor_with_council_approval",
      "form700_required": true,
      "term_length_years": 4,
      "archive_center_amid": null,
      "current_members": [
        {
          "name": "...",
          "role": "chair",
          "appointed_by": "Mayor Martinez",
          "term_end": "2027-06-30"
        }
      ]
    },
    {
      "name": "Personnel Board",
      "type": "quasi_judicial",
      "num_seats": 5,
      "appointment_authority": "mayor_with_council_approval",
      "form700_required": true,
      "term_length_years": 4,
      "notes": "Phillip Front sits on this board"
    },
    {
      "name": "Richmond Rent Board",
      "type": "quasi_judicial",
      "num_seats": 5,
      "appointment_authority": "council",
      "form700_required": true,
      "term_length_years": 4
    }
  ]
}
```

### 3.5 View: Appointment Network

```sql
-- Who appoints whom? Maps the political network from council to commissions.
CREATE VIEW v_appointment_network AS
SELECT
    cm.city_fips,
    c.name AS commission_name,
    c.commission_type,
    cm.name AS commissioner_name,
    cm.role AS commissioner_role,
    cm.appointed_by,
    o.name AS appointing_official_name,
    o.role AS appointing_official_role,
    cm.appointment_date,
    cm.term_end,
    cm.is_current
FROM commission_members cm
JOIN commissions c ON cm.commission_id = c.id
LEFT JOIN officials o ON cm.appointed_by_official_id = o.id
ORDER BY c.name, cm.appointment_date DESC;
```

---

## 4. Ingestion Pipeline

### 4.1 Phase A: Extract Appointments from Existing Council Data

Mine the 21 already-extracted council meetings for appointment actions.

New module: `src/commission_extractor.py`

```python
def extract_appointments_from_meetings(meeting_jsons: list[Path]) -> list[dict]:
    """
    Scan extracted meeting JSONs for commission appointment actions.

    Search criteria:
    - agenda_items where category == 'appointments_confirmations'
    - agenda_items where title contains: 'appoint', 'reappoint', 'commission',
      'board', 'resign', 'vacancy', 'term'
    - Closed session items mentioning 'appointment'

    For each match, extract:
    - commissioner name
    - commission name
    - action type: 'appointment', 'reappointment', 'resignation', 'removal'
    - appointing authority (from item context or motion)
    - term dates if mentioned
    - vote result

    Returns list of appointment records.
    """

def build_commission_roster(appointments: list[dict]) -> dict[str, list[dict]]:
    """
    From a chronological list of appointment actions, reconstruct the
    current roster for each commission.

    Logic:
    - Start with earliest appointment
    - Track appointment → reappointment → resignation/removal chains
    - Mark current members based on: no resignation/removal AND term_end >= today

    This produces a snapshot that can be validated against the city website.
    """
```

### 4.2 Phase B: Scrape Commission Meeting Agendas from eSCRIBE

Extend `escribemeetings_scraper.py` to discover and scrape commission meetings.

```python
# The existing scraper discovers meetings with:
#   POST /MeetingsCalendarView.aspx/GetCalendarMeetings
# Response includes meeting_type_name field.
#
# Current filter: only "Regular Meeting" types for council.
# Extension: also scrape meetings where meeting_type_name matches
# known commission names.

COMMISSION_MEETING_TYPES = [
    "Planning Commission",
    "Rent Board",
    "Personnel Board",
    "Design Review Board",
    "Police Commission",
    "Housing Authority",
    # ... populated from eSCRIBE discovery
]
```

### 4.3 Phase C: Scrape Commission Minutes from Archive Center

Different AMIDs for different bodies. Need to discover these — likely:
- Planning Commission: unknown AMID (query Archive Center)
- Rent Board: unknown AMID
- Others: may not have archived minutes

The `batch_extract.py` already parameterizes AMID. Once we know the IDs, extraction uses the same pipeline.

### 4.4 Phase D: Commission Meeting Extraction

Reuse the Claude Sonnet extraction pipeline (`src/extraction.py`) for commission meeting minutes. The extraction prompt may need slight modifications:

- Commission "votes" may use different terminology ("motion carried", "approved", "denied")
- Quorum rules differ per commission
- Some commissions are advisory (no binding votes)
- Chair may have different procedural powers

The extraction schema is largely the same: agenda items, motions, votes, attendance, public comments.

### 4.5 Phase E: Form 700 Cross-Reference (Future)

When the Form 700 ingestion pipeline is built (separate Phase 2 feature):
1. Match commissioner names against Form 700 filers
2. Cross-reference disclosed interests against commission agenda items
3. Flag potential conflicts using the same `conflict_scanner.py` logic

This is the highest-value integration — commissioners making decisions that affect their disclosed financial interests — but depends on Form 700 data availability.

---

## 5. Integration with Existing Pipeline

### 5.1 Conflict Scanner: Commission Mode

The conflict scanner needs a minor extension to work for commission agendas:

```python
def scan_commission_agenda(
    agenda_json: dict,
    commission_name: str,
    contributions: list[dict],
    form700_data: list[dict] | None = None,
    commission_members: list[dict] | None = None,
) -> ScanResult:
    """
    Same logic as scan_meeting_json(), with commission-specific adjustments:

    1. Match donors/employers against agenda item text (existing logic)
    2. Match commissioner names against donor list (are commissioners donors?)
    3. Match commissioner Form 700 interests against agenda items (if available)
    4. Check appointment chain: does the appointing council member have
       a financial relationship with any entity in the agenda item?

    The fourth check is unique to commissions — it surfaces indirect
    influence where a council member's appointee votes on matters
    related to the council member's donors.
    """
```

### 5.2 Comment Generator: Commission Meetings

The `comment_generator.py` currently targets council meetings. Extension:
- Same comment format, different meeting body reference
- Include commissioner appointment context when relevant
- Note which commissions require Form 700 filings
- "Commissioner [X] was appointed by Council Member [Y], who received contributions from [entity] appearing in this agenda item."

### 5.3 Council Profiles: Appointment Records

`council_profiles.py` can include an "Appointments" section per council member:
- Which commissions they've appointed members to
- Current appointees and their term dates
- Appointment patterns (does this member favor certain types of appointees?)

### 5.4 Frontend (Phase 2)

- **Commission directory:** All commissions with current members, meeting schedule, Form 700 status
- **Commissioner profiles:** Appointment history, voting record (if extracted), Form 700 summary
- **Appointment network visualization:** Interactive graph showing council → commissioner appointment chains
- **Commission meeting pages:** Same format as council meeting pages, with agenda items, votes, conflicts

---

## 6. Richmond-Specific Commission Inventory

A non-exhaustive list of Richmond boards and commissions. Need to verify current status and Form 700 requirements for each.

### Quasi-Judicial (Decision-Making Authority, Form 700 Required)

| Commission | Seats | Appointment | Notes |
|-----------|-------|-------------|-------|
| Planning Commission | 7 | Mayor w/ council approval | Land use, development, zoning |
| Rent Board | 5 | Council | Rent stabilization, eviction protections |
| Personnel Board | 5 | Mayor w/ council approval | Employment appeals, civil service rules. Phillip sits here. |
| Design Review Board | 5 | Mayor w/ council approval | Architectural review of new development |
| Housing Authority | 7 | Mayor | Public housing oversight |
| Police Commission | 7 | Mayor + Council | Civilian police oversight |

### Advisory (May or May Not Require Form 700)

| Commission | Notes |
|-----------|-------|
| Arts and Culture Commission | Public art, cultural programming |
| Commission on Aging | Senior services |
| Human Rights & Human Relations Commission | Civil rights |
| Recreation & Parks Commission | Parks, recreation facilities |
| Youth Council | Youth engagement, advisory |
| Economic Development Commission | Business development, job creation |

### Key Unknowns (to research during implementation)

- Exact number of active commissions
- Which advisory commissions require Form 700
- eSCRIBE meeting type names for each commission
- Archive Center AMIDs for commission minutes (if any)
- Current complete rosters (city website may be stale)

---

## 7. Implementation Plan

### Step 1: Seed Commission Reference Data
- Research Richmond's active commissions from city charter + website
- Populate `commissions` section in `officials.json`
- Focus on quasi-judicial commissions first (Planning, Rent Board, Personnel Board)

### Step 2: Extract Appointments from Existing Meetings
- `src/commission_extractor.py` — mine 21 extracted council meetings for appointment actions
- Build initial roster from appointment history
- Validate against city website

### Step 3: Schema Additions
- Add `commissions` and `commission_members` tables to `src/schema.sql`
- Add `v_appointment_network` view
- Include `city_fips` on everything (non-negotiable)

### Step 4: Discover Commission Meetings in eSCRIBE
- Extend scraper to list all meeting types
- Identify which types correspond to commissions
- Pull sample agenda from Planning Commission to validate parsing

### Step 5: Commission Agenda Extraction
- Test existing extraction prompt on a commission agenda
- Adjust prompt if needed for commission-specific language
- Extract 3-5 commission meetings as proof of concept

### Step 6: Conflict Scanner — Commission Mode
- Add `scan_commission_agenda()` to `conflict_scanner.py`
- Test against Planning Commission agenda with combined contribution data
- Include appointment chain checking

### Step 7: Commission Minutes from Archive Center (if available)
- Discover AMIDs for commission minutes
- Pull and extract historical commission minutes using existing pipeline

---

## 8. What This Spec Does NOT Cover

- **Board of Supervisors (County)** — Contra Costa County oversight is a different scope. Future work for county-level expansion.
- **School board** — West Contra Costa Unified School District has its own board. Different entity, different data sources. Worth considering as a parallel track.
- **Special districts** — East Bay Regional Parks, EBMUD, AC Transit, etc. Each has its own governance structure. Phase 4+ scope.
- **Commission meeting video/audio** — Transcription pipeline is separate and depends on Granicus/video access.
- **Commissioner campaign contributions** — Commissioners don't run campaigns. But they may *donate* to council member campaigns, which is tracked in existing contribution data and would surface in the appointment chain analysis.

---

## 9. File Locations

| Artifact | Path |
|----------|------|
| This spec | `docs/specs/commissions-board-members-spec.md` |
| Commission extractor | `src/commission_extractor.py` |
| Schema additions | `src/schema.sql` (append) |
| Ground truth seed | `src/ground_truth/officials.json` (extend) |
| eSCRIBE scraper (extend) | `src/escribemeetings_scraper.py` |
| Conflict scanner (extend) | `src/conflict_scanner.py` |
| Comment generator (extend) | `src/comment_generator.py` |
