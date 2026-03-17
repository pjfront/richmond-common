"""
Pipeline Lineage CLI — Trace data flows from source to frontend.

Reads docs/pipeline-manifest.yaml and provides:
  trace <node>    — Full upstream/downstream chain for a table, source, or enrichment
  impact <module> — What tables, queries, and pages are affected if this module changes
  rerun <table>   — What sync sources need rerunning to refresh this table
  diagram         — Generate Mermaid flowchart of the full pipeline
  validate        — Check manifest against actual code for drift

Usage:
  python pipeline_map.py trace contributions
  python pipeline_map.py impact conflict_scanner.py
  python pipeline_map.py rerun conflict_flags
  python pipeline_map.py diagram --output docs/pipeline-diagram.md
  python pipeline_map.py validate
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

# Fix Windows console encoding (cp1252 can't handle Unicode in YAML descriptions)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


# ── Project Root Detection ────────────────────────────────────

def _find_project_root(start: Path | None = None) -> Path:
    current = start or Path(__file__).parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() and (current / "src").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find project root")


ROOT = _find_project_root()
MANIFEST_PATH = ROOT / "docs" / "pipeline-manifest.yaml"


# ══════════════════════════════════════════════════════════════
# MANIFEST LOADER
# ══════════════════════════════════════════════════════════════

def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Load and return the pipeline manifest YAML."""
    if not path.exists():
        print(f"ERROR: Manifest not found at {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ══════════════════════════════════════════════════════════════
# GRAPH BUILDER
# ══════════════════════════════════════════════════════════════

class PipelineGraph:
    """Bidirectional graph built from the pipeline manifest.

    Nodes are typed: source, table, enrichment, query, page, schedule.
    Edges are directed: upstream (writes_to/reads_from) and downstream.
    """

    def __init__(self, manifest: dict[str, Any]):
        self.manifest = manifest
        # node_key -> {"type": ..., "data": ...}
        self.nodes: dict[str, dict] = {}
        # node_key -> set of downstream node_keys
        self.downstream: dict[str, set[str]] = defaultdict(set)
        # node_key -> set of upstream node_keys
        self.upstream: dict[str, set[str]] = defaultdict(set)
        # module_name -> set of node_keys that reference this module
        self.module_index: dict[str, set[str]] = defaultdict(set)

        self._build()

    def _key(self, node_type: str, name: str) -> str:
        return f"{node_type}:{name}"

    def _add_edge(self, from_key: str, to_key: str) -> None:
        self.downstream[from_key].add(to_key)
        self.upstream[to_key].add(from_key)

    def _build(self) -> None:
        m = self.manifest

        # ── Sources ───────────────────────────────────────────
        for name, data in (m.get("sources") or {}).items():
            key = self._key("source", name)
            self.nodes[key] = {"type": "source", "data": data, "name": name}
            module = data.get("module", "")
            if module:
                self.module_index[module].add(key)
            for table in (data.get("tables_written") or []):
                self._add_edge(key, self._key("table", table))

        # ── Tables ────────────────────────────────────────────
        for name, data in (m.get("tables") or {}).items():
            key = self._key("table", name)
            self.nodes[key] = {"type": "table", "data": data, "name": name}

        # ── Enrichments ───────────────────────────────────────
        for name, data in (m.get("enrichments") or {}).items():
            key = self._key("enrichment", name)
            self.nodes[key] = {"type": "enrichment", "data": data, "name": name}
            module = data.get("module", "")
            if module:
                self.module_index[module].add(key)
            for table in (data.get("reads_from") or []):
                self._add_edge(self._key("table", table), key)
            for table in (data.get("writes_to") or []):
                self._add_edge(key, self._key("table", table))

        # ── Queries ───────────────────────────────────────────
        for name, data in (m.get("queries") or {}).items():
            key = self._key("query", name)
            self.nodes[key] = {"type": "query", "data": data, "name": name}
            for table in (data.get("tables") or []):
                self._add_edge(self._key("table", table), key)

        # ── Pages ─────────────────────────────────────────────
        for name, data in (m.get("pages") or {}).items():
            key = self._key("page", name)
            self.nodes[key] = {"type": "page", "data": data, "name": name}
            for query in (data.get("queries") or []):
                self._add_edge(self._key("query", query), key)

        # ── Schedules ─────────────────────────────────────────
        for name, data in (m.get("schedules") or {}).items():
            key = self._key("schedule", name)
            self.nodes[key] = {"type": "schedule", "data": data, "name": name}
            for source in (data.get("sources_triggered") or []):
                self._add_edge(key, self._key("source", source))
            for enrichment in (data.get("enrichments_triggered") or []):
                self._add_edge(key, self._key("enrichment", enrichment))

    def find_node(self, query: str) -> str | None:
        """Find a node by name, trying all type prefixes."""
        # Exact match with type prefix
        if query in self.nodes:
            return query
        # Try each type
        for node_type in ("table", "source", "enrichment", "query", "page", "schedule"):
            key = self._key(node_type, query)
            if key in self.nodes:
                return key
        # Fuzzy: check if query is a substring of any node name
        matches = [k for k in self.nodes if query in k]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            print(f"Ambiguous: {query} matches {', '.join(matches)}")
            return None
        return None

    def find_by_module(self, module: str) -> set[str]:
        """Find all nodes that reference a given module file."""
        # Strip path prefixes and .py suffix for flexible matching
        module_base = Path(module).name
        results: set[str] = set()
        for mod_name, node_keys in self.module_index.items():
            if mod_name == module_base or mod_name == module:
                results.update(node_keys)
        return results

    def trace_upstream(self, key: str, visited: set[str] | None = None) -> list[str]:
        """Walk upstream from a node, returning all ancestors."""
        if visited is None:
            visited = set()
        if key in visited:
            return []
        visited.add(key)
        result = [key]
        for parent in sorted(self.upstream.get(key, set())):
            result = self.trace_upstream(parent, visited) + result
        return result

    def trace_downstream(self, key: str, visited: set[str] | None = None) -> list[str]:
        """Walk downstream from a node, returning all descendants."""
        if visited is None:
            visited = set()
        if key in visited:
            return []
        visited.add(key)
        result = [key]
        for child in sorted(self.downstream.get(key, set())):
            result = result + self.trace_downstream(child, visited)
        return result


# ══════════════════════════════════════════════════════════════
# COMMANDS
# ══════════════════════════════════════════════════════════════

def _format_node(key: str, graph: PipelineGraph) -> str:
    """Format a node key for display."""
    node_type, name = key.split(":", 1)
    node = graph.nodes.get(key, {})
    desc = node.get("data", {}).get("description", "")
    icon = {"source": ">>", "table": "[]", "enrichment": "{}",
            "query": "??", "page": "//", "schedule": "@@",
            "view": "()"}.get(node_type, " *")
    desc_suffix = f"  -- {desc}" if desc else ""
    return f"  {icon} [{node_type}] {name}{desc_suffix}"


def cmd_trace(args: argparse.Namespace, graph: PipelineGraph) -> None:
    """Trace full upstream and downstream chain for a node."""
    key = graph.find_node(args.node)
    if not key:
        print(f"Node not found: {args.node}")
        print(f"Available tables: {', '.join(n.split(':',1)[1] for n in graph.nodes if n.startswith('table:'))}")
        sys.exit(1)

    upstream = graph.trace_upstream(key)
    downstream = graph.trace_downstream(key)

    # Remove the node itself from both lists to avoid duplication
    upstream_only = [n for n in upstream if n != key]
    downstream_only = [n for n in downstream if n != key]

    print(f"\n{'=' * 60}")
    print(f"  LINEAGE TRACE: {key}")
    print(f"{'=' * 60}")

    if upstream_only:
        print(f"\n  ^ UPSTREAM ({len(upstream_only)} nodes)")
        print(f"  {'-' * 40}")
        for node in upstream_only:
            print(_format_node(node, graph))

    print(f"\n  * TARGET")
    print(f"  {'-' * 40}")
    print(_format_node(key, graph))

    if downstream_only:
        print(f"\n  v DOWNSTREAM ({len(downstream_only)} nodes)")
        print(f"  {'-' * 40}")
        for node in downstream_only:
            print(_format_node(node, graph))

    print()


def cmd_impact(args: argparse.Namespace, graph: PipelineGraph) -> None:
    """Show what's affected if a module changes."""
    module = args.module
    nodes = graph.find_by_module(module)

    if not nodes:
        # Try as a node name instead
        key = graph.find_node(module)
        if key:
            nodes = {key}
        else:
            print(f"No nodes found for module: {module}")
            print(f"Known modules: {', '.join(sorted(graph.module_index.keys()))}")
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  IMPACT ANALYSIS: {module}")
    print(f"{'=' * 60}")

    all_affected: set[str] = set()
    for node in nodes:
        downstream = graph.trace_downstream(node)
        all_affected.update(downstream)

    # Group by type
    by_type: dict[str, list[str]] = defaultdict(list)
    for key in sorted(all_affected):
        node_type = key.split(":", 1)[0]
        by_type[node_type].append(key)

    for node_type in ("source", "table", "enrichment", "query", "page"):
        items = by_type.get(node_type, [])
        if items:
            print(f"\n  Affected {node_type}s ({len(items)}):")
            print(f"  {'-' * 40}")
            for item in items:
                print(_format_node(item, graph))

    print(f"\n  Total affected: {len(all_affected)} nodes")
    print()


def cmd_rerun(args: argparse.Namespace, graph: PipelineGraph) -> None:
    """Show what sync sources need rerunning to refresh a table."""
    key = graph.find_node(args.table)
    if not key:
        print(f"Table not found: {args.table}")
        sys.exit(1)

    upstream = graph.trace_upstream(key)
    sources = [n for n in upstream if n.startswith("source:")]
    enrichments = [n for n in upstream if n.startswith("enrichment:")]

    print(f"\n{'=' * 60}")
    print(f"  RERUN PLAN: {key}")
    print(f"{'=' * 60}")

    if sources:
        print(f"\n  Sync sources to rerun ({len(sources)}):")
        print(f"  {'-' * 40}")
        for source in sources:
            name = source.split(":", 1)[1]
            print(f"    python data_sync.py --source {name}")

    if enrichments:
        print(f"\n  Enrichments to rerun ({len(enrichments)}):")
        print(f"  {'-' * 40}")
        for enrichment in enrichments:
            data = graph.nodes[enrichment].get("data", {})
            module = data.get("module", "unknown")
            print(f"    python {module}")

    if not sources and not enrichments:
        print("\n  No upstream sources found — this table may be manually populated.")

    print()


def cmd_diagram(args: argparse.Namespace, graph: PipelineGraph) -> None:
    """Generate a Mermaid diagram of the pipeline."""
    lines = [
        "```mermaid",
        "flowchart LR",
        "",
        "  %% ── External Sources ──────────────────────────────",
        "  subgraph Sources[\"External Data Sources\"]",
    ]

    # Sources
    for key, node in sorted(graph.nodes.items()):
        if node["type"] == "source":
            name = node["name"]
            safe_id = f"src_{name.replace('-', '_')}"
            label = node["data"].get("description", name)[:50]
            lines.append(f"    {safe_id}[\"{name}\"]")
    lines.append("  end")
    lines.append("")

    # Layer 1 tables
    lines.append("  subgraph Layer1[\"Layer 1: Document Lake\"]")
    for key, node in sorted(graph.nodes.items()):
        if node["type"] == "table" and node["data"].get("layer") == 1:
            name = node["name"]
            safe_id = f"tbl_{name}"
            lines.append(f"    {safe_id}[(\"{name}\")]")
    lines.append("  end")
    lines.append("")

    # Layer 2 tables (grouped)
    lines.append("  subgraph Layer2[\"Layer 2: Structured Core\"]")
    for key, node in sorted(graph.nodes.items()):
        if node["type"] == "table" and node["data"].get("layer") == 2:
            name = node["name"]
            safe_id = f"tbl_{name}"
            lines.append(f"    {safe_id}[(\"{name}\")]")
    lines.append("  end")
    lines.append("")

    # Enrichments
    lines.append("  subgraph Enrichments[\"Enrichment & Analysis\"]")
    for key, node in sorted(graph.nodes.items()):
        if node["type"] == "enrichment":
            name = node["name"]
            safe_id = f"enr_{name}"
            lines.append(f"    {safe_id}{{\"{name}\"}}")
    lines.append("  end")
    lines.append("")

    # Pages
    lines.append("  subgraph Frontend[\"Frontend Pages\"]")
    for key, node in sorted(graph.nodes.items()):
        if node["type"] == "page":
            name = node["name"]
            safe_id = f"page_{name.replace('/', '_').replace('[', '').replace(']', '').strip('_')}"
            lines.append(f"    {safe_id}[\"{name}\"]")
    lines.append("  end")
    lines.append("")

    # Edges: source → table
    lines.append("  %% ── Source → Table edges ─────────────────────────")
    for key, node in sorted(graph.nodes.items()):
        if node["type"] == "source":
            name = node["name"]
            safe_id = f"src_{name.replace('-', '_')}"
            for table in (node["data"].get("tables_written") or []):
                lines.append(f"  {safe_id} --> tbl_{table}")
    lines.append("")

    # Edges: table → enrichment and enrichment → table
    lines.append("  %% ── Enrichment edges ─────────────────────────────")
    for key, node in sorted(graph.nodes.items()):
        if node["type"] == "enrichment":
            name = node["name"]
            safe_id = f"enr_{name}"
            for table in (node["data"].get("reads_from") or []):
                lines.append(f"  tbl_{table} --> {safe_id}")
            for table in (node["data"].get("writes_to") or []):
                lines.append(f"  {safe_id} --> tbl_{table}")
    lines.append("")

    # Edges: table → page (via queries, simplified)
    lines.append("  %% ── Table → Page edges (via queries) ────────────")
    # Build table→page mapping through queries
    table_to_pages: dict[str, set[str]] = defaultdict(set)
    for qname, qdata in (graph.manifest.get("queries") or {}).items():
        for table in (qdata.get("tables") or []):
            for page in (qdata.get("used_by") or []):
                table_to_pages[table].add(page)

    for table, page_set in sorted(table_to_pages.items()):
        for page in sorted(page_set):
            safe_page = f"page_{page.replace('/', '_').replace('[', '').replace(']', '').strip('_')}"
            lines.append(f"  tbl_{table} -.-> {safe_page}")

    lines.append("```")

    output = "\n".join(lines)

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"# Pipeline Lineage Diagram\n\n")
            f.write(f"_Auto-generated by `pipeline_map.py diagram`. Do not edit manually._\n\n")
            f.write(output)
            f.write("\n")
        print(f"Diagram written to {out_path}")
    else:
        print(output)


# ══════════════════════════════════════════════════════════════
# VALIDATE — Check manifest against actual code
# ══════════════════════════════════════════════════════════════

def _extract_sync_sources_from_code() -> set[str]:
    """Parse SYNC_SOURCES dict keys from data_sync.py."""
    data_sync = ROOT / "src" / "data_sync.py"
    if not data_sync.exists():
        return set()
    content = data_sync.read_text(encoding="utf-8")
    # Find SYNC_SOURCES = { ... } block
    match = re.search(r'SYNC_SOURCES\s*=\s*\{([^}]+)\}', content, re.DOTALL)
    if not match:
        return set()
    block = match.group(1)
    return set(re.findall(r'"(\w+)"', block))


def _extract_db_functions_from_code() -> set[str]:
    """Parse load_*/ingest_* function names from db.py."""
    db_file = ROOT / "src" / "db.py"
    if not db_file.exists():
        return set()
    content = db_file.read_text(encoding="utf-8")
    return set(re.findall(
        r'^def ((?:load_|ingest_|save_extraction)\w+)\(',
        content,
        re.MULTILINE,
    ))


def _extract_query_functions_from_code() -> set[str]:
    """Parse exported async function names from queries.ts."""
    queries_file = ROOT / "web" / "src" / "lib" / "queries.ts"
    if not queries_file.exists():
        return set()
    content = queries_file.read_text(encoding="utf-8")
    return set(re.findall(
        r'^export\s+(?:async\s+)?function\s+(\w+)',
        content,
        re.MULTILINE,
    ))


def _extract_migration_tables() -> set[str]:
    """Parse CREATE TABLE / ALTER TABLE names from migration files."""
    migrations_dir = ROOT / "src" / "migrations"
    if not migrations_dir.exists():
        return set()
    tables: set[str] = set()
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        content = sql_file.read_text(encoding="utf-8")
        # CREATE TABLE [IF NOT EXISTS] table_name
        tables.update(re.findall(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)',
            content,
            re.IGNORECASE,
        ))
        # ALTER TABLE table_name
        tables.update(re.findall(
            r'ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)',
            content,
            re.IGNORECASE,
        ))
        # CREATE.*VIEW [IF NOT EXISTS] view_name
        tables.update(re.findall(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)',
            content,
            re.IGNORECASE,
        ))
    return tables


def cmd_validate(args: argparse.Namespace, graph: PipelineGraph) -> list[str]:
    """Validate manifest against actual code. Returns list of issues."""
    issues: list[str] = []

    # 1. Check SYNC_SOURCES coverage
    code_sources = _extract_sync_sources_from_code()
    manifest_sources = {
        data.get("sync_key", name)
        for name, data in (graph.manifest.get("sources") or {}).items()
    }

    missing_in_manifest = code_sources - manifest_sources
    extra_in_manifest = manifest_sources - code_sources

    for src in sorted(missing_in_manifest):
        issues.append(f"[SYNC_SOURCES] '{src}' in code but missing from manifest sources")
    for src in sorted(extra_in_manifest):
        issues.append(f"[SYNC_SOURCES] '{src}' in manifest but missing from SYNC_SOURCES in code")

    # 2. Check query function coverage
    code_queries = _extract_query_functions_from_code()
    manifest_queries = set((graph.manifest.get("queries") or {}).keys())

    missing_queries = code_queries - manifest_queries
    extra_queries = manifest_queries - code_queries

    for q in sorted(missing_queries):
        issues.append(f"[queries.ts] '{q}' exported in code but missing from manifest queries")
    for q in sorted(extra_queries):
        issues.append(f"[queries.ts] '{q}' in manifest but not exported in code")

    # 3. Check that manifest tables exist in migrations (informational only —
    #    core schema tables predate the migration system and were created
    #    directly in Supabase SQL Editor)
    migration_tables = _extract_migration_tables()
    manifest_tables = set((graph.manifest.get("tables") or {}).keys())
    info_notes: list[str] = []

    if migration_tables:
        for tbl in sorted(manifest_tables):
            tbl_data = graph.manifest["tables"][tbl]
            layer = tbl_data.get("layer")
            if layer in (1, 2) and tbl not in migration_tables:
                info_notes.append(f"'{tbl}' — no migration file (pre-migration core table)")

    # Print results
    if not args.quiet if hasattr(args, 'quiet') else True:
        print(f"\n{'=' * 60}")
        print(f"  MANIFEST VALIDATION")
        print(f"{'=' * 60}")
        print(f"\n  Sync sources:  {len(code_sources)} in code, {len(manifest_sources)} in manifest")
        print(f"  Query funcs:   {len(code_queries)} in code, {len(manifest_queries)} in manifest")
        print(f"  Tables:        {len(manifest_tables)} in manifest, {len(migration_tables)} in migrations")

        if issues:
            print(f"\n  ! {len(issues)} issue(s) found:")
            print(f"  {'-' * 40}")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print(f"\n  OK: Manifest is in sync with code")

        if info_notes:
            print(f"\n  Info: {len(info_notes)} pre-migration tables (expected):")
            for note in info_notes:
                print(f"    . {note}")

        print()

    return issues


# ══════════════════════════════════════════════════════════════
# FIELD — Trace a visible field to its pipeline source
# ══════════════════════════════════════════════════════════════

def cmd_field(args: argparse.Namespace, manifest: dict[str, Any]) -> None:
    """Search the field_map for a field and show its end-to-end lineage."""
    search = " ".join(args.query).lower()
    field_map = manifest.get("field_map") or {}

    matches: list[tuple[str, str, dict]] = []  # (page, field_name, field_data)

    for page, fields in field_map.items():
        if not isinstance(fields, dict):
            continue
        for field_name, field_data in fields.items():
            if not isinstance(field_data, dict):
                continue
            if search in field_name.lower() or search in str(field_data).lower():
                matches.append((page, field_name, field_data))

    if not matches:
        print(f"\n  No fields matching '{search}' found in field_map.")
        print(f"  Try a broader search or check docs/pipeline-manifest.yaml")
        return

    print(f"\n{'=' * 60}")
    print(f"  FIELD TRACE: '{search}' ({len(matches)} match{'es' if len(matches) != 1 else ''})")
    print(f"{'=' * 60}")

    for page, field_name, data in matches:
        print(f"\n  // Page: {page}")
        print(f"  Field: \"{field_name}\"")
        print(f"  {'-' * 40}")

        if data.get("query"):
            print(f"    Query:       {data['query']}")
        if data.get("api_route"):
            print(f"    API Route:   {data['api_route']}")
        if data.get("rpc"):
            print(f"    RPC:         {data['rpc']}")
        if data.get("column"):
            print(f"    Column:      {data['column']}")
        if data.get("enrichment"):
            print(f"    Enrichment:  {data['enrichment']}")
        sources = data.get("sources") or []
        if sources:
            print(f"    Sources:     {', '.join(str(s) for s in sources)}")
            print(f"    Rerun:")
            for src in sources:
                if src == "*":
                    print(f"      python data_sync.py --source <any>")
                else:
                    print(f"      python data_sync.py --source {src}")
        elif data.get("enrichment"):
            enr = data["enrichment"]
            enr_data = (manifest.get("enrichments") or {}).get(enr, {})
            module = enr_data.get("module", enr)
            print(f"    Rerun:       python {module}")
        else:
            print(f"    Sources:     (none -- hardcoded or seeded data)")
        if data.get("note"):
            print(f"    Note:        {data['note']}")

    print()


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline Lineage CLI — trace data flows from source to frontend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # trace
    p_trace = sub.add_parser("trace", help="Trace upstream/downstream chain for a node")
    p_trace.add_argument("node", help="Table, source, enrichment, query, or page name")

    # impact
    p_impact = sub.add_parser("impact", help="Show what's affected if a module changes")
    p_impact.add_argument("module", help="Module filename (e.g., conflict_scanner.py)")

    # rerun
    p_rerun = sub.add_parser("rerun", help="Show what to rerun to refresh a table")
    p_rerun.add_argument("table", help="Table name")

    # diagram
    p_diagram = sub.add_parser("diagram", help="Generate Mermaid diagram")
    p_diagram.add_argument("--output", "-o", help="Output file path (default: stdout)")

    # validate
    p_validate = sub.add_parser("validate", help="Check manifest against code")

    # field
    p_field = sub.add_parser("field", help="Trace a visible field to its pipeline source")
    p_field.add_argument("query", nargs="+", help="Field name or partial match (e.g., 'agenda item count')")

    args = parser.parse_args()
    manifest = load_manifest()
    graph = PipelineGraph(manifest)

    if args.command == "trace":
        cmd_trace(args, graph)
    elif args.command == "impact":
        cmd_impact(args, graph)
    elif args.command == "rerun":
        cmd_rerun(args, graph)
    elif args.command == "diagram":
        cmd_diagram(args, graph)
    elif args.command == "validate":
        issues = cmd_validate(args, graph)
        sys.exit(1 if issues else 0)
    elif args.command == "field":
        cmd_field(args, manifest)


if __name__ == "__main__":
    main()
