# Richmond Commons: current implementation plan

Updated October 4, 2026. This is the active plan; earlier sprint experiments remain historical context.

## Current priority: free basic service and a complete local archive

The operator declined the recurring hosting cost and then clarified the intended outcome: keep the smallest useful free site updating, group the rest into reversible feature tiers, and provide a local edition with the retained records and tools. This supersedes an immediate full public relaunch and the proposed database deletion. Keep the original hosted database intact until a compact replacement and recovery are verified; no deletion is currently authorized. Do not change GoodJobber or shared organization billing.

The public site is paused, ingestion and delivery workflows are disabled, and model spending is locked. Complete local backups of the database, source documents and provider configuration were verified on October 4. The local restored runtime is isolated from cloud credentials. Default public profile is `basic_public`; the localhost profile is `local_archive`. The shared catalog is [feature-tiers.json](../web/src/data/feature-tiers.json); the web route boundary and Python refresh policy consume it. Optional local AI and funded cloud AI remain disabled pending dependency, quality and budget checks. A tier change never removes data or silently resumes a paused provider, job or delivery.

Basic refresh covers deterministic agenda acquisition, keyword tags, and electronic campaign assertions. Existing votes remain available with source-review holds; new structured votes require reviewed extraction, and reviewed paper finance snapshots retain their dated partial coverage. Full source documents and private records belong in the local archive, outside a free public database's storage budget. The public cutover must prove compact PostgreSQL size, import/search/record behavior, a narrow updater and displayed freshness before retiring the old paid Richmond project. Until that cutover, the hosted database continues to incur its existing charge; taking the site offline alone does not remove it.

## Active product direction: search-first relaunch

The operator approved streamlining Richmond Commons around agenda items, their tags, recorded votes, and campaign donations. Meeting order remains an optional way to browse. Search is the main entry. Build a private staged replacement using the existing data and infrastructure, with a public-release target no later than November 3, 2026. This target is not an automatic future deployment instruction.

The implementation and release sequence is in [the October relaunch plan](plans/2026-10-03-search-first-relaunch.md). The current branch stages Search / Meetings / Money, exact agenda-item detail links, and source-backed campaign records. Preserve the underlying source records, schemas, ingestion jobs, and recoverable legacy routes; remove navigation breadth before retiring data or pipelines.

The staged experience is private and read-only. It has no operator session probes, analytics, feedback forms, subscription enrollment, email sends, model calls, billing, or account creation. Its production database access uses the existing public anonymous read configuration. A narrow staged-preview guard, the project's own password-only form with a short-lived HttpOnly cookie, noindex metadata, and denied mutation routes are separate controls; noindex alone is not privacy. Do not provision a Supabase preview branch, add a service, apply a migration, or increase a spending cap for this relaunch preview.

True natural-language search is part of the relaunch goal. The first preview supports explicit submitted searches and bounded, deterministic interpretation of supported questions; it does not yet establish arbitrary semantic understanding or produce generated research answers. Validate topic retrieval and exact vote/finance queries against the original sources before extending those claims.

Five free generated research queries per person per month, followed by prepaid credits, is a proposed cost-recovery policy to validate. Ordinary record access, meeting browse, filters, and source links stay free. No paid-query balance, payment account, price, or automatic reload is implemented or authorized by the staged prototype. Measure inference and hosting costs separately, validate the charging unit and demand, and make any payment-account or billing decision concrete before enabling purchases. The existing zero-new-spend constraint below remains in force.

## Operating cost constraint

The operator made free operation a hard constraint on September 9: identify recurring charges and reduce the site to free service tiers wherever feasible. A substantially cheaper paid option is a fallback to present with its exact ongoing cost and tradeoffs, not an assumed budget. The project should not require recurring personal subsidy before revenue or donations justify it.

Cost investigation and reduction take priority alongside completing the existing resident experience. Do not add paid services, paid preview databases, plan upgrades, automatic credit reloads, or higher model-spending caps. Prefer local verification, existing free services, bounded background work, and cached public pages. Existing capped spending is not permission to increase it.

Verify the actual provider, account, invoice line items, and current usage before attributing a charge or claiming savings. Distinguish a free-tier quota problem from a paid invoice, account-wide usage from this project's usage, and historical measurements from the current deployment. Preserve source records and a tested recovery path before any storage reduction or service migration. Prepare a concrete, verified transition before a billing change that affects availability or data retention; do not downgrade an oversized production database blindly.

## Authority and boundaries

The operator accepted the September 6 project review and instructed: “Spot on! Let's do it all! … otherwise I am happy to completely delegate this to you.” This authorizes implementing, testing, merging, applying bounded migrations, and deploying the reviewed Richmond resident, election, finance, and operator-workflow improvements. It supersedes the S29 baseline/treatment publication dependency and repetitive per-label, per-commit-message, and exact-SHA human approval rituals for this work. Do not request those approvals again. Keep the technical exact-source, CI, target, provenance, budget, and rollback-compatibility checks.

Human judgment remains appropriate for unresolved identity conflicts, consequential unsupported claims, disputed corrections, a material new editorial position, payment-account or billing choices, and work outside the accepted scope. Evidence must precede publication; automated extraction is not independent confirmation. Migration 134 remains prohibited.

On September 6, the operator explicitly answered “Yes” to one digest test at the already configured private canary destination and, after verification, ongoing Monday delivery to currently eligible opted-in subscribers. This authorizes the paired workflow/code/copy activation, its verified deployment, and the bounded delivery rollback described in the activation proposal. It does not authorize outreach, imported recipients, enrollment or preference changes, a new sender or canary address, billing changes, or unreviewed content. Do not ask for the same email authorization again.

The representative canary must use the completed August 31–September 6 UTC publication week, available from September 7 at 00:00 UTC (September 6 at 5 p.m. Richmond time). The planned subscriber schedule is Monday at 16:30 UTC (9:30 a.m. PDT / 8:30 a.m. PST). Prepare and test activation before the canary, then activate only after its exact provider result and content are verified. Preserve one canary attempt and stop on ambiguity; a new run or a changed idempotency key is not a substitute for investigating the existing attempt.

## September delivery context

The following records the September scope. The October relaunch sequence above now leads product work; source integrity and the operating-cost constraints remain prerequisites.

1. Restrict private operator tables and public reference-table writes; verify effective anonymous permissions in an executable database test.
2. Preserve finance source assertions, correct contributions-made direction, replace destructive fuzzy deduplication with explicit reconciliation, and discover local independent-expenditure reports and amendment lineage.
3. Ship a useful November municipal guide, an explanation-led home, three continuing issue histories, exact agenda-item links, and a versioned operator review inbox.
4. Connect validated changes to public briefs and existing subscriptions. Show source coverage and uncertainty instead of guessed completeness. Add a simple passive support route; keep civic facts free.
5. Build sponsor lookup and follow-through views on the same evidence model. Defer broad archive regeneration, generalized chat, other cities, and paid membership infrastructure until usage justifies them.

Use the existing Python, PostgreSQL/Supabase, Next.js, and GitHub Actions stack. Fetch and parse outside short persistence transactions. Cache compact public projections. Reconcile changed source cohorts, preserve raw artifacts, and bound retries and model spending.

### Anderson's campaign reports

The operator specifically requested useful financial information in place of “Paper reports not indexed.” The September 6 source review recovered four distinct 2026 period totals totaling $54,303 through June 30, a $13,423 June 30 cash balance, 14 payments and four later-filed donation notices. Two of those notices concern May receipts. The printed $73,300 running total includes $18,997 reported for 2025. Publish the dated reported figures and their original sources with these distinctions; unresolved donor attachments do not support a complete donor ledger or small-donor percentage.

Use a versioned public snapshot, preserve exact original PDFs privately, and check for changed sources in the existing daily finance job. Prepare source pages and bounded financial candidates for the operator inbox. Generic queue approval records a judgment; publishing revised amounts still requires a source-checked snapshot change and release. This avoids a new database service or paid OCR dependency. Stop the legacy importer from treating unread donor rows as verified small donations. See [source audit](research/2026-09-06-anderson-source-audit.md) and [review runbook](paper-finance-review.md).

## Release record

Before each release, record the exact source SHA, the previous production deployment, included commits, required database changes, CI proof, and public verification. A successful merge is not a deployment; a successful build is not a verified data repair. Never expose operator evidence or credentials in a public release note.

Initial production observed September 6: `0ff9fd50443d8d13e15a4d83845b2997cfc1054a`, deployment `dpl_3Fit9sx7D97BgAbA3iqsRfbjSfUp`. Remote main was `dff3099d8420da236248640eca3f6aee5ef35ac6`. These are observations, not permanently current state.

## Success measures

A resident can identify the next relevant decision and find its source; money totals reconcile to explicitly covered source reports; new filings and revised agendas produce useful updates; corrections remain replayable. Measure weekly operator attention and development spending separately from hosting and production inference. Initial election-pilot attention target: 15–30 minutes weekly, to be measured rather than promised.
