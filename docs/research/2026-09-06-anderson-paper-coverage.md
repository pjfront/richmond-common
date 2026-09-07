# Anderson paper-filing coverage — September 6, 2026

## Verified cause

FPPC **1481105** is the correct committee identifier for Ahmad Anderson. The [City's nomination roster](https://www.richmondca.gov/DocumentCenter/View/78675) identifies Anderson for Mayor 2026 with that number. The new electronic finance index has no receipt assertions reported by that committee. One electronic Form 497 Part 2 claim from the Richmond Police Officers Association reports a $2,500 transfer **to** that committee; it correctly remains separate from recipient-reported cash receipts.

This is a paper-source gap, not a finding of zero fundraising or an inferred surname match. Current [official metadata for Form 460 filing 217094857](https://netfile.com/Connect2/api/public/filing/info/217094857?format=json) returns agency `RICH`, `sosFilerId=1481105`, `localFilerId=RICH-113213`, `isEfiled=false`, `efileSize=0`, the exact committee name, and no `amends`/`amendedBy`. It was filed July 29 and covers May 29–June 30. The two August 17 reports and the August 31/September 3 reports also explicitly return `isEfiled=false` for this identifier.

The prior $73,300 headline came from the existing Form 460 summary cache. Its latest row is filing 217094857, with $9,140 monetary contributions this period and $73,300 in the extracted cumulative field. The [August 8 benchmark](../audits/2026-08-08-form460-vision-benchmark.md) documents the original image-summary validation. **This bridge publishes no monetary amounts** and does not add that cumulative figure to the electronic receipts, compare different periods, or treat cached summary extraction as a reconciled donor breakdown.

The read-only September 6 legacy check found 198 contribution rows totaling $60,567.06, including 74 rows/$18,997.06 dated in 2025. Only 124 rows/$41,570 were dated in 2026. None has a `document_id`. No retained `documents` row was found by the targeted filing IDs, URLs, committee metadata, or contribution links. The latest June 30 period is represented by one $9,140 legacy row, not a source-verified set of itemized donors. These aggregates are diagnostic evidence, not newly published fundraising claims.

## Official inventory adapter

The current [NetFile committee filing page](https://netfile.com/public/RICH/campaign/filingsByFiler/214395297-Anderson_for_Mayor_2026) is backed by public metadata APIs observed in the portal's own JavaScript:

1. `GET https://netfile.com/api/public/sites/api/Filings/byId/217094857?agencyCode=RICH` resolves the known FPPC-linked filing to portal `filerId=214395297`. The portal ID is a separate identifier, not the FPPC number.
2. `GET https://netfile.com/api/public/sites/api/filings/byFiler?agencyCode=RICH&filerId=214395297&isArchived=false` returns that committee's current nonarchived filing array. The September 6 response contains **22 entries and `totalCount=0`**. The portal itself uses the array. The fixture preserves this response; zero in that field cannot mean an empty filing list or establish complete reporting coverage.
3. `GET https://netfile.com/Connect2/api/public/filing/info/{filingId}?format=json` independently verifies the latest periodic filing's FPPC identifier, agency, name, dates, paper/electronic flag, and amendment status.

The checked list's latest periodic report is [217094857, filed July 29, through June 30](https://netfile.com/Connect2/api/public/image/217094857). The four later 24-hour filings are:

| Filing date | Official Form 497 |
|---|---|
| September 3 | [217352920](https://netfile.com/Connect2/api/public/image/217352920) |
| August 31 | [217332630](https://netfile.com/Connect2/api/public/image/217332630) |
| August 17 | [217243030](https://netfile.com/Connect2/api/public/image/217243030) |
| August 17 | [217243444](https://netfile.com/Connect2/api/public/image/217243444) |

Those filing dates do not establish contribution dates or election attribution. A bounded download of the two latest PDFs found one image-only page each and zero deterministic text: 276,143 bytes/SHA-256 `fc9bfe2bfa8b4b74cac3df41e436bfd81648b8ac6e43cc94bf8861cde077e8de`, and 192,630 bytes/SHA-256 `82c8bb5fdc6b49016ee345878db00bdb055161471271f6c839da5942c274bb62`. No OCR/model calls or production writes were made for this audit.

The list also identifies Form 460 **216812159**, filed May 21 for April 19–May 16, absent from the current summary cache. Two earlier filings share the January 1–April 18 period; the bridge does not guess amendment lineage from their dates or numeric IDs. A future paper transaction adapter must preserve those source assertions and reconcile explicit amendments and duplicate-report claims before publishing donor totals. The inventory API can repair rolling-RSS discovery loss without downloading the entire archive.

## Minimal public bridge and storage contract

`getAndersonFilingCoverage()` uses the existing Next.js server data cache, with **one-hour revalidation**, and does not write any database table or monetary assertion. Each successful refresh uses two metadata GETs: the exact configured `byFiler` list and Connect2 metadata for its latest periodic report. Both requests have a 2.5-second timeout, a 256 KiB streamed response ceiling, and redirects disabled; inventories are capped at 100 rows. Neither URL comes from untrusted response fields. Identity changes, inconsistent dates/counts, duplicate IDs, and an ambiguous or superseded latest periodic filing fail closed.

The component retains the dated September 6 source links on failure, explicitly states that the current check is unavailable, and displays the last successful verification time in Richmond. A cached success older than two hours is labeled awaiting a fresh check. The public list shows the latest periodic report and up to four rapid reports filed after its coverage end; it claims no complete campaign history or contribution-date attribution. Reports filed after that coverage end but before the periodic report's filing date are not omitted. New rapid links are not automatically classified as paper solely because the filer previously used paper. The source explanation and links survive an electronic-ledger loading failure.

No schema migration, generated database type, scheduled workflow, provider, PDF extraction route, or monetary total is changed. Future deterministic transaction extraction requires text-bearing filings or a separately verified OCR/manual pathway; retaining the metadata alone does not solve scanned donor extraction.

Validation: 27 targeted frontend tests and 33 pipeline-manifest tests pass, along with TypeScript and targeted ESLint. The local Next.js page successfully fetched current official metadata and displayed its September 6, 10:02 AM Richmond verification time. A 390px browser check confirmed all five filing links, the exact committee inventory link, no horizontal overflow, no framework error overlay, and no browser errors. The local worktree uses an external dependency junction, so verification used Next.js's webpack development mode; Turbopack rejects a junction outside its filesystem root. CI remains the production build check.
