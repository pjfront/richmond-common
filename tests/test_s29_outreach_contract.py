"""Structural guards for the bounded S29 release-and-demand outreach packet."""

from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "s29-outreach.json"
PACKET_PATH = ROOT / "docs" / "plans" / "2026-08-26-s29-bounded-outreach-packet.md"
RUNBOOK_PATH = (
    ROOT / "docs" / "plans" / "2026-08-15-s29-analytics-baseline-release-runbook.md"
)
EXPECTED_COPY = """Richmond Commons is ready for Richmond residents to try. It is a free, independent guide to city government in Richmond, California. See the November 3 mayor's race, follow City Council meetings and votes, find your council district, and sign up for meeting briefings. Plain-language explanations link to public records, and AI-generated explanations are clearly labeled.

Take a look:
https://richmondcommons.org/elections/2026-general

If something looks unclear or wrong, please use the Submit Feedback button."""


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_outreach_contract_is_exactly_bounded() -> None:
    contract = _contract()

    assert set(contract) == {
        "schema_version",
        "packet_id",
        "status",
        "copy",
        "landing_url",
        "latest_treatment_day_1_utc",
        "max_channels",
        "posts_per_channel",
        "paid_promotion",
        "treatment_day_1_post_window_seconds",
        "tracking",
        "private_log",
    }
    assert contract["schema_version"] == 1
    assert contract["packet_id"] == "s29-outreach-v1"
    assert contract["status"] == "approved_pending_channels_and_t0"
    assert contract["latest_treatment_day_1_utc"] == "2026-10-20T00:00:00Z"
    assert contract["max_channels"] == 3
    assert contract["posts_per_channel"] == 1
    assert contract["paid_promotion"] is False
    assert contract["treatment_day_1_post_window_seconds"] == {
        "start": 5 * 60,
        "end": 35 * 60,
    }
    assert contract["tracking"] == {
        "utm_parameters": False,
        "query_parameters": False,
        "fragments": False,
        "url_shorteners": False,
        "custom_events": False,
        "person_level_identifiers": False,
    }


def test_outreach_copy_uses_one_canonical_untracked_link() -> None:
    contract = _contract()
    landing_url = contract["landing_url"]
    parsed = urlsplit(landing_url)

    assert parsed.scheme == "https"
    assert parsed.netloc == "richmondcommons.org"
    assert parsed.path == "/elections/2026-general"
    assert parsed.query == ""
    assert parsed.fragment == ""
    assert contract["copy"] == EXPECTED_COPY
    assert contract["copy"].count(landing_url) == 1
    assert len(re.findall(r"https?://\S+", contract["copy"])) == 1
    assert "Richmond, California" in contract["copy"]
    assert "sign up for meeting briefings" in contract["copy"]
    assert "AI-generated explanations are clearly labeled" in contract["copy"]


def test_private_log_stays_gitignored_and_person_level_free() -> None:
    contract = _contract()
    private_log = contract["private_log"]
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert private_log["path"].startswith("src/data/analytics_checkpoints/")
    assert "src/data/analytics_checkpoints/" in gitignore
    assert private_log["channel_fields"] == [
        "platform",
        "channel_name",
        "source_hostname",
        "scheduled_at_utc",
        "actual_at_utc",
        "status",
    ]
    assert private_log["allowed_statuses"] == [
        "posted",
        "moderation_pending",
        "removed",
        "skipped",
    ]
    assert private_log["prohibited_person_level_fields"] is True


def test_public_packet_and_authoritative_runbook_reference_the_contract() -> None:
    packet = PACKET_PATH.read_text(encoding="utf-8")
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    packet_flat = " ".join(packet.split())
    runbook_flat = " ".join(runbook.split())
    fixed_copy = re.search(
        r"## Fixed public message.*?```text\n(?P<copy>.*?)\n```",
        packet,
        flags=re.DOTALL,
    )

    assert "docs/s29-outreach.json" in packet
    assert "docs/plans/2026-08-26-s29-bounded-outreach-packet.md" in runbook
    assert fixed_copy is not None
    assert fixed_copy.group("copy") == EXPECTED_COPY
    assert "combined release-and-demand" in packet
    assert "not a causal UX experiment" in runbook
    assert "`00:05:00Z` through `00:35:00Z`" in packet_flat
    assert "`00:05Z` through `00:35Z`" in runbook_flat
    assert "`2026-10-20T00:00:00Z`" in packet_flat
    assert "`2026-10-20T00:00:00Z`" in runbook_flat
