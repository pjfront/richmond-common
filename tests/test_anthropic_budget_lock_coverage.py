"""Static check: no src/*.py file imports the old `anthropic` SDK directly.

After the DeepSeek migration (2026-07), all LLM calls go through
`llm_client.LLMClient`, which internally enforces budget caps via
`llm_budget_lock`. Files should NOT import `anthropic` directly — they
should use `from llm_client import LLMClient`.

The `anthropic_budget_lock.py` file is retained as a legacy compatibility
module but is no longer imported by any other src/ file.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parent.parent / "src"

# Files that are explicitly allowed to reference anthropic (the legacy
# shim module itself, and llm_budget_lock which re-exports old names).
LEGACY_ANTHROPIC_REFS: set[str] = {
    "anthropic_budget_lock.py",
}


def _imports_anthropic(tree: ast.Module) -> bool:
    """True if `anthropic` is imported anywhere in the module (directly)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root == "anthropic" and alias.name != "anthropic_budget_lock":
                    return True
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]
            if module == "anthropic" and node.module != "anthropic_budget_lock":
                return True
    return False


def _python_files_in_src() -> list[Path]:
    """Every .py file under src/, excluding __pycache__."""
    files: list[Path] = []
    for p in SRC_DIR.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        files.append(p)
    return sorted(files)


def test_no_files_import_anthropic_directly():
    """After the DeepSeek migration, no src/ file should import `anthropic` directly.

    The only exception is the legacy shim `anthropic_budget_lock.py` which
    retains the old Anthropic SDK references for backward compatibility.
    """
    offenders: list[str] = []

    for path in _python_files_in_src():
        if path.name in LEGACY_ANTHROPIC_REFS:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as e:
            pytest.fail(f"Could not parse {path}: {e}")

        if _imports_anthropic(tree):
            rel = path.relative_to(SRC_DIR)
            offenders.append(str(rel).replace("\\", "/"))

    assert not offenders, (
        "These src/ files still import the old `anthropic` SDK directly.\n"
        "They should use `from llm_client import LLMClient` instead.\n\n"
        f"Offenders: {offenders}"
    )
