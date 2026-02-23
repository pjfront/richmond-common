# Form 700 Research Findings

**Date:** 2026-02-22
**Purpose:** Understand Form 700 filing structure, access methods, and parsing strategies before designing the ingestion feature.

## What is Form 700?

California's Statement of Economic Interests — a financial disclosure form required for elected officials and designated government employees under the Political Reform Act. Officials disclose investments, real property, income, gifts, and travel payments that could create conflicts of interest.

## Form Structure (7 Sections)

### Cover Page
- Filer name, agency, division, position/title
- Jurisdiction of office (state, multi-county, county, city, other)
- Statement type: Annual, Assuming Office, Leaving Office, Candidate, Amendment
- Period covered (date range)
- Verification signature and date

### Schedule A-1: Investments (Stocks, Bonds, Other Interests < 10% Ownership)
- Name of business entity
- General description of business
- Fair market value: $2,000–$10,000, $10,001–$100,000, $100,001–$1,000,000, over $1,000,000
- Nature of investment (stock, partnership, etc.)
- Acquired/disposed dates if during period

**Conflict scanner value:** Cross-reference company names against vendors/contractors in agenda items.

### Schedule A-2: Investments in Business Entities/Trusts (>= 10% Ownership)
- Name of business entity/trust
- Business address
- Business activity description
- Fair market value (same tiers as A-1)
- Nature of investment (sole proprietorship, partnership, LLC, etc.)
- If entity has parent, list parent name
- Your pro rata share of gross income: $0–$499, $500–$1,000, $1,001–$10,000, $10,001–$100,000, over $100,000
- Nature of entity's investment or interest, if any

**Conflict scanner value:** Direct business ownership is the strongest conflict signal — if an official owns 10%+ of a company doing business with the city, that's a clear disclosure requirement.

### Schedule B: Real Property Interests
- Assessor's parcel number or street address
- City and fair market value (same tiers)
- Nature of interest (ownership, deed of trust, easement, option, lease)
- If rental property, gross income received
- Sources of rental income (>= $10,000)
- Loan information if applicable (lender name, address, business activity, interest rate, term, highest balance, guarantor)
- Date acquired/disposed if during period

**Conflict scanner value:** Cross-reference property addresses against land-use, zoning, and development agenda items. A council member who owns property in an area being rezoned has an obvious interest.

### Schedule C: Income, Loans & Business Positions
**Part 1 — Income (>= $500)**
- Source name, address, business activity
- Your business position (if applicable)
- Gross income received: $500–$1,000, $1,001–$10,000, $10,001–$100,000, over $100,000
- Consideration/services for income

**Part 2 — Loans (>= $500)**
- Lender name, address, business activity
- Interest rate, term, highest balance during period
- Whether security was provided and type
- Guarantor if applicable

**Conflict scanner value:** Income sources reveal employment and consulting relationships. If an official receives >$500 from an entity appearing in agenda items, that's a potential conflict.

### Schedule D: Income — Gifts
- Source name, address, business activity
- Gift date, value, description
- Up to 6 sources per form, 3 gifts per source
- Gift threshold: $50+ must be reported (as of 2024-2025)

**Conflict scanner value:** Gifts from entities appearing before the official for decisions. The $50 threshold is very low — catches meals, event tickets, etc.

### Schedule E: Travel Payments, Advances & Reimbursements
- Source name, address
- Is source a nonprofit (501(c)(3))?
- Business activity of source
- Travel dates (start/end)
- Amount
- Type of payment (gift/income)
- Made a speech/participated in panel? (yes/no)
- Travel description (destination, purpose)

**Conflict scanner value:** Travel payments from entities with business before the city — e.g., a developer paying for a council member's conference trip, then appearing on a development approval agenda.

## Filing Locations for Richmond Officials

### 1. NetFile SEI Public Portal (2018+, Local Filers)
- **URL:** `https://public.netfile.com/pub/?AID=RICH`
- **What:** E-filed Form 700s from city employees and lower-level designated positions
- **Format:** Generated PDFs with text layers (extractable with PyMuPDF)
- **API access:** No structured data API. PDFs served via `https://netfile.com/Connect2/api/public/image/{id}`. The Connect2 API is campaign-finance only — no SEI endpoints found.
- **Key detail:** Richmond adopted NetFile e-filing in January 2018. Pre-2018 filings are paper.

### 2. FPPC DisclosureDocs (Section 87200 Filers, 2016+)
- **URL:** `https://form700search.fppc.ca.gov/Search/SearchFilerForms.aspx`
- **What:** State-level repository of Form 700s from "87200 filers" — officials whose positions are specified in Government Code Section 87200
- **Who qualifies (87200):** City council members, mayor, planning commissioners, city manager, city attorney, finance director, and other positions handling contracts/permits
- **Search filters:** Entity, Agency (952+ agencies including "City of Richmond"), Position, Form Type, Date Range, Name
- **Format:** Mix of scanned and generated PDFs

### 3. FPPC eDisclosure Portal (Mandatory from Jan 2025)
- **URL:** `https://form700.fppc.ca.gov/`
- **What:** New mandatory e-filing portal per AB 1170 (effective January 1, 2025)
- **Impact:** All Section 87200 filers must e-file directly with FPPC starting with 2024 annual statements (due April 1, 2025). This is a major shift — previously optional.
- **Implication:** Future Richmond council member filings will be at FPPC, not NetFile. Need to monitor both sources during transition.

### 4. City DocumentCenter (Historical Paper Filings)
- **URL:** `https://www.ci.richmond.ca.us/1439/Form-700---Statement-of-Economic-Interes`
- **What:** Scanned paper filings from older years
- **Format:** Image-based PDFs (not text-extractable, needs OCR)
- **Examples found:**
  - Eduardo Martinez 2015: `DocumentCenter/View/30976/` (scanned, not parseable without OCR)
  - Tom Butt 2013: `DocumentCenter/View/28724/` (scanned, not parseable without OCR)

## PDF Format Analysis

### Two Generations
1. **Pre-2018 (paper filings):** Scanned image PDFs. Variable scan quality. No text layer. Requires OCR (Tesseract or cloud OCR). Lower priority — historical data, less actionable for current conflict detection.
2. **2018+ (NetFile e-filed):** Generated PDFs with clean text layers. PyMuPDF extracts text reliably. Consistent layout because they're computer-generated from form data.

### Parsing Strategy by Format
- **Generated PDFs (2018+):** PyMuPDF text extraction → Claude API structured extraction (same pattern as meeting minutes). Should work well given our existing extraction infrastructure.
- **Scanned PDFs (pre-2018):** OCR → text → Claude API extraction. Add Tesseract or cloud OCR as a preprocessing step. Lower priority.
- **FPPC eDisclosure (2025+):** Unknown format yet — need to check once 2024 annual filings are published (after April 1, 2025). Likely structured data or clean generated PDFs.

## Schema Reference: SF Ethics Commission (Gold Standard)

San Francisco publishes Form 700 as structured open data on DataSF via SODA API. This is the ideal end-state for any city's transparency portal.

### Schedule B (Real Property) — Dataset ID: `9dv8-3432`
Fields: `filerid`, `filername`, `departmentname`, `positionname`, `officeoragency`, `periodoffilingyear`, `filingtype`, `parceloraddress`, `city`, `fairmarketvaluescheduleb`, `natureofinterest`, `dateacquired`, `datedisposed`, `ifrental_grossincomereceived`, `loan_nameoflender`, `loan_addressoflender`, `loan_businessactivityoflender`, `loan_interestrate`, `loan_term`, `loan_highestbalanceduringperiod`, `loan_guarantor`

### Schedule E (Travel) — Dataset ID: `e67f-ux3j`
Fields: `filerid`, `filername`, `departmentname`, `positionname`, `officeoragency`, `periodoffilingyear`, `filingtype`, `nameofsource`, `address`, `city`, `state`, `zip`, `isnonprofit`, `businessactivity`, `startdate`, `enddate`, `amount`, `typeofpayment`, `madespeech`, `traveldescription`

**Takeaway:** Our `form700_interests` table design should align with these field sets — they represent what structured Form 700 data looks like when done right.

## Conflict Scanner Integration

Form 700 is the **highest-value conflict detection signal** because it captures interests officials themselves have disclosed. Unlike campaign contributions (which show who gave money), Form 700 shows what the official personally owns, earns, and receives.

### Integration Points by Schedule
| Schedule | Cross-Reference Against | Signal |
|----------|------------------------|--------|
| A-1 (Investments) | Vendor/contractor names in agenda items | Official holds stock in company getting city contract |
| A-2 (Business Entities) | Vendor names, business license applicants | Official owns 10%+ of company before the body |
| B (Real Property) | Land-use items, zoning changes, development approvals | Official owns property affected by decision |
| C (Income) | Agenda entities paying official >$500 | Financial relationship with party before the body |
| D (Gifts) | Entities appearing in agenda items | Gift-giver has business before the body |
| E (Travel) | Entities appearing in agenda items | Travel sponsor has business before the body |

### Priority for Implementation
1. **Schedule A-2** (direct business ownership) — strongest signal, clearest conflicts
2. **Schedule B** (real property) — land-use conflicts are the most common recusal trigger
3. **Schedule C** (income) — reveals employment/consulting relationships
4. **Schedule D** (gifts) — low threshold catches many connections
5. **Schedule A-1** (investments) — stock ownership in large companies is common but rarely actionable at city level
6. **Schedule E** (travel) — important but least frequently disclosed

## Recommended Extraction Strategy (3 Phases)

### Phase 1: NetFile E-Filed PDFs (Local Filers, 2018+)
- Source: `public.netfile.com/pub/?AID=RICH`
- Scrape filing list → download PDFs via Connect2 API → PyMuPDF text extraction → Claude API structured extraction
- Expected volume: ~50-100 filers/year, 1 filing each = 50-100 PDFs
- Covers: Department heads, commission members, designated employees

### Phase 2: FPPC Filings (Section 87200 Filers)
- Source: `form700search.fppc.ca.gov` (historical) + `form700.fppc.ca.gov` (2025+)
- Covers: Council members, mayor, planning commissioners, city manager, city attorney
- These are the highest-value filers for conflict detection
- May need Playwright for the FPPC search portal (JavaScript-heavy)

### Phase 3: Historical Paper Filings (If Needed)
- Source: City DocumentCenter
- Requires OCR preprocessing (Tesseract or cloud OCR)
- Only pursue if historical conflict analysis is valuable enough to justify OCR costs
- Most valuable for long-serving officials (Tom Butt has 20+ years of filings)

## Key Design Decisions (For Future Design Session)

1. **Table structure:** Single `form700_filings` parent table + per-schedule child tables? Or flatten into a single `form700_interests` table with a `schedule_type` discriminator? SF uses per-schedule datasets, which maps cleanly to separate tables.

2. **Entity matching strategy:** Form 700 entity names (businesses, employers, property addresses) need fuzzy matching against agenda item text. Can reuse/extend the conflict scanner's existing normalization and matching logic.

3. **Filing period tracking:** Form 700 covers a specific period (typically one calendar year). The conflict scanner needs to know which filing period applies to which meeting date — an interest disclosed in 2024's annual filing is relevant for all 2025 meetings until the 2025 annual filing supersedes it.

4. **Dual-source deduplication:** Officials who file both locally (NetFile) and with FPPC may have duplicate records. Need dedup logic by (filer_name, agency, period, schedule_type).

5. **AB 1170 transition handling:** During 2025, some Richmond officials may file with NetFile (habit) while being required to file with FPPC (law). Monitor both sources. After transition settles (~2026), FPPC becomes the primary source for 87200 filers.

6. **Recusal prediction:** The ultimate use case — when an agenda item touches an official's disclosed interest, predict whether recusal is required under the Political Reform Act. This is the most valuable feature Form 700 enables, but also the most complex (requires understanding FPPC's recusal analysis framework).

## FPPC Form 700 Reference URLs

Official form field definitions (2024-2025 filing year):
- Cover Page: `https://fppcada.fppc.ca.gov/form700/form700_2024-2025/03-cover-page.html`
- Schedule A-1: `https://fppcada.fppc.ca.gov/form700/form700_2024-2025/04-schedule-a1.html`
- Schedule A-2: `https://fppcada.fppc.ca.gov/form700/form700_2024-2025/04-schedule-a2.html`
- Schedule B: `https://fppcada.fppc.ca.gov/form700/form700_2024-2025/05-schedule-b.html`
- Schedule C: `https://fppcada.fppc.ca.gov/form700/form700_2024-2025/06-schedule-c.html`
- Schedule D: `https://fppcada.fppc.ca.gov/form700/form700_2024-2025/07-schedule-d.html`
- Schedule E: `https://fppcada.fppc.ca.gov/form700/form700_2024-2025/08-schedule-e.html`

## Richmond-Specific Notes

- Richmond's Conflict of Interest Code resolution: `https://www.ci.richmond.ca.us/DocumentCenter/View/53619/`
- Richmond has ~7 council members + mayor + city manager + city attorney + planning commissioners + numerous commission members and designated employees — total Form 700 filers likely 50-100+
- Council members are Section 87200 filers (broadest disclosure requirements)
- Commission members' disclosure categories vary by commission (defined in the Conflict of Interest Code appendix)
