# Phase 2 Frontend — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Launch a public-facing Next.js frontend backed by Supabase PostgreSQL, showing council meetings, member profiles, transparency reports, and contribution data for Richmond, CA.

**Architecture:** Next.js 14+ App Router with Server Components, fetching data from Supabase PostgreSQL via `@supabase/supabase-js`. Styled with Tailwind CSS. Deployed on Vercel. Existing Python pipeline (`db.py`) extended to load data into Supabase. ISR for caching.

**Tech Stack:** Next.js 14+, TypeScript, Tailwind CSS, Supabase (PostgreSQL + pgvector), Vercel, `@supabase/supabase-js`

---

## Pre-Requisites (Manual Steps by the Operator)

Before Task 1, the operator must:

1. **Create a Supabase project** at https://supabase.com/dashboard
   - Note the project URL (e.g., `https://xxxxx.supabase.co`)
   - Note the `anon` public key (for frontend reads)
   - Note the database connection string (for `db.py` writes)
2. **Add to `.env`:**
   ```
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_ANON_KEY=eyJhb...
   DATABASE_URL=postgresql://postgres:password@db.xxxxx.supabase.co:5432/postgres
   ```
3. **Create a Vercel account** (if not already) at https://vercel.com
4. **Verify Supabase has pgvector:** Run in Supabase SQL editor: `SELECT * FROM pg_extension WHERE extname = 'vector';`

---

## Task 1: Initialize Database on Supabase

**Files:**
- Modify: `src/schema.sql` (minor Supabase compatibility)
- Modify: `src/db.py` (add `load-all` and `load-contributions` commands)
- Modify: `.env.example` (add Supabase vars)

**Step 1: Test schema against Supabase**

Run `src/schema.sql` in the Supabase SQL editor (Dashboard → SQL Editor → New Query → paste contents → Run). Watch for errors. Supabase already has `uuid-ossp` enabled, and pgvector may need enabling via Extensions dashboard first.

If the `ivfflat` index on `chunks.embedding` fails (needs rows to build), wrap it in a comment for now:
```sql
-- CREATE INDEX idx_chunks_embedding ON chunks USING ivfflat ...
-- Uncomment after loading embedding data
```

**Step 2: Verify schema deployed**

In Supabase SQL editor:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
```

Expected: ~20 tables including `cities`, `meetings`, `officials`, `votes`, `contributions`, etc.

Verify Richmond seed:
```sql
SELECT * FROM cities WHERE fips_code = '0660620';
```

**Step 3: Update `.env.example`**

Add Supabase placeholders:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
```

**Step 4: Add `load-all` command to `db.py`**

Add a new CLI command that loads all extracted meeting JSONs from a directory:

```python
load_all_cmd = sub.add_parser("load-all", help="Load all meeting JSONs from a directory")
load_all_cmd.add_argument("directory", help="Directory containing extracted meeting JSON files")
load_all_cmd.add_argument("--city-fips", default=RICHMOND_FIPS)
```

Implementation: glob `*.json` in directory, skip files that don't have `meeting_date` key, call `load_meeting_to_db` for each.

**Step 5: Add `load-contributions` command to `db.py`**

New command to load the combined contributions JSON (27,035 records) into `donors`, `committees`, and `contributions` tables:

```python
load_contribs_cmd = sub.add_parser("load-contributions", help="Load campaign contributions JSON")
load_contribs_cmd.add_argument("json_file", help="Path to combined contributions JSON")
load_contribs_cmd.add_argument("--city-fips", default=RICHMOND_FIPS)
```

Implementation needs:
- Read the combined JSON (array of contribution records)
- For each record: upsert into `donors` (by normalized name + employer), upsert into `committees` (by name), insert `contribution`
- Handle both CAL-ACCESS format (`contributor_name`, `contributor_employer`, `committee`) and NetFile format (`name`, `employer`, `filerName`)
- Print summary: N donors, N committees, N contributions loaded

**Step 6: Load data into Supabase**

```bash
# Point DATABASE_URL at Supabase
cd src
python db.py load-all data/extracted/
python db.py load-contributions data/combined_contributions.json
```

**Step 7: Verify data loaded**

In Supabase SQL editor:
```sql
SELECT COUNT(*) FROM meetings;          -- expect ~21
SELECT COUNT(*) FROM agenda_items;      -- expect ~500+
SELECT COUNT(*) FROM votes;             -- expect ~2000+
SELECT COUNT(*) FROM contributions;     -- expect ~27000
SELECT COUNT(*) FROM officials;         -- expect ~20
```

**Step 8: Commit**

```bash
git add src/db.py .env.example
git commit -m "Phase 2: extend db.py with load-all and load-contributions commands"
```

---

## Task 2: Scaffold Next.js App

**Files:**
- Create: `web/` directory (Next.js project root)
- Create: `web/package.json`, `web/tsconfig.json`, `web/tailwind.config.ts`, `web/next.config.ts`
- Create: `web/.env.local.example`
- Create: `web/src/app/layout.tsx` (root layout)
- Create: `web/src/app/page.tsx` (homepage placeholder)
- Create: `web/src/lib/supabase.ts` (Supabase client)

**Step 1: Create Next.js project**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP
npx create-next-app@latest web --typescript --tailwind --app --src-dir --eslint --no-import-alias
```

When prompted:
- Would you like to use `src/` directory? **Yes**
- Would you like to use App Router? **Yes**
- Would you like to use Turbopack? **Yes** (faster dev builds)
- Import alias: **@/** (default)

**Step 2: Install Supabase client**

```bash
cd web
npm install @supabase/supabase-js
```

**Step 3: Create Supabase client utility**

Create `web/src/lib/supabase.ts`:

```typescript
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

**Step 4: Create `.env.local.example`**

```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

**Step 5: Create `.env.local` with real values**

Copy from `.env.local.example` and fill in real Supabase credentials.

**Step 6: Verify dev server starts**

```bash
cd web
npm run dev
```

Visit http://localhost:3000 — should see Next.js default page.

**Step 7: Verify Supabase connection**

Temporarily add to `web/src/app/page.tsx`:

```typescript
import { supabase } from '@/lib/supabase'

export default async function Home() {
  const { data } = await supabase.from('cities').select('*').eq('fips_code', '0660620')
  return <pre>{JSON.stringify(data, null, 2)}</pre>
}
```

Visit http://localhost:3000 — should see Richmond city data. Remove after verifying.

**Step 8: Set up Supabase Row Level Security (RLS)**

All our tables need to be readable by the anon key. In Supabase SQL editor:

```sql
-- Enable RLS on all tables but allow public read access
-- (No auth needed for MVP — all data is public)
ALTER TABLE cities ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON cities FOR SELECT USING (true);

ALTER TABLE officials ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON officials FOR SELECT USING (true);

ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON meetings FOR SELECT USING (true);

ALTER TABLE meeting_attendance ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON meeting_attendance FOR SELECT USING (true);

ALTER TABLE agenda_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON agenda_items FOR SELECT USING (true);

ALTER TABLE motions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON motions FOR SELECT USING (true);

ALTER TABLE votes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON votes FOR SELECT USING (true);

ALTER TABLE contributions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON contributions FOR SELECT USING (true);

ALTER TABLE donors ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON donors FOR SELECT USING (true);

ALTER TABLE committees ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON committees FOR SELECT USING (true);

ALTER TABLE conflict_flags ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON conflict_flags FOR SELECT USING (true);

ALTER TABLE closed_session_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON closed_session_items FOR SELECT USING (true);

ALTER TABLE public_comments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON public_comments FOR SELECT USING (true);

ALTER TABLE friendly_amendments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON friendly_amendments FOR SELECT USING (true);
```

**Step 9: Commit**

```bash
git add web/
echo "web/node_modules" >> .gitignore
echo "web/.env.local" >> .gitignore
echo "web/.next" >> .gitignore
git add .gitignore
git commit -m "Phase 2: scaffold Next.js app with Supabase client"
```

---

## Task 3: Design System — Layout, Typography, Colors

**Files:**
- Create: `web/src/app/globals.css` (Tailwind config + custom properties)
- Modify: `web/tailwind.config.ts` (extend with civic palette)
- Create: `web/src/app/layout.tsx` (root layout with nav + footer)
- Create: `web/src/components/Nav.tsx`
- Create: `web/src/components/Footer.tsx`

**Step 1: Configure Tailwind with civic color palette**

Edit `web/tailwind.config.ts`:

```typescript
import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        civic: {
          navy: '#1e3a5f',
          'navy-light': '#2d5a8e',
          slate: '#475569',
          amber: '#d97706',
          'amber-light': '#fbbf24',
        },
        vote: {
          aye: '#059669',
          nay: '#dc2626',
          abstain: '#6b7280',
          absent: '#9ca3af',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
```

**Step 2: Create Nav component**

Create `web/src/components/Nav.tsx` — horizontal nav with logo text + links to: Meetings, Council, Reports, About.

**Step 3: Create Footer component**

Create `web/src/components/Footer.tsx` — minimal footer with: "Richmond Transparency Project", data sources link, methodology link, "Not affiliated with the City of Richmond."

**Step 4: Create root layout**

Edit `web/src/app/layout.tsx` — wrap all pages with Nav + Footer, set Inter font, meta tags.

**Step 5: Verify layout renders**

```bash
cd web && npm run dev
```

Check http://localhost:3000 — nav and footer should appear on placeholder page.

**Step 6: Commit**

```bash
git add web/src/components/ web/src/app/layout.tsx web/src/app/globals.css web/tailwind.config.ts
git commit -m "Phase 2: add design system — nav, footer, civic color palette"
```

---

## Task 4: Supabase Data Fetching Layer

**Files:**
- Create: `web/src/lib/queries.ts` (all Supabase queries in one place)
- Create: `web/src/lib/types.ts` (TypeScript types matching schema)

**Step 1: Define TypeScript types**

Create `web/src/lib/types.ts` with interfaces matching the database schema:

```typescript
export interface City {
  fips_code: string
  name: string
  state: string
  county: string | null
  population: number | null
  council_size: number | null
}

export interface Official {
  id: string
  city_fips: string
  name: string
  role: string
  seat: string | null
  is_current: boolean
  term_start: string | null
  term_end: string | null
}

export interface Meeting {
  id: string
  city_fips: string
  meeting_date: string
  meeting_type: string
  call_to_order_time: string | null
  adjournment_time: string | null
  presiding_officer: string | null
}

export interface AgendaItem {
  id: string
  meeting_id: string
  item_number: string
  title: string
  description: string | null
  category: string | null
  is_consent_calendar: boolean
  financial_amount: string | null
  resolution_number: string | null
}

export interface Motion {
  id: string
  agenda_item_id: string
  motion_type: string
  motion_text: string
  moved_by: string | null
  seconded_by: string | null
  result: string
  vote_tally: string | null
  sequence_number: number
}

export interface Vote {
  id: string
  motion_id: string
  official_id: string | null
  official_name: string
  vote_choice: string  // 'aye' | 'nay' | 'abstain' | 'absent'
}

export interface Contribution {
  id: string
  city_fips: string
  donor_id: string
  committee_id: string
  amount: number
  contribution_date: string
  contribution_type: string
  source: string
}

export interface Donor {
  id: string
  name: string
  employer: string | null
  occupation: string | null
}

export interface Committee {
  id: string
  name: string
  candidate_name: string | null
  committee_type: string | null
}

export interface ConflictFlag {
  id: string
  city_fips: string
  agenda_item_id: string | null
  meeting_id: string | null
  official_id: string | null
  flag_type: string
  description: string
  evidence: Record<string, unknown>[]
  confidence: number
  reviewed: boolean
}

export interface Attendance {
  id: string
  meeting_id: string
  official_id: string
  status: string  // 'present' | 'absent' | 'late'
  notes: string | null
}
```

**Step 2: Create query functions**

Create `web/src/lib/queries.ts` with all Supabase queries:

- `getMeetings(cityFips)` — all meetings, newest first
- `getMeeting(meetingId)` — single meeting with agenda items, motions, votes, attendance
- `getOfficials(cityFips, currentOnly?)` — officials list
- `getOfficialProfile(officialId)` — official + voting record + top donors
- `getOfficialVotingRecord(officialId)` — all votes with meeting/item context
- `getTopDonors(officialId, limit?)` — contributions aggregated by donor for an official's committee
- `getMeetingStats(cityFips)` — counts for homepage stats bar
- `getConflictFlags(meetingId?)` — conflict flags, optionally filtered by meeting
- `getAttendance(meetingId)` — who was present/absent

All queries filter by `city_fips = '0660620'` (Richmond). Every query is a server-side function (called from Server Components, never shipped to client).

**Step 3: Verify queries return data**

Create a temporary test page `web/src/app/test/page.tsx` that calls each query and dumps JSON. Verify all return data. Delete after confirming.

**Step 4: Commit**

```bash
git add web/src/lib/
git commit -m "Phase 2: add Supabase data fetching layer with TypeScript types"
```

---

## Task 5: Meetings List Page (`/meetings`)

**Files:**
- Create: `web/src/app/meetings/page.tsx`
- Create: `web/src/components/MeetingCard.tsx`

**Step 1: Build MeetingCard component**

Card showing: meeting date (formatted nicely), meeting type badge, agenda item count, vote count, attendance summary. Links to `/meetings/[id]`.

**Step 2: Build meetings list page**

Server Component that calls `getMeetings('0660620')`. Renders heading + list of MeetingCards, sorted newest first. Add year filter (links or tabs for 2025, 2026).

**Step 3: Verify page renders**

Visit http://localhost:3000/meetings — should show all 21 meetings as cards.

**Step 4: Commit**

```bash
git add web/src/app/meetings/ web/src/components/MeetingCard.tsx
git commit -m "Phase 2: add meetings list page"
```

---

## Task 6: Meeting Detail Page (`/meetings/[id]`)

**Files:**
- Create: `web/src/app/meetings/[id]/page.tsx`
- Create: `web/src/components/AttendanceRoster.tsx`
- Create: `web/src/components/AgendaItemCard.tsx`
- Create: `web/src/components/VoteBreakdown.tsx`
- Create: `web/src/components/CategoryBadge.tsx`
- Create: `web/src/components/VoteBadge.tsx`

**Step 1: Build VoteBadge component**

Small colored badge: green for "aye", red for "nay", gray for "abstain"/"absent". Used inline next to council member names.

**Step 2: Build CategoryBadge component**

Pill badge for agenda item categories (housing, budget, public_safety, etc.) with category-specific colors.

**Step 3: Build AttendanceRoster component**

Horizontal list of council member names with present (green dot) / absent (gray dot) / late (yellow dot) indicators.

**Step 4: Build VoteBreakdown component**

For a single motion: shows each council member's vote with VoteBadge. Shows motion text, moved by, seconded by, result, tally.

**Step 5: Build AgendaItemCard component**

Expandable card (collapsed by default for consent items, expanded for regular items). Shows item number, title, category badge, financial amount if any, conflict flag indicator. Expands to show description + VoteBreakdown for each motion.

**Step 6: Build meeting detail page**

Server Component. Calls `getMeeting(id)`. Renders:
- Header: date, type, presiding officer
- Conflict flag callout (if any flags exist for this meeting)
- AttendanceRoster
- Consent Calendar section (collapsible group of AgendaItemCards)
- Regular Agenda section (AgendaItemCards)

**Step 7: Verify page renders**

Click a meeting card from `/meetings` — should load the full meeting detail with votes and attendance.

**Step 8: Commit**

```bash
git add web/src/app/meetings/[id]/ web/src/components/
git commit -m "Phase 2: add meeting detail page with vote breakdowns"
```

---

## Task 7: Council Members Pages (`/council` and `/council/[slug]`)

**Files:**
- Create: `web/src/app/council/page.tsx`
- Create: `web/src/app/council/[slug]/page.tsx`
- Create: `web/src/components/OfficialCard.tsx`
- Create: `web/src/components/DonorTable.tsx`
- Create: `web/src/components/VotingRecordTable.tsx`

**Step 1: Build OfficialCard component**

Card with: name, role badge (Mayor/Vice Mayor/Council Member), seat/district, placeholder avatar circle with initials, key stats (votes tracked, attendance %). Links to `/council/[slug]`.

Slug = lowercased, hyphenated name (e.g., "eduardo-martinez"). Store as computed in queries, not in DB.

**Step 2: Build council members list page**

Server Component. Calls `getOfficials('0660620')`. Renders grid of OfficialCards. Two sections: "Current Council" and "Former Members" (toggle or separate sections).

**Step 3: Build DonorTable component**

Sortable table: donor name, total amount, number of contributions, source (CAL-ACCESS/NetFile). Top N rows with "show more" link.

**Step 4: Build VotingRecordTable component**

Filterable table: date, meeting, agenda item title, vote choice (with VoteBadge), category. Sortable by date. Filter by category dropdown.

**Step 5: Build council member detail page**

Server Component. Resolves slug to official ID. Calls `getOfficialProfile()`. Renders:
- Header: name, role, district, term dates
- Stats bar: total votes, attendance %, top category
- Top Donors section (DonorTable)
- Conflict Flags section (list of flagged items if any)
- Full Voting Record (VotingRecordTable)

**Step 6: Verify pages render**

Browse `/council` → click a council member → see their profile with voting record and donors.

**Step 7: Commit**

```bash
git add web/src/app/council/ web/src/components/OfficialCard.tsx web/src/components/DonorTable.tsx web/src/components/VotingRecordTable.tsx
git commit -m "Phase 2: add council member list and profile pages"
```

---

## Task 8: Transparency Reports Page (`/reports`)

**Files:**
- Create: `web/src/app/reports/page.tsx`
- Create: `web/src/app/reports/[meetingId]/page.tsx`
- Create: `web/src/components/ConflictFlagCard.tsx`
- Create: `web/src/components/ConfidenceBadge.tsx`

**Step 1: Build ConfidenceBadge component**

Badge showing confidence tier: Tier 1 "Potential Conflict" (red/amber), Tier 2 "Financial Connection" (yellow), Tier 3 not shown publicly.

**Step 2: Build ConflictFlagCard component**

Card showing: flag type, description, evidence citations, confidence badge, affected agenda item link, affected official link.

**Step 3: Build report detail page**

Server Component for `/reports/[meetingId]`. Fetches meeting + conflict flags. Renders:
- Header: "Transparency Report — [Meeting Date]"
- Summary: N items scanned, N flags found
- Tier 1 findings section (if any)
- Tier 2 findings section (if any)
- Clean items note ("N items scanned with no findings")
- Methodology sidebar
- Link to submitted public comment (if available)

Filter: only show flags where `confidence >= 0.5` (Tier 1+2). Tier 3 (`confidence < 0.3`) is internal only.

**Step 4: Build reports list page**

Server Component for `/reports`. Lists all meetings that have been scanned (have conflict_flags or scan audit records). Each shows date, items scanned count, flags found count. Links to detail page.

**Step 5: Verify pages render**

Visit `/reports` → click a report → see the transparency analysis.

**Step 6: Commit**

```bash
git add web/src/app/reports/ web/src/components/ConflictFlagCard.tsx web/src/components/ConfidenceBadge.tsx
git commit -m "Phase 2: add transparency reports pages"
```

---

## Task 9: Homepage (`/`)

**Files:**
- Modify: `web/src/app/page.tsx`
- Create: `web/src/components/StatsBar.tsx`
- Create: `web/src/components/LatestMeetingCard.tsx`
- Create: `web/src/components/HowItWorks.tsx`

**Step 1: Build StatsBar component**

Horizontal bar with 4 stats: "N Meetings Tracked", "N Votes Recorded", "N Contributions Cross-Referenced", "N Conflict Flags". Fetches from `getMeetingStats()`.

**Step 2: Build LatestMeetingCard component**

Featured card showing the most recent meeting: date, key agenda items, attendance, any conflict flags. Links to meeting detail.

**Step 3: Build HowItWorks component**

Three-column section: "1. Ingest" (icon + description), "2. Analyze" (icon + description), "3. Publish" (icon + description). Static content.

**Step 4: Build homepage**

Compose:
- Hero section: "Richmond Transparency Project" + tagline + CTA buttons (Browse Meetings, View Council)
- StatsBar
- LatestMeetingCard
- HowItWorks
- Quick links section

**Step 5: Verify homepage**

Visit http://localhost:3000 — should show full homepage with real data from Supabase.

**Step 6: Commit**

```bash
git add web/src/app/page.tsx web/src/components/StatsBar.tsx web/src/components/LatestMeetingCard.tsx web/src/components/HowItWorks.tsx
git commit -m "Phase 2: build homepage with stats, latest meeting, and how-it-works"
```

---

## Task 10: About / Methodology Page (`/about`)

**Files:**
- Create: `web/src/app/about/page.tsx`

**Step 1: Build about page**

Static content page with sections:
- What is Richmond Transparency Project?
- What This Is NOT (not adversarial, not advocacy, not social media)
- Source Credibility Tiers (Tier 1-4 explained with examples)
- How the Conflict Scanner Works (matching logic, thresholds)
- Data Sources (CAL-ACCESS, NetFile, eSCRIBE, Archive Center — with links)
- Limitations and Disclaimers
- About the Creator (the operator)
- Contact / Feedback

Use clean editorial layout with navy headings, card-styled tier explanations.

**Step 2: Verify page**

Visit http://localhost:3000/about — should render the full methodology page.

**Step 3: Commit**

```bash
git add web/src/app/about/
git commit -m "Phase 2: add about/methodology page"
```

---

## Task 11: ISR Configuration & Performance

**Files:**
- Modify: `web/src/app/meetings/page.tsx` (add revalidate)
- Modify: `web/src/app/meetings/[id]/page.tsx` (add revalidate)
- Modify: `web/src/app/council/page.tsx` (add revalidate)
- Modify: `web/src/app/council/[slug]/page.tsx` (add revalidate)
- Modify: `web/src/app/reports/page.tsx` (add revalidate)
- Modify: `web/src/app/page.tsx` (add revalidate)
- Modify: `web/next.config.ts` (image optimization, etc.)

**Step 1: Add ISR revalidation to all data-fetching pages**

Add to each page that fetches from Supabase:
```typescript
export const revalidate = 3600 // Revalidate every hour
```

**Step 2: Add "Last Updated" display**

Add a small timestamp at the bottom of data pages showing when the page was last generated. Helps users understand data freshness.

**Step 3: Configure `next.config.ts`**

```typescript
const nextConfig = {
  images: {
    unoptimized: true, // No external images yet
  },
}
```

**Step 4: Test build**

```bash
cd web
npm run build
npm run start
```

Verify all pages render in production mode. Check for build errors.

**Step 5: Commit**

```bash
git add web/
git commit -m "Phase 2: configure ISR revalidation and production build"
```

---

## Task 12: Deploy to Vercel

**Files:**
- Create: `web/vercel.json` (optional, for config)

**Step 1: Connect to Vercel**

```bash
cd web
npx vercel
```

Follow prompts to link to Vercel account and project. Set the root directory to `web/`.

**Step 2: Set environment variables**

In Vercel dashboard → Project Settings → Environment Variables:
- `NEXT_PUBLIC_SUPABASE_URL` = your Supabase URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` = your Supabase anon key

**Step 3: Deploy**

```bash
npx vercel --prod
```

**Step 4: Verify live site**

Visit the Vercel URL. Check all pages load with real data. Test navigation between pages.

**Step 5: Commit any Vercel config changes**

```bash
git add web/
git commit -m "Phase 2: deploy to Vercel"
```

---

## Task 13: Automated Pipeline Sync

**Files:**
- Create: `.github/workflows/sync-pipeline.yml` (GitHub Action)
- Modify: `src/run_pipeline.py` (add `--load-db` flag)

**Step 1: Extend `run_pipeline.py` with database loading**

Add `--load-db` flag to `run_pipeline.py` that, after generating the scanner results, also calls `load_meeting_to_db` to push the extracted data into Supabase. This makes the pipeline end-to-end: scrape → extract → scan → load.

**Step 2: Create GitHub Action workflow**

`.github/workflows/sync-pipeline.yml`:

```yaml
name: Sync Pipeline

on:
  schedule:
    - cron: '0 6 * * 1'  # Every Monday at 6am UTC (Sun 10pm PT)
  workflow_dispatch:      # Manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run pipeline
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          cd src
          python run_pipeline.py --date $(date -d "next Monday" +%Y-%m-%d) --load-db
```

This is a starting point — will need refinement based on meeting schedule and error handling.

**Step 3: Add secrets to GitHub repo**

In GitHub → Settings → Secrets → Actions:
- `ANTHROPIC_API_KEY`
- `DATABASE_URL` (Supabase connection string)

**Step 4: Test with manual trigger**

Trigger the workflow manually via GitHub Actions UI. Verify data lands in Supabase.

**Step 5: Commit**

```bash
git add .github/workflows/sync-pipeline.yml src/run_pipeline.py
git commit -m "Phase 2: add automated pipeline sync via GitHub Actions"
```

---

## Summary of Deliverables

| Task | What | Commit |
|------|------|--------|
| 1 | Supabase DB setup + data loading | `extend db.py with load-all and load-contributions` |
| 2 | Next.js scaffold + Supabase client | `scaffold Next.js app` |
| 3 | Design system (nav, footer, colors) | `add design system` |
| 4 | Data fetching layer (queries + types) | `add Supabase data fetching layer` |
| 5 | Meetings list page | `add meetings list page` |
| 6 | Meeting detail page | `add meeting detail page with vote breakdowns` |
| 7 | Council member pages | `add council member list and profile pages` |
| 8 | Transparency reports pages | `add transparency reports pages` |
| 9 | Homepage | `build homepage` |
| 10 | About/methodology page | `add about/methodology page` |
| 11 | ISR + production build | `configure ISR revalidation` |
| 12 | Deploy to Vercel | `deploy to Vercel` |
| 13 | Automated pipeline sync | `add automated pipeline sync` |

**Estimated effort:** 13 tasks, ~2-4 hours per task, ~30-50 hours total.

**Key dependency chain:** Task 1 (DB) → Task 2 (scaffold) → Task 3 (design) → Task 4 (queries) → Tasks 5-10 (pages, parallelizable) → Task 11 (ISR) → Task 12 (deploy) → Task 13 (automation).
