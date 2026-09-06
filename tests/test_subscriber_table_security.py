"""Migration boundaries; effective privileges run in the PostgreSQL CI gate."""
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / 'src/migrations/151_restrict_subscriber_table_access.sql'
MIRROR = ROOT / 'supabase/migrations/20260906015100_restrict_subscriber_table_access.sql'


def test_migration_mirror_is_exact() -> None:
    assert SOURCE.read_bytes() == MIRROR.read_bytes()


def test_only_private_table_grants_change() -> None:
    sql = ' '.join(line for line in SOURCE.read_text().splitlines()
                   if not line.lstrip().startswith('--'))
    assert sql.split() == '''
        REVOKE ALL PRIVILEGES ON TABLE public.email_subscribers
            FROM PUBLIC, anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE public.email_preferences
            FROM PUBLIC, anon, authenticated;
    '''.split()


def test_effective_role_verifier_runs_in_ci() -> None:
    workflow = (ROOT / '.github/workflows/web-tests.yml').read_text()
    assert 'node tests/subscriber_table_security.integration.mjs ' in workflow
