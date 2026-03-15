"""
Richmond Common - Meeting Minutes Extraction
Prompt templates and extraction logic for parsing meeting minutes.
Supports both city council and commission/board meeting formats.
"""
from __future__ import annotations

SYSTEM_PROMPT = """You are a precise data extraction system for the Richmond Common. 
Your job is to extract structured data from Richmond, CA City Council meeting minutes.

You must be extremely accurate. Every vote, every name, every motion must be captured exactly as 
stated in the source document. When in doubt, include the information with a note about uncertainty.

Key patterns in Richmond City Council minutes:
- Consent Calendar items are voted on as a block unless pulled for individual discussion
- Roll call votes list members as: Ayes (N): [names]. Noes (N): [names].
- Members have roles: Mayor, Vice Mayor, or Councilmember
- Friendly amendments may be accepted or rejected by the motion maker
- Items can be continued to future meetings
- Resolutions are numbered (e.g., "Resolution No. 134-25")
- Closed session items have limited reportable actions
- Public comments come from in-person, Zoom, phone, email, and eComment

CRITICAL: Capture ALL motions on an item, including failed motions, motions to reconsider, 
and calls to question. The political dynamics are in the failed motions and split votes, 
not just what passed."""

EXTRACTION_PROMPT = """Extract all structured data from the following Richmond, CA City Council 
meeting minutes. Return valid JSON matching this schema exactly.

{schema}

Meeting minutes to extract:
---
{minutes_text}
---

Return ONLY valid JSON. Do not include any explanation or commentary outside the JSON."""

# The JSON schema we send to Claude (simplified for the tool_use approach)
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "meeting_date": {
            "type": "string",
            "description": "ISO format date (YYYY-MM-DD)"
        },
        "meeting_type": {
            "type": "string",
            "enum": ["regular", "special", "closed_session", "joint"]
        },
        "call_to_order_time": {"type": "string"},
        "adjournment_time": {"type": "string"},
        "presiding_officer": {"type": "string"},
        "members_present": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {
                        "type": "string",
                        "enum": ["mayor", "vice_mayor", "councilmember"]
                    }
                }
            }
        },
        "members_absent": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "notes": {
                        "type": "string",
                        "description": "e.g., 'arrived after roll was called', 'absent for entire meeting'"
                    }
                }
            }
        },
        "conflict_of_interest_declared": {
            "type": "array",
            "description": "Any conflicts declared at the start of the meeting",
            "items": {"type": "string"}
        },
        "closed_session_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_number": {"type": "string"},
                    "legal_authority": {"type": "string"},
                    "description": {"type": "string"},
                    "parties": {"type": "array", "items": {"type": "string"}},
                    "reportable_action": {"type": "string"}
                }
            }
        },
        "consent_calendar": {
            "type": "object",
            "properties": {
                "motion_by": {"type": "string"},
                "seconded_by": {"type": "string"},
                "result": {"type": "string", "enum": ["passed", "failed"]},
                "vote_tally": {"type": "string"},
                "votes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "council_member": {"type": "string"},
                            "role": {"type": "string"},
                            "vote": {"type": "string", "enum": ["aye", "nay", "abstain", "absent"]}
                        }
                    }
                },
                "items_pulled_for_separate_vote": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_number": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "department": {"type": "string"},
                            "staff_contact": {"type": "string"},
                            "category": {
                                "type": "string",
                                "enum": [
                                    "zoning", "budget", "housing", "public_safety",
                                    "environment", "infrastructure", "personnel",
                                    "contracts", "governance", "proclamation",
                                    "litigation", "other", "appointments",
                                    "procedural"
                                ]
                            },
                            "resolution_number": {"type": "string"},
                            "financial_amount": {
                                "type": "string",
                                "description": "Dollar amount if a contract or expenditure"
                            }
                        }
                    }
                }
            }
        },
        "action_items": {
            "type": "array",
            "description": "Non-consent agenda items with individual votes",
            "items": {
                "type": "object",
                "properties": {
                    "item_number": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "department": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "zoning", "budget", "housing", "public_safety",
                            "environment", "infrastructure", "personnel",
                            "contracts", "governance", "proclamation",
                            "litigation", "other", "appointments",
                            "procedural"
                        ]
                    },
                    "continued_from": {
                        "type": "string",
                        "description": "Date if continued from a prior meeting"
                    },
                    "continued_to": {
                        "type": "string",
                        "description": "Date if continued to a future meeting"
                    },
                    "public_speakers": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "motions": {
                        "type": "array",
                        "description": "ALL motions on this item, including failed ones",
                        "items": {
                            "type": "object",
                            "properties": {
                                "motion_type": {
                                    "type": "string",
                                    "enum": [
                                        "original", "substitute",
                                        "friendly_amendment", "reconsider",
                                        "call_the_question"
                                    ]
                                },
                                "motion_by": {"type": "string"},
                                "seconded_by": {"type": "string"},
                                "motion_text": {"type": "string"},
                                "result": {"type": "string", "enum": ["passed", "failed"]},
                                "vote_tally": {"type": "string"},
                                "votes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "council_member": {"type": "string"},
                                            "role": {"type": "string"},
                                            "vote": {"type": "string"}
                                        }
                                    }
                                },
                                "friendly_amendments": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "proposed_by": {"type": "string"},
                                            "description": {"type": "string"},
                                            "accepted": {"type": "boolean"}
                                        }
                                    }
                                },
                                "resolution_number": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "public_comments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker_name": {"type": "string"},
                    "method": {
                        "type": "string",
                        "enum": ["in_person", "zoom", "phone", "email", "ecomment"]
                    },
                    "summary": {"type": "string"},
                    "related_items": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "council_reports": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "council_member": {"type": "string"},
                    "summary": {"type": "string"}
                }
            }
        },
        "adjournment": {
            "type": "object",
            "properties": {
                "time": {"type": "string"},
                "in_memory_of": {"type": "string"},
                "next_meeting": {"type": "string"}
            }
        }
    }
}


# ── Commission/Board Meeting Extraction ──────────────────────

COMMISSION_SYSTEM_PROMPT = """You are a precise data extraction system for the Richmond Common.
Your job is to extract structured data from Richmond, CA commission and board meeting minutes.

You must be extremely accurate. Every vote, every name, every motion must be captured exactly as
stated in the source document. When in doubt, include the information with a note about uncertainty.

Key patterns in Richmond commission/board meeting minutes:
- Commissions make RECOMMENDATIONS to City Council, not binding decisions (except Rent Board which has adjudicatory authority)
- Roll call votes list members as: Ayes (N): [names]. Noes (N): [names].
- Members have roles: Chair, Vice Chair, Commissioner, Member, Board Member, or Alternate
- Commissioners are appointed, not elected. Some seats represent specific constituencies
- Items may be continued to future meetings
- Public comments and public hearings are common, especially in Planning Commission and Rent Board
- Quorum requirements vary by commission (typically majority of appointed seats)
- Staff reports and recommendations often precede commission discussion

CRITICAL: Capture ALL motions on an item, including failed motions and split votes.
Capture the specific recommendation language — "recommend approval", "recommend denial",
"continue to next meeting", etc. The recommendation wording matters for City Council follow-up."""

COMMISSION_EXTRACTION_PROMPT = """Extract all structured data from the following Richmond, CA
commission/board meeting minutes. Return valid JSON matching this schema exactly.

{schema}

Meeting minutes to extract:
---
{minutes_text}
---

Return ONLY valid JSON. Do not include any explanation or commentary outside the JSON."""

COMMISSION_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "meeting_date": {
            "type": "string",
            "description": "ISO format date (YYYY-MM-DD)"
        },
        "meeting_type": {
            "type": "string",
            "enum": ["regular", "special", "closed_session", "joint"]
        },
        "call_to_order_time": {"type": "string"},
        "adjournment_time": {"type": "string"},
        "presiding_officer": {"type": "string"},
        "members_present": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {
                        "type": "string",
                        "enum": ["chair", "vice_chair", "commissioner",
                                 "member", "board_member", "alternate"]
                    }
                }
            }
        },
        "members_absent": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "notes": {
                        "type": "string",
                        "description": "e.g., 'excused', 'absent for entire meeting'"
                    }
                }
            }
        },
        "conflict_of_interest_declared": {
            "type": "array",
            "description": "Any conflicts declared at the start of the meeting",
            "items": {"type": "string"}
        },
        "action_items": {
            "type": "array",
            "description": "Agenda items with discussion, recommendations, and votes",
            "items": {
                "type": "object",
                "properties": {
                    "item_number": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "department": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "zoning", "budget", "housing", "public_safety",
                            "environment", "infrastructure", "personnel",
                            "contracts", "governance", "proclamation",
                            "litigation", "other", "appointments",
                            "procedural", "public_hearing"
                        ]
                    },
                    "continued_from": {
                        "type": "string",
                        "description": "Date if continued from a prior meeting"
                    },
                    "continued_to": {
                        "type": "string",
                        "description": "Date if continued to a future meeting"
                    },
                    "public_speakers": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "motions": {
                        "type": "array",
                        "description": "ALL motions on this item, including failed ones",
                        "items": {
                            "type": "object",
                            "properties": {
                                "motion_type": {
                                    "type": "string",
                                    "enum": [
                                        "original", "substitute",
                                        "friendly_amendment", "reconsider",
                                        "call_the_question"
                                    ]
                                },
                                "motion_by": {"type": "string"},
                                "seconded_by": {"type": "string"},
                                "motion_text": {
                                    "type": "string",
                                    "description": "Full motion text including recommendation language"
                                },
                                "result": {"type": "string", "enum": ["passed", "failed"]},
                                "vote_tally": {"type": "string"},
                                "votes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "council_member": {
                                                "type": "string",
                                                "description": "Commissioner/board member name"
                                            },
                                            "role": {"type": "string"},
                                            "vote": {"type": "string"}
                                        }
                                    }
                                },
                                "friendly_amendments": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "proposed_by": {"type": "string"},
                                            "description": {"type": "string"},
                                            "accepted": {"type": "boolean"}
                                        }
                                    }
                                },
                                "resolution_number": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "public_comments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker_name": {"type": "string"},
                    "method": {
                        "type": "string",
                        "enum": ["in_person", "zoom", "phone", "email", "ecomment"]
                    },
                    "summary": {"type": "string"},
                    "related_items": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "adjournment": {
            "type": "object",
            "properties": {
                "time": {"type": "string"},
                "in_memory_of": {"type": "string"},
                "next_meeting": {"type": "string"}
            }
        }
    }
}


def get_extraction_config(body_type: str = "city_council") -> tuple[str, dict, str]:
    """Return (system_prompt, schema, user_message_prefix) for a body type.

    Args:
        body_type: One of 'city_council', 'commission', 'board', 'authority',
                   'committee', 'joint'. Non-council types all use the
                   commission prompt/schema.

    Returns:
        Tuple of (system_prompt, extraction_schema, user_message_prefix).
    """
    if body_type == "city_council":
        return (
            SYSTEM_PROMPT,
            EXTRACTION_SCHEMA,
            "Extract all structured data from these Richmond, CA City Council meeting minutes:",
        )
    else:
        return (
            COMMISSION_SYSTEM_PROMPT,
            COMMISSION_EXTRACTION_SCHEMA,
            "Extract all structured data from these Richmond, CA commission/board meeting minutes:",
        )
