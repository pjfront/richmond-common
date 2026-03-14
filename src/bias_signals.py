"""
Richmond Common — Bias Audit Structural Risk Signals

Computes structural string properties of donor names that correlate with
known matching failure modes in the conflict scanner. These are properties
of STRINGS, not demographic inference about people.

See docs/specs/bias-audit-spec.md for full specification.
"""
from __future__ import annotations

import json
import string
from pathlib import Path


# ── Surname Frequency Lookup ─────────────────────────────────

# Census 2010 surname frequency data, loaded once at module import.
# Pre-processed from Names_2010Census.csv to {normalized_surname: tier}
# Tier 1 = top 100, Tier 2 = top 1000, Tier 3 = top 10000, Tier 4 = rare
SURNAME_FREQ: dict[str, int] = {}

_CENSUS_PATH = Path(__file__).parent / "data" / "census" / "surname_freq.json"
if _CENSUS_PATH.exists():
    with open(_CENSUS_PATH) as _f:
        SURNAME_FREQ = json.load(_f)


def lookup_surname_frequency_tier(surname: str) -> int | None:
    """Look up surname frequency tier from Census 2010 data.

    Returns 1-4 or None if surname not found or data not loaded.
    """
    if not surname or not surname.strip():
        return None
    normalized = surname.lower().strip()
    return SURNAME_FREQ.get(normalized)


# ── Bias Risk Signals ────────────────────────────────────────

def compute_bias_risk_signals(name: str) -> dict:
    """Compute structural string properties that correlate with matching failures.

    These are NOT demographic inference — they are observable string properties
    that the bias audit uses to check for disparate error rates.

    Args:
        name: Donor name string (e.g., "Maria Garcia-Lopez")

    Returns:
        dict with keys:
            has_compound_surname: bool — hyphenated or >3 tokens
            has_diacritics: bool — non-ASCII letters present
            token_count: int — number of space-separated tokens
            char_count: int — total characters
            surname_frequency_tier: int|None — 1-4 from census data
    """
    tokens = name.strip().split() if name.strip() else []
    has_compound = "-" in name or len(tokens) > 3

    has_diacritics = False
    for c in name:
        if c.isalpha() and c not in string.ascii_letters:
            has_diacritics = True
            break

    surname = tokens[-1] if tokens else ""
    tier = lookup_surname_frequency_tier(surname)

    return {
        "has_compound_surname": has_compound,
        "has_diacritics": has_diacritics,
        "token_count": len(tokens),
        "char_count": len(name),
        "surname_frequency_tier": tier,
    }
