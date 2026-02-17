# Test Data Fixtures

**These are SYNTHETIC test data files.** They do not represent real campaign
contributions or economic interests. They are designed to exercise the
conflict scanner and comment generator against the sample meeting output
from the Sept 23, 2025 Richmond City Council meeting.

## Files

- `sample_contributions.json` — Synthetic campaign contributions in the
  format expected by `conflict_scanner.scan_meeting_json()`. Includes
  employer matches for vendors that appear in the Sept 23 meeting
  (National Auto Fleet Group, Gallagher Benefit Services, Motorola
  Solutions, Jumpstart Mastery, Caltrans, Building Trades).

- `sample_form700.json` — Synthetic Form 700 economic interest disclosures
  in the format expected by the scanner. Includes real property, income,
  and investment interests for each council member.

## Usage

```bash
# Run conflict scanner with test data
cd src/
python conflict_scanner.py sample_output/2025-09-23_council_meeting.json \
    --contributions test_data/sample_contributions.json \
    --form700 test_data/sample_form700.json

# Generate full public comment with test data
python comment_generator.py sample_output/2025-09-23_council_meeting.json \
    --contributions test_data/sample_contributions.json \
    --form700 test_data/sample_form700.json \
    --output test_comment.txt
```

## Data Format

### Contributions
Each contribution dict has:
- `donor_name` — Name of the contributor
- `donor_employer` — Employer (for entity matching against vendors)
- `council_member` — Which council member's committee received it
- `committee_name` — Name of the receiving committee (Form 460)
- `amount` — Dollar amount
- `date` — Contribution date (YYYY-MM-DD)
- `filing_id` — CAL-ACCESS/City Clerk filing ID
- `source` — Data source ("CAL-ACCESS", "City Clerk", etc.)

### Form 700 Interests
Each interest dict has:
- `council_member` — Council member name
- `interest_type` — "real_property", "income", or "investment"
- `description` — Description of the interest
- `location` — Location/address
- `filing_year` — Year filed
- `source_url` — Link to FPPC filing

## Important Note

When real CAL-ACCESS data is ingested, these test fixtures will be
superseded. They exist solely to enable testing of the scanner and
comment generator before the full data pipeline is operational.
