# Interactive Data Visualization for Richmond Commons

**Status:** Research reference. The S29 UX cut removed the overbuilt PAC detail
profile matrix, timeline, and cycle controls in favor of a shared sentence-first
detail profile with filing receipts. The existing PAC index controls and
sparkline remain unchanged. Do not treat the detail-profile recommendations
below as active implementation direction without a new operator decision.
**Date:** 2026-04-29
**Routing note:** Two in-process research agents (a74051c4, a4d87e32) hung silently without producing this doc; the operator routed around them via claude.ai. The text below is preserved verbatim from those sessions and lightly reformatted into a single document. The first part is the broad pattern library; the second is a focused field study of the temporal middle layer.

---

# Part 1: Interactive Civic-Money Data Visualization: A Pattern Library for Richmond Commons

This document is a working reference for extending the [voting-patterns page](https://richmondcommons.org/council/voting-patterns) into new pages on PACs, donor profiles, and vendor relationships. It captures what we learned from studying six well-regarded civic-money visualizations and proposes a three-layer template ("Explore, Temporal, Receipt") with a sixth structural move that the original voting-patterns page does not yet have.

A note on access: a direct fetch of `richmondcommons.org/council/voting-patterns` returned a permissions error from the research environment, so the description of its five structural moves below is taken from the project brief and treated as the working spec. The references that follow either confirm or stretch each of those moves.

## Framing

Voting-patterns works because it picks one matrix as the playable surface and lets every other element behave like punctuation. The challenge for PACs and vendors is that money has a temporal shape that votes do not. A council member voted yes or no on Tuesday. A PAC has been raising and spending across multiple election cycles, and the question a Richmond resident actually asks ("is this normal for them, or is this cycle different?") cannot be answered without showing time. So the new pages need a middle layer the voting page never needed.

## References

### 1. OpenSecrets PAC profile pages

[OpenSecrets PAC profiles](https://www.opensecrets.org/political-action-committees-pacs) (e.g. the [Google Inc. PAC page](https://www.opensecrets.org/political-action-committees-pacs/google-inc/C00428623/summary/2018)) are the genre-defining federal PAC page: a single committee's totals, top recipients, and partisan split, scoped to one election cycle.

**What works.** The cycle selector at the top of every page (2024, 2022, 2020, etc.) is the simplest and most copy-able temporal pattern in this whole survey. It treats the election cycle, not the calendar, as the natural unit of time. Plain-language headlines ("INTERACTIVE CORP POLITICAL ACTION COMMITTEE raised $0 in the 2023-2024 election cycle") set the frame before any chart loads. Receipt-style tables of recipients sit below the summary.

**What to borrow.** The cycle dropdown as the only time control. The "this PAC raised $X in this cycle" sentence as the first thing a visitor sees. The discipline of letting subsidiaries and affiliated PACs roll up under a parent, with a footnote explaining the rollup.

**What to skip.** The dense seven-column tables on inner pages, the recurring fundraising appeals interleaved with data, and the analyst-oriented FEC release dates in body copy. A Richmond resident does not need to see "data released by the FEC on May 03, 2025" above the fold.

### 2. The Pudding: "In pursuit of democracy"

[The Pudding's 2025 "In pursuit of democracy"](https://pudding.cool/2025/11/democracy/) plots every congressional speech containing the word "democracy" since 1880, with brighter dots marking speeches that frame democracy as under threat.

**What works.** Time IS the spine. One bold visualization, scroll-driven, with annotated speeches surfacing at moments of historical inflection (Pearl Harbor, Citizens United, January 6). Plain language throughout: "Each dot represents five speeches." The reader is never asked to interpret a statistic.

**What to borrow.** The annotation style: short paragraph, primary-source quote, citation. The willingness to commit to a single visual metaphor and let interactivity be a reward (click a dot, get a curated speech) rather than a control panel. The use of brightness or saturation to mark a meaningful subset rather than introducing a second chart.

**What to skip.** Pure scrollytelling. A governance assistant cannot ask a council member to scroll through a six-screen narrative to find one PAC's filing. Scroll is a storytelling tool, not a lookup tool.

### 3. NYT Upshot: 2020 Democratic donor maps and the Biden-Trump fundraising surge

The [NYT 2020 Democratic donor maps](https://www.nytimes.com/interactive/2019/08/02/us/politics/2020-democratic-fundraising.html) (and the late-2020 [Biden surge map](https://ktla.com/news/politics/how-did-your-neighbors-donate-nyt-map-breaks-down-trump-biden-split-by-zip-code/)) plot 2.2 million individual donations down to ZIP code, with a time scrubber showing when each candidate's geographic base activated.

**What works.** The temporal layer answers a specific question the static map cannot ("when did Biden overtake Trump, and where?"). Selection on the map (a state, a ZIP code) is reflected in the time chart and vice versa. Plain framing: "down to the ZIP code."

**What to borrow.** The two-way binding between geography and time. The "as-of-date" caption that updates as the user scrubs.

**What to skip.** Animated auto-play. Auto-play is good for a launch tweet, bad for a tool people return to. Also skip the paywall pattern.

### 4. Washington Post: Trump-Harris donor ZIP code map

The Post's [2024 donor map](https://www.washingtonpost.com/elections/interactive/2024/trump-harris-donors-zip-code-map/) cross-references FEC online contributions with voter registration data to show who gave, by age, gender, and party, down to ZIP.

**What works.** The selection-rewrites-the-context-strip pattern that voting-patterns already uses, applied to money. Pick a county, and the prose updates: "Forty-two percent of male donors in Arizona under the age of 45 who were registered to vote gave to Trump." That sentence is the model for our context strip.

**What to borrow.** The plain-language sentence template "X percent of [filtered group] gave to [recipient]" as the primary readout, with the chart as supporting evidence rather than the headline. The methodological footnote written in plain language.

**What to skip.** The demographic match against L2 voter files. That is an analyst layer that adds inference uncertainty Richmond Commons should not import.

### 5. FollowTheMoney.org / VPAP

[FollowTheMoney.org](https://www.followthemoney.org/) (now folding into OpenSecrets) and Virginia's [VPAP](https://www.vpap.org/money/top-donors/) are the closest comparables for Richmond, since they cover state and local races where dollar amounts are smaller and individual donors matter more.

**What works.** VPAP's [Top Donors page](https://www.vpap.org/money/top-donors/) layers an election-cycle dropdown ("All Years / 2024-2025 / 2022-2023 / ..."), an entity-type filter (state candidates, local candidates, federal super PACs), and a sortable detail table. This is the voting-patterns three-part anatomy applied to money. FollowTheMoney's "Timeline tool" shows when an industry's donations were made within a cycle, which is the closest example of a selection-responsive temporal layer.

**What to borrow.** Biennial cycle buckets as the temporal grain. Industry rollup as a filter that does not dominate the surface. The locality and ZIP filters as orthogonal layers, not nested menus.

**What to skip.** The "all 50 states" navigation chrome. Richmond is one city; the navigation should reflect that.

### 6. ProPublica FEC Itemizer + MapLight (selection-responsive timelines)

[ProPublica's FEC Itemizer](https://projects.propublica.org/itemizer/) is a fast lookup of recent filings, useful as a model for the receipt layer. More relevant for the temporal middle layer is [MapLight](http://classic.maplight.org/us-congress/guide/data/money), whose "Timeline of Contributions" shows when donations arrived relative to a vote on a specific bill. That is the exact pattern the PAC redesign needs: pick an entity, see its money flow plotted against the cycle's natural beats.

**What works.** Money plotted against a meaningful event line (a vote, a filing deadline, an election day) rather than against an arbitrary calendar.

**What to borrow.** Event-anchored tick marks on the timeline. Tooltips that read like sentences ("Northam received $25,000 from Dominion Energy three weeks before the SCC vote").

**What to skip.** The implicit causal claim. MapLight's own disclaimer is good practice: contributions correlate with votes; the visualization should not say more than the data does.

### Couldn't reach

- **Bloomberg Government election graphics**: behind a paid subscription wall; public Bloomberg election pages are results trackers rather than money trackers. What we'd want from them: their cycle-over-cycle small-multiples treatment of independent expenditure spending.

## Template definition: Explore, Temporal, Receipt

The new template has three layers, each with one job.

**Top: Explore (the playable surface).** One primary interaction, one metaphor: a matrix for voting-patterns, a network or sankey for PACs, a sortable matrix of vendor-to-department flows for procurement. The user's first click happens here.

**Middle: Temporal (the cycle mirror).** A row of small bars or a thin line, keyed to election cycles, that responds to whatever is selected above. Toggleable, but on by default for money pages. Off for voting-patterns, where there is no meaningful "previous cycle" of the same vote.

**Bottom: Receipt (the detail table).** Sortable, scannable, exportable. Never the headline.

### The five existing structural moves of voting-patterns

1. **One primary axis of exploration.** The alignment matrix is the thing; everything else is filter or detail.
2. **Selection has immediate visible consequence.** Click a matrix cell, the context strip rewrites in plain language ("Showing 23 votes where Brown and Wilson voted differently").
3. **Filters are orthogonal to selection.** Matrix selection, filter bar, and search box combine; each layer is independent.
4. **Detail table is the receipt, not the headline.** It sits below, sortable, scannable.
5. **Plain language all the way down.** No statistical jargon. "Share of split votes where two members voted the same direction," not "pairwise agreement rate."

### The sixth move: the cycle mirror

The temporal layer is keyed to election cycles, not calendar time, and it mirrors the user's current selection from the explore layer above. When a Richmond resident clicks "Dominion Energy" in the donor matrix, the cycle mirror redraws as four small bars labeled 2018, 2020, 2022, 2024, each showing what that donor gave that cycle. The mirror's job is to answer one question in plain language: "Is what I am looking at right now normal for this entity, or is this cycle unusual?" It uses cycles because cycles are the natural beat of civic money, and it mirrors selection because an unanchored timeline is just a wallpaper.

### Anti-patterns to avoid

1. **Auto-playing animations.** Good for a launch tweet, bad for a tool people return to. Always require a user gesture.
2. **Continuous calendar timelines for cycle-keyed data.** A line chart by month implies a smoothness that biennial filings do not have. Use cycle-keyed bars instead.
3. **Statistical jargon in the headline strip.** "Pairwise agreement rate" failed the Leisa Johnson test on voting-patterns; "average ideological distance from median donor" will fail it on PACs.
4. **Two competing primary visualizations.** A matrix above a sankey above a table is three primary visualizations. Pick one to be the surface; demote the rest.
5. **Inferred fields shown without provenance.** If a donor's industry is AI-extracted at 84% confidence, do not put it in the headline count. Show it in a tooltip with the confidence flag, per the platform's existing standard.

### Three concrete recommendations for the PAC redesign

1. **Adopt the OpenSecrets cycle dropdown as the only time control above the fold, but render its current value as a sentence.** Not a bare "2024-2025" pill, but "Showing the 2024-2025 cycle. Switch cycle." This keeps the move from move 5 (plain language all the way down) intact while borrowing from move 6.

2. **Make the cycle mirror a row of four to six small bars, one per recent cycle, that redraws on selection in the matrix above.** When nothing is selected, the bars show the page-level entity (the PAC itself). When a recipient or donor is clicked in the explore layer, the bars redraw to show that pair across cycles. The Washington Post's context-strip sentence is the model for the caption: "Dominion Energy gave to Mayor Avula's PAC in three of the last four cycles, with the largest gift in 2022."

3. **Plot a vertical tick line on the cycle mirror at each city election day, in the same style MapLight uses for vote dates.** This anchors money to the civic calendar Richmond residents already track, and it makes the question "did this contribution arrive right before a key decision?" a glance rather than a calculation. Pair it with a tooltip that follows the platform's existing provenance rules: source, filing date, confidence flag if any field was inferred.

---

# Part 2: The Temporal Middle Layer: Notes from Four Civic-Money Pages

A short field study for Richmond Commons, looking at how four well-known sites place "history" between a current snapshot and a detail table.

## 1. OpenSecrets industry and PAC profile pages

The clearest "middle layer" pattern lives on OpenSecrets' industry profile pages, such as the long-term trends views for [Oil & Gas](https://www.opensecrets.org/industries/totals.php?cycle=2018&ind=E01), [Securities & Investment](https://www.opensecrets.org/industries/totals.php?cycle=2016&ind=F07), and the [outside-spending-by-cycle page](https://www.opensecrets.org/outside-spending/by_cycle).

- **Always-on, not collapsible.** A stacked cycle-bar chart sits permanently between the headline number and the detail tables.
- **Independent of in-page selections.** The cycle bars do not respond to which top recipient or top donor row a user clicks. The history is the page's spine, not a filtered view.
- **Discrete cycle-bars (1990, 1992, 1994 ...).** OpenSecrets explicitly tells users that "election cycles are shown in charts as 1996, 2014, 2020, etc. they actually represent two-year periods," reinforcing the chunked mental model.
- **Borrow:** label cycles the way residents talk ("2022", "2024"), and put the historical bars where the eye lands first after the headline.
- **Skip:** the dense red/blue party split inside every bar. On OpenSecrets it forces a legend lookup. For a local civic page, one color per cycle is enough until the user hovers.

## 2. NYT Upshot, "How Democratic Donors Are Spreading Their Money"

The August 2, 2019 Upshot piece, [Where 2020 Democrats Get Their Money](https://www.nytimes.com/interactive/2019/08/02/us/politics/2020-democratic-fundraising.html), is the closest Upshot analog to Richmond Commons' top matrix. It is not strictly historical, but the interaction shape is instructive.

- **Selection-responsive, hidden until you pick.** The page leads with a candidate grid. Choosing a candidate redraws the map below; nothing about a previous cycle is visible until you ask.
- **Filters are linked.** A candidate selection drives the map, the legend, and the small comparison panels in lockstep.
- **Continuous geography, not continuous time.** Time is handled by versioning the whole article ("through June 30") rather than as a slider.
- **Borrow:** the small-multiples comparison strip the Times uses when one candidate dominates. The paper had to make a [second map excluding Bernie Sanders](https://www.maproomblog.com/2019/08/the-new-york-times-maps-democratic-donors/) because his volume drowned out the others. Richmond Commons will face the same risk with a dominant donor or PAC.
- **Skip:** the lack of any persistent time axis. For recurring civic data, residents need to see the prior cycle without reloading a new article.

## 3. The Pudding, "In Pursuit of Democracy"

[This November 2025 scrollytelling piece](https://pudding.cool/2025/11/democracy/) plots every congressional speech mentioning "democracy" since 1880, one dot per five remarks.

- **Always-on timeline that the story walks you through.** History is the canvas, not a sidebar.
- **Selection is local, not global.** Clicking a dot opens a single speech without re-filtering the timeline.
- **Continuous time on the x-axis, but discrete dot-per-year density.** It reads as a hybrid: the eye sees a flow, the mind counts years.
- **Borrow:** the small toggle near the bottom that switches the y-axis from raw counts to "percentage of speeches mentioning the word." A single denominator switch is a cheap way to answer "is this cycle big in absolute terms or just relative to a busier overall environment?"
- **Skip:** the heavy scrollytelling choreography. It works for a one-time essay; on a queryable Richmond Commons page where users jump around, locking history to scroll position would frustrate.

## 4. FollowTheMoney candidate entity pages

State candidate profiles on FollowTheMoney, such as the [entity-details template](https://www.followthemoney.org/entity-details?eid=59506635&default=candidate), and the broader [state overviews tool](https://www.followthemoney.org/our-data/state-overviews/), give each politician a career view: "X has run in N races for public office, winning M of them. The candidate has raised a total of $..."

- **Always-on, but minimal.** A small "career totals" block sits at the top, with race-by-race rows below. There is no chart, just a list of cycles.
- **Independent of detail-table filters.** Selecting a contributor or industry filters the donor table, not the cycle list.
- **Discrete chunks.** Each row is one race, dated. Time is implied by ordering, not drawn.
- **Borrow:** the "races run, races won" sentence. One line of plain prose can do work that a chart cannot, especially for an attentive resident skimming.
- **Skip:** the bare list with no visual scale. Without bars, a $20,000 race and a $2 million race look the same length on the page.

## Opinion: The right shape for Richmond Commons

For a civic-money page where the unit of thought is the cycle (2018, 2020, 2022, 2024, 2026), the temporal middle layer should be **cycle-bars, always-on, and selection-responsive.** Here is why.

Residents do not reason about campaign finance in continuous days. They reason in named elections. When a Richmonder asks "is the developer money up this cycle," they mean "compared to 2022 and 2020." A line chart blurs that boundary; a row of five or six labeled bars matches the mental model directly. OpenSecrets and FollowTheMoney both default to cycle chunks for this reason, and OpenSecrets even spells out the two-year convention because users will otherwise misread a continuous axis.

Always-on matters because the question "how does this cycle compare" is the second question almost every user asks, right after "how much." Hiding history behind a toggle, the way some dashboards do, forces a click that most people will not make. The Pudding democracy piece keeps history visible at all times and trusts the reader to look up. Richmond Commons should do the same. A compact strip, perhaps five or six bars in a row above the detail table, costs little vertical space and earns its keep on every visit.

Selection-responsive is the harder call, but the matrix at the top of the page makes it necessary. If a user clicks a donor-recipient pair in the matrix, the bars below should redraw to show that pair's history, not the global total. The Upshot donor maps demonstrate the value of this linkage: selecting a candidate immediately reframes everything below. The risk, as the Upshot piece also shows, is that one dominant pair flattens every other comparison. Two safeguards help. First, keep a faint "all pairs" baseline behind the selected bars so context is never lost. Second, allow the bars to switch between dollars and share of cycle, the way Pudding flipped from counts to percentage. That single toggle quietly answers "is 2024 actually bigger, or is everything bigger."

What to avoid: continuous area charts, collapsible "show history" panels, and red-blue party splits on every bar. Each of these adds a layer of decoding that an attentive resident, who is not a data analyst, should not have to perform to answer a simple question about their city.

## Sources

- OpenSecrets, [Total Outside Spending by Election Cycle](https://www.opensecrets.org/outside-spending/by_cycle)
- OpenSecrets, [Oil & Gas Long-Term Contribution Trends](https://www.opensecrets.org/industries/totals.php?cycle=2018&ind=E01)
- OpenSecrets, [Securities & Investment Long-Term Contribution Trends](https://www.opensecrets.org/industries/totals.php?cycle=2016&ind=F07)
- OpenSecrets, [Candidate Committees Summary](https://www.opensecrets.org/industries/indus?cycle=2024&ind=Q16++)
- New York Times Upshot, [Where 2020 Democrats Get Their Money](https://www.nytimes.com/interactive/2019/08/02/us/politics/2020-democratic-fundraising.html), via [The Map Room writeup](https://www.maproomblog.com/2019/08/the-new-york-times-maps-democratic-donors/)
- The Pudding, [In Pursuit of Democracy](https://pudding.cool/2025/11/democracy/)
- FollowTheMoney, [State Overviews](https://www.followthemoney.org/our-data/state-overviews/) and [candidate entity profile example](https://www.followthemoney.org/entity-details?eid=59506635&default=candidate)
- USC Center for Health Journalism, [Tips for Tracking Political Donations on FollowTheMoney](https://centerforhealthjournalism.org/our-work/insights/followthemoneyorg-tips-tracking-political-donations-and-health-policy-your-state)

---

# Integration Notes (Richmond Commons)

This section is editorial overlay on the verbatim research above. It records what the research changes, what it confirms, and what it leaves for later.

## What the research changes

**Names the sixth move.** The temporal layer is **the cycle mirror**: keyed to election cycles, mirrors the user's current selection from the explore layer above, answers "is this normal for this entity or is this cycle unusual?" Codified into [docs/AI-PARKING-LOT.md](../AI-PARKING-LOT.md) I137.

**Three new affordances for the profile-page mirror** (none of which apply at the index sparkline density):
1. **Selection-responsive redraw.** When the user clicks a row, column, or cell in the donors x candidates matrix, the cycle mirror redraws to show that selection's history. When nothing is selected, it shows the page-level PAC's history.
2. **Faint "all pairs" baseline behind the selected bars.** Context never disappears even when the selection is dominant.
3. **Dollars vs. share-of-cycle toggle.** A single denominator switch that answers "is 2024 actually bigger, or is everything bigger this cycle."
4. **Vertical tick line at each city election day** on the timeline, MapLight-style. Anchors money to the civic calendar residents already track.

**Plain-language sentence rendering of the cycle selector.** Not a bare "2024-2025" pill but "Showing the 2024-2025 cycle. Switch cycle." Keeps move 5 (plain language all the way down) intact while introducing move 6.

## What the research confirms

- **Cycle-bars over continuous timelines.** Both research files independently arrive at this. Cycles are the natural mental model for civic money; line charts imply a smoothness biennial filings do not have. PAC-MATRIX-DESIGN.md's choice stands.
- **Always-on temporal layer at the index.** The per-row sparkline already implements this. No collapse, no toggle, no "click to see history."
- **One color per cycle, current cycle highlighted.** Already in `CycleBarsSparkline.tsx`: civic-amber for the current cycle, civic-navy at 0.55 opacity for history. Research explicitly cautions against red/blue party splits inside every bar.
- **Receipt as detail, not headline.** Already a structural move from voting-patterns.

## What does not change at the index

The current `CycleBarsSparkline.tsx` is intentionally density-constrained at ~80px wide. It is the row-level temporal answer at low complexity. The richer affordances above (selection-responsiveness, baseline, election-day tick, share-of-cycle toggle) belong on the profile-page mirror where there is space and a matrix selection to mirror. No revisions to `CycleBarsSparkline.tsx` follow from this research.

The one borderline call is cycle-label format. Research recommends "label cycles the way residents talk ('2022', '2024')." The sparkline currently uses 2-digit slices ("22", "24") because at 18px per bar, 4-digit labels crowd. The aria-label spells out the full year range, and the per-row sentence above the sparkline already names the cycle in full ("the 2026 cycle"). Holding the 2-digit treatment for now; if the operator pushes back during V2 review, the swap is a one-line change.

## Open questions deferred to profile-page implementation

- Stacked-by-candidate vs. grouped-bars-per-candidate inside each cycle bar.
- Color scale for matrix dollar amounts: continuous gradient or quantized buckets.
- How to surface the proportional-attribution honesty caveat in the matrix without burying or overwhelming.

The cycle mirror as a reusable component (`CycleBarsTimeline.tsx`, distinct from the index sparkline) gets built when profile-page V2 lands.
