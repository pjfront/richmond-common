# Civic Sunlight

**One-line:** Maine-based civic-AI newsletter; the published cautionary tale on hallucinations (CJR Nov 2024 reported fake "Council approved" items).
**URL:** [civicsunlight.ai](https://civicsunlight.ai)
**Last updated:** 2026-04-27
**Data confidence:** Medium (founders + hallucination story confirmed; financial details not disclosed)

## Snapshot

| Field | Value |
|---|---|
| Founded | 2024 |
| Stage | Bootstrap / pre-seed |
| Total funding | Not disclosed |
| Lead investor / backer | Not disclosed (likely founder-funded + grants) |
| Headcount | Small (founders + Midcoast Villager partnership reporters) |
| HQ | 21 Elm Street, Camden, ME 04843 |
| Coverage | ~20 towns in Maine (initial) + planned expansion to Ohio, Massachusetts, Texas |

## People

**Founders:**
- **Tom Cochran** — Co-Founder
- **David Mortlock** — Co-Founder
- "Founded by two friends in Maine"

**Editorial / Staff:** Reporters from *Midcoast Villager* (newsroom partnership added Fall 2024 after hallucination incidents).

**Advisors / Backers:** Maine Trust for Local News exploring partnership.

## Buyer & Distribution

- **Buyer profile:** B2C (free newsletter) + B2B (newsroom partnerships).
- **Named customers / partner outlets:** *Midcoast Villager* (Maine newsroom).
- **Channels:** Email newsletter primarily; website archive.
- **Format:** AI-generated summaries; news-style.
- **Lag time:** Not disclosed
- **Geographic strategy:** Maine-first, planned multi-state pilots.

## Product Surface

| Feature | Description |
|---|---|
| **Meeting Summaries** | "Turn hours of government meetings into concise, digestible updates" |
| **Listening Tools** | Topic + keyword tracking with notifications |
| **Trends and Analysis** | Pattern identification across meetings |

**Public testimonials:** Chris (Belfast, ME), Susan (Camden, ME), Molly (Hope, ME).

**Subscriber count:** ~1,000+ (per CJR coverage).

**Negative space:**
- No campaign finance / conflict scanning.
- No source-tier discipline.
- No public records / CPRA pipeline.

## Technical Methodology

| Component | Choice |
|---|---|
| ASR / transcription | Not disclosed |
| LLM | Not disclosed (LLMs general; specific model not named) |
| Pipeline architecture | Process video → noteworthy topics → summaries with time-stamped source links |
| Eval / accuracy framework | **Originally pure-AI; pivoted to human review Fall 2024** after public hallucination incident |
| Cost per meeting | Not disclosed |
| Lag from meeting to publication | Not disclosed |
| Provenance / source labeling | Time-stamped source links (basic) |
| Hallucination defense | **Human review by *Midcoast Villager* reporters** (added under reputational pressure, not by initial design) |
| Open source? | No |

## The hallucination story (Per [CJR coverage](https://www.cjr.org/analysis/ai-local-news-civic-sunlight-maine.php))

This is the most important section about Civic Sunlight — the published cautionary tale that shapes the entire field's posture toward pure-AI civic content.

- **November 2024 newsletter:** stated Concord, NH approved Memorial Field and Penacook Library funding — **both false**, per *Concord Monitor*.
- Other early misheard names: e.g., "Megunticook Lake" rendered phonetically wrong (similar pattern to RC's canonical-names problem before [`src/prompts/canonical_names.md`](../../../src/prompts/canonical_names.md)).
- Founder Cochran claims "90 to 95 percent accurate."
- **Fall 2024 pivot:** partnered with *Midcoast Villager* — reporters now verify and expand on summaries before publication.
- *Midcoast Villager*'s Alex Seitz-Wald: *"We don't have the staff to cover all those towns."* (Why the partnership works for the newsroom: AI does first pass, reporters verify.)

**Key reading for RC:** This is what happens when AI civic content is wrong in public. The reputational hit lands harder than the claimed accuracy rate suggests.

## Pricing

| Tier | Price | Notes |
|---|---|---|
| Free | $0 | Sign-up newsletter |
| Partnership | Custom (B2B) | Newsroom integrations |

## Constraints they operate under

- **Funding constraint:** Bootstrap / unclear external funding. The Maine Trust for Local News partnership exploration suggests they're seeking nonprofit / journalism-foundation funding.
- **Buyer constraint (B2B):** Newsrooms (*Midcoast Villager* type). Newsrooms care about accuracy + journalist-verifiable content. The Fall 2024 pivot to human review was driven by this constraint.
- **Reputational constraint:** Post-CJR coverage, accuracy is a public commitment. The "90–95% accurate" claim binds them.
- **Growth / scale constraint:** Pilots in OH/MA/TX represent expansion mandate. Have to demonstrate replicability.
- **Trust-recovery constraint:** Whatever they ship next is read against the hallucination history.

## What RC is free from by not being them

- **No public hallucination story to recover from.** RC's defenses (D1, D2, D5, source-closest-artifact rule) are pre-incident structural choices, not post-incident pivots.
- **No newsroom buyer constraint.** RC isn't selling to newsrooms.
- **No accuracy claim binding them publicly.** RC documents its hallucination defense in [JOURNAL.md Entry 51](../../../JOURNAL.md) and [`.claude/rules/conventions.md`](../../../.claude/rules/conventions.md) — but doesn't make a public "X% accurate" promise that becomes a constraint.
- **No expansion mandate.** RC stays in Richmond unless and until expansion is interesting.

## Borrowable technical infrastructure

Less than the other deep-technical players (citymeetings.nyc, OpenCouncil), but the **lessons learned** are valuable:

- **Cautionary lesson on pure-AI civic content.** Hold the D1/D2/D5/source-closest-artifact line. Don't soften under any feature pressure. RC's Flock incident (JOURNAL.md Entry 51) is the same lesson, internally surfaced before public exposure.
- **Newsroom-partnership pattern as a *trust-amplification* lever** (not a buyer relationship). If RC ever wants amplified reach, partnering with a Richmond-area newsroom (Richmondside, Richmond Confidential) on a "RC's data + journalist verification" model is conceptually similar.
- **Phonetic name correction.** Same problem RC solved with `canonical_names.md`. Worth confirming our pattern is robust against the kinds of failures Civic Sunlight had publicly.

## Anti-patterns — what RC should NOT borrow

- **Pure-AI without provenance discipline.** Their pre-Fall-2024 architecture is the cautionary tale.
- **Public accuracy claims** ("90–95% accurate"). They become constraints; better to architect for accuracy and let provenance speak for itself.
- **Newsroom buyer dependency.** RC's pure-auto + provenance approach is structurally sustainable without a verification partner; theirs depends on Midcoast Villager.
- **Multi-state pilots driven by expansion-funding mandate.** RC expands when interesting, not when grant timing requires.

## Strategic Position

- **Buyer story:** Free residential newsletter + B2B newsroom partnerships. Maine Trust for Local News partnership exploration suggests journalism-foundation funding model.
- **Differentiator:** First-mover in rural / small-town New England. Newsroom partnership pattern.
- **Weaknesses / gaps:** Opaque tech stack. Public hallucination history is a real liability. Small scale (1,000 subscribers, 20 towns).
- **Roadmap signals:** OH/MA/TX expansion pilots. Maine Trust for Local News partnership.

## Sources

- [civicsunlight.ai](https://civicsunlight.ai)
- [Columbia Journalism Review — "The Rise of AI Local News"](https://www.cjr.org/analysis/ai-local-news-civic-sunlight-maine.php) — the published hallucination story
- [Nieman Lab on civic AI listening tools](https://www.niemanlab.org/2025/03/local-newsrooms-are-using-ai-to-listen-in-on-public-meetings/)

## Open Questions / Research Gaps

- Funding source (founder savings? grants? Maine Trust?)
- ASR + LLM stack
- Cost per meeting
- Subscriber count today (vs. 1,000+ at time of CJR coverage)
- Whether the *Midcoast Villager* partnership has been formalized financially
- Effects of OH/MA/TX pilot launches on accuracy / reputation
- Specific content moderation post-incident (do they now block any specific content type?)

## Notes

- **The single most useful competitor for RC's strategic posture** — their hallucination story is a free lesson. Pin the CJR article. Re-read when temptation to soften D1/D2/D5 arises.
- **Their newsroom partnership is the only adjacent model worth respecting.** If RC ever wants verified-by-journalist content amplification (e.g., for a Richmond-specific story), the pattern is: AI does first pass + provenance metadata, journalist verifies + amplifies. RC retains editorial independence; journalist gains pre-researched material.
- Watch for additional public accuracy incidents — they tend to cluster.
