"""Static check: every function body in src/db/*.py references only names
resolvable in that module's scope.

Motivating bug (2026-05-15): Phase 2.1 split db.py into per-domain
submodules. db/contributions.py kept calling `_normalize_name(...)` inside
load_contributions_to_db but never imported it after the split. db/__init__.py
re-exported it from .officials for *external* callers, so `from db import
load_contributions_to_db` worked syntactically — but at call time, the
function looked up `_normalize_name` in db.contributions's globals (where
it wasn't), raising NameError. Netfile sync failed every hour for 2 days
before the SessionStart health check surfaced it.

This test parses each db submodule with `ast`, conservatively tracks the
names each function defines locally (args, assignments, imports inside
the function, comprehension targets, with-as, except-as, etc.), and
fails if any Name(Load) reference inside a function body is neither
defined locally nor visible at module scope.

Whitelisted: Python module dunders (`__file__`, `__name__`, ...) which
are always present but not introduced by any explicit binding.
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

DB_DIR = Path(__file__).parent.parent / "src" / "db"

# Python module-level dunders that are always available but not visible
# to a naive ast walk because nothing in the source binds them.
MODULE_DUNDERS = {
    "__file__", "__name__", "__doc__", "__package__", "__loader__",
    "__spec__", "__builtins__", "__path__", "__all__",
}

# Builtins are always in scope. `builtins` is the canonical module; using
# `dir(__builtins__)` is fragile because __builtins__ is a module in
# top-level scripts but a dict in submodules.
PYTHON_BUILTINS = set(dir(builtins))


def _collect_target_names(target: ast.expr, out: set[str]) -> None:
    """Recursively collect names bound by an assignment target.

    Handles plain `x =`, tuple unpacking `(a, b) =`, list unpacking,
    and starred unpacking `*rest = ...`.
    """
    if isinstance(target, ast.Name):
        out.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _collect_target_names(elt, out)
    elif isinstance(target, ast.Starred):
        _collect_target_names(target.value, out)


def _module_visible_names(tree: ast.Module) -> set[str]:
    """Names visible at module level: imports, top-level defs, top-level assigns."""
    visible: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue  # star imports are opaque; we just trust them
                visible.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                visible.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            visible.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                _collect_target_names(t, visible)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            _collect_target_names(node.target, visible)
    return visible


def _function_local_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names bound inside a function body (args + assignments + nested binders)."""
    locals_set: set[str] = set()
    for arg in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs:
        locals_set.add(arg.arg)
    if fn.args.vararg:
        locals_set.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        locals_set.add(fn.args.kwarg.arg)

    for sub in ast.walk(fn):
        if isinstance(sub, ast.Assign):
            for t in sub.targets:
                _collect_target_names(t, locals_set)
        elif isinstance(sub, (ast.AugAssign, ast.AnnAssign)):
            _collect_target_names(sub.target, locals_set)
        elif isinstance(sub, (ast.For, ast.AsyncFor)):
            _collect_target_names(sub.target, locals_set)
        elif isinstance(sub, (ast.With, ast.AsyncWith)):
            for item in sub.items:
                if item.optional_vars is not None:
                    _collect_target_names(item.optional_vars, locals_set)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            locals_set.add(sub.name)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            locals_set.add(sub.name)
        elif isinstance(sub, ast.Lambda):
            for arg in sub.args.args + sub.args.kwonlyargs + sub.args.posonlyargs:
                locals_set.add(arg.arg)
        elif isinstance(sub, ast.ImportFrom):
            for alias in sub.names:
                if alias.name == "*":
                    continue
                locals_set.add(alias.asname or alias.name)
        elif isinstance(sub, ast.Import):
            for alias in sub.names:
                locals_set.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(sub, ast.NamedExpr):
            if isinstance(sub.target, ast.Name):
                locals_set.add(sub.target.id)
        elif isinstance(sub, ast.comprehension):
            _collect_target_names(sub.target, locals_set)
    return locals_set


def _scan_module(path: Path) -> list[str]:
    """Return a list of 'unresolved name' violations in this module."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    module_visible = _module_visible_names(tree)
    violations: list[str] = []

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local_names = _function_local_names(fn)
        for ref in ast.walk(fn):
            if not (isinstance(ref, ast.Name) and isinstance(ref.ctx, ast.Load)):
                continue
            name = ref.id
            if name in local_names:
                continue
            if name in module_visible:
                continue
            if name in MODULE_DUNDERS:
                continue
            if name in PYTHON_BUILTINS:
                continue
            violations.append(
                f"{path.name}:{ref.lineno} function {fn.name!r} references unresolved name {name!r}"
            )
    return violations


@pytest.mark.parametrize(
    "db_file",
    sorted(p for p in DB_DIR.glob("*.py") if not p.name.startswith("__")),
    ids=lambda p: p.name,
)
def test_db_submodule_function_name_resolution(db_file: Path) -> None:
    """Every Name(Load) in a function body must resolve to a local, an
    import, a module-level def, or a builtin.

    Regression test for the 2026-05-15 netfile sync failure (NameError on
    `_normalize_name` in db.contributions after the Phase 2.1 split).
    """
    violations = _scan_module(db_file)
    assert not violations, (
        "Unresolved name references found (the Phase 2.1 split-orphan class):\n"
        + "\n".join(violations)
    )
