#!/usr/bin/env python3
"""Point-in-time historical signal backtest.

For each sampled trading day we rebuild the decision card using only data
available up to that day, then compare the next 5 trading days against the
benchmark. The demo fundamentals are deliberately withheld for historical dates
to avoid look-ahead bias; the backtest therefore evaluates the technical/news
portion of the agent.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agent.runner import run_demo_agent  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.data.provider import DemoProvider  # noqa: E402

NEUTRAL_BAND_PCT = 2.0
FORWARD_DAYS = 5
SYMBOLS = ["600519", "300750", "000001", "601318", "002594", "600036"]
SAMPLE_EVERY = 12


def _outcome(action: str, forward_return: float) -> str:
    if action in {"buy", "add"}:
        return "hit" if forward_return > 0 else "miss"
    if action in {"reduce", "sell", "avoid"}:
        return "hit" if forward_return < 0 else "miss"
    return "hit" if abs(forward_return) <= NEUTRAL_BAND_PCT else "miss"


def run_backtest(
    provider: DemoProvider,
    settings: Settings,
    output_path: Path,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for symbol in SYMBOLS:
        try:
            stock = provider.resolve(symbol)
            dates = provider.trading_dates(symbol)
        except Exception:
            continue
        # Start after enough history for MA60 and leave room for the forward window.
        for index in range(70, len(dates) - FORWARD_DAYS - 1, SAMPLE_EVERY):
            as_of = dates[index]
            forward, end_date = provider.forward_return(symbol, as_of, FORWARD_DAYS)
            benchmark = provider.benchmark_forward_return(as_of, FORWARD_DAYS)
            if forward is None or benchmark is None:
                continue
            result = run_demo_agent(provider, stock, as_of, mode="backtest-demo")
            report = result.report
            action = report.get("action", "watch")
            rows.append(
                {
                    "date": as_of,
                    "end_date": end_date,
                    "symbol": symbol,
                    "name": stock["name"],
                    "action": action,
                    "score": report.get("score", 50),
                    "data_quality": report.get("data_quality", "ok"),
                    "forward_return_pct": forward,
                    "benchmark_return_pct": benchmark,
                    "excess_return_pct": round(forward - benchmark, 2),
                    "outcome": _outcome(action, forward),
                }
            )

    total = len(rows)
    hits = sum(1 for row in rows if row["outcome"] == "hit")
    bullish = sum(1 for row in rows if row["action"] in {"buy", "add"})
    bearish = sum(1 for row in rows if row["action"] in {"reduce", "sell", "avoid"})
    neutral = total - bullish - bearish
    directional = bullish + bearish
    directional_hits = sum(
        1
        for row in rows
        if row["action"] in {"buy", "add", "reduce", "sell", "avoid"}
        and row["outcome"] == "hit"
    )
    neutral_hits = sum(
        1
        for row in rows
        if row["action"] in {"hold", "watch"} and row["outcome"] == "hit"
    )
    always_long_hits = sum(
        1 for row in rows if row["forward_return_pct"] > 0
    )
    buy_rows = [row for row in rows if row["action"] in {"buy", "add"}]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "backtest-demo",
        "signals": total,
        "direction_hit_rate": round(directional_hits / directional, 3)
        if directional
        else 0.0,
        "overall_hit_rate": round(hits / total, 3) if total else 0.0,
        "neutral_band_accuracy": round(neutral_hits / neutral, 3)
        if neutral
        else 0.0,
        "always_long_hit_rate": round(always_long_hits / total, 3) if total else 0.0,
        "avg_forward_return_pct": round(
            sum(row["forward_return_pct"] for row in rows) / total, 2
        )
        if total
        else 0.0,
        "buy_signal_avg_forward_return_pct": round(
            sum(row["forward_return_pct"] for row in buy_rows) / len(buy_rows), 2
        )
        if buy_rows
        else 0.0,
        "avg_excess_return_pct": round(
            sum(row["excess_return_pct"] for row in rows) / total, 2
        )
        if total
        else 0.0,
        "avg_benchmark_return_pct": round(
            sum(row["benchmark_return_pct"] for row in rows) / total, 2
        )
        if total
        else 0.0,
        "bullish_signals": bullish,
        "bearish_signals": bearish,
        "neutral_signals": neutral,
        "methodology": (
            f"每 {SAMPLE_EVERY} 个交易日采样一次；只用 as_of 之前的数据；"
            f"预测窗口 {FORWARD_DAYS} 个交易日；中性区间 ±{NEUTRAL_BAND_PCT}%；"
            "方向命中率只统计 buy/add/reduce/sell/avoid；hold/watch 单独看中性区间准确率；"
            "历史日期不注入当前基本面快照，避免未来函数。"
        ),
        "results": rows,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    settings = get_settings()
    provider = DemoProvider(settings.demo_dir)
    summary = run_backtest(
        provider,
        settings,
        ROOT / "evals" / "results" / "backtest_latest.json",
    )
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "results"},
            ensure_ascii=False,
            indent=2,
        )
    )
    for row in summary["results"][:10]:
        print(
            f"{row['date']} {row['symbol']} {row['action']:>6} "
            f"fwd={row['forward_return_pct']:+.1f}% excess={row['excess_return_pct']:+.1f}%"
        )


if __name__ == "__main__":
    main()
