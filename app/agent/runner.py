"""Single-agent runtime.

Two interchangeable paths:
- ``run_demo_agent``: deterministic policy, works offline, used for tests/eval.
- ``run_llm_agent``: OpenAI-compatible function calling, with the demo policy as
  a graceful fallback when the model errors or returns invalid JSON.

Both produce the same ``AgentResult`` contract, so the API, UI and evaluation
harness never need to know which path ran.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agent.policy import synthesize
from app.agent.prompts import SYSTEM_PROMPT, user_prompt
from app.agent.tools import ToolContext, ToolRegistry
from app.agent.validator import validate_and_repair
from app.config import Settings
from app.data.provider import normalize_symbol


REQUIRED_TOOLS = [
    "get_quote",
    "get_history",
    "compute_indicators",
    "search_news",
    "get_fundamentals",
    "get_benchmark",
]


@dataclass
class AgentResult:
    report: Dict[str, Any]
    trace: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    generated_by: str = "demo-policy"
    error: Optional[str] = None


def _trace(
    step: int,
    kind: str,
    tool: str = "",
    args: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    ok: bool = True,
    latency_ms: int = 0,
    summary: str = "",
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "step": step,
        "kind": kind,
        "tool": tool,
        "args": args or {},
        "result": result or {},
        "ok": ok,
        "latency_ms": latency_ms,
        "summary": summary,
        "error": error,
    }


def _collect_evidence(results: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    seen = set()
    for result in results.values():
        for item in result.get("evidence", []):
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            evidence.append(item)
    return evidence


def _run_tool(
    registry: ToolRegistry,
    ctx: ToolContext,
    tool: str,
    args: Dict[str, Any],
    step: int,
) -> Dict[str, Any]:
    started = time.perf_counter()
    result = registry.execute(tool, ctx, args)
    latency = int((time.perf_counter() - started) * 1000)
    result["latency_ms"] = latency
    return result


def run_demo_agent(
    provider: Any,
    stock: Dict[str, Any],
    as_of: str,
    mode: str = "demo",
) -> AgentResult:
    symbol = normalize_symbol(stock["symbol"])
    ctx = ToolContext(provider=provider, symbol=symbol, as_of=as_of, stock=stock)
    registry = ToolRegistry()
    results: Dict[str, Dict[str, Any]] = {}
    trace: List[Dict[str, Any]] = [
        _trace(
            0,
            "plan",
            summary=(
                "先取行情与日线，再计算技术指标；随后核对资讯、基本面与基准，"
                "最后生成带证据的决策卡。"
            ),
        )
    ]
    step = 1
    for tool in REQUIRED_TOOLS:
        args: Dict[str, Any] = {}
        if tool in {"get_history", "compute_indicators", "search_news", "get_benchmark"}:
            args["days"] = 120 if tool != "search_news" else 14
        result = _run_tool(registry, ctx, tool, args, step)
        results[tool] = result
        trace.append(
            _trace(
                step,
                "tool",
                tool=tool,
                args=args,
                result={
                    "ok": result.get("ok"),
                    "summary": result.get("summary"),
                    "data_quality": result.get("data_quality"),
                    "evidence_ids": [item["id"] for item in result.get("evidence", [])],
                },
                ok=bool(result.get("ok")),
                latency_ms=result.get("latency_ms", 0),
                summary=result.get("summary", ""),
                error=result.get("error"),
            )
        )
        step += 1

    evidence = _collect_evidence(results)
    raw_report = synthesize(
        symbol=symbol,
        name=stock.get("name", symbol),
        as_of=as_of,
        stock=stock,
        results=results,
        mode=mode,
    )
    report = validate_and_repair(
        raw_report,
        evidence=evidence,
        symbol=symbol,
        name=stock.get("name", symbol),
        as_of=as_of,
        generated_by=mode,
    )
    trace.append(
        _trace(
            step,
            "final",
            result={
                "action": report["action"],
                "score": report["score"],
                "confidence": report["confidence"],
                "evidence_count": len(report["evidence"]),
            },
            summary=f"生成决策卡：{report['action']} / {report['score']} 分。",
        )
    )
    return AgentResult(
        report=report,
        trace=trace,
        evidence=report["evidence"],
        generated_by=mode,
    )


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    candidate = text.strip()
    if "```" in candidate:
        blocks = candidate.split("```")
        for block in blocks:
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            if block.startswith("{"):
                candidate = block
                break
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(candidate[start : end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    # Conservative public list-price approximations, only used for display.
    pricing = {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "deepseek-chat": (0.27, 1.10),
    }
    key = model.lower().split("/")[-1]
    input_price, output_price = pricing.get(key, (0.0, 0.0))
    return round(
        prompt_tokens / 1_000_000 * input_price
        + completion_tokens / 1_000_000 * output_price,
        6,
    )


def _run_model_tool_loop(
    client: Any,
    settings: Settings,
    messages: List[Dict[str, Any]],
    registry: ToolRegistry,
    ctx: ToolContext,
    trace: List[Dict[str, Any]],
    step: int = 1,
) -> Dict[str, Any]:
    """Single model/tool loop shared by review and research profiles.

    The loop only knows about messages, tools and a context. It does not know
    whether the caller expects a decision card or a research answer; that is
    decided by the caller's finalizer after the loop returns.
    """
    results: Dict[str, Dict[str, Any]] = {}
    prompt_tokens = 0
    completion_tokens = 0

    for _ in range(settings.agent_max_steps):
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=registry.schemas(),
            tool_choice="auto",
            temperature=settings.llm_temperature,
        )
        if response.usage:
            prompt_tokens += response.usage.prompt_tokens or 0
            completion_tokens += response.usage.completion_tokens or 0

        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            return {
                "content": message.content or "",
                "results": results,
                "trace": trace,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "step": step,
                "budget_exhausted": False,
            }

        # Append the assistant message with tool calls exactly as the SDK returns it.
        messages.append(message.model_dump(exclude_none=True))
        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _run_tool(registry, ctx, name, args, step)
            results[name] = result
            trace.append(
                _trace(
                    step,
                    "tool",
                    tool=name,
                    args=args,
                    result={
                        "ok": result.get("ok"),
                        "summary": result.get("summary"),
                        "data_quality": result.get("data_quality"),
                        "evidence_ids": [item["id"] for item in result.get("evidence", [])],
                    },
                    ok=bool(result.get("ok")),
                    latency_ms=result.get("latency_ms", 0),
                    summary=result.get("summary", ""),
                    error=result.get("error"),
                )
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
            step += 1

    return {
        "content": "",
        "results": results,
        "trace": trace,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "step": step,
        "budget_exhausted": True,
    }


def run_llm_agent(
    provider: Any,
    stock: Dict[str, Any],
    as_of: str,
    settings: Settings,
) -> AgentResult:
    from openai import OpenAI

    symbol = normalize_symbol(stock["symbol"])
    ctx = ToolContext(provider=provider, symbol=symbol, as_of=as_of, stock=stock)
    registry = ToolRegistry()
    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.agent_timeout_seconds,
    )
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(symbol, stock.get("name", symbol), as_of)},
    ]
    trace: List[Dict[str, Any]] = [
        _trace(0, "plan", summary="LLM 规划：先补齐行情、指标、资讯与基本面证据，再输出 JSON 决策卡。")
    ]
    loop = _run_model_tool_loop(client, settings, messages, registry, ctx, trace)
    results = loop["results"]
    content = loop["content"]
    prompt_tokens = loop["prompt_tokens"]
    completion_tokens = loop["completion_tokens"]
    step = loop["step"]

    parsed = _extract_json(content) if content else None
    if parsed is not None:
        evidence = _collect_evidence(results)
        # If the model skipped tools, enrich with the deterministic tools before validation.
        if len(results) < 2:
            demo = run_demo_agent(provider, stock, as_of, mode="llm")
            demo.trace.insert(
                0,
                _trace(
                    0,
                    "warning",
                    summary="模型未调用足够工具，自动补齐证据后重算。",
                ),
            )
            return demo
        report = validate_and_repair(
            parsed,
            evidence=evidence,
            symbol=symbol,
            name=stock.get("name", symbol),
            as_of=as_of,
            generated_by=f"llm:{settings.llm_model}",
        )
        trace.append(
            _trace(
                step,
                "final",
                result={
                    "action": report["action"],
                    "score": report["score"],
                    "confidence": report["confidence"],
                    "evidence_count": len(report["evidence"]),
                },
                summary=f"LLM 生成决策卡：{report['action']} / {report['score']} 分。",
            )
        )
        return AgentResult(
            report=report,
            trace=trace,
            evidence=report["evidence"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=_estimate_cost(settings.llm_model, prompt_tokens, completion_tokens),
            generated_by=f"llm:{settings.llm_model}",
        )

    # Budget exhausted or the model never produced valid JSON: fall back to the
    # deterministic policy using whatever evidence has already been collected.
    for tool in REQUIRED_TOOLS:
        if tool not in results:
            results[tool] = _run_tool(registry, ctx, tool, {}, step)
            step += 1
    evidence = _collect_evidence(results)
    raw_report = synthesize(
        symbol=symbol,
        name=stock.get("name", symbol),
        as_of=as_of,
        stock=stock,
        results=results,
        mode="llm-fallback",
    )
    report = validate_and_repair(
        raw_report,
        evidence=evidence,
        symbol=symbol,
        name=stock.get("name", symbol),
        as_of=as_of,
        generated_by="llm-fallback",
    )
    trace.append(
        _trace(
            step,
            "warning",
            summary="LLM 未在步数预算内返回合法 JSON，已切换到确定性策略。",
        )
    )
    return AgentResult(
        report=report,
        trace=trace,
        evidence=report["evidence"],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=_estimate_cost(settings.llm_model, prompt_tokens, completion_tokens),
        generated_by="llm-fallback",
        error="LLM did not return valid JSON within the step budget",
    )


def run_agent(
    provider: Any,
    stock: Dict[str, Any],
    as_of: str,
    settings: Settings,
) -> AgentResult:
    if not settings.llm_enabled:
        return run_demo_agent(provider, stock, as_of, mode="demo")
    try:
        return run_llm_agent(provider, stock, as_of, settings)
    except Exception as exc:
        fallback = run_demo_agent(provider, stock, as_of, mode="demo-fallback")
        fallback.error = f"LLM path failed: {exc}"
        fallback.trace.insert(
            0,
            _trace(
                0,
                "warning",
                summary=f"LLM 调用失败，自动降级到离线策略：{exc}",
            ),
        )
        return fallback
