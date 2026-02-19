"""
Richmond Transparency Project — Council Member Profile Builder

Aggregates data from extracted meeting JSON files to build
comprehensive profiles for each council member:
  - Voting record (aye/nay/abstain rates, split vote positions)
  - Attendance record
  - Motions made and seconded
  - Public comments related to their items
  - Coalition analysis (who votes together)

Works in two modes:
  - JSON mode: reads extracted meeting JSON files from disk
  - Database mode: queries Layer 2 tables

Usage:
    python council_profiles.py ./data/extracted/           # scan directory
    python council_profiles.py meeting1.json meeting2.json # specific files
    python council_profiles.py --db                        # from database
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Data Types ───────────────────────────────────────────────

@dataclass
class VoteRecord:
    """A single vote cast by a council member."""
    meeting_date: str
    item_number: str
    item_title: str
    category: str
    motion_type: str
    vote: str           # 'aye', 'nay', 'abstain', 'absent'
    result: str          # 'passed', 'failed'
    vote_tally: str      # '5-2', '7-0', etc.
    is_consent_calendar: bool
    financial_amount: Optional[str] = None


@dataclass
class MotionRecord:
    """A motion made or seconded by a council member."""
    meeting_date: str
    item_number: str
    item_title: str
    motion_type: str     # 'original', 'substitute', 'friendly_amendment', etc.
    role: str            # 'moved_by' or 'seconded_by'
    result: str
    vote_tally: str


@dataclass
class AttendanceRecord:
    """Attendance for one meeting."""
    meeting_date: str
    meeting_type: str
    status: str          # 'present', 'absent', 'late'
    notes: Optional[str] = None


@dataclass
class CouncilMemberProfile:
    """Complete profile for one council member."""
    name: str
    role: str            # most recent role
    city_fips: str

    # Voting
    total_votes: int = 0
    aye_count: int = 0
    nay_count: int = 0
    abstain_count: int = 0
    absent_count: int = 0
    consent_votes: int = 0
    non_consent_votes: int = 0
    votes: list[VoteRecord] = field(default_factory=list)

    # Motions
    motions_made: int = 0
    motions_seconded: int = 0
    motions: list[MotionRecord] = field(default_factory=list)

    # Attendance
    meetings_present: int = 0
    meetings_absent: int = 0
    meetings_late: int = 0
    attendance: list[AttendanceRecord] = field(default_factory=list)

    # Category breakdown
    votes_by_category: dict = field(default_factory=lambda: defaultdict(lambda: {"aye": 0, "nay": 0, "abstain": 0}))

    # Split votes (non-unanimous) — the interesting ones
    split_vote_positions: list[dict] = field(default_factory=list)

    # Friendly amendments proposed
    amendments_proposed: int = 0
    amendments_accepted: int = 0

    @property
    def aye_rate(self) -> float:
        """Percentage of non-absent votes that were aye."""
        active = self.aye_count + self.nay_count + self.abstain_count
        return self.aye_count / active if active > 0 else 0.0

    @property
    def attendance_rate(self) -> float:
        """Percentage of meetings attended (present or late)."""
        total = self.meetings_present + self.meetings_absent + self.meetings_late
        return (self.meetings_present + self.meetings_late) / total if total > 0 else 0.0

    @property
    def dissent_rate(self) -> float:
        """Percentage of non-consent, non-absent votes that were nay."""
        active_non_consent = sum(
            1 for v in self.votes
            if not v.is_consent_calendar and v.vote in ("aye", "nay", "abstain")
        )
        nay_non_consent = sum(
            1 for v in self.votes
            if not v.is_consent_calendar and v.vote == "nay"
        )
        return nay_non_consent / active_non_consent if active_non_consent > 0 else 0.0


# ── Profile Builder (JSON Mode) ──────────────────────────────

def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


def build_profiles_from_json(
    meeting_files: list[str],
    city_fips: str = "0660620",
) -> dict[str, CouncilMemberProfile]:
    """Build council member profiles from extracted meeting JSON files.

    Args:
        meeting_files: Paths to extracted meeting JSON files
        city_fips: FIPS code (default: Richmond CA)

    Returns:
        Dict mapping normalized name -> CouncilMemberProfile
    """
    profiles: dict[str, CouncilMemberProfile] = {}

    def get_profile(name: str, role: str = "councilmember") -> CouncilMemberProfile:
        key = _normalize_name(name)
        if key not in profiles:
            profiles[key] = CouncilMemberProfile(name=name, role=role, city_fips=city_fips)
        else:
            # Update role if more specific (mayor > vice_mayor > councilmember)
            role_rank = {"mayor": 3, "vice_mayor": 2, "councilmember": 1}
            if role_rank.get(role, 0) > role_rank.get(profiles[key].role, 0):
                profiles[key].role = role
        return profiles[key]

    for filepath in meeting_files:
        with open(filepath) as f:
            data = json.load(f)

        meeting_date = data.get("meeting_date", "unknown")
        meeting_type = data.get("meeting_type", "regular")

        # ── Attendance ──
        for member in data.get("members_present", []):
            p = get_profile(member["name"], member.get("role", "councilmember"))
            late_info = next(
                (m for m in data.get("members_late", [])
                 if _normalize_name(m["name"]) == _normalize_name(member["name"])),
                None,
            )
            if late_info:
                p.meetings_late += 1
                p.attendance.append(AttendanceRecord(
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    status="late",
                    notes=late_info.get("notes"),
                ))
            else:
                p.meetings_present += 1
                p.attendance.append(AttendanceRecord(
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    status="present",
                ))

        for member in data.get("members_absent", []):
            p = get_profile(member["name"], member.get("role", "councilmember"))
            p.meetings_absent += 1
            p.attendance.append(AttendanceRecord(
                meeting_date=meeting_date,
                meeting_type=meeting_type,
                status="absent",
                notes=member.get("notes"),
            ))

        # ── Consent Calendar Votes ──
        consent = data.get("consent_calendar", {})
        consent_item_count = len(consent.get("items", []))
        for vote in consent.get("votes", []):
            p = get_profile(vote["council_member"], vote.get("role", "councilmember"))
            p.total_votes += consent_item_count
            p.consent_votes += consent_item_count
            if vote["vote"] == "aye":
                p.aye_count += consent_item_count
            elif vote["vote"] == "nay":
                p.nay_count += consent_item_count
            elif vote["vote"] == "abstain":
                p.abstain_count += consent_item_count
            elif vote["vote"] == "absent":
                p.absent_count += consent_item_count

            for consent_item in consent.get("items", []):
                p.votes.append(VoteRecord(
                    meeting_date=meeting_date,
                    item_number=consent_item.get("item_number", ""),
                    item_title=consent_item.get("title", ""),
                    category=consent_item.get("category", "other"),
                    motion_type="consent_calendar",
                    vote=vote["vote"],
                    result=consent.get("result", "passed"),
                    vote_tally=consent.get("vote_tally", ""),
                    is_consent_calendar=True,
                    financial_amount=consent_item.get("financial_amount"),
                ))

                cat = consent_item.get("category", "other")
                p.votes_by_category[cat][vote["vote"]] += 1

        # Record consent calendar motion
        if consent.get("motion_by"):
            p = get_profile(consent["motion_by"])
            p.motions_made += 1
            p.motions.append(MotionRecord(
                meeting_date=meeting_date,
                item_number="consent_calendar",
                item_title="Consent Calendar",
                motion_type="consent_calendar",
                role="moved_by",
                result=consent.get("result", "passed"),
                vote_tally=consent.get("vote_tally", ""),
            ))
        if consent.get("seconded_by"):
            p = get_profile(consent["seconded_by"])
            p.motions_seconded += 1
            p.motions.append(MotionRecord(
                meeting_date=meeting_date,
                item_number="consent_calendar",
                item_title="Consent Calendar",
                motion_type="consent_calendar",
                role="seconded_by",
                result=consent.get("result", "passed"),
                vote_tally=consent.get("vote_tally", ""),
            ))

        # ── Action Item Votes ──
        for item in data.get("action_items", []):
            item_num = item.get("item_number", "")
            item_title = item.get("title", "")
            category = item.get("category", "other")

            for motion in item.get("motions", []):
                motion_type = motion.get("motion_type", "original")
                result = motion.get("result", "")
                tally = motion.get("vote_tally", "")

                # Detect if this is a split vote
                is_split = tally and not tally.endswith("-0")

                # Record motion maker
                if motion.get("motion_by"):
                    p = get_profile(motion["motion_by"])
                    p.motions_made += 1
                    p.motions.append(MotionRecord(
                        meeting_date=meeting_date,
                        item_number=item_num,
                        item_title=item_title,
                        motion_type=motion_type,
                        role="moved_by",
                        result=result,
                        vote_tally=tally,
                    ))

                if motion.get("seconded_by"):
                    p = get_profile(motion["seconded_by"])
                    p.motions_seconded += 1
                    p.motions.append(MotionRecord(
                        meeting_date=meeting_date,
                        item_number=item_num,
                        item_title=item_title,
                        motion_type=motion_type,
                        role="seconded_by",
                        result=result,
                        vote_tally=tally,
                    ))

                # Record votes
                all_votes_on_motion = {}
                for vote in motion.get("votes", []):
                    p = get_profile(vote["council_member"], vote.get("role", "councilmember"))
                    p.total_votes += 1
                    p.non_consent_votes += 1
                    v = vote["vote"]
                    if v == "aye":
                        p.aye_count += 1
                    elif v == "nay":
                        p.nay_count += 1
                    elif v == "abstain":
                        p.abstain_count += 1
                    elif v == "absent":
                        p.absent_count += 1

                    p.votes.append(VoteRecord(
                        meeting_date=meeting_date,
                        item_number=item_num,
                        item_title=item_title,
                        category=category,
                        motion_type=motion_type,
                        vote=v,
                        result=result,
                        vote_tally=tally,
                        is_consent_calendar=False,
                    ))

                    p.votes_by_category[category][v] += 1
                    all_votes_on_motion[_normalize_name(vote["council_member"])] = v

                # Record split vote positions
                if is_split:
                    for vote in motion.get("votes", []):
                        p = get_profile(vote["council_member"])
                        p.split_vote_positions.append({
                            "meeting_date": meeting_date,
                            "item_number": item_num,
                            "item_title": item_title,
                            "motion_type": motion_type,
                            "vote": vote["vote"],
                            "result": result,
                            "vote_tally": tally,
                        })

                # Record friendly amendments
                for amendment in motion.get("friendly_amendments", []):
                    if amendment.get("proposed_by"):
                        p = get_profile(amendment["proposed_by"])
                        p.amendments_proposed += 1
                        if amendment.get("accepted"):
                            p.amendments_accepted += 1

    return profiles


# ── Coalition Analysis ────────────────────────────────────────

def analyze_coalitions(profiles: dict[str, CouncilMemberProfile]) -> dict:
    """Analyze voting coalitions: who votes together on split votes.

    Returns a dict of member pairs -> agreement rate on split votes.
    """
    # Collect all split vote records indexed by (meeting_date, item_number, motion_type)
    vote_map: dict[tuple, dict[str, str]] = defaultdict(dict)

    for name, profile in profiles.items():
        for sv in profile.split_vote_positions:
            key = (sv["meeting_date"], sv["item_number"], sv["motion_type"])
            vote_map[key][name] = sv["vote"]

    # Calculate pairwise agreement
    members = list(profiles.keys())
    agreements: dict[tuple, dict] = {}

    for i, m1 in enumerate(members):
        for m2 in members[i + 1:]:
            agree = 0
            disagree = 0
            for key, votes in vote_map.items():
                if m1 in votes and m2 in votes:
                    v1, v2 = votes[m1], votes[m2]
                    # Only count aye/nay votes, not absent/abstain
                    if v1 in ("aye", "nay") and v2 in ("aye", "nay"):
                        if v1 == v2:
                            agree += 1
                        else:
                            disagree += 1

            total = agree + disagree
            if total > 0:
                agreements[(m1, m2)] = {
                    "agree": agree,
                    "disagree": disagree,
                    "total": total,
                    "agreement_rate": agree / total,
                }

    return agreements


# ── Report Generation ────────────────────────────────────────

def format_profile_report(
    profiles: dict[str, CouncilMemberProfile],
    coalitions: dict = None,
) -> str:
    """Format all profiles into a human-readable report."""
    lines = []
    lines.append("RICHMOND CITY COUNCIL — MEMBER PROFILES")
    lines.append("=" * 70)

    # Sort by role (mayor first, then vice mayor, then alphabetical)
    role_order = {"mayor": 0, "vice_mayor": 1, "councilmember": 2}
    sorted_profiles = sorted(
        profiles.values(),
        key=lambda p: (role_order.get(p.role, 9), p.name),
    )

    for p in sorted_profiles:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"  {p.name} ({p.role.replace('_', ' ').title()})")
        lines.append(f"{'─' * 70}")

        # Attendance
        total_meetings = p.meetings_present + p.meetings_absent + p.meetings_late
        lines.append(f"\n  ATTENDANCE ({total_meetings} meetings)")
        lines.append(f"    Present: {p.meetings_present}  |  Late: {p.meetings_late}  |  Absent: {p.meetings_absent}")
        lines.append(f"    Attendance rate: {p.attendance_rate:.0%}")

        # Voting summary
        active_votes = p.aye_count + p.nay_count + p.abstain_count
        lines.append(f"\n  VOTING RECORD ({p.total_votes} total votes, {active_votes} active)")
        lines.append(f"    Aye: {p.aye_count} ({p.aye_rate:.0%})  |  Nay: {p.nay_count}  |  Abstain: {p.abstain_count}  |  Absent: {p.absent_count}")
        lines.append(f"    Consent calendar: {p.consent_votes}  |  Non-consent: {p.non_consent_votes}")
        lines.append(f"    Dissent rate (non-consent): {p.dissent_rate:.0%}")

        # Category breakdown (only non-consent)
        if p.votes_by_category:
            lines.append(f"\n  VOTES BY CATEGORY")
            for cat, counts in sorted(p.votes_by_category.items()):
                total = counts["aye"] + counts["nay"] + counts["abstain"]
                if total > 0:
                    lines.append(f"    {cat:20s}  aye: {counts['aye']:2d}  nay: {counts['nay']:2d}  abstain: {counts['abstain']:2d}")

        # Motions
        lines.append(f"\n  MOTIONS")
        lines.append(f"    Made: {p.motions_made}  |  Seconded: {p.motions_seconded}")
        lines.append(f"    Amendments proposed: {p.amendments_proposed} (accepted: {p.amendments_accepted})")

        # Split votes
        if p.split_vote_positions:
            lines.append(f"\n  SPLIT VOTE POSITIONS ({len(p.split_vote_positions)})")
            for sv in p.split_vote_positions[:10]:  # Show first 10
                side = "MAJORITY" if (
                    (sv["vote"] == "aye" and sv["result"] == "passed") or
                    (sv["vote"] == "nay" and sv["result"] == "failed")
                ) else "MINORITY"
                lines.append(
                    f"    {sv['meeting_date']} {sv['item_number']}: "
                    f"{sv['vote'].upper()} ({sv['vote_tally']}, {sv['result']}) [{side}]"
                    f" — {sv['item_title'][:50]}"
                )
            if len(p.split_vote_positions) > 10:
                lines.append(f"    ... and {len(p.split_vote_positions) - 10} more")

    # Coalition analysis
    if coalitions:
        lines.append(f"\n\n{'=' * 70}")
        lines.append("VOTING COALITIONS (agreement rate on split votes)")
        lines.append("=" * 70)

        # Sort by agreement rate descending
        sorted_pairs = sorted(coalitions.items(), key=lambda x: -x[1]["agreement_rate"])
        for (m1, m2), stats in sorted_pairs:
            name1 = profiles[m1].name
            name2 = profiles[m2].name
            lines.append(
                f"  {name1:25s} <-> {name2:25s}  "
                f"{stats['agreement_rate']:5.0%} "
                f"({stats['agree']}/{stats['total']} agree)"
            )

    lines.append(f"\n{'=' * 70}")
    lines.append("Generated by Richmond Transparency Project")

    return "\n".join(lines)


def profiles_to_json(profiles: dict[str, CouncilMemberProfile]) -> list[dict]:
    """Export profiles as JSON-serializable dicts."""
    result = []
    for key, p in profiles.items():
        result.append({
            "name": p.name,
            "role": p.role,
            "city_fips": p.city_fips,
            "attendance": {
                "present": p.meetings_present,
                "absent": p.meetings_absent,
                "late": p.meetings_late,
                "rate": round(p.attendance_rate, 3),
            },
            "voting": {
                "total": p.total_votes,
                "aye": p.aye_count,
                "nay": p.nay_count,
                "abstain": p.abstain_count,
                "absent": p.absent_count,
                "consent_calendar": p.consent_votes,
                "non_consent": p.non_consent_votes,
                "aye_rate": round(p.aye_rate, 3),
                "dissent_rate": round(p.dissent_rate, 3),
            },
            "motions": {
                "made": p.motions_made,
                "seconded": p.motions_seconded,
                "amendments_proposed": p.amendments_proposed,
                "amendments_accepted": p.amendments_accepted,
            },
            "votes_by_category": {
                cat: dict(counts) for cat, counts in p.votes_by_category.items()
            },
            "split_vote_count": len(p.split_vote_positions),
        })
    return result


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Richmond Transparency Project — Council Member Profiles")
    parser.add_argument("paths", nargs="+", help="Meeting JSON files or directory containing them")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", help="Save report to file")

    args = parser.parse_args()

    # Collect JSON files
    meeting_files = []
    for path in args.paths:
        p = Path(path)
        if p.is_dir():
            meeting_files.extend(sorted(p.glob("*_council_meeting.json")))
        elif p.is_file() and p.suffix == ".json":
            meeting_files.append(p)
        else:
            print(f"Skipping: {path}")

    if not meeting_files:
        print("No meeting JSON files found.")
        return

    print(f"Processing {len(meeting_files)} meeting(s)...")

    profiles = build_profiles_from_json([str(f) for f in meeting_files])
    coalitions = analyze_coalitions(profiles)

    if args.json:
        output = json.dumps(profiles_to_json(profiles), indent=2)
    else:
        output = format_profile_report(profiles, coalitions)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Output saved to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
