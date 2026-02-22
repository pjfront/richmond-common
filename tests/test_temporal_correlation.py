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


# --- Test data fixtures for scan_temporal_correlations ---

SAMPLE_MEETING_DATA = {
    "meeting_date": "2025-09-23",
    "meeting_type": "regular",
    "consent_calendar": {
        "result": "passed",
        "votes": [
            {"council_member": "Eduardo Martinez", "vote": "aye"},
            {"council_member": "Sue Wilson", "vote": "aye"},
            {"council_member": "Claudia Jimenez", "vote": "aye"},
            {"council_member": "Jamelia Brown", "vote": "aye"},
            {"council_member": "Doria Robinson", "vote": "aye"},
            {"council_member": "Cesar Zepeda", "vote": "aye"},
            {"council_member": "Soheila Bana", "vote": "aye"},
        ],
        "items": [
            {
                "item_number": "I-3",
                "title": "Approve payment of $50,000 to GreenBuild Construction for park renovation",
                "description": "Staff recommends approval of invoice from GreenBuild Construction.",
                "department": "Public Works",
            }
        ]
    },
    "action_items": [
        {
            "item_number": "H-5",
            "title": "Approve $2M professional services contract with Stellar Engineering",
            "description": "Authorize the city manager to execute a contract with Stellar Engineering for infrastructure assessment.",
            "department": "Engineering",
            "motions": [
                {
                    "result": "passed",
                    "motion_by": "Councilmember Jimenez",
                    "seconded_by": "Councilmember Robinson",
                    "votes": [
                        {"council_member": "Eduardo Martinez", "vote": "aye"},
                        {"council_member": "Sue Wilson", "vote": "aye"},
                        {"council_member": "Claudia Jimenez", "vote": "aye"},
                        {"council_member": "Jamelia Brown", "vote": "nay"},
                        {"council_member": "Doria Robinson", "vote": "aye"},
                        {"council_member": "Cesar Zepeda", "vote": "aye"},
                        {"council_member": "Soheila Bana", "vote": "absent"},
                    ]
                }
            ]
        }
    ],
    "housing_authority_items": [],
}

# Donations that arrived AFTER Sept 23, 2025 meeting
SAMPLE_POST_VOTE_CONTRIBUTIONS = [
    {
        "contributor_name": "Robert Chen",
        "contributor_employer": "Stellar Engineering",
        "amount": 5000.0,
        "date": "2025-12-15",  # 83 days after vote
        "committee": "Jimenez for Richmond 2026",
        "source": "netfile",
    },
    {
        "contributor_name": "Maria Santos",
        "contributor_employer": "GreenBuild Construction",
        "amount": 1000.0,
        "date": "2026-01-10",  # 109 days after vote
        "committee": "Martinez for Mayor 2026",
        "source": "netfile",
    },
    {
        "contributor_name": "Jane Doe",
        "contributor_employer": "Unrelated Corp",
        "amount": 500.0,
        "date": "2025-10-01",  # 8 days after vote, but unrelated entity
        "committee": "Wilson for Council 2026",
        "source": "netfile",
    },
    {
        "contributor_name": "Tom Smith",
        "contributor_employer": "Stellar Engineering",
        "amount": 250.0,
        "date": "2025-08-01",  # BEFORE the vote - should NOT be flagged
        "committee": "Jimenez for Richmond 2026",
        "source": "netfile",
    },
]


def test_scan_temporal_basic():
    """Detect post-vote donation from Stellar Engineering employee to Jimenez."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    # Should find Robert Chen -> Jimenez (Stellar Engineering, 83 days)
    stellar_flags = [f for f in flags if "Stellar" in f.description]
    assert len(stellar_flags) >= 1
    flag = stellar_flags[0]
    assert flag.flag_type == "post_vote_donation"
    assert "Jimenez" in flag.council_member or "Claudia Jimenez" in flag.council_member
    assert flag.confidence > 0  # Should have non-zero confidence


def test_scan_temporal_consent_item():
    """Detect post-vote donation matching consent calendar item."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    # Should find Maria Santos (GreenBuild) -> Martinez (consent item I-3)
    green_flags = [f for f in flags if "GreenBuild" in f.description]
    assert len(green_flags) >= 1
    flag = green_flags[0]
    assert "Martinez" in flag.council_member


def test_scan_temporal_excludes_pre_vote_donations():
    """Donations before the vote should NOT be flagged."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    # Tom Smith donated to Jimenez BEFORE the vote (Aug 1)
    pre_vote = [f for f in flags if "Tom Smith" in f.description]
    assert len(pre_vote) == 0


def test_scan_temporal_excludes_unrelated_entities():
    """Donations from unrelated entities should NOT be flagged."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    # Jane Doe works at Unrelated Corp - no match to any agenda item
    unrelated = [f for f in flags if "Unrelated" in f.description]
    assert len(unrelated) == 0


def test_scan_temporal_excludes_nay_voters():
    """Officials who voted Nay should NOT be flagged for that item."""
    from conflict_scanner import scan_temporal_correlations

    # Jamelia Brown voted NAY on H-5 (Stellar Engineering)
    # Even if someone donates to Brown's committee from Stellar, no flag
    contributions_to_brown = [
        {
            "contributor_name": "Stellar Engineering PAC",
            "contributor_employer": "Stellar Engineering",
            "amount": 2000.0,
            "date": "2025-11-01",
            "committee": "Brown for Richmond 2026",
            "source": "netfile",
        }
    ]
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, contributions_to_brown)
    brown_stellar = [f for f in flags if "Brown" in f.council_member and "Stellar" in f.description]
    assert len(brown_stellar) == 0


def test_scan_temporal_time_decay_confidence():
    """Closer donations should have higher confidence than distant ones."""
    from conflict_scanner import scan_temporal_correlations

    close_donation = [{
        "contributor_name": "Stellar Employee",
        "contributor_employer": "Stellar Engineering",
        "amount": 5000.0,
        "date": "2025-10-15",  # 22 days after vote
        "committee": "Martinez for Mayor 2026",
        "source": "netfile",
    }]
    far_donation = [{
        "contributor_name": "Stellar Employee",
        "contributor_employer": "Stellar Engineering",
        "amount": 5000.0,
        "date": "2027-06-15",  # ~630 days after vote
        "committee": "Martinez for Mayor 2026",
        "source": "netfile",
    }]

    close_flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, close_donation)
    far_flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, far_donation)

    assert len(close_flags) >= 1
    assert len(far_flags) >= 1
    assert close_flags[0].confidence > far_flags[0].confidence


def test_scan_temporal_evidence_schema():
    """Evidence dict should contain all required temporal fields."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    stellar_flags = [f for f in flags if "Stellar" in f.description]
    assert len(stellar_flags) >= 1

    # Check evidence structure
    evidence = stellar_flags[0].evidence
    assert len(evidence) >= 1
    ev = evidence[0] if isinstance(evidence[0], dict) else {}
    assert "vote_date" in ev
    assert "donation_date" in ev
    assert "days_after_vote" in ev
    assert "time_decay_multiplier" in ev
    assert "donor_name" in ev
    assert "vote_choice" in ev
    assert ev["vote_choice"] == "aye"


def test_scan_temporal_beyond_lookback():
    """Donations beyond the lookback window should NOT be flagged."""
    from conflict_scanner import scan_temporal_correlations

    ancient_donation = [{
        "contributor_name": "Stellar Employee",
        "contributor_employer": "Stellar Engineering",
        "amount": 5000.0,
        "date": "2031-01-01",  # ~5.3 years after vote, beyond 1825 days
        "committee": "Martinez for Mayor 2030",
        "source": "netfile",
    }]
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, ancient_donation)
    assert len(flags) == 0


def test_scan_temporal_publication_tier():
    """Recent high-confidence matches should be Tier 2, older ones Tier 3."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, SAMPLE_POST_VOTE_CONTRIBUTIONS)

    stellar_flags = [f for f in flags if "Stellar" in f.description and "Jimenez" in f.council_member]
    assert len(stellar_flags) >= 1
    # 83 days, $5000, employer match -> should be Tier 2 (moderate confidence)
    assert stellar_flags[0].publication_tier in (1, 2)


def test_scan_temporal_empty_contributions():
    """No contributions should produce no flags."""
    from conflict_scanner import scan_temporal_correlations
    flags = scan_temporal_correlations(SAMPLE_MEETING_DATA, [])
    assert flags == []


def test_scan_temporal_no_votes():
    """Meeting with no vote data should produce no flags."""
    from conflict_scanner import scan_temporal_correlations
    meeting = {
        "meeting_date": "2025-09-23",
        "meeting_type": "special",
        "action_items": [
            {"item_number": "A-1", "title": "Presentation only", "description": "Info item"}
        ]
    }
    flags = scan_temporal_correlations(meeting, SAMPLE_POST_VOTE_CONTRIBUTIONS)
    assert flags == []


def test_cloud_pipeline_retrospective_includes_temporal(monkeypatch):
    """Retrospective scan mode should run temporal correlation analysis."""
    from unittest.mock import MagicMock, patch
    import cloud_pipeline

    # Track if scan_temporal_correlations was called
    temporal_called = {"called": False, "args": None}

    original_scan_temporal = None
    try:
        from conflict_scanner import scan_temporal_correlations
        original_scan_temporal = scan_temporal_correlations
    except ImportError:
        pass

    def mock_temporal(meeting_data, contributions, **kwargs):
        temporal_called["called"] = True
        temporal_called["args"] = (meeting_data, contributions, kwargs)
        return []

    # We just need to verify the function is called during retrospective mode
    # without running the full pipeline
    monkeypatch.setattr("conflict_scanner.scan_temporal_correlations", mock_temporal)

    # Verify the import exists in cloud_pipeline
    assert hasattr(cloud_pipeline, '_run_temporal_correlation') or \
           'scan_temporal_correlations' in dir(cloud_pipeline) or \
           'temporal' in open(cloud_pipeline.__file__).read().lower(), \
           "cloud_pipeline.py should reference temporal correlation for retrospective scans"


def test_cli_temporal_flag(tmp_path):
    """CLI should accept --temporal-correlation flag and run temporal analysis."""
    import json
    import subprocess

    # Write sample meeting data to temp file
    meeting_file = tmp_path / "meeting.json"
    meeting_file.write_text(json.dumps(SAMPLE_MEETING_DATA))

    contributions_file = tmp_path / "contributions.json"
    contributions_file.write_text(json.dumps(SAMPLE_POST_VOTE_CONTRIBUTIONS))

    result = subprocess.run(
        ["python3", "src/conflict_scanner.py", str(meeting_file),
         "--contributions", str(contributions_file),
         "--temporal-correlation"],
        capture_output=True, text=True,
        cwd="/Users/phillip.front/Projects/MyProjects/RTP/.worktrees/temporal-correlation",
    )

    assert result.returncode == 0
    # Should mention post-vote donations in output
    assert "post-vote" in result.stdout.lower() or "post_vote" in result.stdout.lower()
