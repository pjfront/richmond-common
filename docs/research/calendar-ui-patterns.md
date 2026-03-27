# Sparse civic calendars need lists, not grids

**A monthly grid calendar is the wrong default for Richmond Commons' ~2-meetings-per-month schedule.** UX research consistently shows that grid calendars underperform list/agenda views when event density drops below roughly one event per week — and at two per month, a 42-cell grid leaves 95% of cells empty. The strongest pattern for this civic use case is a **grouped agenda list as the primary view** with an optional mini-calendar for date navigation, an inline detail expansion panel, and a responsive mobile-first layout built with pure CSS Grid and Tailwind — no heavy calendar library needed.

This matters because Richmond Commons' audience — journalists on deadline, citizens checking meeting times on phones, city staff sharing links — all need to answer one question fast: *when is the next meeting, and what's on the agenda?* A sparse grid buries that answer. The research below covers layout patterns, interaction design, accessibility, implementation strategy, and real-world examples across civic tech, performing arts, and library systems.

---

## Why the agenda list wins for two meetings a month

Anders Toxboe of UI-Patterns.com states it directly: "The boxed calendar renders almost useless without data. If you only have one or two events a month, the usefulness of the calendar box becomes minimal." Designers default to Google Calendar-style grids because they use them daily for personal scheduling, but those tools optimize for *day-to-day planning with dozens of events* — not for providing an *overview of upcoming civic events*.

Stratifi Creative's 2025 UX analysis reinforces this with a systematic comparison. Grid calendars suffer from **poor scanning** (users ask "what's next?" not "what's on March 14th?"), **cramped mobile rendering**, **accessibility challenges** with screen readers, and **high cognitive load**. Their research found list views excel on every dimension that matters for civic users: ease of scanning, mobile compatibility, screen reader friendliness, and focus on events rather than dates.

The strongest alternative patterns, ranked by fit for this use case:

- **Chronological agenda list** — linear, scrollable, mobile-optimized, screen-reader native. Timely's agenda view explicitly hides dates without events, so "your calendar always looks full, without any blank spaces." This eliminates the empty-state problem entirely.
- **Grouped accordion by month** — Toxboe recommends grouping events into "buckets of time" because "as humans, we don't think in dates. We think in 'buckets' of time: tonight, this weekend, next month." For Richmond's 2020–2026 archive, collapsible month groups let users browse six years of meetings efficiently.
- **Hybrid mini-calendar + agenda** — a compact month grid serves as a *navigation aid* (not the primary view), paired with a detail list below. Fantastical and Google Calendar mobile both use this pattern. The key insight from Welie.com's pattern library: "When the event calendar only has events on some days, make days with events linkable and others not" — dimming or disabling eventless dates in the mini-calendar.

If a grid view is offered at all, it should be secondary and compact. **Dot indicators** on meeting dates (not text labels in cells) keep the grid functional without visual clutter. The grid becomes a date-picker, not a content display.

## Inline expansion beats page navigation for meeting details

The most effective interaction for revealing meeting details — agenda, minutes, votes, video links — is an **inline expansion pattern** where clicking a meeting keeps the calendar/list visible and opens a detail panel without page navigation. Research identified four distinct variants used in production.

**The accordion/expand-below pattern dominates civic sites.** Chicago's City Clerk portal (chicityclerkelms.chicago.gov), CivicPlus municipal platforms, and Yorba Linda, CA all use list-based meeting displays where clicking a meeting row reveals agenda items, minutes PDFs, and video links inline. This is the most natural fit for Richmond Commons' list-first approach. Implementation uses `aria-expanded="true/false"` on the trigger with `aria-controls` pointing to the detail region, and focus moves into the expanded content on activation.

**The popover/bubble pattern** (Google Calendar, Apple Calendar) works for quick previews but struggles with the volume of content a civic meeting carries — agenda PDFs, minutes, vote records, and streaming links need more space than a popover provides. **The side-panel pattern** (Outlook, Oracle Alta "master-detail in-context") provides generous space and keeps both navigation and details visible simultaneously, but requires wider viewports and collapses to stacked layout on mobile.

**The calendar-plus-agenda-below pattern** (demonstrated by Mobiscroll) is the recommended hybrid: a month grid at top with a scrollable agenda/detail section below. Clicking a date scrolls the agenda to that day's meetings. This preserves spatial context while giving meeting details ample room. For mobile, it naturally stacks into mini-calendar → detail list.

The ARIA implementation for inline expansion follows a clear sequence: `aria-expanded` on trigger, move focus to first focusable element in expanded content on open, return focus to trigger on Escape. No `aria-live` region is needed when focus management handles the state change — pairing live regions with focus moves causes screen reader conflicts.

## Real civic tech platforms overwhelmingly use lists

A survey of civic and government calendar implementations reveals a striking pattern: **list views dominate, grid calendars are rare, and the most effective sites combine lists with lightweight navigation aids.**

**TheyWorkForYou** (UK Parliament tracker) offers the best hybrid model observed. It uses a daily agenda list organized by chamber and committee type, with a small monthly grid calendar in the sidebar showing clickable dates — only dates with scheduled business are linked. Every MP name in the agenda is hyperlinked to their profile, creating a rich cross-referenced civic information network. This is the closest existing model to what Richmond Commons should build.

**Chicago Councilmatic** (built by DataMade) uses a clean chronological list with links to agendas and legislation. It "demystifies" city council by linking meetings to legislation and council members, but offers no grid calendar and no timeline. **Granicus/Legistar** — the dominant platform used by hundreds of cities including Richmond — provides utilitarian list-based meeting displays with links to agendas, minutes, and video. Its public-facing interface is functional but not citizen-friendly — text-heavy with minimal visual design.

**Portland, OR** provides the clearest meeting-type taxonomy: Regular Council Meetings (voting sessions), Work Sessions (informational, no public testimony), and Executive Sessions (closed). Each type has an explicit explanation of what citizens can expect, which is a model worth emulating.

Outside civic tech, **performing arts venues handle sparse high-value events effectively.** The Kennedy Center uses a scrollable chronological list with rich visual cards showing date ranges, descriptions, and genre filters — gracefully handling variation from empty days to ten-plus events. Lincoln Center uses a vertical daily list in a weekly grid structure with filtering by event type and presenting organization. **Library systems** like Phoenix Public Library use the LibraryMarket platform, purpose-built for the "many locations, sparse events per location" pattern with location-based browsing and room reservation integration.

**Court docket calendars** are universally plain text lists — no grid views exist in court calendar systems. This reinforces the principle that for sparse, high-importance events with legal implications, lists are the natural format.

## Calendar scope should layer meetings with optional civic dates

Most civic platforms show only official meetings, but the strongest approach is a **layered system with meetings as the primary layer and adjacent civic dates as a filterable secondary layer.**

The case for inclusion is compelling: citizens don't think in terms of "meetings" versus "deadlines" — they want to know *what requires their attention*. A budget vote meeting gains context when shown alongside the public comment deadline that precedes it. CivicPlus research shows residents attend meetings when they understand relevant topics are being discussed.

The case for restraint is equally valid: mixing meeting notices (which carry legal open-meetings-law obligations) with informational dates risks confusing the calendar's official status. Data maintenance becomes harder when different departments own different date types. TheyWorkForYou's focused approach — only official parliamentary business — works well precisely because of its clarity.

The practical consensus from civic tech implementations points to three layers: **primary** (official meetings — legally required, clerk-maintained), **secondary** (public comment periods, budget cycle milestones, filing deadlines — filterable, opt-in), and **integration** (link to authoritative external sources like BallotReady for elections rather than duplicating that data). Austin, TX is notable for archiving election documents alongside meeting records, suggesting the boundary between "meeting" and "civic date" is already blurred in practice.

## Accessible encoding needs color, shape, and text together

WCAG 2.1 Success Criterion 1.4.1 is unambiguous: "Color is not used as the only visual means of conveying information." A calendar using only colored dots for meeting types fails Level A compliance. Nielsen Norman Group research found users are **37% faster** at finding categorized items when visual indicators use both color and icon compared to text alone.

For Richmond Commons' four meeting types, a **3-channel encoding system** provides robust accessibility:

| Meeting type | Color | Shape | Border style | Badge text |
|---|---|---|---|---|
| Regular Meeting | Blue (#0066CC) | ● Filled circle | Solid left accent | "Regular" |
| Special Meeting | Orange (#CC6600) | ★ Star | Dashed left accent | "Special" |
| Closed Session | Purple (#663399) | ■ Square / 🔒 Lock | Dotted left accent | "Closed" |
| Joint Meeting | Teal (#008080) | ◆ Diamond | Double left accent | "Joint" |

**Blue and orange** are the most universally distinguishable color pair across common color vision deficiencies. The palette avoids red-green pairings (which affect ~8% of men) and varies significantly in luminance — passing the grayscale test NNGroup recommends. Each channel is independently sufficient: a user who cannot perceive color differences can distinguish shapes; a user who cannot perceive shapes can read text badges; CSS border styles provide a fourth redundant channel visible even in Windows High Contrast Mode.

For the calendar grid's ARIA implementation, the W3C APG datepicker pattern applies with modification. Use `role="grid"` with roving `tabindex` for the month view — arrow keys navigate between days, Enter/Space activates a date to expand meeting details. Each `gridcell` needs a rich `aria-label`: "Tuesday, March 18, 2025. 1 event: Regular Meeting, 6:00 PM, City Hall Council Chambers." The month/year heading should use `aria-live="polite"` so screen readers announce navigation changes. However, accessibility expert Adrian Roselli warns that `grid` semantics can be problematic — they override native table navigation and require extensive labeling. **For the agenda/list view, semantic HTML with headings and an unordered list is simpler and more robust.** This is another argument for making the list view primary.

## Build the grid from scratch with CSS Grid and date-fns

For a read-only civic calendar with ~2 events per month, **a custom CSS Grid implementation with Tailwind CSS v4 and date-fns is the right approach** — not FullCalendar, not react-big-calendar, not any heavy scheduling library. The entire month grid is fundamentally `grid-cols-7` with day cells. Libraries like FullCalendar (~80KB) and react-big-calendar (~50KB+) are engineered for interactive scheduling with drag-and-drop and resize — features a read-only civic calendar doesn't need.

The core technique, documented in Zell Liew's canonical CSS Grid calendar tutorial: set `grid-template-columns: repeat(7, 1fr)`, position the first day of the month using `grid-column-start` based on its weekday index, and CSS Grid's auto-placement fills the rest. **date-fns** (~6KB tree-shaken) handles all date math: `startOfMonth`, `endOfMonth`, `eachDayOfInterval`, `getDay`, `format`, `addMonths`.

For URL state, **nuqs** (~6KB, featured at Next.js Conf 2025) is the premier solution. It provides a `useQueryState` hook that mirrors `useState` but syncs with the URL, enabling `/meetings?month=2024-03` with browser back/forward support. Use `history: 'push'` for month navigation so the back button returns to the previous month, and `history: 'replace'` for filter changes to avoid polluting browser history. On the SEO side, The Events Calendar (WordPress) explicitly sets `noindex` on calendar month views to prevent index bloat. **Individual meeting pages** (`/meetings/planning-commission-2024-03-15`) should be the indexed resources with Event schema JSON-LD; the calendar view is a navigation interface with a canonical URL stripped of query parameters.

The responsive strategy is critical for Richmond Commons' audience of mobile-primary citizens and older users. **On desktop (≥768px)**, render the full 7-column CSS Grid with meeting details in cells. **On mobile**, switch entirely to a mini month picker at top with a scrollable agenda list below — never show a cramped 7-column grid on a phone. Touch targets must meet the **44×44px WCAG minimum**. Base font size should be 16px minimum on mobile to prevent iOS auto-zoom. Respect `prefers-reduced-motion` for month transition animations.

Reference implementations worth examining include `@zach.codes/react-calendar` (Tailwind-native with hooks like `useMonthlyCalendar`), the official Tailwind UI calendar blocks (paid, production-grade), and the shadcn/ui full-calendar community component. shadcn/ui's built-in Calendar component is built on react-day-picker — excellent for date *selection* but not designed for event *display*, so it's useful as the mini-calendar navigator but not as the main meeting view.

## Conclusion

The recommended architecture for Richmond Commons' meeting calendar inverts the typical calendar design instinct. **Make the agenda list primary, the grid secondary, and the detail panel inline.** The key technical decisions: query-parameter URL state with nuqs (`/meetings?month=2024-03`), custom CSS Grid + Tailwind v4 + date-fns (zero calendar library dependencies, ~12KB total), responsive breakpoint that swaps grid for list on mobile, and 3-channel meeting-type encoding (color + shape + text) for accessibility.

Three implementation insights emerged that weren't obvious before research. First, the most successful civic calendar in the wild — TheyWorkForYou — uses the hybrid pattern (tiny sidebar grid + rich agenda list) that this analysis recommends, validating the approach with a decade of parliamentary tracking. Second, the ARIA `grid` role, while technically correct for a calendar, introduces enough screen reader complexity that accessibility experts increasingly recommend semantic list markup for event calendars — making the list-primary design choice an accessibility win, not just a UX preference. Third, the "next meeting" answer is so dominant as the user's actual question that it deserves a persistent, prominent element above any calendar view — a single card showing the next scheduled meeting with countdown, type badge, and agenda link, satisfying the majority use case before the user ever scrolls.