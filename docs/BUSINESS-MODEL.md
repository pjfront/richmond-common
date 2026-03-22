# Business Model — Richmond Common

*Last updated: 2026-02-15*

---

## 1. Three Monetization Paths (Not Mutually Exclusive)

### Path A: Freemium Consumer Platform

The citizen-facing tool is free or cheap ($5/month). Premium revenue comes from professional users.

**Who pays:**
- Journalists: "Alert me when any council member in my coverage area votes inconsistently with their stated platform"
- Law firms: litigation research, conflict of interest analysis
- Political campaigns: opposition research, voting record analysis
- Real estate developers: "Tell me every time a zoning vote happens within 2 miles of my properties"
- Advocacy organizations: issue tracking across multiple cities
- Researchers: API access to structured municipal governance data

**Pricing tiers (conceptual):**
- Free: public profile pages, basic search, vote digests
- Citizen ($5/month): alerts, full search, conflict reports — less than a local news subscription
- Professional ($50-200/month): API access, custom alerts, cross-city analysis, bulk data export
- Enterprise/API: custom pricing for journalism outlets, research institutions, political organizations

### Path B: Horizontal City Scaling

Once the pipeline works for Richmond, expanding to the next city is a data integration problem, not a product rebuild.

**The math:**
- ~19,000 incorporated cities in the US
- $5/month × 1,000 engaged citizens × 500 cities = **$30M ARR**
- Those numbers aren't crazy for a product that works and gets press coverage
- Even 100 cities × 500 citizens × $5/month = $3M ARR

**Why it scales:**
- State-level data sources (CAL-ACCESS, FPPC) are consistent within each state
- Only city-level scraping varies (and that's what the agent scraper solves)
- Same extraction prompts, same schema, same UI
- California alone has 482 incorporated cities

### Path C: Data Infrastructure Layer

The structured, cross-referenced dataset we'd be building doesn't exist anywhere. Every local government vote, linked to campaign finance, linked to CPRA responses, linked to property records.

**Who pays for the data:**
- Political scientists and academic researchers
- Urban planning organizations
- Civic tech organizations building on top
- Government benchmarking (cities wanting to compare against peers)
- Journalism outlets (investigative research datasets)

---

## 2. Why "Free for Richmond" Is the Best Strategy

Counter-intuitive but correct:

1. **Real deployment with real users.** City staff using conflict scanner, residents checking vote digests, clerk's office referencing document dashboard. Product-market fit validation you can't buy.

2. **Richmond becomes the case study.** "We deployed this in Richmond, the City Clerk uses it, here's how it improved compliance" is infinitely more credible than a demo.

3. **Public visibility creates demand.** When residents in El Cerrito or San Pablo see what Richmond has and they don't, they start asking their councils why.

4. **Personnel Board position = credibility.** Presenting this as a fellow public servant contributing to governance, not an outsider selling. Built-in trust that takes years to establish.

5. **"Free" is only for Richmond.** Other cities pay. Or foundations/grants fund expansion.

---

## 3. Entity Structure Recommendation

### Start With: Fiscal Sponsorship + LLC

**The LLC** is Phillip's. Owns the code, the IP, the technology. Becomes a company if this takes off.

**Fiscal sponsorship** lets you accept grants and tax-deductible donations for the Richmond pilot. "Richmond Common, a fiscally sponsored project of [Code for America / Open Collective]" sounds credible and institutional on public comments.

**Best candidates for fiscal sponsor:**
- Code for America (Brigade network — civic tech volunteers in cities)
- Open Collective Foundation
- Hack Club
- New Venture Fund

**Critical contract term:** IP developed under the project belongs to Phillip (or entity he controls), NOT the fiscal sponsor. Standard, but must be in writing.

### Later Options (Based on Traction)

**If startup path:** Spin LLC into C-corp (or Public Benefit Corporation), take IP, raise VC. PBC (like Patagonia, Kickstarter) allows profit + mission.

**If mission path:** Convert fiscal sponsorship into full 501(c)(3), raise grant funding.

**If both:** Parallel structure (Mozilla model). Nonprofit holds open data, runs free tools, accepts grants. For-profit licenses technology, sells premium features, scales commercially. Complex but proven.

**Don't file anything yet.** Build the thing first. Submit public comments as a private citizen. Entity formation after prototype proves the technology works.

---

## 4. Funding Sources

### Grants (for civic tech / journalism infrastructure)
- Knight Foundation — major civic tech funder
- Democracy Fund
- Google.org
- Mozilla Foundation
- MacArthur Foundation
- ProPublica local projects
- Code for America grants

### Government Innovation Programs
- California state innovation programs
- Federal open government initiatives

### Venture Capital (if for-profit path)
- GovTech Fund — only fund focused specifically on government technology
- Mubadala Ventures — supports govtech expansion
- YC added "government software" to Request for Startups
- Serent Capital — fragmented govtech verticals
- Form Ventures (UK) — regulated markets, civic platforms

### Revenue (self-sustaining)
- 280 subscribers at $5/month covers entire Richmond operating costs
- That's 0.24% of Richmond's 116,448 residents
- Professional tier pricing at $50-200/month significantly accelerates breakeven

---

## 5. Budget Estimates

### Phase 1: Personal Pilot (Months 1-3)

| Item | Monthly | Annual | Notes |
|------|---------|--------|-------|
| Anthropic API (Claude Sonnet) | $40-$80 | $480-$960 | Initial extraction ~$50 one-time, 2-3 meetings/month ongoing |
| PostgreSQL (Supabase free / Railway) | $0-$7 | $0-$84 | Free tier sufficient for pilot |
| Hosting (Vercel free) | $0 | $0 | |
| Domain | $1 | $12 | |
| Email (Resend free) | $0 | $0 | |
| Transcription (Deepgram/Whisper) | $0-$15 | $0-$180 | ~20 hrs of meetings |
| Browser automation (Playwright local) | $0 | $0 | |
| Socrata API | $0 | $0 | Free |
| **Total** | **$41-$103** | **$492-$1,236** | **Biggest cost is time, not money** |

### Phase 2: Beta (Months 4-6, 50-200 users)

| Item | Monthly | Annual | Notes |
|------|---------|--------|-------|
| Anthropic API | $80-$200 | $960-$2,400 | RAG queries $40-$120 + extraction $40-$80 |
| PostgreSQL | $7-$25 | $84-$300 | Railway Starter or Supabase Pro |
| Hosting (Vercel Pro) | $20 | $240 | |
| Email/notifications | $0-$20 | $0-$240 | |
| Video transcription (backfill) | $20-$50 | $240-$600 | |
| Analytics (Plausible/PostHog) | $0-$9 | $0-$108 | |
| Design/UX | $0-$200 | $0-$2,400 | Figma/contractor optional |
| **Total** | **$128-$525** | **$1,536-$4,500** | **A $5K-$10K grant covers this entirely** |

### Phase 3: Full Richmond (Months 7-12)

| Item | Monthly | Annual | Notes |
|------|---------|--------|-------|
| Anthropic API | $200-$600 | $2,400-$7,200 | Cache hit rate 40-60% reduces this |
| PostgreSQL (managed) | $25-$75 | $300-$900 | |
| Hosting + edge caching | $20-$40 | $240-$480 | |
| Email/notifications | $20-$50 | $240-$600 | |
| Browser agent infra | $20-$50 | $240-$600 | |
| Monitoring (Sentry) | $26 | $312 | |
| Analytics | $9-$25 | $108-$300 | |
| Legal (entity, ToS) | — | $500-$2,000 | One-time |
| Design/UX polish | $0-$500 | $0-$6,000 | |
| Video transcription | $50-$100 | $600-$1,200 | Full archive |
| **Total** | **$375-$1,470** | **$4,500-$14,652** | **Even at high end, under $17K/year** |

### Breakeven Math

- At $5/month: need **280 subscribers** to cover Phase 3 high-end costs
- 280 subscribers = **0.24% of Richmond's population**
- Realistically: Richmond stays free (proof-of-concept), revenue comes from scaling to other cities

---

## 6. Competitive Landscape

**Sold TO governments (not competing directly):**
- Madison AI — helps city staff draft reports
- HeyGov ClerkMinutes — helps clerks produce minutes faster
- FOIAXpress / JustFOIA — helps agencies process records requests
- These are govtech. We're civic tech. Different buyer, different mission.

**Academic/research:**
- CitiLink (Portugal) — extracts voting outcomes from minutes. Research prototype, not a product.

**Adjacent:**
- OpenGov (acquired by Cox Enterprises for $1.8B in 2022) — financial transparency for governments. Sold to governments, not citizens.
- Nextdoor — hyperlocal social. $4B+ valuation but still can't monetize.

**Our differentiation:** Built for citizens, against opacity. The product isn't "help the government be efficient." It's "make the information asymmetry disappear."
