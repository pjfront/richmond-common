from copy import deepcopy

import pytest

from feature_policy import (FeaturePolicyError, is_capability_enabled,
                            is_feature_enabled, load_policy, require_paid_capability,
                            resolve_profile, validate_policy)


def test_public_and_explicit_local_defaults_preserve_visibility_without_inference():
    assert resolve_profile() == "basic_public"
    assert resolve_profile(local=True) == "local_archive"
    assert is_feature_enabled("agenda_items")
    assert not is_feature_enabled("stored_ai_content")
    assert is_feature_enabled("stored_ai_content", local=True)
    assert is_feature_enabled("public_records", local=True)
    for name in ("inference", "embeddings", "ocr", "email", "accounts"):
        for profile in load_policy()["profiles"]:
            assert not is_capability_enabled(name, profile, local=profile.startswith("local_"))
    assert not is_feature_enabled("unknown")


def test_local_profile_cannot_be_selected_for_public_context():
    with pytest.raises(FeaturePolicyError):
        resolve_profile("local_archive")


@pytest.mark.parametrize("change", ["missing_feature", "truthy_capability", "missing_profile", "invalid_version", "bad_local_route"])
def test_invalid_control_policy_fails_closed(change):
    policy = deepcopy(load_policy())
    if change == "missing_feature":
        del policy["profiles"]["basic_public"]["features"]["votes"]
    elif change == "truthy_capability":
        policy["profiles"]["basic_public"]["capabilities"]["inference"] = "true"
    elif change == "missing_profile":
        del policy["profiles"]["cloud_ai"]
    elif change == "bad_local_route":
        policy["features"]["campaign_finance"]["localRoutes"] = ["https://example.test"]
    else:
        policy["schemaVersion"] = True
    with pytest.raises(FeaturePolicyError):
        validate_policy(policy)


def test_cloud_profile_name_never_authorizes_provider_call_and_budget_stays_separate():
    policy = deepcopy(load_policy())
    with pytest.raises(FeaturePolicyError):
        require_paid_capability("inference", "cloud_ai", budget_locked=False, policy=policy)
    policy["profiles"]["cloud_ai"]["capabilities"]["inference"] = True
    with pytest.raises(FeaturePolicyError):
        require_paid_capability("inference", "cloud_ai", budget_locked=True, policy=policy)
    require_paid_capability("inference", "cloud_ai", budget_locked=False, policy=policy)
    policy["profiles"]["cloud_ai"]["allowPaid"] = False
    with pytest.raises(FeaturePolicyError):
        require_paid_capability("inference", "cloud_ai", budget_locked=False, policy=policy)
