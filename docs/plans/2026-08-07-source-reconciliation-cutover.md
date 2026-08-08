# Source Reconciliation Cutover

Migration 133 is deliberately additive. It installs source identity,
revision, and tombstone fields plus current-parent policies, but it does not
hide pre-existing `legacy` agenda rows or quarantine historic eSCRIBE raw
documents/attachments. Doing that in the same deployment would temporarily
remove a material share of the public archive before the upstream source can
be re-observed.

The enforcement cutover is a separate operator-controlled change:

1. Deploy migration 133 and the GUID-based, recursively sanitized, atomic
   eSCRIBE writers.
2. Run `python src/data_sync.py --source escribemeetings --sync-type full`.
   A successful run must re-download every declared attachment and record its
   stable DocumentId and content hash before a revision is published. Missing
   text is an enrichment failure to retry, not a reason to leave a superseded
   source revision public.
3. Verify coverage by stable meeting GUID, active raw revision, agenda item,
   attachment DocumentId/content hash, and adopted-minutes ownership. Review
   the draft cutover's complete candidate counts for active unsanitized raw
   documents, legacy agenda items, NULL-revision attachments, and attachments
   owned by legacy agenda rows. First run the draft against a production clone
   with its final `COMMIT` changed to `ROLLBACK`; retain the emitted candidate
   and expected-public-delta notices in the operator record. Resolve all sync
   failures and unexpected candidates; do not infer ownership for unmatched
   rows.
4. Invalidate and regenerate summaries, embeddings, topics, and flags whose
   inputs changed or whose attachment source was retired.
5. Apply a later enforcement migration that is idempotent and only then:
   quarantines unsanitized/superseded eSCRIBE raw rows, quarantines unresolved
   legacy attachments/items from anonymous reads, and verifies zero unexpected
   public-count loss before commit. The staged draft performs its preflight,
   quarantine writes, policy replacement, and exact before/after assertions in
   one serializable transaction. Every public unsanitized raw row must first
   have a current sanitized replacement for the same stable meeting GUID; a
   NULL-GUID raw row fails closed. Each quarantine UPDATE must affect exactly
   its snapshotted candidate count, and the transaction rolls back unless the
   final public counts equal the initial counts minus only those candidates.

Rollback before step 5 is code-only. After step 5, rollback means restoring
the prior RLS policies/tombstones while retaining the service-role audit rows;
no source artifacts are hard-deleted.
