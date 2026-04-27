# Richmond Commons

**One-line:** What happens when one person does civic transparency as a hobby with AI co-authorship and refuses to make a business of it.
**URL:** [richmondcommons.org](https://richmondcommons.org)
**Last updated:** 2026-04-27
**Data confidence:** High (we are us)

## The actual differentiator

**The operator does this for fun, gets paid nothing, owes nothing to anyone except their own curiosity, and can stop at any time without consequence.**

Everything else — provenance discipline, three-layer DB, conflict scanning, source-closest-artifact rule, multi-city architecture — is downstream of *one structural fact*: there is no buyer, no investor, no LP, no advisor, no team, no runway, no roadmap obligation. The operator can build whatever feels right today. Right now that's Richmond civic transparency. Tomorrow it could be something else entirely.

That optionality is the moat. Every other player in this directory ([`_landscape.md`](./_landscape.md)) lives under constraints that *force* specific product decisions. RC has none of those constraints. The technical features are expressions of that freedom, not the differentiator itself.

## Snapshot

| Field | Value |
|---|---|
| Founded | 2025 (operator started; phased build through 2026) |
| Stage | Pre-launch in spirit; live frontend; nonprofit/open-source planned |
| Total funding | $0 — out-of-pocket |
| Lead investor / backer | None. The operator. |
| Headcount | 1 operator + AI |
| HQ | Richmond, CA |
| Coverage | 1 city (Richmond, CA, FIPS 0660620) — multi-city architecture in code |

## People

- **Operator** ([pjfront@gmail.com](mailto:pjfront@gmail.com)) — Richmond resident; also Personnel Board chair (separate role); platform paid for out-of-pocket per [feedback memory](../../../../../.claude/projects/E--Projectz-RichmondTransparencyProject-richmond-transparency-project/memory/feedback_out_of_pocket_budget.md).
- **Claude** — AI co-architect.

No editorial staff. No advisors. No board. The collaborative relationship with city government is operator-maintained, not contracted.

## Buyer & Distribution

- **Buyer profile:** None. There are no buyers. There is no revenue model. Free forever for residents per [`CLAUDE.md`](../../../CLAUDE.md) core values ("Free public access — revenue from professional tools and scaling, never from paywalling public data" — though even the "professional tools" leg is not active).
- **Channels:** Web ([richmondcommons.org](https://richmondcommons.org)), email subscription (Resend, sent from `updates@richmondcommons.org`).
- **Format:** Plain-language narrative paragraphs (6th-grade reading level per [`src/prompts/meeting_recap_system.txt`](../../../src/prompts/meeting_recap_system.txt)) + structured tables for votes / contributions / conflicts / commissions.
- **Lag time:** Hours after transcript becomes available (YouTube auto-captions). Some pipelines weekly/monthly.
- **Geographic strategy:** Single city deeply, multi-city architecture (`src/city_config.py`) ready for any US city via FIPS code. **Expansion is not a goal.** It's an option the operator may exercise or not.

## Product Surface

| Feature | Description |
|---|---|
| Meeting pages | UUID-keyed page per council meeting; agenda items, votes, public comments, recap |
| Council profiles | Per-member pages with stats, donors, voting record |
| Topic timelines | Per-topic chronology of decisions |
| Most Discussed | Volume-ranked agenda items |
| Find My District | District lookup (ArcGIS 2021 redistricting boundaries) |
| Influence maps | Donor → council → agenda connections |
| Public records (CPRA) | NextRequest scraper + compliance dashboard |
| Conflict scanner | Tier 1/2/3 confidence-based donor-vote conflict flags |
| Voting patterns | Coalition matrix as filter surface (S24.26) |
| Election season | Candidate discovery + 2026 primary tracking |
| Email digests | Per-meeting recaps + welcome flow + preference center |
| Operator mode | Cookie-based feature gating for staged graduation |
| Civic glossary | Plain-language ↔ regulatory term mapping |

**Negative space — what RC explicitly doesn't do (yet, and may never):**
- AI content generation for advocacy (the Locunity-style "draft a social post" — would compromise editorial neutrality).
- B2B / pro tier (Hamlet-style developer intelligence — wrong buyer).
- Action marketplace (Locunity-roadmap-style "connect to advocacy orgs" — would distort what residents see).
- Hardware capture (Aware-style — RC isn't selling to cities).
- Multi-city in production (architecture ready; deployment is at operator's discretion).
- Embeddings / semantic search (planned S25; will happen if and when interesting).

## Technical Methodology

| Component | Choice |
|---|---|
| ASR / transcription | YouTube auto-captions via yt-dlp (KCRT YouTube). Fallback: Granicus PDFs. |
| LLM | Claude Sonnet 4 (`claude-sonnet-4-20250514`) for extraction, recap, summaries, vote explainers |
| Pipeline architecture | Three-layer DB: Document Lake (raw JSONB) → Structured Core (normalized tables) → Embedding Index (pgvector, planned S25). 15+ Python modules. Cloud orchestration: GitHub Actions + n8n. |
| Eval / accuracy framework | Pipeline liveness expectations (`docs/pipeline-manifest.yaml` `expectations:` block, ~25 SQL checks). Bias audit. 487 tests. Anon visibility test (RLS gap detection). |
| Cost per meeting | ~$0.06 (Claude Sonnet, ~10.5K input + ~8.9K output tokens). ~$1.44/year for full Richmond minutes extraction. |
| Lag from meeting to publication | Hours when transcript published. Pipeline cadence: daily 7am UTC, weekly Mon 8am UTC, monthly 15th, quarterly. Change detector polls every 15 min. |
| Provenance / source labeling | **Mandatory** D1: every API response that serves UI includes `source_url`, `extracted_at`, `source_tier`, `confidence_score` non-nullable. Source tiers (Tier 1/2/3/4) with bias disclosures (Chevron-funded outlets always tagged). Branched/conditional source labels per render context. |
| Hallucination defense | (1) Source-closest-artifact rule. (2) Canonical names appended to system prompts. (3) Operator review. (4) D2: low-confidence (<90%) excluded from summary counts. (5) D5: AI-generated content always marked. |
| Open source? | Planned S27 (BSL or AGPL-3.0 — choice deferred) |

## Pricing

| Tier | Price | Limits / features |
|---|---|---|
| Public | $0 | Everything, no account required |
| Email subscription | $0 | Welcome flow + meeting recaps + preference center |
| Operator mode | n/a | Cookie-gated for staged feature graduation |

No paid tiers exist. No revenue model. The operator pays out-of-pocket and intends to keep doing so until and unless something changes — which it might, but doesn't have to.

## Constraints we operate under

This is the short list, because it's short:

- **Operator's time:** Finite. Some weeks heavy, some weeks none. No SLA.
- **Operator's curiosity:** The thing that gets built is the thing the operator finds interesting. When that drifts, the product drifts.
- **Out-of-pocket budget:** Per [feedback memory](../../../../../.claude/projects/E--Projectz-RichmondTransparencyProject-richmond-transparency-project/memory/feedback_out_of_pocket_budget.md), optimize for $0. Never frame any cost as "rounding error."
- **City relationship:** The collaborative governance-assistant stance is values-protected. Don't burn the relationship for a momentary product win. (Per [`.claude/rules/richmond.md`](../../../.claude/rules/richmond.md).)
- **Public-good alignment:** Justice, representation, stewardship. Per [`CLAUDE.md`](../../../CLAUDE.md). Self-imposed; not contractual.

That's it. No investor expectations. No buyer requirements. No advisor pressure. No team to maintain. No quarterly metrics. No runway clock.

## What RC is free from

(The inverse. The optionality the operator preserves by refusing the standard shape.)

- **Free to be wrong about what to build, and change it.** No external trust to lose.
- **Free to refuse to monetize.** No funnel pressure.
- **Free to build features no one would pay for.** Conflict scanner, bias audit, public records compliance dashboard — none of these justify a B2B subscription. All of them are valuable to Richmond residents.
- **Free to stay one city forever.** Or expand. Or contract. No TAM justification required.
- **Free to open-source on operator's terms.** AGPL or BSL or MIT based on what feels right, not what an LP prefers.
- **Free to kill features without explaining.** Operator gets bored, feature dies. No press release.
- **Free to pivot.** Right now this is Richmond civic transparency. It could be a different city. A different scope. A different output format. A different domain entirely. The infrastructure is the operator's curiosity engine.
- **Free to refuse the format pressure.** When everyone else is doing Smart Brevity, RC can do something else. When everyone else is doing email-first, RC can be web-first or both or neither. The category orthodoxy doesn't bind.
- **Free to take a sabbatical.** No customers waiting on a feature. The site keeps running on autopilot. Pipelines keep flowing. The operator returns when interesting.

## Borrowable technical infrastructure (from competitors)

These are things RC has taken or could take *without* inheriting the constraints they came with:

- **From [citymeetings.nyc](./citymeetings-nyc.md):** Custom `T###` time markers (avoid timestamp hallucinations). Per-item LLM chunking (8K tokens). 200+ ground-truth eval pattern.
- **From [Locunity](./locunity.md):** Smart Brevity scaffold *structure* (Basics / Why / Other Side / Decisions / Next per item). Public-commenter naming pattern. Single-email-per-meeting briefing format.
- **From [OpenCouncil](./opencouncil.md):** AGPL-3.0 license decision data. Their open code as reference. Multimodal output direction (podcasts, Reels) for D6 ("narrative over numbers") expansion.
- **From [Aware](./aware.md):** Hardware-capture pattern reference if RC ever expands to a city without published streams.
- **From [Civic Sunlight](./civic-sunlight.md):** Cautionary lesson — pure-AI hallucinations are reputation-shredding, hold the D1/D2/D5 line.
- **From [Hamlet](./hamlet.md):** Search-by-company-name pattern as a navigation primitive (relevant for influence map UX).

## Anti-patterns — what RC explicitly should NOT borrow

These look attractive but carry constraints:

- **B2B funnel** (Locunity, Aware, Hamlet, citymeetings.nyc planned). Carries advocacy distortion pressure.
- **VC scaling logic** (Locunity → Series A track). Carries TAM-justification pressure that distorts product roadmap.
- **B2G procurement model** (Aware, HeyGov, CivicPlus). Carries city-clerk-buyer alignment that biases away from residents.
- **Action-marketplace monetization** (Locunity roadmap signal). Would directly distort what residents see based on who pays to be the recommended action.
- **Smart Brevity *voice*** (Axios-style punchy). The structure is fine to borrow; the voice is calibrated for B2B chamber-of-commerce readers and lands wrong for a collaborative governance-assistant stance.
- **Blockchain hashing for verification** (Aware). Procurement-friendly story; not actually solving a real problem RC has.
- **Hardware capture as a business** (Aware Capture). Pulls RC into a procurement vertical it doesn't want.
- **"Civic intelligence layer" framing** (Locunity). Commercial-coded. Conflicts with public-good positioning.

## Strategic Position

- **Buyer story:** None. The operator pays. The operator decides.
- **Differentiator:** Structural optionality. No constraints other than the operator's curiosity, time, and self-imposed values (justice/representation/stewardship + city-relationship protection).
- **Weaknesses / gaps:**
  - Recap format is shorter and less polished than Locunity's Smart Brevity scaffold (technical, fixable in ~1 day).
  - No direct quotes or named public commenters in recap voice (technical, fixable).
  - Coverage is single-city; no horizontal scale yet (intentional, may stay that way).
  - Solo operator + AI; no editorial layer (intentional; AI does it, operator reviews).
  - Pre-launch in spirit; subscriber count is small.
  - Out-of-pocket budget; can't outspend a Series A competitor on growth (intentional; growth isn't the goal).
- **Roadmap signals:**
  - S25: pgvector embeddings, semantic search.
  - S26: Entity resolution, contract tracking, scanner v4.
  - S27: Open source + nonprofit.
  - **All of these are options the operator may exercise. None of them are commitments.**

## Sources

- [`CLAUDE.md`](../../../CLAUDE.md) — project overview
- [`docs/PROJECT-SPEC.md`](../../PROJECT-SPEC.md) — vision + scope
- [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) — three-layer DB
- [`docs/PARKING-LOT.md`](../../PARKING-LOT.md) — sprint execution
- [`docs/AI-PARKING-LOT.md`](../../AI-PARKING-LOT.md) — research + ideas queue
- [`docs/design/DESIGN-RULES-FINAL.md`](../../design/DESIGN-RULES-FINAL.md) — D1–D6
- [`.claude/rules/conventions.md`](../../../.claude/rules/conventions.md) — source-closest-artifact rule
- [`.claude/rules/judgment-boundaries.md`](../../../.claude/rules/judgment-boundaries.md)
- [`.claude/rules/richmond.md`](../../../.claude/rules/richmond.md)
- [JOURNAL.md](../../../JOURNAL.md) — narrative chronicle (Entry 51 motivates source-closest rule)
- Live site: [richmondcommons.org](https://richmondcommons.org)

## Open Questions / Research Gaps

- What's our subscriber count today? (Look at `email_subscribers` table.)
- Empirical lag from meeting end to recap publication in practice.
- How does our recap format actually compare to Locunity's, line-by-line, on the same meeting? (Need to wait for both to publish on a future meeting.)

## Notes

- This file mirrors `_template.md` precisely. We audit ourselves on the same axes we audit them. If we update the template, update this file.
- The "constraints we operate under" section is short *on purpose*. That shortness is the point.
