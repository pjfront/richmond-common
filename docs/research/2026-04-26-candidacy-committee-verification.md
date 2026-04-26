# Candidacy ↔ Committee verification sheet

**Date:** 2026-04-26 · **Owner:** Phillip · **Est. time:** 10 minutes

## What I need from you

For each of **5 cases** below, open the linked NetFile filer page, confirm what cycle each committee belonged to, and tell me which cases I can fix mechanically. The proposed action under each case is what I'll do if you don't override.

## Background

S24.18a started as "merge 6 duplicate candidacies." 4 cases turned out to be straightforward (same `committee_id` on both rows, just augmenting). 2 cases (Doria, Cesar) had **different** `committee_id`s and I asked you to investigate.

When I dug in to draft this sheet, I found the "different committee_ids" weren't a real conflict — they're **two different election cycles**. The research row got linked to the candidate's *current* committee (the 2026 reelection vehicle), not the *historical* committee for the 2022 race they were elected in.

Then I checked whether this happened elsewhere. **It did — 3 more cases.** So this is a 5-case sheet, not 2. Each is a candidacy row whose `election_id` says one year but whose `committee_id` points to a committee from a different year.

## How to verify

NetFile's public portal exposes filer pages at:

```
https://public.netfile.com/pub2/?aid=RICH#/filer/<filer_id>
```

For each case, click each linked filer page to see:
- The committee's full name (usually contains the year)
- The "First filed" date (tells you what cycle it covers)
- The list of FPPC forms they've submitted

If my proposed action looks right, just reply "go" and I'll execute all 5. If any look wrong, tell me which and what the correction is.

---

## Case 1: Cesar Zepeda — 2022 General Election

**The problem:** The "elected to District 2 in 2022" candidacy row currently points to his 2026 reelection committee.

| Source row | committee_id | committee.name | filer_id | Contributions | Date range |
|---|---|---|---|---|---|
| `research` (kept) | `83ca3946…` | Cesar Zepeda for Richmond City Council **2026** | `1450629` | 45 rows / $19,120 | 2023-07-28 → 2026-03-15 |
| `netfile` (orphan) | `83173cfd…` | Cesar Zepeda for City Council **2022** | `1450629` | 67 rows / $23,652 | 2022-08-31 → 2023-06-28 |

**Verify:**
- Filer 1450629: <https://public.netfile.com/pub2/?aid=RICH#/filer/1450629>
- (Both committees share filer_id 1450629 — same person, two committees over time. The 2022 contributions belong to the 2022 election; the 2023-2026 contributions belong to the 2026 reelection.)

**Proposed action:** Update the 2022 candidacy row to point to `83173cfd…` (the 2022 committee). Delete the orphan netfile row. Result: Zepeda's 2022 page will correctly show $23,652 from 67 donors raised for that race.

---

## Case 2: Doria Robinson — 2022 General Election

Same pattern as Zepeda.

| Source row | committee_id | committee.name | filer_id | Contributions | Date range |
|---|---|---|---|---|---|
| `research` (kept) | `1745fd6e…` | Doria Robinson for Richmond City Council **2026** | `1485224` | 64 rows / $25,956 | 2025-11-24 → 2026-04-14 |
| `netfile` (orphan) | `c09b9bd4…` | Doria Robinson for Richmond City Council **2022** | `1451816` | 81 rows / $42,845 | 2022-08-21 → 2023-06-19 |

**Verify:**
- Filer 1451816 (2022): <https://public.netfile.com/pub2/?aid=RICH#/filer/1451816>
- Filer 1485224 (2026): <https://public.netfile.com/pub2/?aid=RICH#/filer/1485224>
- (Note: she has *two different filer IDs* — she retired the 2022 committee and registered a new one for 2026.)

**Proposed action:** Update the 2022 candidacy row to point to `c09b9bd4…` (the 2022 committee). Delete the orphan netfile row. Her 2022 page will show $42,845 from 81 donors.

---

## Case 3: Melvin Willis — 2020 General Election

**The problem:** His "elected" 2020 candidacy is currently linked to his **2024 reelection** committee. There is no netfile companion row to inherit from — the 2020 committee is missing entirely from `election_candidates`, though it likely exists in the `committees` table.

| Source row | committee_id | committee.name | filer_id |
|---|---|---|---|
| `research` (currently wrong) | linked to "Reelect Melvin Willis for Richmond City Council District 1 **2024**" | — | (2024 cycle) |

**Verify (and find his 2020 committee):**
- Search NetFile for "Willis": <https://public.netfile.com/pub2/?aid=RICH>
- Look for a "Willis for City Council 2020" or similar.
- If you find it, give me the filer_id and I'll re-link.

**Proposed action (depends on what you find):**
- **If the 2020 committee exists in NetFile:** I'll find it in our `committees` table by filer_id, point Willis's 2020 candidacy at it.
- **If no 2020 committee exists** (he might have run unincorporated or under a different vehicle): Set `committee_id = NULL` on the 2020 candidacy row. Better than wrong.

---

## Case 4: Soheila Bana — June 2026 Primary

**The problem:** Her 2026 primary candidacy (city_clerk source — i.e., from the 2026 candidate-discovery feed) is linked to her **2022** committee. She likely has a new 2026 committee that hasn't been imported.

| Source row | committee_id | committee.name | filer_id |
|---|---|---|---|
| `city_clerk` | `d8759f95…` | Soheila Bana for Council **2022** | (legacy filer) |

**Verify (and find her 2026 committee):**
- Search NetFile for "Bana": <https://public.netfile.com/pub2/?aid=RICH>
- Look for "Bana for Mayor 2026" or "Bana for Council 2026" (whichever she's running for in the primary).
- Give me the filer_id.

**Proposed action:** Re-link her 2026 candidacy to the new committee once we find it. If no 2026 committee exists yet (she may be filing late), set to NULL.

---

## Case 5: Soheila Bana — November 2026 General Election

Same problem as Case 4 but for the November race.

| Source row | committee_id | committee.name |
|---|---|---|
| `research` | `d8759f95…` | Soheila Bana for Council **2022** |

**Proposed action:** Same fix as Case 4 — apply whatever resolution you choose there to this row too.

---

## What changes after verification

Once you confirm:
- Cases 1 & 2: I run the merge (≈30 seconds), the `no_duplicate_candidacies_per_election` liveness check goes from 2 failures to 0, and Doria/Cesar's 2022 council profiles will display the correct $42K/$24K instead of the wrong-cycle amounts.
- Cases 3, 4, 5: Re-link or NULL out — depends on what you find. None of these are duplicates (they're integrity errors) so they don't show up in the existing liveness check; I'll add a new expectation `committee_election_cycle_matches_candidacy_cycle` to catch this class of bug going forward.

## Why this happened (so the next session doesn't repeat it)

The research seeding script in S22 (election season prep) loaded the council members' "elected" status by querying `committees` for each official name and grabbing the *most recent* one. For incumbents like Zepeda and Robinson, that turned out to be their 2026 reelection committee, not the 2022 committee that won them the seat. NetFile sync correctly created a separate row pointing at the 2022 committee, which is what the loader fix in this session (S24.18a-2) now augments instead of duplicating.

So:
- **Going forward:** S24.18a-2 (already shipped this session) prevents new duplicates by augmenting on `(official_id, election_id)` rather than insert-on-conflict.
- **Backfill:** Once you confirm the 5 cases here, I'll run the fixes and add the new liveness check.

---

**TL;DR:** Cases 1 and 2 are safe to auto-fix once you eyeball the NetFile filer pages and confirm the 2022 committees are real. Cases 3-5 need you to find the right committee on NetFile and tell me the filer_id (or "none, set NULL"). 10 minutes max.
