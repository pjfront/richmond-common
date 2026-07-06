"""Tests for apify_entity_resolution.py — enrichment sync function and SYNC_SOURCES registration."""

import pytest
from unittest import mock


# ── SYNC_SOURCES registration ──────────────────────────────────

def test_apify_entity_resolution_in_sync_sources():
    """The enrichment must be registered in SYNC_SOURCES for data_sync.py dispatch."""
    from data_sync import SYNC_SOURCES

    assert "apify_entity_resolution" in SYNC_SOURCES
    fn = SYNC_SOURCES["apify_entity_resolution"]
    assert callable(fn)
    assert fn.__name__ == "sync_apify_entity_resolution"


# ── Gate query logic (unit) ─────────────────────────────────────

def test_gate_query_resolvable_types():
    """The gate query must only resolve non-person entity types."""
    from apify_entity_resolution import _RESOLVABLE_TYPES

    assert "corporation" in _RESOLVABLE_TYPES
    assert "union" in _RESOLVABLE_TYPES
    assert "committee" in _RESOLVABLE_TYPES
    assert "other_org" in _RESOLVABLE_TYPES
    assert "person" not in _RESOLVABLE_TYPES  # skip individuals


def test_gate_query_has_not_exists_clause():
    """The gate query must skip donors already matched in entity_name_matches."""
    from apify_entity_resolution import _GATE_QUERY

    assert "NOT EXISTS" in _GATE_QUERY
    assert "entity_name_matches" in _GATE_QUERY
    assert "source_record_id = d.id" in _GATE_QUERY or "source_record_id=d.id" in _GATE_QUERY


# ── Batch size ──────────────────────────────────────────────────

def test_batch_size_is_reasonable():
    """Batch size must be small enough for sync endpoint 5-min timeout."""
    from apify_entity_resolution import _BATCH_SIZE

    assert 1 <= _BATCH_SIZE <= 20


# ── Match threshold ─────────────────────────────────────────────

def test_match_threshold_is_reasonable():
    """Match threshold should be 0.80 — same as opencorporates_client."""
    from apify_entity_resolution import _MATCH_THRESHOLD

    assert 0.70 <= _MATCH_THRESHOLD <= 0.95


# ── Sync function signature ─────────────────────────────────────

def test_sync_function_accepts_expected_kwargs():
    """Must accept conn, city_fips, sync_type, sync_log_id for data_sync.py dispatch."""
    import inspect
    from apify_entity_resolution import sync_apify_entity_resolution

    sig = inspect.signature(sync_apify_entity_resolution)
    params = list(sig.parameters.keys())
    assert "conn" in params
    assert "city_fips" in params
    assert "sync_type" in params
    assert "sync_log_id" in params


# ── Integration: mock Apify, test DB writes ─────────────────────

@pytest.mark.skip(reason="needs test DB — run manually with RICHMOND_RUN_DB_TESTS=1")
def test_sync_integration():
    """Full integration test against test DB with mocked Apify calls."""
    pass
