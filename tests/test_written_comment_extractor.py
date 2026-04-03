"""Tests for written_comment_extractor.py — S21 Phase E."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from written_comment_extractor import (
    find_comment_boundary,
    split_emails,
    parse_email_block,
    parse_email_comments,
    extract_item_reference,
    parse_ecomments_from_json,
    _strip_boilerplate,
)
from text_utils import normalize_item_number, resolve_item_id


# ── Sample Data ─────────────────────────────────────────────────────────────

FORMAT_A_EMAIL = """From:
Joan Peters
To:
City Clerk Dept User
Subject:
Public Comments - Agenda Item O-1
Date:
Tuesday, January 27, 2026 1:08:01 PM
This email originated from outside of the City's email system. Do not open links or attachments from untrusted
sources.
Due to a mistake in my typing, this email was not delivered before 1:00pm.
Would you please accept it anyway?
Thank you,
Joan Peters"""

FORMAT_B_EMAIL = """FROM:  KAT T
DATE: FEBRUARY 2, 2026 – 12:41 P.M.
SUBJECT: PUBLIC COMMENT

COMMENTS:
I request that Richmond City Council create an avenue for obtaining responses from
representatives who are perhaps not as able to timely communicate with constituents."""

MINUTES_WITH_APPENDIX = """ROLL CALL
Members present: Martinez, Brown, Zepeda
...
ADJOURNMENT
The meeting was adjourned at 10:15 PM.
________________________

From:
Test Person
To:
City Clerk Dept User
Subject:
Agenda Item P2 - Tobacco
Date:
Monday, February 2, 2026 8:49:22 PM
This is a comment about tobacco regulations."""

TWO_EMAILS = """From:
Alice Smith
To:
City Clerk Dept User
Subject:
open forum public comment
Date:
Monday, January 20, 2026 6:33:10 PM
This email originated from outside of the City's email system. Do not open links or attachments from untrusted
sources.
I have concerns about the budget.

From:
Bob Jones
To:
City Clerk Dept User
Subject:
Agenda Item #P2 Tobacco Retailer License Amendments
Date:
Monday, January 20, 2026 7:15:00 PM
I strongly support the tobacco regulations."""


# ── Tests: find_comment_boundary ────────────────────────────────────────────


class TestFindCommentBoundary:
    def test_standalone_compilation(self):
        text = "From:\nAlice\nTo:\nClerk\nSubject:\nComment\nDate:\nJan 1\nBody text"
        assert find_comment_boundary(text) == text

    def test_minutes_with_appendix(self):
        result = find_comment_boundary(MINUTES_WITH_APPENDIX)
        assert "ROLL CALL" not in result
        assert "ADJOURNMENT" not in result
        assert "Test Person" in result

    def test_no_emails_after_adjournment(self):
        text = "ROLL CALL\n...\nADJOURNMENT\nThe meeting was adjourned.\n"
        result = find_comment_boundary(text)
        assert "ROLL CALL" not in result
        assert "adjourned" in result

    def test_multiple_adjournments_uses_last(self):
        text = "ADJOURNMENT\nfirst\nADJOURNMENT\nFrom:\nAlice\nTo:\nClerk"
        result = find_comment_boundary(text)
        assert "first" not in result
        assert "Alice" in result


# ── Tests: split_emails ─────────────────────────────────────────────────────


class TestSplitEmails:
    def test_single_format_a(self):
        blocks = split_emails(FORMAT_A_EMAIL)
        assert len(blocks) == 1

    def test_single_format_b(self):
        blocks = split_emails(FORMAT_B_EMAIL)
        assert len(blocks) == 1

    def test_two_emails(self):
        blocks = split_emails(TWO_EMAILS)
        assert len(blocks) == 2
        assert "Alice" in blocks[0]
        assert "Bob" in blocks[1]

    def test_mixed_formats(self):
        mixed = FORMAT_B_EMAIL + "\n\n" + FORMAT_A_EMAIL
        blocks = split_emails(mixed)
        assert len(blocks) == 2

    def test_no_emails(self):
        assert split_emails("Just some random text with no headers") == []


# ── Tests: parse_email_block ────────────────────────────────────────────────


class TestParseEmailBlock:
    def test_format_a(self):
        result = parse_email_block(FORMAT_A_EMAIL)
        assert result is not None
        assert result["speaker_name"] == "Joan Peters"
        assert result["subject"] == "Public Comments - Agenda Item O-1"
        assert result["item_ref"] == "O-1"
        assert "mistake" in result["body"]

    def test_format_b(self):
        result = parse_email_block(FORMAT_B_EMAIL)
        assert result is not None
        assert result["speaker_name"] == "KAT T"
        assert result["subject"] == "PUBLIC COMMENT"
        assert result["item_ref"] is None  # open forum
        assert "Richmond City Council" in result["body"]

    def test_boilerplate_stripped(self):
        result = parse_email_block(FORMAT_A_EMAIL)
        assert result is not None
        assert "originated from outside" not in result["body"]

    def test_empty_block(self):
        assert parse_email_block("") is None

    def test_no_name(self):
        assert parse_email_block("Subject:\nSomething\n\nBody text") is None


# ── Tests: extract_item_reference ───────────────────────────────────────────


class TestExtractItemReference:
    def test_agenda_item_with_hash(self):
        assert extract_item_reference("Public Comments Agenda Item #P2 Tobacco") == "P2"

    def test_agenda_item_dash(self):
        assert extract_item_reference("Public Comments - Agenda Item O-1 -- Contract") == "O-1"

    def test_consent_calendar(self):
        ref = extract_item_reference("Remove consent calendar item O.7.a for review")
        assert ref is not None
        assert "7" in ref

    def test_open_forum(self):
        assert extract_item_reference("public comment open forum council meeting") is None

    def test_general_public_comment(self):
        assert extract_item_reference("Public Comments for January meeting") is None

    def test_bare_item_number(self):
        assert extract_item_reference("Comments on V.1 staff report") == "V.1"

    def test_public_comment_with_item_number(self):
        """'Public Comment O.2' should extract O.2, not treat as open forum."""
        assert extract_item_reference("Public Comment O.2") == "O.2"

    def test_empty(self):
        assert extract_item_reference("") is None

    def test_none(self):
        assert extract_item_reference(None) is None


# ── Tests: parse_email_comments (end-to-end) ────────────────────────────────


class TestParseEmailComments:
    def test_standalone_compilation(self):
        results = parse_email_comments(TWO_EMAILS)
        assert len(results) == 2
        assert results[0]["speaker_name"] == "Alice Smith"
        assert results[1]["speaker_name"] == "Bob Jones"

    def test_minutes_with_appendix(self):
        results = parse_email_comments(MINUTES_WITH_APPENDIX)
        assert len(results) == 1
        assert results[0]["speaker_name"] == "Test Person"
        assert results[0]["item_ref"] == "P2"

    def test_no_comments(self):
        assert parse_email_comments("ROLL CALL\n...\nADJOURNMENT\nDone.") == []

    def test_format_b_mixed(self):
        text = FORMAT_B_EMAIL + "\n\n" + FORMAT_A_EMAIL
        results = parse_email_comments(text)
        assert len(results) == 2


# ── Tests: boilerplate stripping ────────────────────────────────────────────


class TestStripBoilerplate:
    def test_removes_warning(self):
        text = "Hello\nThis email originated from outside of the City's email system. Do not open links or attachments from untrusted\nsources.\nActual content"
        result = _strip_boilerplate(text)
        assert "originated" not in result
        assert "Actual content" in result

    def test_removes_doubled_warning(self):
        warning = "This email originated from outside of the City's email system. Do not open links or attachments from untrusted\nsources."
        text = f"Hello\n{warning}\n{warning}\nContent"
        result = _strip_boilerplate(text)
        assert "originated" not in result

    def test_removes_attachments(self):
        text = "Body text\nAttachments:\nfile1.pdf\nfile2.docx"
        result = _strip_boilerplate(text)
        assert "Attachments" not in result
        assert "Body text" in result


# ── Tests: eComment parsing ─────────────────────────────────────────────────


class TestParseEcommentsFromJson:
    def test_basic(self):
        data = {
            "items": [
                {
                    "item_number": "P.2",
                    "title": "Tobacco",
                    "ecomments": [
                        {"name": "Ben", "text": "I support this ordinance", "position": "For"},
                        {"name": "Sarah", "text": "Please reconsider", "position": "Against"},
                    ],
                }
            ]
        }
        results = parse_ecomments_from_json(data)
        assert len(results) == 2
        assert results[0]["speaker_name"] == "Ben"
        assert results[0]["item_number"] == "P.2"
        assert results[1]["speaker_name"] == "Sarah"

    def test_no_ecomments(self):
        data = {"items": [{"item_number": "A", "title": "Roll Call"}]}
        assert parse_ecomments_from_json(data) == []

    def test_empty_items(self):
        assert parse_ecomments_from_json({"items": []}) == []


# ── Tests: shared item resolution ───────────────────────────────────────────


class TestNormalizeItemNumber:
    def test_dotted(self):
        assert normalize_item_number("V.1") == "v.1"

    def test_no_dot(self):
        assert normalize_item_number("P5") == "p.5"

    def test_with_dash(self):
        assert normalize_item_number("O-1") == "o.1"

    def test_trailing_letter(self):
        assert normalize_item_number("V6a") == "v.6.a"


class TestResolveItemId:
    def test_exact_match(self):
        m = {"P.2": "uuid-p2", "V.1": "uuid-v1"}
        assert resolve_item_id("P.2", m) == "uuid-p2"

    def test_normalized_match(self):
        m = {"P.2": "uuid-p2"}
        assert resolve_item_id("P2", m) == "uuid-p2"

    def test_dash_match(self):
        m = {"O.1": "uuid-o1"}
        assert resolve_item_id("O-1", m) == "uuid-o1"

    def test_no_match(self):
        assert resolve_item_id("Z.99", {"A.1": "uuid"}) is None
