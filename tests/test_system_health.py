"""Tests for system_health.py — System Health & Self-Assessment module."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from system_health import (
    BENCHMARK_CASES,
    BenchmarkCase,
    BenchmarkResult,
    ArchitectureReport,
    GitMetrics,
    PipelineTimer,
    PipelineMetricsCollector,
    _find_project_root,
    run_documentation_benchmark,
    detect_documentation_drift,
    analyze_architecture,
    analyze_git_history,
    collect_full_report,
    format_text_report,
)


# ── Project Root Detection ────────────────────────────────────


def test_find_project_root_from_src():
    """Should find root starting from src/ directory."""
    root = _find_project_root(Path(__file__).parent.parent / "src")
    assert (root / "CLAUDE.md").exists()
    assert (root / "src").exists()


def test_find_project_root_from_tests():
    """Should find root starting from tests/ directory."""
    root = _find_project_root(Path(__file__).parent)
    assert (root / "CLAUDE.md").exists()


# ── Benchmark Data Quality ────────────────────────────────────


def test_benchmark_cases_not_empty():
    """Benchmark should have a meaningful number of cases."""
    assert len(BENCHMARK_CASES) >= 10


def test_benchmark_cases_have_all_fields():
    """Every benchmark case should have task, category, files, and keywords."""
    for case in BENCHMARK_CASES:
        assert case.task, f"Case missing task description"
        assert case.category, f"Case '{case.task}' missing category"
        assert len(case.expected_files) > 0, f"Case '{case.task}' has no expected files"
        assert len(case.expected_keywords) > 0, f"Case '{case.task}' has no expected keywords"


def test_benchmark_categories_are_valid():
    """All benchmark categories should be from a known set."""
    valid_categories = {"pipeline", "frontend", "infrastructure", "process", "analysis"}
    for case in BENCHMARK_CASES:
        assert case.category in valid_categories, (
            f"Case '{case.task}' has unknown category '{case.category}'"
        )


def test_benchmark_expected_files_are_relative():
    """Expected files should be relative paths (not absolute)."""
    for case in BENCHMARK_CASES:
        for f in case.expected_files:
            assert not f.startswith("/"), (
                f"Case '{case.task}' has absolute path: {f}"
            )


# ── Documentation Benchmark ──────────────────────────────────


def test_benchmark_runs_on_real_project():
    """Benchmark should produce results when run on the actual project."""
    root = _find_project_root(Path(__file__).parent)
    result = run_documentation_benchmark(root)

    assert result.total_cases == len(BENCHMARK_CASES)
    assert result.total_cases > 0
    assert 0.0 <= result.coverage_score <= 1.0
    assert result.fully_covered + result.partially_covered + result.uncovered == result.total_cases


def test_benchmark_coverage_above_minimum():
    """Benchmark coverage should be above 70% (our documentation is maintained)."""
    root = _find_project_root(Path(__file__).parent)
    result = run_documentation_benchmark(root)

    assert result.coverage_score >= 0.70, (
        f"Documentation coverage {result.coverage_score:.0%} is below 70% minimum. "
        f"Issues: {result.issues}"
    )


def test_benchmark_with_synthetic_case(tmp_path: Path):
    """Benchmark should work with synthetic test cases."""
    # Create minimal project structure
    (tmp_path / "CLAUDE.md").write_text("# Project\nThis is a test project with FIPS codes.")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# main module")

    # Temporarily override BENCHMARK_CASES
    test_cases = [
        BenchmarkCase(
            task="Test task that should pass",
            category="process",
            expected_files=["CLAUDE.md"],
            expected_keywords={"CLAUDE.md": ["project", "FIPS"]},
        ),
        BenchmarkCase(
            task="Test task that should fail",
            category="pipeline",
            expected_files=["nonexistent.py"],
            expected_keywords={"nonexistent.py": ["nothing"]},
        ),
    ]

    # Monkey-patch just for this test
    import system_health
    original = system_health.BENCHMARK_CASES
    system_health.BENCHMARK_CASES = test_cases
    try:
        result = run_documentation_benchmark(tmp_path)
        assert result.total_cases == 2
        assert result.fully_covered == 1
        assert result.coverage_score == 0.5
    finally:
        system_health.BENCHMARK_CASES = original


def test_benchmark_case_details_structure():
    """Each case detail should have the expected fields."""
    root = _find_project_root(Path(__file__).parent)
    result = run_documentation_benchmark(root)

    for detail in result.case_details:
        assert "task" in detail
        assert "category" in detail
        assert "status" in detail
        assert detail["status"] in ("covered", "partial", "uncovered")
        assert "missing_files" in detail
        assert "missing_keywords" in detail


# ── Documentation Drift ───────────────────────────────────────


def test_drift_detection_on_real_project():
    """Drift detection should run without errors on the actual project."""
    root = _find_project_root(Path(__file__).parent)
    issues = detect_documentation_drift(root)
    # Result is a list of strings (may be empty)
    assert isinstance(issues, list)


def test_drift_detects_bad_reference(tmp_path: Path):
    """Should detect a reference to a non-existent file."""
    (tmp_path / "CLAUDE.md").write_text(
        "Check `nonexistent_module.py` for details.\n"
        "Also see `real_file.py` for more.\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "real_file.py").write_text("# exists")

    issues = detect_documentation_drift(tmp_path)
    assert any("nonexistent_module.py" in issue for issue in issues)


def test_drift_ignores_urls(tmp_path: Path):
    """Should not flag URLs as missing files."""
    (tmp_path / "CLAUDE.md").write_text(
        "Visit `www.example.com` and `data.gov.org/api` for info.\n"
    )
    (tmp_path / "src").mkdir()

    issues = detect_documentation_drift(tmp_path)
    assert not any("example.com" in issue for issue in issues)
    assert not any("data.gov" in issue for issue in issues)


# ── Architecture Analysis ─────────────────────────────────────


def test_architecture_analysis_on_real_project():
    """Architecture analysis should produce meaningful results."""
    root = _find_project_root(Path(__file__).parent)
    report = analyze_architecture(root)

    assert report.modules_total > 20  # We have 34+ modules
    assert report.modules_with_tests > 10  # We have 22+ tested
    assert 0.0 <= report.test_coverage_ratio <= 1.0
    assert len(report.import_graph) > 0
    assert len(report.most_imported) > 0


def test_architecture_identifies_core_dependencies():
    """city_config and db should be among most imported modules."""
    root = _find_project_root(Path(__file__).parent)
    report = analyze_architecture(root)

    top_module_names = [name for name, _ in report.most_imported[:5]]
    assert "city_config" in top_module_names, (
        f"city_config should be a core dependency, top modules: {top_module_names}"
    )
    assert "db" in top_module_names, (
        f"db should be a core dependency, top modules: {top_module_names}"
    )


def test_architecture_module_sizes():
    """Module sizes should be populated and reasonable."""
    root = _find_project_root(Path(__file__).parent)
    report = analyze_architecture(root)

    assert len(report.module_sizes) == report.modules_total
    assert all(size > 0 for size in report.module_sizes.values())
    # conflict_scanner should be the largest
    assert report.module_sizes.get("conflict_scanner", 0) > 500


# ── Git Metrics ───────────────────────────────────────────────


def test_git_metrics_on_real_project():
    """Git analysis should produce results in a git repo."""
    root = _find_project_root(Path(__file__).parent)
    metrics = analyze_git_history(root, days=30)

    assert metrics.total_commits > 0
    assert metrics.commits_in_period >= 0
    assert metrics.avg_commits_per_day >= 0


def test_git_metrics_handles_missing_git(tmp_path: Path):
    """Git analysis should handle non-git directories gracefully."""
    metrics = analyze_git_history(tmp_path, days=30)
    # Should not crash, just return zeroed metrics
    assert metrics.total_commits == 0


# ── Pipeline Instrumentation ──────────────────────────────────


def test_pipeline_timer_basic():
    """PipelineTimer should measure elapsed time."""
    import time as _time

    with PipelineTimer("test_stage") as timer:
        _time.sleep(0.05)

    assert timer.stage_name == "test_stage"
    assert timer.elapsed >= 0.04  # Allow some tolerance
    assert timer.elapsed < 1.0

    d = timer.to_dict()
    assert d["stage"] == "test_stage"
    assert d["elapsed_seconds"] >= 0.04


def test_pipeline_metrics_collector():
    """Collector should aggregate timing and token metrics."""
    collector = PipelineMetricsCollector()

    with collector.time("scrape") as t:
        pass  # Instant

    collector.record_tokens("extraction", input_tokens=10500, output_tokens=8900)
    collector.record_tokens("analysis", input_tokens=5000, output_tokens=3000)

    result = collector.to_dict()
    assert len(result["timings"]) == 1
    assert result["timings"][0]["stage"] == "scrape"
    assert len(result["token_usage"]) == 2
    assert result["total_input_tokens"] == 15500
    assert result["total_output_tokens"] == 11900


# ── Full Report ───────────────────────────────────────────────


def test_full_report_structure():
    """Full report should have all expected sections."""
    root = _find_project_root(Path(__file__).parent)
    report = collect_full_report(root, git_days=7)

    assert "generated_at" in report
    assert "documentation_benchmark" in report
    assert "documentation_drift" in report
    assert "architecture" in report
    assert "git_metrics" in report


def test_full_report_text_format():
    """Text report should be non-empty and contain key sections."""
    root = _find_project_root(Path(__file__).parent)
    report = collect_full_report(root, git_days=7)
    text = format_text_report(report)

    assert "System Health Report" in text
    assert "Documentation Architecture Benchmark" in text
    assert "Architecture Health" in text
    assert "Git Metrics" in text
    assert len(text) > 500


def test_full_report_json_serializable():
    """Full report should be JSON-serializable."""
    root = _find_project_root(Path(__file__).parent)
    report = collect_full_report(root, git_days=7)
    # Should not raise
    json_str = json.dumps(report, indent=2)
    assert len(json_str) > 100
    # Round-trip should work
    parsed = json.loads(json_str)
    assert parsed["documentation_benchmark"]["total_cases"] == len(BENCHMARK_CASES)


# ── Pipeline Freshness Status Vocabulary ──────────────────────


def test_pipeline_freshness_uses_completed_status():
    """Pipeline freshness query must use 'completed' status, not 'success'.

    Regression: data_sync_log uses status='completed' for successful runs,
    but the health check originally queried for status='success', causing
    last_success to always be NULL. Every source that had ever failed then
    appeared as perpetually failing (phantom failures).
    """
    from system_health import collect_operator_briefing
    import inspect

    source = inspect.getsource(collect_operator_briefing)
    # The query must match 'completed', not 'success'
    assert "status = 'completed'" in source, (
        "Pipeline freshness query should use status='completed' "
        "(data_sync_log uses 'completed', not 'success')"
    )
    assert "status = 'success'" not in source, (
        "Pipeline freshness query should NOT use status='success' "
        "(data_sync_log uses 'completed' for successful runs)"
    )
