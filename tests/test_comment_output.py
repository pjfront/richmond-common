"""Tests for comment output modes: dual-file and multipart email."""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from email.mime.multipart import MIMEMultipart

from conflict_scanner import ConflictFlag, ScanResult
from comment_generator import (
    generate_comment_for_meeting,
    submit_comment_to_clerk,
    generate_comment_from_scan,
    generate_html_comment_from_scan,
)


@pytest.fixture
def sample_meeting_json(tmp_path):
    """Create a minimal meeting JSON file for testing."""
    meeting = {
        "meeting_date": "2026-02-24",
        "meeting_type": "regular",
        "members_present": [],
        "members_absent": [],
        "conflict_of_interest_declared": [],
        "closed_session_items": [],
        "consent_calendar": {
            "items": [
                {
                    "item_number": "O.1",
                    "title": "Approve City Council Minutes",
                    "description": "Regular meeting minutes",
                    "department": "City Clerk",
                    "category": "governance",
                }
            ]
        },
        "action_items": [],
        "housing_authority_items": [],
    }
    path = tmp_path / "meeting.json"
    path.write_text(json.dumps(meeting))
    return path


@pytest.fixture
def sample_contributions(tmp_path):
    """Create a minimal contributions file."""
    contribs = []
    path = tmp_path / "contributions.json"
    path.write_text(json.dumps(contribs))
    return path


# ── Dual File Output Tests ────────────────────────────────────


class TestDualFileOutput:
    """--output should generate both .txt and .html files."""

    def test_txt_output_created(self, sample_meeting_json, sample_contributions, tmp_path):
        output_path = tmp_path / "comment.txt"
        generate_comment_for_meeting(
            meeting_json_path=str(sample_meeting_json),
            contributions_json_path=str(sample_contributions),
            dry_run=True,
            output_path=str(output_path),
        )
        assert output_path.exists()

    def test_html_output_created_alongside_txt(self, sample_meeting_json, sample_contributions, tmp_path):
        output_path = tmp_path / "comment.txt"
        generate_comment_for_meeting(
            meeting_json_path=str(sample_meeting_json),
            contributions_json_path=str(sample_contributions),
            dry_run=True,
            output_path=str(output_path),
        )
        html_path = tmp_path / "comment.html"
        assert html_path.exists()

    def test_html_output_is_valid_html(self, sample_meeting_json, sample_contributions, tmp_path):
        output_path = tmp_path / "comment.txt"
        generate_comment_for_meeting(
            meeting_json_path=str(sample_meeting_json),
            contributions_json_path=str(sample_contributions),
            dry_run=True,
            output_path=str(output_path),
        )
        html_path = tmp_path / "comment.html"
        html_content = html_path.read_text(encoding="utf-8")
        assert "<html" in html_content
        assert "</html>" in html_content

    def test_html_output_matches_meeting_date(self, sample_meeting_json, sample_contributions, tmp_path):
        output_path = tmp_path / "comment.txt"
        generate_comment_for_meeting(
            meeting_json_path=str(sample_meeting_json),
            contributions_json_path=str(sample_contributions),
            dry_run=True,
            output_path=str(output_path),
        )
        html_path = tmp_path / "comment.html"
        html_content = html_path.read_text(encoding="utf-8")
        assert "2026-02-24" in html_content

    def test_html_filename_derived_from_txt(self, sample_meeting_json, sample_contributions, tmp_path):
        """If output is 'report_2026-02-24.txt', HTML should be 'report_2026-02-24.html'."""
        output_path = tmp_path / "report_2026-02-24.txt"
        generate_comment_for_meeting(
            meeting_json_path=str(sample_meeting_json),
            contributions_json_path=str(sample_contributions),
            dry_run=True,
            output_path=str(output_path),
        )
        html_path = tmp_path / "report_2026-02-24.html"
        assert html_path.exists()


# ── Multipart Email Tests ─────────────────────────────────────


class TestMultipartEmail:
    """Email submission should use multipart/alternative with both formats."""

    def test_submit_builds_multipart_message(self):
        """submit_comment_to_clerk should construct a multipart email."""
        plain = "Plain text comment"
        html = "<html><body>HTML comment</body></html>"
        # We can't test actual SMTP, but we can test the message construction
        msg = submit_comment_to_clerk(
            comment_text=plain,
            html_text=html,
            meeting_date="2026-02-24",
            dry_run=True,
            return_message=True,
        )
        assert msg is not None
        assert msg.get_content_type() == "multipart/alternative"

    def test_multipart_has_plain_text_part(self):
        plain = "Plain text comment"
        html = "<html><body>HTML comment</body></html>"
        msg = submit_comment_to_clerk(
            comment_text=plain,
            html_text=html,
            meeting_date="2026-02-24",
            dry_run=True,
            return_message=True,
        )
        payloads = msg.get_payload()
        types = [p.get_content_type() for p in payloads]
        assert "text/plain" in types

    def test_multipart_has_html_part(self):
        plain = "Plain text comment"
        html = "<html><body>HTML comment</body></html>"
        msg = submit_comment_to_clerk(
            comment_text=plain,
            html_text=html,
            meeting_date="2026-02-24",
            dry_run=True,
            return_message=True,
        )
        payloads = msg.get_payload()
        types = [p.get_content_type() for p in payloads]
        assert "text/html" in types

    def test_subject_includes_meeting_date(self):
        msg = submit_comment_to_clerk(
            comment_text="text",
            html_text="<html></html>",
            meeting_date="2026-02-24",
            dry_run=True,
            return_message=True,
        )
        assert "2026-02-24" in msg["Subject"]

    def test_plain_only_when_no_html(self):
        """When html_text is None, should still work (plain text only)."""
        msg = submit_comment_to_clerk(
            comment_text="Plain only",
            meeting_date="2026-02-24",
            dry_run=True,
            return_message=True,
        )
        # Should be a simple text message, not multipart
        assert msg.get_content_type() == "text/plain"
