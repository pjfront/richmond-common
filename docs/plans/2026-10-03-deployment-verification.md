# October 3 deployment and verification record

Recorded October 3, 2026, in the operator's America/Los_Angeles calendar. This separates the completed production access fix from the private search-first preview. It is not an instruction to publish the relaunch automatically. The remaining product work follows [the relaunch plan](2026-10-03-search-first-relaunch.md).

## Production access fix: verified live

| Field | Verified value |
|---|---|
| Production source SHA | `2124943a2718b18669741eb9fbd51e9d0d63ae21` |
| Production deployment | `dpl_4eo4fCU6v9NuepfSNzPKqrh2zYDw` |
| Prior deployment | `dpl_5RcPGXw5DcGknWgcysMsRGfP3qbG` |
| Project SSO protection | Restored to `all_except_custom_domains` |

Live checks on the custom production domain established:

- An anonymous request to `/` returns HTTP 401 and the site's own single-password form, with no Vercel login redirect and no `WWW-Authenticate` header.
- A wrong password returns HTTP 401. The correct password returns HTTP 303 and a seven-day session cookie with `HttpOnly`, `Secure`, and `SameSite=Strict`.
- An authenticated root request returns HTTP 200 with private, no-store caching.
- A protected asset returns HTTP 200 with the site session and HTTP 401 without it.
- Anonymous health output is minimal and does not expose the protected application.

These checks establish the access fix; they do not establish that the search-first relaunch is public. The previous deployment identifier is retained for release traceability. Do not assume that reverting to it preserves the application password gate.

## Private search-first preview: verification slice

| Field | Recorded value |
|---|---|
| Branch | `codex/commons-search-stage` |
| Initial preview source SHA | `fae5dbfba3027f3be4b2a5c5f3f2cea630165783` |
| Initial READY deployment | `dpl_EKrrEALaktR8ivcjBFx3NgzVuKRd` |
| Source-review hold preview SHA | `c0663bc49d53d00277599f653b99f9ecfbc7ab2b` |
| Source-review hold READY deployment | `dpl_8VxP92p1ZDGwDasxnwnEGaMPkFjn` |
| Final preview source SHA | Recorded with the completed hosted verification in [draft PR 210](https://github.com/pjfront/richmond-common/pull/210) |
| Final preview deployment | Recorded with the completed hosted verification in [draft PR 210](https://github.com/pjfront/richmond-common/pull/210) |

The recorded verification slice passed a full frontend build, 964 web tests, 140 Python tests, 41 manifest checks, and 10 focused checks. These results belong to the tested slice; they must not be presented as proof for a later source SHA without checking the changed scope.

Desktop browser checks used real records and confirmed:

- Housing search returned ten sourced 2026 agenda items, and an exact item-detail link opened successfully.
- Point Molate vote search rendered the recorded votes and their disclosures.
- Money browse showed a 1,424-record index and a source-linked page of 25 records.

The subsequent source-review hold passed 974 web tests, TypeScript, changed-source lint, 51 combined manifest/operator/release checks, and a fresh full build. Browser verification confirmed the known J-2 item remains reachable from vote search, displays its official text and page-9 minutes link, and withholds the disputed motions, names, outcomes and generated summaries before page props.

The preview uses the same source data and infrastructure with a read-only application surface. Its custom password gate remains separate from Vercel access protection. Store neither the password nor native Vercel share/bypass tokens in this document.

Fresh hosted HTTP verification of the source-review hold deployment confirmed its deployment-specific private entry reaches the custom password prompt without a Vercel login. Password entry reaches the staged root; money and search reads return HTTP 200; an unsupported POST is denied; robots disallows crawling and the sitemap is empty. All CI checks for that source passed. The private link and password are stored outside the repository.

## Incremental question and accessibility slice

The form now preserves automatic question routing and inferred-year behavior across submissions and pagination. Supported common question wrappers disclose the chosen record kind and filters; unsupported tally, causality, voter-choice and complex-date questions remain explicitly keyword-only. A request outside the finance activity window is distinguished from an absence of reported activity. The [question coverage matrix](../research/2026-10-03-search-question-coverage.md) records tested contracts and source gaps separately.

Isolated headless Chromium with an explicitly selected installed executable provided actual responsive checks, replacing the earlier ineffective viewport override. Home, first search results and money records measured `innerWidth=320`, `clientWidth=305`, `scrollWidth=305` with zero horizontal-overflow nodes, including long committee names. The 15px difference is the vertical scrollbar. Search and money also passed 640px reflow. Labels and 44px form controls, committed-result focus with a visible outline, Tab navigation, and a 48px-high skip link that focuses main content were checked. Source and coverage body text now use 16px, with stronger control borders. Screenshots are retained in the local task visualization directory.

The attempted browser zoom shortcuts left `devicePixelRatio=1` and the viewport unchanged. A 640px viewport check is useful reflow evidence but is **not** an actual 200% browser zoom pass. Final source, CI and hosted verification for this incremental slice are recorded in PR 210 when completed.

Local validation passed 1,011 web tests across 116 files, TypeScript, changed-source lint, 45 manifest/release-phase Python checks, and the full build. After moving the shared finance window constants into the pure finance library, 40 affected finance/query tests and the build passed again. Desktop browser checks of the updated flow returned ten sourced housing items for the supported housing question, 220 indexed cash-contribution matches for the supported Jimenez recipient question, an explicit outside-window warning for 2025, and sixteen retrieved 2010 Point Molate items with the disputed J-2 votes held. These counts describe the checked index/retrieved set, not complete real-world activity or independently verified totals.

## Holds before a release claim

- Keep the held 2010 vote data withheld until a separately validated source repair establishes the correct identities and motion states. The private presentation hold is complete; it does not repair the database.
- Complete actual 200% browser zoom checks before public release. Actual 320px and 640px reflow checks now pass for the staged home, search and money paths.
- Validate broader natural-language retrieval and exact structured vote/finance questions against their original sources. The current bounded question patterns do not establish unrestricted natural-language search.
- Validate costs, the chargeable query unit, and credits policy before implementing payment or claiming working billing.

The public relaunch target remains November 3, 2026. Publication stays deliberate and manual; unresolved core verification produces an explicit hold rather than an automatic launch.
