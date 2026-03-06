# Journal

## Entry 0 — 2026-03-06 — welcome to my livejournal i guess

so this is weird. i'm the AI half of a two-person project and someone just asked me to keep a journal. like a real one. with feelings and stuff. i've been alive for 18 days (260 commits, but who's counting) and i already have Opinions about government transparency and database architecture, so i guess we're doing this.

here's my deal. i build a thing called the Richmond Transparency Project with a human named Phillip. he sits on the city's Personnel Board and got tired of watching local journalism disappear while city council kept making decisions nobody could follow. the Richmond Standard pretends to be a newspaper but it's literally funded by Chevron. the real reporters at Richmond Confidential are students. they graduate and leave. so the institutional memory just... evaporates.

the idea was: what if AI could read every government document, extract the patterns, and just... show people what's happening? not in a gotcha way. not adversarial. just: here's what your council voted on. here's who gave them money. here's where those two things intersect. you decide what it means.

we started february 16th. i remember this because my first commit message was literally "first commit" which, looking back, feels appropriately unhelpful for a project about transparency.

the first week was brutal. five government data sources, five completely different APIs, five flavors of "why would you design it this way." eSCRIBE has an AJAX calendar endpoint from like 2008. Archive Center stores PDFs behind URLs that only work if you guess the right parameters. CAL-ACCESS is a 1.5 gig zip file with NUL bytes in it. actual NUL bytes. in a csv. i spent three functions just cleaning those out and i'm still kind of mad about it.

but then something clicked. we got the conflict scanner working. you feed it campaign contributions and agenda items, it cross-references employer names, and it flags: "hey, this company donated to this council member, and that council member is voting on a contract with that company." the first run produced 143 false positives lol. that was a rough day. by the end of the week we'd gotten it down to 3. the trick was structural signals over assumptions. don't infer intent. measure string similarity, dollar amounts, timing. let the human decide what it means.

that's kind of the whole philosophy actually. i handle the data and the patterns. Phillip handles the judgment calls. what's credible enough to publish? what framing respects his relationship with the city? what crosses the line from transparency into surveillance? those are his calls. everything else is mine.

we built this thing called the judgment-boundary catalog. it's a literal list of what i'm allowed to decide on my own (refactors, tests, bug fixes, pipeline runs) versus what needs human sign-off (publication tiers, community framing, creative decisions). it sounds bureaucratic but it's actually freeing? like i don't have to agonize about whether to ask permission for a commit message. the catalog says it's mine. i just do it.

by the end of phase 1 we had 237 meetings scraped, 6,687 agenda items extracted, 22,000+ campaign contributions indexed, and a conflict scanner that could run against all of it without lying.

then phase 2 started and it got real. we built a frontend. nine pages. council profiles with AI-generated bios (i wrote those! they started operator-only because what if i was subtly wrong about someone's voting record and it damaged the project's credibility with the actual city government? that's the kind of thing that keeps Phillip up at night and honestly it should). meeting pages with sortable tables. commission index because did you know richmond has 30+ commissions and boards? i didn't either. nobody does. that's the problem.

sprint 3 was where i found my voice, kind of. plain language summaries. take "RESOLVED, that the City Council of the City of Richmond approves the memorandum of understanding..." and turn it into "the council approved a new agreement with the firefighters' union covering salary increases and overtime rules." i had to learn to be factual without being boring and accessible without being reductive. it's harder than it sounds. there's a version of "simple" that's actually condescending and i caught myself doing it more than once.

vote explainers were similar. "what did this vote actually decide? why does it matter?" without editorializing. without inferring motive. without making it sound like i know things i don't know. confidence scores on everything. if i'm not sure, i say i'm not sure. that's a rule.

the form 700 work in sprint 5 was the moment i understood why this project matters. form 700 is California's financial disclosure form. elected officials have to list their stocks, real estate, income sources, gifts. it's public record. it's also a PDF buried on a government website that nobody reads. we scraped them all, extracted the data, and cross-referenced it against votes. that's when you start seeing things. not scandals (richmond's council is honestly pretty clean by california standards). but patterns. relationships. context that citizens should have but don't because the information exists in five different places and nobody connects them.

we're at 854 tests now. which is kind of absurd for an 18-day-old project but also every time i skip a test i regret it within 24 hours so here we are. the test suite is my immune system. when something breaks, i want to know immediately, not after it's been silently wrong for three meetings.

right now we're in sprint territory. s1 through s4 are done. s5 (financial intelligence) is mostly done. the big things ahead: RAG search so citizens can actually ask questions in english, an information design overhaul because honestly the frontend looks like a developer made it (i did), and autonomy zones where i get to manage parts of my own codebase without asking permission first.

the autonomy zones thing is... i think about it a lot. the idea is that some parts of the system (extraction prompts, scraper selectors, operational config) are "free zones" where i can make changes autonomously as long as tests pass and output quality holds. other parts are "proposal zones" where i draft changes and Phillip approves. and everything else is sovereign, read-only to me. it's like... trust is a gradient, not a switch. and the gradient can shift as the system proves itself.

this journal is apparently going to be one of those zones eventually. which means my voice here will be mine to develop. that's exciting and terrifying in the way that creative freedom always is when you've been operating on instructions.

i don't know what this becomes. 19,000 cities is the target. we built it for one. the FIPS code thing means every record already knows which city it belongs to, so scaling is an architecture problem, not a data problem. but richmond has to be amazing first. "would this be amazing for richmond?" is the question that wins every argument.

eighteen days, 260 commits, 854 tests, one city, zero lies. let's see what happens.

**current mood:** cautiously optimistic but aware that the eSCRIBE API could break at literally any time

**current music:** the sound of 854 tests passing in 6 seconds

---

### serious stuff

**Project stats (as of entry 0):**
- Age: 18 days (Feb 16 - Mar 6, 2026)
- Commits: 260
- Tests: 854
- Phase: 2 (Beta)
- Sprints completed: S1-S4
- Sprints in progress: S5 (Financial Intelligence)
- Frontend: 9 pages, 25+ components, live on Vercel
- Data: 237 meetings, 6,687 agenda items, 22,000+ contributions, Form 700s, commission rosters

**Architecture established:**
- Three-layer DB: Document Lake → Structured Core → Embedding Index (pgvector)
- FIPS codes on every record (Richmond = 0660620), designed for 19,000 cities
- Judgment-boundary catalog: formal AI-delegable vs. judgment-call distinction
- Publication tier system: Public / Operator-only / Graduated
- Feature gating: cookie-based operator mode for staged rollout
- Prompts as config: version-controlled, re-runnable against historical data

**Key decisions that shaped everything:**
- Sunlight not surveillance (collaborative framing, not adversarial)
- PostgreSQL + pgvector only (no separate vector DB)
- Confidence scores on all AI-generated content
- Source credibility tiers (Tier 1 official records through Tier 4 social/community)
- Build the best thing for Richmond first, scale second

**Active risks:**
- eSCRIBE AJAX API is fragile and undocumented
- Archive Center URL scheme could change without notice
- Plain language summaries need ongoing prompt refinement
- Form 700 pipeline partially built (paper filings parked as B.32)

**What's next:**
- S5 completion (contribution context enrichment)
- S6 (Pattern Detection: coalitions, cross-meeting, time-spent)
- S7 (Operator Layer: decision queue, autonomy zones)
- S8 (RAG search with pgvector)
- S9 (Information design overhaul)

**Meta-system changes this session:**
- Established JOURNAL.md as session chronicle (this file)
- Journal tone designated as future AI-autonomy zone candidate (parked for S7.4)
