# Richmond Commons: current implementation plan

Updated September 6, 2026. This is the active plan; earlier sprint experiments remain historical context.

## Authority and boundaries

The operator accepted the September 6 project review and instructed: “Spot on! Let's do it all! … otherwise I am happy to completely delegate this to you.” This authorizes implementing, testing, merging, applying bounded migrations, and deploying the reviewed Richmond resident, election, finance, and operator-workflow improvements. It supersedes the S29 baseline/treatment publication dependency and repetitive per-label, per-commit-message, and exact-SHA human approval rituals for this work. Do not request those approvals again. Keep the technical exact-source, CI, target, provenance, budget, and rollback-compatibility checks.

Human judgment remains appropriate for unresolved identity conflicts, consequential unsupported claims, disputed corrections, a material new editorial position, payment-account or billing choices, and work outside the accepted scope. Evidence must precede publication; automated extraction is not independent confirmation. Migration 134 remains prohibited.

On September 6, the operator explicitly answered “Yes” to one digest test at the already configured private canary destination and, after verification, ongoing Monday delivery to currently eligible opted-in subscribers. This authorizes the paired workflow/code/copy activation, its verified deployment, and the bounded delivery rollback described in the activation proposal. It does not authorize outreach, imported recipients, enrollment or preference changes, a new sender or canary address, billing changes, or unreviewed content. Do not ask for the same email authorization again.

The representative canary must use the completed August 31–September 6 UTC publication week, available from September 7 at 00:00 UTC (September 6 at 5 p.m. Richmond time). The planned subscriber schedule is Monday at 16:30 UTC (9:30 a.m. PDT / 8:30 a.m. PST). Prepare and test activation before the canary, then activate only after its exact provider result and content are verified. Preserve one canary attempt and stop on ambiguity; a new run or a changed idempotency key is not a substitute for investigating the existing attempt.

## Delivery order

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
