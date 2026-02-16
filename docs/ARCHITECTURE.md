# Architecture — Richmond Transparency Project

*Last updated: 2026-02-15*

---

## 1. Three-Layer Database Design

Central tension: specificity (fast queries) vs. flexibility (handle unknown data). Solution: three layers providing both.

### Layer 1: Document Lake (Flexible — Everything Goes In)

Every raw document preserved exactly as received. Source of truth. Nothing lost. Re-extractable when prompts improve.

```sql
documents (
  id UUID PRIMARY KEY,
  city_fips VARCHAR(7) NOT NULL,
  source_type VARCHAR(50) NOT NULL,   -- 'minutes', 'agenda', 'campaign_finance', 'news', 'blog', 'newsletter'
  source_url TEXT,
  raw_content BYTEA,
  content_hash VARCHAR(64),           -- SHA-256 for deduplication
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB                      -- schema-less, varies by city/source
);
```

`metadata` JSONB is intentionally schema-less. Different cities have different metadata.

### Layer 2: Structured Core (Specific — Queryable)

Highly normalized tables. All foreign keys trace back to `cities` via `fips_code`.

```sql
-- Foundation
cities (fips_code PK, name, state, county, population, timezone, charter_type)
officials (id, city_fips FK, name, seat, term_start, term_end, party_affiliation)

-- Meetings & Votes
meetings (id, city_fips FK, date, type, transcript_url, minutes_url, video_url)
agenda_items (id, meeting_id FK, item_number, title, description, category, subcategory)
motions (id, agenda_item_id FK, motion_text, moved_by FK, seconded_by FK, result)
votes (id, motion_id FK, official_id FK, vote_choice, on_consent_calendar BOOLEAN)
public_comments (id, meeting_id FK, agenda_item_id FK, speaker_name, text, submitted_by_system BOOLEAN)

-- Campaign Finance
donors (id, name, employer, occupation, address)
contributions (id, donor_id FK, committee_id FK, amount, date, type)

-- Conflict Detection
economic_interests (id, official_id FK, filing_year, schedule, description, value_range)
conflict_flags (id, vote_id FK, donor_id FK, reason, confidence_score, reviewed BOOLEAN)

-- Document Tracking
document_references (id, source_document_id FK, referenced_document_description, found BOOLEAN)
cpra_requests (id, city_fips FK, request_text, target_department, filed_date, response_due, status)

-- News/Media Integration
external_references (
  id, document_id FK,
  entity_type VARCHAR(50),     -- 'official', 'company', 'topic', 'agenda_item'
  entity_id UUID,
  mention_type VARCHAR(50),    -- 'quoted', 'discussed', 'criticized', 'endorsed'
  excerpt TEXT,
  sentiment VARCHAR(20),
  confidence FLOAT
)
```

### Layer 3: Embedding Index (pgvector — No Separate Vector DB)

```sql
chunks (
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents(id),
  chunk_text TEXT,
  embedding vector(1536),
  meeting_id UUID REFERENCES meetings(id),
  agenda_item_id UUID REFERENCES agenda_items(id),
  speaker_id UUID REFERENCES officials(id),
  chunk_type VARCHAR(50)
);
```

Single query combines vector similarity + SQL filtering. Example:

```sql
SELECT m.date, ai.title, v.vote_choice, c.chunk_text
FROM chunks c
LEFT JOIN meetings m ON c.meeting_id = m.id
LEFT JOIN agenda_items ai ON c.agenda_item_id = ai.id
LEFT JOIN votes v ON v.motion_id IN (SELECT id FROM motions WHERE agenda_item_id = ai.id)
WHERE c.embedding <-> query_embedding < 0.3
  AND v.official_id = ?
ORDER BY m.date DESC;
```

---

## 2. City Disambiguation (FIPS Codes)

6+ US cities named Richmond. Entity resolution is foundational for 19,000-city scale.

| City | FIPS | State | County | Pop |
|------|------|-------|--------|-----|
| Richmond, CA | 0660620 | California | Contra Costa | 116,448 |
| Richmond, VA | 5167000 | Virginia | Independent | 226,610 |
| Richmond, IN | 1864260 | Indiana | Wayne | 35,720 |

**Enforced everywhere:**
- Every record includes `city_fips`
- Every web search includes "Richmond, California" — never just "Richmond"
- Every extraction prompt includes city context
- Cheap now, catastrophically expensive to retrofit at city #50

---

## 3. Scaling: Adding City #2

- Add row to `cities` table
- Populate same structured tables
- Extraction prompts may differ per city, output schema identical
- Ingestion layer varies per city platform (Granicus, Legistar, Sire, CivicPlus)
- New data types = new tables, never modify existing (backward compat)

---

## 4. Agent Scraper Architecture (Phase 4)

```
Agent Orchestrator
  ├── City Discovery Agent → find data source URLs
  ├── Site Navigation Agent (Playwright + LLM) → navigate and download
  ├── Document Classification Agent → classify each PDF/HTML
  ├── Extraction Agent (Claude) → structured JSON output
  └── Gap Detection Agent → generate CPRA requests for missing docs
```

Agent instructions are semantic ("find the meeting minutes for January 2024") not structural ("click #minutes-link"). Self-heals when sites change.

**This is the moat at scale.** Anyone can build RAG. Reliable agent scraping across hundreds of government website architectures is genuinely hard.

---

## 5. Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Database | PostgreSQL + pgvector | Single system for structured + vector |
| LLM | Claude Sonnet (Anthropic API) | Tool use for schema enforcement |
| Hosting | Vercel (free → Pro) | Edge caching, fast deploys |
| DB Hosting | Supabase free → Railway → managed | Progressive scaling |
| Transcription | Deepgram / Whisper | Meeting video → text |
| Browser automation | Playwright | Agent scraper backbone |
| Structured data API | Socrata (SODA) via sodapy | Transparent Richmond |
| Frontend | Next.js | React + SSR |
| Orchestration | n8n | Pipelines, scheduling |
| Email | Resend → Postmark | Alert subscriptions |

---

## 6. Tested Extraction Prompt

```python
EXTRACTION_PROMPT = """
You are extracting structured data from Richmond, CA City Council meeting minutes.
This document is from the City of Richmond, California (Contra Costa County).
Do not confuse with other cities named Richmond.

For each vote taken during this meeting, extract:
1. agenda_item: The item number and description
2. motion_text: What was being voted on
3. motion_by / seconded_by
4. result: passed or failed
5. votes: For each council member, their vote (aye/nay/abstain/absent)
6. vote_tally: e.g. "5-2"
7. category: zoning, budget, housing, public_safety, environment,
   infrastructure, personnel, contracts, governance, other

Also extract: meeting_date, meeting_type, council_members_present

Return as JSON. Note consent calendar items separately.
"""
```

Richmond format is highly parseable: `Ayes: [names]. Noes: [names]. Absent: [names]. Abstain: [names].`
