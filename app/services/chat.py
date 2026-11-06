"""Follow-up chat over a stored report."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.config import Settings

SYSTEM = """你是 Watchtower 的复盘助手。你只能基于给定的报告上下文回答，不要编造新的价格、新闻或财务数据。
回答要短、具体，优先给出数字和失效条件；如果报告没有相关信息，直接说“报告里没有这项数据”。
"""


def _format_plan(report: Dict[str, Any]) -> str:
    plan = report.get("plan", {})
    return (
        f"入场 {plan.get('entry_low')}–{plan.get('entry_high')}，"
        f"止损 {plan.get('stop_loss')}，目标 {plan.get('target_price')}，"
        f"建议仓位 {plan.get('position_pct')}%。"
    )


def demo_answer(report: Dict[str, Any], message: str) -> str:
    text = (message or "").strip()
    if any(key in text for key in ("为什么", "依据", "理由", "逻辑")):
        points = "\n".join(f"- {item.get('text', '')}" for item in report.get("thesis", [])[:3])
        return f"核心依据有三点：\n{points}\n\n一句话：{report.get('summary', '')}"
    if any(key in text for key in ("止损", "跌破", "失效")):
        plan = report.get("plan", {})
        return (
            f"报告给出的止损位是 {plan.get('stop_loss')}。"
            f"如果收盘价有效跌破该位置，原判断失效，优先控制回撤，而不是补仓摊薄。"
        )
    if any(key in text for key in ("买", "入场", "建仓", "加仓")):
        plan = report.get("plan", {})
        return (
            f"报告的建议是“{report.get('action')}”，不是无条件买入。"
            f"若执行，参考入场区间 {plan.get('entry_low')}–{plan.get('entry_high')}，"
            f"仓位上限 {plan.get('position_pct')}%，并同步设置 {plan.get('stop_loss')} 止损。"
        )
    if any(key in text for key in ("风险", "隐患", "担心")):
        risks = "\n".join(
            f"- [{item.get('severity')}] {item.get('text')}" for item in report.get("risks", [])
        )
        return f"主要风险：\n{risks}"
    if any(key in text for key in ("目标", "止盈", "看到")):
        return f"报告的目标位是 {report.get('plan', {}).get('target_price')}。目标位不是预测，只是风险收益比的参照。"
    if any(key in text for key in ("评分", "分数", "多少分")):
        return (
            f"评分 {report.get('score')}/100，动作是 {report.get('action')}，"
            f"置信度 {report.get('confidence', 0):.0%}。评分来自趋势、动量、量能、资讯、基本面与相对强弱六类信号。"
        )
    return f"{report.get('summary', '')}\n\n{_format_plan(report)}"


def llm_answer(
    settings: Settings,
    report: Dict[str, Any],
    history: List[Dict[str, Any]],
    message: str,
) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.agent_timeout_seconds,
    )
    context = {
        "symbol": report.get("symbol"),
        "name": report.get("name"),
        "as_of": report.get("as_of"),
        "action": report.get("action"),
        "score": report.get("score"),
        "confidence": report.get("confidence"),
        "summary": report.get("summary"),
        "thesis": report.get("thesis"),
        "risks": report.get("risks"),
        "plan": report.get("plan"),
        "data_quality": report.get("data_quality"),
    }
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "system",
            "content": "报告上下文：\n" + json.dumps(context, ensure_ascii=False, indent=2),
        },
    ]
    for item in history[-8:]:
        if item.get("role") in {"user", "assistant"}:
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": message})
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()
