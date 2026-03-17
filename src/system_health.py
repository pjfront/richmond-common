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
            "CLAUDE.md": ["sunlight", "surveillance", "free public access"],
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
        project_root / "web" / "src" / "components",
        project_root / "src",
        project_root / "src" / "migrations",
        project_root / "tests",
    ]

    drift_issues: list[str] = []
    # Paths that are patterns, examples, or non-filesystem references
    skip_patterns = {
        "00N_description.sql",
        ".env.example",
        ".env",
        "sk-ant-...",
    }

    for claude_file in claude_files:
        if not claude_file.exists():
            continue

        content = claude_file.read_text(encoding="utf-8")
        rel_claude = str(claude_file.relative_to(project_root))

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

    # Discover all src modules
    src_modules: dict[str, Path] = {}
    for py_file in sorted(src_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        module_name = py_file.stem
        src_modules[module_name] = py_file
        report.module_sizes[module_name] = len(
            py_file.read_text(encoding="utf-8").splitlines()
        )

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


def collect_full_report(project_root: Path, git_days: int = 30) -> dict:
    """Run all health checks and return structured report."""
    benchmark = run_documentation_benchmark(project_root)
    drift = detect_documentation_drift(project_root)
    architecture = analyze_architecture(project_root)
    git = analyze_git_history(project_root, days=git_days)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project_root": str(project_root),
        "documentation_benchmark": asdict(benchmark),
        "documentation_drift": drift,
        "architecture": asdict(architecture),
        "git_metrics": asdict(git),
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
