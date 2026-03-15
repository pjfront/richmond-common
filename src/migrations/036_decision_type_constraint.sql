-- Migration 036: Add CHECK constraint for decision_type on pending_decisions
--
-- Previously, decision_type was validated only in Python (decision_queue.py VALID_TYPES).
-- This caused a runtime crash when data_quality_checks.py used 'data_quality' before it
-- was added to VALID_TYPES. A DB constraint provides defense in depth.
--
-- Idempotent: drops existing constraint first if present.

ALTER TABLE pending_decisions
    DROP CONSTRAINT IF EXISTS pending_decisions_decision_type_check;

ALTER TABLE pending_decisions
    ADD CONSTRAINT pending_decisions_decision_type_check
    CHECK (decision_type IN (
        'staleness_alert',
        'anomaly',
        'data_quality',
        'tier_graduation',
        'conflict_review',
        'assessment_finding',
        'pipeline_failure',
        'general'
    ));
