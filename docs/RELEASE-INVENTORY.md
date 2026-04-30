# Release Inventory

_Generated 2026-04-27. Read-only snapshot of every public-routable page in `web/src/app/`. No recommendations — fill the **Decide** column when you're ready: `keep` / `hide` / `gut` / `pivot` / `abandon`._

## How to read this

- **Nav?** — entry visible in `web/src/components/Nav.tsx` desktop dropdowns
  - **Public** — citizens see it
  - **OP** — only visible in operator mode (cookie-flagged)
  - **Contextual** — not in Nav, but linked from a Nav-visible page (e.g. detail pages)
  - **None** — no nav surface; reachable only by direct URL or external/old links
- **Page gate** — does the route's `page.tsx` use `OperatorGate`?
  - **Full** — whole page wrapped (with or without fallback)
  - **Partial** — only some sections gated (operators see more)
  - **No** — unrestricted server-side
- **Tier** — `publication_tier:` in `docs/pipeline-manifest.yaml`. Blank = unmarked.
- **Effective** — synthesis of the above
  - **Live** — citizen finds it via Nav or contextual link, no gating in their path
  - **Operator-only** — Nav hides + page gate (defense-in-depth)
  - **Soft-hidden** — publicly reachable URL, no Nav, no gate (hidden by absence, not by enforcement)

---

## Meetings

| Route | Description | Nav | Page gate | Tier | Effective | Decide |
| --- | --- | --- | --- | --- | --- | --- |
| `/` | Home — upcoming meetings | Public (logo) | No | — | Live | |
| `/meetings` | Meetings index, calendar, month-grouped list | Public | No | — | Live | |
| `/meetings/[id]` | Meeting detail — agenda, votes, attendance | Contextual | Partial | — | Live | |
| `/meetings/[id]/items/[itemNumber]` | Single agenda item detail | Contextual | Partial | — | Live | |
| `/meetings/category/[slug]` | Items in a category | Contextual | No | — | Live | |
| `/meetings/most-discussed` | Items with most public testimony | Public | No | graduated | Live | |
| `/topics` | Topic index (organic, recurrence-promoted) | Public | No | — | Live | |
| `/topics/[slug]` | Topic timeline | Contextual | No | graduated | Live | |

## Council

| Route | Description | Nav | Page gate | Tier | Effective | Decide |
| --- | --- | --- | --- | --- | --- | --- |
| `/council` | Council member grid | Public | No | — | Live | |
| `/council/[slug]` | Member profile (bio, votes, donors, interests) | Contextual | Partial (with fallback) | — | Live (operator sees more) | |
| `/council/stats` | Voting stats, categories, controversy | OP | Full | — | Operator-only | |
| `/council/coalitions` | Pairwise voting alignment | OP | Full | — | Operator-only | |
| `/council/patterns` | Cross-meeting patterns + donor overlap | OP | Full | — | Operator-only | |

## Elections

| Route | Description | Nav | Page gate | Tier | Effective | Decide |
| --- | --- | --- | --- | --- | --- | --- |
| `/elections` | Elections index | Public | No | — | Live | |
| `/elections/[slug]` | Election voter guide | Contextual | Partial (with fallback) | — | Live (operator sees more) | |
| `/elections/[slug]/candidates/[name]` | Candidate detail | Contextual | Partial | — | Live (operator sees more) | |
| `/elections/find-my-district` | Address lookup → district + candidates | Public | No | — | Live | |
| `/elections/districts` | District map | Public | No | — | Live | |

## Influence (operator-only family)

| Route | Description | Nav | Page gate | Tier | Effective | Decide |
| --- | --- | --- | --- | --- | --- | --- |
| `/influence` | Official index with financial connection summaries | OP | Full | — | Operator-only | |
| `/influence/elections` | Election cycles index | None | Full | — | Operator-only | |
| `/influence/elections/[id]` | Election detail | Contextual | Full | — | Operator-only | |
| `/influence/item/[id]` | Agenda item influence map (item center) | Contextual | Full | — | Operator-only | |
| `/influence/methodology` | Methodology disclaimer | None | Full | — | Operator-only | |
| `/reports` | Per-meeting flag reports list | OP | Full | — | Operator-only | |
| `/reports/[meetingId]` | Per-meeting financial flags | Contextual | Full | — | Operator-only | |
| `/financial-connections` | Council-donor network | None | Full (with public fallback) | — | Soft-hidden | |

## Records / Quality (operator-only)

| Route | Description | Nav | Page gate | Tier | Effective | Decide |
| --- | --- | --- | --- | --- | --- | --- |
| `/public-records` | CPRA compliance dashboard | OP | Full | — | Operator-only | |
| `/data-quality` | Pipeline freshness monitoring | OP | Full | — | Operator-only | |
| `/commissions` | Commission index | OP | Full | — | Operator-only | |
| `/commissions/[id]` | Commission detail | Contextual | Full | — | Operator-only | |

## Subscribe / Email (unreleased)

| Route | Description | Nav | Page gate | Tier | Effective | Decide |
| --- | --- | --- | --- | --- | --- | --- |
| `/subscribe` | Email subscribe landing + topic picker | None | No | — | Soft-hidden | |
| `/subscribe/manage` | Token-authenticated preference center | None | No | — | Soft-hidden | |

API routes (no public page, but live endpoints): `/api/subscribe`, `/api/subscribe/preferences`, `/api/email/send-digest`, `/api/email/send-orientation`, `/api/email/send-recap`.

## Operator console

| Route | Description | Nav | Page gate | Tier | Effective | Decide |
| --- | --- | --- | --- | --- | --- | --- |
| `/operator/decisions` | Pending decision queue | OP | Full | — | Operator-only | |
| `/operator/sync-health` | Data source freshness | OP | Full | — | Operator-only | |
| `/operator/settings` | AI scoring parameters | OP | Full | — | Operator-only | |

## Other

| Route | Description | Nav | Page gate | Tier | Effective | Decide |
| --- | --- | --- | --- | --- | --- | --- |
| `/about` | Methodology, source tiers, disclaimers | Public | Partial (operator-only methodology section) | — | Live | |
| `/search` | Full-text + semantic search | Public (search box) | No | — | Live | |

---

## Observations worth flagging

1. **`/financial-connections` and `/subscribe*` are publicly URL-reachable but absent from Nav.** Citizens won't find them by browsing, but direct links work. "Soft-hidden" relies on no one knowing the URL — leaky if old links exist or a search engine indexed them.

2. **Tier coverage in `pipeline-manifest.yaml` is sparse.** Of ~30 page entries, only 3 carry an explicit `publication_tier:` (`graduated` × 3). No entries are marked `unreleased`. Making the field required and enforcing in `python src/pipeline_map.py validate` would surface every unmarked route as an action item.

3. **All operator-only pages use both layers** (Nav hide + `OperatorGate` wrap). Defense-in-depth holds. A non-operator who hits an operator URL directly sees the gate fallback, not the page.

4. **No code-level marker for "unreleased."** Subscribe pages, email API routes, and any other in-flight work look identical to production-ready surfaces in the source tree. Adding a `// UNRELEASED — see RELEASE-INVENTORY.md` header at the top of each page file you decide to retire would make the next pass mechanical.

5. **Public pages with `Partial` gating show operators a richer view of the same surface.** This is fine when the public version stands on its own. For each `Partial` row, worth asking: would the public version still feel coherent if the operator-only sections were removed? If not, the surface may need rethinking.

---

## Process from here

Suggested workflow when you have time:

1. Walk the table, write `keep` / `hide` / `gut` / `pivot` / `abandon` in the **Decide** column for each row.
2. Tell me a single feature you want to focus on next.
3. I execute the `Decide` column in one batch (Nav removal + manifest tier updates + any gating tightening), separately from the focus-feature work, on its own branch.
4. Code stays in-tree for everything except `abandon` rows — and even those just get the page route deleted; pipeline data and types remain for posterity.

Nothing on this list is urgent. The point of writing it down is so you don't have to hold it in your head while you focus on one thing at a time.
