"""
Richmond Transparency Project — System Health & Self-Assessment

Self-monitoring module that evaluates the health of the project's
documentation architecture, codebase conventions, and pipeline
infrastructure. Produces evidence-based assessments rather than
relying on intuition.

Three assessment layers:
  1. Documentation Architecture Benchmark — Does our CLAUDE.md tree
     help the system find the right context for common tasks?
  2. Architecture Health — Module coupling, test coverage, convention
     compliance, documentation drift
  3. Pipeline Instrumentation Helpers — Timing/token decorators for
     incremental adoption across pipeline stages

Usage:
  python system_health.py                         # Full report
  python system_health.py --format json           # JSON output
  python system_health.py --benchmark-only        # Just the doc benchmark
  python system_health.py --architecture-only     # Just architecture health
  python system_health.py --git-only              # Just git metrics
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


# ── Project Root Detection ────────────────────────────────────

def _find_project_root(start: Path | None = None) -> Path:
    """Walk up from start (or this file) to find the repo root."""
    current = start or Path(__file__).parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() and (current / "src").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find project root (no CLAUDE.md found)")


# ══════════════════════════════════════════════════════════════
# LAYER 1: Documentation Architecture Benchmark
# ══════════════════════════════════════════════════════════════

@dataclass
class BenchmarkCase:
    """A single task-to-context mapping for the documentation benchmark."""
    task: str
    category: str  # pipeline, frontend, infrastructure, process, analysis
    expected_files: list[str]  # relative paths from project root
    expected_keywords: dict[str, list[str]]  # file -> keywords that should be present


# The benchmark: 15 common task types mapped to expected documentation context.
# If a developer (human or AI) needs to do this task, these are the files and
# sections they should find. Coverage gaps = documentation debt.
BENCHMARK_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        task="Add a new data source to the pipeline",
        category="pipeline",
        expected_files=[
            "src/CLAUDE.md",
            ".claude/rules/architecture.md",
            "src/city_config.py",
            "src/data_sync.py",
        ],
        expected_keywords={
            "src/CLAUDE.md": ["scraper pattern", "city_config", "data_sync"],
            ".claude/rules/architecture.md": ["three-layer", "tech stack"],
        },
    ),
    BenchmarkCase(
        task="Fix a conflict scanner bug",
        category="analysis",
        expected_files=[
            "src/CLAUDE.md",
            "src/conflict_scanner.py",
            "src/scan_audit.py",
        ],
        expected_keywords={
            "src/CLAUDE.md": ["conflict scanner", "employer filter", "false positive"],
        },
    ),
    BenchmarkCase(
        task="Add a new frontend page",
        category="frontend",
        expected_files=[
            "web/CLAUDE.md",
            ".claude/rules/conventions.md",
            ".claude/rules/team-operations.md",
        ],
        expected_keywords={
            "web/CLAUDE.md": ["app router", "component", "supabase"],
            ".claude/rules/team-operations.md": ["publication tier"],
        },
    ),
    BenchmarkCase(
        task="Run the cloud pipeline for a meeting",
        category="pipeline",
        expected_files=[
            "src/CLAUDE.md",
            "src/cloud_pipeline.py",
        ],
        expected_keywords={
            "src/CLAUDE.md": ["cloud_pipeline", "7 steps", "prospective"],
        },
    ),
    BenchmarkCase(
        task="Add a new city to the platform",
        category="infrastructure",
        expected_files=[
            "CLAUDE.md",
            ".claude/rules/architecture.md",
            ".claude/rules/conventions.md",
            "src/city_config.py",
        ],
        expected_keywords={
            "CLAUDE.md": ["FIPS", "19,000 cities", "multi-city"],
            ".claude/rules/architecture.md": ["city_config", "FIPS", "CityNotConfiguredError"],
            ".claude/rules/conventions.md": ["city_fips", "0660620"],
        },
    ),
    BenchmarkCase(
        task="Debug an eSCRIBE scraper issue",
        category="pipeline",
        expected_files=[
            "src/CLAUDE.md",
            "src/escribemeetings_scraper.py",
        ],
        expected_keywords={
            "src/CLAUDE.md": ["eSCRIBE", "GetCalendarMeetings", "AgendaItem"],
        },
    ),
    BenchmarkCase(
        task="Decide on publication tier for a new feature",
        category="process",
        expected_files=[
            ".claude/rules/team-operations.md",
            ".claude/rules/judgment-boundaries.md",
        ],
        expected_keywords={
            ".claude/rules/team-operations.md": ["publication tier", "graduated", "operator-only"],
            ".claude/rules/judgment-boundaries.md": ["publication tier", "judgment call"],
        },
    ),
    BenchmarkCase(
        task="Write and review a commit message",
        category="process",
        expected_files=[
            ".claude/rules/conventions.md",
            ".claude/rules/judgment-boundaries.md",
        ],
        expected_keywords={
            ".claude/rules/conventions.md": ["imperative mood", "commit"],
            ".claude/rules/judgment-boundaries.md": ["commit message", "AI-delegable"],
        },
    ),
    BenchmarkCase(
        task="Add a database migration",
        category="infrastructure",
        expected_files=[
            ".claude/rules/conventions.md",
            "src/CLAUDE.md",
        ],
        expected_keywords={
            ".claude/rules/conventions.md": ["migration", "idempotent", "IF NOT EXISTS"],
            "src/CLAUDE.md": ["migration", "health check"],
        },
    ),
    BenchmarkCase(
        task="Understand project values and positioning",
        category="process",
        expected_files=[
            "CLAUDE.md",
            ".claude/rules/richmond.md",
        ],
        expected_keywords={
            "CLAUDE.md": ["governance assistant", "watchdog", "free public access"],
            ".claude/rules/richmond.md": ["governance assistant", "adversarial"],
        },
    ),
    BenchmarkCase(
        task="Review bias audit results",
        category="analysis",
        expected_files=[
            "src/CLAUDE.md",
            "src/bias_audit.py",
            "src/scan_audit.py",
            "docs/specs/bias-audit-spec.md",
        ],
        expected_keywords={
            "src/CLAUDE.md": ["bias", "census", "ground truth", "surname"],
        },
    ),
    BenchmarkCase(
        task="Add a commission to the system",
        category="pipeline",
        expected_files=[
            "src/CLAUDE.md",
            "src/commission_roster_scraper.py",
            "src/city_config.py",
        ],
        expected_keywords={
            "src/CLAUDE.md": ["commission", "roster", "term date"],
        },
    ),
    BenchmarkCase(
        task="Troubleshoot CI/CD pipeline failure",
        category="infrastructure",
        expected_files=[
            "src/CLAUDE.md",
            ".claude/rules/conventions.md",
        ],
        expected_keywords={
            "src/CLAUDE.md": ["GitHub Actions", "cloud-pipeline.yml", "data-sync.yml"],
            ".claude/rules/conventions.md": ["pytest"],
        },
    ),
    BenchmarkCase(
        task="Sync campaign finance data",
        category="pipeline",
        expected_files=[
            "src/CLAUDE.md",
            "src/data_sync.py",
            "src/netfile_client.py",
        ],
        expected_keywords={
            "src/CLAUDE.md": ["NetFile", "CAL-ACCESS", "contribution", "dedup"],
        },
    ),
    BenchmarkCase(
        task="Understand the judgment boundary system",
        category="process",
        expected_files=[
            ".claude/rules/judgment-boundaries.md",
            ".claude/rules/team-operations.md",
            "CLAUDE.md",
        ],
        expected_keywords={
            ".claude/rules/judgment-boundaries.md": ["AI-delegable", "judgment call", "override"],
            "CLAUDE.md": ["judgment-boundary", "relentless"],
        },
    ),
]


@dataclass
class BenchmarkResult:
    total_cases: int = 0
    fully_covered: int = 0
    partially_covered: int = 0
    uncovered: int = 0
    coverage_score: float = 0.0
    issues: list[str] = field(default_factory=list)
    case_details: list[dict] = field(default_factory=list)


def run_documentation_benchmark(project_root: Path) -> BenchmarkResult:
    """Run the documentation architecture benchmark.

    For each task type, checks that expected files exist and contain
    expected keywords. Produces a coverage score and list of issues.
    """
    result = BenchmarkResult(total_cases=len(BENCHMARK_CASES))

    for case in BENCHMARK_CASES:
        detail: dict = {
            "task": case.task,
            "category": case.category,
            "status": "covered",
            "missing_files": [],
            "missing_keywords": {},
        }

        # Check file existence
        for rel_path in case.expected_files:
            full_path = project_root / rel_path
            if not full_path.exists():
                detail["missing_files"].append(rel_path)

        # Check keyword presence
        for rel_path, keywords in case.expected_keywords.items():
            full_path = project_root / rel_path
            if not full_path.exists():
                detail["missing_keywords"][rel_path] = keywords
                continue

            try:
                content = full_path.read_text(encoding="utf-8").lower()
            except Exception:
                detail["missing_keywords"][rel_path] = keywords
                continue

            missing = [kw for kw in keywords if kw.lower() not in content]
            if missing:
                detail["missing_keywords"][rel_path] = missing

        # Score this case
        has_file_issues = len(detail["missing_files"]) > 0
        has_keyword_issues = len(detail["missing_keywords"]) > 0

        if has_file_issues or has_keyword_issues:
            if has_file_issues and len(detail["missing_files"]) == len(case.expected_files):
                detail["status"] = "uncovered"
                result.uncovered += 1
            else:
                detail["status"] = "partial"
                result.partially_covered += 1

            # Log specific issues
            for f in detail["missing_files"]:
                result.issues.append(f"[{case.task}] Missing file: {f}")
            for f, kws in detail["missing_keywords"].items():
                result.issues.append(
                    f"[{case.task}] Missing keywords in {f}: {', '.join(kws)}"
                )
        else:
            result.fully_covered += 1

        result.case_details.append(detail)

    if result.total_cases > 0:
        result.coverage_score = round(result.fully_covered / result.total_cases, 3)

    return result


# ── Documentation Drift Detection ─────────────────────────────

# Patterns to find file references in markdown
_FILE_REF_PATTERNS = [
    re.compile(r"`([a-zA-Z_./-]+\.[a-z]{1,4})`"),  # `filename.ext`
    re.compile(r"`([a-zA-Z_/-]+/)`"),  # `directory/`
]

# Markdown link targets with a path separator and an extension —
# these are unambiguous file references that the project_root-relative
# check should always resolve. Catches sub-directory references that
# the bare-filename patterns above lose context for.
_MARKDOWN_LINK_PATH_PATTERN = re.compile(r"\]\(([a-zA-Z_./-]+/[a-zA-Z_./-]+\.[a-z]{1,4})\)")


def detect_documentation_drift(project_root: Path) -> list[str]:
    """Find file/directory references in CLAUDE.md files that don't exist.

    Uses context-aware resolution: CLAUDE.md files reference paths relative
    to various directories (docs/, .claude/rules/, web/src/, etc.), so we
    try multiple resolution strategies before flagging as drift.
    """
    claude_files = [
        project_root / "CLAUDE.md",
        project_root / "src" / "CLAUDE.md",
        project_root / "web" / "CLAUDE.md",
    ]
    for rule_file in sorted((project_root / ".claude" / "rules").glob("*.md")):
        claude_files.append(rule_file)

    # Context-aware search directories: where to look for referenced files
    # beyond the standard project_root and file-relative paths
    context_dirs = [
        project_root / "docs",
        project_root / ".claude" / "rules",
        project_root / ".github" / "workflows",
        project_root / "web" / "src",
        project_root / "web" / "src" / "app",
        project_root / "web" / "src" / "lib",
        project_root / "web" / "src" / "lib" / "queries",
        project_root / "web" / "src" / "components",
        project_root / "src",
        project_root / "src" / "migrations",
        project_root / "src" / "prompts",
        project_root / "tests",
    ]

    drift_issues: list[str] = []
    # Paths that are patterns, examples, or non-filesystem references
    skip_patterns = {
        "00N_description.sql",
        ".env.example",
        ".env",
        "sk-ant-...",
        "api-CqnnFGtv.js",  # External NextRequest SPA bundle reference, not a local file
    }

    for claude_file in claude_files:
        if not claude_file.exists():
            continue

        content = claude_file.read_text(encoding="utf-8")
        rel_claude = str(claude_file.relative_to(project_root))

        # Build a set of file paths that appear as markdown link
        # targets in this document. These are unambiguous: the link
        # target IS a file path, no resolution needed. We use this set
        # to suppress false positives on bare backtick references whose
        # full path is given in the same markdown link.
        link_target_basenames: set[str] = set()
        for match in _MARKDOWN_LINK_PATH_PATTERN.finditer(content):
            link_path = match.group(1)
            if (project_root / link_path).exists():
                link_target_basenames.add(link_path.rsplit("/", 1)[-1])

        for pattern in _FILE_REF_PATTERNS:
            for match in pattern.finditer(content):
                ref = match.group(1)

                # Skip non-path references
                if ref in skip_patterns:
                    continue
                if ref.startswith("http") or ref.startswith("www."):
                    continue
                if ref.startswith("*.") or ref.startswith("**"):
                    continue
                # Skip URLs that leaked through (domain patterns)
                if re.search(r"\.[a-z]{2,}\.[a-z]{2,}", ref):
                    continue
                # Skip things that look like code, not paths
                if "(" in ref or ")" in ref or "=" in ref:
                    continue
                # Skip very short refs that are probably not paths
                if len(ref) < 4:
                    continue
                # Skip refs that look like config values or variables
                if ref.startswith("--") or ref.startswith("#"):
                    continue
                # Skip if a markdown link in the same document gives
                # this filename a full path target that resolves.
                if "/" not in ref and ref in link_target_basenames:
                    continue

                # Resolution strategy: try multiple locations
                found = False

                # 1. Exact path from project root
                if (project_root / ref).exists():
                    found = True

                # 2. Relative to the CLAUDE.md file's directory
                if not found and (claude_file.parent / ref).exists():
                    found = True

                # 3. Context-aware: try all known directories
                if not found:
                    for ctx_dir in context_dirs:
                        if (ctx_dir / ref).exists():
                            found = True
                            break

                # 4. Strip known prefixes and retry (e.g., "web/lib/x" -> "lib/x")
                if not found and "/" in ref:
                    parts = ref.split("/")
                    for i in range(1, len(parts)):
                        short_ref = "/".join(parts[i:])
                        for ctx_dir in context_dirs:
                            if (ctx_dir / short_ref).exists():
                                found = True
                                break
                        if found:
                            break

                if not found:
                    drift_issues.append(
                        f"[{rel_claude}] References '{ref}' — not found"
                    )

    return drift_issues


# ══════════════════════════════════════════════════════════════
# LAYER 2: Architecture Health Analysis
# ══════════════════════════════════════════════════════════════

@dataclass
class ArchitectureReport:
    modules_total: int = 0
    modules_with_tests: int = 0
    test_coverage_ratio: float = 0.0
    untested_modules: list[str] = field(default_factory=list)
    import_graph: dict[str, list[str]] = field(default_factory=dict)
    most_imported: list[tuple[str, int]] = field(default_factory=list)
    convention_issues: list[str] = field(default_factory=list)
    module_sizes: dict[str, int] = field(default_factory=dict)


def _extract_local_imports(filepath: Path, src_modules: set[str]) -> list[str]:
    """Parse a Python file's AST to find imports of local project modules."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in src_modules:
                    imports.append(base)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base = node.module.split(".")[0]
                if base in src_modules:
                    imports.append(base)

    return sorted(set(imports))


def _check_conventions(project_root: Path) -> list[str]:
    """Spot-check key conventions across the codebase."""
    issues: list[str] = []
    src_dir = project_root / "src"

    for py_file in sorted(src_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Check: future annotations import (type hint convention)
        if "def " in content and "from __future__ import annotations" not in content:
            issues.append(f"{py_file.name}: missing 'from __future__ import annotations'")

    return issues


def analyze_architecture(project_root: Path) -> ArchitectureReport:
    """Analyze module structure, test coverage, and conventions."""
    report = ArchitectureReport()
    src_dir = project_root / "src"
    test_dir = project_root / "tests"

    # Discover all src modules (top-level .py files + packages with __init__.py)
    src_modules: dict[str, Path] = {}
    for py_file in sorted(src_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        module_name = py_file.stem
        src_modules[module_name] = py_file
        report.module_sizes[module_name] = len(
            py_file.read_text(encoding="utf-8").splitlines()
        )
    # Packages (Phase 2.1+: db/, scanner/, pipelines/) — count total LOC across
    # __init__.py + submodules so size and import attribution stay realistic.
    for pkg_init in sorted(src_dir.glob("*/__init__.py")):
        pkg_name = pkg_init.parent.name
        if pkg_name.startswith("__"):
            continue
        src_modules[pkg_name] = pkg_init
        total_lines = 0
        for py in pkg_init.parent.rglob("*.py"):
            try:
                total_lines += len(py.read_text(encoding="utf-8").splitlines())
            except OSError:
                pass
        report.module_sizes[pkg_name] = total_lines

    report.modules_total = len(src_modules)

    # Discover test files and map to modules
    tested_modules: set[str] = set()
    if test_dir.exists():
        for test_file in test_dir.glob("test_*.py"):
            # Extract module name from test file name
            # test_conflict_scanner.py -> conflict_scanner
            # test_conflict_scanner_tiers.py -> conflict_scanner
            test_name = test_file.stem.removeprefix("test_")
            # Try exact match first
            if test_name in src_modules:
                tested_modules.add(test_name)
            else:
                # Try prefix match (test_conflict_scanner_tiers -> conflict_scanner)
                for mod_name in src_modules:
                    if test_name.startswith(mod_name):
                        tested_modules.add(mod_name)

    report.modules_with_tests = len(tested_modules)
    report.untested_modules = sorted(set(src_modules.keys()) - tested_modules)
    if report.modules_total > 0:
        report.test_coverage_ratio = round(
            report.modules_with_tests / report.modules_total, 3
        )

    # Build import graph
    src_module_names = set(src_modules.keys())
    import_counts: dict[str, int] = {m: 0 for m in src_module_names}

    for mod_name, mod_path in src_modules.items():
        imports = _extract_local_imports(mod_path, src_module_names)
        report.import_graph[mod_name] = imports
        for imp in imports:
            import_counts[imp] = import_counts.get(imp, 0) + 1

    # Sort by most imported (most depended-upon modules)
    report.most_imported = sorted(
        import_counts.items(), key=lambda x: x[1], reverse=True
    )[:10]

    # Convention checks
    report.convention_issues = _check_conventions(project_root)

    return report


# ══════════════════════════════════════════════════════════════
# LAYER 2b: Git-Derived Metrics
# ══════════════════════════════════════════════════════════════

@dataclass
class GitMetrics:
    total_commits: int = 0
    commits_in_period: int = 0
    period_days: int = 30
    most_changed_files: list[tuple[str, int]] = field(default_factory=list)
    rework_candidates: list[str] = field(default_factory=list)
    commit_categories: dict[str, int] = field(default_factory=dict)
    avg_commits_per_day: float = 0.0


def analyze_git_history(project_root: Path, days: int = 30) -> GitMetrics:
    """Analyze git history for churn, rework, and commit patterns."""
    metrics = GitMetrics(period_days=days)

    try:
        # Total commits
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=project_root,
        )
        if result.returncode == 0:
            metrics.total_commits = int(result.stdout.strip())

        # Commits in period
        result = subprocess.run(
            ["git", "rev-list", "--count", f"--since={days} days ago", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=project_root,
        )
        if result.returncode == 0:
            metrics.commits_in_period = int(result.stdout.strip())
            metrics.avg_commits_per_day = round(
                metrics.commits_in_period / max(days, 1), 1
            )

        # Most changed files in period
        result = subprocess.run(
            ["git", "log", f"--since={days} days ago", "--name-only",
             "--pretty=format:", "--diff-filter=AMRC"],
            capture_output=True, text=True, timeout=30,
            cwd=project_root,
        )
        if result.returncode == 0:
            file_counts: dict[str, int] = {}
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("commit "):
                    file_counts[line] = file_counts.get(line, 0) + 1

            sorted_files = sorted(
                file_counts.items(), key=lambda x: x[1], reverse=True
            )
            metrics.most_changed_files = sorted_files[:15]
            # Rework candidates: files changed 5+ times
            metrics.rework_candidates = [
                f for f, count in sorted_files if count >= 5
            ]

        # Commit message categories
        result = subprocess.run(
            ["git", "log", f"--since={days} days ago", "--pretty=format:%s"],
            capture_output=True, text=True, timeout=10,
            cwd=project_root,
        )
        if result.returncode == 0:
            categories: dict[str, int] = {}
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Extract prefix (feat:, fix:, docs:, etc.)
                if ":" in line and len(line.split(":")[0]) < 20:
                    prefix = line.split(":")[0].strip().lower()
                    # Normalize "phase 2" prefix
                    if prefix.startswith("phase"):
                        prefix = "phase"
                    categories[prefix] = categories.get(prefix, 0) + 1
                else:
                    categories["other"] = categories.get("other", 0) + 1

            metrics.commit_categories = dict(
                sorted(categories.items(), key=lambda x: x[1], reverse=True)
            )

    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

    return metrics


# ══════════════════════════════════════════════════════════════
# LAYER 3: Pipeline Instrumentation Helpers
# ══════════════════════════════════════════════════════════════

class PipelineTimer:
    """Context manager for timing pipeline stages.

    Usage:
        with PipelineTimer("scrape_escribemeetings") as timer:
            data = scrape_meeting(session, meeting)
        print(f"Scraping took {timer.elapsed:.1f}s")

    Collected timings can be aggregated into scan_runs.metadata.
    """

    def __init__(self, stage_name: str) -> None:
        self.stage_name = stage_name
        self.start_time: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self) -> PipelineTimer:
        self.start_time = time.time()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed = round(time.time() - self.start_time, 3)

    def to_dict(self) -> dict:
        return {"stage": self.stage_name, "elapsed_seconds": self.elapsed}


class PipelineMetricsCollector:
    """Collects timing and token metrics across pipeline stages.

    Usage:
        collector = PipelineMetricsCollector()

        with collector.time("scrape"):
            data = scrape()

        collector.record_tokens("extraction", input_tokens=10500, output_tokens=8900)

        # At the end, store in scan_runs.metadata
        metadata["pipeline_metrics"] = collector.to_dict()
    """

    def __init__(self) -> None:
        self.timings: list[dict] = []
        self.token_usage: list[dict] = []
        self._active_timer: PipelineTimer | None = None

    def time(self, stage_name: str) -> PipelineTimer:
        """Return a context manager that times a stage."""
        timer = PipelineTimer(stage_name)
        self.timings.append(timer.to_dict)  # Store reference, resolve on to_dict
        self._active_timer = timer
        return timer

    def record_tokens(
        self, operation: str, input_tokens: int, output_tokens: int,
        model: str = "claude-sonnet",
    ) -> None:
        """Record token usage for a Claude API call."""
        self.token_usage.append({
            "operation": operation,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model,
        })

    def to_dict(self) -> dict:
        timings = []
        for t in self.timings:
            if callable(t):
                timings.append(t())
            else:
                timings.append(t)
        total_input = sum(t["input_tokens"] for t in self.token_usage)
        total_output = sum(t["output_tokens"] for t in self.token_usage)
        return {
            "timings": timings,
            "token_usage": self.token_usage,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
        }


# ══════════════════════════════════════════════════════════════
# Report Generation
# ══════════════════════════════════════════════════════════════

HEALTH_REPORTS_DIR = Path("data/health_reports")


def analyze_pipeline_lineage(project_root: Path) -> dict:
    """Validate pipeline manifest against code and return results.

    Returns dict with keys: sources_code, sources_manifest, queries_code,
    queries_manifest, issues (list of strings), status (ok/drift).
    """
    try:
        sys.path.insert(0, str(project_root / "src"))
        from pipeline_map import (
            load_manifest,
            PipelineGraph,
            _extract_sync_sources_from_code,
            _extract_query_functions_from_code,
        )

        manifest_path = project_root / "docs" / "pipeline-manifest.yaml"
        if not manifest_path.exists():
            return {
                "sources_code": 0, "sources_manifest": 0,
                "queries_code": 0, "queries_manifest": 0,
                "issues": ["pipeline-manifest.yaml not found"],
                "status": "missing",
            }

        manifest = load_manifest(manifest_path)
        graph = PipelineGraph(manifest)

        code_sources = _extract_sync_sources_from_code()
        manifest_sources = {
            data.get("sync_key", name)
            for name, data in (manifest.get("sources") or {}).items()
        }
        code_queries = _extract_query_functions_from_code()
        manifest_queries = set((manifest.get("queries") or {}).keys())

        manifest_enrichments = set((manifest.get("enrichments") or {}).keys())
        manifest_all = manifest_sources | manifest_enrichments

        issues: list[str] = []
        for src in sorted(code_sources - manifest_all):
            issues.append(f"[SYNC_SOURCES] '{src}' in code but missing from manifest")
        for src in sorted(manifest_all - code_sources):
            issues.append(f"[SYNC_SOURCES] '{src}' in manifest but not in code")
        for q in sorted(code_queries - manifest_queries):
            issues.append(f"[queries.ts] '{q}' in code but missing from manifest")
        for q in sorted(manifest_queries - code_queries):
            issues.append(f"[queries.ts] '{q}' in manifest but not in code")

        return {
            "sources_code": len(code_sources),
            "sources_manifest": len(manifest_sources),
            "queries_code": len(code_queries),
            "queries_manifest": len(manifest_queries),
            "tables_manifest": len(manifest.get("tables") or {}),
            "enrichments_manifest": len(manifest.get("enrichments") or {}),
            "pages_manifest": len(manifest.get("pages") or {}),
            "graph_nodes": len(graph.nodes),
            "issues": issues,
            "status": "drift" if issues else "ok",
        }
    except Exception as e:
        return {
            "sources_code": 0, "sources_manifest": 0,
            "queries_code": 0, "queries_manifest": 0,
            "issues": [f"Pipeline lineage check failed: {e}"],
            "status": "error",
        }


# ══════════════════════════════════════════════════════════════
# LAYER 6: Operator Briefing (database-dependent, graceful fallback)
# ══════════════════════════════════════════════════════════════

DEFAULT_FIPS = "0660620"


def collect_operator_briefing(city_fips: str = DEFAULT_FIPS) -> dict:
    """Collect operator-relevant status from the database.

    Returns a dict with:
      - decision_queue: pending decisions summary + items
      - pipeline_freshness: recent sync status per source
      - migration_status: which migrations have corresponding tables
      - available: True if DB was reachable

    Gracefully returns {available: False} if DB connection fails —
    the rest of the health check is file-based and should not break.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env", override=True)
        from db import get_connection
        conn = get_connection()
    except Exception:
        return {"available": False, "error": "Database connection unavailable"}

    briefing: dict = {"available": True}

    try:
        cur = conn.cursor()

        # ── Decision Queue ──
        try:
            from decision_queue import get_decision_summary, get_pending
            summary = get_decision_summary(conn, city_fips)
            pending = get_pending(conn, city_fips)
            briefing["decision_queue"] = {
                "summary": summary,
                "items": [
                    {
                        "title": d["title"],
                        "description": d.get("description") or "",
                        "severity": d["severity"],
                        "type": d["decision_type"],
                        "age": str(d["created_at"]),
                    }
                    for d in pending[:10]  # Cap at 10 for brevity
                ],
            }
        except Exception:
            briefing["decision_queue"] = None

        # ── Pipeline Freshness ──
        try:
            cur.execute("""
                SELECT source,
                       MAX(completed_at) as last_sync,
                       MAX(CASE WHEN status = 'completed' THEN completed_at END) as last_success,
                       MAX(CASE WHEN status = 'failed' THEN completed_at END) as last_failure
                FROM data_sync_log
                WHERE city_fips = %s
                GROUP BY source
                ORDER BY source
            """, (city_fips,))
            rows = cur.fetchall()
            briefing["pipeline_freshness"] = [
                {
                    "source": row[0],
                    "last_sync": str(row[1]) if row[1] else None,
                    "last_success": str(row[2]) if row[2] else None,
                    "last_failure": str(row[3]) if row[3] else None,
                }
                for row in rows
            ]
        except Exception:
            briefing["pipeline_freshness"] = None

        # ── Pending Migrations (tables referenced in migrations but not in DB) ──
        try:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            existing_tables = {row[0] for row in cur.fetchall()}
            briefing["existing_tables"] = sorted(existing_tables)
        except Exception:
            briefing["existing_tables"] = None

        # ── OpenCorporates API Budget ──
        try:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE called_at > NOW() - INTERVAL '1 day') as daily,
                    COUNT(*) FILTER (WHERE called_at > NOW() - INTERVAL '1 month') as monthly
                FROM opencorporates_api_usage
            """)
            row = cur.fetchone()
            briefing["opencorporates_budget"] = {
                "daily_used": row[0] or 0,
                "monthly_used": row[1] or 0,
                "daily_limit": 50,
                "monthly_limit": 200,
            }
        except Exception:
            briefing["opencorporates_budget"] = None

    except Exception as e:
        briefing["error"] = str(e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return briefing


def format_operator_briefing(briefing: dict) -> str:
    """Format operator briefing as text for SessionStart output."""
    if not briefing.get("available"):
        # NB: do NOT use adjacent string-literal concatenation with `* 40`.
        # `"Operator Briefing\n" "-" * 40` parses as `("Operator Briefing\n-") * 40`
        # because Python first auto-concats the two adjacent literals into
        # `"Operator Briefing\n-"`, then `* 40` repeats THAT whole string 40
        # times. Symptom: the SessionStart hook output started with
        # "Operator Briefing\n-" repeated ~40 times. Explicit `+` keeps the
        # divider as a divider.
        return (
            "Operator Briefing\n"
            + "-" * 40 + "\n"
            + "  (Database unavailable — skipping operator briefing)\n"
        )

    lines: list[str] = []
    lines.append("Operator Briefing")
    lines.append("-" * 40)

    # Decision Queue
    dq = briefing.get("decision_queue")
    if dq and dq.get("summary", {}).get("total_pending", 0) > 0:
        summary = dq["summary"]
        count_parts = []
        for sev in ["critical", "high", "medium", "low", "info"]:
            cnt = summary["counts"].get(sev, 0)
            if cnt > 0:
                count_parts.append(f"{cnt} {sev}")
        lines.append(
            f"  Decisions pending: {summary['total_pending']} "
            f"({', '.join(count_parts)})"
        )
        for item in dq["items"][:5]:
            lines.append(f"    - [{item['severity']}] {item['title']}")
            # Show description (truncated) so generic auto-generated titles
            # like "Assessment finding: failure" don't hide the real content.
            desc = (item.get("description") or "").strip()
            if desc:
                # Collapse internal whitespace to keep one line readable.
                desc = " ".join(desc.split())
                if len(desc) > 130:
                    desc = desc[:127] + "..."
                lines.append(f"        {desc}")
    else:
        lines.append("  Decisions pending: 0")

    # Pipeline Freshness — only show actionable items (failures)
    pf = briefing.get("pipeline_freshness")
    if pf:
        failed: list[str] = []
        for src in pf:
            if src["last_failure"] and src["last_success"]:
                if src["last_failure"] > src["last_success"]:
                    failed.append(src["source"])
            elif src["last_failure"] and not src["last_success"]:
                failed.append(src["source"])

        if failed:
            lines.append(f"  Pipeline failures: {', '.join(failed)}")
        else:
            lines.append(f"  Pipeline: {len(pf)} sources tracked, no recent failures")
    elif pf is not None and len(pf) == 0:
        lines.append("  Pipeline: no sync log entries yet (syncs run via GitHub Actions)")
    else:
        lines.append("  Pipeline: (sync log unavailable)")

    # OpenCorporates Budget
    oc = briefing.get("opencorporates_budget")
    if oc:
        lines.append(
            f"  OC API budget: {oc['daily_used']}/{oc['daily_limit']} daily, "
            f"{oc['monthly_used']}/{oc['monthly_limit']} monthly"
        )

    lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# LAYER 7: Risk Summary (top-of-report attention surface)
# ══════════════════════════════════════════════════════════════
#
# The Risk Summary is the first thing the operator sees at every
# SessionStart. The goal is to surface what's at risk *right now*
# in ~5-10 lines, before any benchmark coverage or module health
# tables.
#
# Five signals, each gracefully degrading if its source is down:
#   1. commits_since_last_report — git log since the most recently
#      saved health_*.json timestamp (falls back to 24h window)
#   2. red_ci_runs — `gh run list` for recent failures (skipped if
#      `gh` CLI is not installed or not authenticated)
#   3. decision_queue_p0 — critical/high pending decisions (reuses
#      the already-collected operator_briefing.decision_queue, so
#      one less DB round-trip)
#   4. cost_to_date — month-to-date Anthropic spend from
#      pipeline_journal vs RICHMOND_API_MONTHLY_CAP_USD
#   5. cta — derived: present if any P0 condition is true
#
# Reordering rationale (T0.5 of plans/steady-crafting-island.md):
# the SessionStart hook previously led with Documentation
# Architecture Benchmark — a coverage table that changes maybe
# once per week. The operator's first 5 seconds of attention is
# now on what changed since they last looked, what's red, and
# what needs triage.

def collect_risk_summary(
    project_root: Path,
    briefing: dict | None = None,
) -> dict:
    """Collect risk-first signals for the top of the SessionStart brief.

    Each source degrades gracefully — a network or DB failure does
    not propagate, the missing piece becomes None in the returned
    dict and is omitted from the formatted output.
    """
    summary: dict = {
        "commits_since_last_report": None,
        "red_ci_runs": None,
        "decision_queue_p0": None,
        "cost_to_date": None,
        "monthly_cap": None,
        "pending_operator_review": None,
        "at_risk": False,
    }

    # ── 1. Commits since last health report (or last 24h) ──
    try:
        last_report_time = _last_health_report_timestamp(project_root)
        since_arg = last_report_time or "24 hours ago"
        result = subprocess.run(
            ["git", "log", f"--since={since_arg}", "--pretty=format:%h %s"],
            capture_output=True, text=True, timeout=10,
            cwd=project_root,
        )
        if result.returncode == 0:
            items = [line for line in result.stdout.strip().split("\n") if line]
            summary["commits_since_last_report"] = {
                "count": len(items),
                "since": since_arg,
                "items": items[:5],
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

    # ── 2. Recent RED CI runs (via gh CLI) ──
    # Failing silently if `gh` is unavailable is correct — local dev
    # may not have it installed. The CI signal degrades but the rest
    # of the brief still produces.
    try:
        result = subprocess.run(
            ["gh", "run", "list", "--limit", "10",
             "--json", "conclusion,workflowName,headBranch,databaseId,createdAt"],
            capture_output=True, text=True, timeout=15,
            cwd=project_root,
        )
        if result.returncode == 0:
            runs = json.loads(result.stdout)
            red = [r for r in runs if r.get("conclusion") == "failure"]
            summary["red_ci_runs"] = {
                "checked": len(runs),
                "failed": len(red),
                "items": [
                    {
                        "workflow": r.get("workflowName"),
                        "branch": r.get("headBranch"),
                        "id": r.get("databaseId"),
                    }
                    for r in red[:3]
                ],
            }
            if red:
                summary["at_risk"] = True
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass

    # ── 3. Decision queue P0 (reuse already-collected briefing) ──
    if briefing and briefing.get("available"):
        dq = briefing.get("decision_queue") or {}
        items = dq.get("items") or []
        p0 = [
            i for i in items
            if i.get("severity") in ("critical", "high")
        ]
        if p0:
            summary["decision_queue_p0"] = {
                "count": len(p0),
                "items": p0[:5],
            }
            summary["at_risk"] = True
        else:
            # DB reachable and we asked — report the honest zero,
            # so the operator can distinguish "no P0s" from "no data."
            summary["decision_queue_p0"] = {"count": 0, "items": []}

    # ── 4. Cost to date (month-to-date Anthropic spend) ──
    try:
        cap_env = os.getenv("RICHMOND_API_MONTHLY_CAP_USD", "5.00")
        cap = float(cap_env)
        summary["monthly_cap"] = cap

        if briefing and briefing.get("available"):
            cost = _read_monthly_anthropic_cost()
            if cost is not None:
                summary["cost_to_date"] = round(cost, 2)
                if cost >= cap:
                    summary["at_risk"] = True
    except (ValueError, TypeError):
        pass

    # ── 5. Pending operator review (gated UI awaiting graduation) ──
    # Local YAML, no network/DB — can't fail in the same ways as cost
    # or DQ. Surfaces the count + a few oldest entries so the operator
    # can see what's still floating in operator-mode limbo. Does NOT
    # set at_risk — these are long-standing obligations, not urgent
    # triage. See docs/operator-review-queue.yaml and the contract
    # documented in .claude/rules/conventions.md.
    summary["pending_operator_review"] = _collect_pending_operator_review(project_root)

    # ── 6. Migration ledger drift (every-session detector) ──
    # The supabase_migrations ledger must stay in lockstep with the
    # committed supabase/migrations/ filenames; one mismatched row
    # HARD-BREAKS `supabase db push` (and the Schema Drift CI gate) for
    # ALL future migrations. This is the structural fix for the recurring
    # "applied SQL directly, recorded a mismatched version" drift that sat
    # unseen for two weeks (only surfacing on the next migration PR). See
    # src/migration_ledger.py for the full contract + `--fix`.
    try:
        from migration_ledger import summarize as _ledger_summarize
        ledger = _ledger_summarize(project_root)
        if ledger is not None:
            summary["migration_ledger"] = ledger
            if not ledger["clean"]:
                summary["at_risk"] = True
    except Exception:
        # Detector must never break the brief — soft-skip on any failure.
        pass

    return summary


def _collect_pending_operator_review(project_root: Path) -> dict | None:
    """Read operator-review-queue.yaml and return pending_graduation summary.

    Returns:
        dict with `count` (int), `oldest_age_days` (int|None), and `items`
        (list of {id, gated_at, file} for oldest 3), OR None if the file
        is missing/unparseable (treated as soft skip — don't break the
        whole brief over a YAML hiccup).
    """
    try:
        import yaml
        path = project_root / "docs" / "operator-review-queue.yaml"
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        gates = [g for g in (data.get("gates") or [])
                 if g.get("category") == "pending_graduation"]
        if not gates:
            return {"count": 0, "oldest_age_days": None, "items": []}

        # Sort by gated_at ascending (oldest first). YAML may parse dates
        # as `date` objects; str() handles both cleanly.
        gates_sorted = sorted(gates, key=lambda g: str(g.get("gated_at", "")))
        from datetime import date, datetime
        today = date.today()

        def _age_days(g: dict) -> int | None:
            raw = g.get("gated_at")
            if isinstance(raw, date):
                gated = raw
            elif isinstance(raw, str):
                try:
                    gated = datetime.strptime(raw, "%Y-%m-%d").date()
                except ValueError:
                    return None
            else:
                return None
            return (today - gated).days

        oldest_age = _age_days(gates_sorted[0])
        items = [
            {
                "id": g["id"],
                "gated_at": str(g.get("gated_at", "")),
                "file": g.get("file", ""),
                "view_at": g.get("view_at", ""),
                "age_days": _age_days(g),
            }
            for g in gates_sorted[:3]
        ]
        return {
            "count": len(gates),
            "oldest_age_days": oldest_age,
            "items": items,
        }
    except Exception:
        # YAML parse error, missing pyyaml, etc. Soft-skip rather than
        # blowing up the whole brief.
        return None


def _last_health_report_timestamp(project_root: Path) -> str | None:
    """Return the timestamp string of the most recent saved report, or None.

    Used as `--since` for `git log` so the brief shows
    'commits since you last looked' instead of a fixed 24h window.
    The report's `generated_at` is ISO 8601 with Z, which git
    understands directly.
    """
    reports_dir = project_root / "src" / HEALTH_REPORTS_DIR
    if not reports_dir.exists():
        return None
    reports = sorted(reports_dir.glob("health_*.json"), reverse=True)
    if not reports:
        return None
    try:
        with open(reports[0], encoding="utf-8") as f:
            data = json.load(f)
        return data.get("generated_at")
    except (OSError, json.JSONDecodeError):
        return None


def _read_monthly_anthropic_cost() -> float | None:
    """Return month-to-date Anthropic spend from pipeline_journal.

    Reads from `pipeline_journal` entries with `entry_type='api_cost'`
    in the current month. The Anthropic budget lock writes one such
    entry per API call (see src/anthropic_budget_lock.py).

    Returns None if the journal is unreachable (DB error, table missing,
    etc.). Returns 0.0 if reachable but empty. Caller treats None as
    "skip the line in the formatted output."

    Schema note (fixed 2026-05-17): the journal column is `metrics`
    (jsonb), not `payload`, and the cost key is `approx_cost` (matching
    PipelineJournal.log_api_cost), not `cost_usd`. The original buggy
    query referenced a non-existent column; the try/except caught the
    error silently and the SessionStart brief showed "no cost data" for
    a month while real spend ran ~$1.82. Caught by the explicit shape
    test in tests/test_system_health.py::TestReadMonthlyAnthropicCost.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env", override=True)
        from db import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(SUM(
                        (metrics->>'approx_cost')::numeric
                    ), 0)
                    FROM pipeline_journal
                    WHERE entry_type = 'api_cost'
                      AND created_at >= date_trunc('month', NOW())
                """)
                row = cur.fetchone()
                return float(row[0]) if row and row[0] is not None else 0.0
        finally:
            conn.close()
    except Exception:
        return None


def format_risk_summary(summary: dict) -> str:
    """Format the risk summary as the very top of the SessionStart brief.

    Sparse data degrades silently — if a signal is None, its line is
    omitted entirely rather than printing "unavailable" noise. The
    structure is designed to be scannable in under 5 seconds.
    """
    lines: list[str] = []
    lines.append("Risk / Action Queue")
    lines.append("=" * 60)

    # 1. Commits since last session
    commits = summary.get("commits_since_last_report")
    if commits is not None:
        n = commits["count"]
        since = commits["since"]
        if n == 0:
            lines.append(f"  Commits since {since}: 0")
        else:
            lines.append(f"  Commits since {since}: {n}")
            for item in commits["items"][:3]:
                lines.append(f"    - {item}")
            if n > 3:
                lines.append(f"    ... and {n - 3} more")

    # 2. RED CI runs
    ci = summary.get("red_ci_runs")
    if ci is not None:
        if ci["failed"] == 0:
            lines.append(f"  CI status (last {ci['checked']} runs): all green")
        else:
            lines.append(
                f"  CI status (last {ci['checked']} runs): "
                f">> {ci['failed']} RED <<"
            )
            for r in ci["items"]:
                lines.append(
                    f"    - {r['workflow']} on {r['branch']} "
                    f"(run {r['id']})"
                )

    # 3. Decision queue P0
    dq = summary.get("decision_queue_p0")
    if dq is not None:
        if dq["count"] == 0:
            lines.append("  Decisions pending (P0): 0")
        else:
            lines.append(f"  Decisions pending (P0): {dq['count']}")
            for item in dq["items"]:
                lines.append(f"    - [{item['severity']}] {item['title']}")
    # If dq is None: DB unavailable. Don't lie about a zero count.

    # 4. Cost to date
    cost = summary.get("cost_to_date")
    cap = summary.get("monthly_cap")
    if cost is not None and cap:
        pct = round(100 * cost / cap) if cap else 0
        if cost >= cap:
            lines.append(
                f"  Cost this month: ${cost:.2f} / ${cap:.2f} "
                f">> CAP HIT ({pct}%) <<"
            )
        else:
            lines.append(
                f"  Cost this month: ${cost:.2f} / ${cap:.2f} ({pct}%)"
            )

    # 5. Pending operator review (gated UI awaiting graduation)
    por = summary.get("pending_operator_review")
    if por is not None:
        n = por["count"]
        if n == 0:
            lines.append("  Pending operator review: 0 gates")
        else:
            oldest = por.get("oldest_age_days")
            age_str = (
                f", oldest {oldest} days" if isinstance(oldest, int) else ""
            )
            lines.append(
                f"  Pending operator review: {n} gates{age_str}"
            )
            for item in por["items"]:
                age = item.get("age_days")
                age_label = f"{age}d" if isinstance(age, int) else "?"
                view_at = item.get("view_at") or ""
                # Lead with the URL the operator opens — that's the
                # action. File path is supporting detail (where in code
                # the gate lives) and we keep id for cross-reference.
                if view_at:
                    lines.append(
                        f"    - {item['id']} ({age_label}) — view: {view_at}"
                    )
                else:
                    # Defensive — the test enforces view_at exists for
                    # pending_graduation, but be honest if it's missing.
                    lines.append(
                        f"    - {item['id']} ({age_label}) — {item['file']} (no view_at)"
                    )
            if n > len(por["items"]):
                lines.append(f"    ... and {n - len(por['items'])} more")
            lines.append(
                "    Operator login: /operator/login · full list + checklists: docs/operator-review-queue.yaml"
            )

    # 5b. Migration ledger drift (breaks `supabase db push` if out of sync)
    ledger = summary.get("migration_ledger")
    if ledger is not None:
        if ledger["clean"]:
            lines.append("  Migration ledger: in sync")
        else:
            lines.append(
                f"  Migration ledger: >> {ledger['drift_count']} DRIFT <<  "
                f"(remap {ledger['remappable']}, "
                f"orphan {ledger['orphan_ledger']}, "
                f"unrecorded {ledger['unrecorded_local']})"
            )
            for dline in (ledger.get("detail") or "").splitlines():
                lines.append(f"    {dline}")
            lines.append(
                "    Fix safe cases: python src/migration_ledger.py --fix  "
                "(breaks `supabase db push` until resolved)"
            )

    # 6. CTA — derived
    if summary.get("at_risk"):
        lines.append("")
        lines.append(
            "  >> Triage required. "
            "Review P0 items above before continuing other work. <<"
        )

    lines.append("")
    return "\n".join(lines)


def analyze_pipeline_liveness(project_root: Path) -> dict:
    """Run pipeline expectation checks against the live database.

    This is the runtime counterpart to analyze_pipeline_lineage:
    static lineage answers "where could data go?", liveness answers
    "did the latest record actually flow through?"

    Returns dict with keys: total, passing, failing, errored, failures,
    status (ok/issues/error/skipped). Gracefully returns {"status":"skipped"}
    when DB is unavailable so the rest of the health check still runs.
    """
    try:
        sys.path.insert(0, str(project_root / "src"))
        from pipeline_map import load_manifest, run_liveness_checks

        manifest = load_manifest(project_root / "docs" / "pipeline-manifest.yaml")
        expectations = manifest.get("expectations") or []
        if not expectations:
            return {
                "total": 0,
                "passing": 0,
                "failing": 0,
                "errored": 0,
                "failures": [],
                "status": "skipped",
                "reason": "no expectations declared",
            }

        results = run_liveness_checks(expectations)

        n_pass = sum(1 for r in results if r["status"] == "pass")
        n_fail = sum(1 for r in results if r["status"] == "fail")
        n_error = sum(1 for r in results if r["status"] == "error")
        n_skip = sum(1 for r in results if r["status"] == "skipped")

        failures: list[dict] = []
        for r in results:
            if r["status"] in ("fail", "error"):
                exp = r["expectation"]
                failures.append({
                    "id": r["id"],
                    "owner": exp.get("owner", "?"),
                    "severity": exp.get("severity", "info"),
                    "status": r["status"],
                    "count": len(r.get("failures", [])),
                    "description": exp.get("description", ""),
                    "reason": r.get("reason"),
                    "examples": [f.get("detail") for f in r.get("failures", [])[:3]],
                })

        # Paused (skipped) expectations are not failures and not passes —
        # they're intentionally silenced (e.g., `pause_when_env:
        # RICHMOND_API_BUDGET_LOCK` while the audit is in flight). Surface
        # them at the bottom of the section so the operator still knows
        # what coverage is currently disabled.
        paused: list[dict] = []
        for r in results:
            if r["status"] == "skipped":
                exp = r["expectation"]
                paused.append({
                    "id": r["id"],
                    "owner": exp.get("owner", "?"),
                    "severity": exp.get("severity", "info"),
                    "reason": r.get("reason", "skipped"),
                })

        return {
            "total": len(results),
            "passing": n_pass,
            "failing": n_fail,
            "errored": n_error,
            "skipped": n_skip,
            "failures": failures,
            "paused": paused,
            "status": "ok" if (n_fail + n_error) == 0 else "issues",
        }
    except Exception as e:
        return {
            "total": 0, "passing": 0, "failing": 0, "errored": 0,
            "failures": [],
            "status": "error",
            "reason": str(e)[:200],
        }


def collect_full_report(project_root: Path, git_days: int = 30) -> dict:
    """Run all health checks and return structured report."""
    benchmark = run_documentation_benchmark(project_root)
    drift = detect_documentation_drift(project_root)
    architecture = analyze_architecture(project_root)
    git = analyze_git_history(project_root, days=git_days)
    lineage = analyze_pipeline_lineage(project_root)
    liveness = analyze_pipeline_liveness(project_root)

    # Operator briefing (DB-dependent, graceful fallback)
    operator = collect_operator_briefing()
    # Risk summary leads the formatted report. Collected AFTER operator
    # briefing so it can reuse the already-fetched decision_queue items
    # without a second DB round-trip.
    risk = collect_risk_summary(project_root, operator)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project_root": str(project_root),
        "risk_summary": risk,
        "operator_briefing": operator,
        "documentation_benchmark": asdict(benchmark),
        "documentation_drift": drift,
        "architecture": asdict(architecture),
        "git_metrics": asdict(git),
        "pipeline_lineage": lineage,
        "pipeline_liveness": liveness,
    }


def save_report(report: dict, project_root: Path) -> Path:
    """Save report to data/health_reports/ with timestamp filename.

    Returns the path to the saved file. Reports accumulate over time
    so trend analysis can compare snapshots.
    """
    reports_dir = project_root / "src" / HEALTH_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = report["generated_at"].replace(":", "").replace("-", "")
    filename = f"health_{timestamp}.json"
    filepath = reports_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return filepath


def load_previous_report(project_root: Path) -> dict | None:
    """Load the most recent saved report for trend comparison."""
    reports_dir = project_root / "src" / HEALTH_REPORTS_DIR
    if not reports_dir.exists():
        return None

    reports = sorted(reports_dir.glob("health_*.json"), reverse=True)
    if not reports:
        return None

    with open(reports[0], encoding="utf-8") as f:
        return json.load(f)


def format_trend_comparison(current: dict, previous: dict) -> str:
    """Compare two reports and return a summary of changes."""
    lines: list[str] = []
    lines.append("Trend (vs. previous report)")
    lines.append("-" * 40)
    lines.append(f"  Previous: {previous['generated_at']}")
    lines.append(f"  Current:  {current['generated_at']}")
    lines.append("")

    cb = current["documentation_benchmark"]
    pb = previous["documentation_benchmark"]
    cov_delta = cb["coverage_score"] - pb["coverage_score"]
    cov_arrow = "+" if cov_delta > 0 else "" if cov_delta == 0 else ""
    lines.append(
        f"  Doc benchmark:  {pb['coverage_score']:.0%} -> {cb['coverage_score']:.0%} "
        f"({cov_arrow}{cov_delta:+.0%})"
    )

    ca = current["architecture"]
    pa = previous["architecture"]
    test_delta = ca["test_coverage_ratio"] - pa["test_coverage_ratio"]
    lines.append(
        f"  Test coverage:  {pa['test_coverage_ratio']:.0%} -> {ca['test_coverage_ratio']:.0%} "
        f"({test_delta:+.0%})"
    )
    lines.append(
        f"  Module count:   {pa['modules_total']} -> {ca['modules_total']} "
        f"({ca['modules_total'] - pa['modules_total']:+d})"
    )

    cd = current.get("documentation_drift", [])
    pd = previous.get("documentation_drift", [])
    lines.append(
        f"  Drift issues:   {len(pd)} -> {len(cd)} "
        f"({len(cd) - len(pd):+d})"
    )

    cc = ca.get("convention_issues", [])
    pc = pa.get("convention_issues", [])
    lines.append(
        f"  Convention issues: {len(pc)} -> {len(cc)} "
        f"({len(cc) - len(pc):+d})"
    )

    cg = current["git_metrics"]
    pg = previous["git_metrics"]
    lines.append(
        f"  Commits/day:    {pg['avg_commits_per_day']} -> {cg['avg_commits_per_day']}"
    )

    lines.append("")
    return "\n".join(lines)


def format_text_report(report: dict) -> str:
    """Format full report as human-readable text."""
    lines: list[str] = []

    lines.append("System Health Report")
    lines.append("=" * 60)
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")

    # ── Risk / Action Queue (TOP — first 5 seconds of attention) ──
    # See LAYER 7 comment block above collect_risk_summary for rationale.
    risk = report.get("risk_summary")
    if risk:
        lines.append(format_risk_summary(risk))

    # ── Operator Briefing (decision-queue detail + freshness) ──
    operator = report.get("operator_briefing")
    if operator:
        lines.append(format_operator_briefing(operator))

    # ── Documentation Benchmark ──
    bench = report["documentation_benchmark"]
    lines.append("Documentation Architecture Benchmark")
    lines.append("-" * 40)
    lines.append(
        f"  Coverage: {bench['fully_covered']}/{bench['total_cases']} tasks "
        f"fully covered ({bench['coverage_score']:.0%})"
    )
    lines.append(f"  Partial:  {bench['partially_covered']}")
    lines.append(f"  Missing:  {bench['uncovered']}")

    if bench["issues"]:
        lines.append("")
        lines.append("  Issues:")
        for issue in bench["issues"]:
            lines.append(f"    - {issue}")

    # Per-category breakdown
    categories: dict[str, list[dict]] = {}
    for case in bench["case_details"]:
        cat = case["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(case)

    lines.append("")
    lines.append("  By category:")
    for cat, cases in sorted(categories.items()):
        covered = sum(1 for c in cases if c["status"] == "covered")
        lines.append(f"    {cat:20s} {covered}/{len(cases)} covered")

    lines.append("")

    # ── Documentation Drift ──
    drift = report["documentation_drift"]
    lines.append("Documentation Drift")
    lines.append("-" * 40)
    if drift:
        lines.append(f"  {len(drift)} stale reference(s) found:")
        for issue in drift:
            lines.append(f"    - {issue}")
    else:
        lines.append("  No drift detected — all file references are valid")
    lines.append("")

    # ── Architecture Health ──
    arch = report["architecture"]
    lines.append("Architecture Health")
    lines.append("-" * 40)
    lines.append(
        f"  Modules: {arch['modules_total']} total, "
        f"{arch['modules_with_tests']} tested "
        f"({arch['test_coverage_ratio']:.0%})"
    )

    if arch["untested_modules"]:
        lines.append(f"  Untested: {', '.join(arch['untested_modules'])}")

    lines.append("")
    lines.append("  Most depended-upon modules:")
    for mod, count in arch["most_imported"][:7]:
        lines.append(f"    {mod:30s} imported by {count} modules")

    # Module sizes
    if arch["module_sizes"]:
        lines.append("")
        lines.append("  Largest modules (lines):")
        sorted_sizes = sorted(
            arch["module_sizes"].items(), key=lambda x: x[1], reverse=True
        )
        for mod, size in sorted_sizes[:7]:
            lines.append(f"    {mod:30s} {size:,} lines")

    if arch["convention_issues"]:
        lines.append("")
        lines.append(f"  Convention issues ({len(arch['convention_issues'])}):")
        for issue in arch["convention_issues"]:
            lines.append(f"    - {issue}")
    lines.append("")

    # ── Pipeline Lineage ──
    lineage = report.get("pipeline_lineage")
    if lineage:
        lines.append("Pipeline Lineage")
        lines.append("-" * 40)
        if lineage["status"] == "ok":
            lines.append(
                f"  Sync sources: {lineage['sources_code']} in code, "
                f"{lineage['sources_manifest']} in manifest (OK)"
            )
            lines.append(
                f"  Query funcs:  {lineage['queries_code']} in code, "
                f"{lineage['queries_manifest']} in manifest (OK)"
            )
            lines.append(
                f"  Graph: {lineage.get('graph_nodes', '?')} nodes "
                f"({lineage.get('tables_manifest', '?')} tables, "
                f"{lineage.get('enrichments_manifest', '?')} enrichments, "
                f"{lineage.get('pages_manifest', '?')} pages)"
            )
        elif lineage["status"] == "missing":
            lines.append("  pipeline-manifest.yaml not found")
        else:
            lines.append(f"  Status: {lineage['status']}")

        if lineage.get("issues"):
            lines.append("")
            lines.append("  Issues:")
            for issue in lineage["issues"]:
                lines.append(f"    - {issue}")
        lines.append("")

    # ── Pipeline Liveness ──
    liveness = report.get("pipeline_liveness")
    if liveness:
        lines.append("Pipeline Liveness")
        lines.append("-" * 40)
        if liveness["status"] == "skipped":
            lines.append(f"  Skipped: {liveness.get('reason', '')}")
        elif liveness["status"] == "error":
            lines.append(f"  Error: {liveness.get('reason', '')[:120]}")
        else:
            n_total = liveness["total"]
            n_pass = liveness["passing"]
            n_fail = liveness["failing"]
            n_error = liveness["errored"]
            n_skip = liveness.get("skipped", 0)
            status_word = "OK" if liveness["status"] == "ok" else "issues"
            skip_str = f", {n_skip} paused" if n_skip else ""
            lines.append(
                f"  {n_total} expectation(s): {n_pass} passing, "
                f"{n_fail} failing, {n_error} errored{skip_str} ({status_word})"
            )

            paused = liveness.get("paused") or []
            if paused:
                lines.append("")
                lines.append("  Paused (intentional — see pause_when_env):")
                for p in paused[:10]:
                    lines.append(
                        f"    [..] {p['id']} (owner={p['owner']}, severity={p['severity']}) — {p.get('reason', '')}"
                    )
                if len(paused) > 10:
                    lines.append(f"    ... and {len(paused) - 10} more")

            failures = liveness.get("failures") or []
            if failures:
                # Sort by severity (high first), then status (error first)
                sev_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
                failures = sorted(
                    failures,
                    key=lambda f: (
                        0 if f["status"] == "error" else 1,
                        sev_order.get(f["severity"], 99),
                        f["id"],
                    ),
                )
                lines.append("")
                lines.append("  Failures:")
                for f in failures[:10]:
                    sev_icon = {"high": "!!", "medium": "!", "low": ".", "info": " "}.get(
                        f["severity"], " "
                    )
                    if f["status"] == "error":
                        lines.append(
                            f"    [??] {f['id']} (owner={f['owner']}): "
                            f"errored — {f.get('reason', '')[:80]}"
                        )
                    else:
                        lines.append(
                            f"    [{sev_icon}] {f['id']} "
                            f"(owner={f['owner']}, {f['count']} failure"
                            f"{'s' if f['count'] != 1 else ''}, severity={f['severity']})"
                        )
                        if f.get("examples"):
                            for ex in f["examples"][:2]:
                                if ex:
                                    lines.append(f"         {ex}")
                if len(failures) > 10:
                    lines.append(f"    ... and {len(failures) - 10} more")
        lines.append("")

    # ── Git Metrics ──
    git = report["git_metrics"]
    lines.append("Git Metrics")
    lines.append("-" * 40)
    lines.append(f"  Total commits: {git['total_commits']}")
    lines.append(
        f"  Last {git['period_days']} days: {git['commits_in_period']} commits "
        f"({git['avg_commits_per_day']}/day)"
    )

    if git["commit_categories"]:
        lines.append("")
        lines.append("  Commit categories:")
        for cat, count in git["commit_categories"].items():
            lines.append(f"    {cat:20s} {count}")

    if git["most_changed_files"]:
        lines.append("")
        lines.append("  Most changed files:")
        for f, count in git["most_changed_files"][:10]:
            marker = " ** REWORK" if count >= 5 else ""
            lines.append(f"    {count:3d}x  {f}{marker}")

    if git["rework_candidates"]:
        lines.append("")
        lines.append(
            f"  Rework candidates ({len(git['rework_candidates'])} files "
            f"changed 5+ times):"
        )
        for f in git["rework_candidates"]:
            lines.append(f"    - {f}")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — System Health & Self-Assessment"
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--benchmark-only", action="store_true",
        help="Only run the documentation benchmark",
    )
    parser.add_argument(
        "--architecture-only", action="store_true",
        help="Only run architecture analysis",
    )
    parser.add_argument(
        "--git-only", action="store_true",
        help="Only run git metrics analysis",
    )
    parser.add_argument(
        "--git-days", type=int, default=30,
        help="Number of days for git history analysis (default: 30)",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Don't save report to data/health_reports/",
    )
    args = parser.parse_args()

    project_root = _find_project_root()

    if args.benchmark_only:
        benchmark = run_documentation_benchmark(project_root)
        drift = detect_documentation_drift(project_root)
        if args.format == "json":
            print(json.dumps({"benchmark": asdict(benchmark), "drift": drift}, indent=2))
        else:
            report = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "documentation_benchmark": asdict(benchmark),
                "documentation_drift": drift,
                "architecture": {
                    "modules_total": 0, "modules_with_tests": 0,
                    "test_coverage_ratio": 0, "untested_modules": [],
                    "most_imported": [], "convention_issues": [],
                    "module_sizes": {},
                },
                "git_metrics": {
                    "total_commits": 0, "commits_in_period": 0,
                    "period_days": 0, "most_changed_files": [],
                    "rework_candidates": [], "commit_categories": {},
                    "avg_commits_per_day": 0,
                },
            }
            print(format_text_report(report))
        return

    if args.architecture_only:
        architecture = analyze_architecture(project_root)
        if args.format == "json":
            print(json.dumps(asdict(architecture), indent=2))
        else:
            print(f"Modules: {architecture.modules_total} total, "
                  f"{architecture.modules_with_tests} tested")
            if architecture.untested_modules:
                print(f"Untested: {', '.join(architecture.untested_modules)}")
        return

    if args.git_only:
        git = analyze_git_history(project_root, days=args.git_days)
        if args.format == "json":
            print(json.dumps(asdict(git), indent=2))
        else:
            print(f"Commits (last {git.period_days}d): {git.commits_in_period}")
            if git.rework_candidates:
                print(f"Rework candidates: {', '.join(git.rework_candidates)}")
        return

    # Full report
    report = collect_full_report(project_root, git_days=args.git_days)

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_text_report(report))

        # Show trend comparison if a previous report exists
        previous = load_previous_report(project_root)
        if previous:
            print()
            print(format_trend_comparison(report, previous))

    # Save report by default (unless --no-save or subset mode)
    if not args.no_save:
        filepath = save_report(report, project_root)
        print(f"\nReport saved to {filepath.relative_to(project_root)}")


if __name__ == "__main__":
    main()
