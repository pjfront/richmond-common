# Visual Verification Workflow

_How Claude Code verifies its own frontend work using Claude Preview. Read this before making visual changes to any component or page._

## When to Verify

**After every visual change, before committing.** This includes:
- New components or pages
- Layout changes, spacing adjustments, responsive behavior
- Color, typography, or design token changes
- Content changes that affect page composition (T6 framing)
- Any change to a component listed in `DESIGN-DEBT.md`

## How It Works

Claude Preview (MCP tools) provides a built-in visual feedback loop:

1. **Start the dev server** — `preview_start` launches Next.js dev
2. **Navigate** — `preview_snapshot` loads any page and returns DOM structure
3. **Screenshot** — `preview_screenshot` captures the rendered page
4. **Inspect** — `preview_inspect` checks specific CSS values (spacing, colors, contrast)
5. **Resize** — `preview_resize` tests responsive behavior at different breakpoints
6. **Interact** — `preview_click`, `preview_fill` test interactive elements
7. **Debug** — `preview_console_logs`, `preview_network` catch runtime errors

No separate Playwright install needed. No test suite to maintain.

## Standard Breakpoints

Every visual change is verified at two widths:

| Breakpoint | Width | Represents |
|---|---|---|
| Desktop | 1280px | Standard laptop/desktop |
| Mobile | 375px | iPhone SE / small Android — mobile-primary older residents |

## Standard Pages to Check

After any change that could affect shared components (Nav, Footer, layout), screenshot these pages at both breakpoints:

1. **Homepage** — `/` (hero, search, navigation)
2. **Meeting detail** — `/meetings/[id]` (data-dense, agenda items, votes)
3. **Council profile** — `/council/[slug]` (T6 composition order, KPIs)
4. **Any page you just modified**

For changes scoped to a single page, only that page needs verification.

## Screenshot Storage

Screenshots are ephemeral — they exist in the conversation context for review, not saved to disk. If a screenshot reveals a violation worth tracking, add it to `DESIGN-DEBT.md` with the specific rule and component.

---

## Design Rule Verification Checklist

Every rule from `DESIGN-RULES-FINAL.md` is classified by verification method. After visual changes, check all Tier A and Tier B rules. Tier C requires human review.

### Tier A — DOM/Inspection Verifiable

_Can be verified programmatically via `preview_inspect`, `preview_snapshot`, or `preview_console_logs`. These are mechanical checks._

| Rule | What to Check | How |
|---|---|---|
| **U2** (semantic HTML) | Heading hierarchy h1→h2→h3, no skipped levels | `preview_snapshot`: check heading structure in DOM |
| **U2** (Radix primitives) | No `<div onClick>` reimplementations | `preview_snapshot`: interactive elements use proper roles |
| **U4** (signal depth) | Collapsed sections include counts | `preview_snapshot`: verify count text in section headers |
| **U9** (states) | Loading/empty/error states defined | `preview_snapshot`: trigger each state, verify content |
| **U11** (touch targets) | Interactive elements ≥ 44×44px | `preview_inspect`: check computed width/height |
| **U11** (reflow) | No horizontal scroll at 200% zoom | `preview_resize` to 640px width (simulates 200% on 1280) |
| **A1** (labels) | Form inputs have `<label>` elements | `preview_snapshot`: check label association |
| **A2** (contrast) | 4.5:1 body text, 3:1 large text/UI | `preview_inspect`: compare foreground/background colors |
| **A3** (keyboard) | Tab order is logical | `preview_eval`: simulate tab navigation |
| **A4** (ARIA) | Live regions on dynamic content | `preview_snapshot`: check `aria-live`, `role="alert"` attributes |
| **A5** (responsive) | Card/list layout on narrow viewports | `preview_resize` to 375px, `preview_snapshot` |
| **C3** (tables) | Sortable, `<caption>` present, CSV button visible | `preview_snapshot`: check table structure |
| **C4** (CivicTerm) | Plain language visible, tooltip has structured content | `preview_snapshot` + `preview_click` on term |
| **C6** (SourceBadge) | Source tier + freshness on every card | `preview_snapshot`: search for badge elements |

### Tier B — Screenshot Verifiable

_Requires visual judgment from the AI. Checked via `preview_screenshot` and evaluated against the design rules._

| Rule | What to Look For |
|---|---|
| **U1** (source attribution) | Every data point has a visible source link, timestamp, and tier badge |
| **U3** (3 KPIs) | Summary cards show exactly 3 metrics; one is visually dominant |
| **U5** (2-click depth) | Detail views show export/download affordances in toolbar, not behind menus |
| **U6** (no interstitials) | Data loads immediately; no splash, onboarding, or gated explainers |
| **U7** (Norman/Tufte) | Polished chrome on cards/nav; minimal decoration in data areas |
| **U8** (AI labels) | AI-generated content marked "AI-generated summary" (not just "Summary") |
| **U10** (URLs) | Pages use human-readable slugs; filter state in URL params |
| **U13** (low-confidence) | No low-confidence data in summary counts or flags |
| **T1** (plain language) | Navigation uses plain words: "Money" not "Campaign Finance" |
| **T2** (benchmarks) | Dollar figures and percentages include inline comparison context |
| **T3** (Tier 3 disclosure) | Tier 3 sources show bias parenthetical every time |
| **T4** (hedged language) | AI summaries use factual phrasing, no characterizations |
| **T6** (page composition) | Profile pages: identity/role first → activity → flagged findings last |
| **T7** (narrative over numbers) | Primary presentation is sentences, not charts/tables/raw stats |
| **A2** (color independence) | Information conveyed by color is also conveyed by shape/label/pattern |
| **C1** (chart annotations) | Charts have at least one visible text annotation; factual, not interpretive |
| **C7** (search) | Search input visible in top nav on every page |
| **C8** (confidence) | Below-90% data points show confidence indicator |

### Tier C — Human Judgment Required

_Cannot be verified by AI. Flag for Phillip's review._

| Rule | Why It Needs Human Review |
|---|---|
| **T4** (tone) | Whether hedged language *feels* neutral vs. stilted requires editorial judgment |
| **T6** (framing) | Whether page composition creates an accusatory *impression* is subjective |
| **T7** (narrative quality) | Whether narrative descriptions are clear to a lay audience |
| **U14** (corrections) | Whether correction/context mechanisms feel fair and accessible to officials |
| **C5** (CivicMetric) | Whether benchmark comparisons are genuinely clarifying vs. misleading |
| **"Sunlight not surveillance"** | Whether the overall page *feels* like a governance assistant vs. a gotcha tool |
| **Publication tier** | Whether a feature is ready to graduate from operator-only to public |

---

## Verification Workflow

```
1. Make your visual change
2. preview_snapshot the modified page — check Tier A rules (DOM structure)
3. preview_screenshot at 1280px — check Tier B rules (visual quality)
4. preview_resize to 375px + preview_screenshot — check mobile layout
5. If shared components changed, repeat for standard pages
6. Fix any violations found
7. Note any Tier C items for human review in the commit message
8. If a new violation can't be fixed now, add to DESIGN-DEBT.md
9. Commit
```

## What This Does NOT Replace

- **Human design review.** Tier C rules require Phillip's judgment.
- **Claude Chat design feedback.** Strategic design philosophy and UX strategy happen there.
- **CI/CD tests.** This is a self-check workflow, not an assertion suite that blocks deployment.
