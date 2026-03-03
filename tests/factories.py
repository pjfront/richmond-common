"""Test factories for building realistic mock data.

Import directly: `from factories import make_escribemeetings_raw`
These match real API response formats so tests validate against actual data shapes.
"""


def make_escribemeetings_raw(
    date: str = "2026/03/03",
    time: str = "18:30:00",
    name: str = "City Council",
    guid: str = "test-guid-0001",
    cancelled: bool = False,
) -> dict:
    """Build a realistic raw eSCRIBE meeting dict.

    Matches the format returned by the eSCRIBE calendar API
    (POST /MeetingsCalendarView.aspx/GetCalendarMeetings).

    Args:
        date: Date in eSCRIBE format "YYYY/MM/DD"
        time: Time in "HH:MM:SS" format
        name: Meeting type name
        guid: Meeting GUID
        cancelled: Whether the meeting is cancelled
    """
    return {
        "ID": guid,
        "MeetingName": name,
        "StartDate": f"{date} {time}",
        "EndDate": f"{date} 20:00:00",
        "FormattedStart": f"{date.replace('/', '-')}T{time}",
        "Description": "",
        "IsCancelled": cancelled,
    }
