"""Public conflict eligibility mirrors the existing UI threshold and retains worker access."""
from pathlib import Path
import re
ROOT=Path(__file__).parents[1]
SOURCE=ROOT/'src/migrations/152_public_conflict_eligibility.sql'

def test_migration_mirror_and_existing_threshold():
    sql=SOURCE.read_text()
    assert SOURCE.read_bytes()==(ROOT/'supabase/migrations/20260906015200_public_conflict_eligibility.sql').read_bytes()
    threshold=re.search(r'CONFIDENCE_PUBLISHED\s*=\s*([\d.]+)',(ROOT/'web/src/lib/thresholds.ts').read_text()).group(1)
    assert f'confidence >= {float(threshold):.2f}' in sql
    assert 'AS RESTRICTIVE FOR SELECT TO anon, authenticated' in sql
    assert 'REVOKE ALL ON TABLE public.conflict_flags FROM PUBLIC, anon, authenticated;' in sql
    assert 'GRANT SELECT ON TABLE public.conflict_flags TO anon, authenticated;' in sql
    assert 'DROP POLICY IF EXISTS "Public read"' not in sql
    assert 'ALTER TABLE public.conflict_flags FORCE ROW LEVEL SECURITY' not in sql

def test_definer_rpc_matches_source_and_publication_eligibility():
    sql=SOURCE.read_text()
    assert 'cf.is_current = TRUE' in sql and 'cf.confidence >= 0.70' in sql and 'cf.false_positive IS NOT TRUE' in sql
    assert 'cf.meeting_id IS NULL OR flag_meeting.id IS NOT NULL' in sql
    assert 'cf.agenda_item_id IS NULL OR flag_item.id IS NOT NULL' in sql
    assert 'SET search_path = pg_catalog, pg_temp' in sql
    assert 'confidence >= 0.50' not in sql
    assert not re.search(r'\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\b',sql,re.I)

def test_actual_postgres_proof_runs_in_permission_ci():
    workflow=(ROOT/'.github/workflows/web-tests.yml').read_text()
    assert 'node tests/conflict_public_eligibility.integration.mjs' in workflow
