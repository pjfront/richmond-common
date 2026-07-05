# S28 — Interest Profiles (Entity Profile Layer)

**Operator vision (2026-07-05, verbatim intent):** "Profiles for council members, PACs, Unions, Corporations, Donors. Each gets its own page and profiles for those particular kinds of interests."

**Publication tier: Graduated** (organization entities first; individual donors carry an extra judgment gate — see Open Decisions).

## The idea

Every significant actor in Richmond money-and-politics gets its own profile page, and "interests" is rendered per actor type — the profile answers *"who is this, what do they want from city government, and what's the money trail?"* in plain language. This completes PROJECT-SPEC §5 (official profiles with finance + conflicts + Form 700) and extends it across the full influence graph. It is the "reference desk" layer: any name a reader encounters anywhere on the site should be clickable through to its profile.

| Entity type | Their "interests" lens | Data status |
|---|---|---|
| **Council members / officials** | Form 700 economic interests (holdings, income, gifts) + campaign donors + voting record + conflict flags | Voting public ✓ · finance summary removed 2026-06 (restore) · Form 700 ingested + scanner signal exists but **never surfaced on council profiles** (only commissions) · flags gated pending S26 scanner validation |
| **PACs / committees** | Funders-in, spending-out, per-cycle activity, sponsor disclosure | **Built** — `/pac` + `/pac/[slug]` (59 pages), V2 sentence-led + cycle bars, operator-gated since 2026-04-29. Graduation checklist in operator-review-queue.yaml |
| **Unions** | Giving to candidates/PACs, independent expenditures, endorsement patterns, items they spoke on | Data present in contributions/IEs (SEIU $607K+, POA $831K, IAFF transfers); no entity typing, no pages |
| **Corporations** | Giving, city contracts, permits/licenses, agenda items naming them, disclosure rules (Chevron) | Giving present (Chevron $635K); `business_entities` tables exist empty (migration 040, awaits $100 CA SOS bulk — S26); permits/licenses in Socrata mirrors (**OD-14 dependency**: the DB diet must not drop data this sprint needs — trim to recent years instead of dropping) |
| **Individual donors** | Aggregate giving across cycles/committees, employer context | Data present (22K+ contributions, normalized names); **privacy/framing judgment gate before any page ships** |

## Build order (each slice independently shippable)

1. **S28.1 — Council "Economic Interests" section.** Form 700 holdings/income/gifts on council profiles, narrative-first per D6, honest source labels, + restore the factual campaign-finance summary (its removal in June was scanner-flag retrenchment; a factual donor summary is Tier 1 data already public elsewhere on the site). Fastest slice — the pipeline side is fully plumbed (`src/form700_extractor.py`, `src/scanner/signals/form700.py`, `src/db/form700.py`).
2. **S28.2 — Entity typing on donors.** Classify entity-like donor rows into `person | union | corporation | committee | other_org` — rules first (business suffixes, "Local N", known-org list, existing PAC-signal patterns from the /pac work), LLM batch for the remainder. Reuse the netfile lesson: `committee_type` is unreliable; name-pattern + registry evidence beats source metadata. New `donors.entity_type` + `entity_slug`.
3. **S28.3 — Organization profile pages** (`/orgs/[slug]` or extend the /pac route family — decide during design; Tenet 1 says no premature unifying abstraction). Unions and corporations: sentence-led profile (PAC V2 grammar), cycle bars, giving table, IE/endorsement section, agenda-item mentions, mandatory disclosures (Chevron rule from `.claude/rules/richmond.md`). Graduated tier.
4. **S28.4 — PAC graduation.** The oldest built-but-hidden entity class; walk the existing checklist (index + 3-5 detail pages, totals vs NetFile, categorization spot-check) and graduate as the first public entity profiles beyond candidates.
5. **S28.5 — Cross-linking pass.** Donor names on candidate/council pages link to entity profiles; entity profiles link back to items/meetings. This is what makes the graph feel like one site.
6. **S28.6 — Individual donor pages** (LAST, gated on Open Decision 1). Aggregate-giving profiles for individuals above a materiality threshold.
7. **Scanner-fix track (parallel, = S26):** entity resolution (CA SOS bulk), pattern taxonomy, validated batch rescan — this is what earns conflict *flags* back onto all these profiles. S28.2's typing work feeds S26's resolution directly.

## Open decisions (operator)

1. **Individual-donor privacy posture.** All of it is public record, but a dedicated page per private citizen has different weight than a row in a table (see richmond.md on former members: "legitimate flags, but context matters"). Options: (a) org-entities only, individuals never get pages; (b) threshold (pages only for donors above $X aggregate, e.g. $5K); (c) all donors. Proposed default: **(b) with a high threshold**, decided at S28.6 time, not now.
2. **Union framing.** The operator's collaborative stance + Personnel Board position make labor framing sensitive (POA, SEIU, IAFF are the largest players). Framing review before S28.3 graduation is a judgment call, same as every public-facing label.
3. **Route naming** ("/orgs" vs "/donors" vs folding into a "Contributions" nav family per I129's Path B sequencing: Candidates → PACs → orgs/donors next).

## Dependencies & constraints

- **OD-14 (DB diet)** must preserve permits/licenses data (corporation interests) — trim by year, don't drop, if the diet proceeds before S28.3.
- S26's $100 CA SOS purchase unlocks authoritative corporation identity; S28.3 can ship before it using name-based profiles with honest confidence labels.
- Every new public-facing table/query follows D1 provenance + pipeline-manifest + operator-review-queue sync rules.
