"""Tests for eSCRIBE scraper text deduplication across nested containers.

Verifies that parent agenda items (e.g., V.1) don't inherit text from
their children (V.1.a, V.1.b) when containers are nested in HTML.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from escribemeetings_scraper import parse_agenda_item


# ── Fixtures ──────────────────────────────────────────────────


NESTED_HTML = """
<div class="AgendaItemContainer">
  <div class="AgendaItemTitleRow">
    <span class="AgendaItemCounter">V.1.</span>
    <span class="AgendaItemTitle"><a href="#">Community Services</a></span>
  </div>
  <div class="AgendaItemDescription RichText">Department overview text.</div>

  <div class="AgendaItemContainer">
    <div class="AgendaItemTitleRow">
      <span class="AgendaItemCounter">V.1.a.</span>
      <span class="AgendaItemTitle"><a href="#">Kaiser Grant</a></span>
    </div>
    <div class="AgendaItemDescription RichText">
      ADOPT a resolution to ACCEPT $4,500 from Kaiser Permanente for Park Prescription Day.
    </div>
  </div>

  <div class="AgendaItemContainer">
    <div class="AgendaItemTitleRow">
      <span class="AgendaItemCounter">V.1.b.</span>
      <span class="AgendaItemTitle"><a href="#">Workforce Grants</a></span>
    </div>
    <div class="AgendaItemDescription RichText">
      ACCEPT $246,601 in workforce development grant funds from Construction
      Trades ($67,000), Chevron ($20,000), Pinole Youth Foundation ($10,000),
      and California EDD ($149,601).
    </div>
  </div>
</div>
"""

FLAT_HTML = """
<div class="AgendaItemContainer">
  <div class="AgendaItemTitleRow">
    <span class="AgendaItemCounter">V.2.</span>
    <span class="AgendaItemTitle"><a href="#">Standalone Item</a></span>
  </div>
  <div class="AgendaItemDescription RichText">
    Approve a contract for $50,000 with Acme Corp for park maintenance.
  </div>
  <div class="RichText">Additional body text about the contract scope.</div>
</div>
"""


# ── Tests ─────────────────────────────────────────────────────


class TestNestedContainerTextDedup:
    """Parent items must NOT inherit text from nested child containers."""

    def test_parent_excludes_child_description(self):
        soup = BeautifulSoup(NESTED_HTML, "html.parser")
        container = soup.select_one("[class*='AgendaItemContainer']")
        item = parse_agenda_item(container)

        assert item is not None
        assert item["item_number"] == "V.1"
        # Parent should only have its own text, not children's
        assert "$4,500" not in item["description"]
        assert "$246,601" not in item["description"]
        assert "Kaiser" not in item["description"]
        assert "workforce" not in item["description"].lower()

    def test_child_keeps_own_description(self):
        soup = BeautifulSoup(NESTED_HTML, "html.parser")
        containers = soup.select("[class*='AgendaItemContainer']")

        # Second container is V.1.a (Kaiser grant)
        child_a = parse_agenda_item(containers[1])
        assert child_a is not None
        assert child_a["item_number"] == "V.1.a"
        assert "$4,500" in child_a["description"]
        assert "Kaiser" in child_a["description"]

        # Third container is V.1.b (Workforce grants)
        child_b = parse_agenda_item(containers[2])
        assert child_b is not None
        assert child_b["item_number"] == "V.1.b"
        assert "$246,601" in child_b["description"]

    def test_parent_has_own_description_only(self):
        soup = BeautifulSoup(NESTED_HTML, "html.parser")
        container = soup.select_one("[class*='AgendaItemContainer']")
        item = parse_agenda_item(container)

        # Parent's own description is "Department overview text."
        assert "Department overview" in item["description"]


class TestFlatContainerUnchanged:
    """Items without nested containers should work as before."""

    def test_flat_item_keeps_all_text(self):
        soup = BeautifulSoup(FLAT_HTML, "html.parser")
        container = soup.select_one("[class*='AgendaItemContainer']")
        item = parse_agenda_item(container)

        assert item is not None
        assert item["item_number"] == "V.2"
        assert "$50,000" in item["description"]
        assert "contract scope" in item["description"]
