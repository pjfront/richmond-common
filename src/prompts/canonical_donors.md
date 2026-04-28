# Canonical Donors — Richmond Civic Donor Vocabulary

This file is the **authoritative entity-name reference** for donors that
appear in campaign-finance data, especially paper-filed Form 460/497 PDFs
extracted via Claude Vision OCR. Vision-extracted text frequently varies
the wording of the same legal entity from one filing to the next:

- "Richmond Police Officers Association" → "Richmond City Police"
- "International Association of Firefighters Local 188" → "Independent PAC Local 188 International Association of Firefighters"
- "SEIU Local 1021 Candidate PAC" → "S.E.I.U. Local 1021"

Without canonicalization, the same legal entity ends up under multiple
`donors.id` rows, breaking dedup, breaking influence-map graph edges,
and inflating "unique donor" counts in filing-period briefings.

This file is parsed by `src/canonical_donors.py` into an alias→canonical
mapping applied at contribution load time, in `db.load_contributions_to_db`,
for any row where `source='city_clerk'` (which collapses both NetFile API
and FPPC paper filings — paper-vision rows are the ones that need it,
but applying uniformly is cheap and prevents new aliases from leaking in).

When adding a new entity:
- Use the EXACT canonical name as the entry header (matched on the
  legal-entity name — usually the FPPC-registered committee name).
- Note the entity type (PAC, union, corporation, individual, advocacy).
- List variants under "Aliases:" as `; `-separated strings, lowercase
  comparison is case-insensitive.

The parser collapses leading/trailing whitespace and is strict about
exact-match (no substring fuzz) — keep aliases comprehensive.

---

## Public-Sector Unions

**Richmond Police Officers Association PAC** — Police union PAC
- Aliases: Richmond Police Officers Association; Richmond P.O.A.; Richmond POA; Richmond Police Officers Assoc; Richmond Police Officers Assoc PAC; Richmond Police Officers Assn; Richmond Police Officers Assn PAC; Richmond City Police; RPOA; RPOA PAC; Richmond Police Officers Association Independent Expenditure PAC; Richmond Police Officers PAC; Richmond Police Officers PAC#951606; Union Members' Dues. Richmond Police Officers Association is the intermediary for all contributions.

**International Association of Firefighters Local 188** — Firefighters union local
- Aliases: IAFF Local 188; Firefighters Local 188; IAFF 188; International Association of Fire Fighters Local 188; Independent PAC Local 188 International Association of Firefighters; Independent PAC Local 188 IAFF; Local 188 International Association of Firefighters; International Assoc. Firefighters Local 188 Independent PAC; International Association of Firefighters Local 188 Independent PAC; International Assoc Firefighters Local 188

**SEIU Local 1021 Candidate PAC** — Service workers union political committee
- Aliases: SEIU 1021; SEIU Local 1021; S.E.I.U. Local 1021; Service Employees International Union Local 1021; SEIU 1021 PAC; SEIU 1021 Candidate PAC; SEIU Local 1021 PAC

**United Teachers of Richmond** — Richmond teachers union
- Aliases: UTR; United Teachers Richmond; United Teachers of Richmond Association; West Contra Costa Teachers Association; United Teachers of Richmond PAC

**Operating Engineers Local 3** — Construction operators union
- Aliases: IUOE Local 3; Operating Engineers 3; International Union of Operating Engineers Local 3; Operating Engineers Local Union No. 3

---

## Corporations & Industry PACs

**Chevron Richmond** — Refinery operator (Chevron Corporation)
- Aliases: Chevron; Chevron Corporation; Chevron USA; Chevron U.S.A. Inc.; Chevron Products Company; ChevronTexaco; Chevron Richmond Refinery

**California Apartment Association PAC** — Landlord industry PAC
- Aliases: CAA PAC; California Apartment Association; CAA-PAC; CAA Issues PAC

**California Real Estate PAC** — Realtors industry PAC
- Aliases: CREPAC; CARPAC; California Association of Realtors PAC; CAR PAC; California REALTORS PAC

---

## Coalition & Issue PACs

**Richmond Working Families** — Progressive coalition PAC
- Aliases: Richmond Working Families PAC; Working Families Richmond

**East Bay Working Families PAC** — Regional progressive PAC
- Aliases: East Bay Working Families; East Bay Working Families Political Action Committee

**Building Trades Council** — Construction trades coalition
- Aliases: Contra Costa Building & Construction Trades Council; Contra Costa Building Trades Council; Contra Costa Building and Construction Trades Council; Building Trades Council Contra Costa

---

## Notes for Maintainers

This list is **not exhaustive**. It covers the entities most affected by
Vision OCR drift on paper-filed Richmond mayoral candidates' Q1 2026
forms (the originating use case for I124, 2026-04-28). When the
filing-period-briefing test fixture (`tests/test_filing_period_briefing.py`)
diverges from the Richmondside article ground truth in a "donor count
too high" direction, the most common cause is a missing alias here.

**Adding new entities:** just append the entry. Re-running
`python src/load_paper_filings.py` re-applies canonicalization to all
existing paper-filed rows; no migration needed.

**Removing entities:** do not — once an alias is canonicalized into a
donor row, removing the alias entry breaks the lookup but doesn't undo
the existing row. If an entry is wrong, fix the canonical name in place
and re-run the loader; the donors table will pick up the renamed entity
on the next load.
