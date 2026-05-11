-- Migration 104: Revoke anon UPDATE on operator_config
--
-- SECURITY FIX (2026-05-09 architecture audit, Phase 0.1):
-- Migration 074 granted `operator_config FOR UPDATE TO anon USING (true)` with
-- the comment "OperatorGate protects frontend." OperatorGate is a client-side
-- cookie. Anyone with the publicly-shipped anon key (which ships in every
-- browser bundle) could mutate publication thresholds via curl, weaponizing
-- the publication tier system.
--
-- Anon retains SELECT (operator_config is read by public-facing queries to
-- determine confidence thresholds; that's safe). Writes now require service_role.
-- Operator writes go through `web/src/app/api/operator/settings` which now uses
-- iron-session auth (Phase 0.2/0.3) and the service_role key server-side.

DROP POLICY IF EXISTS operator_config_anon_write ON operator_config;

-- Defensive: also revoke any direct grants
REVOKE INSERT, UPDATE, DELETE ON operator_config FROM anon;

-- Keep service_role full access (already exists from 074, idempotent re-create)
DROP POLICY IF EXISTS operator_config_service_all ON operator_config;
CREATE POLICY operator_config_service_all
  ON operator_config FOR ALL TO service_role USING (true);

-- Keep anon SELECT (intentional — public pages read thresholds)
DROP POLICY IF EXISTS operator_config_anon_read ON operator_config;
CREATE POLICY operator_config_anon_read
  ON operator_config FOR SELECT TO anon USING (true);
