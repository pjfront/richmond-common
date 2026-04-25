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

---

## Richmond City Council (current term)

**Eduardo Martinez** — Mayor

**Cesar Zepeda** — Vice Mayor, District 2

**Jamelia Brown** — Councilmember, District 1
- Often misheard as: Jamilia, Jamelya

**Doria Robinson** — Councilmember, District 3
- Often misheard as: Doria, Dorea

**Soheila Bana** — Councilmember, District 4
- Often misheard as: Sohaila, Sohela, Banna

**Sue Wilson** — Councilmember, District 5

**Claudia Jimenez** — Councilmember, District 6
- Often misheard as: Hemenez, Hymenez

---

## Former Richmond officials (mentioned in historical context)

**Tom Butt** — Former Mayor (2015-2022), longtime councilmember before that

**Gayle McLaughlin** — Former Mayor (2007-2015)

**Ben Choi** — Former Councilmember

**Jovanka Beckles** — Former Councilmember
- Often misheard as: Jovonka, Joanka, Beckless, Beckless

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

## To verify / add (placeholders)

These names appear in recent transcripts but spelling is uncertain.
Operator: please verify and update. Until verified, the model may use
phonetic transcription which could be wrong.

- *Fire Chief Osorio* — appears in 4/21 paramedic discussion (verify)
- *Finance Director* — surname uncertain (transcribed "Combmes" — likely
  "Coombes" or similar)
- *Police Chief* — current chief's name (verify)
- *City Manager* — current city manager's name (verify; transcribed
  "Shasa Curl" in some past content but verify spelling)

---

## Maintenance

This file is hand-curated. To add a name:

1. Edit this file directly. Keep entries in canonical alphabetical or
   role-based order within each section.
2. Commit. AI-delegable maintenance — same enforcement pattern as
   PARKING-LOT and pipeline-manifest.

A separate sync script (future: `src/sync_canonical_names.py`) can
auto-pull current Richmond officials from the `officials` DB table and
keep the "Richmond City Council (current term)" section in sync. For
now, manual edits are fine — the council changes rarely.

When a name first appears in a recap and gets misspelled, add it here
in the same commit that fixes the recap. That way the next regeneration
spells it right and the misspelling can't recur.
