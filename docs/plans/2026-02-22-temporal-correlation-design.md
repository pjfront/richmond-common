# Temporal Correlation Analysis — Design Document

**Date:** 2026-02-22
**Goal:** Detect donations filed AFTER favorable votes, surfacing the "follow the money after the vote" pattern that investigative journalism traditionally uncovers.

**Approach:** Extend the existing conflict scanner with a new `post_vote_donation` flag type. No new tables, no new migrations, no new API routes — purely additive logic on existing infrastructure.

---

## Problem

The conflict scanner currently detects pre-vote donations: "this donor contributed to Councilmember X before X voted on an item involving the donor's employer." This is valuable but misses the inverse pattern: donations that arrive *after* a favorable vote. Post-vote donations are among the highest-value findings for accountability journalism — a developer donating to a council member's re-election campaign 3 months after that member voted to approve their project.

## Design Decisions

### Lookback window: 5 years (1,825 days), configurable per city
Richmond council terms are 4 years, some commission seats are 5. The default covers the longest appointment cycle. Configurable for other cities with different term lengths.

### Time-decay confidence multiplier
Closer donations are stronger signals. Confidence is base match quality × decay factor:

| Window | Days | Multiplier |
|--------|------|------------|
| 0–90 | Immediate reward | 1.0x |
| 91–180 | Election cycle timing | 0.85x |
| 181–365 | Annual pattern | 0.7x |
| 366–730 | Re-election cycle | 0.5x |
| 731–1825 | Long-term relationship | 0.3x |

### Vote direction: Aye only (for now)
Aye votes have a clear beneficiary named in the agenda item (vendor, contractor, applicant). Nay-vote correlation requires knowing who benefits from something NOT passing — a "stakeholder mapping" problem scoped for later (see DECISIONS.md 2026-02-22 entry).

`vote_choice` is stored in every flag's evidence so we can retroactively add Nay correlation without re-scanning.

### Framing: Purely factual (Option A)
No judgment language. Just dates, dollars, names, and the temporal gap. Example:

> Councilmember Johnson voted Aye on Item H-5 (Approve $2M contract with Acme Corp) on Sept 23, 2025. Jane Smith (employer: Acme Corp) contributed $5,000 to Johnson for Richmond 2026 on Dec 15, 2025.

Subject to revision based on user feedback via the existing feedback system.

### Publication tier defaults
- 0–180 days + high match confidence → Tier 2 (published as "Financial Connection")
- All others → Tier 3 (internal tracking only)

Conservative default. Can promote to Tier 1 after ground truth review validates the signal quality.

---

## Data Flow

1. Retrospective scan runs against a past meeting
2. Load meeting's extracted JSON (agenda items + vote records)
3. For each agenda item with a recorded vote:
   a. Extract officials who voted Aye
   b. Extract entity names from agenda item (vendor, contractor, applicant)
4. For each (official, entity) pair:
   a. Search contributions where:
      - `contribution_date > meeting_date`
      - `contribution_date <= meeting_date + lookback_window`
      - Donor name/employer matches entity via existing `names_match()` logic
      - Committee receiving donation is associated with the official
   b. For each match, compute confidence = base_confidence × time_decay_multiplier
   c. Create `ConflictFlag` with `flag_type = 'post_vote_donation'`
5. Store flags in `conflict_flags` table (existing)
6. Supersede any prior temporal flags for the same meeting (existing `supersede_flags_for_meeting()`)

## Evidence Schema (JSONB)

```json
{
  "vote_date": "2025-09-23",
  "vote_choice": "aye",
  "agenda_item_number": "H-5",
  "agenda_item_title": "Approve $2M contract with Acme Corp",
  "donation_date": "2025-12-15",
  "days_after_vote": 83,
  "donor_name": "Jane Smith",
  "donor_employer": "Acme Corp",
  "donation_amount": 5000.00,
  "recipient_official": "Councilmember Johnson",
  "recipient_committee": "Johnson for Richmond 2026",
  "lookback_window_days": 1825,
  "time_decay_multiplier": 1.0,
  "match_type": "employer_to_vendor"
}
```

## Frontend Display

- Post-vote flags appear in existing transparency reports
- New section "Post-Vote Donations" below pre-vote flags on report detail page
- `ConflictFlagCard.tsx` conditionally displays "X days after vote" callout for `post_vote_donation` flag type
- Existing `FeedbackButton` works as-is for user verification
- No new components needed

## Scheduling & Triggers

- **Prospective scans:** Unaffected (can't detect future donations)
- **Retrospective scans:** Temporal correlation runs as an additional pass
- **Quarterly sweep:** New cron schedule in `cloud-pipeline.yml` runs retrospective scans across trailing 24 months of meetings
- **CLI:** `python conflict_scanner.py <meeting.json> --temporal-correlation --contributions <file>`

## Files Changed

| File | Change | Overlap with Session B? |
|------|--------|------------------------|
| `src/conflict_scanner.py` | Add `scan_temporal_correlations()` function, `post_vote_donation` flag type, time-decay config | Low risk — Session B moves constants out, we add new function at bottom |
| `src/cloud_pipeline.py` | Call temporal scan during retrospective mode | Low risk — different code sections |
| `web/src/components/ConflictFlagCard.tsx` | Conditional `days_after_vote` display | No overlap |
| `web/src/app/reports/[meetingId]/page.tsx` | "Post-Vote Donations" section | No overlap |
| `.github/workflows/cloud-pipeline.yml` | Quarterly cron schedule | No overlap |

**Merge order:** Merge Session B (multi-city) first, then rebase this branch on top.

## Future Extensions (not in scope)

- Nay-vote correlation (requires stakeholder mapping — see DECISIONS.md)
- Movers/seconders weighting (officials who actively championed an item, not just voted Aye)
- Cross-meeting patterns (same donor donates after multiple favorable votes by same official)
- Automated ground truth review prompts for high-confidence temporal flags
