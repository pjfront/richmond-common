"""Enforce the cost/quality routing decision at source-control time."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"

ROUTINE_MODULES = (
    "batch_classify_proceeding.py",
    "batch_recategorize.py",
    "batch_summarize.py",
    "bio_generator.py",
    "correct_recap_names.py",
    "plain_language_summarizer.py",
    "vote_explainer.py",
)


def _python_strings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_routine_call_sites_cannot_drift_back_to_pro():
    for filename in ROUTINE_MODULES:
        source = (SRC / filename).read_text(encoding="utf-8")
        assert "ROUTINE_MODEL" in source, filename
        assert '"deepseek-v4-pro"' not in source, filename
        assert "'deepseek-v4-pro'" not in source, filename


def test_retired_deepseek_aliases_are_not_executable_callsite_literals():
    allowed_registry = SRC / "llm_client.py"
    for path in SRC.rglob("*.py"):
        if path in {allowed_registry, SRC / "anthropic_budget_lock.py"}:
            continue
        strings = _python_strings(path)
        assert "deepseek-chat" not in strings, path
        assert "deepseek-reasoner" not in strings, path


def test_openai_chat_candidates_remain_benchmark_only():
    allowed_registries = {
        SRC / "llm_client.py",
        SRC / "llm_budget_lock.py",
    }
    for path in SRC.rglob("*.py"):
        if path in allowed_registries:
            continue
        strings = _python_strings(path)
        assert "gpt-5.6-luna" not in strings, path
        assert "gpt-5-nano" not in strings, path


def test_self_assessment_is_the_explicit_reasoning_route():
    source = (SRC / "self_assessment.py").read_text(encoding="utf-8")
    assert "model=REASONING_MODEL" in source
    assert 'thinking={"type": "enabled"}' in source
    assert 'reasoning_effort="high"' in source
