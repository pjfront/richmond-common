# Public numbers and methodology audit — September 6, 2026

The two Claudia Jimenez screenshots exposed a broader failure: multiple layers independently converted incomplete or differently scoped records into authoritative-looking totals. This change removes those competing public calculations and keeps dated records and checked source summaries.

## Findings and corrections

| Finding | Correction |
| --- | --- |
| The historical finance view showed $132,617, two donor counts (208 and 203), uneven lifetime rankings and duplicated election labels. A campaign committee appeared among people. | Remove lifetime sums, person counts, rankings, guessed cycles and donor grouping. Show individual dated entries with their reported type, committee, amount and original filing. Record-year filters describe actual dates. |
| The former $710 “2026 Election” slice included November 2024–March 2025 records. | No election-year inference from historical receipt dates. Checked 2026 mayoral reports remain separate from council committee history. |
| Cached donor totals, current-cycle charts and recipient aggregates implied reconciled records and resolved identities. | An alphabetical, explicitly selective historical directory and paged source-entry profiles replace the rankings and charts. The old $5,000 eligibility threshold is disclosed as an index-selection rule, not a verified lifetime total. |
| Public candidate cards used incomplete financial coverage to order candidates, describe competition and produce statistics. | The roster reads candidate identities independently of financial data. Reviewed campaign summaries have dated links; one listed candidate does not establish an unopposed race. |
| Stored AI biographies and separately queried statistics contradicted the voting table. Election-history prose inferred reelection and questionable campaigns. | One dated coverage paragraph uses the table's source rows. Remove generated statistical biographies, election-history prose, attendance/majority rates and unequal comparisons. |
| Missing choices became “absent”; repeated vote rows could inflate tallies or motion counts. | Normalize by official identity within each motion. Preserve explicit absence, distinguish unresolved choices and collapse repeated rows. Different motions stay separate. |
| “Most discussed” was a weighted controversy score; one selected motion's result was treated as the agenda item's outcome. | Retire the ranking and redirect its URL to dated split-motion records. Display exact motion text, recorded choices and original sources, distinguishing minutes from tentative transcripts. Private analyses require server authorization before their queries run. |
| Meeting and topic cards ranked AI speaker estimates. Comment rows were called unique people; unknown channels became spoken comments. | Keep agenda order and individual comment records. Count records by ID, show only established channels, identify AI themes and remove estimated comment rankings and generated meeting-wide numeric narratives. |
| Topic detail pages counted calendar dates as meetings, hid a 100-entry limit and showed isolated extracted amounts/comment estimates. | Count distinct meeting IDs within the displayed entries, disclose the newest-100 limit and generated tags/summaries, and remove numeric badges without context. |
| Meeting counts blended stored values, an RPC and a server-capped fallback; failures could become zero votes. | Use one complete RPC count source. A genuinely empty meeting has an explicit zero row; a missing row or failed read is unavailable. Detail lists use complete bounded source reads. |
| Public-records statistics confused closure duration with first response and legal compliance, with competing denominators. | One request collection supplies the list and statistics. Show portal status, closure duration and its valid-duration denominator. Missing duration remains unavailable. |
| Commission seat arithmetic inferred vacancies from incomplete membership records. | Show the source-listed roster and recorded terms. Remove inferred vacancy and aggregate seat headlines. |
| Truncated or failed finance, donor, topic, meeting and request reads could publish convincing partial totals or empty success. | A shared reader requires exact stable counts, stable unique IDs and complete bounded pages; offsets follow actual server response size. Canonical finance keeps its event-specific completeness/provenance checks and rejects missing payloads. |
| Anonymous flag access was broader than the existing visible-current-confidence rule; a definer aggregate bypassed that restriction. | Migration 152 adds a restrictive public eligibility policy, removes public write privileges and aligns the flag-count RPC. Existing source-validity policy and service-role access remain. Authenticated operator context uses its private client only after authorization. |

## Smaller architecture

Retire unused aggregate queries and components instead of adding more comparison adapters. Keep a single complete-read primitive, a single vote-choice/identity normalization path, and a single public-records snapshot. Cache only small topic aggregates for one hour; never persist the full topic corpus in that cache or convert failures into cached empty success. Update the pipeline manifest and operator registry with the removed paths. Validate the existing standalone civic review workflow command explicitly instead of misclassifying it as a missing source registration.

Limit Next.js build workers to two, with one page render per worker, so large developer machines do not multiply concurrent prerender reads against the shared database. These are installed Next 16.1.6 build settings, not request-serving limits. Local verification encountered a sitemap statement timeout and a separate Windows worker crash with 27 workers; two workers alone still allowed 16 simultaneous pages and hit a meeting-count timeout. The settings bound build pressure without changing query results or concealing failures. Both affected queries passed isolated reads.

## Validation and release boundary

- Regression coverage exercises server caps, changed counts, duplicate IDs, failures, explicit zeros, unknown dates/channels, repeated motions and authorized/private query boundaries.
- Browser checks cover council finance/votes, dated campaign summaries, meeting discovery/detail, public records, donors and split-motion records at mobile and desktop widths.
- Migration 152 has an exact Supabase mirror and a PostgreSQL role/replay/source-parent/RPC proof in CI. It changes only `conflict_flags` privileges/policy and `get_meeting_flag_counts(text)`; production application must use the committed SQL and record pre/post evidence.
- This release does not change checked campaign amounts, publish pending civic packets, activate email delivery, or apply migration 134.

## Remaining limits

Historical finance entries have not all been reconciled against amendments and committee summary statements. A reported name is not a verified unique person; a raw monetary classification does not prove a payment is new outside cash. Source entries remain visible without deriving those claims. The checked mayoral summaries and typed 2026 records carry their own dated scope.

Complete paged HTTP reads detect visible count/identity drift but are not a transactional database snapshot: a concurrent substitution that preserves counts can escape that check. Published summaries still need source reconciliation. Extraction can omit or misread historical votes and comments; the public UI therefore describes the records available, not complete civic participation or a person's policy position. Item-level generated text remains labeled as generated and is not a basis for the retired numerical rankings.

The private data-quality and freshness endpoints still have different 45/60-day operational thresholds. They are not resident-facing measures of completeness. Consolidating that operator policy can be a separate decision without inventing a new public reliability score.
