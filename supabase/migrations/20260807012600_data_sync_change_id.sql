-- Consumer-side idempotency for change-detector repository_dispatch events.
--
-- GitHub may accept a dispatch even when the detector later loses its state
-- acknowledgement. Retrying that observation must not run the same paid sync
-- twice. The detector supplies a deterministic SHA-256 change_id and the
-- consumer claims it atomically in data_sync_log before doing any work.

ALTER TABLE data_sync_log
    ADD COLUMN IF NOT EXISTS change_id VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_data_sync_log_change_id
    ON data_sync_log (city_fips, source, change_id)
    WHERE change_id IS NOT NULL;

COMMENT ON COLUMN data_sync_log.change_id IS
    'Deterministic detector fingerprint hash; null for manual/scheduled syncs.';
