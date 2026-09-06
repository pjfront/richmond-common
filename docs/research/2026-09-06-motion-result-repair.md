# Motion outcome and significance repair

This follows the resident release and fixes contradictory vote summaries in existing public meeting surfaces.

## Corrected behavior

- Split means an individual recorded motion has both ayes and nays. All-nay votes, absences, abstentions and recusals are not splits.
- A displayed split tally and its result refer to the same motion. The nearest split is selected consistently. Passage is never inferred from ayes exceeding nays; the recorded official-minutes result controls, including special-threshold failures.
- Multiple motions produce a neutral count and a request to inspect their outcomes. A failed motion to reject followed by adoption no longer makes the item Failed. A single motion is labelled as a motion, amendment, substitute, reconsideration or procedural action as supported by its stored type.
- Transcript outcomes remain unverified. Existing generated vote explainers are hidden when the formal outcome is unknown, preventing an old explainer from contradicting the unverified label.
- Missing per-motion vote rows say Vote not recorded rather than inventing an absence. Counts normalize yes/no variants and keep abstention, absence, recusal and unknown categories separate. Roll-call layouts wrap on mobile.
- Consent-calendar membership alone never supplies a passed indicator. Recorded split votes remain visible even if an item also retains a consent flag.
- Public comments are described as recorded comments. The featured-item label does not claim to measure what Richmond as a whole cares about or which issue is most controversial.
- The council-profile table keeps multiple votes/outcomes explicit and links to the individual item. Related-agenda cards remove untrustworthy aggregate Passed/Failed badges and similarity percentages; official titles and links remain.

## Verification

TypeScript passes. Targeted ESLint has no errors; the pre-existing TanStack Table compiler-compatibility warning remains. Focused tests cover failed reject-then-adopt, all nays, a majority tally with formal failure, transcript/unknown outcomes, consistent motion selection, consent, amendments/procedural actions, recusal/absence/missing rows, recorded comments, council-profile split detection and related-card containment. Existing read-failure behavior is preserved.

The real June 23 budget item renders at 375px with 6 aye, 0 nay and 1 absent, without horizontal overflow or browser errors. Its stored vote is transcript-derived, so its outcome is labelled unverified until formal minutes are ingested. This frontend repair does not modify or claim to reconcile stored motion data.
