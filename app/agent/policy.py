"""Deterministic demo policy.

This is not a trading strategy. It is the offline fallback that lets the whole
product run without an API key, and the baseline the LLM agent is compared
against. The policy is intentionally transparent: each score component maps to
an evidence id, so the UI can explain the output.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas import ACTION_LABELS


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _action_for(score: int) -> str:
    if score >= 78:
        return "buy"
    if score >= 63:
        return "add"
    if score >= 47:
        return "hold"
    if score >= 35:
        return "watch"
    if score >= 22:
        return "reduce"
    return "sell"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _evidence_ids(results: Dict[str, Dict[str, Any]], tool: str) -> List[str]:
    return [item["id"] for item in results.get(tool, {}).get("evidence", [])]


def synthesize(
    symbol: str,
    name: str,
    as_of: str,
    stock: Dict[str, Any],
    results: Dict[str, Dict[str, Any]],
    mode: str = "demo",
) -> Dict[str, Any]:
    quote = results.get("get_quote", {}).get("data", {})
    ind = results.get("compute_indicators", {}).get("data", {})
    news_data = results.get("search_news", {}).get("data", {})
    fund_data = results.get("get_fundamentals", {}).get("data", {}).get("data", {})
    bench = results.get("get_benchmark", {}).get("data", {})

    close = _num(quote.get("price"), _num(ind.get("close")))
    ma5 = _num(ind.get("ma5"), close)
    ma10 = _num(ind.get("ma10"), close)
    ma20 = _num(ind.get("ma20"), close)
    rsi = _num(ind.get("rsi14"), 50)
    ret20 = _num(ind.get("return_20d_pct"))
    ret5 = _num(ind.get("return_5d_pct"))
    vol_ratio = _num(ind.get("volume_ratio_5_20"), 1.0)
    trend = ind.get("trend", "震荡整理")
    trend_score = int(_num(ind.get("trend_score"), 50))
    support = _num(ind.get("support_20d"), close * 0.95)
    resistance = _num(ind.get("resistance_20d"), close * 1.05)

    counts = news_data.get("counts", {})
    positive = int(counts.get("positive", 0))
    negative = int(counts.get("negative", 0))
    news_items = news_data.get("items", [])
    news_ids = [item["id"] for item in news_items[:3]]

    pe = fund_data.get("pe")
    pb = fund_data.get("pb")
    roe = fund_data.get("roe")
    score = 50.0

    # Trend and momentum
    if trend == "多头排列":
        score += 14
    elif trend == "空头排列":
        score -= 14
    elif ind.get("above_ma20"):
        score += 5
    else:
        score -= 5

    if ret20 > 5:
        score += 6
    elif ret20 > 0:
        score += 3
    elif ret20 < -5:
        score -= 6
    else:
        score -= 3

    # Mean-reversion / overbought guard
    if 55 <= rsi <= 68:
        score += 4
    elif rsi > 75:
        score -= 5
    elif rsi < 30:
        score += 2

    if vol_ratio > 1.25:
        score += 3
    elif vol_ratio < 0.7:
        score -= 1

    # News sentiment
    score += _clamp(positive * 2 - negative * 3, -8, 8)

    # Fundamentals
    if roe is not None:
        if _num(roe) >= 15:
            score += 3
        elif _num(roe) < 8:
            score -= 2
    else:
        score -= 2
    if pe is not None and _num(pe) > 60:
        score -= 3

    # Relative strength vs benchmark (20d)
    bench20 = bench.get("return_20d_pct")
    relative = None
    if bench20 is not None:
        relative = round(ret20 - _num(bench20), 2)
        if relative > 2:
            score += 3
        elif relative < -2:
            score -= 2

    score_int = int(round(_clamp(score, 5, 95)))
    action = _action_for(score_int)

    quality_flags = [
        results.get("get_quote", {}).get("data_quality", "missing"),
        results.get("compute_indicators", {}).get("data_quality", "missing"),
        results.get("search_news", {}).get("data_quality", "missing"),
        results.get("get_fundamentals", {}).get("data_quality", "missing"),
        results.get("get_benchmark", {}).get("data_quality", "missing"),
    ]
    data_quality = "ok" if all(flag == "ok" for flag in quality_flags) else "partial"
    if not quote or not ind:
        data_quality = "stale"

    confidence = 0.62
    if all(results.get(tool, {}).get("ok") for tool in results):
        confidence += 0.08
    if len(news_items) >= 3:
        confidence += 0.04
    if data_quality != "ok":
        confidence -= 0.12
    confidence = round(_clamp(confidence, 0.4, 0.86), 2)

    # Trade plan: anchor entries to MA10, stop below MA20, target above resistance.
    anchor = ma10 if ma10 > 0 else close
    entry_low = round(min(anchor, close) * 0.99, 2)
    entry_high = round(max(anchor, close) * 1.005, 2)
    stop_loss = round(min(entry_low * 0.96, ma20 * 0.97 if ma20 > 0 else close * 0.93), 2)
    target_price = round(max(resistance * 1.01, close * 1.08), 2)
    if stop_loss >= entry_low:
        stop_loss = round(entry_low * 0.95, 2)
    if target_price <= entry_high:
        target_price = round(entry_high * 1.06, 2)

    if score_int >= 80:
        position = 30.0
    elif score_int >= 63:
        position = 20.0
    elif score_int >= 47:
        position = 10.0
    else:
        position = 0.0

    # Summary and explanations
    momentum_word = "偏强" if ret20 > 2 else "偏弱" if ret20 < -2 else "震荡"
    news_word = "偏正面" if positive > negative else "偏负面" if negative > positive else "中性"
    action_label = ACTION_LABELS.get(action, action)
    summary = (
        f"{trend}，20 日动量 {ret20:+.1f}%（{momentum_word}），RSI14 {rsi:.0f}；"
        f"近端资讯{news_word}。当前倾向“{action_label}”："
        f"关注 {entry_low:.2f}–{entry_high:.2f} 区间，跌破 {stop_loss:.2f} 止损，"
        f"上方目标 {target_price:.2f}。"
    )

    thesis = [
        {
            "text": (
                f"均线呈{trend}，收盘价{'站上' if ind.get('above_ma20') else '低于'} MA20，"
                f"趋势评分 {trend_score}/100。"
            ),
            "evidence_ids": _evidence_ids(results, "compute_indicators"),
        },
        {
            "text": (
                f"20 日收益 {ret20:+.1f}%，5 日收益 {ret5:+.1f}%，"
                f"量比 {vol_ratio:.2f}，短线动能{momentum_word}。"
            ),
            "evidence_ids": _evidence_ids(results, "compute_indicators")
            + _evidence_ids(results, "get_history"),
        },
    ]
    if news_items:
        thesis.append(
            {
                "text": (
                    f"近端资讯 {len(news_items)} 条：正面 {positive} 条、负面 {negative} 条，"
                    f"舆情{news_word}。"
                ),
                "evidence_ids": news_ids,
            }
        )
    if fund_data:
        thesis.append(
            {
                "text": (
                    f"PE {pe if pe is not None else 'N/A'}，PB {pb if pb is not None else 'N/A'}，"
                    f"ROE {roe if roe is not None else 'N/A'}%，估值与盈利质量作为辅助校验。"
                ),
                "evidence_ids": _evidence_ids(results, "get_fundamentals"),
            }
        )
    if relative is not None:
        thesis.append(
            {
                "text": f"相对沪深300的 20 日超额收益 {relative:+.1f} 个百分点。",
                "evidence_ids": _evidence_ids(results, "get_benchmark"),
            }
        )

    risks: List[Dict[str, Any]] = []
    if rsi > 72:
        risks.append(
            {
                "text": f"RSI14 为 {rsi:.0f}，接近超买区，短线追高回撤风险上升。",
                "severity": "medium",
                "evidence_ids": _evidence_ids(results, "compute_indicators"),
            }
        )
    if pe is not None and _num(pe) > 45:
        risks.append(
            {
                "text": f"PE 为 {_num(pe):.1f}，估值对盈利兑现要求较高。",
                "severity": "medium",
                "evidence_ids": _evidence_ids(results, "get_fundamentals"),
            }
        )
    if negative > positive:
        risks.append(
            {
                "text": f"近端负面资讯 {negative} 条多于正面 {positive} 条，需跟踪事件进展。",
                "severity": "high" if negative >= 2 else "medium",
                "evidence_ids": news_ids,
            }
        )
    if data_quality != "ok":
        risks.append(
            {
                "text": "部分数据缺失或工具失败，结论置信度已下调。",
                "severity": "medium",
                "evidence_ids": _evidence_ids(results, "get_fundamentals"),
            }
        )
    if not risks:
        risks.append(
            {
                "text": "模型基于历史数据与公开资讯，无法预测突发事件，需结合仓位管理。",
                "severity": "low",
                "evidence_ids": _evidence_ids(results, "compute_indicators")[:1],
            }
        )

    evidence: List[Dict[str, Any]] = []
    seen = set()
    for tool in (
        "get_quote",
        "get_history",
        "compute_indicators",
        "search_news",
        "get_fundamentals",
        "get_benchmark",
    ):
        for item in results.get(tool, {}).get("evidence", []):
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            evidence.append(item)

    return {
        "symbol": symbol,
        "name": name,
        "as_of": quote.get("as_of", as_of),
        "action": action,
        "score": score_int,
        "confidence": confidence,
        "summary": summary,
        "thesis": thesis,
        "risks": risks,
        "plan": {
            "entry_low": entry_low,
            "entry_high": entry_high,
            "stop_loss": stop_loss,
            "target_price": target_price,
            "position_pct": position,
            "horizon": "5d" if action in {"buy", "add"} else "10d",
        },
        "data_quality": data_quality,
        "evidence": evidence,
        "validation_notes": [],
        "generated_by": mode,
        "disclaimer": "仅供研究与演示，不构成投资建议。",
    }
