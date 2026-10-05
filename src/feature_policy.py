"""Shared, reversible visibility and execution policy; never changes records.

Reads web/src/data/feature-tiers.json. Feature visibility does not grant
operator access, enable a generator, or authorize a paid provider request.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

POLICY_PATH = Path(__file__).resolve().parent.parent / "web/src/data/feature-tiers.json"
PROFILE_IDS = frozenset({"basic_public", "local_archive", "local_ai", "cloud_ai"})
LOCAL_PROFILES = frozenset({"local_archive", "local_ai"})
CAPABILITY_IDS = frozenset({
    "refresh_agenda", "refresh_tags", "refresh_finance", "inference",
    "embeddings", "ocr", "email", "accounts",
})
FEATURE_GROUPS = frozenset({"record_core", "deep_records", "analysis", "ai", "communication"})


class FeaturePolicyError(ValueError):
    """An invalid or unavailable policy fails closed."""


def validate_policy(policy: Any) -> dict[str, Any]:
    if not isinstance(policy, dict) or type(policy.get("schemaVersion")) is not int or policy["schemaVersion"] != 1:
        raise FeaturePolicyError("Unsupported feature-policy schema version")
    defaults, features, profiles, storage = (policy.get(key) for key in ("defaults", "features", "profiles", "storage"))
    if not isinstance(defaults, dict) or defaults != {"public": "basic_public", "local": "local_archive"}:
        raise FeaturePolicyError("Public/basic and local/archive defaults are required")
    if not isinstance(features, dict) or not features:
        raise FeaturePolicyError("Feature catalog is missing")
    for feature in features.values():
        if (not isinstance(feature, dict) or feature.get("group") not in FEATURE_GROUPS
                or not isinstance(feature.get("label"), str) or not feature["label"]
                or not isinstance(feature.get("description"), str)
                or not isinstance(feature.get("routes"), list)
                or not isinstance(feature.get("localRoutes", []), list)
                or any(not isinstance(route, str) or not route.startswith("/")
                       for route in feature["routes"] + feature.get("localRoutes", []))):
            raise FeaturePolicyError("Invalid feature catalog entry")
    if not isinstance(profiles, dict) or set(profiles) != PROFILE_IDS:
        raise FeaturePolicyError("All four named feature profiles are required")
    if not isinstance(storage, dict) or set(storage) != PROFILE_IDS:
        raise FeaturePolicyError("Storage policy is required for every profile")
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict) or type(profile.get("allowPaid")) is not bool:
            raise FeaturePolicyError("Invalid profile paid authorization")
        flags, capabilities = profile.get("features"), profile.get("capabilities")
        if (not isinstance(flags, dict) or set(flags) != set(features)
                or any(type(flag) is not bool for flag in flags.values())):
            raise FeaturePolicyError("Every profile must explicitly set every feature")
        if (not isinstance(capabilities, dict) or set(capabilities) != CAPABILITY_IDS
                or any(type(flag) is not bool for flag in capabilities.values())):
            raise FeaturePolicyError("Every profile must explicitly set every capability")
        rules = storage[profile_id]
        if (not isinstance(rules, dict) or type(rules.get("writerReady")) is not bool
                or rules.get("mode") not in {"full_archive", "compact_public"}):
            raise FeaturePolicyError("Invalid storage writer policy")
        ceiling = rules.get("maxDatabaseBytes")
        if ceiling is not None and (type(ceiling) is not int or ceiling <= 0):
            raise FeaturePolicyError("Storage ceiling must be positive or explicitly null")
    return policy


def load_policy(path: Path | str | None = None) -> dict[str, Any]:
    try:
        policy = json.loads(Path(path or POLICY_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FeaturePolicyError("Feature policy could not be loaded") from exc
    return validate_policy(policy)


def resolve_profile(profile: str | None = None, *, local: bool = False, policy: dict[str, Any] | None = None) -> str:
    selected = profile or (policy or load_policy())["defaults"]["local" if local else "public"]
    if selected not in PROFILE_IDS:
        raise FeaturePolicyError("Unknown feature profile")
    if selected in LOCAL_PROFILES and not local:
        raise FeaturePolicyError("Local profiles require an explicit local context")
    return selected


def is_feature_enabled(feature: str, profile: str | None = None, *, local: bool = False,
                       policy: dict[str, Any] | None = None) -> bool:
    current = policy or load_policy()
    selected = resolve_profile(profile, local=local, policy=current)
    return current["profiles"][selected]["features"].get(feature) is True


def is_capability_enabled(capability: str, profile: str | None = None, *, local: bool = False,
                          policy: dict[str, Any] | None = None) -> bool:
    current = policy or load_policy()
    selected = resolve_profile(profile, local=local, policy=current)
    return current["profiles"][selected]["capabilities"].get(capability) is True


def require_paid_capability(capability: str, profile: str, *, budget_locked: bool,
                            local: bool = False, policy: dict[str, Any] | None = None) -> None:
    """A profile name alone cannot authorize a billable request."""
    current = policy or load_policy()
    selected = resolve_profile(profile, local=local, policy=current)
    if (capability not in {"inference", "embeddings"} or budget_locked
            or current["profiles"][selected]["allowPaid"] is not True
            or not is_capability_enabled(capability, selected, local=local, policy=current)):
        raise FeaturePolicyError("Paid capability is disabled or its budget is locked")


def assert_worker_provider_allowed(capability: str) -> None:
    """Gate legacy providers when a profile is explicitly configured.

    Unconfigured legacy callers retain their existing budget/provider behavior.
    Local model adapters are not implemented here and cannot borrow cloud keys.
    """
    requested = os.environ.get("RICHMOND_FEATURE_PROFILE")
    if requested is None:
        return
    current = load_policy()
    local = os.environ.get("RICHMOND_LOCAL_ARCHIVE") == "true" and not os.environ.get("VERCEL")
    selected = resolve_profile(requested, local=local, policy=current)
    if (capability not in {"inference", "embeddings"}
            or current["profiles"][selected]["allowPaid"] is not True
            or not is_capability_enabled(capability, selected, local=local, policy=current)):
        raise FeaturePolicyError("Configured worker profile disables this provider capability")
