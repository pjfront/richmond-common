"""No-network tests for bounded monthly provider configuration reads."""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import provider_capacity as capacity  # noqa: E402


PROJECT_REF = "abcdefghijklmnopqrst"
ORG_SLUG = "richmond-commons-org"
VERCEL_ORG_ID = "team_abcdefgh"


def _environment() -> dict[str, str]:
    return {
        "VERCEL_TOKEN": "vercel-private-token",
        "VERCEL_ORG_ID": VERCEL_ORG_ID,
        "SUPABASE_ACCESS_TOKEN": "sbp_private-token",
        "SUPABASE_URL": f"https://{PROJECT_REF}.supabase.co",
    }


def _transport_factory(
    *,
    vercel_plan: str = "hobby",
    supabase_plan: str = "pro",
    project_status: str = "ACTIVE_HEALTHY",
    selected_addons: list[dict] | None = None,
    preview_count: int = 0,
):
    requests = []

    def transport(request, timeout, response_cap):
        requests.append((request, timeout, response_cap))
        url = request.full_url
        if url == f"https://api.vercel.com/v2/teams/{VERCEL_ORG_ID}":
            return {
                "id": VERCEL_ORG_ID,
                "billing": {"plan": vercel_plan},
            }
        if url == f"https://api.supabase.com/v1/projects/{PROJECT_REF}":
            return {
                "ref": PROJECT_REF,
                "status": project_status,
                "organization_slug": ORG_SLUG,
            }
        if url == f"https://api.supabase.com/v1/organizations/{ORG_SLUG}":
            return {"plan": supabase_plan}
        if url == (
            f"https://api.supabase.com/v1/organizations/{ORG_SLUG}/projects"
            "?offset=0&limit=20"
        ):
            return {
                "projects": [
                    {"ref": PROJECT_REF, "status": "ACTIVE_HEALTHY"},
                    {"ref": "bcdefghijklmnopqrstu", "status": "ACTIVE_HEALTHY"},
                ],
                "pagination": {"count": 2, "limit": 20, "offset": 0},
            }
        if url == (
            f"https://api.supabase.com/v1/projects/{PROJECT_REF}/billing/addons"
        ):
            return {
                "selected_addons": selected_addons or [],
                "available_addons": [],
            }
        if url == f"https://api.supabase.com/v1/projects/{PROJECT_REF}/branches":
            branches = [{"is_default": True}]
            branches.extend({"is_default": False} for _ in range(preview_count))
            return branches
        raise AssertionError(f"unexpected request path: {url}")

    return transport, requests


def test_success_is_exactly_six_bounded_gets_and_configuration_only():
    transport, requests = _transport_factory()
    state = capacity.collect_provider_capacity(
        _environment(), transport=transport
    )

    assert state["status"] == "pass"
    assert state["coverage"] == "configuration_invariants_only"
    assert state["manual_usage_required"] is True
    assert state["calls_attempted"] == state["call_limit"] == 6
    assert len(requests) == 6
    assert all(request.method == "GET" for request, _, _ in requests)
    assert all(timeout == 12 for _, timeout, _ in requests)
    assert all(cap == 64 * 1024 for _, _, cap in requests)
    assert all("private-token" not in request.full_url for request, _, _ in requests)
    assert all(request.headers["Authorization"].startswith("Bearer ")
               for request, _, _ in requests)
    details = " ".join(check["detail"] for check in state["checks"])
    assert "Hobby" in details and "Pro" in details
    assert "2 active project(s)" in details
    assert "no selected paid add-ons" in details
    assert "no Preview branch" in details
    assert "private-token" not in json.dumps(state)


def test_plan_addon_health_and_branch_drift_fail_without_mutation():
    transport, _ = _transport_factory(
        vercel_plan="pro",
        supabase_plan="free",
        project_status="ACTIVE_UNHEALTHY",
        selected_addons=[{"type": "ipv4", "secret": "private"}],
        preview_count=1,
    )
    state = capacity.collect_provider_capacity(
        _environment(), transport=transport
    )

    assert state["status"] == "fail"
    failed = {check["id"] for check in state["checks"]
              if check["status"] == "fail"}
    assert failed == {
        "vercel_plan",
        "supabase_project_health",
        "supabase_plan",
        "supabase_paid_addons",
        "supabase_preview_branches",
    }
    rendered = json.dumps(state)
    assert "private" not in rendered
    assert "DELETE" not in rendered and "upgrade now" not in rendered


def test_missing_configuration_fails_before_any_provider_call():
    called = False

    def transport(*_args):
        nonlocal called
        called = True
        raise AssertionError("network must not be called")

    state = capacity.collect_provider_capacity({}, transport=transport)

    assert state["status"] == "fail"
    assert state["calls_attempted"] == 0
    assert called is False
    details = " ".join(check["detail"] for check in state["checks"])
    assert "VERCEL_TOKEN" in details
    assert "SUPABASE_ACCESS_TOKEN" in details


def test_provider_error_never_copies_body_url_or_token():
    def denied(request, timeout, response_cap):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "denied private-token",
            {},
            io.BytesIO(b"sbp_private-token reflected provider body"),
        )

    state = capacity.collect_provider_capacity(_environment(), transport=denied)
    rendered = json.dumps(state)

    assert state["status"] == "fail"
    assert state["calls_attempted"] == 4
    assert "HTTP 401" in rendered
    for forbidden in (
        "private-token",
        "reflected provider body",
        PROJECT_REF,
        VERCEL_ORG_ID,
    ):
        assert forbidden not in rendered


def test_default_transport_rejects_oversized_body_without_parsing(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcode(self):
            return 200

        def read(self, size):
            assert size == capacity.RESPONSE_CAP_BYTES + 1
            return b"x" * size

    class Opener:
        def open(self, request, timeout):
            assert timeout == capacity.TIMEOUT_SECONDS
            return Response()

    monkeypatch.setattr(capacity.urllib.request, "build_opener", lambda *_: Opener())
    request = capacity.urllib.request.Request("https://api.vercel.com/test")
    with pytest.raises(capacity.ProviderReadError, match="64 KiB"):
        capacity._default_transport(
            request,
            capacity.TIMEOUT_SECONDS,
            capacity.RESPONSE_CAP_BYTES,
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://abcdefghijklmnopqrst.supabase.co",
        "https://abcdefghijklmnopqrst.supabase.co/path",
        "https://user:pass@abcdefghijklmnopqrst.supabase.co",
        "https://short.supabase.co",
        "https://abcdefghijklmnopqrst.example.com",
    ],
)
def test_supabase_project_url_must_be_exact(url):
    with pytest.raises(capacity.ProviderReadError):
        capacity._supabase_ref(url)


def test_supabase_project_ref_accepts_documented_lowercase_letters_and_digits():
    assert capacity._supabase_ref(
        "https://abc123def456ghi789jk.supabase.co"
    ) == "abc123def456ghi789jk"


def test_provider_redirects_are_never_followed():
    handler = capacity._NoProviderRedirects()
    assert handler.redirect_request(None, None, 302, "found", {}, "https://evil") is None


def test_workflow_wires_existing_read_only_credentials_and_no_internal_api():
    root = Path(__file__).parent.parent
    workflow = (root / ".github/workflows/alerting.yml").read_text(encoding="utf-8")
    source = (root / "src/provider_capacity.py").read_text(encoding="utf-8")

    for expected in (
        "SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}",
        "SUPABASE_URL: ${{ secrets.SUPABASE_URL }}",
        "VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}",
        "VERCEL_ORG_ID: ${{ vars.VERCEL_ORG_ID }}",
    ):
        assert expected in workflow
    assert "repository_dispatch:" in workflow
    assert "types: [alerting-run]" in workflow
    assert "  workflow_dispatch:" not in workflow
    assert "github.event.action == 'alerting-run'" in workflow
    assert workflow.index("Validate trusted trigger payload before credentials") < (
        workflow.index("SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}")
    )
    assert "ALERT_MODE: ${{ steps.trigger.outputs.mode }}" in workflow
    assert "api.vercel.com" in source and "api.supabase.com" in source
    assert "vercel.com/api/" not in source
    assert "supabase.com/dashboard/api" not in source
    assert "requests." not in source


def test_playbook_explains_manual_gap_and_gives_novice_action():
    root = Path(__file__).parent.parent
    playbook = (root / "docs/operator-alert-playbook.md").read_text(
        encoding="utf-8"
    )
    section = playbook.split("## Monthly provider usage check", 1)[1].split(
        "## Provider messages", 1
    )[0]
    normalized = " ".join(section.split())

    assert "LLM API COST" in section
    assert "PROVIDER USAGE AND LIMITS" in section
    assert "`ACTION: Complete these five steps by the 7th" in section
    assert "https://vercel.com/dashboard" in section
    assert "https://supabase.com/dashboard/org/_/usage" in section
    assert "Dashboard-internal endpoints are deliberately excluded" in normalized
    assert "remove emails, tokens" in section
    assert "`ACTION: Open PowerShell" in section
    assert (
        "'{\"event_type\":\"alerting-run\","
        "\"client_payload\":{\"mode\":\"monthly\"}}' | gh api "
        "--method POST repos/pjfront/richmond-common/dispatches "
        "--input - --silent"
    ) in section
    assert "--raw-field" not in section
    assert "gh auth status" in section
    assert "active account is pjfront" in section
    assert "skipped job or no new run is a failure" in section
    assert "--hostname" not in section
    assert "--ref" not in section
