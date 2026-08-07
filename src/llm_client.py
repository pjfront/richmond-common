"""Cost-aware, Anthropic-compatible LLM client over OpenAI-style APIs.

The production default is direct DeepSeek V4 Flash in non-thinking mode.
Higher-cost or multimodal routes must be selected explicitly.  There is no
automatic provider fallback: a missing provider key, unknown model, or
unsupported capability raises before any network request is made.

Existing call sites can continue to use the Anthropic-shaped interface::

    client = LLMClient(timeout=60.0)
    response = client.messages.create(
        model=ROUTINE_MODEL,
        max_tokens=1200,
        temperature=0,
        system="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Hello"}],
    )

``response.content``, ``response.usage``, ``response.stop_reason``, and tool
blocks mirror the subset of Anthropic's Messages response used by this repo.
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
import warnings
from dataclasses import dataclass, field
from typing import Any, Literal

from openai import OpenAI


# ---------------------------------------------------------------------------
# Routes and logical tiers
# ---------------------------------------------------------------------------

DEEPSEEK_FLASH_MODEL = "deepseek-v4-flash"
DEEPSEEK_PRO_MODEL = "deepseek-v4-pro"
KIMI_K3_MODEL = "kimi-k3"
KIMI_K3_GATEWAY_MODEL = "moonshotai/kimi-k3"
KIMI_K26_MODEL = "kimi-k2.6"
KIMI_K26_GATEWAY_MODEL = "moonshotai/kimi-k2.6"
OPENAI_LUNA_MODEL = "gpt-5.6-luna"

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"
AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"


class LLMRouteError(ValueError):
    """Base class for routing/configuration failures detected pre-request."""


class LLMUnsupportedRouteError(LLMRouteError):
    """Raised when a model has no deliberately configured production route."""


class LLMProviderConfigurationError(LLMRouteError):
    """Raised when a selected provider is unknown or lacks its own API key."""


class LLMCapabilityError(LLMRouteError):
    """Raised when a selected route cannot safely provide a requested feature."""


class LLMBatchUnsupportedError(LLMCapabilityError):
    """Raised while batch support remains quarantined pending contract tests."""


@dataclass(frozen=True)
class ModelRoute:
    """One explicit model-to-provider route.

    ``thinking_policy`` is one of:
      * ``toggle_default_off``: send an explicit enabled/disabled body field;
      * ``always_on``: the model always reasons and cannot be disabled.

    Batch is a client capability, not just a provider claim.  It remains false
    until the repository's upload/status/result contract is integration-tested.
    """

    model: str
    provider: Literal["deepseek", "moonshot", "ai_gateway", "openai"]
    api_key_env: str
    base_url: str
    thinking_policy: Literal["toggle_default_off", "always_on"]
    supports_vision: bool = False
    supports_batch: bool = False


MODEL_ROUTES: dict[str, ModelRoute] = {
    DEEPSEEK_FLASH_MODEL: ModelRoute(
        model=DEEPSEEK_FLASH_MODEL,
        provider="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        base_url=DEEPSEEK_BASE_URL,
        thinking_policy="toggle_default_off",
    ),
    DEEPSEEK_PRO_MODEL: ModelRoute(
        model=DEEPSEEK_PRO_MODEL,
        provider="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        base_url=DEEPSEEK_BASE_URL,
        thinking_policy="toggle_default_off",
    ),
    KIMI_K26_MODEL: ModelRoute(
        model=KIMI_K26_MODEL,
        provider="moonshot",
        api_key_env="MOONSHOT_API_KEY",
        base_url=MOONSHOT_BASE_URL,
        thinking_policy="toggle_default_off",
        supports_vision=True,
    ),
    KIMI_K26_GATEWAY_MODEL: ModelRoute(
        model=KIMI_K26_GATEWAY_MODEL,
        provider="ai_gateway",
        api_key_env="AI_GATEWAY_API_KEY",
        base_url=AI_GATEWAY_BASE_URL,
        thinking_policy="toggle_default_off",
        # Gateway multimodal calls remain quarantined until we have a tested,
        # conservative image-token estimator for that route.  The direct
        # Moonshot estimator is the only pre-spend source of truth today.
        supports_vision=False,
    ),
    KIMI_K3_MODEL: ModelRoute(
        model=KIMI_K3_MODEL,
        provider="moonshot",
        api_key_env="MOONSHOT_API_KEY",
        base_url=MOONSHOT_BASE_URL,
        thinking_policy="always_on",
        supports_vision=True,
    ),
    KIMI_K3_GATEWAY_MODEL: ModelRoute(
        model=KIMI_K3_GATEWAY_MODEL,
        provider="ai_gateway",
        api_key_env="AI_GATEWAY_API_KEY",
        base_url=AI_GATEWAY_BASE_URL,
        thinking_policy="always_on",
        supports_vision=False,
    ),
    OPENAI_LUNA_MODEL: ModelRoute(
        model=OPENAI_LUNA_MODEL,
        provider="openai",
        api_key_env="OPENAI_API_KEY",
        base_url=OPENAI_BASE_URL,
        # The compatibility client maps disabled/enabled to explicit OpenAI
        # reasoning efforts. It never sends the DeepSeek `thinking` body.
        thinking_policy="toggle_default_off",
        # Although the model accepts images, visual input remains quarantined
        # until this router has an OpenAI-specific image-token estimator.
        supports_vision=False,
    ),
}


def _validated_tier_model(
    env_name: str,
    default: str,
    allowed: set[str],
) -> str:
    """Read a logical-tier override and fail closed on an unsafe value."""
    value = os.environ.get(env_name, default).strip()
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise LLMUnsupportedRouteError(
            f"{env_name}={value!r} is not allowed for this tier. "
            f"Allowed model IDs: {choices}."
        )
    return value


# Stable logical names for call sites.  K3 is a challenger, never the default
# reasoning route.  DeepSeek Pro reasons only when create(thinking=...) enables it.
ROUTINE_MODEL = _validated_tier_model(
    "RICHMOND_LLM_ROUTINE_MODEL", DEEPSEEK_FLASH_MODEL, {DEEPSEEK_FLASH_MODEL}
)
QUALITY_MODEL = _validated_tier_model(
    "RICHMOND_LLM_QUALITY_MODEL", DEEPSEEK_PRO_MODEL, {DEEPSEEK_PRO_MODEL}
)
REASONING_MODEL = _validated_tier_model(
    "RICHMOND_LLM_REASONING_MODEL", DEEPSEEK_PRO_MODEL, {DEEPSEEK_PRO_MODEL}
)
CHALLENGER_MODEL = _validated_tier_model(
    "RICHMOND_LLM_CHALLENGER_MODEL",
    KIMI_K3_MODEL,
    {KIMI_K3_MODEL, KIMI_K3_GATEWAY_MODEL},
)
VISION_MODEL = _validated_tier_model(
    "RICHMOND_LLM_VISION_MODEL",
    KIMI_K26_MODEL,
    {KIMI_K26_MODEL},
)
DEFAULT_MODEL = ROUTINE_MODEL

MODEL_MAP: dict[str, str] = {
    "routine": ROUTINE_MODEL,
    "quality": QUALITY_MODEL,
    "reasoning": REASONING_MODEL,
    "challenger": CHALLENGER_MODEL,
    "vision": VISION_MODEL,
}

_LEGACY_MODEL_PREFIXES = (
    "claude-",
    "gpt-",
    "openai/",
    "anthropic/",
)
_RETIRED_DEEPSEEK_ALIASES = {"deepseek-chat", "deepseek-reasoner"}


def _map_model(model: str) -> str:
    """Resolve a logical alias to one exact, configured model ID."""
    requested = (model or "").strip()
    resolved = MODEL_MAP.get(requested, requested)
    if resolved in MODEL_ROUTES:
        return resolved
    if requested in _RETIRED_DEEPSEEK_ALIASES:
        raise LLMUnsupportedRouteError(
            f"Model alias {requested!r} is retired. Use ROUTINE_MODEL for "
            "DeepSeek V4 Flash or REASONING_MODEL with "
            "thinking={'type': 'enabled'} for explicit reasoning."
        )
    if requested.startswith(_LEGACY_MODEL_PREFIXES):
        raise LLMUnsupportedRouteError(
            f"Chat model {requested!r} has no configured route. OpenAI and "
            "Anthropic chat are not automatic fallbacks; benchmark and add an "
            "explicit ModelRoute before using one."
        )
    choices = ", ".join(sorted(MODEL_ROUTES))
    raise LLMUnsupportedRouteError(
        f"Unknown LLM model/route {requested!r}. Configured model IDs: {choices}; "
        f"logical aliases: {', '.join(sorted(MODEL_MAP))}."
    )


def get_model_route(model: str) -> ModelRoute:
    """Return the validated route for a logical alias or exact model ID."""
    return MODEL_ROUTES[_map_model(model)]


def _resolve_api_key(route: ModelRoute) -> str:
    """Resolve only the credential owned by the selected provider."""
    key = os.environ.get(route.api_key_env, "").strip()
    if not key:
        raise LLMProviderConfigurationError(
            f"{route.api_key_env} is required for model {route.model!r} via "
            f"provider {route.provider!r}. No cross-provider key fallback is used."
        )
    return key


# ---------------------------------------------------------------------------
# Anthropic-compatible response shapes
# ---------------------------------------------------------------------------


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class LLMContentBlock:
    text: str | None = None
    type: str = "text"
    input: dict[str, Any] | None = None
    name: str | None = None
    id: str | None = None


@dataclass
class LLMResponse:
    content: list[LLMContentBlock] = field(default_factory=list)
    model: str = ""
    usage: LLMUsage = field(default_factory=LLMUsage)
    stop_reason: str | None = None


_FINISH_REASON_MAP: dict[str, str] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "end_turn",
}


def _map_stop_reason(finish_reason: str | None) -> str | None:
    if finish_reason is None:
        return None
    return _FINISH_REASON_MAP.get(finish_reason, finish_reason)


_PASSTHROUGH_CREATE_KWARGS = {
    "frequency_penalty",
    "n",
    "parallel_tool_calls",
    "presence_penalty",
    "reasoning_effort",
    "response_format",
    "seed",
    "top_p",
    "user",
}

_OPENAI_REASONING_EFFORTS: dict[str, frozenset[str]] = {
    OPENAI_LUNA_MODEL: frozenset({"none", "low", "medium", "high", "xhigh", "max"}),
}
_OPENAI_DISABLED_REASONING_EFFORT: dict[str, str] = {
    OPENAI_LUNA_MODEL: "none",
}


def _thinking_type(value: Any, *, route: ModelRoute) -> Literal["enabled", "disabled"]:
    """Normalize the Anthropic-style thinking argument for one route."""
    if value is None:
        return "enabled" if route.thinking_policy == "always_on" else "disabled"
    if isinstance(value, bool):
        kind = "enabled" if value else "disabled"
    elif isinstance(value, dict):
        extra_keys = set(value) - {"type"}
        if extra_keys:
            raise LLMCapabilityError(
                "Only thinking={'type': 'enabled'|'disabled'} is supported by "
                f"the OpenAI-compatible router; unsupported keys: {sorted(extra_keys)}."
            )
        kind = str(value.get("type", "")).lower()
    else:
        raise LLMCapabilityError(
            "thinking must be None, bool, or {'type': 'enabled'|'disabled'}."
        )
    if kind not in {"enabled", "disabled"}:
        raise LLMCapabilityError(
            "thinking.type must be exactly 'enabled' or 'disabled'."
        )
    if route.thinking_policy == "always_on" and kind == "disabled":
        raise LLMCapabilityError(
            f"{route.model} is an always-thinking challenger and cannot be used "
            "as a non-thinking route."
        )
    return kind  # type: ignore[return-value]


def _is_forced_tool_choice(tool_choice: dict[str, Any] | str | None) -> bool:
    if tool_choice is None:
        return False
    if isinstance(tool_choice, str):
        return tool_choice not in {"auto", "none"}
    if isinstance(tool_choice, dict) and tool_choice.get("type") in {"auto", "none"}:
        return False
    return True


def _estimate_input_tokens(
    system: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    route: ModelRoute | None = None,
    api_key: str | None = None,
    openai_messages: list[dict[str, Any]] | None = None,
    translated_tools: list[dict[str, Any]] | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> int:
    """Conservative preflight estimate; actual provider usage drives the ledger.

    Base64 image bytes are not text tokens. For direct Moonshot vision calls,
    use the provider's token-estimation endpoint and add a 10% + 64 token
    safety margin. Gateway vision remains quarantined because it cannot use
    that provider-specific estimator reliably.
    """
    has_visual_input = any(
        isinstance(message.get("content"), list)
        and any(
            isinstance(block, dict)
            and block.get("type") in {"image_url", "video_url"}
            for block in message["content"]
        )
        for message in messages
    )
    if has_visual_input:
        if route is None or route.provider != "moonshot" or not api_key:
            raise LLMCapabilityError(
                "Vision preflight requires the direct Moonshot route so token "
                "usage can be estimated before spending."
            )
        # Moonshot documents only ``model`` and ``messages`` for this
        # endpoint.  Tool schemas are therefore budgeted locally instead of
        # sending an undocumented ``tools`` field that may be rejected.
        payload: dict[str, Any] = {
            "model": route.model,
            "messages": openai_messages or messages,
        }
        request = urllib.request.Request(
            "https://api.moonshot.ai/v1/tokenizers/estimate-token-count",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read())
            raw_estimated = result["data"]["total_tokens"]
            if (
                isinstance(raw_estimated, bool)
                or not isinstance(raw_estimated, int)
                or raw_estimated <= 0
            ):
                raise TypeError(
                    "Moonshot token estimator returned a non-positive integer"
                )
            estimated = raw_estimated
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LLMCapabilityError(
                "Moonshot vision token estimation failed; refusing an "
                "unbudgeted multimodal request."
            ) from exc
        local_budget_payload: dict[str, Any] = {}
        if translated_tools:
            local_budget_payload["tools"] = translated_tools
        if request_metadata:
            local_budget_payload["request_metadata"] = request_metadata
        local_tokens = 0
        if local_budget_payload:
            local_tokens = len(
                json.dumps(
                    local_budget_payload,
                    ensure_ascii=False,
                    default=str,
                ).encode("utf-8")
            )
            # Tool schemas and request metadata (including JSON schemas) are
            # excluded from Moonshot's documented estimator input. One token
            # per UTF-8 byte is a conservative tokenizer-independent ceiling;
            # the fixed allowance covers provider framing.
            local_tokens += 256
        return max(1, math.ceil((estimated + local_tokens) * 1.10) + 64)

    payload = {
        "system": system,
        "messages": messages,
        "tools": translated_tools if translated_tools is not None else (tools or []),
        "request_metadata": request_metadata or {},
    }
    # Byte length is a deliberately conservative upper bound for byte-fallback
    # tokenizers and avoids authorizing a request on the usual-but-not-guaranteed
    # "three characters per token" heuristic.  The fixed allowance covers chat
    # template/role framing that is not visible in the serialized payload.
    payload_bytes = len(
        json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    )
    return max(1, payload_bytes + 256)


def _validate_message_content(
    route: ModelRoute,
    messages: list[dict[str, Any]],
) -> None:
    """Enforce modality boundaries before handing content to Chat Completions."""
    for message in messages:
        content = message.get("content")
        if content is None or isinstance(content, str):
            continue
        if not isinstance(content, list):
            raise LLMCapabilityError(
                "Message content must be text or an OpenAI-format content-block list."
            )
        for block in content:
            if isinstance(block, str):
                continue
            if not isinstance(block, dict):
                raise LLMCapabilityError("Message content blocks must be dictionaries.")
            block_type = block.get("type")
            if block_type == "document":
                raise LLMCapabilityError(
                    "Anthropic document/PDF blocks are quarantined: this router does "
                    "not silently translate them into Chat Completions input. Convert "
                    "the source to a verified image_url/file workflow first."
                )
            if block_type == "image":
                raise LLMCapabilityError(
                    "Anthropic image blocks are unsupported. Use an OpenAI-format "
                    "{'type': 'image_url', 'image_url': {...}} block on VISION_MODEL."
                )
            if block_type in {"image_url", "video_url"}:
                if not route.supports_vision:
                    raise LLMCapabilityError(
                        f"Model {route.model!r} is text-only in this router; select "
                        "VISION_MODEL for image/video input."
                    )
                continue
            if block_type == "text":
                continue
            raise LLMCapabilityError(
                f"Unsupported message content block type {block_type!r}."
            )


def _usage_attr(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _valid_usage_int(value: Any, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"usage.{field} must be an integer")
    if value < 0 or (positive and value == 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"usage.{field} must be {qualifier}")
    return value


def _validated_usage_tokens(usage: Any) -> tuple[int, int, int, int]:
    """Validate provider-reported usage before releasing any budget ceiling.

    Every non-empty chat request has prompt framing, so a zero prompt count is
    treated as an accounting contract failure.  Optional cache fields must be
    sane and cannot exceed the total prompt count.  If duplicate compatible
    fields disagree, the smaller cache count is used because it produces the
    more conservative cost.
    """
    if usage is None:
        raise ValueError("response omitted usage")
    input_tokens = _valid_usage_int(
        _usage_attr(usage, "prompt_tokens"),
        "prompt_tokens",
        positive=True,
    )
    output_tokens = _valid_usage_int(
        _usage_attr(usage, "completion_tokens"),
        "completion_tokens",
    )

    cache_counts: list[int] = []
    for name in ("prompt_cache_hit_tokens", "cached_tokens"):
        value = _usage_attr(usage, name)
        if value is not None:
            cache_counts.append(_valid_usage_int(value, name))
    details = _usage_attr(usage, "prompt_tokens_details")
    cache_write_tokens = 0
    if details is not None:
        value = _usage_attr(details, "cached_tokens")
        if value is not None:
            cache_counts.append(
                _valid_usage_int(value, "prompt_tokens_details.cached_tokens")
            )
        value = _usage_attr(details, "cache_write_tokens")
        if value is not None:
            cache_write_tokens = _valid_usage_int(
                value, "prompt_tokens_details.cache_write_tokens"
            )
    if any(value > input_tokens for value in cache_counts):
        raise ValueError("reported cache-read tokens exceed prompt_tokens")
    cache_read_tokens = min(cache_counts, default=0)
    if cache_read_tokens + cache_write_tokens > input_tokens:
        raise ValueError(
            "reported cache-read and cache-write tokens exceed prompt_tokens"
        )
    return input_tokens, output_tokens, cache_read_tokens, cache_write_tokens


class LLMClient:
    """Anthropic-shaped client with explicit, lazy OpenAI-compatible routing.

    ``api_key`` remains available for tests and legacy direct construction.  To
    prevent a key being sent to the wrong host, providing it without ``provider``
    pins the client to DeepSeek.  Normal production use should omit both and let
    the selected route resolve its provider-specific environment variable.
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 60.0,
        # Provider SDK retries can create multiple billable generations while
        # this router reserves and logs only one.  Keep one SDK call equal to
        # one paid attempt; higher-level callers may retry explicitly and will
        # pass through a fresh budget preflight each time.
        max_retries: int = 0,
        *,
        provider: str | None = None,
    ):
        known_providers = {route.provider for route in MODEL_ROUTES.values()}
        if provider is not None and provider not in known_providers:
            raise LLMProviderConfigurationError(
                f"Unknown provider {provider!r}; configured providers: "
                f"{', '.join(sorted(known_providers))}."
            )
        if api_key and provider is None:
            provider = "deepseek"
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or max_retries != 0
        ):
            raise ValueError(
                "LLMClient max_retries must be 0; retrying one reserved SDK "
                "request can create unaccounted billable generations"
            )
        self._api_key_override = api_key
        self._pinned_provider = provider
        self._timeout = timeout
        self._max_retries = 0
        self._clients: dict[str, OpenAI] = {}
        self.timeout = timeout

    @property
    def messages(self) -> "LLMClient":
        return self

    def _client_for_route(self, route: ModelRoute) -> OpenAI:
        if self._pinned_provider and route.provider != self._pinned_provider:
            raise LLMProviderConfigurationError(
                f"Client is pinned to provider {self._pinned_provider!r}, but "
                f"model {route.model!r} requires {route.provider!r}."
            )
        client = self._clients.get(route.provider)
        if client is not None:
            return client
        key = self._api_key_override or _resolve_api_key(route)
        client = OpenAI(
            api_key=key,
            base_url=route.base_url,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )
        self._clients[route.provider] = client
        return client

    def create(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1024,
        system: Any = None,
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | str | None = None,
        thinking: Any = None,
        stop: str | list[str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Create one completion after validating route, capability, and budget."""
        import llm_budget_lock

        mapped_model = _map_model(model)
        route = MODEL_ROUTES[mapped_model]
        thinking_kind = _thinking_type(thinking, route=route)
        _validate_message_content(route, messages)
        if system is not None:
            _validate_message_content(route, [{"content": system}])

        unknown_kwargs = set(kwargs) - _PASSTHROUGH_CREATE_KWARGS - {"extra_body"}
        if unknown_kwargs:
            raise TypeError(
                "Unsupported LLM create parameter(s): "
                f"{', '.join(sorted(unknown_kwargs))}. Add an explicit, tested "
                "translation before passing provider-specific parameters."
            )

        completion_count = kwargs.get("n")
        if completion_count is not None and (
            isinstance(completion_count, bool)
            or not isinstance(completion_count, int)
            or completion_count != 1
        ):
            raise LLMCapabilityError(
                "The router fixes n at exactly 1; multiple completions would multiply output "
                "spend beyond this router's one-response budget reservation."
            )

        if thinking_kind == "enabled" and tools:
            raise LLMCapabilityError(
                f"{mapped_model} thinking mode with tools is quarantined because "
                "this compatibility wrapper cannot replay provider "
                "reasoning_content across tool turns. Disable thinking or use a "
                "provider-native agent loop that preserves the complete assistant "
                "message."
            )
        caller_reasoning_effort = kwargs.get("reasoning_effort")
        provider_reasoning_effort = caller_reasoning_effort
        if route.provider == "openai":
            supported_efforts = _OPENAI_REASONING_EFFORTS[mapped_model]
            disabled_effort = _OPENAI_DISABLED_REASONING_EFFORT[mapped_model]
            if provider_reasoning_effort is None:
                provider_reasoning_effort = (
                    "low" if thinking_kind == "enabled" else disabled_effort
                )
            if provider_reasoning_effort not in supported_efforts:
                choices = ", ".join(sorted(supported_efforts))
                raise LLMCapabilityError(
                    f"{mapped_model} supports reasoning_effort values: {choices}."
                )
            if (
                thinking_kind == "disabled"
                and provider_reasoning_effort != disabled_effort
            ):
                raise LLMCapabilityError(
                    f"{mapped_model} with thinking disabled requires "
                    f"reasoning_effort={disabled_effort!r}."
                )
        elif caller_reasoning_effort is not None:
            if thinking_kind != "enabled":
                raise LLMCapabilityError(
                    "reasoning_effort is allowed only when thinking is explicitly enabled."
                )
            if mapped_model in {DEEPSEEK_FLASH_MODEL, DEEPSEEK_PRO_MODEL}:
                supported_efforts = {"high", "max"}
            elif mapped_model in {KIMI_K3_MODEL, KIMI_K3_GATEWAY_MODEL}:
                supported_efforts = {"low", "high", "max"}
            else:
                supported_efforts = set()
            if caller_reasoning_effort not in supported_efforts:
                choices = ", ".join(sorted(supported_efforts)) or "none"
                raise LLMCapabilityError(
                    f"{mapped_model} supports reasoning_effort values: {choices}."
                )
        if temperature is not None and thinking_kind == "enabled":
            raise LLMCapabilityError(
                f"temperature is not a meaningful control for {mapped_model} in "
                "thinking mode; omit it or disable thinking."
            )
        if temperature is not None and route.provider == "openai":
            raise LLMCapabilityError(
                f"{mapped_model} benchmark routes quarantine temperature; omit it "
                "so reasoning-mode compatibility cannot silently change."
            )
        if mapped_model in {KIMI_K26_MODEL, KIMI_K26_GATEWAY_MODEL}:
            expected = 1.0 if thinking_kind == "enabled" else 0.6
            if temperature is not None and temperature != expected:
                raise LLMCapabilityError(
                    f"{mapped_model} fixes temperature at {expected} in "
                    f"{thinking_kind} mode; omit temperature or pass {expected}."
                )
        if mapped_model in {
            KIMI_K26_MODEL,
            KIMI_K26_GATEWAY_MODEL,
            KIMI_K3_MODEL,
            KIMI_K3_GATEWAY_MODEL,
        }:
            fixed_kimi_parameters = {
                "top_p": 0.95,
                "n": 1,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
            }
            for parameter, expected_value in fixed_kimi_parameters.items():
                actual = kwargs.get(parameter)
                if actual is not None and actual != expected_value:
                    raise LLMCapabilityError(
                        f"{mapped_model} fixes {parameter} at {expected_value}; "
                        "omit it or pass the fixed value."
                    )

        if thinking_kind == "enabled":
            ignored_sampling = {
                key for key in ("top_p", "presence_penalty", "frequency_penalty")
                if kwargs.get(key) is not None
            }
            if ignored_sampling and route.provider == "deepseek":
                raise LLMCapabilityError(
                    f"{mapped_model} ignores sampling controls in thinking mode: "
                    f"{', '.join(sorted(ignored_sampling))}. Omit them."
                )

        response_format = kwargs.get("response_format")
        if response_format is not None:
            if not isinstance(response_format, dict):
                raise LLMCapabilityError("response_format must be an object.")
            format_type = response_format.get("type")
            if mapped_model in {DEEPSEEK_FLASH_MODEL, DEEPSEEK_PRO_MODEL}:
                supported_formats = {"text", "json_object"}
            elif mapped_model in {KIMI_K26_MODEL, KIMI_K26_GATEWAY_MODEL}:
                supported_formats = {"text", "json_object"}
            else:
                supported_formats = {"text", "json_object", "json_schema"}
            if format_type not in supported_formats:
                raise LLMCapabilityError(
                    f"{mapped_model} does not support response_format type "
                    f"{format_type!r}; supported: {', '.join(sorted(supported_formats))}."
                )

        openai_messages: list[dict[str, Any]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(dict(msg) for msg in messages)

        create_kwargs: dict[str, Any] = {
            "model": mapped_model,
            "messages": openai_messages,
        }
        if route.provider == "openai":
            create_kwargs["max_completion_tokens"] = max_tokens
            create_kwargs["reasoning_effort"] = provider_reasoning_effort
        else:
            create_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            create_kwargs["temperature"] = temperature
        if stop is not None:
            create_kwargs["stop"] = stop

        translated_tools: list[dict[str, Any]] | None = None
        if tools:
            translated_tools = _translate_tools_to_openai(tools)
            if translated_tools:
                create_kwargs["tools"] = translated_tools
        if tool_choice is not None:
            translated_choice = _translate_tool_choice_to_openai(tool_choice)
            if translated_choice is not None:
                create_kwargs["tool_choice"] = translated_choice

        for key in _PASSTHROUGH_CREATE_KWARGS:
            if key in kwargs and kwargs[key] is not None:
                create_kwargs[key] = kwargs[key]

        caller_extra_body = kwargs.get("extra_body")
        if caller_extra_body is not None and not isinstance(caller_extra_body, dict):
            raise TypeError("extra_body must be a dict when provided.")
        if caller_extra_body:
            raise LLMCapabilityError(
                "Caller-supplied extra_body is quarantined because the OpenAI "
                "SDK merges it after routed model, token, tool, and sampling "
                "fields, which could bypass capability and budget enforcement."
            )
        extra_body: dict[str, Any] = {}
        if (
            route.thinking_policy == "toggle_default_off"
            and route.provider != "openai"
        ):
            extra_body["thinking"] = {"type": thinking_kind}
        if extra_body:
            create_kwargs["extra_body"] = extra_body

        # The Moonshot vision estimator receives the full prompt. Honor the
        # hard kill switch before constructing a client or transmitting that
        # provider-bound preflight request.
        llm_budget_lock._assert_api_unlocked()

        # Resolve the selected provider's own credential before touching the
        # budget database. OpenAI-compatible client construction performs no API call.
        sdk_client = self._client_for_route(route)
        provider_api_key = self._api_key_override or _resolve_api_key(route)
        request_metadata = {
            key: value
            for key, value in create_kwargs.items()
            if key not in {
                "model", "messages", "tools", "max_tokens",
                "max_completion_tokens",
            }
        }
        estimated_input = _estimate_input_tokens(
            system,
            messages,
            tools,
            route=route,
            api_key=provider_api_key,
            openai_messages=openai_messages,
            translated_tools=translated_tools,
            request_metadata=request_metadata,
        )
        reservation_id = llm_budget_lock._enforce_caps_pre_call(
            mapped_model,
            estimated_input_tokens=estimated_input,
            max_output_tokens=max_tokens,
        )

        raw = sdk_client.chat.completions.create(**create_kwargs)
        raw_usage = getattr(raw, "usage", None)
        try:
            (
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
            ) = (
                _validated_usage_tokens(raw_usage)
            )
        except ValueError as exc:
            # The provider may have billed this response, but without valid
            # usage we cannot safely lower either the monthly or event ceiling.
            # Leave both reservations conservative and stop this process from
            # authorizing another paid request.
            llm_budget_lock._invalidate_mtd_cache(poison=True)
            raise llm_budget_lock.LLMBudgetAccountingError(
                f"{mapped_model} returned invalid cost usage: {exc}. The "
                "request ceiling remains reserved."
            ) from exc
        usage = LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read_tokens,
            cache_creation_input_tokens=cache_write_tokens,
        )
        returned_model = getattr(raw, "model", None) or mapped_model
        cost = llm_budget_lock._approx_cost(
            mapped_model,
            usage.input_tokens,
            usage.output_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens,
            cache_write_input_tokens=usage.cache_creation_input_tokens,
        )
        caller = llm_budget_lock._detect_caller()
        settlement_metadata = {
            "provider": route.provider,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_input_tokens": usage.cache_read_input_tokens,
            "cache_write_input_tokens": usage.cache_creation_input_tokens,
            "thinking": thinking_kind,
            "provider_model": returned_model,
        }
        settled = llm_budget_lock._settle_cost_reservation(
            reservation_id,
            cost,
            metadata=settlement_metadata,
        )
        logged = llm_budget_lock._log_cost(
            mapped_model,
            usage.input_tokens,
            usage.output_tokens,
            cost,
            caller,
            extra={
                "provider": route.provider,
                "cache_read_input_tokens": usage.cache_read_input_tokens,
                "cache_write_input_tokens": usage.cache_creation_input_tokens,
                "thinking": thinking_kind,
                "provider_model": returned_model,
                "reservation_id": str(reservation_id),
            },
        )
        if settled and logged:
            try:
                llm_budget_lock._settle_process_spend(reservation_id, cost)
            except Exception as exc:
                llm_budget_lock._invalidate_mtd_cache(poison=True)
                raise llm_budget_lock.LLMBudgetAccountingError(
                    "Durable LLM accounting succeeded but the process event "
                    "ceiling could not be reconciled; refusing further spend."
                ) from exc
            llm_budget_lock._add_cached_mtd_spend(cost)
        else:
            llm_budget_lock._invalidate_mtd_cache(poison=True)
            failed_parts = []
            if not settled:
                failed_parts.append("atomic reservation settlement")
            if not logged:
                failed_parts.append("cost journal write")
            warnings.warn(
                f"LLM cost ${cost:.6f} for {mapped_model} could not be persisted; "
                f"failed: {', '.join(failed_parts)}. The in-process event cap "
                "still includes it and further paid calls are blocked.",
                RuntimeWarning,
                stacklevel=2,
            )

        choice = raw.choices[0]
        message = choice.message

        content_blocks: list[LLMContentBlock] = []
        text_output = getattr(message, "content", None) or ""
        if isinstance(text_output, str):
            text_output = text_output.strip()
        if text_output:
            content_blocks.append(LLMContentBlock(type="text", text=str(text_output)))

        for tool_call in getattr(message, "tool_calls", None) or []:
            arguments = getattr(tool_call.function, "arguments", "")
            try:
                parsed_input = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                parsed_input = {"_raw": arguments}
            content_blocks.append(
                LLMContentBlock(
                    type="tool_use",
                    id=getattr(tool_call, "id", None),
                    name=getattr(tool_call.function, "name", None),
                    input=parsed_input,
                )
            )

        response = LLMResponse(
            content=content_blocks,
            model=returned_model,
            usage=usage,
            stop_reason=_map_stop_reason(getattr(choice, "finish_reason", None)),
        )
        if thinking_kind == "enabled" and not content_blocks:
            finish_reason = getattr(choice, "finish_reason", None)
            raise LLMCapabilityError(
                f"{mapped_model} returned no final answer after thinking "
                f"(finish_reason={finish_reason!r}). The hidden reasoning trace "
                "is never substituted for final content; retry with a larger "
                "output ceiling or a bounded non-thinking pass."
            )
        return response

    # Batch is deliberately unavailable until provider upload/status/result
    # semantics and tool-call reconstruction are covered by contract tests.
    def batch_prepare_requests(self, requests: list[dict[str, Any]]) -> str:
        models = {
            _map_model((req.get("params") or req.get("body") or {}).get("model", DEFAULT_MODEL))
            for req in requests
        } or {DEFAULT_MODEL}
        detail = ", ".join(sorted(models))
        raise LLMBatchUnsupportedError(
            f"Batch API is quarantined for configured route(s): {detail}. "
            "Use synchronous calls until batch contract tests are implemented."
        )

    def batch_upload(self, jsonl_content: str, filename: str = "batch_requests.jsonl") -> str:
        raise LLMBatchUnsupportedError(
            "Batch upload is quarantined; no configured provider route supports it."
        )

    def batch_create(self, input_file_id: str) -> str:
        raise LLMBatchUnsupportedError(
            "Batch creation is quarantined; no configured provider route supports it."
        )

    def batch_status(self, batch_id: str) -> dict[str, Any]:
        raise LLMBatchUnsupportedError(
            "Batch status is quarantined; no configured provider route supports it."
        )

    def batch_download_results(self, batch_id: str) -> list[dict[str, Any]]:
        raise LLMBatchUnsupportedError(
            "Batch result collection is quarantined; no configured provider route supports it."
        )


def _translate_tools_to_openai(
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Translate Anthropic tool schemas while passing OpenAI schemas through."""
    translated: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") == "function" and "function" in tool:
            translated.append(tool)
            continue
        name = tool.get("name", "")
        if not name:
            raise LLMCapabilityError("Every tool requires a non-empty name.")
        translated.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema")
                    or tool.get("parameters", {}),
                },
            }
        )
    return translated


def _translate_tool_choice_to_openai(
    tool_choice: dict[str, Any] | str,
) -> dict[str, Any] | str | None:
    if isinstance(tool_choice, str):
        if tool_choice not in {"auto", "none", "required"}:
            raise LLMCapabilityError(f"Unsupported tool_choice string {tool_choice!r}.")
        return tool_choice
    choice_type = tool_choice.get("type", "")
    if choice_type == "tool":
        name = tool_choice.get("name", "")
        if not name:
            raise LLMCapabilityError("Forced Anthropic tool_choice requires a name.")
        return {"type": "function", "function": {"name": name}}
    if choice_type == "function":
        return tool_choice
    if choice_type == "any":
        return "required"
    if choice_type in {"auto", "none"}:
        return choice_type
    raise LLMCapabilityError(f"Unsupported Anthropic tool_choice {tool_choice!r}.")
