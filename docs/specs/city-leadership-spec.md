# City Leadership & Top Employees Spec

*Created: 2026-02-20*
*Status: Draft — awaiting review before implementation*

---

## 1. Motivation

The conflict scanner currently cross-references campaign donors against council agenda items. But council members aren't the only people making decisions — **city staff drive the agenda**. The city manager, department heads, and senior staff:

- Write staff reports recommending council action
- Negotiate contracts before council votes on them
- Manage vendor relationships for ongoing services
- Shape policy proposals that council rubber-stamps on consent calendar

When a $2M contract appears on an agenda, the public sees "Recommended by: Public Works Department." They don't see *who* in Public Works recommended it, what that person earns, or how long they've been in the role. This information is already public (via Socrata payroll data) — it's just not *accessible*.

### What this enables

1. **Staff-to-agenda linking:** "This item is being recommended by [Name], [Title], who has been in this role since [date] and earns $[salary]."
2. **Department spending context:** "The Fire Department's $4.2M equipment contract is being recommended by a department with a $52M annual budget and 180 employees."
3. **Revolving door detection (future):** When a former city employee appears as a vendor or consultant on a future agenda, flag it.
4. **Compensation transparency:** Top earners, department-level compensation breakdowns, year-over-year changes.

### Monetization filter

- **Path A (Freemium):** Citizens can look up who runs their city and what they earn — ✓
- **Path B (Horizontal):** Every city has employees and most publish payroll data (many via Socrata/Tyler) — ✓
- **Path C (Data Infrastructure):** Structured org data with cross-references to agenda items — ✓

All three. High priority.

---

## 2. Data Sources

### 2.1 Primary: Socrata Payroll Dataset

- **Dataset:** `crbs-mam9` on `transparentrichmond.org`
- **Already mapped** in `src/socrata_client.py` as `DATASETS["payroll"]`
- **Expected fields:** employee name, job title, department, salary/compensation, fiscal year
- **Credibility:** Tier 1 (official government records)
- **Update frequency:** Likely annual or semi-annual
- **Access:** Public, no auth required

**First step before implementation:** Query the dataset metadata to confirm exact column names and data types:
```bash
cd src && python socrata_client.py payroll --list-columns
```

### 2.2 Secondary: eSCRIBE Staff Reports

Staff reports on eSCRIBE agenda packets include the recommending department and sometimes the staff contact name. The `escribemeetings_scraper.py` already extracts this text. Cross-referencing staff names from payroll against names in staff reports creates the staff-to-agenda link.

### 2.3 Tertiary: City Website

Richmond's city website lists department heads and contact info at `ci.richmond.ca.us/Directory.aspx`. This provides a manual seed/verification source for the org hierarchy. Not automatable at scale but useful for initial Richmond data.

### 2.4 Future: Expenditure Data Cross-Reference

Socrata `expenditures` dataset (`86qj-wgke`) includes vendor name, amount, department, and date. Cross-referencing vendor payments against employee names could surface revolving-door situations (former employee now a consultant). This is Phase 3+ scope.

---

## 3. Data Model

### 3.1 New Table: `city_employees`

```sql
CREATE TABLE city_employees (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),

    -- Identity
    name VARCHAR(300) NOT NULL,
    normalized_name VARCHAR(300) NOT NULL,      -- lowercase, stripped, for matching
    job_title VARCHAR(300) NOT NULL,
    department VARCHAR(200) NOT NULL,

    -- Organizational hierarchy
    is_department_head BOOLEAN NOT NULL DEFAULT FALSE,
    reports_to UUID REFERENCES city_employees(id),  -- NULL for city manager
    hierarchy_level SMALLINT,                        -- 1=city manager, 2=department head, 3=division manager, etc.

    -- Compensation (from Socrata payroll)
    annual_salary NUMERIC(12, 2),
    total_compensation NUMERIC(12, 2),              -- salary + benefits if available
    fiscal_year VARCHAR(4),                          -- which payroll year this data is from

    -- Employment
    hire_date DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    left_date DATE,                                  -- NULL if still employed

    -- Source tracking
    source VARCHAR(50) NOT NULL,                     -- 'socrata_payroll', 'city_website', 'meeting_extraction', 'manual'
    socrata_record_id VARCHAR(100),                  -- for dedup against future payroll pulls
    document_id UUID REFERENCES documents(id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_employee_year UNIQUE (city_fips, normalized_name, department, fiscal_year)
);

CREATE INDEX idx_employees_city ON city_employees(city_fips);
CREATE INDEX idx_employees_current ON city_employees(city_fips) WHERE is_current = TRUE;
CREATE INDEX idx_employees_department ON city_employees(department);
CREATE INDEX idx_employees_normalized ON city_employees(normalized_name);
CREATE INDEX idx_employees_hierarchy ON city_employees(hierarchy_level);
CREATE INDEX idx_employees_salary ON city_employees(annual_salary DESC);
```

### 3.2 Ground Truth Extension: `officials.json`

Extend the existing file with a `city_leadership` section:

```json
{
  "city_fips": "0660620",
  "city_name": "Richmond, California",
  "updated": "2026-02-20",
  "current_council_members": [ ... ],
  "former_council_members": [ ... ],
  "city_leadership": [
    {
      "name": "Shasa Curl",
      "title": "City Manager",
      "department": "City Manager's Office",
      "hierarchy_level": 1,
      "notes": "Appointed 2021"
    },
    {
      "name": "...",
      "title": "Police Chief",
      "department": "Police Department",
      "hierarchy_level": 2,
      "notes": ""
    }
  ]
}
```

This serves as a verification seed — we can check Socrata payroll data against known department heads to validate our extraction logic.

### 3.3 View: Staff-Agenda Cross-Reference

```sql
CREATE VIEW v_staff_agenda_context AS
SELECT
    ai.id AS agenda_item_id,
    ai.item_number,
    ai.title AS item_title,
    ai.department AS item_department,
    ai.financial_amount,
    m.meeting_date,
    m.city_fips,
    ce.name AS staff_name,
    ce.job_title AS staff_title,
    ce.annual_salary,
    ce.hierarchy_level,
    ce.is_department_head
FROM agenda_items ai
JOIN meetings m ON ai.meeting_id = m.id
LEFT JOIN city_employees ce
    ON m.city_fips = ce.city_fips
    AND ce.is_current = TRUE
    AND ce.department ILIKE '%' || ai.department || '%'
    AND ce.is_department_head = TRUE;
```

---

## 4. Ingestion Pipeline

### 4.1 Socrata Payroll Pull

New module: `src/payroll_ingester.py`

```python
def pull_payroll(fiscal_year: str = "2026") -> list[dict]:
    """
    Pull payroll data from Socrata and normalize into city_employees format.

    Steps:
    1. Query Socrata payroll dataset for the given fiscal year
    2. Normalize names (lowercase, strip whitespace)
    3. Identify department heads by title keywords (Director, Chief, Manager, Superintendent)
    4. Infer hierarchy_level from title patterns
    5. Return list of dicts ready for city_employees table
    """

def identify_department_heads(employees: list[dict]) -> list[dict]:
    """
    Heuristic identification of department heads from payroll data.

    Title keywords that indicate leadership:
    - Level 1: 'City Manager', 'City Attorney', 'City Clerk'
    - Level 2: 'Director', 'Chief', 'Fire Chief', 'Police Chief'
    - Level 3: 'Assistant Director', 'Deputy Director', 'Division Manager',
               'Superintendent', 'Captain'
    - Level 4: 'Supervisor', 'Senior Manager', 'Principal'

    Note: This is a heuristic. The ground truth file (officials.json)
    provides manual verification for Richmond department heads.
    """

def detect_departures(current: list[dict], previous: list[dict]) -> list[dict]:
    """
    Compare current vs. previous fiscal year payroll to detect:
    - New hires (in current, not in previous)
    - Departures (in previous, not in current)
    - Title changes (same person, different title)
    - Department changes (same person, different department)

    Returns list of change records for tracking.
    """
```

### 4.2 Staff Name Extraction from Agenda Items

The `agenda_items` table already has `staff_contact` (VARCHAR 500) and `department` columns from the extraction pipeline. Many agenda items include language like:

> "Recommended by: Public Works Department, Contact: [Name], [Title]"

The enrichment step:
1. Parse `staff_contact` field for person names
2. Match against `city_employees` by normalized name + department
3. If matched, link the agenda item to the employee record

This doesn't need a new table — it's a cross-reference query at display time.

### 4.3 Scaling Considerations

- **Multi-city:** Socrata/Tyler is used by thousands of cities. The payroll pull logic is generic — only the dataset ID changes per city.
- **FIPS tagging:** Every `city_employees` record includes `city_fips`. Non-negotiable.
- **Title normalization:** Different cities use different titles for equivalent roles. A future mapping table (`title_equivalents`) could normalize "City Administrator" = "City Manager" = "Town Manager" across cities.

---

## 5. Integration with Existing Pipeline

### 5.1 Conflict Scanner Enhancement

The conflict scanner currently matches donor names against agenda text. New match type:

- **`staff_vendor_match`:** When a city employee's name appears in both the payroll data AND as a vendor/contractor in the expenditures dataset. This is the "revolving door" signal.
- **`staff_recommendation`:** When a department head's department is recommending a contract to a vendor who donated to a council member's campaign. Not a conflict per se, but adds context.

These are lower-confidence signals — informational, not accusatory. They'd appear in the comment generator's "context" section, not the "conflicts" section.

### 5.2 Comment Generator Enhancement

The `comment_generator.py` output could include a "Staff Context" section:

```
STAFF CONTEXT:
- Item C.3 ($2.1M Public Works contract): Recommended by Public Works Department.
  Department head: [Name], [Title], annual salary: $[amount].
  [Name] has held this position since [date].
```

This adds transparency without making accusations. The information is factual and sourced from public payroll data.

### 5.3 Frontend (Phase 2)

When the Next.js frontend launches:
- **Department pages:** List staff, budget, recent agenda items, top vendors
- **Employee search:** Look up any city employee by name, see title, department, compensation
- **Top earners list:** Sortable table of highest-paid employees
- **Org chart visualization:** Interactive hierarchy from city manager down

---

## 6. Implementation Plan

### Step 1: Explore Socrata Payroll Schema
- Query dataset metadata for `crbs-mam9`
- Document actual column names, data types, row counts
- Pull a sample of 50 rows to understand data shape
- Determine available fiscal years

### Step 2: Build Payroll Ingester
- `src/payroll_ingester.py` — pull, normalize, identify department heads
- CLI: `python payroll_ingester.py [--fiscal-year 2026] [--stats] [--output FILE]`
- Output: JSON in `city_employees` format, saved to `src/data/city_employees.json`

### Step 3: Schema Addition
- Add `city_employees` table to `src/schema.sql`
- Add `v_staff_agenda_context` view
- Include `city_fips` on everything (non-negotiable)

### Step 4: Seed Ground Truth
- Manually populate `city_leadership` section in `officials.json`
- Start with city manager + department heads (~15-20 people)
- Validate against Socrata payroll pull

### Step 5: Staff-Agenda Cross-Reference
- Add matching logic to link agenda items' `staff_contact` / `department` fields to `city_employees` records
- Integrate into comment generator as optional "Staff Context" section

### Step 6: Departure Detection (Optional)
- Compare fiscal year payroll snapshots
- Surface notable changes: new department head, departures, title changes

---

## 7. What This Spec Does NOT Cover

- **Performance evaluations or disciplinary records** — not public, not in scope
- **Individual employee schedules or timesheets** — too granular, not relevant
- **Pension/retirement data** — potentially valuable but different data source (CalPERS), future scope
- **Contractor/temp worker data** — not in payroll dataset, would need expenditure cross-reference
- **Political activity of employees** — private citizens' political participation is not our business unless it creates a conflict under Government Code 87100

---

## 8. File Locations

| Artifact | Path |
|----------|------|
| This spec | `docs/specs/city-leadership-spec.md` |
| Payroll ingester | `src/payroll_ingester.py` |
| Schema additions | `src/schema.sql` (append) |
| Ground truth seed | `src/ground_truth/officials.json` (extend) |
| Payroll data cache | `src/data/city_employees.json` |
| Socrata client (existing) | `src/socrata_client.py` |
