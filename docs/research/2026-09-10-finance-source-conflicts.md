# Finance source conflicts — September 10, 2026

This bounded review uses original Richmond, California NetFile filings and the official Connect2 transaction inventory. It adds loan-source coverage and withholds two kinds of unresolved claim from the public transaction list. It does not establish complete committee totals, assign activity to November, or alter candidate snapshot JSON.

## Loan and receipt disagreement

RPOA PAC (FPPC 951606) reports a $30,000 loan to Safe Richmond Neighborhoods (1490887), dated May 29, on [Form 460 filing 217081719, page 49](https://netfile.com/Connect2/api/public/image/217081719#page=49). The original page was rendered and visually checked: Schedule H column (b) shows $30,000 loaned this period, column (d) shows $30,000 outstanding, and column (f) gives May 29 as the date incurred. Page 47 also describes a loan. The document covers May 29–June 30.

The official type 14 (`F460H`) API returns the same lender, borrower, date and value in transaction `27e52105-d8f5-40b5-935c-b495012ef230`. Its June 30 source PDF SHA-256 is `f668672fd9d5fbd121d1544454ed16a34740a1e1810359afe85be94f77204d6e`; the retained metadata response hash is `643ecc8204390033b48b9128b8923f3f239424b1478a6a0c5ecc985545b1db21`.

Four current claims describe that exact committee/date/amount combination as a receipt or transfer:

- [Recipient Schedule A, filing 217288271](https://netfile.com/Connect2/api/public/image/217288271), transaction `9650c6f9-545f-4341-b163-b4b20038ac89`.
- [Recipient Form 497 Part 1, filing 216840276](https://netfile.com/Connect2/api/public/image/216840276), transaction `45814e3f-10b7-4837-82b1-b45a00442661`.
- [Donor Form 497 Part 2, filing 216841017](https://netfile.com/Connect2/api/public/image/216841017), transaction `fa1ba819-249c-40e5-9a57-b45a01461217`.
- [Recipient Form 496 Part 3, filing 216896453](https://netfile.com/Connect2/api/public/image/216896453), transaction `4e8a1acf-6a0b-4069-b146-b46d012b06d5`.

The four claims previously formed one monetary event. The new loan schedule prevents that event from being presented as an additional cash gift while interpretation is unresolved. All five original assertions remain intact. The Schedule H entry remains explicitly a **reported loan amount**, not net-new borrowing or a determination that the recipient's accounting is incorrect. The existing operator queue packages all five source links for a resolve-only judgment. Approval cannot rewrite financial records or publish an amount.

The guard requires current source records, the same explicit FPPC IDs for both parties, matching date and positive amount, and the correct reporting-filer direction. It also applies to a Schedule B1 loan received under those exact conditions. Missing IDs, differing dates/amounts, superseded records and negative adjustments do not trigger it. A same-date resemblance is a reason for review, not proof of one economic event.

## Repeated independent-spending claim

East Bay Working Families (1390351) lists a May 4 mailer supporting Claudia Jimenez for $12,682.30 in both [filing 216728089, page 1](https://netfile.com/Connect2/api/public/image/216728089#page=1) and [filing 216772061, page 2](https://netfile.com/Connect2/api/public/image/216772061#page=2). Their transaction IDs are `0d2037b0-c356-4cd4-ab80-b441011fa681` and `83023461-f480-4477-8854-b44a01675d14`.

The latter filing explicitly amends 216720589, not 216728089. Both claims therefore survive a query that correctly excludes superseded filings. The later [May 26 report, filing 216817898](https://netfile.com/Connect2/api/public/image/216817898), prints a $79,773.84 cumulative figure, while adding the indexed rapid-report rows produced $92,456.14. The difference is $12,682.30. This is strong reason to compare the two originals; it is not permission to delete whichever entry sorts last or to certify the printed cumulative figure as a complete spending total.

Both repeated claims now wait for source review. The comparison requires distinct current filings with the same source scope, identified spender, exact date, positive monetary amount, verified candidate and support/opposition, nullable election date, and nonempty reported description. Same-filing rows remain separate. Different descriptions, targets, dates or values are not merged. Explicit amendment lineage remains authoritative. Source payloads and values never change.

## What is still outside coverage

The live September 10 transaction enum identifies type 5 as Schedule D and type 14 as Schedule H. Schedule D's 62 indexed 2026 rows comprise 53 `MON` and nine `IND` entries. The monetary entries include the loan above; the independent-spending entries overlap rapid Form 496 reports. Consequently, importing all Schedule D rows as spending or donations would introduce another error. This release does not expand Schedule D publication. Type 9, Form 461 Part 5, returned zero indexed rows; that is not evidence of no outside spending elsewhere.

The official [Form 460 instructions](https://fppc.ca.gov/content/dam/fppc/NS-Documents/TAD/Campaign%20Forms/460.pdf) distinguish Schedule B1 loans received, B2 loan guarantors, D contributions/independent expenditures, and H loans made. The local source mappings now reflect that distinction. Electronic records, paper-source gaps and reports filed with other agencies remain explicitly separate.

## Validation and release boundary

A fresh read-only acquisition through September 10 returned 1,267 assertions, eight coverage entries, 1,176 publishable source events and 19 pending assertions. It includes the newly filed [September 8 IBEW 302 receipt in filing 217409736](https://netfile.com/Connect2/api/public/image/217409736). It used 116 metadata requests, 13 original PDFs totaling 876,900 bytes, and zero model calls. These are source-inventory diagnostics, not campaign totals.

Reprocessing the exact same sources with the prior code yields 1,178 public events. The only projection changes are removal of the four-report May 29 monetary event and the two repeated mailer events, plus addition of the reported Schedule H loan. All other event keys and values match. The 2026 source-evidence hash for the reviewed acquisition is `8f3fa9cde7fc3adab8d7a6359e9f0ac0b8c918e69e1e8a34886cf90c0423ee6a`.

Regression tests use minimal source-field fixtures without addresses. They cover exact identities, direction, missing/changed sources, preserved raw payloads, same-filing repetitions, explicit supersession, the full eight-form acquisition requirement, failed-source aborts and one source-comparison packet per conflict. PostgreSQL integration executes the real batch writer and packet reader/writer, including address-free selection and resolve-only approval.

At the time of this source review, the acquisition is read-only. Applying the complete reviewed snapshot belongs to the normal release step after code/UI verification. There is no migration, archive backfill, new table, new service or paid parsing path. The existing daily finance job owns subsequent refreshes. Legacy contributions and checked-in candidate summaries are untouched.
