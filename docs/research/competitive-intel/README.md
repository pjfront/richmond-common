# Competitive Intelligence — Civic-AI Landscape

**Purpose:** This is a **negative map**, not a "what to copy" map.

The civic-AI players in this directory all live under constraints Richmond Commons doesn't share — investor pressure, B2B revenue requirements, advisor influence, scaling logic, buyer expectations, runway. Every product compromise they make traces back to one of those constraints.

The point of this directory is to make those constraints **visible** so RC can:
1. **Borrow their technical infrastructure freely** — Deepgram, T### markers, chunking strategies, OpenCouncil's code, prompt patterns, eval frameworks. None of that carries their constraints.
2. **Refuse to inherit their business infrastructure** — funnels, advocacy framing, growth logic, distribution shape, action-marketplace monetization, B2B-buyer alignment. All of that carries constraints we don't have.

**The operator's structural advantage:** doing this for fun, with no buyers, no investors, no LPs, no obligations to anyone but the operator's own curiosity. *Right now* this looks like Richmond civic transparency. It could look like anything. That optionality is the moat — and it's the one moat the rest of the field structurally cannot replicate.

**Updated:** 2026-04-27

## How to use this directory

- **Reading order for a fresh briefing:** `_landscape.md` → `_self.md` → quick-reference matrix below → individual profiles as relevant.
- **For Claude:** When the user mentions a competitor by name, load that profile. When they ask about market shape or "who else does X," load `_landscape.md` + the matrix below. When deciding whether to borrow something, ask: is this *technical* infrastructure (yes, take it) or *business* infrastructure (no, don't drift toward their constraints).
- **For updates:** Each profile has a **Last updated** date. When new public info surfaces, edit the relevant profile and bump the date. Add to **Sources**. Drop stale guesses into **Open Questions**.
- **Confidence labels** (High / Medium / Low) are honest signals about data quality.

## Methodology

**What goes in:**
- Public data only — websites, Crunchbase, Tracxn, LinkedIn, press, podcasts, GitHub, founder writings, our own observation of their product output.
- Direct verification when possible (their actual emails, the actual code, the actual pricing page).
- Inferred facts clearly marked.
- **Constraints they operate under** — investors, advisors, buyers, growth metrics — because those constraints are what RC's negative map is *of*.

**What stays out:**
- Anything requiring non-public access.
- Speculation about strategy without an observable signal.
- Sentiment / vibes.

## Profile template

New profiles copy [`_template.md`](./_template.md). The template has two sections that distinguish this from a normal competitive analysis:

1. **Constraints they operate under** — the things they *have* to do because of their structure. (Their LP, their advisors, their runway, their buyer.)
2. **What RC is free from by not being them** — the inverse. The optionality the operator preserves by refusing this shape.

## Quick-reference matrix

The table is the fast scan. Detail in individual profiles. RC at top; rest alphabetical. "?" = unknown / not yet researched.

| | Coverage | Funded by | Has to | Doesn't have to | Borrowable infra | Borrowable shape? |
|---|---|---|---|---|---|---|
| **[Richmond Commons](./_self.md)** | 1 city | Operator's pocket | — | (everything) | n/a | n/a |
| [Aware](./aware.md) | 3,835 cities | Unknown investor(s) | Justify $400-$1,000/mo gov contracts; sell hardware kit | Be Richmond-specific; ignore non-paying cities | Hardware-capture pattern for cities w/o streams; tiered freemium UX | No |
| [citymeetings.nyc](./citymeetings-nyc.md) | NYC Council | Solo founder's time | Eventually monetize via paid pro tier (lobbyists/journalists) | Cover anything other than NYC | **Deepgram + GPT-4 Turbo + T### markers + 8K chunking + 200+ ground-truth eval** | No (planning freemium) |
| [Civic Sunlight](./civic-sunlight.md) | ~20 Maine towns | Founders + grants? | Recover from public hallucination story; partner w/ newsroom for review | Rush summaries to publication | Cautionary lesson on hallucinations | No (still pre-product/market fit) |
| [CivicPlus](./civicplus.md) | 1000s of cities (incumbent) | PE-backed | Defend Archive Center / govtech suite; sell enterprise renewals | Care about residents directly | Their Archive Center is *our scrape source* | No |
| [Hamlet](./hamlet.md) | 1,800 bodies, 50+ states | Unknown | Sell to real-estate developers + lobbyists; produce RVI/RFI scores their buyers want | Be a citizen tool | Search-by-company-name pattern | No |
| [HeyGov ClerkMinutes](./heygov.md) | ? | ? | Sell to clerks; integrate w/ govtech procurement | Show residents anything | None directly relevant | No |
| [Locunity](./locunity.md) | ~100 jurisdictions | $125K SAIF | Justify next round to SAIF; sell B2B advocacy/chamber accounts; build action marketplace | Stay residential-only | **Smart Brevity scaffold; per-meeting email; named-quote extraction; commenter coverage** | No |
| [Next30Days](./next30days.md) | Seattle, Bellevue | ? | ? | ? | Pre-meeting briefing as primary surface | Maybe (orientation framing) |
| [OpenCouncil](./opencouncil.md) | 10 Greek municipalities | Helidoni Foundation | Serve Greek civic mandate; satisfy Helidoni grant | Be US-centric | **Full open-source AGPL-3.0 stack — read their code freely** | Partial (open-source decision) |

## What each player has to do (and RC doesn't)

The same data, sliced by constraint:

- **Locunity** has to deliver SAIF a venture-scale outcome. That means building toward an action-marketplace where advocacy groups pay to be the recommended action on tracked issues. RC doesn't have to do this; the operator can refuse to monetize action.
- **Aware** has to justify $400+/mo to municipal procurement officers. That's why they built Aware Capture (hardware) and blockchain hashing — both are procurement-friendly story elements. RC doesn't sell to procurement.
- **citymeetings.nyc** has to eventually fund Vikram's time. That's why a paid pro tier for lobbyists/journalists is on his roadmap. RC's operator funds itself by not needing to be funded.
- **Hamlet** has to deliver Regulatory Velocity / Friction scores their buyers (developers, data center site selectors) actually use to make decisions. They've optimized the product for that buyer's question. RC isn't optimizing for any buyer.
- **HeyGov / CivicPlus** have to keep B2G procurement contracts renewing. Their product priorities reflect what city clerks ask for in RFPs. RC doesn't sell to cities.
- **Civic Sunlight** has to recover from a public hallucination incident. They added human review under reputational pressure. RC built provenance discipline pre-incident as a structural feature.
- **OpenCouncil** has to serve a Greek civic mandate that includes WhatsApp / TikTok / Reels because that's where Greek citizens are. RC's distribution is whatever the operator wants.
- **Next30Days** has Seattle/Bellevue scope because that's where the founder's network is. RC's scope is whatever Richmond happens to need.

In all cases the constraint is **legible from the structure of who funds them**. The infrastructure they build is real and reusable. The shape they take is downstream of constraints we don't have.

## What RC can do that no one else can

Optionality enabled by no buyers / no LPs / no runway / for-fun:

- **Be wrong about what to build, then change it without explaining to anyone.** Pivots cost RC nothing externally. They cost competitors trust, runway, and team morale.
- **Refuse to monetize even when offered.** Locunity's residential free tier *has* to feed the B2B funnel. RC's free tier feeds nothing — it just exists.
- **Build features no one would pay for.** The conflict scanner, the bias audit, the source-tier discipline, the public records compliance dashboard, the commission rosters. Each of these is unjustifiable to a B2B buyer; each is high-value to a Richmond resident.
- **Stay deeply Richmond-specific.** Locunity needs to scale to "America's civic intelligence layer" because $125K → next round → 9-figure outcome. RC can stay one city forever, or expand only when the architecture is genuinely ready.
- **Open-source on the operator's terms.** No commercial licensing pressure. Pick AGPL or BSL or MIT based on what feels right, not what investors prefer.
- **Adopt or refuse Smart Brevity.** Locunity *has* to deliver the format their B2B buyers expect (Axios style; chambers of commerce read Axios). RC can adopt the *parts* that serve Richmond residents and discard the *parts* that serve commercial buyers.
- **Kill features without explaining.** Operator gets bored with the influence map? Kill it. No press release. No churn alarm. No board to convince.

## How to use this when making a decision

When a feature decision comes up, ask in this order:

1. **Is this borrowed *technical* infrastructure?** (Prompt structure, ASR vendor, chunking strategy, time-marker format, open-source library.) → Take it freely.
2. **Is this borrowed *business* infrastructure?** (Buyer alignment, advocacy framing, growth funnel, action marketplace, scaling pressure.) → Don't take it. The constraint will follow the shape.
3. **Does this preserve or reduce optionality?** (Can we stop doing this in 6 months without pain? Can the operator pivot to something different without breaking promises?) → Optionality-preserving choices win.

That's the negative map.

## Sibling indexes

- [`docs/research/`](../) — broader research output
- [`docs/AI-PARKING-LOT.md`](../../AI-PARKING-LOT.md) — research + ideas queue
- [`docs/PARKING-LOT.md`](../../PARKING-LOT.md) — sprint execution
