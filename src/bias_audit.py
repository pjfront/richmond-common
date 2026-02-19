"""
Richmond Transparency Project -- Periodic Bias Audit

Analyzes accumulated ground-truth data from audit sidecars to detect
systematic bias in the conflict scanner's matching logic.

See docs/specs/bias-audit-spec.md Section 6 for specification.

Reads all audit sidecar files from src/data/audit_runs/, filters to
only ground-truthed matched decisions, then computes:
  - Overall precision (TP / total)
  - Per-surname-tier false positive rates
  - Per-name-property false positive rates (compound, diacritics)
  - Disparity flags when Tier 4 FP rate exceeds 2x Tier 1

Usage:
  python bias_audit.py
  python bias_audit.py --min-decisions 50  # override minimum for testing
  python bias_audit.py --audit-dir path/to/audit_runs
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

AUDIT_DIR = Path(__file__).parent / "data" / "audit_runs"
DEFAULT_MIN_DECISIONS = 100


def load_all_verdicts(audit_dir: Path) -> list[dict]:
    """Load all ground-truthed decisions from audit sidecar files.

    Returns only decisions where:
      - matched is True (actual flags, not suppressed near-misses)
      - ground_truth is not None (has been reviewed)
    """
    verdicts = []
    for path in sorted(audit_dir.glob("*.json")):
        if path.name.startswith("bias_audit_report"):
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for d in data.get("decisions", []):
            if d.get("matched") and d.get("ground_truth") is not None:
                verdicts.append(d)
    return verdicts


def compute_bias_statistics(verdicts: list[dict]) -> dict:
    """Compute per-tier false positive rates and overall precision.

    Returns:
        dict with 'overall' stats, 'by_surname_tier' breakdown,
        and 'by_name_property' breakdown.
    """
    if not verdicts:
        return {
            "overall": {"total": 0, "true_positives": 0, "false_positives": 0, "precision": None},
            "by_surname_tier": {},
            "by_name_property": {},
        }

    total = len(verdicts)
    true_pos = sum(1 for v in verdicts if v["ground_truth"] is True)
    false_pos = total - true_pos

    # Per surname tier
    tier_stats = defaultdict(lambda: {"total": 0, "true_positives": 0, "false_positives": 0})
    for v in verdicts:
        tier = (v.get("bias_signals") or {}).get("surname_frequency_tier")
        tier_key = tier if tier is not None else "unknown"
        tier_stats[tier_key]["total"] += 1
        if v["ground_truth"] is True:
            tier_stats[tier_key]["true_positives"] += 1
        else:
            tier_stats[tier_key]["false_positives"] += 1

    for tier_key, stats in tier_stats.items():
        stats["false_positive_rate"] = (
            stats["false_positives"] / stats["total"] if stats["total"] > 0 else 0.0
        )

    # Per name property
    property_stats = {}
    for prop in ("has_compound_surname", "has_diacritics"):
        with_prop = [v for v in verdicts if (v.get("bias_signals") or {}).get(prop)]
        without_prop = [v for v in verdicts if not (v.get("bias_signals") or {}).get(prop)]
        property_stats[prop] = {
            "with": {
                "total": len(with_prop),
                "false_positives": sum(1 for v in with_prop if v["ground_truth"] is False),
                "false_positive_rate": (
                    sum(1 for v in with_prop if v["ground_truth"] is False) / len(with_prop)
                    if with_prop else 0.0
                ),
            },
            "without": {
                "total": len(without_prop),
                "false_positives": sum(1 for v in without_prop if v["ground_truth"] is False),
                "false_positive_rate": (
                    sum(1 for v in without_prop if v["ground_truth"] is False) / len(without_prop)
                    if without_prop else 0.0
                ),
            },
        }

    return {
        "overall": {
            "total": total,
            "true_positives": true_pos,
            "false_positives": false_pos,
            "precision": true_pos / total if total > 0 else None,
        },
        "by_surname_tier": dict(tier_stats),
        "by_name_property": property_stats,
    }


def format_bias_report(stats: dict) -> str:
    """Format bias statistics as a human-readable report."""
    lines = []
    lines.append("BIAS AUDIT REPORT")
    lines.append("=" * 60)

    overall = stats["overall"]
    lines.append(f"Total ground-truthed decisions: {overall['total']}")
    lines.append(f"True positives: {overall['true_positives']}")
    lines.append(f"False positives: {overall['false_positives']}")
    if overall["precision"] is not None:
        lines.append(f"Overall precision: {overall['precision']:.1%}")
    lines.append("")

    lines.append("FALSE POSITIVE RATE BY SURNAME FREQUENCY TIER")
    lines.append("-" * 60)
    tier_labels = {
        1: "Tier 1 (top 100)",
        2: "Tier 2 (top 1K)",
        3: "Tier 3 (top 10K)",
        4: "Tier 4 (rare)",
        "unknown": "Unknown",
    }
    for tier_key in [1, 2, 3, 4, "unknown"]:
        if tier_key in stats["by_surname_tier"]:
            t = stats["by_surname_tier"][tier_key]
            label = tier_labels.get(tier_key, str(tier_key))
            lines.append(f"  {label}: {t['false_positive_rate']:.1%} FP rate ({t['total']} decisions)")
    lines.append("")

    lines.append("FALSE POSITIVE RATE BY NAME PROPERTIES")
    lines.append("-" * 60)
    for prop, data in stats.get("by_name_property", {}).items():
        lines.append(f"  {prop}:")
        lines.append(f"    With:    {data['with']['false_positive_rate']:.1%} FP rate ({data['with']['total']} decisions)")
        lines.append(f"    Without: {data['without']['false_positive_rate']:.1%} FP rate ({data['without']['total']} decisions)")

    # Flag disparities
    lines.append("")
    lines.append("DISPARITY FLAGS")
    lines.append("-" * 60)
    tier_data = stats.get("by_surname_tier", {})
    if 1 in tier_data and 4 in tier_data:
        t1_rate = tier_data[1]["false_positive_rate"]
        t4_rate = tier_data[4]["false_positive_rate"]
        if t1_rate > 0 and t4_rate / t1_rate > 2.0:
            lines.append(f"  WARNING: Tier 4 (rare) surnames have {t4_rate/t1_rate:.1f}x the FP rate of Tier 1 (common)")
        elif t4_rate > t1_rate * 1.5:
            lines.append(f"  NOTE: Tier 4 FP rate ({t4_rate:.1%}) elevated vs Tier 1 ({t1_rate:.1%})")
        else:
            lines.append("  No significant disparity detected between Tier 1 and Tier 4")
    else:
        lines.append("  Insufficient data for tier comparison")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Richmond Transparency Project -- Periodic Bias Audit")
    parser.add_argument("--audit-dir", default=str(AUDIT_DIR), help="Path to audit_runs directory")
    parser.add_argument("--min-decisions", type=int, default=DEFAULT_MIN_DECISIONS,
                        help=f"Minimum ground-truthed decisions required (default: {DEFAULT_MIN_DECISIONS})")
    parser.add_argument("--output", help="Save report JSON to file")
    args = parser.parse_args()

    audit_dir = Path(args.audit_dir)
    print(f"Loading verdicts from {audit_dir} ...")
    verdicts = load_all_verdicts(audit_dir)
    print(f"Found {len(verdicts)} ground-truthed decisions")

    if len(verdicts) < args.min_decisions:
        print(f"\nInsufficient data for meaningful bias analysis.")
        print(f"Need {args.min_decisions}+ ground-truthed decisions, currently have {len(verdicts)}.")
        print(f"Use --min-decisions to override (for testing).")
        return

    stats = compute_bias_statistics(verdicts)
    report = format_bias_report(stats)
    print(f"\n{report}")

    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = audit_dir / f"bias_audit_report_{timestamp}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nReport JSON saved to {output_path}")


if __name__ == "__main__":
    main()
