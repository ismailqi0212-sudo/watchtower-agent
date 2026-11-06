"""Dependency-free technical indicators.

Why not pandas-ta? The project is a resume-sized system: a few dozen lines of
explicit, testable math is easier to explain than a large indicator library,
and it keeps the demo installable on any Python 3.9+ machine.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence


def _closes(bars: Sequence[Dict[str, Any]]) -> List[float]:
    return [float(bar["close"]) for bar in bars]


def sma(values: Sequence[float], window: int) -> Optional[float]:
    if window <= 0 or len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 4)


def pct_change(values: Sequence[float], periods: int) -> Optional[float]:
    if len(values) <= periods or values[-periods - 1] == 0:
        return None
    return round((values[-1] / values[-periods - 1] - 1) * 100, 2)


def rsi(values: Sequence[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    gains = []
    losses = []
    for prev, cur in zip(values[-period - 1 : -1], values[-period:]):
        delta = cur - prev
        if delta >= 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def annualized_volatility(values: Sequence[float], window: int = 20) -> Optional[float]:
    if len(values) <= window:
        return None
    returns = []
    for prev, cur in zip(values[-window - 1 : -1], values[-window:]):
        if prev > 0 and cur > 0:
            returns.append(math.log(cur / prev))
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    return round(math.sqrt(variance) * math.sqrt(252) * 100, 2)


def max_drawdown(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1)
    return round(worst * 100, 2)


def volume_ratio(volumes: Sequence[float]) -> Optional[float]:
    if len(volumes) < 21:
        return None
    recent = sum(volumes[-5:]) / 5
    baseline = sum(volumes[-25:-5]) / 20
    if baseline <= 0:
        return None
    return round(recent / baseline, 2)


def _trend_label(close: float, ma5: Optional[float], ma10: Optional[float], ma20: Optional[float]) -> str:
    if None in (ma5, ma10, ma20):
        return "数据不足"
    if ma5 > ma10 > ma20 and close > ma20:
        return "多头排列"
    if ma5 < ma10 < ma20 and close < ma20:
        return "空头排列"
    return "震荡整理"


def compute_indicators(bars: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a compact, serializable technical snapshot."""

    closes = _closes(bars)
    volumes = [float(bar["volume"]) for bar in bars]
    if not closes:
        return {}

    close = closes[-1]
    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    recent = bars[-20:]
    support = round(min(float(bar["low"]) for bar in recent), 2)
    resistance = round(max(float(bar["high"]) for bar in recent), 2)
    trend = _trend_label(close, ma5, ma10, ma20)
    above_ma20 = bool(ma20 and close > ma20)
    rsi14 = rsi(closes)
    vol_ratio = volume_ratio(volumes)
    ret20 = pct_change(closes, 20)
    ret5 = pct_change(closes, 5)

    if trend == "多头排列" and ret20 is not None and ret20 > 0:
        trend_score = 82
    elif trend == "多头排列":
        trend_score = 68
    elif trend == "空头排列":
        trend_score = 22
    elif above_ma20:
        trend_score = 58
    else:
        trend_score = 40

    return {
        "close": round(close, 2),
        "ma5": round(ma5, 2) if ma5 else None,
        "ma10": round(ma10, 2) if ma10 else None,
        "ma20": round(ma20, 2) if ma20 else None,
        "ma60": round(ma60, 2) if ma60 else None,
        "rsi14": rsi14,
        "volume_ratio_5_20": vol_ratio,
        "return_5d_pct": ret5,
        "return_20d_pct": ret20,
        "return_60d_pct": pct_change(closes, 60),
        "volatility_20d_pct": annualized_volatility(closes),
        "max_drawdown_60d_pct": max_drawdown(closes[-60:]),
        "support_20d": support,
        "resistance_20d": resistance,
        "trend": trend,
        "trend_score": trend_score,
        "above_ma20": above_ma20,
        "ma_alignment": f"MA5 {ma5:.2f} / MA10 {ma10:.2f} / MA20 {ma20:.2f}"
        if ma5 and ma10 and ma20
        else "均线数据不足",
    }
