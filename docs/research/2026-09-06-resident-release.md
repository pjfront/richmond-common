# Resident experience release, September 6, 2026

This implements the operator-approved Astra plan: a useful homepage, a small set of source-checked issue histories, and clear election/participation paths. The historical S29 metadata and sitemap hold is superseded for this release. It does not publish held campaign directories or operator material.

## What ships

- Homepage: What changed, Coming up, November choices, and routes for residents new to local government.
- `/stories` and three stable dossiers: Chevron settlement/city budget; the fire-station bond; Flock cameras/data privacy.
- English/Spanish core explanations with language retained through client navigation. Imported agenda titles and official sources remain in their original language. Explanations disclose AI authorship and the September 6 source check.
- Specific source boundaries: the Chevron announcement is not a payment receipt; the budget is not completed spending; Resolution 143-26 places a $120 million maximum bond before voters, requiring two-thirds approval; March 17 minutes record a 4–3 direction to negotiate a Flock amendment, not a verified signed contract.
- Responsive navigation, keyboard skip link, semantic mobile disclosure, clearer search scope, source and correction links with readable text and tap targets; topic results now link to exact agenda-item pages.
- Reviewed public metadata/JSON-LD and bounded sitemap discovery enabled. `/support` and the November guide are supplied by the integration branch.

## Data and operating boundaries

`web/src/data/civic-stories.ts` contains the dated, source-checked initial context and reviewed topic phrases. New agenda entries never rewrite those outcomes or infer political positions. Related Chevron/budget entries explicitly do not establish project funding. New factual briefs can be added by the separate approval workflow.

One shared hourly cache reads at most 16 recent and 6 upcoming non-cancelled Richmond council meetings and 1,000 active agenda rows. Shared source identities are deduplicated; same-date meetings are not assumed identical. A row-limit warning appears at the cap. Agenda matching is a bounded discovery aid, not a complete history. It makes no model calls. Errors escape the cached loader so failed refreshes cannot replace usable data with an apparently successful empty list; the UI explicitly distinguishes unavailable records from no matching titles.

## Verification

- TypeScript check and targeted ESLint pass.
- 40 tests across resident source/query/journey checks, sitemap/metadata, and existing public-containment/accessibility cases passed before final small copy/cache-limit adjustments; final changed-path tests rerun for the commit.
- Browser: real anonymous reads at localhost:3004; homepage and story detail loaded without browser errors. Desktop 1280px, mobile 375px, and 640px reflow had no horizontal overflow. Spanish translated core explanations and stayed selected when following All stories.
- The June 23 operating-budget agenda link resolved to `/meetings/2cfd2dd4-c596-497f-9a15-bedc4fdb0b32/items/o.1`, showing the exact item and official-agenda route.
- The current imported window had 16 recent and zero upcoming council meetings. The homepage consequently directs residents to the city's official calendar; it does not claim no meeting is scheduled.

Primary source URLs and their exact event associations are maintained in the seed data file. No production writes, schema changes, paid model calls, push, or deployment were performed in this subtask.
