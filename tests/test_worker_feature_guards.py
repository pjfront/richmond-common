from unittest.mock import Mock, patch

import pytest

import llm_budget_lock
from feature_policy import FeaturePolicyError, assert_worker_provider_allowed


@pytest.mark.parametrize("profile", ["basic_public", "local_archive", "local_ai", "cloud_ai", "typo", ""])
def test_explicit_profile_refuses_legacy_provider_requests_before_reservation(monkeypatch, profile):
    monkeypatch.setenv("RICHMOND_FEATURE_PROFILE", profile)
    monkeypatch.setenv("RICHMOND_LOCAL_ARCHIVE", "true")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("RICHMOND_API_BUDGET_LOCK", "false")
    monkeypatch.setattr(llm_budget_lock, "_assert_accounting_not_poisoned", lambda: None)
    reserve = Mock()
    monkeypatch.setattr(llm_budget_lock, "_reserve_monthly_budget", reserve)
    for model in ("deepseek-v4-flash", "text-embedding-3-small"):
        with pytest.raises(FeaturePolicyError):
            llm_budget_lock._reserve_projected_spend_pre_call(model, 0.001)
    reserve.assert_not_called()


def test_unconfigured_legacy_worker_keeps_existing_budget_contract(monkeypatch):
    monkeypatch.delenv("RICHMOND_FEATURE_PROFILE", raising=False)
    assert_worker_provider_allowed("inference")
    assert_worker_provider_allowed("embeddings")


def test_llm_hook_stops_before_provider_client_or_token_preflight(monkeypatch):
    from llm_client import LLMClient
    monkeypatch.setenv("RICHMOND_FEATURE_PROFILE", "basic_public")
    provider = Mock()
    monkeypatch.setattr(LLMClient, "_client_for_route", provider)
    with pytest.raises(FeaturePolicyError):
        LLMClient().messages.create(model="deepseek-v4-flash", max_tokens=20,
                                    messages=[{"role": "user", "content": "test"}])
    provider.assert_not_called()


def test_embedding_hook_stops_before_provider_client_or_network(monkeypatch):
    # Legacy import-time dotenv is suppressed here just as in the isolated runner.
    with patch("dotenv.load_dotenv", return_value=False):
        import embedding_generator
    monkeypatch.setenv("RICHMOND_FEATURE_PROFILE", "basic_public")
    provider = Mock()
    monkeypatch.setattr(embedding_generator, "_get_openai_client", provider)
    with pytest.raises(FeaturePolicyError):
        embedding_generator.generate_embeddings(["actual nonempty civic text"])
    provider.assert_not_called()
