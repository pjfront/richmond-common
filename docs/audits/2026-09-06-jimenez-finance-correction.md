# Jimenez campaign finance correction

Public correction to the council profile and November guide, authorized by the operator's report of a misleading $710 “2026 Election” total.

## What the profile actually counted

The historical contribution query selected committees directly linked to the council official. Jimenez's 2020 and 2024 council committees were linked this way; her 2026 mayoral committee, FPPC 1488504, was linked through her candidacies instead. The donor table then guessed election cycles from candidacy dates, using a year as the key. Primary and general election dates produced duplicate keys and the wrong date window.

The eight rows behind $710 belong to the 2024 council committee, FPPC 1467767:

| Donor | Receipt dates | Amount |
| --- | --- | ---: |
| Paul Moore | January 5, 2025 | $335 |
| Janet Johnson | November 9 and December 9, 2024; January 9, February 9 and March 9, 2025 | Five gifts of $50 |
| Roberto Reyes | November 13, 2024 | $100 |
| Ryan Murray | December 5, 2024 | $25 |

These rows contain $225 received in 2024 and $485 in 2025. None was received in 2026. Their original reports are [the July–December 2024 report](https://netfile.com/Connect2/api/public/image/213045787) and [the January–June 2025 report](https://netfile.com/Connect2/api/public/image/214610872). The legacy election foreign keys also incorrectly point to November 2026 and are not used as attribution evidence.

## Correct public presentation

- Historical donation filters use actual calendar years present in the records. Committee names, source reports and receipt dates remain available with the records. No election is inferred from timing.
- The council profile's comparative fundraising and donor rankings are removed. The seven-official query exceeded the default database row limit, and linked-committee coverage differed between officials.
- The current mayoral campaign uses the same checked source summary on the council profile and November guide. Its identity is the exact official/committee linkage, not a similar-name guess or a union of legacy transaction rows.
- The source summary reports $60,365 in cash donations for January–June 2026, $2,000 noncash separately, and $18,655.12 cash remaining June 30. Five separately reported July receipts total $6,000; these do not establish complete post-June fundraising. An August-filed report describes a February receipt and is kept with that earlier date.

The latest [June 30 report, page 3](https://netfile.com/Connect2/api/public/image/217136864#page=3) states these calendar-year cash and noncash totals. Three adjacent, nonoverlapping reporting periods independently sum to $60,365. The May 17–28 report overlaps the later May 17–June 30 report and is not added again. Exact source hashes, amendment metadata and reviewed pages are retained in `web/src/data/jimenez-reported-finance.json`.

## Cross-form cash classification

The previous $68,918 indexed cash subtotal also included a $2,000 Diana Wear entry from Form 497. The amended periodic report identifies the same name/date/value on Schedule C as a noncash payment for speech coaching ([page 16](https://netfile.com/Connect2/api/public/image/216815171#page=16)). The [rapid report](https://netfile.com/Connect2/api/public/image/216668328) does not establish a separate cash receipt. This is a cross-form reconciliation problem, not a reason to edit the original disclosure.

The deterministic reconciliation guard withholds conflicting rapid claims from public cash totals while retaining the periodic noncash record and both original assertions for review. It does not merge ambiguous gifts or infer that every similarly named donation is the same event. The daily finance job uses the same guard and packages the counterpart sources for operator review.

## Boundaries

This correction does not claim the historical donation table is a complete campaign total. It does not repair every legacy election foreign key, merge the mayoral committee's legacy rows, change corporate/union identities, rank campaigns, publish civic briefs, or change subscriber delivery. Migration 134 remains untouched. Source-checked totals retain their reporting dates when newer filings appear; a later report requires a new source check before replacing them.

Verification and deployment receipts are retained locally under this change's `tmp` directory. Do not describe the repair as deployed until the exact reviewed release passes production checks.
