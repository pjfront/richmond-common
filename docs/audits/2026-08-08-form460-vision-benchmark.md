# Richmond Form 460 image-summary benchmark — 2026-08-08

## Decision

Allow `gpt-5.6-luna` as the sole second OpenAI chat exception, limited to the
bounded summary-page extraction path for image-only Form 460 filings. This does
not change the DeepSeek-first text route. It does not route full contribution
extraction, any other NetFile work, or any other product feature to OpenAI.
Missing credentials fail closed and leave the filing retryable. Kimi remains an
explicit optional vision route, not a fallback selected with another provider's
credential.

At benchmark time the local environment had an OpenAI credential and no
Moonshot/Kimi credential. Luna was therefore the only configured inexpensive
vision option eligible for a paid comparison. No secret value was displayed.

## Representative Richmond cohort

Both inputs are Tier 1 official NetFile filings for Richmond, California:

- [Filing 217094857 — Anderson for Mayor 2026](https://netfile.com/Connect2/api/public/image/217094857), seven image-only pages. The official summary and Schedule A arithmetic establish `$7,993 + $1,147 = $9,140`; the scanned Schedule A amount overlay is visibly shifted.
- [Filing 217098289 — Black Men & Women PAC](https://netfile.com/Connect2/api/public/image/217098289), five image-only pages. The official summary reports `$5,000` monetary contributions and `$5,000` total contributions for both the period and cycle.

The benchmark used `detail=original`, at most six rendered PNG pages, thinking
disabled, a 2,000-token output ceiling, tool-required structured output, and the
hard event cap `RICHMOND_EVENT_BUDGET_USD=0.50`. OpenAI documents Luna image
input at `detail=original` using exact 32-by-32 pixel patches; the router now
reserves that patch count plus a conservative text/framing margin before each
call. See the official [Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
and [vision guide](https://developers.openai.com/api/docs/guides/images-vision).

## Exact outputs

All amounts are dollars.

| Field | 217094857 | 217098289 |
|---|---:|---:|
| Period | 2026-05-29–2026-06-30 | 2026-01-01–2026-06-30 |
| Monetary, period / cycle | 9,140 / 73,300 | 5,000 / 5,000 |
| Loans, period / cycle | 0 / 0 | 0 / 0 |
| Nonmonetary, period / cycle | 0 / 0 | 0 / 0 |
| Total, period / cycle | 9,140 / 73,300 | 5,000 / 5,000 |
| Schedule A itemized / unitemized | 7,993 / 1,147 | 5,000 / 0 |

The final controlled run matched every expected field for both filings. The
validator independently enforces the printed FPPC identities: Schedule A Lines
1 + 2 = Line 3 / Summary Page monetary contributions, and monetary + loans +
nonmonetary = total. Negative Schedule A corrections remain valid; official
Richmond filing 216805176 is the regression case (`-$100 + $0 = -$100`). A Luna
response that fails deterministic arithmetic receives at most one correction
pass; other routes and failure types do not gain a retry.

## Attempts and spend

The event ledger is the source of truth. Five settled calibration/benchmark
calls were made: three for the shifted Anderson filing and two for the PAC. The
early Anderson results were rejected while the prompt and deterministic
arithmetic guard were tightened; no rejected result was persisted.

| Reservation | Filing / result | Preflight estimate | Actual |
|---|---|---:|---:|
| `5b239555-1c9f-48eb-bba2-a7877a67bb5d` | 217094857, calibration rejected | $0.00569260 | $0.00291160 |
| `2717184f-d687-43c7-a725-982f7a7b2764` | 217098289, paired calibration | $0.00524460 | $0.00246980 |
| `ef981982-057d-46e1-8feb-594b23049780` | 217094857, arithmetic rejection | $0.00577960 | $0.00292600 |
| `de374f89-adb3-405c-bbcd-556494193859` | 217094857, exact final output | $0.00585020 | $0.00291600 |
| `f2c9c6fa-3ebc-4daf-9918-3174b5bedf1d` | 217098289, exact final output | $0.00540200 | $0.00249820 |
| **Benchmark total** | **5 calls** | **$0.02796900** | **$0.01372160** |

Actual experimental spend was **$0.01372160**, or 2.75% of the authorized
$0.50 maximum. The final exact two-filing run itself cost $0.00541420.

## Targeted production redrive proof

The separately capped redrive event
`calaccess-form460-vision-redrive-20260808` settled three Luna calls at an
estimated $0.01709600 and actual **$0.00835460**. Benchmark plus redrive actual
spend was **$0.02207620**.

The completed reconciliation log is
`482b6361-fc1a-4a36-9ab1-20f594e8eaa9`: 62 filings examined, 32 UNI rows
synthesized, `$223,231.36` synthesized, 21 already matched, nine over-form
review cases, zero pending summaries, and durable/cache-complete flags true.
The pre-redrive log `f178e385-e026-4c8b-ab6c-42e287260c92` recorded both
filings as retryable-incomplete because `MOONSHOT_API_KEY` was absent. There is
no matching `source_change_jobs` dead-letter row or pending-decision row; the
failure obligation lived in reconciliation metadata. The final completed log
has `incomplete_count=0`, `form460_summaries_pending=0`, and
`retryable_incomplete=false`, which is the terminal redrive proof.
For the two targets:

- cache: 0 rows before (empty MD5 `d41d8cd98f00b204e9800998ecf8427e`), 2 rows after (MD5 `02be67fa1a1c260242ec2beb9f6a0867`);
- contributions: 0 target rows before; after, one `$9,140` UNI row for
  217094857 and one `$5,000` UNI row for 217098289;
- Richmond UNI state: 25 rows / `$204,662.18` / MD5
  `2d214a7ea47ab90a67b6acfebe988dd4` before, and 32 rows / `$223,231.36` /
  MD5 `620abecd42f35d36c858234eadb3da27` after.

A read-only set difference between the recoverable pre-redrive production clone
and production proves the exact seven-row / **$18,569.18** net increase. All
seven use contribution date 2026-06-30:

| Filing | Amount | Committee ID | Committee |
|---|---:|---|---|
| 217061696 | $1,000.00 | `208ff284-6b72-4bf6-b8cb-5c5e754db296` | Independent PAC Local 188 International Association of Firefighters |
| 217094857 | $9,140.00 | `fc05300e-7848-4253-b0d4-56a8a6e71c42` | Anderson for Mayor 2026 |
| 217098289 | $5,000.00 | `a3aeae7e-73da-404d-8cfd-1374d3ace233` | Black Men and Women PAC |
| 217112024 | $2,974.18 | `83ca3946-1a97-49b6-9bf0-3ac3fcd5b384` | Cesar Zepeda for Richmond City Council 2026 |
| 217136030 | $345.00 | `2879140a-b423-452d-9711-0656c38962e8` | Vote Sue Wilson for 2024 Richmond City Council District 5 |
| 217136864 | $105.00 | `67296c98-1b35-4bf8-9cd6-81f797c12e09` | Claudia Jimenez for Mayor of Richmond 2026 |
| 217150089 | $5.00 | `55cda928-3c2a-48ba-a187-1116b3e5841c` | Jamin Pursell for City Council 2026 |

The two target filings account for $14,140.00; the five non-target summaries
account for the remaining **$4,429.18**. This was one full atomic
reconciliation, not seven independent inserts: the implementation computes and
validates the complete replacement set before the delete, deletes the prior UNI
cohort once, loads all replacements with internal commits disabled, and calls
`commit()` once; any exception calls `rollback()`. All 32 resulting rows also
share the transaction timestamp `2026-08-09T00:10:23.113999Z`.

The PAC was linked to the official filer ID `961580` through a conditional new
committee row. It was not merged with the distinct historical committee filer
ID `941580` (14 contributions from filing 775799 in 2001).

## Boundary

Production remains DeepSeek-first. Luna may be selected only for (1) the
previously benchmarked failed-negated-motion explainer case and (2) this
image-only Form 460 summary call site. Any third OpenAI chat route or broader
Kimi route requires its own representative Richmond benchmark and operator
approval.
