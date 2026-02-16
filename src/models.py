"""
Richmond Transparency Project - Data Models
Core data structures for extracting and storing city council meeting data.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class VoteChoice(str, Enum):
    AYE = "aye"
    NAY = "nay"
    ABSTAIN = "abstain"
    ABSENT = "absent"


class VoteResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class MeetingType(str, Enum):
    REGULAR = "regular"
    SPECIAL = "special"
    CLOSED_SESSION = "closed_session"
    JOINT = "joint"


class AgendaCategory(str, Enum):
    ZONING = "zoning"
    BUDGET = "budget"
    HOUSING = "housing"
    PUBLIC_SAFETY = "public_safety"
    ENVIRONMENT = "environment"
    INFRASTRUCTURE = "infrastructure"
    PERSONNEL = "personnel"
    CONTRACTS = "contracts"
    GOVERNANCE = "governance"
    PROCLAMATION = "proclamation"
    LITIGATION = "litigation"
    OTHER = "other"


class MotionType(str, Enum):
    ORIGINAL = "original"
    SUBSTITUTE = "substitute"
    FRIENDLY_AMENDMENT = "friendly_amendment"
    RECONSIDER = "reconsider"
    CALL_THE_QUESTION = "call_the_question"


@dataclass
class CouncilMember:
    name: str
    role: str  # e.g., "councilmember", "vice_mayor", "mayor"
    seat: Optional[str] = None
    term_start: Optional[date] = None
    term_end: Optional[date] = None


@dataclass
class IndividualVote:
    council_member: str
    role: str  # mayor, vice_mayor, councilmember
    vote: VoteChoice


@dataclass
class Motion:
    motion_type: MotionType
    motion_by: str
    seconded_by: Optional[str]
    motion_text: str
    result: VoteResult
    vote_tally: str  # e.g., "5-2"
    votes: list[IndividualVote]
    friendly_amendments: list[dict] = field(default_factory=list)


@dataclass
class AgendaItem:
    item_number: str  # e.g., "O.1.a", "P.1", "C.2"
    title: str
    description: str
    department: Optional[str]
    staff_contact: Optional[str]
    category: AgendaCategory
    is_consent_calendar: bool
    was_pulled_from_consent: bool
    motions: list[Motion]
    resolution_number: Optional[str] = None
    continued_to: Optional[str] = None
    continued_from: Optional[str] = None
    public_speakers: list[str] = field(default_factory=list)


@dataclass
class ClosedSessionItem:
    item_number: str
    legal_authority: str  # e.g., "Government Code Section 54956.9"
    description: str
    parties: list[str]
    reportable_action: Optional[str]


@dataclass
class PublicComment:
    speaker_name: str
    method: str  # "in_person", "zoom", "email", "ecomment"
    summary: str
    related_agenda_items: list[str]  # item numbers referenced


@dataclass
class Meeting:
    meeting_date: date
    meeting_type: MeetingType
    call_to_order_time: str
    adjournment_time: Optional[str]
    presiding_officer: str
    members_present: list[CouncilMember]
    members_absent: list[CouncilMember]
    members_late: list[dict]  # name + arrival context
    closed_session_items: list[ClosedSessionItem]
    consent_calendar_items: list[AgendaItem]
    consent_calendar_vote: Optional[Motion]
    action_items: list[AgendaItem]  # non-consent items
    public_comments: list[PublicComment]
    city_manager_report: Optional[str]
    proclamations: list[dict]
    council_reports: list[dict]  # AB 1234 reports, committee updates
    adjourned_in_memory_of: Optional[str]
    next_meeting_date: Optional[str]
    source_url: Optional[str] = None
    source_document: Optional[str] = None


# --- Campaign Finance Models (for Phase 2) ---

@dataclass
class Donor:
    name: str
    employer: Optional[str]
    occupation: Optional[str]
    address: Optional[str]


@dataclass
class Contribution:
    donor: Donor
    recipient_committee: str
    amount: float
    date: date
    filing_id: str  # FPPC filing reference
    contribution_type: str  # monetary, nonmonetary, loan


@dataclass
class ConflictFlag:
    """Generated when cross-referencing vote data with financial/property data."""
    agenda_item: str
    council_member: str
    flag_type: str  # "campaign_contribution", "property_proximity", "form700_interest"
    description: str
    evidence: list[dict]  # source documents and specifics
    confidence: float  # 0-1, how confident the system is this is a real flag
    legal_reference: str  # relevant Gov Code section
