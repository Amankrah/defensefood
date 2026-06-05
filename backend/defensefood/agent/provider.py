"""
Provider abstraction for tool-use loops.

Two implementations — :class:`AnthropicProvider` and :class:`OpenAIProvider`
— behind a single :class:`LLMProvider` Protocol. Both run the same agentic
contract:

* Accept a system prompt + a list of typed tools (from
  :mod:`defensefood.agent.tools`).
* Drive a tool-use loop: the model proposes tool calls, the provider executes
  them (via ``invoke_tool``), and the loop continues until the model returns a
  final text response (or a budget is exhausted).
* Return :class:`AgentRun` with the full transcript, usage, cost, and tool
  trace so the runner can persist audit rows.

Prompt caching is applied to the system prompt + tool definitions on both
sides (Anthropic ``cache_control``, OpenAI now caches automatically when the
prefix is repeated).

This module intentionally does **not** know about briefs, the SSE endpoint, or
the cache. It is a low-level driver; :mod:`defensefood.agent.runner` and
:mod:`defensefood.agent.briefs` are the consumers.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol

from defensefood.agent import tools as agent_tools
from defensefood.agent.config import AgentConfig, ProviderName, Tier, get_config

logger = logging.getLogger(__name__)

# Per-million-token USD prices. Approximate — updated as providers publish new
# rates. Used for the cost ledger and budget cap.
_PRICES: dict[str, tuple[float, float]] = {
    # Anthropic Claude 4.x family.
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
    # OpenAI GPT-5 family (rough estimates; tune from billing dashboard).
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (2.50, 10.00),
}


def _usd_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    in_per_m, out_per_m = _PRICES.get(model, (3.0, 15.0))
    return tokens_in / 1_000_000 * in_per_m + tokens_out / 1_000_000 * out_per_m


# ── shared result type ────────────────────────────────────────────────────


@dataclass
class ToolTrace:
    """Single tool call + result, captured for audit."""

    name: str
    args: dict[str, Any]
    result: dict[str, Any]
    latency_ms: int


@dataclass
class AgentRun:
    """Final state of a single tool-use loop call."""

    final_text: str
    tool_traces: list[ToolTrace] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    model: str = ""
    provider: str = ""
    stop_reason: str = ""
    structured_output: Optional[dict[str, Any]] = None


# ── Protocol ──────────────────────────────────────────────────────────────


class LLMProvider(Protocol):
    """Minimal contract every provider implements."""

    name: ProviderName

    def tool_use_loop(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tool_names: list[str],
        state: Any,
        tier: Tier = "narrative",
        max_iters: int = 8,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        force_tool: Optional[str] = None,
    ) -> AgentRun: ...


# ── Anthropic ─────────────────────────────────────────────────────────────


class AnthropicProvider:
    """Anthropic Messages API + tool use."""

    name: ProviderName = "anthropic"

    def __init__(self, cfg: Optional[AgentConfig] = None) -> None:
        from anthropic import Anthropic

        self._cfg = cfg or get_config()
        if not self._cfg.have_anthropic():
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; cannot construct AnthropicProvider."
            )
        self._client = Anthropic(api_key=self._cfg.anthropic_api_key)

    def tool_use_loop(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tool_names: list[str],
        state: Any,
        tier: Tier = "narrative",
        max_iters: int = 8,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        force_tool: Optional[str] = None,
    ) -> AgentRun:
        model = self._cfg.resolve_model("anthropic", tier)
        tools_payload = agent_tools.anthropic_schemas(tool_names)

        # Cache the tool definitions: they are stable across briefs.
        # Mark the last tool with cache_control so everything up to and
        # including it is cached for ~5 minutes.
        if tools_payload:
            tools_payload[-1] = {
                **tools_payload[-1],
                "cache_control": {"type": "ephemeral"},
            }

        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_prompt}
        ]
        run = AgentRun(final_text="", model=model, provider="anthropic")

        tool_choice: dict[str, Any] = {"type": "auto"}
        if force_tool:
            tool_choice = {"type": "tool", "name": force_tool}

        for _ in range(max_iters):
            resp = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_blocks,
                tools=tools_payload,
                tool_choice=tool_choice,
                messages=messages,
            )

            run.stop_reason = getattr(resp, "stop_reason", "") or ""
            usage = getattr(resp, "usage", None)
            if usage:
                run.tokens_in += int(getattr(usage, "input_tokens", 0) or 0)
                # Cached tokens are counted but priced separately by Anthropic;
                # for budget purposes we collapse to in/out totals.
                run.tokens_in += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
                run.tokens_in += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
                run.tokens_out += int(getattr(usage, "output_tokens", 0) or 0)

            # Collect content into a message we echo back.
            assistant_blocks: list[dict[str, Any]] = []
            tool_uses: list[Any] = []
            text_chunks: list[str] = []
            for block in resp.content:
                btype = getattr(block, "type", None)
                if btype == "text":
                    text_chunks.append(block.text)
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif btype == "tool_use":
                    tool_uses.append(block)
                    assistant_blocks.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": dict(block.input or {}),
                        }
                    )
            messages.append({"role": "assistant", "content": assistant_blocks})

            if not tool_uses:
                run.final_text = "\n".join(text_chunks).strip()
                if force_tool and assistant_blocks and assistant_blocks[-1].get("type") == "tool_use":
                    # Shouldn't reach here because force_tool branch returns
                    # via the tool_uses path; defensive.
                    pass
                break

            # Execute each tool use and append a single user message with the
            # tool_result blocks.
            tool_result_blocks: list[dict[str, Any]] = []
            for tu in tool_uses:
                t0 = time.perf_counter()
                raw = agent_tools.invoke_tool(
                    tu.name, dict(tu.input or {}), state=state
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                run.tool_traces.append(
                    ToolTrace(
                        name=tu.name,
                        args=dict(tu.input or {}),
                        result=raw,
                        latency_ms=latency_ms,
                    )
                )
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(raw, ensure_ascii=False, default=str),
                        "is_error": not raw.get("ok", True),
                    }
                )

                # If we forced a particular tool, stop after the first call:
                # the structured output is now captured in the trace.
                if force_tool and tu.name == force_tool:
                    run.structured_output = raw.get("result")
                    run.final_text = ""
                    messages.append(
                        {"role": "user", "content": tool_result_blocks}
                    )
                    run.cost_usd = _usd_cost(model, run.tokens_in, run.tokens_out)
                    run.messages = messages
                    return run

            messages.append({"role": "user", "content": tool_result_blocks})

        run.cost_usd = _usd_cost(model, run.tokens_in, run.tokens_out)
        run.messages = messages
        return run


# ── OpenAI ────────────────────────────────────────────────────────────────


class OpenAIProvider:
    """OpenAI Chat Completions API + tool use."""

    name: ProviderName = "openai"

    def __init__(self, cfg: Optional[AgentConfig] = None) -> None:
        from openai import OpenAI

        self._cfg = cfg or get_config()
        if not self._cfg.have_openai():
            raise RuntimeError(
                "OPENAI_API_KEY is not set; cannot construct OpenAIProvider."
            )
        self._client = OpenAI(api_key=self._cfg.openai_api_key)

    def tool_use_loop(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tool_names: list[str],
        state: Any,
        tier: Tier = "narrative",
        max_iters: int = 8,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        force_tool: Optional[str] = None,
    ) -> AgentRun:
        model = self._cfg.resolve_model("openai", tier)
        tools_payload = agent_tools.openai_schemas(tool_names)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        run = AgentRun(final_text="", model=model, provider="openai")

        tool_choice: Any = "auto"
        if force_tool:
            tool_choice = {"type": "function", "function": {"name": force_tool}}

        for _ in range(max_iters):
            kwargs: dict[str, Any] = dict(
                model=model,
                messages=messages,
                tools=tools_payload,
                tool_choice=tool_choice,
            )
            # Some GPT-5 variants reject ``temperature``; pass only when the
            # provider accepts it. Try with temperature first; fall back if
            # the API complains (one extra round-trip in the unhappy path).
            try:
                resp = self._client.chat.completions.create(
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                    **kwargs,
                )
            except Exception as exc:
                if "temperature" in str(exc).lower() or "max_tokens" in str(exc).lower():
                    resp = self._client.chat.completions.create(**kwargs)
                else:
                    raise

            usage = getattr(resp, "usage", None)
            if usage:
                run.tokens_in += int(getattr(usage, "prompt_tokens", 0) or 0)
                run.tokens_out += int(getattr(usage, "completion_tokens", 0) or 0)

            choice = resp.choices[0]
            run.stop_reason = choice.finish_reason or ""
            msg = choice.message
            tool_calls = list(msg.tool_calls or [])

            # Echo assistant message into the transcript exactly as OpenAI expects.
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)

            if not tool_calls:
                run.final_text = (msg.content or "").strip()
                break

            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                t0 = time.perf_counter()
                raw = agent_tools.invoke_tool(
                    tc.function.name, args, state=state
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                run.tool_traces.append(
                    ToolTrace(
                        name=tc.function.name,
                        args=args,
                        result=raw,
                        latency_ms=latency_ms,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(raw, ensure_ascii=False, default=str),
                    }
                )
                if force_tool and tc.function.name == force_tool:
                    run.structured_output = raw.get("result")
                    run.final_text = ""
                    run.cost_usd = _usd_cost(model, run.tokens_in, run.tokens_out)
                    run.messages = messages
                    return run

        run.cost_usd = _usd_cost(model, run.tokens_in, run.tokens_out)
        run.messages = messages
        return run


# ── factory ───────────────────────────────────────────────────────────────


def get_provider(
    name: Optional[ProviderName] = None,
    cfg: Optional[AgentConfig] = None,
) -> LLMProvider:
    """Return a provider instance. Defaults to ``cfg.default_provider``."""
    cfg = cfg or get_config()
    target: ProviderName = name or cfg.default_provider
    if target == "anthropic":
        return AnthropicProvider(cfg)
    if target == "openai":
        return OpenAIProvider(cfg)
    raise ValueError(f"Unknown provider: {target!r}")


__all__ = [
    "AgentRun",
    "AnthropicProvider",
    "LLMProvider",
    "OpenAIProvider",
    "ToolTrace",
    "get_provider",
]
