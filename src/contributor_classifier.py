"""
Richmond Common — Contributor Type Classification

Classifies campaign finance contributors into five types:
  corporate, union, individual, pac_ie, other

Two classification paths:
  1. Authoritative: CAL-ACCESS ENTITY_CD field (IND, COM, OTH, PTY, SCC)
  2. Inferred: Name-pattern heuristics for NetFile (no entity type field)

Usage:
    from contributor_classifier import classify_contributor

    result = classify_contributor(
        name="SEIU Local 1021",
        entity_code="OTH",   # from CAL-ACCESS, or None for NetFile
        source="calaccess",
    )
    # result = ("union", "entity_cd")  — (type, source)
"""
from __future__ import annotations

import re

# ── Contributor type enum values ──
CORPORATE = "corporate"
UNION = "union"
INDIVIDUAL = "individual"
PAC_IE = "pac_ie"
OTHER = "other"

VALID_TYPES = {CORPORATE, UNION, INDIVIDUAL, PAC_IE, OTHER}

# ── CAL-ACCESS ENTITY_CD mapping ──
# These are FPPC-defined codes in the RCPT_CD table.
# IND = Individual, COM = Committee (recipient committee, rarely a donor),
# OTH = Other (businesses, orgs, unions — needs name-pattern disambiguation),
# PTY = Political party, SCC = Small contributor committee
ENTITY_CD_MAP: dict[str, str] = {
    "IND": INDIVIDUAL,
    "COM": PAC_IE,
    "PTY": PAC_IE,
    "SCC": PAC_IE,
    # OTH requires name-pattern disambiguation (could be corporate or union)
}

# ── Name patterns for inference ──
# Order matters: more specific patterns first.

_UNION_PATTERNS = re.compile(
    r"\b("
    r"union|local\s+\d|seiu|ibew|ufcw|afscme|aft\b|iatse|unite\s+here|"
    r"teamsters|laborers|plumbers|carpenters|firefighters|nurses|teachers|"
    r"workers|trades\s+council|labor\s+council|building\s+trades|"
    r"police\s+officers|officers\s+assoc|deputy\s+sheriffs|"
    r"correctional\s+officers|liuna|ciu|cwa|uaw|usw"
    r")\b",
    re.IGNORECASE,
)

_PAC_PATTERNS = re.compile(
    r"\b("
    r"pac$|political\s+action|independent\s+expenditure|"
    r"ballot\s+measure|committee|"
    r"for\s+council|for\s+mayor|for\s+supervisor|"
    r"for\s+assembly|for\s+senate|for\s+governor|"
    r"for\s+city\s+council|for\s+richmond"
    r")\b",
    re.IGNORECASE,
)

_CORPORATE_PATTERNS = re.compile(
    r"\b("
    r"inc\.?|corp\.?|llc|ltd\.?|l\.?l\.?c\.?|l\.?t\.?d\.?|"
    r"co\.|company|enterprises|holdings|group|partners|"
    r"associates|investments|properties|construction|"
    r"consulting|services|solutions|technologies|industries|"
    r"ventures|management|development|realty|builders|"
    r"contracting|advisors|capital|financial|funding|"
    r"real\s+estate|engineering|electric|plumbing|"
    r"roofing|paving|trucking|demolition|excavating|"
    r"landscaping|janitorial|security|staffing"
    r")\b",
    re.IGNORECASE,
)


def classify_contributor(
    name: str,
    entity_code: str | None = None,
    source: str = "netfile",
) -> tuple[str, str]:
    """Classify a contributor into one of five types.

    Args:
        name: Contributor/donor name.
        entity_code: Raw ENTITY_CD from CAL-ACCESS (IND, COM, OTH, etc.),
            or None for NetFile records.
        source: Data source ("calaccess" or "netfile").

    Returns:
        Tuple of (contributor_type, classification_source).
        classification_source is "entity_cd" for authoritative CAL-ACCESS
        mapping, or "inferred" for name-pattern heuristic.
    """
    name = (name or "").strip()

    # Path 1: Authoritative classification from CAL-ACCESS ENTITY_CD
    if entity_code:
        code = entity_code.strip().upper()
        if code in ENTITY_CD_MAP:
            mapped = ENTITY_CD_MAP[code]
            # For IND, trust it directly
            if mapped == INDIVIDUAL:
                return INDIVIDUAL, "entity_cd"
            # For COM/PTY/SCC, trust it but check for union PACs
            if mapped == PAC_IE:
                if _UNION_PATTERNS.search(name):
                    return UNION, "entity_cd"
                return PAC_IE, "entity_cd"

        # OTH = business or organization — disambiguate by name
        if code == "OTH":
            return _classify_by_name(name), "entity_cd"

    # Path 2: Inferred classification from name patterns (NetFile path)
    return _classify_by_name(name), "inferred"


def _classify_by_name(name: str) -> str:
    """Classify contributor type by name patterns alone.

    Priority order: union > pac > corporate > individual.
    Union first because union PACs often contain both "union" and "committee".
    """
    if not name:
        return OTHER

    # Union patterns (most specific)
    if _UNION_PATTERNS.search(name):
        return UNION

    # PAC/Committee patterns
    if _PAC_PATTERNS.search(name):
        return PAC_IE

    # Corporate patterns
    if _CORPORATE_PATTERNS.search(name):
        return CORPORATE

    # Default: individual (most common at city level)
    return INDIVIDUAL
