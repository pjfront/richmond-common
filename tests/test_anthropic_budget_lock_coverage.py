"""Static check: every src/*.py file that imports the anthropic SDK
must also import src/anthropic_budget_lock so the monkey-patch is in
effect for that process.

Background (Phase D-1, 2026-05-16): PR #26/#27 introduced a budget
rail by monkey-patching `anthropic.Anthropic.messages.create` from
`src/anthropic_budget_lock.py`. The patch only takes effect if that
module is imported BEFORE `anthropic` is first used; the convention
is `import anthropic_budget_lock  # noqa: F401` as the first import
in every script that uses the SDK.

The Phase C doc-drift audit (`docs/audits/2026-05-doc-drift-audit.md`
finding C8) found 4 entry-point scripts that called `messages.create`
without importing the budget lock — meaning those CLI invocations
bypassed both the kill switch and the auto-journaling.

This test prevents that regression class. It parses each src/*.py
file with `ast`, finds the imports, and asserts: if `anthropic` is
imported (directly or as a submodule), then `anthropic_budget_lock`
must also be imported at module scope.

Library modules that are imported BY an entry point inherit the
monkey-patch via Python's import side effects — they don't need the
import themselves. The test relies on a manually-curated allowlist
(`LIBRARY_MODULES_NEVER_AS_ENTRY_POINT`) for files that are never
run as `python <file>.py` and are only imported by other modules
that DO carry the lock. Treat the allowlist as evidence of a
deliberate design choice, not a forever-exemption.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parent.parent / "src"

# Files imported by entry points that already wire the budget lock.
# These modules cannot be run as `python <file>.py`; they're library
# code only. If you change one of these to be a CLI entry point, you
# MUST add the budget-lock import to it AND remove it from this list.
LIBRARY_MODULES_NEVER_AS_ENTRY_POINT = {
    "bio_generator.py",            # imported by generate_bios.py
    "plain_language_summarizer.py", # imported by generate_summaries.py
    # NB: pipelines/enrichments.py is also a library module but lives
    # in src/pipelines/ — checked separately below.
    # community_voice_extractor.py, pipeline.py, form700_extractor.py,
    # and vote_explainer.py have `if __name__ == "__main__":` blocks and
    # are real CLI entry points — they each carry the budget-lock import.
}

PIPELINES_LIBRARY_MODULES = {
    "enrichments.py",   # imported by data_sync.py via SYNC_SOURCES dispatch
}


def _imports_anthropic_anywhere(tree: ast.Module) -> bool:
    """True if `anthropic` is imported anywhere in the module.

    Includes top-level AND function-body (lazy) imports. Lazy imports
    still bypass the budget lock if the lock isn't imported at top
    level — the monkey-patch only applies if it ran BEFORE `anthropic`
    was first used in this process.
    """
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


def _imports_budget_lock(tree: ast.Module) -> bool:
    """True if the module imports anthropic_budget_lock at top level.

    Only top-level counts here: the budget lock has to be imported at
    module load time so its monkey-patch runs before `anthropic` is
    first touched in the process.
    """
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "anthropic_budget_lock":
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "anthropic_budget_lock":
                return True
    return False


def _python_files_in_src() -> list[Path]:
    """Every .py file under src/, excluding __pycache__ and the budget lock itself."""
    files: list[Path] = []
    for p in SRC_DIR.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if p.name == "anthropic_budget_lock.py":
            continue
        files.append(p)
    return sorted(files)


def test_anthropic_callers_import_budget_lock():
    """Every src/*.py using `anthropic` imports `anthropic_budget_lock`.

    Library modules in the allowlist are exempt because they're only
    imported by entry points that already carry the lock — the
    monkey-patch is in effect via import order.
    """
    offenders: list[str] = []

    for path in _python_files_in_src():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as e:
            pytest.fail(f"Could not parse {path}: {e}")

        if not _imports_anthropic_anywhere(tree):
            continue

        # Check allowlist
        rel = path.relative_to(SRC_DIR)
        rel_str = str(rel).replace("\\", "/")
        if rel.parts == (path.name,) and path.name in LIBRARY_MODULES_NEVER_AS_ENTRY_POINT:
            continue
        if rel.parts[:1] == ("pipelines",) and path.name in PIPELINES_LIBRARY_MODULES:
            continue

        if not _imports_budget_lock(tree):
            offenders.append(rel_str)

    assert not offenders, (
        "These src/*.py files import the `anthropic` SDK but do NOT import\n"
        "`anthropic_budget_lock` — meaning Anthropic calls from these paths\n"
        "bypass both the kill switch and the auto-journaling rail.\n\n"
        "Fix: add `import anthropic_budget_lock  # noqa: F401` as the FIRST\n"
        "non-future import in each file. (Place it before `import anthropic`.)\n\n"
        "If the file is truly never executed as `python <file>.py` (it's only\n"
        "imported by an entry point that already wires the lock), add it to\n"
        "`LIBRARY_MODULES_NEVER_AS_ENTRY_POINT` in this test with a comment\n"
        "noting which entry point imports it.\n\n"
        f"Offenders: {offenders}"
    )


def test_allowlisted_modules_actually_lack_main_guard():
    """Allowlisted 'library only' modules must NOT have `if __name__ == \"__main__\":`.

    If they do, they're entry points pretending to be libraries, and the
    allowlist is a lie. Either:
      - Remove the main guard, OR
      - Remove the file from the allowlist + add the budget-lock import.
    """
    suspects: list[str] = []

    for name in LIBRARY_MODULES_NEVER_AS_ENTRY_POINT:
        path = SRC_DIR / name
        if not path.exists():
            continue  # Allowlist entry refers to deleted file — separate cleanup
        text = path.read_text(encoding="utf-8")
        if 'if __name__ == "__main__":' in text or "if __name__ == '__main__':" in text:
            suspects.append(name)

    for name in PIPELINES_LIBRARY_MODULES:
        path = SRC_DIR / "pipelines" / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if 'if __name__ == "__main__":' in text or "if __name__ == '__main__':" in text:
            suspects.append(f"pipelines/{name}")

    assert not suspects, (
        "These modules are in the budget-lock 'library only' allowlist but\n"
        "have an `if __name__ == \"__main__\":` block — meaning they CAN be\n"
        "run as `python <file>.py`, and a direct invocation would bypass\n"
        "the budget lock.\n\n"
        f"Suspects: {suspects}\n\n"
        "Fix: remove from allowlist and add the budget-lock import, OR\n"
        "remove the main guard if the CLI path was leftover dev scaffolding."
    )
