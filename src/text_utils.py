"""Shared text processing utilities for the Richmond Transparency pipeline."""
from __future__ import annotations

import re


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
