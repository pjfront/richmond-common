# citymeetings.nyc

**One-line:** Solo software engineer in NYC making council meetings navigable; the most technically transparent player in the field.
**URL:** [citymeetings.nyc](https://citymeetings.nyc) · [founder blog](https://vikramoberoi.com)
**Last updated:** 2026-04-27
**Data confidence:** High (founder publishes detailed methodology)

## Snapshot

| Field | Value |
|---|---|
| Founded | December 2023 (newsletter); September 2024 (daily publication) |
| Stage | Self-funded, pre-revenue |
| Total funding | None — solo founder time |
| Lead investor / backer | None |
| Headcount | 1 (founder) |
| HQ | NYC |
| Coverage | NYC City Council + planned expansion (community boards, Planning Commission, Loft Board, state-level) |

## People

**Founder:**
- **Vikram Oberoi** ([vikramoberoi.com](https://vikramoberoi.com))
  - Software engineer, NYC-based
  - Has existing client work that funds his time on this
  - Started newsletter Dec 2023; recognized methodology overfitting Apr 2024; rebuilt summer 2024; daily publication launched Sep 2024
  - Got NY1 coverage Oct 2024 → steady 15–20 newsletter signups weekly + growing search traffic
  - Site went on summer break June 2025 → returned September 2025

**Editorial / Staff:** None — solo + manual review by founder.

**Advisors / Backers:** None disclosed.

## Buyer & Distribution

- **Buyer profile:** Currently free B2C; planned freemium with paid pro tier for **lobbyists, journalists, government affairs, RFP-monitoring sales teams, community advocates**.
- **Named customers / users:** Government staff (legislative affairs, policy analysts, government affairs), lobbyists, advocates, journalists, RFP-monitoring vendors.
- **Channels:** Web (citymeetings.nyc) + email newsletter ("Keys to the City Council")
- **Format:** **Chapter-based navigation** — meetings broken into linkable, time-stamped sub-segments with titles and descriptions. Reader navigates rather than reads a summary.
- **Lag time:** ~24 hours
- **Geographic strategy:** NYC-only, by deliberate choice (depth over breadth)

## Product Surface

| Feature | Description |
|---|---|
| **Per-meeting page** | Video + transcript + chapter markers (QUESTION / TESTIMONY / REMARKS / PROCEDURE) |
| **Chapter timeline** | Linkable sub-segments with AI-generated titles + descriptions |
| **Speaker identification** | Per-sentence speaker labels (manually verified) |
| **Search across meetings** | Find specific chapters / topics across the corpus |
| **Newsletter** | "Keys to the City Council" — narrative summaries |

**Negative space:**
- No campaign finance overlay.
- No conflict-of-interest scanning.
- No multi-city architecture (NYC-only by design).
- No B2B platform yet (planned).
- No real-time alerts (planned).

## Technical Methodology

This is the player most transparent about technical choices. Founder published [a detailed writeup](https://vikramoberoi.com/posts/how-citymeetings-nyc-uses-ai-to-make-it-easy-to-navigate-city-council-meetings/) and [Maximum NY interview](https://www.maximumnewyork.com/p/citymeetings-interview).

| Component | Choice |
|---|---|
| ASR / transcription | **Deepgram** (with diarization). Tested Whisper + Pyannote, preferred Deepgram out-of-the-box quality. |
| LLM | **GPT-4 Turbo** (since Nov 2023) — chosen for context window + cost-perf. Evaluated GPT-3.5 (cheaper but worse), Gemini 1.5, Claude Opus. |
| Pipeline architecture | 3-step: speaker ID → marker extraction (QUESTION/TESTIMONY/REMARKS/PROCEDURE) → chapter creation/titling. Each step on 8K-token windows. |
| Chunking | **8K-token windows.** Full-transcript prompts caused "lost in the middle" — LLM gave up on mid-sections. Critical lesson. |
| Time references | **Custom `T###` markers, NOT timestamps.** "LLMs frequently hallucinate timestamps." Strong RC takeaway. |
| Eval / accuracy framework | Custom review tools, **200+ ground-truth examples**, iterated 35–50% → 80–90% accuracy via systematic checkbox validation. |
| Cost per meeting | $5–10 |
| Lag from meeting to publication | ~24 hours |
| Provenance / source labeling | Each chapter links to a specific transcript segment + video timestamp |
| Hallucination defense | **Human-in-the-loop:** manual speaker review (per-call), manual chapter section marking (~5 min/meeting). Founder explicit: *"I don't believe using AI alone is a great way to use AI today."* |
| Open source? | No, but founder shares prompts in [public gists](https://gist.github.com/voberoi/) |
| Tooling | `instructor` Python package for structured LLM output |

## Pricing

| Tier | Price | Limits / features |
|---|---|---|
| Free (current) | $0 | Full access |
| Pro (planned) | TBD | Targeted at lobbyists, journalists, government affairs |

## Constraints they operate under

- **Funding constraint:** Solo founder funding via existing client work. Time is the bottleneck.
- **Buyer constraint (planned):** Future freemium needs to attract lobbyists / journalists / government affairs as paying tier. Product expansion plans (state-level, community boards) are calibrated for those buyers.
- **Growth / scale constraint:** Geographic coverage capped at NYC for now; founder explicitly chose depth.
- **Runway constraint:** No external runway; pace is determined by founder's day-job income.
- **Brand / framing constraint:** Founder has reputation for technical rigor (NY1 coverage, civic-tech community) — public commitments to accuracy claims become constraints.

Compared to other players: **fewer constraints, but the future-monetization plan introduces them.** Right now the closest thing in the field to "doing this for the love of it." Note that this changes as soon as the paid pro tier launches.

## What RC is free from by not being them

Less of a contrast — citymeetings.nyc is closest to RC in spirit. But still:

- **RC has Claude AI as co-architect**, not a single human's nights and weekends. Different velocity profile.
- **RC isn't planning a paid pro tier**, so RC's product priorities don't tilt toward what lobbyists / journalists / government affairs would pay for.
- **RC has multi-city architecture** baked in; NYC-only is intentional but binds him.
- **RC integrates campaign finance + conflicts + CPRA**; he hasn't (because individual would be too much work for one person).

## Borrowable technical infrastructure

This is the **richest source of borrowable technical infrastructure** in the field:

- **Deepgram with diarization** — out-of-the-box speaker labels, tested better than Whisper + Pyannote.
- **GPT-4 Turbo with 8K-token windows** — full-transcript prompts fail; chunking solves "lost in the middle."
- **Custom `T###` time markers (not raw timestamps)** — "LLMs frequently hallucinate timestamps." If RC ever embeds time references in recap output, use this pattern.
- **3-step pipeline structure** — speaker ID → marker extraction → chapter creation/titling. Each step constrained, each step has its own prompt + eval.
- **`instructor` Python package** for structured LLM output.
- **200+ ground-truth examples + systematic checkbox eval** — iterated 35–50% → 80–90% accuracy. RC has pipeline liveness expectations for "did data flow"; this is the analog for "is the recap factually correct."
- **Chain-of-thought reasoning + 5–10 examples per prompt** — better than single-shot.
- **Manual section marking with custom UI (~5 min/meeting)** — the human-in-the-loop trick for accuracy that doesn't require a full editor.
- **Founder's gists** are public — read them.

## Anti-patterns — what RC should NOT borrow

- **Plans for a paid pro tier targeting lobbyists / journalists / government affairs** — same incentive misalignment as Locunity's B2B funnel. Different buyer than residents.
- **Single-city scope as a permanent constraint** — for citymeetings.nyc it's a feature; for RC it's an option, not a commitment.
- **Manual speaker / chapter review per meeting** — sustainable for him because he funds it via day job; not for RC.

## Strategic Position

- **Buyer story (current):** No buyers; founder funds via client work. Free for residents.
- **Differentiator:** Technical rigor + NYC-only depth + transparent methodology. Most respected in the civic-tech community.
- **Weaknesses / gaps:** Solo + no editorial layer + manual review is the bottleneck. Coverage scope tightly bound to NYC. Eventually monetization compromises will arrive.
- **Roadmap signals:**
  - Expansion: community boards, City Planning Commission, Loft Board, Community Education Councils, Panel for Educational Policy.
  - State-level proceedings (Assembly, Senate, state agencies).
  - Future: city rules linkage with bills, budget change tracking + notifications.
  - Paid pro tier (timeline unclear).

## Sources

- [citymeetings.nyc](https://citymeetings.nyc) · [about](https://citymeetings.nyc/about/) · [coverage](https://citymeetings.nyc/coverage-shoutouts-and-citations/)
- [Vikram Oberoi blog](https://vikramoberoi.com) · [technical writeup](https://vikramoberoi.com/posts/how-citymeetings-nyc-uses-ai-to-make-it-easy-to-navigate-city-council-meetings/)
- [Maximum NY interview ("Anatomy of an AI-Driven Civic Tech Product")](https://www.maximumnewyork.com/p/citymeetings-interview)
- [NY1 coverage Oct 2024](https://ny1.com/nyc/all-boroughs/CTV/2024/10/12/new-website-uses-ai-to-monitor-city-hall-meetings)
- [Founder gists](https://gist.github.com/voberoi/)
- [Vikram on LinkedIn](https://www.linkedin.com/in/voberoi)

## Open Questions / Research Gaps

- Current subscriber count
- Cost trajectory now that GPT-4 Turbo pricing has dropped + alternatives (Claude Sonnet, Gemini 1.5) are mature
- Paid pro tier launch timing + pricing
- Whether the public gists include the latest production prompts or earlier versions
- Whether he's open to collaboration with peer projects (potentially RC could share canonical-name patterns or borrow eval framework)

## Notes

- The closest thing in the field to a peer for RC's spirit (solo, depth-over-breadth, technically rigorous, civic-good motivation). The biggest difference: he's planning to monetize; RC isn't.
- Worth tracking his moves more closely than any other player — his methodology evolves transparently.
