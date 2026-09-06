# September 6 release evidence

## Access and maintenance release — deployed

Production was independently verified at `7c56b6e5f92acb1553a807256ba1ae7c1e863331`, deployment `dpl_DJyqAKnwN7UPZ66cfJxoPo2ZuXHE`, on September 6. The Vercel API confirmed READY production state, the pinned Richmond project, exact GitHub commit/ref metadata, and the `richmondcommons.org` alias. The homepage and `/api/health` returned HTTP200; health reported healthy.

The immediately preceding production deployment was `dpl_3Fit9sx7D97BgAbA3iqsRfbjSfUp`, source `0ff9fd50443d8d13e15a4d83845b2997cfc1054a`. The release includes reviewed main changes since that source: protected operator reads, retired unfinished public directory/detail paths, council accessibility and contrast repairs, bounded sitemap/discovery, contained subscriber delivery and recap recovery, and release/preview tooling. The upcoming resident experience is a separate release.

Build Check main-push run34043577214 passed on the deployed commit. PR171's schema comparison, build, Python, frontend and database permission checks passed. Its generated types came directly from production through pinned SupabaseCLI2.112.0; the schema object did not change, apart from the hosted PostgREST version metadata. The remaining generated changes were helper formatting.

The deploy wrapper uploaded an immutable Git archive, 2,676KB across388 estimated files, using pinned VercelCLI59.1.4. Its final stdout URL parser rejected the CLI output after deployment completed. Independent control-plane and HTTP verification resolved the ambiguity; the deployment was neither repeated nor rolled back. The captured stdout bytes were not retained, so their precise format is unknown.

Migration147 was applied atomically from committed SQL, with an exact statement recorded in the migration ledger. Its SHA256 is `f91813f86e8eb667077986c3ed7f44ebf841e45b1b14ed209c2f11d023c52a15`. Anonymous/authenticated access to private operator tables is denied; neighborhood councils remain publicly readable with no public mutation grants. Service access and existing row counts were preserved. Migrations145 and146 were already applied before this release. Migration136 remains applied; forbidden134 remains absent. No database rollback was performed.

The production server has the required sensitive service-role environment key. An authenticated production inbox smoke test could not be completed because this checkout has no local operator password; no credentials were changed or requested. Route authorization and service-client behavior passed executable tests, and the private table grants passed actual PostgreSQL checks.

## Resident and finance release — prepared, not yet deployed

The integrated frontend passes370 tests. TypeScript, focused lint, provenance/manifest checks and the release-record tests pass. Disposable PostgreSQL tests cover finance evidence immutability, public roles and views, versioned publication, source invalidation, and the exact legacy repair with complete rollback after an injected final-insert failure.

Migrations148 and149 are prepared. Their September6 read-only production preflight found neither applied. The finance import and guarded legacy correction have not yet been run against production. A new isolated schema rehearsal, generated database types, main-branch checks, bounded migration application, data reconciliation, browser verification and production attestation remain required.

## Financial operation

Vercel's connected team reports the Hobby plan. No billing or payment-account changes were made. The support page uses the Ko-fi URL already recorded in the repository; its external checkout was not independently exercised. Voluntary donations are expressly permitted by [Vercel's fair-use guidelines](https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage), checked September6. Paid products or advertising require a separate hosting/billing decision. No paid model calls, subscriber broadcasts or outreach were initiated by this release work.
