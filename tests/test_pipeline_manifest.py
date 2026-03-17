"""Tests that pipeline-manifest.yaml stays in sync with actual code.

These tests catch drift between the manifest and the codebase:
- SYNC_SOURCES keys in data_sync.py
- Exported query functions in queries.ts
- Graph integrity (no broken references)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src/ to path for imports
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pipeline_map import (
    PipelineGraph,
    load_manifest,
    _extract_sync_sources_from_code,
    _extract_query_functions_from_code,
)


@pytest.fixture
def manifest():
    return load_manifest(ROOT / "docs" / "pipeline-manifest.yaml")


@pytest.fixture
def graph(manifest):
    return PipelineGraph(manifest)


# ── Sync Source Coverage ──────────────────────────────────────


class TestSyncSourceCoverage:
    """Every SYNC_SOURCES key must appear in the manifest, and vice versa."""

    def test_all_code_sources_in_manifest(self, manifest):
        code_sources = _extract_sync_sources_from_code()
        manifest_sources = {
            data.get("sync_key", name)
            for name, data in (manifest.get("sources") or {}).items()
        }
        missing = code_sources - manifest_sources
        assert not missing, (
            f"SYNC_SOURCES keys in code but missing from manifest: {missing}. "
            f"Add entries to docs/pipeline-manifest.yaml."
        )

    def test_no_extra_manifest_sources(self, manifest):
        code_sources = _extract_sync_sources_from_code()
        manifest_sources = {
            data.get("sync_key", name)
            for name, data in (manifest.get("sources") or {}).items()
        }
        extra = manifest_sources - code_sources
        assert not extra, (
            f"Manifest sources not in SYNC_SOURCES: {extra}. "
            f"Remove stale entries from docs/pipeline-manifest.yaml."
        )


# ── Query Function Coverage ───────────────────────────────────


class TestQueryCoverage:
    """Every exported query function must appear in the manifest."""

    def test_all_code_queries_in_manifest(self, manifest):
        code_queries = _extract_query_functions_from_code()
        manifest_queries = set((manifest.get("queries") or {}).keys())
        missing = code_queries - manifest_queries
        assert not missing, (
            f"Query functions in code but missing from manifest: {missing}. "
            f"Add entries to docs/pipeline-manifest.yaml."
        )

    def test_no_extra_manifest_queries(self, manifest):
        code_queries = _extract_query_functions_from_code()
        manifest_queries = set((manifest.get("queries") or {}).keys())
        extra = manifest_queries - code_queries
        assert not extra, (
            f"Manifest queries not in code: {extra}. "
            f"Remove stale entries from docs/pipeline-manifest.yaml."
        )


# ── Graph Integrity ───────────────────────────────────────────


class TestGraphIntegrity:
    """Manifest references should be internally consistent."""

    def test_source_tables_exist(self, manifest, graph):
        """Every table referenced in sources.tables_written must exist in tables."""
        manifest_tables = set((manifest.get("tables") or {}).keys())
        for src_name, src_data in (manifest.get("sources") or {}).items():
            for table in (src_data.get("tables_written") or []):
                assert table in manifest_tables, (
                    f"Source '{src_name}' references table '{table}' "
                    f"which is not defined in manifest tables section."
                )

    def test_enrichment_tables_exist(self, manifest, graph):
        """Every table in enrichment reads_from/writes_to must exist."""
        manifest_tables = set((manifest.get("tables") or {}).keys())
        for enr_name, enr_data in (manifest.get("enrichments") or {}).items():
            for table in (enr_data.get("reads_from") or []):
                assert table in manifest_tables, (
                    f"Enrichment '{enr_name}' reads from '{table}' "
                    f"which is not defined in manifest tables section."
                )
            for table in (enr_data.get("writes_to") or []):
                assert table in manifest_tables, (
                    f"Enrichment '{enr_name}' writes to '{table}' "
                    f"which is not defined in manifest tables section."
                )

    def test_query_tables_exist(self, manifest, graph):
        """Every table referenced in queries must exist."""
        manifest_tables = set((manifest.get("tables") or {}).keys())
        for q_name, q_data in (manifest.get("queries") or {}).items():
            for table in (q_data.get("tables") or []):
                assert table in manifest_tables, (
                    f"Query '{q_name}' references table '{table}' "
                    f"which is not defined in manifest tables section."
                )

    def test_page_queries_exist(self, manifest, graph):
        """Every query referenced in pages must exist."""
        manifest_queries = set((manifest.get("queries") or {}).keys())
        for page_name, page_data in (manifest.get("pages") or {}).items():
            for query in (page_data.get("queries") or []):
                assert query in manifest_queries, (
                    f"Page '{page_name}' references query '{query}' "
                    f"which is not defined in manifest queries section."
                )

    def test_graph_has_nodes(self, graph):
        """Graph should have a reasonable number of nodes."""
        assert len(graph.nodes) > 50, (
            f"Graph only has {len(graph.nodes)} nodes — expected 50+. "
            f"Manifest may be incomplete."
        )

    def test_every_layer2_table_has_writer(self, manifest):
        """Every Layer 2 table should have at least one source or enrichment writing to it."""
        for tbl_name, tbl_data in (manifest.get("tables") or {}).items():
            if tbl_data.get("layer") != 2:
                continue
            writers = tbl_data.get("written_by", {})
            sources = writers.get("sources") or []
            enrichments = writers.get("enrichments") or []
            assert sources or enrichments, (
                f"Layer 2 table '{tbl_name}' has no writers (sources or enrichments). "
                f"Update written_by in the manifest."
            )
