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

AST helpers are shared with tests/test_package_module_name_resolution.py
(which extends the same check to pipelines/ and scanner/) via
tests/_ast_name_resolution.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Import shared helpers — extracted 2026-05-17 when coverage was extended
# from src/db/ to all src/ subpackages.
sys.path.insert(0, str(Path(__file__).parent))
from _ast_name_resolution import scan_module  # noqa: E402

DB_DIR = Path(__file__).parent.parent / "src" / "db"


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
    violations = scan_module(db_file)
    assert not violations, (
        "Unresolved name references found (the Phase 2.1 split-orphan class):\n"
        + "\n".join(violations)
    )
