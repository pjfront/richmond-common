"""Static check: every function body in src/{pipelines,scanner}/*.py
references only names resolvable in that module's scope.

Extends tests/test_db_module_name_resolution.py from the original
motivating scope (`src/db/` only) to the other src/ subpackages.

Why now (2026-05-17): the netfile/calaccess `_normalize_name` NameError
that fired May 14-15 was already caught by the db-scoped test, but the
broader bug class — "lazy-imported function references a name the module
never imported, found only at call time" — can recur in ANY package
split. The pipelines/ package was created by Phase 2.3 (extracted from
data_sync.py); scanner/ is the conflict-scanner package. Both have
multiple submodules and the same shape of risk.

This test runs in <100ms total and adds nothing to the failure mode
surface area: it's pure AST analysis on filesystem reads. Adding
new packages is a one-line change to PACKAGE_DIRS below.

Helper imports come from tests/_ast_name_resolution.py — kept in
sync with test_db_module_name_resolution.py so refinements to the
scanner (e.g., better handling of TYPE_CHECKING blocks) benefit
both tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Same helpers as test_db_module_name_resolution.py.
sys.path.insert(0, str(Path(__file__).parent))
from _ast_name_resolution import scan_module  # noqa: E402

SRC_DIR = Path(__file__).parent.parent / "src"

# Subpackages under src/ that should be statically scanned.
# Add a new package directory here when one is created.
PACKAGE_DIRS = [
    SRC_DIR / "pipelines",
    SRC_DIR / "scanner",
]


def _all_package_files() -> list[Path]:
    """Every non-dunder *.py inside our scanned subpackages (recursive).

    Recurses into subdirectories because scanner/signals/ has 10 sibling
    modules. Skips __init__.py and __pycache__.
    """
    files: list[Path] = []
    for pkg in PACKAGE_DIRS:
        if not pkg.exists():
            continue
        for p in pkg.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if p.name.startswith("__"):
                continue
            files.append(p)
    return sorted(files)


def _file_id(path: Path) -> str:
    """Test ID: pkg[/subdir]/file.py — distinguishes scanner/signals/X
    from any hypothetical pipelines/signals/X.
    """
    src_dir = SRC_DIR.resolve()
    rel = path.resolve().relative_to(src_dir)
    return str(rel).replace("\\", "/")


@pytest.mark.parametrize(
    "module_file",
    _all_package_files(),
    ids=_file_id,
)
def test_subpackage_function_name_resolution(module_file: Path) -> None:
    """Every Name(Load) in a function body must resolve.

    Catches the same class as test_db_module_name_resolution.py, just
    for the other src/ subpackages. Fails the same way: with the
    file:line, function name, and unresolved name.

    Fix shape: add the missing import at the top of the module, OR
    add it inside the function body. (Top of module is preferred so
    the next reader sees the dependency without scrolling.)
    """
    violations = scan_module(module_file)
    assert not violations, (
        "Unresolved name references in subpackage module — same shape\n"
        "as the 2026-05-15 db.contributions/_normalize_name NameError.\n"
        "Most likely cause: a function was extracted from a different\n"
        "module that had the import at top, and the import wasn't\n"
        "carried along.\n\n"
        + "\n".join(violations)
    )


def test_package_dirs_are_actually_packages() -> None:
    """Each PACKAGE_DIRS entry must exist AND be a real Python package.

    If a package is renamed or removed, this fails LOUDLY — better than
    silently skipping all checks for that package.
    """
    missing: list[str] = []
    not_packages: list[str] = []
    for pkg in PACKAGE_DIRS:
        if not pkg.exists():
            missing.append(str(pkg))
            continue
        if not (pkg / "__init__.py").exists():
            not_packages.append(str(pkg))
    assert not missing, (
        f"PACKAGE_DIRS references missing directories: {missing}.\n"
        "If a package was renamed/removed, update PACKAGE_DIRS."
    )
    assert not not_packages, (
        f"PACKAGE_DIRS references directories without __init__.py: {not_packages}.\n"
        "AST scanning is package-scoped; bare dirs aren't applicable."
    )


def test_at_least_one_file_is_scanned() -> None:
    """Sanity check: if PACKAGE_DIRS is empty or all dirs are empty,
    the parametrized test would generate zero cases and silently pass.

    Force a failure in that scenario so we notice.
    """
    files = _all_package_files()
    assert len(files) >= 5, (
        f"Only {len(files)} *.py files found across {PACKAGE_DIRS}. "
        "Expected at least 5 (pipelines/ alone has 10+). "
        "Did PACKAGE_DIRS lose entries or did src/ restructure?"
    )
