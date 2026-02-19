"""
Richmond Transparency Project — Scan Audit Logger

Logs matching decisions (flags + near-misses) and per-scan filter funnel
statistics for bias audit analysis.

Phase 1: JSON sidecar files (pre-database).
Phase 2+: Write directly to matching_decisions and scan_audit_summary tables.

See docs/specs/bias-audit-spec.md for full specification.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from bias_signals import compute_bias_risk_signals


@dataclass
class MatchingDecision:
    """One match or near-miss from the conflict scanner.

    Logged for every flag produced AND every match suppressed by
    council-member, government-employer, or government-donor filters.
    """
    donor_name: str
    donor_employer: str
    agenda_item_number: str
    agenda_text_preview: str       # first 500 chars of item text
    match_type: str                # 'exact', 'contains', 'employer_match', 'suppressed_council_member', etc.
    confidence: float
    matched: bool                  # True = flag produced, False = suppressed

    # Auto-computed
    bias_signals: dict = field(default=None, init=False)

    # Ground truth (populated during review)
    ground_truth: bool = None
    ground_truth_source: str = None
    audit_notes: str = None

    def __post_init__(self):
        self.bias_signals = compute_bias_risk_signals(self.donor_name)
        # Truncate preview to 500 chars
        if self.agenda_text_preview and len(self.agenda_text_preview) > 500:
            self.agenda_text_preview = self.agenda_text_preview[:500]

    def to_dict(self) -> dict:
        return {
            "donor_name": self.donor_name,
            "donor_employer": self.donor_employer,
            "agenda_item_number": self.agenda_item_number,
            "agenda_text_preview": self.agenda_text_preview,
            "match_type": self.match_type,
            "confidence": self.confidence,
            "matched": self.matched,
            "bias_signals": self.bias_signals,
            "ground_truth": self.ground_truth,
            "ground_truth_source": self.ground_truth_source,
            "audit_notes": self.audit_notes,
        }


@dataclass
class ScanAuditSummary:
    """Per-scan filter funnel statistics."""
    scan_run_id: str
    city_fips: str
    meeting_date: str
    total_agenda_items: int
    total_contributions_compared: int

    # Filter funnel counts
    filtered_no_text_match: int = 0
    filtered_short_name: int = 0
    filtered_council_member: int = 0
    filtered_govt_employer: int = 0
    filtered_govt_donor: int = 0
    filtered_dedup: int = 0
    passed_to_flag: int = 0
    suppressed_near_miss: int = 0

    # Surname tier distribution — all donors compared
    donors_surname_tier_1: int = 0
    donors_surname_tier_2: int = 0
    donors_surname_tier_3: int = 0
    donors_surname_tier_4: int = 0
    donors_surname_unknown: int = 0

    # Surname tier distribution — flagged donors only
    flagged_surname_tier_1: int = 0
    flagged_surname_tier_2: int = 0
    flagged_surname_tier_3: int = 0
    flagged_surname_tier_4: int = 0
    flagged_surname_unknown: int = 0

    @property
    def total_comparisons(self) -> int:
        return self.total_agenda_items * self.total_contributions_compared

    def to_dict(self) -> dict:
        return {
            "scan_run_id": self.scan_run_id,
            "city_fips": self.city_fips,
            "meeting_date": self.meeting_date,
            "total_agenda_items": self.total_agenda_items,
            "total_contributions_compared": self.total_contributions_compared,
            "total_comparisons": self.total_comparisons,
            "filtered_no_text_match": self.filtered_no_text_match,
            "filtered_short_name": self.filtered_short_name,
            "filtered_council_member": self.filtered_council_member,
            "filtered_govt_employer": self.filtered_govt_employer,
            "filtered_govt_donor": self.filtered_govt_donor,
            "filtered_dedup": self.filtered_dedup,
            "passed_to_flag": self.passed_to_flag,
            "suppressed_near_miss": self.suppressed_near_miss,
            "donors_surname_tier_1": self.donors_surname_tier_1,
            "donors_surname_tier_2": self.donors_surname_tier_2,
            "donors_surname_tier_3": self.donors_surname_tier_3,
            "donors_surname_tier_4": self.donors_surname_tier_4,
            "donors_surname_unknown": self.donors_surname_unknown,
            "flagged_surname_tier_1": self.flagged_surname_tier_1,
            "flagged_surname_tier_2": self.flagged_surname_tier_2,
            "flagged_surname_tier_3": self.flagged_surname_tier_3,
            "flagged_surname_tier_4": self.flagged_surname_tier_4,
            "flagged_surname_unknown": self.flagged_surname_unknown,
        }


class ScanAuditLogger:
    """Collects matching decisions during a scan run and saves to JSON sidecar.

    Usage:
        logger = ScanAuditLogger()
        # During scan...
        logger.log_decision(MatchingDecision(...))
        # After scan...
        logger.summary = ScanAuditSummary(...)
        logger.save(Path("audit_2026-02-17.json"))
    """

    def __init__(self, scan_run_id: str = None):
        self.scan_run_id = scan_run_id or str(uuid.uuid4())
        self.decisions: list[MatchingDecision] = []
        self.summary: ScanAuditSummary = None

    def log_decision(self, decision: MatchingDecision):
        self.decisions.append(decision)

    def save(self, output_path: Path):
        """Write decisions + summary to a JSON sidecar file."""
        data = {
            "scan_run_id": self.scan_run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "decisions": [d.to_dict() for d in self.decisions],
            "summary": self.summary.to_dict() if self.summary else None,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
