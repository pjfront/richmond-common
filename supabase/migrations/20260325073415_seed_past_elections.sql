-- Migration 057: Seed past Richmond elections
-- Needed for the contribution time-period toggle on council profiles.
-- Without past election dates, the toggle has no reference point.

-- November 2024 General Election (most recent)
INSERT INTO elections (city_fips, election_date, election_type, election_name, jurisdiction, source, source_url, source_tier, notes)
VALUES (
    '0660620',
    '2024-11-05',
    'general',
    'Richmond November 2024 General Election',
    'City of Richmond',
    'seed',
    'https://www.sos.ca.gov/elections/prior-elections/statewide-election-results/general-election-november-5-2024',
    1,
    'California statewide general election. Richmond city council seats on ballot.'
)
ON CONFLICT (city_fips, election_date, election_type) DO NOTHING;

-- March 2024 Primary
INSERT INTO elections (city_fips, election_date, election_type, election_name, jurisdiction, source, source_url, source_tier, notes)
VALUES (
    '0660620',
    '2024-03-05',
    'primary',
    'Richmond March 2024 Primary',
    'City of Richmond',
    'seed',
    'https://www.sos.ca.gov/elections/prior-elections/statewide-election-results/primary-election-march-5-2024',
    1,
    'California statewide primary.'
)
ON CONFLICT (city_fips, election_date, election_type) DO NOTHING;

-- November 2022 General Election
INSERT INTO elections (city_fips, election_date, election_type, election_name, jurisdiction, source, source_url, source_tier, notes)
VALUES (
    '0660620',
    '2022-11-08',
    'general',
    'Richmond November 2022 General Election',
    'City of Richmond',
    'seed',
    'https://www.sos.ca.gov/elections/prior-elections/statewide-election-results/general-election-november-8-2022',
    1,
    'Eduardo Martinez elected mayor. Multiple council seats on ballot.'
)
ON CONFLICT (city_fips, election_date, election_type) DO NOTHING;
