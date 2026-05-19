"""Operator review queue safeguard.

Every `<OperatorGate>` in `web/src/` must have a corresponding entry in
`docs/operator-review-queue.yaml`. Without this guard, AI-built features
silently accumulate behind operator gates and the operator forgets they
exist — exactly the pain point that led to this test being written
(2026-05-18 session).

Three enforcement tests:

  1. test_every_gate_is_registered — adding a new `<OperatorGate>` to
     a .tsx file without registering it in the YAML fails CI.

  2. test_no_stale_registry_entries — deleting an `<OperatorGate>`
     without removing the YAML entry fails CI (so the queue stays
     honest as features graduate).

  3. test_pending_graduation_entries_have_validation_checklist — every
     pending_graduation entry must have non-empty `what_to_validate`
     text. Forces the AI wrapping a new gate to write down what "ready
     to graduate" actually means, so future-you (or another session)
     can act on it cold.

Pattern is the same as:
  - tests/test_anon_visibility_coverage.py (web .from() registry)
  - tests/test_migration_discipline.py (mirror discipline)
  - tests/test_d1_provenance.py (D1 provenance manifest)

Each of those started with a real silent-failure case. This one starts
with the operator naming the pain explicitly: "I'm absolutely not going
to remember these things."
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).parent.parent
_REGISTRY_PATH = _ROOT / "docs" / "operator-review-queue.yaml"
_WEB_SRC = _ROOT / "web" / "src"

_VALID_CATEGORIES = {"permanent", "pending_graduation"}


def _load_registry() -> dict:
    """Load and validate top-level structure of the registry."""
    if not _REGISTRY_PATH.exists():
        pytest.fail(
            f"Registry file not found: {_REGISTRY_PATH}.\n\n"
            "Every <OperatorGate> in web/src/ must be cataloged here. "
            "See the file header for the contract."
        )
    with _REGISTRY_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    assert isinstance(data, dict), "Registry top level must be a mapping"
    assert "gates" in data, "Registry must have a top-level 'gates:' key"
    assert isinstance(data["gates"], list), "'gates' must be a list"
    return data


def _scan_gate_sites() -> list[tuple[Path, int]]:
    """Return [(file_path, line_no), ...] for every <OperatorGate> in web/src/."""
    sites: list[tuple[Path, int]] = []
    # Match <OperatorGate followed by space, '>', or end-of-line — covers
    # both single-line opens (`<OperatorGate>`, `<OperatorGate fallback={...}>`)
    # and multi-line opens (`<OperatorGate\n  fallback={...}>`). Excluding
    # word characters via the lookahead avoids false-matches on
    # OperatorGateProvider or hypothetical OperatorGate2 variants.
    # `splitlines()` strips line terminators, so we anchor to `$` to catch
    # the multi-line variant where the line ends right after "OperatorGate".
    pattern = re.compile(r"<OperatorGate(?=[\s>]|$)")

    def _line_is_comment(stripped: str) -> bool:
        # JSDoc continuation (` * ...`), line comment (`// ...`), or
        # block-comment opener (`/* ...`) on the same line. Misses the
        # exotic case where code + // comment + <OperatorGate> all appear
        # on one line, but that pattern doesn't exist in practice and
        # would arguably deserve linting separately anyway.
        return (
            stripped.startswith("*")
            or stripped.startswith("//")
            or stripped.startswith("/*")
        )

    for path in sorted(list(_WEB_SRC.rglob("*.tsx")) + list(_WEB_SRC.rglob("*.ts"))):
        # Skip duplicates from .ts rglob double-counting .tsx files (it
        # doesn't, but the merged list pattern is robust either way).
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not pattern.search(line):
                continue
            if _line_is_comment(line.lstrip()):
                continue
            sites.append((path, lineno))
    return sites


def _normalize_relpath(p: Path) -> str:
    """Path relative to repo root, in posix form (forward slashes).

    Registry stores posix paths; live filesystem may use Windows
    backslashes on this dev box. Normalize for honest comparison.
    """
    return p.relative_to(_ROOT).as_posix()


def _registry_to_set(reg: dict) -> set[tuple[str, int]]:
    """Project registry to {(file, line)} for cross-checking."""
    out: set[tuple[str, int]] = set()
    for entry in reg["gates"]:
        out.add((entry["file"], int(entry["line"])))
    return out


def _site_set(sites: list[tuple[Path, int]]) -> set[tuple[str, int]]:
    return {(_normalize_relpath(p), ln) for p, ln in sites}


# ──────────────────────────────────────────────────────────────────


def test_registry_well_formed():
    """Every registry entry has the required fields with valid values.

    Required: id, file, line, category, gated_at, reason.
    Optional: what_to_validate (required for pending_graduation only —
    asserted by a separate test below so the failure messages are clear).
    Optional: graduates_to (only meaningful for pending_graduation).
    """
    reg = _load_registry()
    required = {"id", "file", "line", "category", "gated_at", "reason"}
    seen_ids: dict[str, str] = {}
    for entry in reg["gates"]:
        missing = required - set(entry.keys())
        assert not missing, (
            f"Registry entry missing required keys {missing}: {entry!r}"
        )
        assert entry["category"] in _VALID_CATEGORIES, (
            f"Invalid category {entry['category']!r} for entry "
            f"{entry['id']!r} — must be one of {_VALID_CATEGORIES}"
        )
        # ID uniqueness
        if entry["id"] in seen_ids:
            pytest.fail(
                f"Duplicate registry id {entry['id']!r} — first seen at "
                f"{seen_ids[entry['id']]}, also at {entry['file']}"
            )
        seen_ids[entry["id"]] = entry["file"]


def test_every_gate_is_registered():
    """Every <OperatorGate> in web/src/ has an entry in the registry.

    Catches the silent-failure case: AI wraps something in OperatorGate
    without telling the operator. The operator then doesn't know the
    gate exists and can never make the graduation decision.
    """
    reg = _load_registry()
    reg_set = _registry_to_set(reg)
    site_set = _site_set(_scan_gate_sites())

    unregistered = sorted(site_set - reg_set)
    assert not unregistered, (
        f"<OperatorGate> sites missing from operator-review-queue.yaml:\n  "
        + "\n  ".join(f"{f}:{ln}" for f, ln in unregistered)
        + "\n\nFix: add an entry to docs/operator-review-queue.yaml in "
        "the same commit. For pending_graduation entries, include a "
        "concrete what_to_validate checklist so the operator can act on "
        "the gate without re-deriving context."
    )


def test_no_stale_registry_entries():
    """Every registry entry points to a real <OperatorGate> at the right line.

    Catches the reverse failure: AI removes/moves an OperatorGate
    without updating the registry. Without this guard, the queue would
    accumulate dead entries and lose credibility as a source of truth.
    """
    reg = _load_registry()
    site_set = _site_set(_scan_gate_sites())

    stale = []
    for entry in reg["gates"]:
        key = (entry["file"], int(entry["line"]))
        if key not in site_set:
            # Check whether the file still has ANY gate (line drifted)
            # vs. no gate at all (was removed). Different fix paths.
            file_has_any_gate = any(
                f == entry["file"] for f, _ in site_set
            )
            if file_has_any_gate:
                lines_in_file = sorted(
                    ln for f, ln in site_set if f == entry["file"]
                )
                stale.append(
                    f"{entry['id']} → {entry['file']}:{entry['line']} "
                    f"no longer matches a gate (file still has gates "
                    f"at lines {lines_in_file}; update entry's line: field)"
                )
            else:
                stale.append(
                    f"{entry['id']} → {entry['file']}:{entry['line']} "
                    f"no longer exists (file has no <OperatorGate> at all; "
                    f"either restore the gate or remove this entry)"
                )

    assert not stale, (
        "Stale registry entries in operator-review-queue.yaml:\n  "
        + "\n  ".join(stale)
        + "\n\nFix: either restore the gate, update the line: field to "
        "match its new position, or remove the entry entirely (if the "
        "feature was graduated to public)."
    )


def test_pending_graduation_entries_have_validation_checklist():
    """Every pending_graduation entry has non-empty what_to_validate.

    Forces the AI wrapping a new gate to write down what "ready to
    graduate" actually means. Without this, future-you (or another
    session) reading the registry has no idea what the gate is waiting
    on. The discipline of writing the checklist also surfaces gates
    that probably shouldn't be pending_graduation in the first place
    ("hmm, I can't write a checklist because this is actually permanent
    operator-only").
    """
    reg = _load_registry()
    missing = []
    for entry in reg["gates"]:
        if entry["category"] != "pending_graduation":
            continue
        wtv = entry.get("what_to_validate", "")
        if not isinstance(wtv, str) or not wtv.strip():
            missing.append(entry["id"])

    assert not missing, (
        "pending_graduation entries missing what_to_validate text:\n  "
        + "\n  ".join(missing)
        + "\n\nEvery pending_graduation gate needs a concrete checklist "
        "(3-5 lines, what to click/check) so the operator knows what "
        "'ready to graduate' means without re-deriving context. If you "
        "can't write a checklist, the gate is probably permanent "
        "operator-only — re-categorize."
    )


def test_id_format():
    """Registry ids are kebab-case, lowercase, ASCII.

    The id is referenced in commit messages, parking-lot entries, and
    the SessionStart brief. Consistent shape keeps grep honest.
    """
    bad = []
    for entry in _load_registry()["gates"]:
        if not re.fullmatch(r"[a-z][a-z0-9-]*[a-z0-9]", entry["id"]):
            bad.append(entry["id"])
    assert not bad, (
        f"Registry ids must be kebab-case (lowercase letters + digits + "
        f"hyphens). Bad ids: {bad}"
    )
