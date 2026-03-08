# Court Records Research: Contra Costa County / Tyler Odyssey

**Date:** 2026-03-07
**Sprint:** S8.2
**Status:** Research complete, build approved (targeted lookup tool)

## Portal Identification

**System:** Tyler Technologies Odyssey Portal
**URL:** https://odyportal.cc-courts.org/portal
**Smart Search:** https://odyportal.cc-courts.org/Portal/Home/Dashboard/29
**Hearings Search:** https://odyportal.cc-courts.org/Portal/Home/Dashboard/26

The court's main website is transitioning from `cc-courts.org` to `contracosta.courts.ca.gov`. Both domains are currently active.

A separate, older Traffic Portal exists at `https://cmsportal.cc-courts.org/` (different system, not Odyssey).

## Data Availability

| Case Type | Case Info | Documents | Hearing Dates |
|-----------|-----------|-----------|---------------|
| Civil (unlimited/limited) | Yes | Yes (free download) | Yes |
| Small Claims | Yes | Yes (free download) | Yes |
| Probate | Register of actions only | No | Yes |
| Criminal | **No** | **No** | Calendar only |
| Family Law | **No** | **No** | **No** |
| Traffic | Separate portal | No | Yes |

**Key limitations:**
- Criminal case data is not available online. Requires in-person or mail requests (forms CR-147, CR-114).
- Pre-2000 cases have limited or no electronic records.
- Sealed and confidential cases are excluded.

**Search fields (Smart Search):**
- Party name (first/last)
- Case number
- Date range
- Attorney name

**Per-case data available:**
- Case number, type, category
- Filing date, status, disposition
- Parties (plaintiff/defendant names, roles)
- Register of actions (filings timeline)
- Hearing dates and courtroom
- Downloadable documents (civil cases)

## Technical Architecture

- ASP.NET application (standard for Tyler products)
- JavaScript for dynamic content, but search/results pages may work with standard form POST/GET
- Predictable URL patterns (case detail pages)
- Cookie/session-based authentication
- SSL certificates may have issues (observed during research)

## The judyrecords Incident (2022) and Its Impact

In 2022, judyrecords.com discovered a severe vulnerability in Tyler Odyssey portals: case URLs followed predictable patterns and the system did not verify user authorization before returning data. This exposed approximately 322,525 confidential California State Bar discipline records.

**Consequences:**
- Tyler took portals offline across multiple states (CA, TX, GA, OH, KS)
- 1,390,336 Odyssey Portal cases removed from judyrecords
- California State Bar data breach disclosure
- Google cached ~250,000 unprotected case links including sealed cases
- Tyler significantly hardened portal security afterwards

**Impact on RTP:** Post-judyrecords, Odyssey portals are hardened against bulk scraping. RTP's targeted lookup approach (20-50 name searches) is unaffected because it's functionally identical to manual citizen use, but bulk scraping would carry higher legal and reputational risk.

## Legal Framework

**California Government Code 68150:**
- Trial court records maintained electronically shall be viewable at the court
- Courts must provide at least one method of free public access to electronic records
- Standards must ensure public access "with at least the same amount of convenience as paper records"
- Does not explicitly address automated/bulk access

**Risk assessment for RTP's targeted lookups:**
- Court records are public information. Right to access is clear.
- Targeted name searches (20-50 queries) are indistinguishable from manual citizen access.
- No bulk scraping, no systematic enumeration, no predictable URL exploitation.
- Defensible as standard public records access consistent with California law.

## API Alternatives

**No public API exists for Contra Costa County court records.** Tyler offers an Enterprise Justice Integration Portal with commercial APIs, but these are licensed to government agencies only.

**State-level access:** California has no state-level API for trial court records. Each of the 58 superior courts manages independently.

**Third-party aggregators:**
- **CourtListener** (Free Law Project): Free REST API, primarily federal courts and appellate opinions. Limited California trial court coverage. Not useful for Contra Costa County Superior Court civil cases.
- **UniCourt:** Commercial API with broad state court coverage. Paid.
- **Docket Alarm:** Commercial API for bulk document access. Paid.

None are viable free alternatives for our use case.

## Existing Open-Source Scrapers

1. **biglocalnews/court-scraper:** Platform-based framework with `court_scraper.platforms.odyssey` module. Uses requests + Selenium. Multi-jurisdiction. Most architecturally aligned with RTP's approach.
2. **open-austin/indigent-defense-stats:** Mature Odyssey scraper (Texas counties). Saves HTML, parses to JSON. Odyssey interface is consistent across jurisdictions.
3. **freelawproject/juriscraper:** Free Law Project's scraper library. More focused on appellate opinions than trial court records.

## RTP Implementation Decision

**Approach:** Targeted name-based lookup tool (not bulk scraper).

**Rationale:**
- RTP's need is narrow: cross-reference officials, donors, and contractors against civil court cases
- Volume is small (~20-50 name searches over time)
- Legal risk profile is very low (equivalent to manual citizen searches)
- Criminal records unavailable online, but civil cases cover the most relevant data for conflict detection (lawsuits, liens, judgments involving officials/donors)
- Credibility tier: 1 (official court records)
- Publication tier: Graduated (legal data requires careful framing validation)

**Rate limiting:** 3s between name searches, 2s between case detail fetches. Total runtime for full search list: ~6 minutes.

## Sources

- Contra Costa Odyssey Portal: https://odyportal.cc-courts.org/portal
- Court Records Page: https://contracosta.courts.ca.gov/online-services/records
- Criminal Records Info: https://contracosta.courts.ca.gov/divisions/criminal/court-records-criminal-cases
- judyrecords incident: https://www.judyrecords.com/what-happened-with-tyler-technologies
- California Gov Code 68150: https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=68150.&lawCode=GOV
- court-scraper (biglocalnews): https://github.com/biglocalnews/court-scraper
- CourtListener API: https://www.courtlistener.com/help/api/
