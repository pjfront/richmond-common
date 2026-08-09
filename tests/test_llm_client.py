"""Provider-contract tests for the fail-closed OpenAI-compatible LLM router."""
from __future__ import annotations

import base64
import json
import math
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

import llm_budget_lock as gate  # noqa: E402
import llm_client as llm  # noqa: E402


def _raw_response(
    *, text="ok", tool_calls=None, cached_tokens=0, cache_write_tokens=0,
    model=None,
):
    message = SimpleNamespace(
        content=text,
        reasoning_content=None,
        tool_calls=tool_calls or [],
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=20,
            prompt_tokens_details=SimpleNamespace(
                cached_tokens=cached_tokens,
                cache_write_tokens=cache_write_tokens,
            ),
        ),
        model=model,
    )


@pytest.fixture(autouse=True)
def clean_provider_env(monkeypatch):
    for name in (
        "DEEPSEEK_API_KEY",
        "MOONSHOT_API_KEY",
        "AI_GATEWAY_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def mocked_runtime(monkeypatch):
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.return_value = _raw_response()
    constructor = MagicMock(return_value=sdk_client)
    monkeypatch.setattr(llm, "OpenAI", constructor)

    reservation_id = uuid.uuid4()
    preflight = MagicMock(return_value=reservation_id)
    settle = MagicMock(return_value=True)
    settle_process = MagicMock()
    log_cost = MagicMock(return_value=True)
    monkeypatch.setattr(gate, "_enforce_caps_pre_call", preflight)
    monkeypatch.setattr(gate, "_settle_cost_reservation", settle)
    monkeypatch.setattr(gate, "_settle_process_spend", settle_process)
    monkeypatch.setattr(gate, "_log_cost", log_cost)
    monkeypatch.setattr(gate, "_detect_caller", MagicMock(return_value="test"))
    monkeypatch.setattr(gate, "_add_cached_mtd_spend", MagicMock())
    estimate_input = MagicMock(return_value=100)
    monkeypatch.setattr(llm, "_estimate_input_tokens", estimate_input)
    return SimpleNamespace(
        constructor=constructor,
        client=sdk_client,
        preflight=preflight,
        settle=settle,
        settle_process=settle_process,
        reservation_id=reservation_id,
        log_cost=log_cost,
        estimate_input=estimate_input,
    )


class TestLogicalTiers:
    def test_safe_defaults_are_stable(self):
        assert llm.ROUTINE_MODEL == "deepseek-v4-flash"
        assert llm.QUALITY_MODEL == "deepseek-v4-pro"
        assert llm.REASONING_MODEL == "deepseek-v4-pro"
        assert llm.CHALLENGER_MODEL == "kimi-k3"
        assert llm.VISION_MODEL == "kimi-k2.6"
        assert llm.DEFAULT_MODEL == llm.ROUTINE_MODEL

    @pytest.mark.parametrize("alias", ["routine", "quality", "reasoning", "challenger", "vision"])
    def test_logical_aliases_resolve_to_configured_routes(self, alias):
        assert llm._map_model(alias) in llm.MODEL_ROUTES

    @pytest.mark.parametrize("model", ["deepseek-chat", "deepseek-reasoner", "claude-sonnet-5", "gpt-5.4"])
    def test_retired_or_unconfigured_chat_aliases_fail_closed(self, model):
        with pytest.raises(llm.LLMUnsupportedRouteError):
            llm._map_model(model)

    def test_unknown_model_fails_closed(self):
        with pytest.raises(llm.LLMUnsupportedRouteError, match="Unknown LLM"):
            llm._map_model("future-cheap-model")


class TestProviderSelection:
    def test_default_uses_direct_deepseek_key_not_openai_fallback(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-embedding-secret")

        response = llm.LLMClient().messages.create(
            messages=[{"role": "user", "content": "hello"}]
        )

        assert response.model == llm.ROUTINE_MODEL
        mocked_runtime.constructor.assert_called_once_with(
            api_key="deepseek-secret",
            base_url=llm.DEEPSEEK_BASE_URL,
            timeout=60.0,
            max_retries=0,
        )
        kwargs = mocked_runtime.client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "deepseek-v4-flash"
        assert kwargs["extra_body"]["thinking"] == {"type": "disabled"}

    def test_openai_key_is_never_used_for_missing_deepseek_key(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("OPENAI_API_KEY", "embeddings-only")
        with pytest.raises(llm.LLMProviderConfigurationError, match="DEEPSEEK_API_KEY"):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "hello"}],
            )
        mocked_runtime.constructor.assert_not_called()

    @pytest.mark.parametrize(
        ("model", "disabled_effort"),
        [
            (llm.OPENAI_LUNA_MODEL, "none"),
        ],
    )
    def test_openai_benchmark_routes_are_explicit_and_cost_bounded(
        self, model, disabled_effort, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("OPENAI_API_KEY", "openai-chat-secret")

        llm.LLMClient().create(
            model=model,
            max_tokens=77,
            messages=[{"role": "user", "content": "benchmark"}],
        )

        mocked_runtime.constructor.assert_called_once_with(
            api_key="openai-chat-secret",
            base_url=llm.OPENAI_BASE_URL,
            timeout=60.0,
            max_retries=0,
        )
        kwargs = mocked_runtime.client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == model
        assert kwargs["max_completion_tokens"] == 77
        assert "max_tokens" not in kwargs
        assert kwargs["reasoning_effort"] == disabled_effort
        assert "extra_body" not in kwargs
        mocked_runtime.preflight.assert_called_once_with(
            model,
            estimated_input_tokens=100,
            max_output_tokens=77,
        )

    def test_openai_route_never_falls_back_to_deepseek_key(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        with pytest.raises(
            llm.LLMProviderConfigurationError, match="OPENAI_API_KEY"
        ):
            llm.LLMClient().create(
                model=llm.OPENAI_LUNA_MODEL,
                messages=[{"role": "user", "content": "benchmark"}],
            )
        mocked_runtime.constructor.assert_not_called()

    @pytest.mark.parametrize("model", [llm.KIMI_K26_MODEL, llm.KIMI_K3_MODEL])
    def test_direct_kimi_uses_moonshot_key_and_official_base_url(
        self, model, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        llm.LLMClient().create(
            model=model,
            messages=[{"role": "user", "content": "hello"}],
        )
        mocked_runtime.constructor.assert_called_once_with(
            api_key="moonshot-secret",
            base_url=llm.MOONSHOT_BASE_URL,
            timeout=60.0,
            max_retries=0,
        )

    @pytest.mark.parametrize(
        "model", [llm.KIMI_K3_GATEWAY_MODEL, llm.KIMI_K26_GATEWAY_MODEL]
    )
    def test_gateway_models_require_gateway_key(
        self, model, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("AI_GATEWAY_API_KEY", "gateway-secret")
        llm.LLMClient().create(
            model=model,
            messages=[{"role": "user", "content": "hello"}],
        )
        mocked_runtime.constructor.assert_called_once_with(
            api_key="gateway-secret",
            base_url=llm.AI_GATEWAY_BASE_URL,
            timeout=60.0,
            max_retries=0,
        )

    def test_explicit_key_is_pinned_to_explicit_provider(
        self, mocked_runtime
    ):
        client = llm.LLMClient(api_key="deepseek-test")
        with pytest.raises(llm.LLMProviderConfigurationError, match="pinned"):
            client.create(
                model=llm.KIMI_K26_MODEL,
                messages=[{"role": "user", "content": "hello"}],
            )
        mocked_runtime.constructor.assert_not_called()

    def test_unknown_provider_rejected_at_construction(self):
        with pytest.raises(llm.LLMProviderConfigurationError, match="Unknown provider"):
            llm.LLMClient(provider="mystery")

    @pytest.mark.parametrize("retries", [False, True, 0.0, -1, 1, 2])
    def test_sdk_retries_are_rejected_before_any_provider_call(self, retries):
        with pytest.raises(ValueError, match="max_retries must be 0"):
            llm.LLMClient(max_retries=retries)


class TestThinkingAndParameters:
    def test_deepseek_thinking_is_explicit_and_reasoning_effort_is_forwarded(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        llm.LLMClient().create(
            model=llm.REASONING_MODEL,
            messages=[{"role": "user", "content": "analyze"}],
            thinking={"type": "enabled"},
            reasoning_effort="high",
        )
        kwargs = mocked_runtime.client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}
        assert kwargs["reasoning_effort"] == "high"

    @pytest.mark.parametrize("effort", ["high", "max"])
    def test_supported_deepseek_reasoning_efforts(
        self, effort, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        llm.LLMClient().create(
            model=llm.REASONING_MODEL,
            messages=[{"role": "user", "content": "analyze"}],
            thinking=True,
            reasoning_effort=effort,
        )
        assert (
            mocked_runtime.client.chat.completions.create.call_args.kwargs[
                "reasoning_effort"
            ]
            == effort
        )

    @pytest.mark.parametrize("effort", ["low", "high", "max"])
    def test_supported_k3_reasoning_efforts(
        self, effort, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        llm.LLMClient().create(
            model=llm.KIMI_K3_MODEL,
            messages=[{"role": "user", "content": "analyze"}],
            reasoning_effort=effort,
        )
        assert (
            mocked_runtime.client.chat.completions.create.call_args.kwargs[
                "reasoning_effort"
            ]
            == effort
        )

    def test_reasoning_effort_requires_thinking(self, monkeypatch, mocked_runtime):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        with pytest.raises(llm.LLMCapabilityError, match="only when thinking"):
            llm.LLMClient().create(
                model=llm.QUALITY_MODEL,
                messages=[{"role": "user", "content": "analyze"}],
                reasoning_effort="high",
            )

    def test_invalid_reasoning_effort_fails_before_request(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        with pytest.raises(llm.LLMCapabilityError, match="high, max"):
            llm.LLMClient().create(
                model=llm.REASONING_MODEL,
                messages=[{"role": "user", "content": "analyze"}],
                thinking=True,
                reasoning_effort="xhigh",
            )
        mocked_runtime.constructor.assert_not_called()

    def test_forced_tool_choice_rejected_in_thinking_mode(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        with pytest.raises(llm.LLMCapabilityError, match="quarantined"):
            llm.LLMClient().create(
                model=llm.REASONING_MODEL,
                messages=[{"role": "user", "content": "analyze"}],
                thinking=True,
                tools=[{"name": "extract", "input_schema": {"type": "object"}}],
                tool_choice={"type": "tool", "name": "extract"},
            )

    def test_k26_rejects_reasoning_effort(self, monkeypatch, mocked_runtime):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        with pytest.raises(llm.LLMCapabilityError, match="values: none"):
            llm.LLMClient().create(
                model=llm.KIMI_K26_MODEL,
                messages=[{"role": "user", "content": "analyze"}],
                thinking=True,
                reasoning_effort="high",
            )

    @pytest.mark.parametrize(
        ("parameter", "value"),
        [
            ("top_p", 0.5),
            ("n", 2),
            ("presence_penalty", 1.0),
            ("frequency_penalty", 1.0),
        ],
    )
    def test_k26_rejects_nonfixed_sampling_parameters(
        self, parameter, value, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        with pytest.raises(llm.LLMCapabilityError, match=f"fixes {parameter}"):
            llm.LLMClient().create(
                model=llm.KIMI_K26_MODEL,
                messages=[{"role": "user", "content": "hello"}],
                **{parameter: value},
            )

    def test_k3_is_always_thinking_and_cannot_be_disabled(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        with pytest.raises(llm.LLMCapabilityError, match="always-thinking"):
            llm.LLMClient().create(
                model=llm.CHALLENGER_MODEL,
                messages=[{"role": "user", "content": "hello"}],
                thinking=False,
            )


class TestToolsStructuredOutputAndUsage:
    def test_anthropic_tools_translate_and_tool_response_round_trips(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        tool_call = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name="extract", arguments='{"value": 7}'),
        )
        mocked_runtime.client.chat.completions.create.return_value = _raw_response(
            text="", tool_calls=[tool_call]
        )
        response = llm.LLMClient().create(
            model=llm.QUALITY_MODEL,
            messages=[{"role": "user", "content": "extract"}],
            tools=[{
                "name": "extract",
                "description": "Extract a value",
                "input_schema": {"type": "object", "properties": {"value": {"type": "integer"}}},
            }],
            tool_choice={"type": "tool", "name": "extract"},
        )
        request = mocked_runtime.client.chat.completions.create.call_args.kwargs
        assert request["tools"][0]["type"] == "function"
        assert request["tool_choice"] == {
            "type": "function",
            "function": {"name": "extract"},
        }
        assert request["extra_body"]["thinking"] == {"type": "disabled"}
        assert response.stop_reason == "end_turn"
        assert response.content[0].type == "tool_use"
        assert response.content[0].id == "call_1"
        assert response.content[0].input == {"value": 7}

    def test_structured_output_kwarg_is_forwarded(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        schema = {"type": "json_object"}
        llm.LLMClient().create(
            model=llm.ROUTINE_MODEL,
            messages=[{"role": "user", "content": "json"}],
            response_format=schema,
        )
        request = mocked_runtime.client.chat.completions.create.call_args.kwargs
        assert request["response_format"] == schema
        assert mocked_runtime.estimate_input.call_args.kwargs["request_metadata"][
            "response_format"
        ] == schema

    @pytest.mark.parametrize("completion_count", [False, 0, 2, 3, 1.0, "1"])
    def test_multiple_or_malformed_completions_fail_before_budget_or_provider(
        self, monkeypatch, mocked_runtime, completion_count
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        with pytest.raises(llm.LLMCapabilityError, match="fixes n at exactly 1"):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "hello"}],
                n=completion_count,
            )
        mocked_runtime.estimate_input.assert_not_called()
        mocked_runtime.preflight.assert_not_called()
        mocked_runtime.client.chat.completions.create.assert_not_called()

    def test_single_completion_is_allowed(self, monkeypatch, mocked_runtime):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        llm.LLMClient().create(
            model=llm.ROUTINE_MODEL,
            messages=[{"role": "user", "content": "hello"}],
            n=1,
        )
        assert mocked_runtime.client.chat.completions.create.call_args.kwargs["n"] == 1

    def test_deepseek_rejects_json_schema(self, monkeypatch, mocked_runtime):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        with pytest.raises(llm.LLMCapabilityError, match="does not support"):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "json"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "answer", "schema": {"type": "object"}},
                },
            )
        mocked_runtime.client.chat.completions.create.assert_not_called()

    def test_k3_accepts_json_schema(self, monkeypatch, mocked_runtime):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        schema = {
            "type": "json_schema",
            "json_schema": {"name": "answer", "schema": {"type": "object"}},
        }
        llm.LLMClient().create(
            model=llm.KIMI_K3_MODEL,
            messages=[{"role": "user", "content": "json"}],
            response_format=schema,
        )
        assert (
            mocked_runtime.client.chat.completions.create.call_args.kwargs[
                "response_format"
            ]
            == schema
        )

    def test_unknown_provider_kwarg_is_not_silently_discarded(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        with pytest.raises(TypeError, match="Unsupported LLM create"):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "hello"}],
                mystery_option=True,
            )
        mocked_runtime.constructor.assert_not_called()

    @pytest.mark.parametrize(
        "extra_body",
        [
            {"max_tokens": 100_000},
            {"model": "unpriced-model"},
            {"n": 10},
            {"thinking": {"type": "enabled"}},
            {"provider_extension": True},
        ],
    )
    def test_caller_extra_body_cannot_override_routing_or_budget_fields(
        self, extra_body, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        with pytest.raises(llm.LLMCapabilityError, match="extra_body is quarantined"):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                max_tokens=100,
                messages=[{"role": "user", "content": "hello"}],
                extra_body=extra_body,
            )
        mocked_runtime.preflight.assert_not_called()
        mocked_runtime.client.chat.completions.create.assert_not_called()

    @pytest.mark.parametrize(
        ("parameter", "value"),
        [
            ("top_p", 0.5),
            ("n", 2),
            ("presence_penalty", 1.0),
            ("frequency_penalty", 1.0),
        ],
    )
    def test_k3_rejects_nonfixed_sampling_parameters(
        self, parameter, value, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        with pytest.raises(llm.LLMCapabilityError, match=f"fixes {parameter}"):
            llm.LLMClient().create(
                model=llm.KIMI_K3_MODEL,
                messages=[{"role": "user", "content": "analyze"}],
                **{parameter: value},
            )
        mocked_runtime.constructor.assert_not_called()

    def test_cache_read_usage_is_preserved_and_logged(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        mocked_runtime.client.chat.completions.create.return_value = _raw_response(
            cached_tokens=40
        )
        response = llm.LLMClient().create(
            model=llm.ROUTINE_MODEL,
            messages=[{"role": "user", "content": "hello"}],
        )
        assert response.usage.input_tokens == 100
        assert response.usage.cache_read_input_tokens == 40
        assert mocked_runtime.log_cost.call_args.kwargs["extra"][
            "cache_read_input_tokens"
        ] == 40
        mocked_runtime.settle.assert_called_once()
        assert mocked_runtime.settle.call_args.args[0] == mocked_runtime.reservation_id
        assert mocked_runtime.log_cost.call_args.kwargs["extra"][
            "reservation_id"
        ] == str(mocked_runtime.reservation_id)
        assert mocked_runtime.log_cost.call_args.kwargs["extra"][
            "provider_model"
        ] == llm.ROUTINE_MODEL
        mocked_runtime.settle_process.assert_called_once()

    def test_openai_cache_write_usage_is_preserved_and_logged(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
        mocked_runtime.client.chat.completions.create.return_value = _raw_response(
            cached_tokens=20,
            cache_write_tokens=30,
        )
        response = llm.LLMClient().create(
            model=llm.OPENAI_LUNA_MODEL,
            messages=[{"role": "user", "content": "hello"}],
        )
        assert response.usage.cache_read_input_tokens == 20
        assert response.usage.cache_creation_input_tokens == 30
        assert mocked_runtime.log_cost.call_args.kwargs["extra"][
            "cache_write_input_tokens"
        ] == 30

    @pytest.mark.parametrize(
        "usage",
        [
            None,
            SimpleNamespace(prompt_tokens=None, completion_tokens=1),
            SimpleNamespace(prompt_tokens="100", completion_tokens=1),
            SimpleNamespace(prompt_tokens=-1, completion_tokens=1),
            SimpleNamespace(prompt_tokens=0, completion_tokens=0),
            SimpleNamespace(prompt_tokens=100, completion_tokens=None),
            SimpleNamespace(prompt_tokens=100, completion_tokens="1"),
            SimpleNamespace(prompt_tokens=100, completion_tokens=-1),
            SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=1,
                prompt_cache_hit_tokens=101,
            ),
            SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=1,
                prompt_tokens_details=SimpleNamespace(cached_tokens="40"),
            ),
            SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=1,
                prompt_tokens_details=SimpleNamespace(
                    cached_tokens=80,
                    cache_write_tokens=30,
                ),
            ),
        ],
    )
    def test_invalid_provider_usage_keeps_ceiling_and_poisons(
        self, usage, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        raw = _raw_response()
        raw.usage = usage
        mocked_runtime.client.chat.completions.create.return_value = raw
        invalidate = MagicMock()
        monkeypatch.setattr(gate, "_invalidate_mtd_cache", invalidate)

        with pytest.raises(gate.LLMBudgetAccountingError, match="invalid cost usage"):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "hello"}],
            )

        mocked_runtime.settle.assert_not_called()
        mocked_runtime.log_cost.assert_not_called()
        mocked_runtime.settle_process.assert_not_called()
        invalidate.assert_called_once_with(poison=True)

    def test_reasoning_only_response_is_logged_then_rejected(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        raw = _raw_response(text="")
        raw.choices[0].message.reasoning_content = "private trace"
        raw.choices[0].finish_reason = "length"
        mocked_runtime.client.chat.completions.create.return_value = raw

        with pytest.raises(llm.LLMCapabilityError, match="no final answer"):
            llm.LLMClient().create(
                model=llm.REASONING_MODEL,
                messages=[{"role": "user", "content": "analyze"}],
                thinking=True,
                reasoning_effort="high",
            )

        mocked_runtime.log_cost.assert_called_once()

    def test_failed_cost_write_poisons_future_spend(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        mocked_runtime.log_cost.return_value = False
        invalidate = MagicMock()
        monkeypatch.setattr(gate, "_invalidate_mtd_cache", invalidate)

        with pytest.warns(RuntimeWarning, match="could not be persisted"):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "hello"}],
            )

        invalidate.assert_called_once_with(poison=True)
        mocked_runtime.settle_process.assert_not_called()

    def test_failed_reservation_settlement_poisons_future_spend(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        mocked_runtime.settle.return_value = False
        invalidate = MagicMock()
        monkeypatch.setattr(gate, "_invalidate_mtd_cache", invalidate)

        with pytest.warns(RuntimeWarning, match="reservation settlement"):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "hello"}],
            )

        invalidate.assert_called_once_with(poison=True)
        mocked_runtime.settle_process.assert_not_called()

    def test_process_spend_settlement_failure_poisons_and_raises(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        mocked_runtime.settle_process.side_effect = RuntimeError("state lost")
        invalidate = MagicMock()
        monkeypatch.setattr(gate, "_invalidate_mtd_cache", invalidate)

        with pytest.raises(
            gate.LLMBudgetAccountingError,
            match="process event ceiling",
        ):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "hello"}],
            )

        invalidate.assert_called_once_with(poison=True)

    def test_accounting_failure_blocks_second_call_before_provider(
        self, monkeypatch
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        monkeypatch.setitem(gate._mtd_cache, "poisoned", False)
        sdk_client = MagicMock()
        sdk_client.chat.completions.create.return_value = _raw_response()
        monkeypatch.setattr(llm, "OpenAI", MagicMock(return_value=sdk_client))
        monkeypatch.setattr(
            gate, "_reserve_monthly_budget", MagicMock(return_value=uuid.uuid4())
        )
        monkeypatch.setattr(
            gate, "_settle_cost_reservation", MagicMock(return_value=False)
        )
        monkeypatch.setattr(gate, "_log_cost", MagicMock(return_value=True))

        client = llm.LLMClient()
        with pytest.warns(RuntimeWarning, match="reservation settlement"):
            client.create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "first"}],
            )

        with pytest.raises(gate.LLMBudgetAccountingError, match="prior LLM cost"):
            client.create(
                model=llm.ROUTINE_MODEL,
                messages=[{"role": "user", "content": "second"}],
            )
        assert sdk_client.chat.completions.create.call_count == 1


class TestModalityAndBatchBoundaries:
    def test_openai_luna_original_vision_uses_local_patch_estimator(self):
        width, height = 1025, 769
        png_header = (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00\x00\x00\x0dIHDR"
            + width.to_bytes(4, "big")
            + height.to_bytes(4, "big")
        )
        data_url = "data:image/png;base64," + base64.b64encode(
            png_header
        ).decode("ascii")
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Read the form"},
                {
                    "type": "image_url",
                    "image_url": {"url": data_url, "detail": "original"},
                },
            ],
        }]

        estimated = llm._estimate_input_tokens(
            "system",
            messages,
            None,
            route=llm.get_model_route(llm.OPENAI_LUNA_MODEL),
            api_key="test-key",
            openai_messages=messages,
        )

        exact_image_patches = math.ceil(width / 32) * math.ceil(height / 32)
        assert estimated > exact_image_patches
        assert estimated < exact_image_patches + 2_000

    @pytest.mark.parametrize(
        "image_url",
        [
            {"url": "data:image/png;base64,AA=="},
            {"url": "https://example.com/form.png", "detail": "original"},
        ],
    )
    def test_openai_luna_vision_rejects_unbudgetable_images(self, image_url):
        messages = [{
            "role": "user",
            "content": [{"type": "image_url", "image_url": image_url}],
        }]

        with pytest.raises(llm.LLMCapabilityError):
            llm._estimate_input_tokens(
                None,
                messages,
                None,
                route=llm.get_model_route(llm.OPENAI_LUNA_MODEL),
                api_key="test-key",
            )

    def test_openai_luna_accepts_explicit_original_png_blocks(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
        content = [{
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,AA==",
                "detail": "original",
            },
        }]

        llm.LLMClient().create(
            model=llm.OPENAI_LUNA_MODEL,
            messages=[{"role": "user", "content": content}],
        )

        request = mocked_runtime.client.chat.completions.create.call_args.kwargs
        assert request["messages"] == [{"role": "user", "content": content}]
        assert request["reasoning_effort"] == "none"

    def test_direct_moonshot_vision_uses_provider_token_estimator(self, monkeypatch):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"data":{"total_tokens":1000}}'
        urlopen = MagicMock(return_value=response)
        monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
        route = llm.get_model_route(llm.KIMI_K26_MODEL)
        messages = [{
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,AA=="},
            }],
        }]

        estimated = llm._estimate_input_tokens(
            None,
            messages,
            None,
            route=route,
            api_key="test-key",
            openai_messages=messages,
        )

        assert estimated == 1164  # 10% safety margin + 64 tokens
        request = urlopen.call_args.args[0]
        assert request.full_url.endswith("/tokenizers/estimate-token-count")
        assert b'"model": "kimi-k2.6"' in request.data

    def test_moonshot_estimator_excludes_tools_but_budgets_them_locally(
        self, monkeypatch
    ):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"data":{"total_tokens":1000}}'
        urlopen = MagicMock(return_value=response)
        monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
        route = llm.get_model_route(llm.KIMI_K26_MODEL)
        messages = [{
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,AA=="},
            }],
        }]
        translated_tools = [{
            "type": "function",
            "function": {
                "name": "save_rows",
                "parameters": {
                    "type": "object",
                    "properties": {"rows": {"type": "array"}},
                },
            },
        }]

        estimated = llm._estimate_input_tokens(
            None,
            messages,
            translated_tools,
            route=route,
            api_key="test-key",
            openai_messages=messages,
            translated_tools=translated_tools,
        )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        assert payload == {"model": "kimi-k2.6", "messages": messages}
        tool_bytes = len(
            json.dumps(
                translated_tools,
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        )
        assert estimated >= math.ceil((1000 + tool_bytes + 256) * 1.10) + 64

    def test_moonshot_estimator_budgets_response_schema_locally(self, monkeypatch):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"data":{"total_tokens":1000}}'
        monkeypatch.setattr(
            llm.urllib.request,
            "urlopen",
            MagicMock(return_value=response),
        )
        route = llm.get_model_route(llm.KIMI_K26_MODEL)
        messages = [{
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,AA=="},
            }],
        }]
        schema = {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "large_schema",
                    "schema": {"description": "x" * 10_000},
                },
            }
        }

        estimated = llm._estimate_input_tokens(
            None,
            messages,
            None,
            route=route,
            api_key="test-key",
            openai_messages=messages,
            request_metadata=schema,
        )

        assert estimated > 11_000

    def test_hard_lock_prevents_remote_vision_estimator(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        monkeypatch.setenv("RICHMOND_API_BUDGET_LOCK", "true")
        with pytest.raises(gate.LLMBudgetLockError, match="BUDGET_LOCK"):
            llm.LLMClient().create(
                model=llm.KIMI_K26_MODEL,
                messages=[{
                    "role": "user",
                    "content": [{
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,AA=="},
                    }],
                }],
            )
        mocked_runtime.constructor.assert_not_called()
        mocked_runtime.estimate_input.assert_not_called()
        mocked_runtime.preflight.assert_not_called()

    @pytest.mark.parametrize("total_tokens", [True, "1000", 0, -1])
    def test_moonshot_estimator_rejects_malformed_or_nonpositive_usage(
        self, monkeypatch, total_tokens,
    ):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "data": {"total_tokens": total_tokens},
        }).encode("utf-8")
        monkeypatch.setattr(
            llm.urllib.request,
            "urlopen",
            MagicMock(return_value=response),
        )
        route = llm.get_model_route(llm.KIMI_K26_MODEL)
        messages = [{
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,AA=="},
            }],
        }]

        with pytest.raises(llm.LLMCapabilityError, match="estimation failed"):
            llm._estimate_input_tokens(
                None,
                messages,
                None,
                route=route,
                api_key="test-key",
                openai_messages=messages,
            )

    def test_gateway_vision_without_provider_estimator_fails_closed(self):
        route = llm.get_model_route(llm.KIMI_K26_GATEWAY_MODEL)
        messages = [{
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,AA=="},
            }],
        }]
        with pytest.raises(llm.LLMCapabilityError, match="direct Moonshot"):
            llm._estimate_input_tokens(
                None,
                messages,
                None,
                route=route,
                api_key="gateway-key",
            )

    def test_text_only_deepseek_rejects_image_blocks(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
        with pytest.raises(llm.LLMCapabilityError, match="text-only"):
            llm.LLMClient().create(
                model=llm.ROUTINE_MODEL,
                messages=[{
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}],
                }],
            )
        mocked_runtime.constructor.assert_not_called()

    def test_kimi_accepts_openai_image_url_blocks(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        content = [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
            {"type": "text", "text": "Read this"},
        ]
        llm.LLMClient().create(
            model=llm.VISION_MODEL,
            messages=[{"role": "user", "content": content}],
        )
        request = mocked_runtime.client.chat.completions.create.call_args.kwargs
        assert request["messages"] == [{"role": "user", "content": content}]
        assert request["extra_body"]["thinking"] == {"type": "disabled"}

    def test_anthropic_pdf_document_blocks_are_quarantined(
        self, monkeypatch, mocked_runtime
    ):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
        with pytest.raises(llm.LLMCapabilityError, match="document/PDF"):
            llm.LLMClient().create(
                model=llm.VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": [{
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": "AA=="},
                    }],
                }],
            )
        mocked_runtime.constructor.assert_not_called()

    @pytest.mark.parametrize(
        "model",
        [
            llm.ROUTINE_MODEL,
            llm.QUALITY_MODEL,
            llm.KIMI_K26_MODEL,
            llm.KIMI_K26_GATEWAY_MODEL,
            llm.KIMI_K3_MODEL,
            llm.KIMI_K3_GATEWAY_MODEL,
        ],
    )
    def test_batch_is_quarantined_for_every_configured_route(
        self, model, mocked_runtime
    ):
        with pytest.raises(llm.LLMBatchUnsupportedError, match="quarantined"):
            llm.LLMClient().batch_prepare_requests([
                {"custom_id": "x", "params": {"model": model, "messages": []}}
            ])
        mocked_runtime.constructor.assert_not_called()
