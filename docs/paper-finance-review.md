# Paper finance snapshots and source review

Anderson's public numbers come from `web/src/data/anderson-reported-finance.json`, read by `web/src/lib/anderson-finance.ts`. They are source-checked reported figures, not a reconciled transaction ledger. The source audit records the actual filing discrepancies in `docs/research/2026-09-06-anderson-source-audit.md`.

The snapshot has `schema_version: 1`, the exact committee identity (FPPC 1481105; portal 214395297), an explicit review date/method, and `sources[]`. Each source pins its filing ID, form, filing date, reporting period where applicable, original URL, PDF hash, metadata hash, and reviewed pages. `periodic` contains the latest source's decimal-string-or-null fields and caveats. `periodic_history` lists one checked report per adjacent period; `rapid_receipts` preserves actual receipt dates, reported donor names and source pages. Blank cells remain null. A second scan of the same period is corroborating evidence, not another period or an inferred amendment.

Four reviewed 2026 periods can be added only after proving that they are adjacent and nonoverlapping. Do not add printed running totals to those periods or add a 497 merely because its filing date is later. The source audit found two August-filed notices reporting May receipts and a running total carrying prior-year money. Donor attachment conflicts prevent describing the summary subtotal as a complete donor reconstruction.

## Daily automation

`src/paper_finance_review.py` is part of the existing `daily-finance-ledger` job in `data-sync.yml`. It uses the original committee's official byFiler inventory, then verifies each selected filing against independent Connect2 FPPC/agency/form/period metadata. It reads all pinned sources, all periodic reports covering or filed since January 2026 (including newly filed older-period amendments), and rapid reports filed after the current reviewed periodic cutoff. Exact PDF and metadata hashes must match a reviewed paper source; changed metadata cannot silently inherit the old review. This is a bounded current-source check, not a historical archive backfill or rolling-RSS dependency.

The job has only the database credential. It installs local Tesseract, uses no paid model/API credential, and does not send email. Image processing stays local. The snapshot and inventory allow up to 100 sources. Each run reads their bounded metadata, then permits 16 PDF reads, 6 MiB per PDF, 32 MiB total source bytes and four changed preparations. Excess work is deferred with an explicit count; unseen sources go first, then the oldest successful check. An expired prepared source with unchanged bytes does not consume a preparation slot. A conservative 6 MiB reservation before each PDF keeps the byte budget from aborting completed work. The 100-source inventory limit requires a separately reviewed pagination change if the official inventory eventually exceeds it.

Requests do not follow redirects or retry. Each request has connection/read timeouts and a 30-second streaming deadline check; a blocked socket can still consume its read timeout. Each local OCR call is capped at 30 seconds, the first eight PDF pages are prepared, and transcript/response sizes are bounded. The existing job has a 15-minute timeout. Omitted pages and candidate-token truncation are explicit.

Reviewed hash-identical sources require no OCR. A successful first import retains exact raw PDF bytes once; ordinary subsequent runs read only inventory/metadata. An unchanged source's PDF becomes eligible for another hash check after seven days. Changed metadata forces an earlier PDF check. A source with unavailable OCR remains a review obligation and retries preparation on the next poll; it is never recorded as a valid zero-result filing. Parser output preserves private text/geometry, while the queue exposes only allowlisted financial labels, amount/date candidates and source-page links. These tokens do not establish donor/date/amount row associations.

## Persistence and publication boundary

### The two committee organization reports

The same daily command also monitors `web/src/data/committee-organization-filings.json`. This public snapshot pins the reviewed Form 410 for Safe Richmond Neighborhoods (FPPC 1490887, portal 216706544) and East Bay Working Families (FPPC 1390351, portal 168662145), including source hashes/pages and explicitly printed sponsor facts. It never derives a sponsor from the money ledger or a similar name. Public wording remains tied to the report's filing date while a changed source waits for review.

The organization pass has its own selector: two exact committees, up to 200 inventory rows per committee, and at most 16 relevant organization reports per committee. EBWF's inventory already has 148 entries, so Anderson's separate 100-row bound is preserved. Each pass selects its pinned source plus any Form 410 filed on or after that source's portal date. It verifies exact agency, FPPC ID, form UUID, filing identity and dates against independent Connect2 metadata. A changed reported committee name produces a review packet when both official endpoints agree on the same FPPC identity. A missing baseline, malformed inventory or wrong identity fails explicitly; no empty sponsor list replaces the public snapshot.

On first verification, the reviewed PDF hash and source identity/date must match the checked-in snapshot. The private cache anchors that verified metadata version. Daily checks reuse unchanged PDF bytes for seven days; changed metadata forces another bounded PDF read, and a weekly recheck detects a replaced scan under the same filing ID. Updating the checked-in review version forces a new byte check before accepting its metadata anchor. The pass allows four PDF reads, two newly changed source records, 6 MiB per PDF and 32 MiB total reads per run, with explicit deferred counts and unseen/oldest-check ordering. Candidate and organization passes have independent source budgets; the existing 15-minute job remains their overall limit.

Organization packets include the old source-pinned claims, new source identity/date/hash, old reviewed page links and the new whole-PDF link. They ask whether any sponsor, purpose or identity changed. They **do not extract new sponsor claims**, use OCR or a model, change the JSON, publish a brief, or modify finance rows. Each source version uses the existing resolve-only engineering inbox; repeated checks do not reopen rejected judgments. A source-checked JSON PR and deployment are still required to publish a new dated description. An amendment label or a later filing ID is not treated as proof of source supersession.

Raw evidence uses the same private `netfile_transaction` document boundary, with artifact kinds `committee_organization_pdf` and `committee_organization_review`. Its cache is separate from Anderson's paper-review cache. No table, migration, workflow or additional scheduled job is introduced. The command attempts both watches independently and exits unsuccessfully if either source pass fails, while retaining successful private evidence from the other. Its report adds `organizations` counters and `failed_sections`; neither failure advances a public “checked” date.

For a controlled offline organization check, `--source-dir` may provide `organization-216706544.inventory.json`, `organization-168662145.inventory.json`, and the same `{filing_id}.pdf`/`{filing_id}.metadata.json` source files. `--organizations` selects the reviewed registry file; identity and source-hash constraints still apply.

### Shared privacy and publication boundary

No new table or migration is required. Raw PDFs and their source/metadata/OCR records use the existing `documents` table with `source_type='netfile_transaction'` and explicit `artifact_kind='paper_filing_pdf'` or `paper_filing_review`. This existing finance class is covered by migration148's restrictive public-read policy. A new `netfile_paper` class would not be covered; do not change the class without extending and testing that policy. Hash collisions with an existing public document class fail closed. Public pages do not read these private records.

Each filing's evidence insertion and engineering packet commit together under an advisory lock. Content hashes retain immutable source versions; a successful later byte check updates only the check timestamp. An unchanged daily replay performs no source or decision write. Identical evidence remains suppressed after rejection. Improved preparation can update an open packet's evidence and review version, but does not reopen a closed judgment.

The producer uses migration149's existing review inbox with `action_kind='resolve_only'`. The packet includes the exact source version, dates, prepared candidates, proposed snapshot file, source-page links, affected pages, recommendation and alternatives. **Approving it only records a judgment. It cannot publish amounts, create a civic brief, modify contributions, or rebuild a finance projection.**

To publish a new numeric snapshot, inspect the original prepared pages, resolve or preserve conflicting cells, edit the checked-in JSON with exact new hashes/pages/periods, and add or update the source/overlap tests. Use a normal reviewed PR and deployment. Record the engineering packet's resolution with that result. The next unchanged poll preserves the accepted snapshot. This deliberately makes the remaining source interpretation and code publication step explicit; it does not claim that generic queue approval executes a financial repair.

## Commands and verification

The default command is read-only:

```bash
python src/paper_finance_review.py --report tmp/finance/paper-review-summary.json
```

`--source-dir` can reuse exact retained `{filing_id}.pdf` and `{filing_id}.metadata.json` files for a controlled first import, avoiding duplicate source downloads. An optional retained `inventory.json` is useful for offline tests. Official identity, byte limits and source hashes are still checked. Add `--apply` only for the authorized private evidence/queue write; it does not publish a snapshot.

The September 6 preparation dry run used the current official inventory, a read-only database cache lookup, and all ten retained reviewed originals: 10 filings checked, 0 changed sources, 1 HTTP request, 0 PDF downloads, 0 LLM calls and 0 publications. Total retained source bytes read were 22,498,060. It made no production write.

Automated tests execute source identity, period, hash, replay, local OCR command, address-free candidate display and workflow contracts. Organization tests additionally cover the 148-row inventory, renamed but identically numbered committees, replaced scans, changed metadata, weekly checks, new-report bounds and rejected/approved review behavior. The real Python writer runs both source classes against disposable PostgreSQL with the production finance privacy and review migrations: anon/auth cannot read raw evidence, service writes work, generic approval never publishes, rejection suppresses identical sources, and a packet failure rolls back its evidence rows. Source failure never changes the public JSON.

Local preparation did not exercise a real Tesseract binary: no reviewed baseline needed OCR and the Windows host lacked it. Native PDF text extraction and the exact subprocess/TSV contract are tested; changed-scan accuracy remains a source review step, not a claim made by those tests. The GitHub job installs Tesseract before running the producer.
