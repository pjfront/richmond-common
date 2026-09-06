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

Automated tests execute source identity, period, hash, replay, local OCR command, address-free candidate display and workflow contracts. The real Python writer also runs against disposable PostgreSQL with the production finance privacy and review migrations: anon/auth cannot read raw evidence, service writes work, generic approval never publishes, rejection suppresses identical sources, and a packet failure rolls back its evidence rows. Source failure never changes the public JSON.

Local preparation did not exercise a real Tesseract binary: no reviewed baseline needed OCR and the Windows host lacked it. Native PDF text extraction and the exact subprocess/TSV contract are tested; changed-scan accuracy remains a source review step, not a claim made by those tests. The GitHub job installs Tesseract before running the producer.
