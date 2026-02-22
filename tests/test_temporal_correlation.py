# tests/test_temporal_correlation.py
"""Tests for temporal correlation analysis (post-vote donation detection)."""
import pytest
from datetime import date


def test_time_decay_multiplier_immediate():
    """0-90 days after vote should have highest confidence multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(30) == 1.0
    assert get_time_decay_multiplier(90) == 1.0


def test_time_decay_multiplier_election_cycle():
    """91-180 days after vote should have 0.85 multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(91) == 0.85
    assert get_time_decay_multiplier(180) == 0.85


def test_time_decay_multiplier_annual():
    """181-365 days after vote should have 0.7 multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(200) == 0.7
    assert get_time_decay_multiplier(365) == 0.7


def test_time_decay_multiplier_reelection():
    """366-730 days should have 0.5 multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(400) == 0.5
    assert get_time_decay_multiplier(730) == 0.5


def test_time_decay_multiplier_long_term():
    """731-1825 days should have 0.3 multiplier."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(800) == 0.3
    assert get_time_decay_multiplier(1825) == 0.3


def test_time_decay_multiplier_beyond_window():
    """Beyond max lookback should return 0.0."""
    from conflict_scanner import get_time_decay_multiplier
    assert get_time_decay_multiplier(1826) == 0.0
    assert get_time_decay_multiplier(3000) == 0.0


def test_extract_votes_from_action_item():
    """Extract aye voters from an action item with motions."""
    from conflict_scanner import extract_aye_voters
    item = {
        "item_number": "H-5",
        "title": "Approve contract with Acme Corp",
        "motions": [
            {
                "result": "passed",
                "votes": [
                    {"council_member": "Eduardo Martinez", "vote": "aye"},
                    {"council_member": "Sue Wilson", "vote": "aye"},
                    {"council_member": "Jamelia Brown", "vote": "nay"},
                ]
            }
        ]
    }
    voters = extract_aye_voters(item)
    assert "Eduardo Martinez" in voters
    assert "Sue Wilson" in voters
    assert "Jamelia Brown" not in voters


def test_extract_votes_from_consent_item():
    """Consent items inherit the consent calendar's vote record."""
    from conflict_scanner import extract_aye_voters
    item = {
        "item_number": "I-1",
        "title": "Approve payment to BuildCo",
    }
    consent_votes = [
        {"council_member": "Eduardo Martinez", "vote": "aye"},
        {"council_member": "Claudia Jimenez", "vote": "aye"},
        {"council_member": "Cesar Zepeda", "vote": "absent"},
    ]
    voters = extract_aye_voters(item, consent_votes=consent_votes)
    assert "Eduardo Martinez" in voters
    assert "Claudia Jimenez" in voters
    assert "Cesar Zepeda" not in voters


def test_extract_votes_no_vote_data():
    """Items without votes return empty set."""
    from conflict_scanner import extract_aye_voters
    item = {"item_number": "A-1", "title": "Presentation"}
    voters = extract_aye_voters(item)
    assert voters == set()


def test_extract_votes_failed_motion():
    """Only extract from passed motions."""
    from conflict_scanner import extract_aye_voters
    item = {
        "item_number": "H-3",
        "title": "Deny rezoning",
        "motions": [
            {
                "result": "failed",
                "votes": [
                    {"council_member": "Eduardo Martinez", "vote": "aye"},
                ]
            }
        ]
    }
    voters = extract_aye_voters(item)
    assert voters == set()
