# tests/test_commission_roster_scraper.py
"""Tests for city website commission roster scraping."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from commission_roster_scraper import (
    parse_roster_page,
    normalize_member_name,
    build_member_record,
    _extract_name_and_role,
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


# ── Realistic CivicPlus HTML (empty <thead>, styled <td> headers) ──
# Matches the actual structure observed on ci.richmond.ca.us
CIVICPLUS_ROSTER_HTML = """
<html><body>
<div class="fr-view">
<table cellpadding="0" style="width: 69%;">
<thead></thead>
<tbody>
  <tr>
    <td style="background-color: rgb(100, 151, 196);"><p align="center"><strong><span style="color: rgb(255, 255, 255);"> Name</span></strong></p></td>
    <td style="background-color: rgb(100, 151, 196);"><p align="center"><strong><span style="color: rgb(255, 255, 255);">Appointed</span></strong></p></td>
    <td style="background-color: rgb(100, 151, 196);"><p align="center"><strong><span style="color: rgb(255, 255, 255);">Term Expiration</span></strong></p></td>
  </tr>
  <tr><td>Bruce Brubaker</td><td>04/22/2025</td><td>06/30/2026</td></tr>
  <tr><td>Alexander Golovets</td><td>02/20/2024</td><td>06/30/2026</td></tr>
</tbody>
</table>
</div></body></html>
"""

# Personnel Board HTML — has section headers and VACANT-with-qualifier rows
PERSONNEL_BOARD_HTML = """
<html><body>
<table>
<thead></thead>
<tbody>
  <tr>
    <td style="background-color: rgb(100, 151, 196);"><strong>Name</strong></td>
    <td style="background-color: rgb(100, 151, 196);"><strong>Appointed</strong></td>
    <td style="background-color: rgb(100, 151, 196);"><strong>Term Expiration</strong></td>
  </tr>
  <tr><td>2 SEATS APPOINTED BY ELECTION:</td><td></td><td></td></tr>
  <tr><td>VACANT - Employee Representative</td><td></td><td>12/01/2022</td></tr>
  <tr><td>VACANT - Public Safety Representative</td><td></td><td>12/31/2023</td></tr>
  <tr><td>3 SEATS COUNCIL APPOINTED:</td><td></td><td></td></tr>
  <tr><td>Vernetta Buckner</td><td>02/07/2023</td><td>12/31/2027</td></tr>
  <tr><td>Phillip Front</td><td>01/21/2025</td><td>12/31/2028</td></tr>
</tbody>
</table>
</body></html>
"""


class TestCivicPlusEmptyThead:
    """Real-world pattern: empty <thead>, header row in <tbody> as styled <td>."""

    def test_finds_members_with_empty_thead(self):
        members = parse_roster_page(CIVICPLUS_ROSTER_HTML)
        assert len(members) == 2

    def test_header_row_not_included_as_member(self):
        members = parse_roster_page(CIVICPLUS_ROSTER_HTML)
        names = [m["name"] for m in members]
        assert "Name" not in names

    def test_extracts_correct_names(self):
        members = parse_roster_page(CIVICPLUS_ROSTER_HTML)
        names = [m["name"] for m in members]
        assert "Bruce Brubaker" in names
        assert "Alexander Golovets" in names

    def test_extracts_term_dates(self):
        members = parse_roster_page(CIVICPLUS_ROSTER_HTML)
        bruce = [m for m in members if m["name"] == "Bruce Brubaker"][0]
        assert bruce["term_end"] == "2026-06-30"


class TestSectionHeaderFiltering:
    """Personnel Board has section headers and VACANT-with-qualifier rows."""

    def test_filters_section_headers(self):
        members = parse_roster_page(PERSONNEL_BOARD_HTML)
        names = [m["name"] for m in members]
        assert not any("SEATS" in n.upper() for n in names)

    def test_filters_vacant_with_qualifier(self):
        members = parse_roster_page(PERSONNEL_BOARD_HTML)
        names = [m["name"] for m in members]
        assert not any("vacant" in n.lower() for n in names)

    def test_finds_real_members_only(self):
        members = parse_roster_page(PERSONNEL_BOARD_HTML)
        assert len(members) == 2
        names = [m["name"] for m in members]
        assert "Vernetta Buckner" in names
        assert "Phillip Front" in names


class TestNormalizeVacantPatterns:
    """Expanded vacancy detection patterns discovered from live pages."""

    def test_vacant_with_dash_qualifier(self):
        assert normalize_member_name("VACANT - Employee Representative") == ""

    def test_vacant_with_role(self):
        assert normalize_member_name("VACANT - Public Safety Representative") == ""

    def test_section_header_seats(self):
        assert normalize_member_name("2 SEATS APPOINTED BY ELECTION:") == ""

    def test_section_header_council(self):
        assert normalize_member_name("3 SEATS COUNCIL APPOINTED:") == ""


class TestAnnotationFiltering:
    """Annotation rows from live roster pages that aren't real members."""

    def test_asterisk_annotation(self):
        assert normalize_member_name("* filling an unexpired term") == ""

    def test_asterisk_no_space(self):
        assert normalize_member_name("*Filling an unexpired term") == ""

    def test_asterisk_serving(self):
        assert normalize_member_name("*serving remainder of term") == ""

    def test_no_fund_members(self):
        assert normalize_member_name("No Fund Members") == ""

    def test_no_current_members(self):
        assert normalize_member_name("No current members") == ""


class TestRoleSuffixExtraction:
    """Role extraction from various Richmond roster name formats."""

    def test_parenthetical_chair(self):
        name, role = _extract_name_and_role("Jane Smith (Chair)")
        assert name == "Jane Smith"
        assert role == "chair"

    def test_parenthetical_vice_chair(self):
        name, role = _extract_name_and_role("Bob Johnson (Vice Chair)")
        assert name == "Bob Johnson"
        assert role == "vice_chair"

    def test_dash_chair(self):
        name, role = _extract_name_and_role("Marisol Cantu - Chair")
        assert name == "Marisol Cantu"
        assert role == "chair"

    def test_dash_vice_chair(self):
        name, role = _extract_name_and_role("Myrtle Braxton - Vice Chair")
        assert name == "Myrtle Braxton"
        assert role == "vice_chair"

    def test_comma_chair(self):
        name, role = _extract_name_and_role("Carol Hegstrom, Chair")
        assert name == "Carol Hegstrom"
        assert role == "chair"

    def test_comma_vice_chair(self):
        name, role = _extract_name_and_role("Jaycine Scott, Vice Chair")
        assert name == "Jaycine Scott"
        assert role == "vice_chair"

    def test_chairperson_suffix(self):
        name, role = _extract_name_and_role("Evelyn Santos - Chairperson")
        assert name == "Evelyn Santos"
        assert role == "chair"

    def test_dash_treasurer(self):
        name, role = _extract_name_and_role("Rose Brooks - Treasurer")
        assert name == "Rose Brooks"
        assert role == "member"

    def test_plain_name_no_role(self):
        name, role = _extract_name_and_role("Alice Williams")
        assert name == "Alice Williams"
        assert role == "member"


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


class TestCityConfigIntegration:
    def test_commissions_escribemeetings_config_exists(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        sources = cfg["data_sources"]
        assert "commissions_escribemeetings" in sources

    def test_mapping_has_planning_commission(self):
        from city_config import get_city_config
        cfg = get_city_config("0660620")
        mapping = cfg["data_sources"]["commissions_escribemeetings"]
        assert "Planning Commission" in mapping
