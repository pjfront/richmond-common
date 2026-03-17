# Civic Transparency SDK — Vision & Strategic Context

**Purpose:** This document explains WHERE the SDK is going and WHY, so that implementation decisions on the current layer don't accidentally block future layers.
**Audience:** Claude Code (for design context), Phillip (for strategic alignment)
**Status:** Living document — update as strategy evolves

---

## ⚠️ Implementation Boundary

**This document is for CONTEXT ONLY. Do not build anything described in Layers 2-5.**

When implementing Layer 1, use this document to understand *why* a design choice matters. If you find yourself writing code that only makes sense in a multi-city context, stop — you've crossed the boundary. Everything you build should work perfectly for a single city with zero awareness of the layers above it.

---

## 1. The Five-Layer Model

The SDK is structured as five layers, each building on the one below. Only Layer 1 is in scope for implementation now.

```
┌─────────────────────────────────────────────────┐
│  Layer 5: Spec Language & Configuration Intel    │  PRIVATE — future
│  "Compress specs so Claude Code needs fewer      │
│   decisions per task"                            │
├─────────────────────────────────────────────────┤
│  Layer 4: Multi-City Orchestration               │  PRIVATE — future
│  "Onboard a new city in hours, not weeks"        │
├─────────────────────────────────────────────────┤
│  Layer 3: Entity Resolution                      │  OPEN SOURCE — future
│  "The same person across every data source"      │
├─────────────────────────────────────────────────┤
│  Layer 2: Pipeline Primitives                    │  OPEN SOURCE — future
│  "Standardized Source, Extraction, Pipeline"     │
├─────────────────────────────────────────────────┤
│  Layer 1: Convention Enforcement        ← NOW    │  OPEN SOURCE — building
│  "Decide once, enforce always"                   │
└─────────────────────────────────────────────────┘
```

### Layer 1: Convention Enforcement (OPEN SOURCE — CURRENT)

**What it does:** Makes the computer enforce project rules that currently live in human memory. FIPS codes on every record, source tiers on every document, bias disclosures on stakeholder sources, AI disclosures on human-facing content, universal identifiers on every entity.

**Why it matters:** Every layer above assumes these conventions are already enforced. If Layer 2 has to check whether a FIPS code is present before processing a document, the convention has leaked upward. Layer 1 guarantees it.

**Success criteria:** A developer can `pip install` this package, point it at their city's data, and be unable to accidentally violate the core conventions. Convention violations are errors, not warnings.

### Layer 2: Pipeline Primitives (OPEN SOURCE — FUTURE)

**What it will do:** Provide standardized building blocks for civic data extraction. A `Source` class that knows how to connect to Socrata, Legistar, CAL-ACCESS, or a Playwright scraper — all behind the same interface. A `Document` class that manages lifecycle from raw ingestion through extraction to structured storage. An `Extraction` class that runs content through LLM prompts, validates output against schemas, and writes results to the structured core. A `Pipeline` class that orchestrates source → document → extraction → storage as a single unit.

**Why it matters for Layer 1 now:** Layer 1's `db/document_lake.py` is where Layer 2's `Source` classes will write. Layer 1's `conventions/tiers.py` is what Layer 2's ingestion will validate against. Layer 1's `models/` are the base classes that Layer 2's source-specific models will extend. If these interfaces are awkward or rigid, Layer 2 has to work around them.

**Design implication for Layer 1:** Keep function signatures clean and composable. Prefer passing explicit parameters over reading global state. Return values that are easy for a pipeline to chain (e.g., `store_document()` returns a `document_id` that Layer 2 passes to `extract_document()`).

### Layer 3: Entity Resolution (OPEN SOURCE — FUTURE)

**What it will do:** Connect the same real-world person, organization, or entity across every data source in the system. "Eduardo Martinez" on a council vote, "Eduardo M. Martinez" on a campaign filing, and "Mayor Martinez" in a news article are the same person. The entity resolution system maintains a canonical entity registry, scores match confidence, logs every matching decision with metadata, flags ambiguous cases for human review, and builds ground truth sets from verified municipal minutes.

**Why it matters for Layer 1 now:** Layer 1's `conventions/identifiers.py` generates the universal IDs that entity resolution will link together. Layer 1's `models/official.py` is the canonical entity that resolved records will point to. The logging system needs to support match-confidence tracking.

**Design implication for Layer 1:** Universal identifiers must be stable (deterministic generation from natural keys) so that entity resolution can build reliable mappings. The logging system should be extensible enough to support structured match-confidence events without modification. Models should anticipate having multiple "alias" or "source_reference" records pointing to one canonical entity — don't design models that assume one record per person.

### Layer 4: Multi-City Orchestration (PRIVATE — FUTURE)

**What it will do:** Make it possible to onboard a new city in hours instead of weeks. A `City` configuration object that specifies a city's FIPS code, data sources, council structure, meeting formats, and extraction peculiarities. A registry that manages hundreds or thousands of city configurations. Orchestration that runs pipelines across all active cities, handles failures per-city without blocking others, and reports health per-city. Cross-city querying — "show me all cities that voted on rent control in 2024."

**Why it matters for Layer 1 now:** Every Layer 1 function takes `city_fips` as an explicit parameter. This is the seam that Layer 4 plugs into. Layer 4 iterates over its city registry and calls the same Layer 1/2/3 functions once per city, passing different FIPS codes each time. If any Layer 1 function stores city context in global state, or assumes there's only one city, Layer 4 breaks.

**Design implication for Layer 1:** No global city state. No singletons that cache one city's configuration. Every function is stateless with respect to which city it's operating on — city identity comes in through parameters, never through ambient context. The config system supports a `default_city_fips` for convenience in single-city deployments, but this is sugar, not architecture — the underlying functions still require explicit FIPS.

### Layer 5: Spec Language & Configuration Intelligence (PRIVATE — FUTURE)

**What it will do:** Compress the specs that Phillip writes for Claude Code. Instead of writing natural language that describes how to connect to an API, store results, tag tiers, and filter by FIPS, a spec would reference SDK vocabulary: "Add a new Socrata source for Richmond's building permits using `Source.socrata(dataset_id='xxxx', city_fips='0660620')`." The SDK's well-documented, well-named API becomes a shared language between Phillip and Claude Code that reduces ambiguity and makes specs shorter, faster to write, and more reliable to execute.

Beyond spec compression, this layer would include configuration intelligence — the ability to partially auto-generate city configurations by detecting patterns. If 200 cities use Legistar, the system learns what a Legistar city configuration looks like and pre-fills it for city 201.

**Why it matters for Layer 1 now:** Layer 5 depends on Layer 1 having a clean, well-named, well-documented public API. If function names are cryptic, or parameter names are inconsistent, or the module structure is confusing, the "spec language" that emerges from it will be equally confusing. Layer 1 is literally building the vocabulary that Layer 5 will use.

**Design implication for Layer 1:** Naming matters enormously. Consistency matters enormously. `store_document`, `get_document`, `list_documents` — not `save_doc`, `fetch_document`, `query_docs`. Every public function should have a docstring that reads like a sentence a human would write in a spec. If you can't naturally say "use `store_document()` to store the meeting minutes," the name is wrong.

---

## 2. The Open-Core Business Model

The SDK follows an open-core model. Layers 1-3 are open source. Layers 4-5 are proprietary.

```
OPEN SOURCE (civic_sdk)              PROPRIETARY (richmond-transparency-project)
─────────────────────────            ─────────────────────────────────────────────
Layer 1: Convention Enforcement      Layer 4: Multi-City Orchestration
Layer 2: Pipeline Primitives         Layer 5: Spec Language & Config Intelligence
Layer 3: Entity Resolution           + Application layer (frontend, APIs, alerts)
```

### Why this split

**Open layers (1-3) are tools.** They help any civic tech developer build a transparency pipeline for their city. They're valuable alone but require significant manual effort to operate at scale. Open-sourcing them builds community, credibility, trust with government partners, and surfaces edge cases across many cities' data formats that we'd never encounter working on Richmond alone.

**Proprietary layers (4-5) are leverage.** They turn manual effort into automated scale. The difference between "I can build a transparency pipeline for my city" and "I can operate transparency pipelines for 19,000 cities" is the proprietary layer. This is what Path B (horizontal scaling) and Path D (B2B data API) customers pay for.

### What this means for implementation

Nothing in Layers 1-3 should:
- Require a license key or authentication to Anthropic/project services
- Phone home to any server
- Have features that only work in the proprietary context
- Reference proprietary layer code, even in comments

Everything in Layers 1-3 should:
- Work fully offline with a local PostgreSQL instance
- Be documented well enough that a stranger could use it
- Have a clear extension/plugin mechanism where Layers 4-5 attach
- Follow standard Python packaging conventions (pyproject.toml, semantic versioning)

---

## 3. Monetization Paths and How They Connect

Features are prioritized by which monetization paths they serve:

| Path | Description | Depends On |
|------|-------------|------------|
| **A: Freemium Platform** | Free civic tool with premium features for power users | Layers 1-3 (one city) |
| **B: Horizontal Scaling** | Same platform, many cities | Layers 1-4 |
| **C: Data Infrastructure** | Structured civic dataset as a product | Layers 1-3 + API layer |
| **D: B2B Data API** | Sales intelligence for orgs selling to city governments | Layers 1-4 + API layer |

**Layer 1 serves all four paths.** Convention enforcement is foundational — it doesn't matter whether the consumer is a citizen, a journalist, a city employee, or a sales team. The data quality guarantees are the same. This is why Layer 1 is the right starting point.

---

## 4. Richmond as Proving Ground

Richmond, California (FIPS 0660620) is the pilot city. Everything is built and tested on Richmond data first. The project should work beautifully for Richmond before any multi-city code is written.

Richmond-specific context that matters for design:
- 7 council members, ~24 regular meetings per year
- Minutes are highly parseable: "Ayes: [names]. Noes: [names]. Abstentions: [names]."
- Transparent Richmond Socrata portal with 300+ open datasets
- CAL-ACCESS for state-level campaign finance (California)
- Contra Costa County NetFile API for local campaign finance
- Active boards and commissions (Planning, Personnel, Design Review, etc.)
- Major political dynamics: Chevron as significant political spender; progressive coalition government
- Local journalism: Richmond Confidential (UC Berkeley), Richmondside (Cityside.org)

This context should inform model design (e.g., the `Official` model should accommodate both council members and board/commission members) and test data (use real Richmond examples in tests where possible — they're public records).

---

## 5. What Success Looks Like at Each Layer

| Layer | Success Metric |
|-------|---------------|
| **1** | Cannot store a record without valid FIPS. Cannot ingest without a tier. Cannot publish AI content without disclosure. Tests prove it. |
| **2** | Can add a new data source type by implementing one interface. Extraction is re-runnable on stored documents. Pipeline runs are idempotent. |
| **3** | Same person is correctly linked across council votes, campaign filings, and board appointments with logged confidence. Ambiguous matches surface for human review rather than being silently resolved. |
| **4** | A new city can be onboarded by writing a configuration file, not by writing code. Cross-city queries return results in under 5 seconds for the first 100 cities. |
| **5** | Phillip's specs are 50% shorter than pre-SDK specs. Claude Code's implementation accuracy increases because specs reference precise SDK functions instead of describing procedures from scratch. |

---

## 6. Guiding Principles

These apply to every layer and every implementation decision:

1. **Governance assistant, not adversarial watchdog.** The system makes government transparent, not confrontational. Feature naming, data presentation, and API design should reflect this. "Stance timeline" not "contradiction detection."

2. **Decide once, enforce always.** If a rule matters, it's in code, not documentation. If it's in documentation, it's a suggestion, not a rule.

3. **Instrumentation before optimization.** Log everything that matters before tuning anything. Measure convention enforcement rates, extraction accuracy, entity resolution confidence — then optimize based on data.

4. **Structured data over display.** Features that create reusable structured data are always higher priority than features that display data nicely. The pipeline feeds many consumers; the display serves one.

5. **Convention violations are errors.** Not warnings, not log messages. Errors. The pipeline stops. This is the whole point of the SDK.

6. **Single-city is a first-class experience.** The SDK is not a degraded version of the multi-city platform. It's a complete, useful tool for one city. Multi-city is an enhancement, not a prerequisite.

7. **Non-adversarial framing is load-bearing.** This isn't just positioning — it affects feature design, API naming, data presentation, and partnership viability. Every design decision should pass the test: "Would a city council member be comfortable seeing this?"

---

*This document provides strategic context. The build spec (CIVIC-SDK-SPEC.md) provides implementation instructions. When in doubt, follow the build spec. When the build spec is ambiguous, use this document to understand intent.*
