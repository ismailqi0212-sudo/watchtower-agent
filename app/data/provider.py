"""Market data provider contract and the offline demo implementation.

Swapping in a real vendor is intentionally a small change: implement the same
five methods (quote/history/news/fundamentals/benchmark) and point the app at
it. The agent only knows the tool contract, never the vendor SDK.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


class UnknownSymbolError(ValueError):
    pass


def normalize_symbol(raw: str) -> str:
    value = (raw or "").strip().upper()
    value = re.sub(r"^(SH|SZ|SS|HK|US)[.:]?", "", value)
    value = re.sub(r"\.(SH|SZ|SS|HK|US)$", "", value)
    if re.fullmatch(r"\d{6}", value):
        return value
    return value


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


class DemoProvider:
    """Deterministic fixtures shipped with the repo."""

    name = "demo-fixture"

    def __init__(self, demo_dir: Path):
        self.demo_dir = Path(demo_dir)
        self.meta = self._read("meta.json", {})
        self.stocks: List[Dict[str, Any]] = self._read("stocks.json", [])
        self.news: Dict[str, List[Dict[str, Any]]] = self._read("news.json", {})
        self.fundamentals: Dict[str, Dict[str, Any]] = self._read(
            "fundamentals.json", {}
        )
        self.benchmark = self._read("benchmark.json", {})
        self._stock_map = {item["symbol"]: item for item in self.stocks}
        self._bars: Dict[str, List[Dict[str, Any]]] = {}

    def _read(self, name: str, default: Any) -> Any:
        path = self.demo_dir / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_bars(self, symbol: str) -> List[Dict[str, Any]]:
        symbol = normalize_symbol(symbol)
        if symbol not in self._bars:
            path = self.demo_dir / "bars" / f"{symbol}.json"
            if not path.exists():
                raise UnknownSymbolError(f"unknown symbol: {symbol}")
            self._bars[symbol] = json.loads(path.read_text(encoding="utf-8"))
        return self._bars[symbol]

    def list_stocks(self) -> List[Dict[str, Any]]:
        return list(self.stocks)

    def resolve(self, raw: str) -> Dict[str, Any]:
        value = (raw or "").strip()
        if not value:
            raise UnknownSymbolError("empty symbol")
        symbol = normalize_symbol(value)
        if symbol in self._stock_map:
            return dict(self._stock_map[symbol])
        for item in self.stocks:
            if value in {item["name"], item["symbol"]}:
                return dict(item)
        raise UnknownSymbolError(f"unknown symbol: {raw}")

    def get_quote(self, symbol: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        bars = self._slice(symbol, as_of)
        if not bars:
            raise UnknownSymbolError(f"no bars for {symbol}")
        last = bars[-1]
        prev = bars[-2] if len(bars) > 1 else last
        change_pct = round((last["close"] / prev["close"] - 1) * 100, 2) if prev["close"] else 0.0
        return {
            "symbol": normalize_symbol(symbol),
            "as_of": last["date"],
            "price": last["close"],
            "open": last["open"],
            "high": last["high"],
            "low": last["low"],
            "prev_close": prev["close"],
            "change_pct": change_pct,
            "volume": last["volume"],
            "source": self.name,
            "data_quality": "ok",
        }

    def get_history(
        self, symbol: str, days: int = 120, as_of: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        bars = self._slice(symbol, as_of)
        if not bars:
            raise UnknownSymbolError(f"no bars for {symbol}")
        return bars[-max(2, min(int(days), len(bars))) :]

    def get_news(
        self, symbol: str, days: int = 14, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        symbol = normalize_symbol(symbol)
        limit = _parse_date(as_of) or _parse_date(self.meta.get("as_of"))
        cutoff = limit - timedelta(days=max(1, int(days))) if limit else None
        items = []
        for item in self.news.get(symbol, []):
            item_date = _parse_date(item.get("date"))
            if limit and item_date and item_date > limit:
                continue
            if cutoff and item_date and item_date < cutoff:
                continue
            items.append(dict(item))
        items.sort(key=lambda item: item.get("date", ""), reverse=True)
        items = items[:20]
        return {
            "symbol": symbol,
            "items": items,
            "data_quality": "ok" if items else "missing",
        }

    def get_fundamentals(
        self, symbol: str, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        symbol = normalize_symbol(symbol)
        data = dict(self.fundamentals.get(symbol, {}))
        if not data:
            return {"symbol": symbol, "data": {}, "data_quality": "missing"}
        # Demo fundamentals are a single snapshot; refuse to leak them into a
        # historical backtest where they would be look-ahead information.
        if as_of and data.get("as_of") and data["as_of"] > as_of:
            return {
                "symbol": symbol,
                "data": {},
                "data_quality": "missing",
                "note": "point-in-time fundamentals unavailable in demo fixtures",
            }
        missing = [key for key in ("pe", "pb", "roe") if data.get(key) is None]
        data["missing_fields"] = missing
        return {
            "symbol": symbol,
            "data": data,
            "data_quality": "partial" if missing else "ok",
        }

    def get_benchmark(
        self, days: int = 120, as_of: Optional[str] = None, market: str = "cn"
    ) -> Dict[str, Any]:
        bars = self.benchmark.get("bars", [])
        limit = _parse_date(as_of)
        if limit:
            bars = [bar for bar in bars if _parse_date(bar["date"]) <= limit]
        bars = bars[-max(2, min(int(days), len(bars))) :]
        if len(bars) < 2:
            return {"symbol": "CSI300", "bars": bars, "data_quality": "missing"}
        ret = (bars[-1]["close"] / bars[0]["close"] - 1) * 100
        return {
            "symbol": self.benchmark.get("symbol", "CSI300"),
            "name": self.benchmark.get("name", "沪深300"),
            "as_of": bars[-1]["date"],
            "bars": bars,
            "period_return_pct": round(ret, 2),
            "data_quality": "ok",
        }

    def _slice(self, symbol: str, as_of: Optional[str]) -> List[Dict[str, Any]]:
        bars = self._load_bars(symbol)
        limit = _parse_date(as_of)
        if limit:
            bars = [bar for bar in bars if _parse_date(bar["date"]) <= limit]
        return bars

    def latest_date(self, symbol: str) -> str:
        return self._load_bars(symbol)[-1]["date"]

    def trading_dates(self, symbol: str) -> List[str]:
        return [bar["date"] for bar in self._load_bars(symbol)]

    def bar_on(self, symbol: str, day: str) -> Optional[Dict[str, Any]]:
        for bar in self._load_bars(symbol):
            if bar["date"] == day:
                return bar
        return None

    def forward_return(
        self, symbol: str, start_date: str, trading_days: int = 5
    ) -> Tuple[Optional[float], Optional[str]]:
        bars = self._load_bars(symbol)
        index = next(
            (i for i, bar in enumerate(bars) if bar["date"] >= start_date), None
        )
        if index is None or index + trading_days >= len(bars):
            return None, None
        start = bars[index]["close"]
        end_bar = bars[index + trading_days]
        if not start:
            return None, None
        return round((end_bar["close"] / start - 1) * 100, 2), end_bar["date"]

    def benchmark_forward_return(
        self, start_date: str, trading_days: int = 5
    ) -> Optional[float]:
        bars = self.benchmark.get("bars", [])
        index = next(
            (i for i, bar in enumerate(bars) if bar["date"] >= start_date), None
        )
        if index is None or index + trading_days >= len(bars):
            return None
        start = bars[index]["close"]
        end = bars[index + trading_days]["close"]
        if not start:
            return None
        return round((end / start - 1) * 100, 2)
