"""Canonical donor-name resolver for paper-filed campaign finance rows.

Parses ``src/prompts/canonical_donors.md`` into an alias→canonical map
and exposes ``canonicalize_donor_name(name)`` for use at contribution
load time.

Why this exists: Vision OCR on California FPPC paper filings emits the
same legal entity under different surface names from one filing to the
next ("Richmond Police Officers Association" vs "Richmond City Police",
"IAFF Local 188" vs "Independent PAC Local 188 International Association
of Firefighters"). Without alias collapse, the same entity ends up under
multiple ``donors.id`` rows, breaking dedup, breaking influence-graph
edges, and inflating "unique donor" counts in the filing-period briefing.

Reads from ``src/prompts/canonical_donors.md`` (source-closest authority
maintained by humans). Does NOT read from any database table — the
canonical map is a configuration artifact, not a derived view.

Reference pattern: ``src/correct_recap_names.py`` for the canonical_names
counterpart on transcript-derived content.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DONORS_MD = _PROMPTS_DIR / "canonical_donors.md"

# Markdown entry pattern:
#   **Canonical Name** — entity-type description
#   - Aliases: alias1; alias2; alias3
#
# We capture the canonical name from the bold header and the alias list
# from the next non-blank line that starts with "- Aliases:".
_HEADER_RE = re.compile(r"^\*\*([^*]+)\*\*\s*[-—]")
_ALIASES_RE = re.compile(r"^-\s*Aliases:\s*(.+)$", re.IGNORECASE)


def _normalize_for_lookup(name: str) -> str:
    """Aggressive normalization for alias matching.

    Lowercase + collapse internal whitespace + strip punctuation that
    OCR commonly drops or adds (periods, commas, asterisks, parens).
    Keeps hyphens because they carry meaning in some entity names.
    """
    if not name:
        return ""
    # Lowercase, strip
    s = name.strip().lower()
    # Drop common OCR-noise punctuation
    s = re.sub(r"[.,*()'\"]", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


@lru_cache(maxsize=1)
def _load_alias_map() -> dict[str, str]:
    """Parse canonical_donors.md into {normalized_alias: canonical_name}.

    Cached for the process lifetime — the map is small (~50 entries)
    and the file is read-mostly. Edit the .md and restart any long-
    running process to pick up changes.
    """
    if not _DONORS_MD.exists():
        return {}

    alias_map: dict[str, str] = {}
    current_canonical: str | None = None

    for raw in _DONORS_MD.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()

        header_m = _HEADER_RE.match(line)
        if header_m:
            current_canonical = header_m.group(1).strip()
            # Self-mapping: the canonical name is its own alias so that
            # rows already storing the canonical string round-trip cleanly.
            alias_map[_normalize_for_lookup(current_canonical)] = current_canonical
            continue

        if current_canonical is None:
            continue

        alias_m = _ALIASES_RE.match(line)
        if alias_m:
            for alias in alias_m.group(1).split(";"):
                alias = alias.strip()
                if alias:
                    alias_map[_normalize_for_lookup(alias)] = current_canonical

    return alias_map


def canonicalize_donor_name(name: str) -> str:
    """Return the canonical entity name for a donor name, or the input
    unchanged if no alias matches.

    Match is on aggressively-normalized form (case-insensitive, OCR-noise
    punctuation stripped). Returns the canonical surface form preserved
    from the markdown header so the donors table stores human-readable
    names.

    Pure function: no DB, no I/O after first call (alias map is cached).
    """
    if not name:
        return name
    key = _normalize_for_lookup(name)
    return _load_alias_map().get(key, name)


def reload_alias_map() -> None:
    """Clear the cached alias map. Useful for tests or after editing the .md."""
    _load_alias_map.cache_clear()


if __name__ == "__main__":
    # Smoke test — print the loaded map and try a few known aliases.
    amap = _load_alias_map()
    print(f"Loaded {len(amap)} alias entries from {_DONORS_MD}")
    print()
    test_cases = [
        "Richmond City Police",
        "Independent PAC Local 188 International Association of Firefighters",
        "SEIU 1021",
        "Chevron",
        "Some Random Donor LLC",
    ]
    for tc in test_cases:
        canonical = canonicalize_donor_name(tc)
        marker = "->" if canonical != tc else "  "
        print(f"  {tc!r}\n  {marker} {canonical!r}\n")
