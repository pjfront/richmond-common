"""Keep the authorized resident release and its superseded baseline traceable."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PHASE_PATH = ROOT / "docs" / "s29-release-phase.json"
FLAG_PATH = ROOT / "web" / "src" / "lib" / "s29-release-phase.ts"


def _phase() -> dict[str, object]:
    return json.loads(PHASE_PATH.read_text(encoding="utf-8"))


def test_release_record_preserves_the_superseded_baseline_and_reviewed_merges() -> None:
    phase = _phase()["historical_baseline"]
    assert phase["phase"] == "baseline"
    assert phase["public_treatment_enabled"] is False
    assert phase["production_anchor_sha"] == (
        "0ff9fd50443d8d13e15a4d83845b2997cfc1054a"
    )
    assert phase["held_merges"] == [
        {
            "pull_request": 110,
            "merge_sha": "c5dbcc7d61d9de4b08f161282c2541bd62184bec",
            "scope": "rolling_24_month_agenda_item_sitemap",
        },
        {
            "pull_request": 119,
            "merge_sha": "8b5e2f8d83cbc7814bcea4deb91305ce18c02fe6",
            "scope": "public_seo_json_ld_and_expanded_sitemap",
        },
    ]


def test_source_flag_matches_the_authorized_resident_release() -> None:
    phase = _phase()
    assert phase["schema_version"] == 2
    assert phase["phase"] == "resident_release"
    assert phase["public_treatment_enabled"] is True
    assert phase["release_id"] == "2026-09-06-resident-release"
    authorization = phase["authorization"]
    assert authorization == {
        "date": "2026-09-06",
        "plan": "docs/CURRENT-PLAN.md",
        "decision": "operator_approved_resident_plan",
        "supersedes": "s29_baseline_treatment_publication_dependency",
    }
    plan = (ROOT / authorization["plan"]).read_text(encoding="utf-8")
    assert "It supersedes the S29 baseline/treatment publication dependency" in plan
    assert set(phase["scope"]) == {
        "rolling_24_month_agenda_item_sitemap",
        "public_seo_json_ld_and_expanded_sitemap",
        "source_checked_resident_stories",
    }
    source = FLAG_PATH.read_text(encoding="utf-8")
    match = re.search(r"export const S29_PUBLIC_TREATMENT_ENABLED: boolean = (true|false)", source)
    assert match is not None
    assert (match.group(1) == "true") is phase["public_treatment_enabled"]
    assert "not proof of production deployment" in phase["note"]


def test_legacy_discovery_surfaces_keep_the_source_gate() -> None:
    # The October private-search stage replaced the root layout. The remaining
    # legacy pages still retain the authorized resident-release source gate.
    surfaces = (
        "web/src/app/council/[slug]/page.tsx",
        "web/src/app/elections/[slug]/page.tsx",
        "web/src/app/meetings/[id]/page.tsx",
        "web/src/app/sitemap.ts",
    )
    for relative_path in surfaces:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert source.count("S29_PUBLIC_TREATMENT_ENABLED") >= 2, relative_path

    sitemap = (ROOT / "web/src/app/sitemap.ts").read_text(encoding="utf-8")
    assert "? buildTreatmentSitemap(asOf)" in sitemap
    assert ": buildBaselineSitemap()" in sitemap


def test_private_search_layout_does_not_publish_legacy_discovery_markup() -> None:
    source = (ROOT / "web/src/app/layout.tsx").read_text(encoding="utf-8")
    robots = re.search(r"robots:\s*\{([^}]+)\}", source)
    assert robots is not None
    assert re.search(r"\bindex:\s*false\b", robots.group(1))
    assert re.search(r"\bfollow:\s*false\b", robots.group(1))
    assert re.search(r"\bnoarchive:\s*true\b", robots.group(1))
    assert re.search(r"\bnosnippet:\s*true\b", robots.group(1))
    assert "siteStructuredData" not in source
    assert "site-structured-data" not in source
    assert "S29_PUBLIC_TREATMENT_ENABLED" not in source
