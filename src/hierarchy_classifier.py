"""Title-based hierarchy classification for city employees.

Uses keyword pattern matching to infer organizational hierarchy
from job titles. Zero LLM cost — structured data + heuristics.

Levels:
    1 = Executive (City Manager, City Attorney, City Clerk)
    2 = Department Head (Director, Chief, City Engineer)
    3 = Senior Management (Assistant/Deputy Director, Division Manager)
    4 = Mid-Management (Supervisor, Senior Manager, Principal, Battalion Chief)
    0 = Unclassified (all other employees)
"""
from __future__ import annotations

import re

LEVEL_LABELS = {
    0: "Unclassified",
    1: "Executive",
    2: "Department Head",
    3: "Senior Management",
    4: "Mid-Management",
}

# Titles that contain "chief" but are NOT department heads.
# These are trade ranks or mid-level operational roles.
_CHIEF_EXCLUSIONS = re.compile(
    r"\b(chief\s+electrician|chief\s+mechanic|chief\s+operator"
    r"|chief\s+technician|chief\s+dispatcher)\b"
)

# Battalion chief is a fire service rank (mid-management, not dept head)
_BATTALION_CHIEF = re.compile(r"\bbattalion\s+chief\b")

# Order matters: check level 3 (assistant/deputy) BEFORE level 2 (director/chief)
# so "Assistant Director" doesn't match "Director" first.
_LEVEL_3_PATTERNS = [
    re.compile(r"\bassistant\s+(city\s+manager|city\s+attorney|city\s+clerk|director|chief)\b"),
    re.compile(r"\bassistant\s+to\s+the\b"),
    re.compile(r"\bdeputy\s+(director|chief|city|building|fire)\b"),
    re.compile(r"\bdep\s+dir\b(?!.*\bcity\s+engineer\b)"),  # "DEP DIR" but NOT if also "CITY ENGINEER"
    re.compile(r"\bdivision\s+manager\b"),
    re.compile(r"\bassistant\s+deputy\b"),
]

_LEVEL_1_PATTERNS = [
    re.compile(r"\bcity\s+manager\b"),
    re.compile(r"\bcity\s+attorney\b"),
    re.compile(r"\bcity\s+clerk\b"),
]

_LEVEL_2_PATTERNS = [
    re.compile(r"\bdirector\b"),
    re.compile(r"\bcity\s+engineer\b"),
    # "chief" — but exclude trade ranks and battalion chiefs
    re.compile(r"\bchief\b"),
]

_LEVEL_4_PATTERNS = [
    re.compile(r"\bsupervisor\b"),
    re.compile(r"\bsenior\s+manager\b"),
    re.compile(r"\bprincipal\s+(planner|analyst|engineer|accountant)\b"),
]


def classify_title(title: str | None) -> tuple[int, bool]:
    """Classify a job title into hierarchy level and department head status.

    Returns:
        (hierarchy_level, is_department_head) tuple.
        Levels 1-2 are department heads. Level 0 is unclassified.
    """
    if not title:
        return 0, False

    t = title.lower().strip()

    # Exclude trade-rank "chief" titles early — these are level 0
    if _CHIEF_EXCLUSIONS.search(t):
        return 0, False

    # Battalion chief is mid-management (level 4), not a department head
    if _BATTALION_CHIEF.search(t):
        return 4, False

    # Check level 3 FIRST — "assistant director" should not match "director"
    for pattern in _LEVEL_3_PATTERNS:
        if pattern.search(t):
            return 3, False

    for pattern in _LEVEL_1_PATTERNS:
        if pattern.search(t):
            return 1, True

    for pattern in _LEVEL_2_PATTERNS:
        if pattern.search(t):
            return 2, True

    for pattern in _LEVEL_4_PATTERNS:
        if pattern.search(t):
            return 4, False

    return 0, False
