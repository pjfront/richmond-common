# Data Sources — Richmond Common

*Last updated: 2026-02-15*

---

## Pilot Phase (Critical — Months 1-3)

### Council Minutes (Archive Center)
- **URL:** ci.richmond.ca.us/Archive.aspx?AMID=31
- **Method:** HTTP + PDF parse
- **Difficulty:** Low
- **Notes:** URLs follow predictable pattern (ViewFile/Item/{id}). Highly consistent format. Post-2022 coverage.

### Council Agendas
- **URL:** Same archive system
- **Method:** HTTP + PDF parse
- **Difficulty:** Low
- **Notes:** Agendas published before meetings with staff reports. Essential for pre-meeting conflict scanning.

### Transparent Richmond (Socrata / Tyler Technologies)
- **URL:** transparentrichmond.org
- **API:** SODA REST API — SQL-like querying, free, no auth needed
- **Difficulty:** Very Low
- **Notes:** 300+ datasets. Budget, capital projects, permits, performance measures, police incidents, calls for service. Daily/weekly/monthly auto-updates. Structured JSON/CSV. Python library: sodapy. API endpoint: `https://www.transparentrichmond.org/resource/{dataset-id}.json`

### CAL-ACCESS (Campaign Finance)
- **URL:** cal-access.sos.ca.gov
- **Method:** Bulk download
- **Difficulty:** Medium
- **Notes:** California statewide campaign finance database. Download bulk data for Richmond-area committees. API is notoriously clunky — bulk download is more reliable. Essential for conflict scanner.

### City Clerk Campaign Reports
- **URL:** ci.richmond.ca.us/1440/Campaign-Reports
- **Method:** HTTP + PDF parse
- **Difficulty:** Medium
- **Notes:** Form 460 filings. Local supplement to CAL-ACCESS. More detail on local races.

---

## Beta Phase 1 (High Priority — Months 4-6)

### FPPC Form 700 (Economic Interests)
- **URL:** fppc.ca.gov + local filings
- **Method:** HTTP + PDF parse
- **Difficulty:** Medium
- **Notes:** Property holdings (Schedule A-2), income sources (Schedule C), investments (Schedule A-1). Essential for 500-foot conflict detection under CA Government Code 87100.

### NextRequest (CPRA Portal)
- **URL:** cityofrichmondca.nextrequest.com
- **API:** REST at /api/v2/requests (paginated JSON, 100/page) — BUT API keys are admin-only
- **Method:** Browser agent for public portal (React/Angular, JS-rendered)
- **Difficulty:** Medium
- **Notes:** Shows request text, status, department, timeline, released documents. Strategic value: reveals what citizens are asking for, response times, redaction patterns. Check before filing new CPRA requests to avoid duplicates.

### Granicus Video Archive
- **URL:** richmond.granicus.com
- **Method:** HTTP for linked documents + Whisper/Deepgram for transcription
- **Difficulty:** Medium
- **Notes:** 2006-2021 coverage. robots.txt blocks scraping, but linked documents may be accessible. Videos give verbatim record even when official minutes are summarized.

### RPD Open Data Portal
- **URL:** opendata.ci.richmond.ca.us
- **API:** Socrata (SODA)
- **Difficulty:** Very Low
- **Notes:** Police data and air quality. Secondary portal to Transparent Richmond.

---

## Beta Phase 2 (Medium/Low Priority — Months 7-12)

### Tom Butt Blog
- **URL:** tombutt.com/forum
- **Method:** HTTP + HTML parse
- **Difficulty:** Low
- **Notes:** 15+ years of Richmond political analysis. Well-structured HTML. Former Mayor, continued posting. Tier 3 source (stakeholder). Test case for news integration pipeline.

### Richmond Confidential
- **URL:** richmondconfidential.org
- **Method:** HTTP + HTML parse
- **Difficulty:** Low
- **Notes:** UC Berkeley Graduate School of Journalism. High quality. Tier 2 source (independent journalism).

### Richmond Standard
- **URL:** richmondstandard.com
- **Method:** HTTP + HTML parse
- **Difficulty:** Low
- **Notes:** Chevron-funded. Tier 3 source. The funding itself is an interesting data point to surface.

### Sire AgendaPLUS (Historical)
- **URL:** ci.richmond.ca.us (Sire system)
- **Method:** Browser agent
- **Difficulty:** High
- **Notes:** Historical resolutions, ordinances, agendas, minutes. Tabbed interface. Valuable for deep historical context.

### Contra Costa Property Records
- **URL:** County portal
- **Method:** Browser agent
- **Difficulty:** High
- **Notes:** Cross-reference council member and donor property interests against zoning/development votes. Phase 2 enrichment for conflict scanner.

### Contra Costa Court Records
- **URL:** odyportal.cc-courts.org
- **Method:** Browser agent
- **Difficulty:** Very High
- **Notes:** Odyssey portal: cookie-gated, JavaScript-heavy, SSL-protected. Shows hearing dates and filed document names, NOT actual documents (those require in-person/mail requests, $0.50/page). Use case: cross-reference city litigation mentioned in closed session items. County scanning 12M pages for paperless system — better access may come naturally. Manual spot-checks initially.

### Planning Commission Minutes
- **URL:** Same archive system as council
- **Method:** Same as council minutes
- **Difficulty:** Low

### Rent Board Minutes
- **URL:** Same archive system
- **Method:** Same as council minutes
- **Difficulty:** Low

---

## Newsletter Ingestion (All Phases)

Subscribe to every Richmond council member's newsletter with a project email address. Pipe incoming Mailchimp/Constant Contact HTML emails directly into document lake. Real-time ingestion, exactly as constituents receive them. Same for campaign email lists during election seasons.

---

## News/Media (Phase 2+)

Broader news search via API: NewsAPI, Google News API, or web search with date filters. For every agenda item, search related news coverage from past 90 days, link relevant articles. Regional coverage: East Bay Times, SF Chronicle, KQED, Bay Area broadcast.
