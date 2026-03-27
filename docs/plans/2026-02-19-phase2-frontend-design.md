# Phase 2 Frontend Design — Richmond Commons

*Date: 2026-02-19*
*Status: Approved*

---

## Overview

Build a public-facing web frontend that makes the Phase 1 data pipeline visible to Richmond residents. This is the first milestone of Phase 2: "Other people can use it."

**Goal:** Launch a read-only website where anyone can browse council meetings, view council member profiles with voting records and donor data, and read pre-meeting transparency reports.

**Success metric:** Live at a public URL with all 21 extracted meetings, 27,035 contribution records, and conflict scanner output accessible.

---

## Architecture

### Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Frontend | Next.js 14+ (App Router) | React Server Components, ISR, Vercel-native |
| Database | Supabase (PostgreSQL + pgvector) | Managed Postgres, pgvector pre-installed, free tier covers Phase 2 |
| Hosting | Vercel | Preview deploys, edge caching, seamless Next.js integration |
| Styling | Tailwind CSS | Utility-first, fast iteration on editorial layouts |
| Auth | None (MVP) | All data is public. Auth added later for subscriptions/alerts |

### Data Flow

**Stage 1 — Batch loader (launch):**
```
Pipeline (Python, manual run)
    → db.py load <json_file>
    → Supabase PostgreSQL
    → Next.js Server Components (ISR, revalidate hourly)
    → Vercel CDN
```

**Stage 2 — Automated sync (before Phase 2 complete):**
```
Scheduled trigger (n8n / GitHub Actions / cron)
    → eSCRIBE scrape → Claude extraction → conflict scan
    → db.py load
    → Supabase PostgreSQL
    → Next.js ISR auto-revalidates
```

### Rendering Strategy

**Incremental Static Regeneration (ISR):**
- Pages are server-rendered on first request, then cached at the Vercel edge
- Revalidation period: 1 hour (configurable)
- No client-side API calls needed for MVP pages
- Combines static-site speed with database freshness

---

## Design Language

**Modern editorial with civic credibility.** ProPublica meets The Markup.

### Visual Identity

- **Typography:** Bold sans-serif headings (Inter or similar system font stack). Clean body text with strong hierarchy.
- **Color palette:**
  - Primary: Navy (#1e3a5f) — civic authority
  - Secondary: Slate (#475569) — readable body text
  - Background: White (#ffffff) + light gray (#f8fafc) for alternating sections
  - Accent: Amber/orange (#d97706) — warnings, conflict flags
  - Success: Green (#059669) — passed votes, clean items
  - Danger: Red (#dc2626) — failed votes, high-confidence flags
- **Layout:** Card-based with generous whitespace. Content-first, scannable.
- **Data visualization:** Styled data tables that feel like news graphics, not spreadsheets. Color-coded badges for vote outcomes and conflict tiers.

---

## Pages & Information Architecture

### 1. Homepage (`/`)

**Purpose:** Explain what Richmond Commons is, surface latest data, drive navigation.

**Content:**
- Hero: Mission one-liner + "Your city government, in one place and in plain language."
- Stats bar: meetings tracked, votes recorded, conflicts flagged, contributions cross-referenced
- Latest meeting card with key highlights
- "How it works" — 3-step visual (Ingest → Analyze → Publish)
- Quick links to meetings, council, transparency reports
- Footer: methodology link, data sources, disclaimers

### 2. Meetings List (`/meetings`)

**Purpose:** Chronological index of all tracked council meetings.

**Content:**
- Filterable by year (2025, 2026)
- Each meeting card shows: date, type, number of agenda items, number of votes, attendance count
- Badge if transparency report exists for that meeting
- Sorted newest-first

### 3. Meeting Detail (`/meetings/[date]`)

**Purpose:** Full extracted data for a single meeting. The most complex page.

**Content:**
- Header: meeting date, type, attendance summary
- Transparency report callout (if flags exist): "N potential conflicts flagged — view report"
- Attendance roster: present/absent with visual indicators
- Consent calendar section: collapsible list of consent items with pass/fail
- Regular agenda section: expandable cards per item showing:
  - Item number and title
  - Description/summary
  - Motion text, moved by, seconded by
  - Vote breakdown (per council member) with color coding
  - Conflict flag badge (if applicable) linking to transparency report
  - Category badge (housing, budget, public_safety, etc.)

### 4. Council Members (`/council`)

**Purpose:** Grid/list of current (and former) council members.

**Content:**
- Card per council member: name, seat/district, photo placeholder, term dates
- Key stats: votes tracked, attendance rate, number of conflict flags
- Toggle between current and former members
- Link to individual profile page

### 5. Council Member Detail (`/council/[slug]`)

**Purpose:** Comprehensive profile built from council_profiles.py data + contribution data.

**Content:**
- Header: name, seat, term, photo placeholder
- Voting summary: total votes, attendance %, top categories
- Top donors table: name, amount, source (CAL-ACCESS/NetFile)
- Conflict flags: list of flagged items across all scanned meetings
- Full voting record: filterable/sortable table (date, meeting, item, vote, category)
- Coalition analysis: who this member votes with most on split votes

### 6. Transparency Reports (`/reports`)

**Purpose:** The flagship feature — pre-meeting conflict analysis made public.

**Content:**
- List of reports by meeting date
- Each report shows:
  - Meeting date and number of items scanned
  - Tier 1 findings (Potential Conflicts) — full detail with citations
  - Tier 2 findings (Financial Connections) — full detail with citations
  - Tier 3 (low confidence) — NOT shown publicly, tracked internally only
  - Clean items summary ("N items scanned with no findings")
  - Methodology section: how the scanner works, data sources, confidence tiers
  - Link to submitted public comment (if applicable)

### 7. About / Methodology (`/about`)

**Purpose:** Build credibility. Explain how everything works.

**Content:**
- What Richmond Commons is and isn't (governance assistant, not adversarial)
- Source credibility tiers (Tier 1-4 explained)
- How the conflict scanner works (matching logic, thresholds, bias audit)
- Data sources: CAL-ACCESS, NetFile, eSCRIBE, Archive Center
- Limitations and disclaimers
- Who built this (the operator, city government context)
- Open source / methodology transparency

---

## Database Migration

### Approach

Deploy existing `schema.sql` to Supabase. Extend `db.py` to accept a Supabase connection string.

### Tables Populated at Launch

| Table | Source | Record Count (est.) |
|-------|--------|-------------------|
| `cities` | Seed | 1 (Richmond) |
| `officials` | `ground_truth/officials.json` + extraction | ~20 (7 current + 13 former) |
| `meetings` | 21 extracted JSONs | 21 |
| `agenda_items` | Extracted from meetings | ~500+ |
| `motions` | Extracted from meetings | ~300+ |
| `votes` | Extracted from meetings | ~2,000+ |
| `contributions` | Combined CAL-ACCESS + NetFile | 27,035 |
| `conflict_flags` | Scanner output | Variable per scan |
| `attendance` | Extracted from meetings | ~140+ |

### Tables Created but Empty (Future Use)

- `documents` (Layer 1 — raw document lake)
- `chunks` (Layer 3 — pgvector embeddings for RAG)
- `economic_interests` (Form 700 data)
- `cpra_requests` (CPRA tracking)
- `external_references` (news integration)

---

## Automated Sync (Phase 2, Post-Launch)

After the frontend is live with batch-loaded data, add automation:

### Pipeline

1. **Trigger:** Scheduled (weekly before council meetings, or on-demand)
2. **Steps:**
   - eSCRIBE scraper discovers new/upcoming meetings
   - Download agenda packets and attachments
   - Claude extraction produces structured JSON
   - Conflict scanner runs against contribution database
   - `db.py load` pushes results to Supabase
   - Next.js ISR revalidates on next request
3. **Implementation:** n8n workflow or GitHub Actions (TBD based on complexity)
4. **Monitoring:** Log pipeline runs, alert on failures

---

## What's NOT in This Design

These are separate Phase 2 milestones that build on this foundation:

- **RAG search** — Requires pgvector embeddings (Layer 3), search UI, Claude API integration
- **Email alert subscriptions** — Requires auth, user accounts, email service (Resend)
- **Video transcription** — Requires Deepgram/Whisper integration, Granicus scraper
- **Form 700 ingestion** — Requires new data source, parser, scanner integration
- **News integration** — Requires RSS/scraping for Richmond Confidential, East Bay Times
- **CPRA request tracking** — Requires workflow UI, status tracking
- **Document completeness dashboard** — Requires document gap detection logic

---

## Risk & Mitigations

| Risk | Mitigation |
|------|-----------|
| Schema.sql needs changes for Supabase | Test migration on Supabase free project first |
| db.py load format doesn't match schema exactly | Write integration tests for the load path |
| 21 meetings isn't enough data to look compelling | Homepage stats + transparency reports carry the narrative |
| ISR revalidation causes stale data confusion | Show "last updated" timestamps on all pages |
| Conflict flags without context alarm people | Methodology section + confidence tiers + disclaimers |
