"""Review requests have one guarded, audited path; evidence never executes."""
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid
import pytest

from db.decisions import update_decision_status
from decision_queue import create_decision, resolve_decision

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / 'src/migrations/149_operator_review_inbox.sql'


def test_migration_is_exactly_mirrored():
    assert SOURCE.read_bytes() == (ROOT / 'supabase/migrations/20260906014900_operator_review_inbox.sql').read_bytes()


def test_review_rpc_is_service_only_and_locks_both_reviewed_records():
    sql = SOURCE.read_text()
    assert 'REVOKE ALL ON FUNCTION public.review_decision(uuid, text, bigint, uuid, text, text) FROM PUBLIC, anon, authenticated' in sql
    assert 'WHERE id = p_decision_id FOR UPDATE' in sql
    assert 'WHERE id = decision.target_brief_id FOR UPDATE' in sql
    assert 'decision.review_version <> p_expected_version' in sql
    assert 'brief.content_version IS DISTINCT FROM decision.target_content_version' in sql
    assert 'EXECUTE evidence' not in sql


@patch('decision_queue.insert_pending_decision')
def test_publication_creation_has_explicit_target_and_is_editorial(insert):
    create_decision(MagicMock(), '0660620', 'general', 'medium', 'Review', 'Sources ready', 'test',
                    action_kind='publish_brief', target_brief_id=str(uuid.uuid4()), target_content_version=2)
    assert insert.call_args.kwargs['review_class'] == 'editorial'
    assert insert.call_args.kwargs['target_content_version'] == 2


@pytest.mark.parametrize('extra', [
    {'action_kind': 'execute_sql'}, {'action_kind': 'publish_brief'},
    {'action_kind': 'resolve_only', 'target_content_version': 1},
])
def test_unsupported_or_incomplete_publication_contract_is_rejected(extra):
    with pytest.raises(ValueError):
        create_decision(MagicMock(), '0660620', 'general', 'medium', 'Review', 'Context', 'test', **extra)


def connection(results):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = results
    return conn, cursor


def test_python_generic_resolution_uses_version_and_atomic_rpc():
    conn, cursor = connection([(4, 'resolve_only'), ({'ok': True},)])
    key = uuid.uuid4()
    assert update_decision_status(conn, uuid.uuid4(), 'approved', idempotency_key=key)
    sql, params = cursor.execute.call_args.args
    assert sql == 'SELECT public.review_decision(%s, %s, %s, %s, %s, %s)'
    assert params[1:4] == ('approve', 4, str(key))
    conn.commit.assert_called_once()


def test_python_publication_refuses_unreviewed_implicit_version():
    conn, _ = connection([(4, 'publish_brief')])
    with pytest.raises(ValueError, match='explicitly reviewed'):
        update_decision_status(conn, uuid.uuid4(), 'approved')
    conn.rollback.assert_called_once()


@patch('decision_queue.update_decision_status', return_value=True)
def test_explicit_publication_guard_and_retry_key_are_preserved(update):
    key = str(uuid.uuid4())
    assert resolve_decision(MagicMock(), str(uuid.uuid4()), 'approved', expected_version=7, idempotency_key=key)
    assert update.call_args.kwargs['expected_version'] == 7
    assert update.call_args.kwargs['idempotency_key'] == key
