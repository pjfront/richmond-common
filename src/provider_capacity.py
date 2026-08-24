"""Bounded provider configuration checks for the monthly operator summary.

This module intentionally does not claim to collect provider billing usage.
Vercel Hobby resource totals and Supabase organization billing-cycle totals are
available in their dashboards, but not through stable authenticated interfaces
that cover this project.  The checks below use only documented, read-only APIs
to verify the invariants that can be automated truthfully.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping


VERCEL_API_BASE = "https://api.vercel.com"
SUPABASE_API_BASE = "https://api.supabase.com"
EXPECTED_VERCEL_PLAN = "hobby"
EXPECTED_SUPABASE_PLAN = "pro"
EXPECTED_SUPABASE_PROJECT_STATUS = "ACTIVE_HEALTHY"

CALL_LIMIT = 6
TIMEOUT_SECONDS = 12
RESPONSE_CAP_BYTES = 64 * 1024
ORGANIZATION_PROJECT_LIMIT = 20
BRANCH_LIMIT = 20

VERCEL_ORG_ID_RE = re.compile(r"^team_[A-Za-z0-9]{8,}$")
SUPABASE_REF_RE = re.compile(r"^[a-z0-9]{20}$")
SUPABASE_ORG_SLUG_RE = re.compile(r"^[\w-]{1,120}$")

Transport = Callable[[urllib.request.Request, int, int], Any]


class ProviderReadError(RuntimeError):
    """A bounded provider read failed without retaining response content."""


class _NoProviderRedirects(urllib.request.HTTPRedirectHandler):
    """Never forward bearer credentials to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _provider_error_shape(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"network error ({type(exc.reason).__name__})"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ProviderReadError):
        message = str(exc)
        if (
            re.fullmatch(r"HTTP \d{3}", message)
            or re.fullmatch(r"network error \([A-Za-z0-9_]+\)", message)
            or message in {
                "timeout",
                "invalid bounded JSON response",
                "provider returned an unexpected JSON shape",
                "response exceeded the 64 KiB safety cap",
            }
        ):
            return message
        return "provider read error"
    return type(exc).__name__


def _default_transport(
    request: urllib.request.Request,
    timeout: int,
    response_cap: int,
) -> Any:
    try:
        opener = urllib.request.build_opener(_NoProviderRedirects())
        with opener.open(request, timeout=timeout) as response:
            status = int(getattr(response, "status", None) or response.getcode())
            body = response.read(response_cap + 1)
        if status < 200 or status >= 300:
            raise ProviderReadError(f"HTTP {status}")
        if len(body) > response_cap:
            raise ProviderReadError("response exceeded the 64 KiB safety cap")
        payload = json.loads(body.decode("utf-8"))
    except ProviderReadError:
        raise
    except urllib.error.HTTPError as exc:
        # Do not read or copy the response body. Provider bodies may contain
        # request identifiers, account metadata, or reflected credentials.
        raise ProviderReadError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ProviderReadError(
            f"network error ({type(exc.reason).__name__})"
        ) from exc
    except TimeoutError as exc:
        raise ProviderReadError("timeout") from exc
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProviderReadError("invalid bounded JSON response") from exc
    if not isinstance(payload, (dict, list)):
        raise ProviderReadError("provider returned an unexpected JSON shape")
    return payload


def _supabase_ref(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        parsed_port = parsed.port
    except ValueError as exc:
        raise ProviderReadError("SUPABASE_URL is not a valid project URL") from exc
    host = (parsed.hostname or "").lower()
    suffix = ".supabase.co"
    ref = host[: -len(suffix)] if host.endswith(suffix) else ""
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed_port is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or SUPABASE_REF_RE.fullmatch(ref) is None
    ):
        raise ProviderReadError("SUPABASE_URL is not an exact hosted project URL")
    return ref


def _check(
    checks: list[dict[str, str]],
    check_id: str,
    status: str,
    detail: str,
) -> None:
    checks.append({"id": check_id, "status": status, "detail": detail})


def collect_provider_capacity(
    environment: Mapping[str, str] | None = None,
    *,
    transport: Transport = _default_transport,
) -> dict[str, Any]:
    """Return a safe monthly configuration snapshot using at most six GETs.

    Every provider/network/schema problem is returned as bounded alert data.
    The function never raises provider response content and never retries.
    """
    env = environment if environment is not None else os.environ
    checks: list[dict[str, str]] = []
    calls_attempted = 0

    def get_json(
        *,
        provider: str,
        check_id: str,
        url: str,
        token: str,
    ) -> Any | None:
        nonlocal calls_attempted
        if calls_attempted >= CALL_LIMIT:
            _check(
                checks,
                check_id,
                "fail",
                f"{provider} read skipped because the six-call ceiling was reached.",
            )
            return None
        calls_attempted += 1
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "RichmondCommons-ProviderCapacity/1.0",
            },
            method="GET",
        )
        try:
            return transport(request, TIMEOUT_SECONDS, RESPONSE_CAP_BYTES)
        except Exception as exc:
            _check(
                checks,
                check_id,
                "fail",
                f"{provider} read failed ({_provider_error_shape(exc)}).",
            )
            return None

    vercel_token = str(env.get("VERCEL_TOKEN") or "").strip()
    vercel_org_id = str(env.get("VERCEL_ORG_ID") or "").strip()
    if not vercel_token or VERCEL_ORG_ID_RE.fullmatch(vercel_org_id) is None:
        _check(
            checks,
            "vercel_plan",
            "fail",
            "Vercel plan check is missing valid VERCEL_TOKEN or VERCEL_ORG_ID configuration.",
        )
    else:
        team = get_json(
            provider="Vercel",
            check_id="vercel_plan",
            url=f"{VERCEL_API_BASE}/v2/teams/{vercel_org_id}",
            token=vercel_token,
        )
        if team is not None:
            try:
                plan = team["billing"]["plan"]
                response_team_id = team["id"]
            except (KeyError, TypeError):
                _check(
                    checks,
                    "vercel_plan",
                    "fail",
                    "Vercel team response schema changed; plan could not be verified.",
                )
            else:
                if response_team_id != vercel_org_id:
                    _check(
                        checks,
                        "vercel_plan",
                        "fail",
                        "Vercel returned a different team than the configured team.",
                    )
                elif plan != EXPECTED_VERCEL_PLAN:
                    _check(
                        checks,
                        "vercel_plan",
                        "fail",
                        "Vercel team plan does not match the required Hobby plan.",
                    )
                else:
                    _check(
                        checks,
                        "vercel_plan",
                        "pass",
                        "Vercel account plan is Hobby.",
                    )

    supabase_token = str(env.get("SUPABASE_ACCESS_TOKEN") or "").strip()
    supabase_url = str(env.get("SUPABASE_URL") or "").strip()
    try:
        project_ref = _supabase_ref(supabase_url)
    except ProviderReadError:
        project_ref = ""
    if not supabase_token or not project_ref:
        _check(
            checks,
            "supabase_configuration",
            "fail",
            "Supabase checks are missing valid SUPABASE_ACCESS_TOKEN or SUPABASE_URL configuration.",
        )
    else:
        project = get_json(
            provider="Supabase",
            check_id="supabase_project_health",
            url=f"{SUPABASE_API_BASE}/v1/projects/{project_ref}",
            token=supabase_token,
        )
        organization_slug = ""
        if project is not None:
            try:
                response_ref = project["ref"]
                project_status = project["status"]
                organization_slug = project["organization_slug"]
            except (KeyError, TypeError):
                _check(
                    checks,
                    "supabase_project_health",
                    "fail",
                    "Supabase project response schema changed; health could not be verified.",
                )
            else:
                if (
                    response_ref != project_ref
                    or SUPABASE_ORG_SLUG_RE.fullmatch(str(organization_slug)) is None
                ):
                    organization_slug = ""
                    _check(
                        checks,
                        "supabase_project_health",
                        "fail",
                        "Supabase returned a different or invalid project identity.",
                    )
                elif project_status != EXPECTED_SUPABASE_PROJECT_STATUS:
                    _check(
                        checks,
                        "supabase_project_health",
                        "fail",
                        "Supabase production project does not report ACTIVE_HEALTHY.",
                    )
                else:
                    _check(
                        checks,
                        "supabase_project_health",
                        "pass",
                        "Supabase production project reports ACTIVE_HEALTHY.",
                    )

        if organization_slug:
            encoded_slug = urllib.parse.quote(organization_slug, safe="")
            organization = get_json(
                provider="Supabase",
                check_id="supabase_plan",
                url=f"{SUPABASE_API_BASE}/v1/organizations/{encoded_slug}",
                token=supabase_token,
            )
            if organization is not None:
                plan = organization.get("plan") if isinstance(organization, dict) else None
                if plan != EXPECTED_SUPABASE_PLAN:
                    _check(
                        checks,
                        "supabase_plan",
                        "fail",
                        "Supabase organization plan does not match the required Pro plan.",
                    )
                else:
                    _check(
                        checks,
                        "supabase_plan",
                        "pass",
                        "Supabase organization plan is Pro.",
                    )

            org_projects = get_json(
                provider="Supabase",
                check_id="supabase_quota_scope",
                url=(
                    f"{SUPABASE_API_BASE}/v1/organizations/{encoded_slug}/projects"
                    f"?offset=0&limit={ORGANIZATION_PROJECT_LIMIT}"
                ),
                token=supabase_token,
            )
            if org_projects is not None:
                try:
                    projects = org_projects["projects"]
                    total = org_projects["pagination"]["count"]
                    limit = org_projects["pagination"]["limit"]
                    refs = {item["ref"] for item in projects}
                    active = sum(
                        1
                        for item in projects
                        if str(item.get("status") or "").startswith("ACTIVE_")
                    )
                except (KeyError, TypeError):
                    _check(
                        checks,
                        "supabase_quota_scope",
                        "fail",
                        "Supabase organization project inventory schema changed.",
                    )
                else:
                    if (
                        not isinstance(projects, list)
                        or isinstance(total, bool)
                        or not isinstance(total, int)
                        or total < len(projects)
                        or total > ORGANIZATION_PROJECT_LIMIT
                        or limit != ORGANIZATION_PROJECT_LIMIT
                        or project_ref not in refs
                    ):
                        _check(
                            checks,
                            "supabase_quota_scope",
                            "fail",
                            "Supabase organization project inventory exceeded or violated its 20-row bound.",
                        )
                    else:
                        _check(
                            checks,
                            "supabase_quota_scope",
                            "pass",
                            f"Supabase organization currently has {active} active project(s); usage quotas are organization-wide.",
                        )

        addons = get_json(
            provider="Supabase",
            check_id="supabase_paid_addons",
            url=f"{SUPABASE_API_BASE}/v1/projects/{project_ref}/billing/addons",
            token=supabase_token,
        )
        if addons is not None:
            selected = addons.get("selected_addons") if isinstance(addons, dict) else None
            if not isinstance(selected, list):
                _check(
                    checks,
                    "supabase_paid_addons",
                    "fail",
                    "Supabase add-on response schema changed.",
                )
            elif selected:
                _check(
                    checks,
                    "supabase_paid_addons",
                    "fail",
                    f"Supabase reports {len(selected)} selected paid add-on(s) for the production project.",
                )
            else:
                _check(
                    checks,
                    "supabase_paid_addons",
                    "pass",
                    "Supabase production project has no selected paid add-ons.",
                )

        branches = get_json(
            provider="Supabase",
            check_id="supabase_preview_branches",
            url=f"{SUPABASE_API_BASE}/v1/projects/{project_ref}/branches",
            token=supabase_token,
        )
        if branches is not None:
            try:
                if not isinstance(branches, list) or len(branches) > BRANCH_LIMIT:
                    raise TypeError
                if any(
                    not isinstance(item, dict)
                    or not isinstance(item.get("is_default"), bool)
                    for item in branches
                ):
                    raise TypeError
                defaults = [item for item in branches if item["is_default"] is True]
                previews = [item for item in branches if item["is_default"] is False]
            except (KeyError, TypeError):
                _check(
                    checks,
                    "supabase_preview_branches",
                    "fail",
                    "Supabase branch response schema changed or exceeded its 20-row bound.",
                )
            else:
                if len(defaults) != 1 or previews:
                    _check(
                        checks,
                        "supabase_preview_branches",
                        "fail",
                        f"Supabase reports {len(previews)} non-default Preview branch(es).",
                    )
                else:
                    _check(
                        checks,
                        "supabase_preview_branches",
                        "pass",
                        "Supabase has only the default branch; no Preview branch is running.",
                    )

    failures = [check for check in checks if check["status"] == "fail"]
    return {
        "schema_version": 1,
        "status": "fail" if failures else "pass",
        "coverage": "configuration_invariants_only",
        "calls_attempted": calls_attempted,
        "call_limit": CALL_LIMIT,
        "timeout_seconds": TIMEOUT_SECONDS,
        "response_cap_bytes": RESPONSE_CAP_BYTES,
        "checks": checks,
        "manual_usage_required": True,
        "automated_usage_gaps": [
            "Vercel Hobby rolling resource totals",
            "Supabase organization billing-cycle usage and projected overage",
        ],
    }
