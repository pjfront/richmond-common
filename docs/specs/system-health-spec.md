# System Health & Self-Assessment Spec

**Date:** 2026-02-27
**Phase:** 2 (Meta-layer)
**Publication tier:** Operator-only (system introspection tooling)

## Problem

The project has solid reactive monitoring (staleness, health endpoints, audit trails) but no proactive self-assessment. We can't answer: "Is our documentation architecture working?", "Which modules are undertested?", "Are our conventions actually followed?", or "Does our sprint cadence match what we actually build?"

These are the kind of questions that accumulate tech debt silently when unanswered.

## Solution

A `system_health.py` module that produces evidence-based assessments across three layers:

### Layer 1: Documentation Architecture Benchmark

Maps common task types → expected context files/keywords. Validates that:
- Referenced files exist
- Expected sections are findable
- Coverage is measured (what % of task types have documented context)
- Drift is detected (stale references, orphaned sections)

This is the self-retrieval test: does our CLAUDE.md tree actually help the system find what it needs?

### Layer 2: Architecture Health

- **Module-test coverage**: Which src/ modules have tests, which don't?
- **Import coupling**: Dependency graph from import analysis. Where are the bottlenecks?
- **Convention compliance**: Spot-checks for FIPS enforcement, dotenv loading, type hints
- **Documentation drift**: File references in CLAUDE.md that point to non-existent files

### Layer 3: Pipeline Instrumentation Helpers

- `PipelineTimer` context manager for per-stage timing
- `TokenCounter` wrapper for Claude API calls
- Designed for incremental adoption (decorate one function at a time)

## Non-goals (v1)

- No database dependency (reads filesystem + git only)
- No API calls (fast to run)
- No frontend endpoint yet (CLI-only, like staleness_monitor.py)
- No automated anomaly detection (that's v2)

## Output

CLI with `--format text|json`, following staleness_monitor.py pattern. Produces a structured report suitable for logging to decisions.md or feeding into future dashboards.

## What This Enables

- Evidence-based architecture refactoring decisions
- CLAUDE.md tree restructuring based on coverage gaps
- Sprint cadence evaluation based on actual build patterns
- Convention drift detection before it becomes tech debt
