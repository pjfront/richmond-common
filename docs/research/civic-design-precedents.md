# Civic design precedents for the Influence Map

**No active tool connects campaign money to legislative votes — and research confirms plain-language narrative is the right approach to fill this gap.** Richmond Common's "Influence Map" would occupy genuinely uncharted territory in civic tech. The last tool to systematically link donor money with specific roll-call votes was MapLight, which froze its public research platform around 2017. Every other major transparency tool keeps financial data and voting records in separate silos. Meanwhile, UX research consistently shows that narrative presentation improves comprehension for non-expert audiences by roughly 47% compared to raw data displays — precisely the audience a city-council transparency platform must reach. This document catalogs the UX patterns, strengths, and design gaps of eight major civic transparency tools, plus local-level platforms, to inform the Influence Map's design.

---

## ProPublica Represent: shut down, but its design process endures

**Status: Defunct as of mid-2024.** The tool now displays a retirement notice at projects.propublica.org/represent/, and its Congress API has been permanently shut down.

ProPublica Represent operated from 2016 to 2024, tracking U.S. Congressional activity with a design forged through a **Stanford d.school UX partnership** that interviewed congressional reporters, students, activists, lobbyists, and nonvoters. Its 2018 redesign introduced several patterns worth emulating:

**Vote-legislation display.** Vote results used cartogram visualizations showing the relative geographic clout of delegations — not just yes/no tables. Bill pages used card-based sections with a curated action timeline that **defaulted to showing only major events**, hiding minor procedural actions behind a click. This progressive disclosure pattern reduced overwhelm without sacrificing completeness.

**Navigation model.** Hybrid person-centered and activity-centered. Member pages featured an activity feed — a chronological stream of votes, bill introductions, statements, and news articles borrowed from ProPublica's Election DataBot. State delegation pages aggregated all members with combined feeds, serving local journalists covering entire delegations.

**Narrative approach.** Represent explicitly used **conversational, plain-English bill statuses** designed to be "easier to scan." Member pages were framed around two questions: "What is my representative doing?" and "What does she really care about?" Machine learning identified the distinctive issues each lawmaker talked about, presented in natural-language summaries.

**Financial connections: absent.** Despite maintaining a separate Campaign Finance API and stating aspirations to show "the incentives that drive" officials, ProPublica **never integrated donor data into Represent's UI**. Votes and money remained in separate products throughout the tool's lifespan.

**Key lessons.** The user-centered design process is exemplary. The activity feed concept — converting static profiles into living timelines — is directly transferable to city council contexts. The tool's ultimate shutdown, however, is the biggest cautionary tale: sustainability for civic tools built by nonprofit newsrooms is fragile. Cross-linking to other tools (GovTrack, C-SPAN) rather than siloing data was a wise architectural choice.

---

## GovTrack: 21 years of analytical depth, zero financial data

**Status: Active and updated daily**, tracking the 119th Congress (2025–2027). Run independently by Civic Impulse, LLC since 2004 with no outside funding — the longest-surviving civic transparency tool of its kind.

**Vote-legislation display.** GovTrack's vote pages are the richest in civic tech. They layer multiple visualization types on a single page: hexagonal cartograms color-coded by party and vote direction, an **ideology seating chart** arranging members on a spectrum, algorithmically identified "statistically notable votes" (the least predictable given party alignment), and caucus analysis showing which memberships correlate with the vote outcome. For Senate votes, GovTrack uniquely shows the **percentage of the U.S. population represented by the yeas** — contextualizing democratic representation beyond raw counts.

Bill pages feature a **calculated prognosis** ("55% chance of being enacted") with linked methodology, a text-comparison tool showing percentage overlap between related bills, and built-in **study guides** with adaptive educational questions. Every page provides MLA, Wikipedia, and BibTeX citation formats.

**Navigation model.** Multi-entry with roughly equal weight on Members, Bills, and Votes. An address lookup enables person-centered entry. A powerful alert/tracking system lets users create custom watchlists with email and RSS notifications — a distinguishing engagement pattern.

**Financial connections: deliberately excluded.** GovTrack tracks no campaign contributions, donor relationships, or lobbying data. Its independence statement emphasizes "no financers, sponsors, investors, or partners." External library guides (e.g., UC Berkeley) point users to OpenSecrets and FollowTheMoney for financial data — treating legislation and money as separate research domains.

**Narrative approach.** Hybrid. Bill statuses use conversational English ("This bill passed in the House on March 5, 2026 and goes to the Senate next"). Extensive inline explanations of procedure appear throughout (what "cloture" means, why the Speaker rarely votes). Blog posts by named authors provide weekly narrative recaps. But **core data display remains tables, charts, and structured metadata** — not story-first.

**Key lessons.** GovTrack's analytical layers transform raw data into insight. The prognosis calculation, population-representation metric, and statistically notable vote detection are design patterns that elevate a transparency tool from data browser to accountability platform. The longevity model — small, independent, self-funded — is instructive for sustainability. Its main weakness: a **utilitarian Bootstrap-era visual design** that can overwhelm casual users with information density.

---

## Open States: absorbed into Plural Policy, free tier is skeletal

**Status: Effectively sunsetted as an independent product.** Open States was absorbed into Plural Policy (pluralpolicy.com) in 2023. The free tier retains a "Find Your Legislators" tool, limited bill search, API access, and bulk data downloads. The open-source scrapers on GitHub remain active and run daily for all 50 states, DC, and Puerto Rico.

**Vote-legislation display.** Vote pages on the free tier show plain HTML tables: vote totals, party breakdown, and a roll-call table listing each legislator's name, party, and vote. **No charts, no visualizations, no color coding** beyond text labels. Very data-forward, sparse design.

**Navigation model.** Dual-entry: bill search and address-based legislator lookup. No issue or topic-based browsing on the free tier.

**Financial connections: none.** The free tier is strictly legislative data. The commercial Plural platform may offer financial intelligence features behind a paywall, but the open data layer contains zero campaign finance information.

**Narrative approach: none.** Pure structured data presentation. Motion text is displayed as-is from official records. No plain-English summaries, no interpretive layer.

**Key lessons.** Open States' strongest pattern is **source attribution**: every page states "Data updated periodically throughout the day from the official website of the [State Legislature]" with a direct URL to the original source document and a link to file a GitHub issue for inconsistencies. The standardized data model (based on Open Civic Data) covering all 50 states is architecturally important — but the brand fragmentation from the Plural transition creates user confusion. The interface assumes legislative literacy and is hostile to casual civic engagement.

---

## CalMatters Digital Democracy: the gold standard for financial integration

**Status: Very active and expanding.** Launched April 2024 by CalMatters in collaboration with Cal Poly SLU and 10up. Won the **Punch Sulzberger Prize for Journalism Innovation** and an Emmy Award. Expanded to Hawai'i in 2025 with plans for additional states. Launched "My Legislator" personalized weekly email newsletters in January 2026.

**Vote-legislation display.** Multi-layered and contextual. Legislator pages show bill activity summaries with visual progress bars ("Of 54 bills: 21 Passed, 9 Failed, 24 Pending"). Critically, **vote data appears within AI-generated hearing transcripts** with synchronized video — users can see the exact moment a vote was called and read the debate alongside it. An **Alignment Meter** shows what percentage of the time a legislator's votes align with various organizations (ACLU, Sierra Club, Chamber of Commerce), creating a vote-to-interest-group connection.

**Financial connections: extensive and deeply integrated.** This is Digital Democracy's standout feature and the closest active precedent to what the Influence Map envisions:

- **Legislator financial profiles** include election money broken down by industry sector (using OpenSecrets categories), with dollar amounts and bar charts
- **Comparative framing**: "396.0% higher than the average legislators"
- **Independent expenditures** with comparison to peers
- **Personal gifts table** showing giver, value, date, and description for each gift, with rankings ("This legislator is ranked 5th highest for the amount of personal gifts received")
- **Gift rules explained inline**: "Legislators are not allowed to accept gifts of more than $10 per month from registered lobbyists"
- **Organization pages** aggregate lobbying testimony, bill alignments, and all financial exchanges between an organization and legislators in one place
- **"Top 10/Bottom 10" homepage rankings** for Election Money, Labor Money, Oil Money, Personal Gifts, and Sponsored Travel

**Navigation model.** Triple-entry: person-centered (legislator profiles), issue-centered (six curated topic areas: Education, Health, Environment, Justice, Housing, Poverty), and search-centered. Tabbed legislator pages (Overview / Financials / Policy / Hearings / District) provide progressive disclosure.

**Narrative approach.** Mixed. Legislator bios are written in journalistic prose. Financial sections include explanatory plain-English paragraphs inline. Comparative sentences appear throughout ("396.0% higher than the average legislators"). But bill titles remain in legislative jargon, and there are **no auto-generated plain-English bill summaries** — a notable gap.

**Sourcing and caveats.** Inline and explicit: "The industry categories for donors come from Open Secrets, a nonpartisan research organization. Some contributions are 'uncoded,' meaning they have not been assigned to an industry sector." A dedicated methodology page documents all sources, entity resolution challenges, and data coverage windows. Caveats are well-placed near relevant data: "NOTE: Senators are elected every four years. Twenty of the 40 Senators are on the ballot in even-numbered years, so Senators may do little or no fundraising in the first two-year session."

**Key lessons.** Digital Democracy is the single most important precedent for the Influence Map. Its financial integration demonstrates that **showing money alongside legislative activity on the same profile page is achievable and powerful**. Its cross-entity search — where searching for "Chevron" reveals donations, lobbying testimony, gifts, travel, and bill positions holistically — is exactly the kind of connection the Influence Map should make. Its main weakness for Richmond Common's purposes: vote data is embedded in transcripts rather than displayed as structured roll-call views, and it provides no open API for developers.

---

## Follow The Money: legacy state finance data with Power Mapping innovation

**Status: Semi-active legacy site.** The National Institute on Money in Politics merged with the Center for Responsive Politics in 2021 to form OpenSecrets. The followthemoney.org website still serves state campaign finance data through the 2024 election cycle with a prominent banner: "While the data is current, the site isn't maintained and you may find bugs."

**Vote-money display.** Follow The Money does not directly show vote-money connections on individual bills. Its most notable feature was **Power Mapping** — a tool that lets users specify which industries support or oppose a hypothetical bill, then generates a predictive visualization of lawmakers' likely positions based on their campaign contribution profiles. This is analytical and predictive rather than retrospective, but it demonstrates a valid design concept: mapping financial relationships to predicted legislative behavior.

**Financial data display.** Primarily tables with a powerful "Show Me" query builder for multi-parameter searches. Highcharts for visualization. Data organized by 19 economic sectors with sub-categories. Drill-down navigation from state election overviews to individual contributors.

**Key lessons.** The **50-state coverage** from 1990 onward remains unique in depth. The Power Mapping concept — using donor data to predict vote alignment — is transferable to the Influence Map as a complementary analytical feature. But the interface is researcher-oriented, with tutorial videos running 10–52 minutes, signaling a steep learning curve incompatible with civic engagement goals.

---

## OpenSecrets: the federal finance standard, but no vote connection

**Status: Active as of March 2026**, with ~7.5 million annual visitors, but experienced serious financial difficulties in 2024, laying off a third of its staff. Data releases are current (FEC data from February 2025, lobbying data from January 2026, outside spending from March 2026).

**Vote-money display: absent.** OpenSecrets does not connect campaign contributions to specific legislative votes. Member profiles show top donor industries, PAC splits, and sector breakdowns — but this data exists independently from any voting record. The site mentions "connections between committee members, industries, and interests that they regulate" but doesn't develop this into a clear feature linking votes to money.

**Navigation model.** Multi-centered: politician profiles ("Candidates & Officeholders"), organization profiles ("Lobbying & Groups"), and race-centered views ("Elections"). Critically, **there is no bill-centered navigation path**. You cannot search for a bill and see who funded the legislators who voted on it.

**Financial data display.** Sortable tables dominate, supplemented by bar charts, interactive geographic maps, and time-series visualizations. Organization profiles compile contributions, lobbying, and outside spending on a single page — a useful multi-dimensional view. Some features require paid membership ($40/year).

**Narrative approach.** OpenSecrets has an active news section with journalists writing articles that narratively contextualize the data. The data tools themselves use descriptive headings ("See which industries and organizations are supporting your elected representatives") but **do not generate dynamic sentences** like "Senator X received $Y from Industry Z."

**Key lessons.** OpenSecrets' organization profiles — showing all dimensions of an entity's political activity in one place — are a strong model for the Influence Map's entity pages. Its sourcing is excellent: every data page shows the release date of its underlying government filings. The 2024 layoffs, however, underscore the sustainability challenge for nonprofit transparency organizations.

---

## MapLight: the pioneer of vote-money correlation, now effectively dormant

**Status: Pivoted entirely from its original research mission.** MapLight still exists as a 501(c)(3) but now sells government software (campaign finance e-filing, lobbying systems, ethics disclosure). The current maplight.org is a corporate-style site marketing "Technology for Democracy." The original vote-money research platform survives at classic.maplight.org but is frozen circa 2017 (115th Congress data).

**MapLight is the single most important precedent for the Influence Map.** It was the only tool to systematically connect campaign contributions with legislative votes at scale. Here is exactly how it worked:

**"Contributions by Vote" — the key innovation.** For each roll-call vote on a bill, MapLight displayed a table correlating how legislators voted (YES/NO) with how much money they received from interest groups on each side. The page read: *"See whether there is a correlation between interest groups that supported this vote and members that voted yes."* It showed average contributions: interest groups supporting the bill gave YES voters an average of $X vs. NO voters an average of $Y. Individual legislator-level data was accessible, showing each person's vote alongside contribution totals from supporting and opposing interests.

**"Timeline of Contributions."** A temporal visualization showing when contributions were received relative to a vote date — the "Money Near Votes" feature that graphically identified large donations arriving just before or after votes.

**Interest group position research — the critical linking layer.** MapLight employed paid researchers who manually documented which organizations supported or opposed each bill using hearing testimony, news databases, and public statements. This manual research created the bridge between finance data and vote data by establishing which interest groups had a stake in each bill. Organizations were tagged with CRP-compatible industry category codes for aggregation.

**Narrative sentence display — yes, MapLight used this approach.** Their news stories and reports consistently expressed findings as plain-language sentences:

- "The House voted to eliminate a permit requirement for pesticides last week, as sponsors received **12 times more** in campaign contributions from the agricultural chemical industry than the bill's opponents"
- "Senators voting against the Manchin-Toomey Amendment received, on average, **11 times more money ($25,631)** from pro-gun interest groups than senators voting for it ($2,340)"
- "Interest groups that supported this amendment gave **50% more** to Senators that voted YES than to Senators that voted NO"

**Causation disclaimer — essential design precedent.** MapLight included an explicit disclaimer on every data page: *"Campaign contributions are only one factor affecting legislator behavior. The correlations we highlight between industry and union giving and legislative outcomes do not show that one caused the other, and we do not make this claim."* This is the model the Influence Map should adopt.

**Why MapLight's research tool died.** The manual interest-group-position research required paid staff and was expensive to maintain. The model couldn't scale beyond Congress, California, and Wisconsin. MapLight pivoted to selling campaign finance disclosure software to governments — a more sustainable revenue model. The Institute for Free Speech also criticized the "Money Near Votes" feature as potentially misleading, arguing it lacked context about legislators' broader voting patterns and party alignment.

**Key lessons.** MapLight proves the Influence Map concept is viable and that narrative sentences connecting money to votes are effective for public communication. Its failure points are equally instructive: **the manual linking of interest groups to bills was the bottleneck**, party alignment was an insufficient confound to address, and the consumer-facing model wasn't financially sustainable. At the city council level, however, the linking problem may be more tractable — fewer bills, more direct stakeholder testimony at public meetings, and clearer interest-group connections.

---

## Councilmatic: the only open-source city council tracker still running

**Status: Active, maintained by DataMade.** Two instances confirmed operational: **Chicago Councilmatic** (chicago.councilmatic.org) with data current through March 2026, and **LA Metro Board Agendas** (boardagendas.metro.net). The NYC instance appears defunct. The codebase (django-councilmatic) was last updated August 2025.

**Vote-legislation display.** Limited by data reality. Chicago City Council primarily uses voice votes, so individual roll-call data is rarely available. The site focuses on legislation status tracking (Introduced, Referred, Substituted, Signed) with action timelines and committee assignments. Each piece of legislation is classified as **"Routine" or "Non-Routine"** — a brilliant editorial filter that makes Chicago's 500+ monthly legislative items manageable.

**Financial connections: none.** Zero campaign finance integration.

**Navigation model.** Bill-centered with person and committee secondary paths. Homepage leads with latest council meeting activity. Ward-based geographic lookup ("Find Your Ward and Alder") enables person-centered entry. A "Compare Alders" tool enables cross-member comparison.

**Narrative approach: strong.** Homepage text reads: "At the latest City Council meeting on Mar 18th, council members took action on 524 pieces of legislation, including 169 that are non-routine." Uses accessible language throughout and gender-neutral terminology ("alder" instead of "alderman"). In 2024, DataMade introduced **AI-generated bill summaries using LLMs** for non-routine legislation — translating legally dense ordinance text into plain English. This is a notable innovation directly relevant to the Influence Map.

**Key lessons.** Councilmatic demonstrates that open-source, city-specific civic tools are viable. The Routine/Non-Routine classification pattern is directly transferable — city councils produce enormous volumes of consent-calendar items, and surfacing what matters is critical. The AI bill summarization feature shows the path forward for plain-language accessibility. Its scaling failure (only 2 active instances in 10+ years) reveals the challenge Richmond Common faces at 19,000 cities: per-city deployment and maintenance is not scalable without a fundamentally different architecture.

---

## Ballotpedia: encyclopedic breadth, governance-light

**Status: Very active.** Over **671,000 articles** with professional editorial staff. Covers federal, state, and local government.

**Vote-legislation display.** Varies dramatically by level. State legislator pages include sponsored bills (via BillTrack50) and third-party legislative scorecards. City council member pages have **no legislation or voting data** — they focus exclusively on elections (history, endorsements, campaign themes).

**Financial connections.** Partial. Federal and state race pages show FEC/state campaign finance overview figures. Local race coverage includes campaign finance **only for designated "battleground" races**. Financial data and legislative activity exist in completely separate sections with no cross-linking.

**Navigation model.** Person-centered and election-centered, organized as a wiki. The dominant paradigm is "Who is running? → Who won? → What are their positions?" rather than "What legislation is being considered? → Who voted how?" This creates an **election-heavy, governance-light** coverage model.

**Narrative approach: extensive.** Every article uses encyclopedia-style plain English: "Erik Bottcher (Democratic Party) is a member of the New York City Council, representing District 3. He assumed office on January 1, 2022." Context paragraphs explain local government structures. Candidate survey responses are reproduced verbatim with explicit disclaimers.

**Local coverage.** Ballotpedia covers the top 100 U.S. cities by population plus all 50 state capitals, expanding state by state (31 states as of 2026). Coverage includes mayoral and council elections, some campaign finance, and government structure descriptions. It does **not** track legislation, voting records, committee activity, or meeting schedules at the local level.

**Key lessons.** Ballotpedia's encyclopedic neutrality, rigorous sourcing (footnoted references throughout), and "Sample Ballot Lookup" tool are strong patterns. Its cross-level integration — the same person has entries as city council member, state legislator, and congressional candidate — is architecturally useful. But its fundamental gap for Richmond Common's purposes is the absence of governance data at the local level: it tracks who gets elected but not what they do once in office.

---

## Local-level tools: a fragmented landscape with a massive gap

The local civic tech ecosystem is dominated by government-facing tools (Legistar, CivicPlus, OpenGov) built for clerks and administrators, not citizens. The citizen-facing layer is thin, fragmented, and has no tool combining voting records with campaign finance at the city council level.

**Legistar (Granicus)** is the dominant legislative management system, used by **7,000+ government organizations**. It captures full legislative workflow including roll-call votes, but its public-facing portal is bureaucratic and clerk-oriented. Several cities expose Legistar APIs (NYC, Chicago), which downstream tools like Councilmatic scrape. Legistar contains no campaign finance data.

**FiscalNote/Curate** is the closest thing to multi-city legislative monitoring at scale, scanning **12,000+ local government entities** for meeting minutes, agendas, and policy trends. But it targets enterprise lobbyists and government affairs teams — not citizens — at enterprise pricing with no campaign finance integration.

**Hamlet** indexes **3,500+ governing bodies** and 33,000+ meeting transcripts, with video-linked search results that jump to relevant moments. It targets real estate developers and investors. **CivicSearch** covers 547 cities with transcript search organized into 75 policy topics, targeting researchers and journalists. Neither connects money to votes.

**Intro.nyc** is a lightweight, open-source NYC Council legislation search tool demonstrating that a useful citizen-facing tool can be built with minimal complexity on top of Legistar APIs.

**Local campaign finance systems are extremely fragmented.** The Sunlight Foundation's Municipal Campaign Finance Data Roadmap documented wide variance in how cities release campaign finance data — different rules, formats, systems, and disclosure requirements in each of the 19,000+ U.S. cities. Houston approved $1M+ for a new campaign finance system in February 2026 to replace a 2007-era platform. NYC's Campaign Finance Board has a robust "Follow the Money" disclosure tool, but it is **completely separate from legislative voting records**. MapLight partnered with Denver to build "SearchLight Denver" for campaign finance disclosure, but this too lacks vote integration.

**The civic tech community has fragmented since Code for America's brigade sunset in January 2023.** The Alliance of Civic Technologists (ACT), launched in 2024, is rebuilding with 7 inaugural member organizations (Chi Hack Night, Open Austin, BetaNYC, and others), but it is a network/support organization, not a product builder.

**No existing platform combines city council voting records, campaign finance data, and multi-city scaling for citizens.** This is the core gap Richmond Common targets. The closest precedents are MapLight (money + votes, but only federal/state, now legacy), Councilmatic (citizen-friendly legislation UI, but ~2 cities and no finance), and FiscalNote/Curate (multi-city scale, but enterprise-only and no vote-finance correlation).

---

## Sentence-based narrative display: precedents and research

### Existing precedents

The sentence-based narrative approach for civic financial data is **extremely rare** but not without precedent.

**ProPublica's "Opportunity Gap" (2013)** is the strongest technical precedent. Using Narrative Science's AI platform, ProPublica auto-generated plain-English paragraphs for 52,000+ schools from structured educational equity data. The editorial insight is directly applicable: *"Mentioning a data point in a narrative made it seem much more important than simply including it on the page of an interactive database."* The system generated varied sentence structures to avoid sounding robotic. The team worked with AI engineers "much as an editor and reporter do," iterating on narrative quality.

**MapLight's news reports (2005–2017)** consistently used narrative sentences connecting money to votes: "Senators voting against the Manchin-Toomey Amendment received, on average, 11 times more money from pro-gun interest groups than senators voting for it." These sentences were hand-written by researchers, not auto-generated, but they establish the template for what the Influence Map's automated sentences should look like.

**Campaign finance Twitter bots** — notably @young_bots by Lindsay Young — consumed the FEC's real-time e-filing API and tweeted filings as text sentences, demonstrating automated conversion of structured finance data to narrative text.

**MOXY 5.0 (2025)** uses AI to generate narrative politician profiles from legislative data, distilling legislation into "objective evaluations along key issues." **Politibot** (Spain) delivers political facts conversationally via Telegram/Messenger.

**No major tool has applied auto-generated narrative sentences specifically to campaign-finance-to-vote correlations.** Richmond Common's approach is genuinely novel in this space.

### Research supporting the narrative approach

The evidence base for narrative presentation of civic data is strong and consistent:

**Comprehension improvements.** A 2019 study by Obie et al. found **significant improvement in user comprehension** with author-driven narratives vs. interactive visualizations without narratives. A 2024 CHI conference study (N=103) confirmed that data stories improve both the **efficiency and effectiveness** of comprehension tasks, and are "especially advantageous for audiences with limited visualisation literacy." A 2025 study of budget data visualization found visualization-enhanced information improved comprehension by **47%** and willingness to engage civically by **32%** compared to traditional presentation.

**The civic literacy gap demands this approach.** A 2023 US Chamber of Commerce Foundation survey (N=2,000) found **70%+ of Americans fail a basic civic literacy quiz**. Only 25% are "very confident" they could explain how government works. MIT researchers (Martinez, Mollica, Gibson, 2024) confirmed that despite 50+ years of the plain-language movement, U.S. laws remain laden with psycholinguistic complexity. The target audience for Richmond Common likely has limited baseline civic and financial literacy — narrative sentences are not a luxury but a necessity.

**Bias concerns are real and must be designed for.** The Obie et al. study found that users express concern about **bias of narratives** in data presentation. There is a documented "fine line between aiding understanding and introducing bias." MapLight's explicit causation disclaimer is the essential design response to this concern.

**Layered narrative + data is optimal.** A 2025 study ("TableTale") found that combining narrative text with access to underlying data tables at multiple granularities **reduced perceived workload, achieved higher usability ratings, shortened reading time, and eliminated unanswered comprehension tasks**. This directly supports the Influence Map's architecture: sentence as primary display, with progressive disclosure to underlying data.

---

## Cross-cutting patterns: density, sourcing, and confidence

### Information density

The best civic tools use **progressive disclosure** — initially showing only the most important information, with deeper detail available on demand. GovTrack's tabbed bill pages (Overview / Summary / Details / Text), CalMatters' tabbed legislator profiles (Overview / Financials / Policy / Hearings / District), and Councilmatic's Routine/Non-Routine classification all implement variants of this pattern. Nielsen Norman Group guidelines recommend limiting to **2–3 disclosure layers** to avoid user disorientation.

The key principle from Algolia's UX research: "Information density isn't about cramming more details — it's about **intelligently displaying what matters most** in a way users can process." For the Influence Map, this means the narrative sentence is Layer 1, a source/confidence bar is Layer 2, and individual contribution records and methodology are Layer 3.

### Sourcing and attribution

Three models emerge from the tools analyzed:

- **Open States' per-page model**: Every page states "Data updated periodically from the official website of [legislature]" with a direct URL to the source document and a link to report issues. Simple and effective.
- **CalMatters' inline-explanation model**: Attribution is woven into the data display itself ("The industry categories for donors come from Open Secrets, a nonpartisan research organization").
- **GovTrack's freshness-disclosure model**: "Congress.gov is generally updated one day after events occur, and so legislative activity shown here may be one day behind."

The Influence Map should combine all three: per-sentence source links, inline explanations of where financial data originates, and freshness timestamps on every data point.

### Confidence and caveat language

MapLight's causation disclaimer is the gold standard: *"The correlations we highlight do not show that one caused the other, and we do not make this claim."* CalMatters' contextual caveats are also well-designed: flagging uncoded contributions, explaining electoral cycle timing effects, and acknowledging entity-resolution challenges ("it's difficult to know if the 'Bob Smith' who testified in 2023 is the same 'Bob Smith' who testified in 2024").

For the Influence Map, recommended caveat patterns include:

- **"Data as of" timestamps** showing when contribution data was last pulled from filing sources
- **Completeness indicators**: "3 contributions found in available records; additional contributions may exist in unfiled or delayed reports"
- **Relationship qualification**: "received contributions from" rather than "was paid by"
- **Aggregation transparency**: Show that "$4,200 across 3 contributions" is a sum, with links to individual records
- **Temporal context**: Clarify whether the stated date range represents all available data or a deliberate analytical window

---

## Synthesis: what no tool does and why it matters

Across all eight tools and dozens of local platforms, a clear pattern emerges. The civic transparency ecosystem is organized into **three disconnected silos**:

1. **Legislative tracking** (GovTrack, Open States, Councilmatic, Legistar) — tracks bills, votes, and legislative process
2. **Campaign finance** (OpenSecrets, Follow The Money, local ethics boards) — tracks donations, expenditures, and lobbying
3. **Election information** (Ballotpedia, local media) — tracks candidates, races, and outcomes

These three domains share the same actors (legislators, donors, organizations) but are architecturally isolated from each other. **Only MapLight ever systematically bridged silos 1 and 2** — and its public research tool has been frozen since 2017. CalMatters Digital Democracy comes closest among active tools by placing financial data on the same profile page as legislative activity, but it does not connect specific donations to specific votes.

At the **city council level specifically**, the gap is even wider. No existing tool connects local campaign finance to local voting records. Legistar holds the voting data. City ethics boards hold the finance data. They never meet.

The Influence Map's approach — expressing each financial connection as a plain-language sentence — addresses both the integration gap and the comprehension gap simultaneously. It bridges the data silos while making the results accessible to the 70%+ of Americans who cannot pass a basic civic literacy quiz.

---

## Design recommendations for the Influence Map

**Adopt MapLight's bill-centered entry point.** Start from the agenda item or vote, then reveal financial connections — not the reverse. Users care about issues first, money second. MapLight's bill-centered navigation was its most distinctive and effective design choice.

**Use a four-layer progressive disclosure architecture.** Layer 1: the narrative sentence ("Council Member Martinez voted yes. His campaign received $4,200 from Acme Development PAC across 3 contributions between 2022–2024."). Layer 2: inline source citation and confidence bar ("Source: Richmond campaign finance filings, updated March 15, 2026 · Correlation shown, not causation"). Layer 3: expandable detail (individual contribution dates/amounts, the PAC's other recipients, Martinez's full donor profile). Layer 4: raw data access (links to original filing documents, downloadable datasets).

**Include a MapLight-style causation disclaimer on every page**, not buried in a methodology section. The exact phrasing should be tested, but something close to: "Campaign contributions are one of many factors in how council members vote. Financial connections shown here are correlations, not evidence of influence."

**Adopt CalMatters' comparative framing.** Sentences like "396% higher than the average legislator" make raw dollar amounts meaningful. For the Influence Map: "Council Member Martinez received 3.2× more from real estate interests than the average council member" gives users a frame of reference.

**Implement Councilmatic's Routine/Non-Routine filter** for city council contexts. Most council votes are consent-calendar items. Surfacing which agenda items have unusual financial connections — and which are routine — will be essential to avoid overwhelming users.

**Borrow GovTrack's "statistically notable" detection.** Algorithmically flagging votes where a member broke from their usual pattern, or where financial connections are unusually concentrated, would give the Influence Map an analytical edge beyond raw data display.

**Plan for the interest-group-position problem.** MapLight's research tool died because manually documenting who supports or opposes each bill required paid staff. At the city council level, this problem is more tractable: public comment records, development application stakeholders, and hearing testimony can be parsed — especially with modern NLP. But this is the critical linking layer that makes the whole system work, and it must be resourced from day one.

**Design for the data fragmentation reality.** Scaling to 19,000 cities means confronting 19,000 different campaign finance disclosure systems. The Open Civic Data standard and Legistar API provide some legislative data standardization, but campaign finance remains deeply fragmented. The platform will likely need a city-by-city onboarding process — or a strategy to focus on cities where both legislative and financial data are programmatically accessible.

**Build on open standards and open source.** Councilmatic's limited scaling (2 cities in 10+ years) and MapLight's pivot to proprietary software both suggest that open-source, community-maintained infrastructure is necessary but insufficient. A sustainable model likely requires either a SaaS approach (as DataMade's Councilmatic now offers) or foundation/institutional funding — not volunteer maintenance.

---

## Conclusion

The Influence Map occupies a genuine gap in the civic tech landscape. The last tool to connect campaign money with legislative votes was MapLight, and it stopped updating its public research platform nearly a decade ago. The narrative sentence approach is supported by robust UX research showing comprehension gains of 30–47% for non-expert audiences, and MapLight's own reporting demonstrated that sentences like "Senators voting against [bill] received 11× more from [industry]" are effective vehicles for civic accountability data.

The hardest design problem is not the sentence generation — it is the **linking layer** that connects donors to the issues they have a stake in. MapLight's reliance on manual research for this linking was its undoing. At the city council level, the smaller scale of legislation and the directness of public testimony may make this problem more tractable, but it remains the critical technical and editorial challenge.

Three active tools offer the strongest design patterns to draw from: **CalMatters Digital Democracy** for financial-legislative integration and progressive disclosure, **GovTrack** for analytical depth and sustainability, and **Councilmatic** for city-council-specific UX and AI-powered plain-language summaries. The Influence Map's unique contribution would be combining these approaches — financial integration, analytical insight, narrative accessibility — at the local government level where no tool currently operates.