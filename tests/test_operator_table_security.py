"""Contracts for private operator state and public registry access."""
from pathlib import Path
import re

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / 'src/migrations/147_restrict_operator_table_access.sql'
MIRROR = ROOT / 'supabase/migrations/20260906014700_restrict_operator_table_access.sql'
PRIVATE_TABLES = ('pending_decisions', 'pipeline_journal')


def executable_sql():
    return '\n'.join(line for line in SOURCE.read_text().splitlines()
                     if not line.lstrip().startswith('--'))


def test_migration_mirror_matches():
    assert SOURCE.read_bytes() == MIRROR.read_bytes()


def test_private_tables_deny_all_public_privileges_and_scope_rls():
    sql = executable_sql()
    for table in PRIVATE_TABLES:
        assert f'REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM PUBLIC, anon, authenticated;' in sql
        assert f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO service_role;' in sql
        assert re.search(rf'CREATE POLICY {table}_service_all ON public\.{table}\s+'
                         r'FOR ALL TO service_role USING \(true\) WITH CHECK \(true\);', sql)


def test_neighborhood_access_is_public_read_service_write():
    sql = executable_sql()
    assert 'REVOKE ALL PRIVILEGES ON TABLE public.neighborhood_councils FROM PUBLIC, anon, authenticated;' in sql
    assert 'GRANT SELECT ON TABLE public.neighborhood_councils TO anon, authenticated;' in sql
    assert re.search(r'CREATE POLICY neighborhood_councils_service_write ON public\.neighborhood_councils\s+'
                     r'FOR ALL TO service_role USING \(true\) WITH CHECK \(true\);', sql)


def test_migration_has_no_data_mutation_or_unrelated_objects():
    sql = executable_sql()
    assert set(re.findall(r'public\.(\w+)', sql)) == {*PRIVATE_TABLES, 'neighborhood_councils'}
    assert not re.search(r'\b(INSERT INTO|UPDATE public\.|DELETE FROM|TRUNCATE|DROP TABLE|DROP FUNCTION)\b', sql)


def test_public_health_does_not_probe_private_operator_tables():
    source = (ROOT / 'web/src/app/api/health/route.ts').read_text()
    for table in PRIVATE_TABLES:
        assert f"'{table}'" not in source
