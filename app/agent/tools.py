"""Tool registry and the six tools the agent can call.

Each tool returns a small, JSON-serializable envelope. The ``evidence`` list is
the important part: every downstream claim must point at an evidence id, so the
UI can render "why did the agent say this?" and the validator can reject
unsupported assertions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.data.indicators import compute_indicators
from app.data.provider import normalize_symbol


@dataclass
class ToolContext:
    provider: Any
    symbol: str
    as_of: Optional[str] = None
    stock: Dict[str, Any] = field(default_factory=dict)
    research: Any = None
    session_id: str = ""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[[ToolContext, Dict[str, Any]], Dict[str, Any]]


def _envelope(
    data: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    summary: str,
    quality: str = "ok",
    ok: bool = True,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "data": data,
        "evidence": evidence,
        "summary": summary,
        "data_quality": quality,
        "error": error,
    }


def _quote(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    symbol = normalize_symbol(args.get("symbol") or ctx.symbol)
    quote = ctx.provider.get_quote(symbol, as_of=ctx.as_of)
    label = f"{quote['price']:.2f} ({quote['change_pct']:+.2f}%)"
    evidence = [
        {
            "id": f"quote:{symbol}:{quote['as_of']}",
            "kind": "quote",
            "label": "最新行情",
            "summary": f"收盘 {quote['price']:.2f} 元，日涨跌 {quote['change_pct']:+.2f}%",
            "as_of": quote["as_of"],
            "payload": {
                "price": quote["price"],
                "change_pct": quote["change_pct"],
                "volume": quote["volume"],
                "source": quote["source"],
            },
        }
    ]
    return _envelope(
        quote,
        evidence,
        f"{symbol} 最新价 {label}，成交量 {quote['volume']:,} 股。",
    )


def _history(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    symbol = normalize_symbol(args.get("symbol") or ctx.symbol)
    days = int(args.get("days") or 120)
    bars = ctx.provider.get_history(symbol, days=days, as_of=ctx.as_of)
    closes = [bar["close"] for bar in bars]
    period_return = round((closes[-1] / closes[0] - 1) * 100, 2) if closes[0] else 0.0
    last = bars[-1]
    evidence = [
        {
            "id": f"history:{symbol}:{last['date']}",
            "kind": "history",
            "label": "日线区间",
            "summary": f"{bars[0]['date']} 至 {last['date']}，区间收益 {period_return:+.2f}%",
            "as_of": last["date"],
            "payload": {
                "bars": len(bars),
                "start": bars[0]["date"],
                "end": last["date"],
                "period_return_pct": period_return,
            },
        }
    ]
    return _envelope(
        {
            "symbol": symbol,
            "bars": len(bars),
            "start": bars[0]["date"],
            "end": last["date"],
            "period_return_pct": period_return,
            "preview": bars[-12:],
        },
        evidence,
        f"获取 {len(bars)} 根日线，区间收益 {period_return:+.2f}%。",
        quality="ok" if len(bars) >= 60 else "partial",
    )


def _indicators(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    symbol = normalize_symbol(args.get("symbol") or ctx.symbol)
    days = int(args.get("days") or 120)
    bars = ctx.provider.get_history(symbol, days=days, as_of=ctx.as_of)
    snapshot = compute_indicators(bars)
    as_of = bars[-1]["date"]
    evidence = [
        {
            "id": f"ind:{symbol}:{as_of}",
            "kind": "indicator",
            "label": "技术指标",
            "summary": (
                f"{snapshot.get('trend', '未知')}；RSI14 {snapshot.get('rsi14', 'N/A')}；"
                f"20 日动量 {snapshot.get('return_20d_pct', 'N/A')}%"
            ),
            "as_of": as_of,
            "payload": snapshot,
        }
    ]
    return _envelope(
        {"symbol": symbol, "as_of": as_of, **snapshot},
        evidence,
        f"计算 MA/RSI/量比/支撑压力，当前趋势：{snapshot.get('trend', '未知')}。",
        quality="ok" if snapshot.get("ma20") else "partial",
    )


def _news(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    symbol = normalize_symbol(args.get("symbol") or ctx.symbol)
    limit = int(args.get("days") or 14)
    result = ctx.provider.get_news(symbol, days=limit, as_of=ctx.as_of)
    items = result["items"]
    positive = sum(1 for item in items if item.get("sentiment") == "positive")
    negative = sum(1 for item in items if item.get("sentiment") == "negative")
    neutral = len(items) - positive - negative
    evidence = []
    for item in items:
        evidence.append(
            {
                "id": item["id"],
                "kind": "news",
                "label": item.get("source", "资讯"),
                "summary": item.get("title", ""),
                "as_of": item.get("date", ""),
                "payload": {
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "sentiment": item.get("sentiment"),
                    "summary": item.get("summary"),
                },
            }
        )
    return _envelope(
        {
            "symbol": symbol,
            "items": items,
            "counts": {"positive": positive, "negative": negative, "neutral": neutral},
        },
        evidence,
        f"检索到 {len(items)} 条资讯：正面 {positive} 条 / 负面 {negative} 条 / 中性 {neutral} 条。",
        quality=result["data_quality"],
    )


def _fundamentals(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    symbol = normalize_symbol(args.get("symbol") or ctx.symbol)
    result = ctx.provider.get_fundamentals(symbol, as_of=ctx.as_of)
    data = result["data"]
    if data:
        evidence = [
            {
                "id": f"fund:{symbol}",
                "kind": "fundamental",
                "label": "基本面",
                "summary": (
                    f"PE {data.get('pe', 'N/A')} / PB {data.get('pb', 'N/A')} / "
                    f"ROE {data.get('roe', 'N/A')}%"
                ),
                "as_of": data.get("as_of", ""),
                "payload": data,
            }
        ]
        summary = (
            f"PE {data.get('pe', 'N/A')}，PB {data.get('pb', 'N/A')}，"
            f"ROE {data.get('roe', 'N/A')}%。"
        )
    else:
        evidence = []
        summary = "未获取到基本面数据。"
    return _envelope(
        {"symbol": symbol, "data": data},
        evidence,
        summary,
        quality=result["data_quality"],
    )


def _benchmark(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    days = int(args.get("days") or 120)
    market = str(args.get("market") or ctx.stock.get("market") or "cn")
    result = ctx.provider.get_benchmark(days=days, as_of=ctx.as_of, market=market)
    bars = result.get("bars", [])
    if len(bars) < 2:
        return _envelope(
            result, [], "基准数据不足。", quality="missing", ok=False, error="benchmark unavailable"
        )
    as_of = bars[-1]["date"]
    evidence = [
        {
            "id": f"bench:{result['symbol']}:{as_of}",
            "kind": "benchmark",
            "label": result.get("name", "基准指数"),
            "summary": f"{result['symbol']} 区间收益 {result['period_return_pct']:+.2f}%",
            "as_of": as_of,
            "payload": {
                "symbol": result["symbol"],
                "period_return_pct": result["period_return_pct"],
            },
        }
    ]
    def _pct(period: int):
        if len(bars) <= period:
            return None
        return round((bars[-1]["close"] / bars[-period - 1]["close"] - 1) * 100, 2)

    return _envelope(
        {
            "symbol": result["symbol"],
            "name": result.get("name"),
            "as_of": as_of,
            "period_return_pct": result["period_return_pct"],
            "return_20d_pct": _pct(20),
            "return_60d_pct": _pct(60),
            "bars": len(bars),
        },
        evidence,
        f"{result.get('name', '基准')} 区间收益 {result['period_return_pct']:+.2f}%。",
    )


def build_tools() -> Dict[str, ToolSpec]:
    specs = [
        ToolSpec(
            name="get_quote",
            description="获取股票最新收盘价、涨跌幅、成交量。",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码，默认当前标的"}
                },
                "additionalProperties": False,
            },
            handler=_quote,
        ),
        ToolSpec(
            name="get_history",
            description="获取最近 N 个交易日的日线数据与区间收益。",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "days": {"type": "integer", "minimum": 20, "maximum": 180},
                },
                "additionalProperties": False,
            },
            handler=_history,
        ),
        ToolSpec(
            name="compute_indicators",
            description="计算 MA5/10/20/60、RSI14、量比、波动率、支撑位和压力位。",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "days": {"type": "integer", "minimum": 60, "maximum": 180},
                },
                "additionalProperties": False,
            },
            handler=_indicators,
        ),
        ToolSpec(
            name="search_news",
            description="检索最近 N 条个股新闻、公告与研报摘要。",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "days": {"type": "integer", "minimum": 3, "maximum": 30},
                },
                "additionalProperties": False,
            },
            handler=_news,
        ),
        ToolSpec(
            name="get_fundamentals",
            description="获取 PE、PB、ROE、市值、股息率、营收与利润增速。",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "additionalProperties": False,
            },
            handler=_fundamentals,
        ),
        ToolSpec(
            name="get_benchmark",
            description="获取沪深300基准区间收益，用于相对强弱比较。",
            parameters={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "minimum": 20, "maximum": 180},
                    "market": {"type": "string", "enum": ["cn", "us"]},
                },
                "additionalProperties": False,
            },
            handler=_benchmark,
        ),
    ]
    return {spec.name: spec for spec in specs}


class ToolRegistry:
    def __init__(self, extra: Optional[Dict[str, ToolSpec]] = None) -> None:
        self._tools = build_tools()
        if extra:
            self._tools.update(extra)

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    def execute(
        self, name: str, ctx: ToolContext, args: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        spec = self._tools.get(name)
        if spec is None:
            return {
                "ok": False,
                "data": {},
                "evidence": [],
                "summary": "",
                "data_quality": "missing",
                "error": f"unknown tool: {name}",
                "latency_ms": 0,
            }
        try:
            result = spec.handler(ctx, args or {})
        except Exception as exc:  # tool failures must never kill the run
            result = {
                "ok": False,
                "data": {},
                "evidence": [],
                "summary": "",
                "data_quality": "missing",
                "error": str(exc),
            }
        result["tool"] = name
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return result
