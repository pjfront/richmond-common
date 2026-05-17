"""Shared AST helpers for unresolved-name detection across src/ packages.

Used by:
  - tests/test_db_module_name_resolution.py (motivating bug: db/contributions
    calling _normalize_name without importing it after Phase 2.1 split)
  - tests/test_package_module_name_resolution.py (broader: same bug class
    in any src/ subpackage — pipelines/, scanner/, future splits)

Underscore prefix on this module keeps pytest from collecting it as a test
file. Helpers are conservative: they accept a name if it's plausibly in
scope (locals, imports, module-level defs, builtins, dunders) AND honor
Python's lexical scoping for nested functions (closures). The goal is
zero false positives so the test never gets ignored or weakened.
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

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

# Nodes that introduce a new lexical scope. We do NOT descend into these
# when collecting an outer function's own statements — they get their own
# scan with their own scope chain.
_NESTED_SCOPE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


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


def _walk_shallow(node: ast.AST):
    """Yield descendants of `node` BUT stop at nested scope boundaries.

    Unlike `ast.walk`, this does not descend into nested FunctionDef /
    AsyncFunctionDef / ClassDef / Lambda — those are scanned separately
    with their own scope chains. Yields `node` itself first.
    """
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _NESTED_SCOPE_TYPES):
            # Yield the nested-scope node itself (so its decorators are
            # visible at the parent level) but stop descending into its
            # body — caller handles nested scopes separately.
            yield child
            continue
        yield from _walk_shallow(child)


def module_visible_names(tree: ast.Module) -> set[str]:
    """Names visible at module level: imports, top-level defs, top-level assigns.

    Honors conditional top-level guards (try/except/if blocks) — code like:
        try:
            import anthropic
        except ImportError:
            anthropic = None
    binds `anthropic` at module scope regardless of which branch runs.
    """
    visible: set[str] = set()
    for node in tree.body:
        _collect_top_level_bindings(node, visible)
    return visible


def _collect_top_level_bindings(node: ast.AST, visible: set[str]) -> None:
    """Walk `node` shallowly to find names bound at module level."""
    if isinstance(node, ast.ImportFrom):
        for alias in node.names:
            if alias.name == "*":
                continue
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
    elif isinstance(node, (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)):
        # Conditional / loop / with at module level: recurse to find any
        # bindings guarded by the construct (try/except imports, etc.).
        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, _NESTED_SCOPE_TYPES):
                # Don't descend into nested functions/classes from module
                # level (they get added by their own def name).
                continue
            _collect_top_level_bindings(child, visible)


def function_local_names(fn) -> set[str]:
    """Names bound inside a function body, NOT descending into nested scopes.

    Includes args + assignments + nested binders (for/with/except) that
    live in the function's own scope. Nested function/class defs add
    their NAME to the local set (so the def itself is resolvable) but
    their bodies are scanned separately.
    """
    locals_set: set[str] = set()
    for arg in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs:
        locals_set.add(arg.arg)
    if fn.args.vararg:
        locals_set.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        locals_set.add(fn.args.kwarg.arg)
    if isinstance(fn, ast.Lambda):
        # Lambdas have only args; no body statements to scan for further bindings.
        return locals_set

    for sub in _walk_shallow(fn):
        if sub is fn:
            continue
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
        elif isinstance(sub, _NESTED_SCOPE_TYPES):
            # Nested def/class — the NAME is locally bound here. Body is
            # scanned separately with its own scope chain.
            if hasattr(sub, "name"):
                locals_set.add(sub.name)
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
    return locals_set


def _comprehension_bindings(node: ast.AST) -> set[str]:
    """Names bound by ANY comprehension inside `node` (shallow walk).

    Comprehensions have their own scope in Python 3, but for the purposes
    of "is this name resolvable?" the bindings are visible to expressions
    inside the comprehension. Collect them upfront.
    """
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.comprehension):
            _collect_target_names(sub.target, out)
    return out


def scan_module(path: Path) -> list[str]:
    """Return a list of 'unresolved name' violations in this module.

    Honors nested-function lexical scoping: each function is checked
    against its own locals plus every enclosing function's locals plus
    the module-visible names plus builtins plus dunders.

    Conservative by design: when in doubt, accept the name. The goal is
    to catch the split-orphan class (`function calls _normalize_name; the
    module never imports it`) without crying wolf on legitimate dynamic
    or guarded code.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    module_visible = module_visible_names(tree)
    violations: list[str] = []

    def _check_scope_refs(scope_node, enclosing: set[str], fn_name: str) -> None:
        own_locals = function_local_names(scope_node)
        comp_bindings = _comprehension_bindings(scope_node)
        full_scope = enclosing | own_locals | comp_bindings

        for ref in _walk_shallow(scope_node):
            if ref is scope_node:
                continue
            if not (isinstance(ref, ast.Name) and isinstance(ref.ctx, ast.Load)):
                continue
            name = ref.id
            if name in full_scope:
                continue
            if name in MODULE_DUNDERS:
                continue
            if name in PYTHON_BUILTINS:
                continue
            violations.append(
                f"{path.name}:{ref.lineno} function {fn_name!r} references unresolved name {name!r}"
            )

        # Recurse into nested function / class / lambda scopes.
        new_enclosing = enclosing | own_locals
        for child in ast.iter_child_nodes(scope_node):
            _recurse_nested(child, new_enclosing)

    def _recurse_nested(node: ast.AST, enclosing: set[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _check_scope_refs(node, enclosing, node.name)
        elif isinstance(node, ast.Lambda):
            _check_scope_refs(node, enclosing, "<lambda>")
        elif isinstance(node, ast.ClassDef):
            # Class body sees the enclosing scope; methods see the class
            # body's bindings too. For the purposes of this check, treat
            # the class as transparent (methods get checked individually).
            class_locals: set[str] = set()
            for sub in ast.iter_child_nodes(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    class_locals.add(sub.name)
                elif isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        _collect_target_names(t, class_locals)
            for sub in ast.iter_child_nodes(node):
                _recurse_nested(sub, enclosing | class_locals)
        else:
            for child in ast.iter_child_nodes(node):
                _recurse_nested(child, enclosing)

    # Top-level: each module-level FunctionDef/AsyncFunctionDef/ClassDef
    # is the entry into the recursive scan.
    for node in ast.iter_child_nodes(tree):
        _recurse_nested(node, module_visible)

    return violations
