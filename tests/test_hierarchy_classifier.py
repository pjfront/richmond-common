# tests/test_hierarchy_classifier.py
"""Tests for title-based hierarchy classification."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from hierarchy_classifier import classify_title, LEVEL_LABELS


class TestClassifyTitle:
    """Hierarchy level 1-4 inference from job titles."""

    def test_city_manager(self):
        level, is_head = classify_title("City Manager")
        assert level == 1
        assert is_head is True

    def test_city_attorney(self):
        level, is_head = classify_title("City Attorney")
        assert level == 1
        assert is_head is True

    def test_city_clerk(self):
        level, is_head = classify_title("City Clerk")
        assert level == 1
        assert is_head is True

    def test_director(self):
        level, is_head = classify_title("Director of Public Works")
        assert level == 2
        assert is_head is True

    def test_fire_chief(self):
        level, is_head = classify_title("Fire Chief")
        assert level == 2
        assert is_head is True

    def test_police_chief(self):
        level, is_head = classify_title("Chief of Police")
        assert level == 2
        assert is_head is True

    def test_city_engineer(self):
        level, is_head = classify_title("City Engineer")
        assert level == 2
        assert is_head is True

    def test_assistant_director(self):
        level, is_head = classify_title("Assistant Director of Finance")
        assert level == 3
        assert is_head is False

    def test_deputy_director(self):
        level, is_head = classify_title("Deputy Director")
        assert level == 3
        assert is_head is False

    def test_division_manager(self):
        level, is_head = classify_title("Division Manager - Planning")
        assert level == 3
        assert is_head is False

    def test_supervisor(self):
        level, is_head = classify_title("Maintenance Supervisor")
        assert level == 4
        assert is_head is False

    def test_senior_manager(self):
        level, is_head = classify_title("Senior Manager of IT Services")
        assert level == 4
        assert is_head is False

    def test_principal_planner(self):
        level, is_head = classify_title("Principal Planner")
        assert level == 4
        assert is_head is False

    def test_regular_employee(self):
        level, is_head = classify_title("Administrative Assistant II")
        assert level == 0
        assert is_head is False

    def test_empty_title(self):
        level, is_head = classify_title("")
        assert level == 0
        assert is_head is False

    def test_none_title(self):
        level, is_head = classify_title(None)
        assert level == 0
        assert is_head is False

    def test_case_insensitive(self):
        level, _ = classify_title("CITY MANAGER")
        assert level == 1

    def test_assistant_not_promoted_to_director(self):
        """'Assistant to the City Manager' should NOT be level 1."""
        level, is_head = classify_title("Assistant to the City Manager")
        assert level == 3
        assert is_head is False

    def test_level_labels(self):
        assert LEVEL_LABELS[0] == "Unclassified"
        assert LEVEL_LABELS[1] == "Executive"
        assert len(LEVEL_LABELS) == 5


class TestEdgeCases:
    """Titles that could trip up naive matching."""

    def test_chief_financial_officer(self):
        level, is_head = classify_title("Chief Financial Officer")
        assert level == 2
        assert is_head is True

    def test_engineering_technician(self):
        """'Engineer' in title but not 'City Engineer'."""
        level, is_head = classify_title("Engineering Technician")
        assert level == 0
        assert is_head is False

    def test_police_sergeant(self):
        """Sergeant has 'police' context but is not Chief."""
        level, is_head = classify_title("Police Sergeant")
        assert level == 0
        assert is_head is False


class TestRealRichmondTitles:
    """Test against actual Socrata payroll titles (ALL CAPS)."""

    def test_city_manager_uppercase(self):
        level, is_head = classify_title("CITY MANAGER")
        assert level == 1
        assert is_head is True

    def test_city_attorney_uppercase(self):
        level, is_head = classify_title("CITY ATTORNEY")
        assert level == 1
        assert is_head is True

    def test_city_clerk_uppercase(self):
        level, is_head = classify_title("CITY CLERK")
        assert level == 1
        assert is_head is True

    def test_director_of_public_works(self):
        level, is_head = classify_title("DIRECTOR OF PUBLIC WORKS")
        assert level == 2
        assert is_head is True

    def test_director_of_finance(self):
        level, is_head = classify_title("DIRECTOR OF FINANCE")
        assert level == 2
        assert is_head is True

    def test_director_of_community_dev(self):
        level, is_head = classify_title("DIRECTOR OF COMMUNITY DEV")
        assert level == 2
        assert is_head is True

    def test_fire_chief_uppercase(self):
        level, is_head = classify_title("FIRE CHIEF")
        assert level == 2
        assert is_head is True

    def test_police_chief_uppercase(self):
        level, is_head = classify_title("POLICE CHIEF")
        assert level == 2
        assert is_head is True

    def test_dep_dir_pw_city_engineer(self):
        """Richmond-specific combo title: DEP DIR PW - CITY ENGINEER."""
        level, is_head = classify_title("DEP DIR PW - CITY ENGINEER")
        assert level == 2
        assert is_head is True

    def test_deputy_city_manager(self):
        level, is_head = classify_title("DEPUTY CITY MANAGER")
        assert level == 3
        assert is_head is False

    def test_deputy_fire_chief(self):
        level, is_head = classify_title("DEPUTY FIRE CHIEF")
        assert level == 3
        assert is_head is False

    def test_deputy_director_of_finance(self):
        level, is_head = classify_title("DEPUTY DIRECTOR OF FINANCE")
        assert level == 3
        assert is_head is False

    def test_assistant_city_attorney(self):
        level, is_head = classify_title("ASSISTANT CITY ATTORNEY")
        assert level == 3
        assert is_head is False

    def test_executive_director_rent_program(self):
        """Executive Director should be level 2 (department head)."""
        level, is_head = classify_title("EXECUTIVE DIRECTOR RENT PRGRM")
        assert level == 2
        assert is_head is True

    def test_port_director(self):
        level, is_head = classify_title("PORT DIRECTOR")
        assert level == 2
        assert is_head is True

    def test_administrative_chief(self):
        """ADMINISTRATIVE CHIEF is a chief-level position."""
        level, is_head = classify_title("ADMINISTRATIVE CHIEF")
        assert level == 2
        assert is_head is True

    def test_battalion_chief_not_dept_head(self):
        """Battalion chiefs are mid-level fire officers, not dept heads."""
        level, is_head = classify_title("BATTALION CHIEF")
        assert level == 4
        assert is_head is False

    def test_chief_electrician_not_dept_head(self):
        """Chief Electrician is a trades position, not leadership."""
        level, is_head = classify_title("CHIEF ELECTRICIAN")
        assert level == 0
        assert is_head is False

    def test_comm_shift_supervisor(self):
        level, is_head = classify_title("COMM SHIFT SUPERVISOR")
        assert level == 4
        assert is_head is False

    def test_parks_supervisor(self):
        level, is_head = classify_title("PARKS SUPERVISOR")
        assert level == 4
        assert is_head is False

    def test_police_officer_not_classified(self):
        level, is_head = classify_title("POLICE OFFICER")
        assert level == 0
        assert is_head is False

    def test_office_clerk_not_classified(self):
        level, is_head = classify_title("OFFICE CLERK-CASHIER G/III")
        assert level == 0
        assert is_head is False

    def test_fire_chief_annuitant(self):
        """Retired annuitant should still classify as chief-level."""
        level, is_head = classify_title("FIRE CHIEF ANNUITANT")
        assert level == 2
        assert is_head is True

    def test_director_of_human_resources(self):
        level, is_head = classify_title("DIRECTOR OF HUMAN RESOURCES")
        assert level == 2
        assert is_head is True

    def test_director_of_information_tech(self):
        level, is_head = classify_title("DIRECTOR OF INFORMATION TECH")
        assert level == 2
        assert is_head is True

    def test_director_of_economic_dev(self):
        level, is_head = classify_title("DIRECTOR OF ECONOMIC DEVELOPME")
        assert level == 2
        assert is_head is True
