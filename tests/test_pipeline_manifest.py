"""Tests that pipeline-manifest.yaml stays in sync with actual code.

These tests catch drift between the manifest and the codebase:
- SYNC_SOURCES keys in data_sync.py
- Exported query functions in queries.ts
- Graph integrity (no broken references)
- Field map coverage (every query and page has field_map entries)
"""
from __future__ import annotations

import re
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


# ── Field Map Coverage ────────────────────────────────────────


class TestFieldMapCoverage:
    """Field map must cover all data-serving queries and all page routes."""

    def _get_field_map_queries(self, manifest) -> set[str]:
        """Extract all query function names referenced in field_map entries."""
        queries: set[str] = set()
        for _page, fields in (manifest.get("field_map") or {}).items():
            if not isinstance(fields, dict):
                continue
            for _field, data in fields.items():
                if isinstance(data, dict) and data.get("query"):
                    queries.add(data["query"])
        return queries

    def _get_field_map_pages(self, manifest) -> set[str]:
        """Extract all page routes from the field_map."""
        return set((manifest.get("field_map") or {}).keys())

    def _get_data_serving_queries(self, manifest) -> set[str]:
        """Get query functions that serve data to pages (not utility functions)."""
        all_queries = set((manifest.get("queries") or {}).keys())
        # Exclude pure utility functions that don't read tables
        utility_queries: set[str] = set()
        for name, data in (manifest.get("queries") or {}).items():
            tables = data.get("tables") or []
            if not tables:
                utility_queries.add(name)
        return all_queries - utility_queries

    def test_every_data_query_in_field_map(self, manifest):
        """Every data-serving query function must appear in at least one field_map entry."""
        data_queries = self._get_data_serving_queries(manifest)
        field_map_queries = self._get_field_map_queries(manifest)
        missing = data_queries - field_map_queries
        assert not missing, (
            f"Query functions serve data but have no field_map entries: {missing}. "
            f"Add field_map entries to docs/pipeline-manifest.yaml for these queries."
        )

    def test_field_map_queries_exist(self, manifest):
        """Every query referenced in field_map must exist in the queries section."""
        manifest_queries = set((manifest.get("queries") or {}).keys())
        field_map_queries = self._get_field_map_queries(manifest)
        missing = field_map_queries - manifest_queries
        assert not missing, (
            f"Field map references non-existent queries: {missing}. "
            f"Either add these queries to the queries section or fix the field_map."
        )

    def test_every_content_page_has_field_map(self, manifest):
        """Every page that uses queries must have field_map entries."""
        field_map_pages = self._get_field_map_pages(manifest)
        for page_name, page_data in (manifest.get("pages") or {}).items():
            page_queries = page_data.get("queries") or []
            if not page_queries:
                continue  # Static pages (about, data-quality) may have no queries
            assert page_name in field_map_pages, (
                f"Page '{page_name}' uses queries {page_queries} but has no field_map entries. "
                f"Add field_map entries for this page in docs/pipeline-manifest.yaml."
            )

    def test_field_map_pages_exist(self, manifest):
        """Every page in field_map must exist in the pages section."""
        manifest_pages = set((manifest.get("pages") or {}).keys())
        field_map_pages = self._get_field_map_pages(manifest)
        missing = field_map_pages - manifest_pages
        assert not missing, (
            f"Field map references non-existent pages: {missing}. "
            f"Either add these pages to the pages section or fix the field_map."
        )

    def test_every_field_has_source_or_enrichment(self, manifest):
        """Every field_map entry must specify either sources or enrichment (or note explaining why not)."""
        for page, fields in (manifest.get("field_map") or {}).items():
            if not isinstance(fields, dict):
                continue
            for field_name, data in fields.items():
                if not isinstance(data, dict):
                    continue
                has_sources = bool(data.get("sources"))
                has_enrichment = bool(data.get("enrichment"))
                has_api_route = bool(data.get("api_route"))
                has_note = bool(data.get("note"))
                assert has_sources or has_enrichment or has_api_route or has_note, (
                    f"Field '{field_name}' on page '{page}' has no sources, "
                    f"enrichment, api_route, or explanatory note. Every field must "
                    f"be traceable to a pipeline source."
                )

    def test_page_directories_match_field_map(self, manifest):
        """Every page directory in web/src/app/ with a page.tsx should have field_map coverage."""
        app_dir = ROOT / "web" / "src" / "app"
        if not app_dir.exists():
            pytest.skip("web/src/app/ not found")

        field_map_pages = self._get_field_map_pages(manifest)
        # Static/utility pages that don't need field_map coverage
        exempt_pages = {"/about", "/operator"}

        for page_tsx in app_dir.rglob("page.tsx"):
            # Convert file path to route: web/src/app/council/page.tsx → /council
            rel = page_tsx.parent.relative_to(app_dir)
            route = "/" + str(rel).replace("\\", "/")
            if route == "/.":
                route = "/"

            # Skip dynamic segments in path for matching
            # e.g., /meetings/[id] → check if /meetings/[id] is in field_map
            if route in exempt_pages:
                continue
            # Skip API routes and operator pages
            if route.startswith("/api") or route.startswith("/operator"):
                continue

            assert route in field_map_pages, (
                f"Page route '{route}' (from {page_tsx.relative_to(ROOT)}) "
                f"has no field_map entries in the manifest."
            )
