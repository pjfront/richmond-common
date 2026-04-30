# Locunity

**One-line:** SF pre-seed startup pairing AI with human editors to deliver Smart Brevity meeting briefings; Bay Area + Kentucky; the trigger for this entire repository.
**URL:** [locunity.com](https://www.locunity.com) · [app](https://app.locunity.com) · [LinkedIn](https://www.linkedin.com/company/locunity)
**Last updated:** 2026-04-28
**Data confidence:** High (verified email content, founder LinkedIn, Crunchbase, Tracxn, pricing page; ASR vendor still unknown)

## Snapshot

| Field | Value |
|---|---|
| Founded | 2025 |
| Stage | Pre-seed |
| Total funding | $125,000 (Aug 19 2025) |
| Lead investor / backer | Safe AI Fund (SAIF) — Geoff Ralston's ex-YC fund (standard SAIF check $100K on $10M cap; $125K = slightly above) |
| Headcount | 3 (per Crunchbase / chamber-of-commerce listings); operating range likely 2–10 |
| HQ | **Martinez, CA** (per Crunchbase + Martinez Chamber of Commerce); SF address (2261 Market St STE 68363) is the registered virtual mailbox |
| Coverage | ~100 jurisdictions: SF + Alameda + Contra Costa + San Mateo counties + Jefferson, KY |

## People

**Founders:**
- **Jonathan Bash — CEO** ([linkedin.com/in/jtbash](https://www.linkedin.com/in/jtbash/))
  - 3x PRSA-award-winning communications strategist, 15+ years
  - Co-Founder, Homeless Action Coalition
  - Runs the [Contra Costa Civic.News+ Substack](https://contracosta.substack.com/about) (own "Civic News LLC" / "Civics" network) — Locunity is the productized version of that newsletter approach
  - Doubles as Locunity's "Contra Costa Editor"
  - **Read:** PR/comms operator, not engineer. Owns the editorial voice. Explains the Smart Brevity output.

- **Dev Iyer — CTO** ([linkedin.com/in/devpiyer](https://www.linkedin.com/in/devpiyer/))
  - Prior: **Twitch, SoundCloud, OpenGov** ← OpenGov is the meaningful signal (govtech SaaS, last valued ~$1.8B)
  - Doubles as "San Francisco Editor"
  - **Read:** Real civic-tech engineering pedigree.

**Editorial / Staff:**
- **Laura Patch** — Editor, Bay Area (the human in the human-in-the-loop)

**Advisors / Notable backers (notably elite for $125K pre-seed):**
- Geoff Ralston (ex-YC President; founded SAIF, lead investor)
- Lenny Mendonca (ex-Chief Economic Advisor, State of California)
- Matt McMahon (ex-EVP, CBS / Paramount)
- Reed Albergotti (Tech Editor, Semafor)
- Alistair Barr (ex-Tech Editor, Business Insider)

This bench is vastly stronger than $125K pre-seed implies — staged for a Series A.

## Buyer & Distribution

- **Buyer profile:** B2C funnel → B2B revenue. Free residential tier acquires advocacy / business / chamber / government affairs buyers.
- **Named customers:** East Bay Leadership Council · Oakland Report · League of Women Voters California · Votelight · SF Chamber of Commerce · City of Oakland Police Commission
- **Channels:** Email (primary, `reports@members.locunity.com` — pattern matches Customer.io / Sendgrid) + Web dashboard (`app.locunity.com`, JS-rendered, auth-walled)
- **Format:** **Smart Brevity per-item** — Basics / Why it matters / The other side / Decisions / What's next, with named quotes
- **Lag time:** ~5 days (verified: 4/22 meeting → 4/27 03:05Z email)
- **Geographic strategy:** Regional Bay Area expansion + KY beachhead, ambition to reach all "90,000 elected bodies" in US (per founder claim)

## Product Surface

| Feature | Description |
|---|---|
| **Meeting Briefings** | Email + dashboard recap per meeting, Smart Brevity format |
| **Auto Minutes / Verbatim Transcripts** | Generated from audio/video |
| **Policy Radar** | Keyword + issue tracking on agendas, push alerts |
| **Civic Map** | Directory of officials/staffers/commissioners |
| **Live Feed** | Real-time aggregation of news + social on tracked issues |
| **AI Content Generator** | Draft social posts, memos referencing their data corpus |
| **Constituent Question Tracking** | Cross-meeting tracking of recurring questions |

**Negative space — what Locunity explicitly doesn't do:**
- Campaign finance integration (no NetFile / CAL-ACCESS overlay).
- Conflict-of-interest detection per agenda item.
- Public records / CPRA pipeline.
- Source provenance metadata in output.
- Open source.
- Multi-city architecture with FIPS-keyed registry (their coverage list is hand-curated).

## Technical Methodology

| Component | Choice |
|---|---|
| ASR / transcription | **Inferred** — Whisper or Deepgram (not disclosed) |
| LLM | **Inferred** — proprietary stack (described as "AI-first") |
| Pipeline architecture | Inferred: ASR → chunked LLM extraction with templated Smart Brevity prompt → human editor review → email + dashboard publish |
| Eval / accuracy framework | Human editor pass (Laura Patch / Bash for Contra Costa) catches errors |
| Cost per meeting | Unknown |
| Lag from meeting to publication | ~5 days (1 verified data point) |
| Provenance / source labeling | None visible. The reader trusts the email. |
| Hallucination defense | Human editor review |
| Open source? | No (proprietary "AI-first stack") |

**The 4/22/2026 Richmond email** (verified content) reveals format details:
- ~2,500 words covering a 7-hour meeting
- News-style headline ("Council Deadlocks on Craneway Pavilion as $12M Liability Splits Vote")
- Lede paragraph + bullet summary + per-item Smart Brevity sections
- Direct quotes from named council members AND public commenters (Margarita Mitas, Susan Lustig, Don Gosney, etc.)
- Vote breakdowns with exact member names per side ("3-3-1, For: …, Against: …, Abstain: …")
- Canonical name spellings correct (Soheila Bana, Doria Robinson, Sue Wilson) — they have a name dictionary or human editor catches this
- Specifics from buried discussion: Madison Capital auxiliary lease (legal terms not in agenda summary)

**Inferred pipeline:** Pull video from Granicus/eSCRIBE → ASR → chunked LLM extraction with single templated prompt per agenda item (rigid uniformity is the giveaway) → top-of-meeting synthesis for headline + lede + bullets → human editor pass → publish.

## Pricing

| Tier | Price | Limits / features |
|---|---|---|
| Free | $0 | 2 commissions, 1 issue + 1 keyword, meeting briefings, agenda alerts |
| Pro | $20/mo flat | 5 commissions, 3 issues + 1 keyword, content generation, Civic Map |
| Enterprise / Government | Custom | 6+ commissions, unlimited tracking, minutes & agendas creation, SSO, Slack, gov procurement; annual + nonprofit discounts |

## Constraints they operate under

- **Funding constraint:** $125K SAIF pre-seed → next round needs venture-scale outcome story. Geoff Ralston's bench is staged for a Series A. **They have to grow.**
- **Buyer constraint:** Real revenue comes from B2B (chambers, advocacy groups, government affairs, agencies). Residential free tier is the funnel; the *real* product is calibrated for what advocacy groups will pay for.
- **Growth / scale constraint:** Coverage count is the metric SAIF tracks for next round. They have to push toward "America's civic intelligence layer" framing even when depth would serve users better.
- **Advisor / board constraint:** Elite advisor bench (ex-YC president, ex-CA Chief Economic Advisor, ex-CBS EVP, two senior tech journalists) creates pressure to be a generation-defining story. Hard to stay small.
- **Runway constraint:** $125K pre-seed isn't long for SF salaries; need to either scale fast or hit revenue inflection. Both options compress decisions.
- **Brand / framing constraint:** "Shape what's next" tagline + the action-marketplace roadmap ("connecting with organizations, events, and opportunities tied to the exact issues you're tracking") commit them to advocacy-adjacent positioning. They can't easily walk back to neutral-observer.

## What RC is free from by not being them

- **No SAIF.** RC doesn't have to deliver a venture-scale outcome.
- **No B2B funnel pressure.** RC's free tier feeds nothing; it just exists.
- **No advisor bench expecting acceleration.** RC's pace is the operator's pace.
- **No coverage metric.** RC can stay one city without justifying TAM.
- **No advocacy-action monetization pressure.** RC will never have a buyer paying to be the recommended action on a given issue.
- **No editor on payroll.** RC's pure-auto with provenance discipline is sustainable because nobody's salary depends on it.

## Borrowable technical infrastructure

- **Smart Brevity scaffold structure** — Basics / Why / Other Side / Decisions / Next per agenda item. The structure is reusable; it's a prompt template.
- **Public-commenter naming pattern** — surfacing names + paraphrased substance + occasional verbatim quotes. We have `public_comments` rows; just need to feed them as structured input alongside transcript.
- **Single-email-per-meeting briefing format** — one meeting → one email → one URL.
- **Vote-tally formatting** — "3-3-1, For: …, Against: …, Abstain: …" with member names per side.
- **News-style headlines** — conflict-forward, specific, not topic-style.
- **"Minor Items" catch-all section pattern** — covers everything that didn't merit a full section.

## Anti-patterns — what RC should NOT borrow

- **Smart Brevity *voice* (Axios punchy)** — calibrated for B2B chamber-of-commerce readers. The structure is fine; the voice lands wrong for collaborative governance-assistant stance.
- **"Civic intelligence layer" framing** — commercial-coded; conflicts with public-good positioning.
- **"Shape what's next" advocacy tagline** — would push RC away from neutral-observer stance.
- **Action-marketplace monetization** (their roadmap signal: *"Soon you'll be able to act on it directly — connecting with organizations, events, and opportunities tied to the exact issues you're tracking"*). Direct distortion of what residents see based on who pays.
- **B2B funnel via residential free tier** — incentive misalignment.
- **Editorial layer dependency** — sustainable only with revenue; RC's pure-auto + provenance is the alternative.
- **VC scaling logic** — the constraint distorts the product roadmap.

## Strategic Position

- **Buyer story:** Free residents → $20/mo Pro → Enterprise/Government. B2B revenue funds the B2C top of funnel. Real money is in chambers / advocacy groups / government affairs / agencies tracking meetings as part of their work.
- **Differentiator:** Smart Brevity editorial voice + elite advisor bench + ex-OpenGov technical pedigree. The advisor bench in particular is hard to assemble.
- **Weaknesses / gaps:** No depth (no finance, conflicts, CPRA, source-tier discipline). Closed-source. ~5-day lag is slower than citymeetings.nyc (~24h). Bay Area concentration hasn't been validated nationally (Jefferson, KY is the only outlier).
- **Roadmap signals:**
  - **Action-marketplace layer** explicitly hinted in welcome email — this will be a major shift when shipped.
  - Coverage push to all 90,000 elected bodies (per stated TAM).
  - Likely Series A in next 12 months given advisor bench.

## Sources

- [locunity.com](https://www.locunity.com) · [pricing](https://www.locunity.com/pricing) · [LinkedIn company](https://www.linkedin.com/company/locunity) · [app.locunity.com](https://app.locunity.com)
- [Crunchbase: Locunity](https://www.crunchbase.com/organization/locunity)
- [Tracxn: Locunity profile](https://tracxn.com/d/companies/locunity/__a3rbIS_bsATtR18Kz939MYXttq0-gFTxXFmjmipDCJ0)
- [Jonathan Bash on LinkedIn](https://www.linkedin.com/in/jtbash/) · [Bash's Substack](https://contracosta.substack.com/about)
- [Dev Iyer on LinkedIn](https://www.linkedin.com/in/devpiyer/)
- [Geoff Ralston / SAIF — TechCrunch](https://techcrunch.com/2025/04/17/former-y-combinator-president-geoff-ralston-launches-new-ai-safety-fund/) · [SAIF.vc](https://www.saif.vc/)
- The 4/22/2026 Richmond council briefing email (verified, Gmail account `pjfront@gmail.com`)
- The 4/26/2026 founding-member welcome email (verified, same)
- [East Bay Leadership Council membership listing](http://eastbayleadershipcouncil.memberzone.com/list/member/locunity-inc-4586)

## Open Questions / Research Gaps

- ASR vendor (Whisper vs Deepgram vs custom)
- Exact LLM (likely GPT-4 / Claude / hybrid; not disclosed)
- Subscriber count
- Freshness SLA — is ~5 days typical or for that specific meeting?
- Action-marketplace details — when shipped, what's the monetization mechanism?
- Whether they're talking to the City of Richmond directly (relationship-relevant)
- Series A timeline + valuation expectations
- Whether SAIF restricts what kinds of advocacy content gets generated through the platform

## Notes

- They're the trigger for this entire repository. The 4/22 Richmond email landing in the operator's Gmail at 03:05Z on 4/27 prompted *"so much more detailed and well-written than anything I could build right now"* and started this research.
- Watch for their Series A announcement and the action-marketplace ship — both are inflection points that will reshape the field.
