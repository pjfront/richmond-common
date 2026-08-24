"""Shared Richmond-only safety rails for orientation preview selectors."""

from __future__ import annotations


RICHMOND_FIPS = "0660620"
RICHMOND_TIMEZONE = "America/Los_Angeles"

# A regular Richmond council agenda is normally published only days before its
# meeting. Two weeks catches an early packet without generating stale previews.
ORIENTATION_LOOKAHEAD_DAYS = 14

# This is a hard ceiling, including force runs. Normal Richmond cadence should
# produce one candidate; ten leaves room for corrected/duplicate source rows
# while keeping one accidental run small and inexpensive.
ORIENTATION_CANDIDATE_CAP = 10

# Agenda input is bounded independently from the meeting batch. A malformed or
# duplicated packet must not create an unbounded database read or paid prompt.
ORIENTATION_SECTION_ITEM_CAP = 15
# Fetch one sentinel row beyond each section's prompt cap. This proves that a
# section was truncated without counting or loading the rest of a bad packet.
ORIENTATION_SECTION_FETCH_CAP = ORIENTATION_SECTION_ITEM_CAP + 1
ORIENTATION_ITEM_NUMBER_MAX_CHARS = 40
ORIENTATION_TITLE_MAX_CHARS = 240
ORIENTATION_DESCRIPTION_MAX_CHARS = 360
ORIENTATION_CONTEXT_MAX_CHARS = 20_000

RICHMOND_TODAY_SQL = (
    f"(CURRENT_TIMESTAMP AT TIME ZONE '{RICHMOND_TIMEZONE}')::date"
)

# Shared by the generator and the enrichment pending gate so both agree on
# whether a meeting has usable, source-closest agenda text.
ORIENTATION_ELIGIBLE_AGENDA_ITEMS_SQL = """
    EXISTS (
        SELECT 1
        FROM agenda_items ai
        WHERE ai.meeting_id = m.id
          AND ai.agenda_source_retired_at IS NULL
          AND NULLIF(BTRIM(CONCAT_WS(' ', ai.title, ai.description)), '') IS NOT NULL
    )
""".strip()


def require_richmond_fips(city_fips: str) -> None:
    """Fail closed when an orientation path is invoked for another city."""
    if city_fips != RICHMOND_FIPS:
        raise ValueError(
            f"Orientation previews are Richmond-only ({RICHMOND_FIPS}); "
            f"received {city_fips!r}"
        )
