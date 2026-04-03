"""Shared text processing utilities for the Richmond Transparency pipeline."""
from __future__ import annotations

import re
from typing import Optional


def extract_financial_amount(text: str | None) -> str | None:
    """Extract the largest dollar amount from text.

    Handles $X,XXX and $X.X million/billion patterns.
    Returns the largest amount found, normalized to "$X,XXX" format.
    """
    if not text:
        return None

    amounts: list[int] = []

    # Match $X million / $X.X billion patterns first (highest value)
    for m in re.finditer(r'\$(\d+(?:\.\d+)?)\s*(million|billion)', text, re.IGNORECASE):
        val = float(m.group(1))
        multiplier = 1_000_000_000 if m.group(2).lower() == 'billion' else 1_000_000
        amounts.append(int(val * multiplier))

    # Match $X,XXX,XXX or $X,XXX patterns
    for m in re.finditer(r'\$([\d,]+(?:\.\d{2})?)', text):
        raw = m.group(1).replace(',', '')
        try:
            val = float(raw)
            amounts.append(int(val))
        except ValueError:
            continue

    if not amounts:
        return None

    largest = max(amounts)
    return f"${largest:,}"


# ── Agenda Item Resolution ──────────────────────────────────────────────────


def normalize_item_number(s: str) -> str:
    """Normalize agenda item numbers for fuzzy matching.

    Inserts dots between letter/digit boundaries so various shorthand
    formats map to the same canonical form:
      'P5' -> 'p.5', 'N3D' -> 'n.3.d', 'V6a' -> 'v.6.a', 'O-1' -> 'o.1'
    """
    s = s.strip().upper().replace("-", ".")
    result = re.sub(r"([A-Z])(\d)", r"\1.\2", s)
    result = re.sub(r"(\d)([A-Z])", r"\1.\2", result)
    return result.lower()


def resolve_item_id(
    item_number: str,
    item_id_map: dict[str, str],
) -> Optional[str]:
    """Resolve an item number to a UUID, trying exact then normalized match."""
    if item_number in item_id_map:
        return item_id_map[item_number]

    norm = normalize_item_number(item_number)
    for db_num, db_id in item_id_map.items():
        if normalize_item_number(db_num) == norm:
            return db_id

    return None
