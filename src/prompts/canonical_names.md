# Canonical Names — Richmond Civic Vocabulary

This file is the **authoritative spelling reference** for any name that appears
in AI-generated content (meeting recaps, comment summaries, theme narratives,
orientation previews). Auto-generated YouTube/Granicus captions transcribe
names phonetically, which produces misspellings like "Joya" for "Gioia" or
"Alshshire" for "Aleshire" — those misspellings then leak into our
public-facing recaps unless the model is told otherwise.

When adding a name:
- Use the EXACT canonical spelling as the entry header.
- Note the role/title.
- If the name is commonly mistranscribed, add the phonetic mishearings
  under "Often misheard as:" so the model knows what to map.

This file is loaded into the system prompt of every transcript-derived
generation. Keep it under ~200 lines for token efficiency. When this file
grows past that, split into category files.

The Richmond council and municipal staff sections are kept in sync with the
`officials` and `city_employees` database tables via
`src/sync_canonical_names.py`. External figures (county supervisors, retained
counsel, recurring orgs) are hand-curated below.

---

## Richmond City Council (current term)

**Eduardo Martinez** — Mayor

**Cesar Zepeda** — Vice Mayor, District 2
- Often misheard as: Zapeda, Sapeda, Zepada

**Jamelia Brown** — Councilmember, District 1
- Often misheard as: Jamilia, Jamelya

**Doria Robinson** — Councilmember, District 3
- Often misheard as: Doria, Dorea

**Soheila Bana** — Councilmember, District 4
- Often misheard as: Sohaila, Sohela, Banna

**Sue Wilson** — Councilmember, District 5
- Also appears in payroll as: Suzanne Wilson (formal/legal name)
- Often misheard as: Susan Wilson

**Claudia Jimenez** — Councilmember, District 6
- Often misheard as: Hemenez, Hymenez, Himenez

---

## Richmond Municipal Staff (current, FY2026)

Auto-synced from `city_employees` table. Source: City of Richmond payroll (Socrata dataset `crbs-mam9`).

**Shannon Moore** — City Attorney

**Pamela Christian** — City Clerk
- Often misheard as: Pam Christian, Pamala

**Kinshasa Curl** — City Manager
- Often misheard as: Shasa, Kenshasa, Kinshaza

**Heather McLaughlin Westmoreland** — Senior Assistant City Attorney
- Often misheard as: McGloughlin, Mcgloflin

**Patrick Seals** — Administrative Chief (City Manager's office)

**Robert Armijo** — Deputy Director of Public Works / City Engineer
- Often misheard as: Armeho, Armeeho, Armiho

**Lina Velasco** — Director of Community Development (Planning & Building)
- Often misheard as: Lena Velasco, Velasko, Velazco

**Nannette Beacham** — Director of Economic Development
- Often misheard as: Nanette, Beechum, Beachum

**Emily Combs** — Director of Finance
- Often misheard as: Combmes, Coombes, Combes, Coombs

**Sharrone Taylor** — Director of Human Resources
- Often misheard as: Sharon Taylor, Sharron

**Sue Hartman** — Director of Information Technology

**Daniel Chavarria** — Director of Public Works
- Often misheard as: Chavaria, Chavarea

**Nicolas Traylor** — Executive Director, Rent Program
- Often misheard as: Nicholas, Nicolaus, Trailor

**Aaron Osorio** — Fire Chief
- Often misheard as: Osario, Osorrio, Asorio

**Bisa French** — Police Chief
- Often misheard as: Beesa, Bissa

**Timothy Simmons** — Police Chief
- Often misheard as: Simons, Simon's

**Charles Gerard** — Port Director

**Lashonda White** — Deputy City Manager (Community Services)
- Often misheard as: La Shonda, La'Shonda

**Nicolina Mastay** — Deputy City Manager (Finance)
- Often misheard as: Nicoleena, Mastey

---

## Former Richmond officials (mentioned in historical context)

**Tom Butt** — Former Mayor (2015-2022), longtime councilmember before that

**Gayle McLaughlin** — Former Mayor (2007-2015)

**Ben Choi** — Former Councilmember

**Jovanka Beckles** — Former Councilmember
- Often misheard as: Jovonka, Joanka, Beckless

---

## Contra Costa County (frequently appears in Richmond meetings)

**John Gioia** — Supervisor, District 1 (Richmond is in his district)
- Pronounced "Joy-ah"
- Often misheard as: Joya, Joia, Joyah

**Federal Glover** — Supervisor, District 5 (former Pittsburg mayor)

**Diane Burgis** — Supervisor, District 3

---

## Common municipal counsel / consultants

**David Aleshire** — Aleshire & Wynder LLP (frequently retained as special counsel)
- Often misheard as: Alshire, Alshshire, Aleshyre, Allshire

---

## Recurring local organizations / committees

**Richmond Police Officers Association (RPOA)** — police union, frequent
public-comment speakers at council meetings

**Aleshire & Wynder** — municipal law firm

**Chevron Richmond** — refinery operator. Disclose funding when referencing
**Richmond Standard** (their owned/funded news site).

**KCRT** — City of Richmond's public-access TV channel; broadcasts and
records council meetings (uploads to YouTube @KCRTTV)

---

## Maintenance

Two parts to this file:

1. **Auto-synced sections** ("Richmond City Council" + "Richmond Municipal
   Staff") are regenerated by `python src/sync_canonical_names.py` from the
   `officials` and `city_employees` DB tables. Run after any council/staff
   change. The sync preserves "Often misheard as:" lines that have been
   curated by hand — only the headers are regenerated.

2. **Hand-curated sections** (former officials, county, retained counsel,
   recurring orgs) are edited directly. Keep entries in canonical
   alphabetical or role-based order within each section.

When a name first appears in a recap and gets misspelled, add the
"Often misheard as:" alias here in the same commit that fixes the recap.
That way the next regeneration spells it right and the misspelling can't
recur. AI-delegable maintenance — same enforcement pattern as PARKING-LOT
and pipeline-manifest sync.
