"""
Thin translation layer: Anthropic-compatible interface over DeepSeek API.

DeepSeek uses an OpenAI-compatible API. This wrapper accepts Anthropic-style
parameters (system=, messages=[...], thinking={"type":"disabled"}, etc.),
translates them to the OpenAI format, and wraps the response back into
Anthropic-compatible shape so existing call sites change minimally.

Usage (replaces `import anthropic; client = anthropic.Anthropic()`):

    from llm_client import LLMClient
    client = LLMClient(timeout=60.0)
    response = client.messages.create(
        model="deepseek-v4-pro",
        max_tokens=1200,
        temperature=0,
        system="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Hello"}],
    )
    text = response.content[0].text
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    stop_reason = response.stop_reason
    model_used = response.model

Reads DEEPSEEK_API_KEY from environment. Falls back to the OPENAI_API_KEY
env var if DEEPSEEK_API_KEY is not set (for CI compatibility).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI


# ── Model mapping ──────────────────────────────────────────────

DEFAULT_MODEL = "deepseek-v4-pro"  # Primary model — 1M context, replaces claude-sonnet-5

MODEL_MAP: dict[str, str] = {
    "claude-sonnet-5": DEFAULT_MODEL,
    "claude-sonnet-4-5": DEFAULT_MODEL,
    "claude-sonnet-4": DEFAULT_MODEL,
    "claude-sonnet": DEFAULT_MODEL,
    "claude-haiku-4-5": DEFAULT_MODEL,
    "claude-haiku": DEFAULT_MODEL,
    "claude-3-5-sonnet": DEFAULT_MODEL,
    "claude-3-5-haiku": DEFAULT_MODEL,
    "claude-opus": DEFAULT_MODEL,
    "claude-opus-4": DEFAULT_MODEL,
    "claude-3-opus": DEFAULT_MODEL,
    "deepseek-v4-pro": DEFAULT_MODEL,
    "deepseek-reasoner": DEFAULT_MODEL,
    "deepseek-v4-pro": DEFAULT_MODEL,
}

DEFAULT_BASE_URL = "https://api.deepseek.com"


def _resolve_api_key() -> str:
    """Resolve API key: DEEPSEEK_API_KEY first, then OPENAI_API_KEY fallback."""
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "DEEPSEEK_API_KEY not set in environment. "
            "Set it in .env or export it before running."
        )
    return key


def _map_model(model: str) -> str:
    """Map a model name through MODEL_MAP, returning the input unchanged if
    it's already a DeepSeek model or unrecognised."""
    return MODEL_MAP.get(model, model)


# ── Response shape dataclasses ──────────────────────────────────

@dataclass
class LLMUsage:
    """Token usage, mirroring Anthropic's response.usage shape."""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMContentBlock:
    """Content block, mirroring Anthropic's response.content[n] shape."""
    text: str | None = None
    type: str = "text"
    input: dict[str, Any] | None = None   # populated for tool_use blocks
    name: str | None = None                # tool name (for tool_use blocks)


@dataclass
class LLMResponse:
    """Response object mirroring Anthropic's Messages.create() return shape."""
    content: list[LLMContentBlock] = field(default_factory=list)
    model: str = ""
    usage: LLMUsage = field(default_factory=LLMUsage)
    stop_reason: str | None = None


# ── Stop reason mapping ────────────────────────────────────────

_FINISH_REASON_MAP: dict[str, str] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "end_turn",
}


def _map_stop_reason(finish_reason: str | None) -> str | None:
    """Map OpenAI finish_reason to Anthropic stop_reason."""
    if finish_reason is None:
        return None
    return _FINISH_REASON_MAP.get(finish_reason, finish_reason)


# ── Client ─────────────────────────────────────────────────────

class LLMClient:
    """Anthropic-compatible client backed by DeepSeek (OpenAI SDK).

    Constructor matches anthropic.Anthropic():
        LLMClient(api_key=None, timeout=60.0, max_retries=2)

    Call pattern matches anthropic.Anthropic().messages.create():
        client.messages.create(
            model=...,
            max_tokens=...,
            system=...,
            messages=[...],
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ):
        resolved_key = api_key or _resolve_api_key()
        self._client = OpenAI(
            api_key=resolved_key,
            base_url=DEFAULT_BASE_URL,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.timeout = timeout

    @property
    def messages(self) -> "LLMClient":
        """Property so `client.messages.create(...)` reads naturally."""
        return self

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        system: str | None = None,
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        thinking: Any = None,          # accepted and discarded (Anthropic-specific)
        stop: str | list[str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call the LLM. Signature is a superset of Anthropic's Messages.create().

        ``thinking`` is silently discarded (DeepSeek has no equivalent).
        ``system`` is prepended as a role:system message in the OpenAI request.
        """
        import llm_budget_lock  # noqa: F401  # ensure budget gate is loaded

        mapped_model = _map_model(model)

        # Build OpenAI-format message list
        openai_messages: list[dict[str, Any]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        for msg in messages:
            openai_messages.append(dict(msg))

        # Build keyword arguments for the OpenAI call
        create_kwargs: dict[str, Any] = {
            "model": mapped_model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            create_kwargs["temperature"] = temperature
        if stop is not None:
            create_kwargs["stop"] = stop

        # Tool-use translation: Anthropic tools → OpenAI tools
        if tools:
            openai_tools = _translate_tools_to_openai(tools)
            if openai_tools:
                create_kwargs["tools"] = openai_tools
        if tool_choice:
            openai_tool_choice = _translate_tool_choice_to_openai(tool_choice)
            if openai_tool_choice is not None:
                create_kwargs["tool_choice"] = openai_tool_choice

        # Enforce budget caps before the call
        llm_budget_lock._enforce_caps_pre_call(mapped_model)

        # ── Call DeepSeek ──────────────────────────────────
        raw = self._client.chat.completions.create(**create_kwargs)

        # ── Translate response ─────────────────────────────
        choice = raw.choices[0]
        finish_reason = choice.finish_reason
        msg = choice.message

        # Build content blocks
        content_blocks: list[LLMContentBlock] = []

        # DeepSeek v4-pro is a reasoning model: output is in `reasoning_content`
        # when thinking is used, falling back to `content` for standard chat models.
        text_output = (
            msg.content
            or getattr(msg, "reasoning_content", None)
            or ""
        ).strip()

        if text_output:
            content_blocks.append(LLMContentBlock(
                type="text",
                text=text_output,
            ))
        if msg.tool_calls:
            for tc in msg.tool_calls:
                parsed_input: dict[str, Any] = {}
                try:
                    parsed_input = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    parsed_input = {"_raw": tc.function.arguments}
                content_blocks.append(LLMContentBlock(
                    type="tool_use",
                    name=tc.function.name,
                    input=parsed_input,
                ))

        usage = LLMUsage(
            input_tokens=getattr(raw.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(raw.usage, "completion_tokens", 0) or 0,
        )

        response = LLMResponse(
            content=content_blocks,
            model=raw.model or mapped_model,
            usage=usage,
            stop_reason=_map_stop_reason(finish_reason),
        )

        # ── Log cost ───────────────────────────────────────
        try:
            cost = llm_budget_lock._approx_cost(
                mapped_model, usage.input_tokens, usage.output_tokens
            )
            llm_budget_lock._add_process_spend(cost)
            caller = llm_budget_lock._detect_caller()
            llm_budget_lock._log_cost(
                mapped_model,
                usage.input_tokens,
                usage.output_tokens,
                cost,
                caller,
            )
        except Exception:
            pass  # cost logging must never break the pipeline

        return response

    # ── Batch API helpers ──────────────────────────────────────

    def batch_prepare_requests(
        self,
        requests: list[dict[str, Any]],
    ) -> str:
        """Convert Anthropic-format batch requests to OpenAI JSONL.

        Each request dict should have:
            custom_id: str
            params: {model, messages, max_tokens, system?, tools?, tool_choice?}

        Returns JSONL string ready for file upload.
        """
        lines: list[str] = []
        for req in requests:
            custom_id = req["custom_id"]
            params = dict(req.get("params", req.get("body", {})))

            mapped_model = _map_model(params.get("model", DEFAULT_MODEL))
            openai_messages: list[dict[str, Any]] = []

            system_text = params.pop("system", None)
            if system_text:
                openai_messages.append({"role": "system", "content": system_text})

            for m in params.get("messages", []):
                openai_messages.append(dict(m))

            # Remove Anthropic-specific params
            params.pop("thinking", None)

            body: dict[str, Any] = {
                "model": mapped_model,
                "messages": openai_messages,
                "max_tokens": params.get("max_tokens", 4096),
            }

            if "temperature" in params and params["temperature"] is not None:
                body["temperature"] = params["temperature"]

            tools = params.get("tools")
            if tools:
                body["tools"] = _translate_tools_to_openai(tools)
            tool_choice = params.get("tool_choice")
            if tool_choice:
                openai_tc = _translate_tool_choice_to_openai(tool_choice)
                if openai_tc is not None:
                    body["tool_choice"] = openai_tc

            line = json.dumps({
                "custom_id": custom_id,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": body,
            }, ensure_ascii=False)
            lines.append(line)

        return "\n".join(lines)

    def batch_upload(
        self,
        jsonl_content: str,
        filename: str = "batch_requests.jsonl",
    ) -> str:
        """Upload JSONL to the API and return a file_id."""
        resp = self._client.files.create(
            file=(filename, jsonl_content.encode("utf-8")),
            purpose="batch",
        )
        return resp.id

    def batch_create(self, input_file_id: str) -> str:
        """Create a batch job from an uploaded file. Returns batch_id."""
        resp = self._client.batches.create(
            input_file_id=input_file_id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
        )
        return resp.id

    def batch_status(self, batch_id: str) -> dict[str, Any]:
        """Check batch status. Returns a dict with Anthropic-compatible keys."""
        resp = self._client.batches.retrieve(batch_id)
        counts = resp.request_counts
        return {
            "id": resp.id,
            "processing_status": resp.status,
            "request_counts": {
                "processing": counts.total - counts.completed - counts.failed,
                "succeeded": counts.completed,
                "errored": counts.failed,
                "canceled": 0,
                "expired": 0 if resp.status != "expired" else counts.total,
            },
            "created_at": str(resp.created_at),
            "ended_at": str(resp.ended_at) if resp.ended_at else None,
            "output_file_id": getattr(resp, "output_file_id", None),
        }

    def batch_download_results(self, batch_id: str) -> list[dict[str, Any]]:
        """Download and parse batch results into Anthropic-compatible result dicts.

        Each result dict has: custom_id, result.type, result.message.content,
        result.message.usage (input_tokens/output_tokens), result.message.model.
        """
        status = self.batch_status(batch_id)
        if status["processing_status"] not in ("completed", "ended"):
            return []

        output_file_id = status.get("output_file_id")
        if not output_file_id:
            return []

        content = self._client.files.content(output_file_id)
        results: list[dict[str, Any]] = []
        for line in content.text.strip().split("\n"):
            if not line.strip():
                continue
            entry = json.loads(line)
            result: dict[str, Any] = {
                "custom_id": entry.get("custom_id", ""),
                "result": {"type": "errored"},
            }
            response_body = entry.get("response") or {}
            status_code = response_body.get("status_code", 0)

            if status_code == 200 and "error" not in entry:
                body = response_body.get("body", {})
                choices = body.get("choices", [])
                choice = choices[0] if choices else {}
                msg_content = (
                    choice.get("message", {}).get("content")
                    or choice.get("message", {}).get("reasoning_content")
                    or ""
                )
                finish = choice.get("finish_reason", "stop")

                result["result"] = {
                    "type": "succeeded",
                    "message": {
                        "content": [
                            {"type": "text", "text": msg_content}
                        ],
                        "usage": {
                            "input_tokens": body.get("usage", {}).get("prompt_tokens", 0),
                            "output_tokens": body.get("usage", {}).get("completion_tokens", 0),
                        },
                        "model": body.get("model", ""),
                        "stop_reason": _map_stop_reason(finish),
                    },
                }
            else:
                error = entry.get("error") or response_body
                result["result"]["error"] = error

            results.append(result)

        return results


# ── Tool translation helpers ───────────────────────────────────

def _translate_tools_to_openai(
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Translate Anthropic-style tools to OpenAI-style tools."""
    openai_tools: list[dict[str, Any]] = []
    for tool in tools:
        # Handle Anthropic format: {"name": "...", "description": "...", "input_schema": {...}}
        # Also pass through if already in OpenAI format: {"type": "function", "function": {...}}
        if tool.get("type") == "function" and "function" in tool:
            openai_tools.append(tool)
        else:
            name = tool.get("name", "")
            desc = tool.get("description", "")
            schema = tool.get("input_schema") or tool.get("parameters", {})
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": schema,
                },
            })
    return openai_tools


def _translate_tool_choice_to_openai(
    tool_choice: dict[str, Any] | str,
) -> dict[str, Any] | str | None:
    """Translate Anthropic-style tool_choice to OpenAI-style."""
    if isinstance(tool_choice, str):
        # "auto", "none", "required"
        return tool_choice
    if isinstance(tool_choice, dict):
        tc_type = tool_choice.get("type", "")
        if tc_type == "tool":
            name = tool_choice.get("name", "")
            return {"type": "function", "function": {"name": name}}
        if tc_type == "function":
            return tool_choice  # already OpenAI format
        if tc_type == "any":
            return "required"
    # Fallback: return as-is
    return tool_choice
