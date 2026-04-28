# What Richmond Commons Focuses On

**Updated:** 2026-04-28
**Companion to:** [`README.md`](./README.md) (the negative map) and [`_self.md`](./_self.md) (RC profile).

The negative map answers *what we won't become*. This file answers *what we are becoming*. Same data, opposite framing. Read both — they reinforce each other.

---

## What Richmond Commons IS

Richmond Commons is **public civic infrastructure for Richmond, California**, built and maintained by one operator + Claude as co-architects, paid for out-of-pocket, free forever for residents, with mandatory provenance on every claim and depth across data layers no commercial player can afford to build.

Its real engine is the operator's curiosity. Right now that curiosity points at Richmond civic transparency. It could point elsewhere later. The shape of the work follows what the operator finds interesting; the architecture supports any direction the curiosity goes.

## The compass

**The operator does this for fun.** Every other civic-AI player carries an obligation — to investors, buyers, advisors, runway, brand, growth metric. RC carries none of those obligations. The operator's curiosity is the only obligation, and curiosity is renewable.

That's not a soft positioning. It's a **structural fact** that determines what RC can and can't do:

- Can build features no one would pay for. (Conflict scanner. Bias audit. CPRA compliance. Source-tier disclosures. Open-source release.)
- Can refuse to monetize even when offered. (No advocacy marketplace. No Pro tier. No B2B funnel.)
- Can stay one city forever — or expand tomorrow. The architecture supports both; the choice is the operator's.
- Can pivot, kill features, or take a break without breaking external promises.
- Can pick license + data model + tech stack based on what's interesting, not what closes a contract.

## What RC focuses on

### 1. Depth in one place over breadth across many

The competitive landscape proves depth is unjustifiable against business constraints — every other player is at the meeting-summary layer because that's what their buyers will pay for. RC integrates **meeting summaries + campaign finance + conflicts + public records + commissions + topic timelines + influence maps + voting patterns** because none of those individually are commercially valuable but together they are *useful*.

Layered depth is the moat. Hold it.

### 2. Mandatory provenance on every claim

D1 is the architectural commitment: every API response that serves UI carries `source_url`, `extracted_at`, `source_tier`, `confidence_score`. D2 keeps low-confidence data out of summary counts. D5 marks AI-generated content. Migration 095 closed the gap for derived artifacts (every recap/summary/bio carries a sibling `*_provenance` JSONB).

This is what no commercial competitor can replicate without rebuilding their schema. It's the structural defense against hallucinations that lets RC be pure-auto where everyone else needs editors.

### 3. Source-closest artifacts

Every generator reads from raw persisted data, not derivatives. Every debug investigation starts with "what artifact is this reading?" — the lesson from JOURNAL.md Entry 51 (the Flock incident) and Entry 50/52 (the provenance pattern audit). Generators document their inputs in module docstrings.

When this discipline holds, attributions are honest. When it slips, the platform confidently asserts things that aren't true. The discipline is the product.

### 4. Source-tier transparency

Every data point is tagged by reliability:
- **Tier 1:** Official government records (certified minutes, NetFile filings, CAL-ACCESS, Socrata)
- **Tier 2:** Independent journalism (Richmond Confidential, East Bay Times, KQED)
- **Tier 3:** Stakeholder communications — with bias disclosed (Tom Butt E-Forum labeled, Richmond Standard always tagged "funded by Chevron Richmond")
- **Tier 4:** Community / social — context only, never sole source

Citizens can see *where* a claim comes from. Most other players hide this. RC surfaces it.

### 5. Plain language, narrative over numbers

D4 + D6: visible labels at 6th-grade reading level, technical precision in tooltips/CSV/API. Public-facing output is short, plain-language description of what happened. Numbers only when materially important. Narrative descriptions carry their own context; numbers stripped of context get misrepresented.

### 6. Free forever, no funnels

No paid tier. No advocacy marketplace. No B2B upsell. No "Pro" features gated behind subscription. The free tier is the only tier. Operator pays out-of-pocket; sustainability is nonprofit + grants in S27, not extraction.

### 7. Multi-city architecture, single-city deployment

Every record carries `city_fips`. Every scraper accepts a city config. The architecture supports any US city. **Deployment** to any city other than Richmond is opportunistic — the operator decides when and where based on what's interesting, not on TAM justification.

### 8. Collaborative governance-assistant stance

RC is not an adversarial watchdog. It's a governance assistant. Accountability is a byproduct of transparency, not the stated goal. The operator maintains a collaborative relationship with city government because that relationship is itself valuable — both for accuracy (real conversations beat scraped agendas) and for what RC can do in Richmond over time.

This stance is values-protected. Don't drift into advocacy framing under any pressure.

### 9. Open source on the operator's terms

S27 is the planned open-source transition. License (BSL vs AGPL-3.0) is the operator's choice based on what fits — not what an LP, advisor, or buyer prefers. OpenCouncil's AGPL-3.0 is a peer reference; not a binding default.

### 10. Operator's curiosity as compass

When the operator gets bored with a feature, it can die. When something new is interesting, it can be built. There is no roadmap obligation. There is no team to convince. There is no quarterly metric. The curiosity engine drives. Everything else is downstream.

---

## What's next (concrete focus from current backlog)

These are the actual upcoming items per [`docs/PARKING-LOT.md`](../../PARKING-LOT.md). Each is an option the operator may exercise, not a commitment:

| Sprint | Theme | What it does |
|---|---|---|
| **S24** Election Finish | Subscriber acquisition · candidate discovery · council member SEO · Richmond 101 · neighborhoods page · feature graduation | Finish the pre-primary push (June 2 primary) |
| **S25** Search & Similarity | pgvector embeddings · semantic search (RAG) · "Similar Discussions" · proceeding type classification | Layer 3 of the three-layer DB; the embedding index gets populated |
| **S26** Entity Resolution & Scanner v4 | CA SOS bulk data · contract entity tracking · influence pattern taxonomy · batch rescan · contract frontend | Tighten conflict detection; ship the influence patterns |
| **S27** Open Source & Polish | CONTRIBUTING.md + license (BSL or AGPL) · feature graduation review · guide page · council photos · design debt sweep | Make RC publicly contributable |

**Borrowable improvements identified during competitive intel** (independent of sprints, do when interesting):

- Smart Brevity scaffold for meeting recaps (Locunity-inspired structure, RC voice)
- Public commenter naming in recap voice (data already in `public_comments` table)
- Per-meeting briefing email format (one meeting → one email → one URL)
- Custom `T###` time markers if ever embedding timestamps in output (citymeetings.nyc trick — prevents hallucinations)
- 200+ ground-truth eval pattern for accuracy measurement (citymeetings.nyc)

---

## Every "don't" → its "do"

The negative map says *don't borrow X*. Each refusal is a commitment to something positive instead.

| Anti-pattern (what we refuse) | Positive commitment (what we do instead) |
|---|---|
| ❌ B2B advocacy / chamber funnel | ✅ Build for Richmond residents directly. They are the customer. No buyer means no incentive misalignment. |
| ❌ VC scaling logic / coverage metric | ✅ Stay deep in one city until expansion is *interesting*. Architecture is multi-city; deployment is opportunistic. |
| ❌ Procurement-officer alignment | ✅ Resident-comprehension alignment. Plain language, narrative recaps, source links. |
| ❌ Blockchain transcript hashing (theatrical) | ✅ Real provenance: `source_url + source_tier + confidence_score` non-nullable on every record. |
| ❌ Smart Brevity *voice* (Axios punchy, B2B-coded) | ✅ Collaborative governance-assistant *voice*. Borrow the *structure* (Basics / Why / Other Side / Decisions / Next), discard the punch. |
| ❌ "Civic intelligence layer" framing (commercial) | ✅ "Civic infrastructure" framing (public good). |
| ❌ "Shape what's next" advocacy tagline | ✅ Neutral observer stance. Information citizens use to decide for themselves. |
| ❌ Action-marketplace monetization | ✅ Information layer only. What residents do with it is up to them. |
| ❌ **Selling civic-meeting data to capital interests so they can route around community opposition (Hamlet's RVI/RFI pattern)** | ✅ **Civic data goes to the same side that created it — residents.** The asymmetry test is a hard line: residents went to public meetings to be heard; any product that helps capital interests skip listening is the opposite of what RC is for. |
| ❌ Hardware capture as a business | ✅ If we ever need streamless-city ingestion, borrow the *pattern* (record + upload) without owning a hardware roadmap. |
| ❌ Editorial layer dependency | ✅ Pure-auto with provenance discipline + source-closest-artifact rule. The discipline IS the editor. |
| ❌ Public accuracy-percentage claims | ✅ Auditable provenance. The reader checks any claim against its source link. |
| ❌ Multi-state pilot expansion under grant pressure | ✅ Single-city depth until expansion is interesting. |
| ❌ Closed-source enterprise platform | ✅ Open source on operator's terms (S27). License chosen by what fits. |
| ❌ Govtech vendor procurement model | ✅ Direct resident-facing. No middleman city contract. No RFP. |
| ❌ Foundation-grant cycle constraints | ✅ Out-of-pocket today; grants/nonprofit in S27 if and when they fit, on RC's terms. |
| ❌ Quarterly metrics, OKRs, board reports | ✅ Operator's curiosity is the metric. Build what's interesting; ship when it's ready; pivot when it isn't. |
| ❌ Brand consistency pressure | ✅ Brand is whatever the operator wants. Right now it's Richmond Commons. Could be anything. |

---

## Decision framework (positive version)

When a feature decision comes up, ask in this order:

1. **Is this serving Richmond residents directly?** → Build it.
2. **Does this preserve provenance discipline (D1/D2/D5/source-closest-artifact)?** → If yes, build it. If it would soften provenance, find a different path.
3. **The asymmetry test — could this help capital interests skip community input?** (Could a developer, lobbyist, government-affairs buyer use this output to anticipate or route around community opposition more effectively than residents themselves can?) → If yes, refuse it, regardless of how lucrative or technically interesting. This is the Hamlet line. Hard stop.
4. **Does this preserve optionality?** (Can we kill it in 6 months without external pain?) → Optionality-preserving choices win.
5. **Is this what the operator finds interesting right now?** → If yes, build it. If not, park it. The operator's curiosity is the only constraint that matters.

Then borrow technical infrastructure freely (Deepgram, GPT-4 patterns, T### markers, OpenCouncil code, Smart Brevity *structure*) and refuse business infrastructure (funnels, advocacy framing, scaling metrics, procurement alignment, any flavor of selling civic data to the side overriding community input).

---

## How this file relates to the rest of the directory

- [`README.md`](./README.md) — the negative map; the matrix of competitors; what each player *has to do* and what RC doesn't.
- [`_landscape.md`](./_landscape.md) — market segments, convergence patterns, what's missing from the field.
- [`_self.md`](./_self.md) — RC audited on the same template as competitors. The depth view.
- **This file** — the positive declaration. Where RC is going. What we will build.
- Per-competitor profiles — detail when needed.

If [`README.md`](./README.md) is the *map of the territory* and [`_self.md`](./_self.md) is the *map of where we sit*, this file is the *direction we walk*.
