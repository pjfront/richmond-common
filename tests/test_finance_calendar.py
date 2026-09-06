from datetime import date

from filing_period_briefing import resolve_period


def test_november_2026_activity_cutoffs_are_separate_from_deadlines():
    first = resolve_period("2026-general-pre1")
    second = resolve_period("2026-general-pre2")
    final = resolve_period("2026-general-post")
    assert (first.period_start, first.period_end, first.filing_deadline) == (date(2026,7,1), date(2026,9,19), date(2026,9,24))
    assert (second.period_start, second.period_end, second.filing_deadline) == (date(2026,9,20), date(2026,10,17), date(2026,10,22))
    assert (final.period_start, final.period_end, final.filing_deadline) == (date(2026,10,18), date(2026,12,31), date(2027,2,1))
    assert first.election_date == second.election_date == final.election_date == date(2026,11,3)


def test_rapid_reporting_includes_election_day():
    period = resolve_period("2026-pre-general-24h")
    assert period.period_start == date(2026,8,5)
    assert period.period_end == date(2026,11,3)
