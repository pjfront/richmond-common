"""Containment and caching guards for deterministic public detail routes."""

from pathlib import Path


ROOT = Path(__file__).parent.parent


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_public_detail_routes_are_explicit_isr_surfaces():
    for relative_path in (
        "web/src/app/meetings/[id]/page.tsx",
        "web/src/app/meetings/[id]/items/[itemNumber]/page.tsx",
        "web/src/app/council/[slug]/page.tsx",
    ):
        page = _read(relative_path)
        assert "export const dynamic = 'force-static'" in page
        assert "export const revalidate = 86400" in page
        assert "index: false" not in page


def test_metadata_and_page_reads_are_request_deduplicated():
    meetings = _read("web/src/lib/queries/meetings.ts")
    council = _read("web/src/lib/queries/council.ts")

    assert "getMeeting = cache(async function getMeeting" in meetings
    assert "getAgendaItemDetail = cache(async function getAgendaItemDetail" in meetings
    assert "getOfficialBySlug = cache(async function getOfficialBySlug" in council


def test_public_page_render_does_not_query_operator_only_detail_data():
    meeting_page = _read("web/src/app/meetings/[id]/page.tsx")
    item_page = _read("web/src/app/meetings/[id]/items/[itemNumber]/page.tsx")
    council_page = _read("web/src/app/council/[slug]/page.tsx")

    assert "getConflictFlags" not in meeting_page
    assert "MeetingConflictsSection" not in meeting_page
    assert "item.conflict_flags" not in item_page
    assert "import InfluenceMapItemSection" not in item_page
    assert "getEconomicInterests" not in council_page
    assert "getForm700Filings" not in council_page


def test_operator_detail_endpoints_authenticate_before_no_store_reads():
    for route_name in (
        "meeting-context",
        "agenda-item-context",
        "council-context",
    ):
        route = _read(f"web/src/app/api/operator/{route_name}/route.ts")
        assert "withOperatorAuth" in route
        assert "export const GET = withOperatorAuth" in route
        assert "private, no-store" in route
        assert "isUuid" in route


def test_empty_uuid_sentinels_are_not_sent_to_postgres():
    meetings = _read("web/src/lib/queries/meetings.ts")
    assert "['__none__']" not in meetings
    assert "if (!isUuid(meetingId)) return null" in meetings


def test_conflict_flag_agenda_item_index_is_forward_mirrored():
    source = _read("src/migrations/139_index_conflict_flags_current_agenda_item.sql")
    mirror = _read(
        "supabase/migrations/20260815013900_index_conflict_flags_current_agenda_item.sql"
    )

    assert source == mirror
    assert "ON public.conflict_flags (agenda_item_id)" in source
    assert "WHERE is_current = TRUE" in source
    assert "Migration 134 remains untouched and forbidden" in source
