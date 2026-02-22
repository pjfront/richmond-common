# tests/test_commission_roster_scraper.py
"""Tests for city website commission roster scraping."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from commission_roster_scraper import (
    parse_roster_page,
    normalize_member_name,
    build_member_record,
)


# ── Inline HTML fixture ──────────────────────────────────────
# Mimics Richmond's actual commission roster page structure.
# Richmond uses CivicPlus/CivicEngage with simple HTML tables:
#   columns: Name | Appointed | Term Expiration

SAMPLE_ROSTER_HTML = """
<html><body>
<div class="fr-view">
<p><strong>Maximum members: 7</strong></p>
<p>Vacancies: 2 (as of 02/17/2026)</p>
<table>
  <thead>
    <tr>
      <th>NAME</th>
      <th>APPOINTED</th>
      <th>TERM EXPIRATION</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Jane Smith (Chair)</td>
      <td>09/15/2020, 07/26/2022</td>
      <td>06/30/2027</td>
    </tr>
    <tr>
      <td>Bob Johnson (Vice Chair)</td>
      <td>02/20/2024</td>
      <td>06/30/2028</td>
    </tr>
    <tr>
      <td>Alice Williams</td>
      <td>01/26/2021</td>
      <td>06/30/2026</td>
    </tr>
    <tr>
      <td>VACANT</td>
      <td>07/02/2024</td>
      <td>06/30/2026</td>
    </tr>
    <tr>
      <td>VACANT</td>
      <td></td>
      <td></td>
    </tr>
  </tbody>
</table>
</div>
</body></html>
"""


class TestNormalizeMemberName:
    def test_basic_name(self):
        assert normalize_member_name("Jane Smith") == "jane smith"

    def test_strips_extra_whitespace(self):
        assert normalize_member_name("  Jane   Smith  ") == "jane smith"

    def test_vacant_returns_empty(self):
        assert normalize_member_name("VACANT") == ""

    def test_vacancy_returns_empty(self):
        assert normalize_member_name("Vacancy") == ""

    def test_tbd_returns_empty(self):
        assert normalize_member_name("TBD") == ""

    def test_none_returns_empty(self):
        assert normalize_member_name(None) == ""


class TestParseRosterPage:
    def test_parses_members(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        # VACANT rows should be excluded
        assert len(members) == 3

    def test_extracts_name(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        names = [m["name"] for m in members]
        assert "Jane Smith" in names

    def test_extracts_role_from_parenthetical(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        chair = [m for m in members if m["name"] == "Jane Smith"][0]
        assert chair["role"] == "chair"

    def test_vice_chair_role(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        vc = [m for m in members if m["name"] == "Bob Johnson"][0]
        assert vc["role"] == "vice_chair"

    def test_member_role(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        member = [m for m in members if m["name"] == "Alice Williams"][0]
        assert member["role"] == "member"

    def test_extracts_term_end(self):
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        chair = [m for m in members if m["name"] == "Jane Smith"][0]
        assert chair["term_end"] == "2027-06-30"

    def test_extracts_term_end_with_multiple_dates(self):
        """When multiple term dates listed, take the last (latest) one."""
        members = parse_roster_page(SAMPLE_ROSTER_HTML)
        chair = [m for m in members if m["name"] == "Jane Smith"][0]
        # Should get the last date in the TERM EXPIRATION column
        assert chair["term_end"] == "2027-06-30"


class TestBuildMemberRecord:
    def test_includes_city_fips(self):
        raw = {"name": "Jane Smith", "role": "chair", "term_end": "2027-06-30"}
        rec = build_member_record(raw, commission_name="Planning Commission", city_fips="0660620")
        assert rec["city_fips"] == "0660620"
        assert rec["source"] == "city_website"

    def test_normalized_name(self):
        raw = {"name": "Jane Smith", "role": "member", "term_end": None}
        rec = build_member_record(raw, commission_name="Rent Board", city_fips="0660620")
        assert rec["normalized_name"] == "jane smith"

    def test_is_current_true_by_default(self):
        raw = {"name": "Jane Smith", "role": "member", "term_end": None}
        rec = build_member_record(raw, commission_name="Rent Board", city_fips="0660620")
        assert rec["is_current"] is True
