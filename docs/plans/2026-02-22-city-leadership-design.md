# City Leadership & Top Employees — Design

**Date:** 2026-02-22
**Status:** Approved
**Scope:** Data pipeline only (ingestion + schema + seed data + CLI). No frontend, scanner integration, or comment generator changes.
**Branch:** Will be assigned during implementation planning
**Parallel with:** Commissions & Board Members feature

## Goal

Pull city employee payroll data from Socrata, normalize it, infer organizational hierarchy, and store in a `city_employees` table. Seed ground truth for department heads. Enable future staff-to-agenda cross-referencing and revolving door detection.

## Approach

**Socrata-first with title keyword hierarchy inference.** No Claude API calls needed — payroll data is structured, and title-based heuristics reliably identify department heads. Ground truth file validates the heuristic output.

## Data Model

### New table: `city_employees`

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | |
| `city_fips` | VARCHAR(7) NOT NULL | Multi-city scaling (non-negotiable) |
| `name` | VARCHAR(300) | Full name from payroll |
| `normalized_name` | VARCHAR(300) | Lowercased, stripped — for matching |
| `job_title` | VARCHAR(300) | Exact title from payroll |
| `department` | VARCHAR(200) | Department name |
| `is_department_head` | BOOLEAN | Inferred from title keywords |
| `hierarchy_level` | SMALLINT | 1=City Manager, 2=Director/Chief, 3=Asst Dir, 4=Supervisor |
| `annual_salary` | NUMERIC | Base salary |
| `total_compensation` | NUMERIC | Salary + benefits (if available in dataset) |
| `fiscal_year` | VARCHAR(4) | Enables year-over-year tracking |
| `is_current` | BOOLEAN | Latest fiscal year = TRUE |
| `source` | VARCHAR(50) | `socrata_payroll` / `manual` |
| `socrata_record_id` | VARCHAR(100) | Dedup key from Socrata |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Unique constraint:** `(city_fips, normalized_name, department, fiscal_year)` — handles multiple fiscal years for same person without duplicates.

**Indexes:** `city_fips`, `(is_current, city_fips)`, `department`, `normalized_name`, `(hierarchy_level, city_fips)`, `(annual_salary DESC)`.

### New view: `v_staff_agenda_context`

Joins `agenda_items` → `meetings` → `city_employees` on department name match. Filters to `is_current = TRUE`. Provides staff context for agenda items (which department head oversees this item's department).

## Pipeline

### New module: `src/payroll_ingester.py`

1. Resolves Socrata config from city_config registry (`get_data_source_config(fips, "socrata")`)
2. Calls `socrata_client.query_dataset("payroll")` for specified fiscal year
3. Normalizes names (same `normalize_name()` logic as conflict scanner)
4. Classifies hierarchy level via title keyword matching:
   - **Level 1:** city manager, city attorney, city clerk
   - **Level 2:** director, chief (fire/police/financial), city engineer
   - **Level 3:** assistant director, deputy director, division manager
   - **Level 4:** supervisor, senior manager, principal planner/analyst
   - **Level 0 (unclassified):** all other employees
5. Marks `is_department_head = TRUE` for levels 1-2
6. Outputs JSON compatible with `city_employees` table schema
7. Optionally loads directly to Supabase via `db.py` helpers

**CLI:**
```bash
python payroll_ingester.py --fiscal-year 2026 --stats           # Summary only
python payroll_ingester.py --fiscal-year 2026 --output FILE     # Save JSON
python payroll_ingester.py --fiscal-year 2026 --load            # Load to DB
python payroll_ingester.py --list-departments                   # Show departments
```

**First step before coding:** Run `python socrata_client.py payroll --list-columns` to confirm exact column names and data types in the Socrata dataset. Schema may vary.

## Ground Truth

Extend `src/ground_truth/officials.json` with a `city_leadership` section:

```json
{
  "city_leadership": [
    {
      "name": "Shasa Curl",
      "title": "City Manager",
      "department": "City Manager's Office",
      "hierarchy_level": 1,
      "notes": "Appointed 2021"
    }
  ]
}
```

Approximately 15-20 entries: city manager, city attorney, city clerk, and department heads (Public Works, Police, Fire, Finance, Planning, Community Development, Library, IT, HR, etc.).

## Migration

`src/migrations/004_city_employees.sql` — idempotent (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`). Creates table, indexes, and view.

## Cost

- Socrata API: $0 (public data, no auth required)
- Claude API: $0 (no LLM calls — structured data + keyword heuristics)
- Storage: Negligible (hundreds of rows per fiscal year)

## What's NOT in this round

- Staff-to-agenda name matching in the conflict scanner
- Frontend pages (employee directory, department profiles)
- Departure detection (year-over-year fiscal year diffs)
- Comment generator integration ("Staff Context" section)
- Revolving door detection (former staff as vendors)

## Multi-City Scaling

Socrata/Tyler are used by thousands of US cities. The payroll ingester accepts city config, so adding a new city requires only adding a Socrata domain + payroll dataset ID to the registry. Title normalization heuristics are generic (Director/Chief/Manager patterns are universal). A future `title_equivalents` mapping may be needed for "City Administrator" = "City Manager" = "Town Manager" equivalence.

## Monetization Alignment

- **Path A (Freemium):** Citizens look up who runs their city and what they earn
- **Path B (Scaling):** Every city has employees; most publish payroll via Socrata/Tyler
- **Path C (Data):** Structured org chart data cross-referenced to agenda items
