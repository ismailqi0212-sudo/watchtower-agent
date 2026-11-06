"""Free US-market data via Nasdaq's public quote API.

Yahoo/yfinance rate-limits shared IPs aggressively. Nasdaq's public endpoint is
a useful key-less fallback for daily OHLC, quotes, company summary and SPY as a
benchmark. It does not provide a complete fundamentals/news feed, so those
fields degrade to ``partial``/``missing`` unless Tavily is configured.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.data.provider import UnknownSymbolError, normalize_symbol

BASE = "https://api.nasdaq.com/api/quote"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
    if not text or text.upper() in {"N/A", "NA", "NONE", "--"}:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y%m%d", "%b %d, %Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    return None


class NasdaqProvider:
    name = "nasdaq"

    def __init__(self, news_provider: Any = None):
        self.news_provider = news_provider
        self.meta = {"as_of": date.today().isoformat()}
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    def _cached(self, key: str, ttl: float, fn):
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        value = fn()
        self._cache[key] = (now, value)
        return value

    def _get(self, path: str) -> Dict[str, Any]:
        response = self._session.get(f"{BASE}/{path}", timeout=20)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status", {}).get("rCode", 200) != 200:
            raise RuntimeError(str(payload.get("status") or payload))
        return payload.get("data") or {}

    # ------------------------------------------------------------------
    # symbols / summary
    # ------------------------------------------------------------------
    def _info(self, symbol: str) -> Dict[str, Any]:
        key = f"info:{symbol}"

        def load():
            try:
                return self._get(f"{symbol}/info?assetclass=stocks")
            except Exception:
                return {}

        return self._cached(key, 3600, load)

    def resolve(self, raw: str) -> Dict[str, Any]:
        symbol = normalize_symbol(raw).upper()
        if not symbol:
            raise UnknownSymbolError("empty symbol")
        info = self._info(symbol)
        name = info.get("companyName") or symbol
        return {
            "symbol": symbol,
            "name": str(name).replace(" Common Stock", "").strip(),
            "market": "us",
            "industry": "",
            "exchange": str(info.get("exchange") or "US"),
        }

    def list_stocks(self) -> List[Dict[str, Any]]:
        return []

    # ------------------------------------------------------------------
    # history / quote
    # ------------------------------------------------------------------
    def _history(
        self, symbol: str, days: int, as_of: Optional[str], assetclass: str = "stocks"
    ) -> List[Dict[str, Any]]:
        end = _parse_date(as_of) or date.today()
        start = end - timedelta(days=max(40, days * 2 + 30))
        key = f"hist:{assetclass}:{symbol}:{start.isoformat()}:{end.isoformat()}:{days}"

        def load():
            data = self._get(
                f"{symbol}/historical?assetclass={assetclass}"
                f"&fromdate={start.isoformat()}&todate={end.isoformat()}&limit=400"
            )
            rows = []
            for row in (data.get("tradesTable") or {}).get("rows", []):
                day = _parse_date(row.get("date"))
                close = _num(row.get("close"))
                if not day or close is None or day > end:
                    continue
                rows.append(
                    {
                        "date": day.isoformat(),
                        "open": _num(row.get("open")) or close,
                        "high": _num(row.get("high")) or close,
                        "low": _num(row.get("low")) or close,
                        "close": close,
                        "volume": int(_num(row.get("volume")) or 0),
                    }
                )
            rows.sort(key=lambda item: item["date"])
            if not rows:
                raise ValueError(f"no price history for {symbol}")
            return rows[-max(2, days) :]

        return self._cached(key, 300, load)

    def get_history(
        self, symbol: str, days: int = 120, as_of: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self._history(normalize_symbol(symbol).upper(), max(2, int(days)), as_of)

    def latest_date(self, symbol: str) -> str:
        bars = self.get_history(symbol, days=5)
        if not bars:
            raise UnknownSymbolError(f"no data for {symbol}")
        return bars[-1]["date"]

    def get_quote(self, symbol: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        symbol = normalize_symbol(symbol).upper()
        bars = self._history(symbol, 10, as_of)
        last = bars[-1]
        prev = bars[-2] if len(bars) > 1 else last
        change = round((last["close"] / prev["close"] - 1) * 100, 2) if prev["close"] else 0.0
        return {
            "symbol": symbol,
            "as_of": last["date"],
            "price": last["close"],
            "open": last["open"],
            "high": last["high"],
            "low": last["low"],
            "prev_close": prev["close"],
            "change_pct": change,
            "volume": last["volume"],
            "source": self.name,
            "data_quality": "ok",
        }

    # ------------------------------------------------------------------
    # news / fundamentals
    # ------------------------------------------------------------------
    def get_news(
        self, symbol: str, days: int = 14, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        symbol = normalize_symbol(symbol).upper()
        items: List[Dict[str, Any]] = []
        if self.news_provider is not None:
            try:
                items = self.news_provider.search(
                    symbol=symbol,
                    name=self.resolve(symbol)["name"],
                    days=days,
                    as_of=as_of,
                )
            except Exception:
                items = []
        return {
            "symbol": symbol,
            "items": items,
            "data_quality": "ok" if items else "missing",
            "source": "tavily" if items else "none",
        }

    def get_fundamentals(self, symbol: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        symbol = normalize_symbol(symbol).upper()
        end = _parse_date(as_of) or date.today()
        if (date.today() - end).days > 3:
            return {
                "symbol": symbol,
                "data": {},
                "data_quality": "missing",
                "note": "historical point-in-time fundamentals unavailable from Nasdaq snapshot",
            }
        key = f"summary:{symbol}"

        def load():
            return self._get(f"{symbol}/summary?assetclass=stocks")

        try:
            raw = self._cached(key, 900, load)
        except Exception as exc:
            return {
                "symbol": symbol,
                "data": {},
                "data_quality": "missing",
                "note": f"Nasdaq summary unavailable: {exc}",
            }
        summary = raw.get("summaryData") or {}
        data = {
            "as_of": date.today().isoformat(),
            "market_cap_billion": round((_num((summary.get("MarketCap") or {}).get("value")) or 0) / 1e9, 2)
            if summary.get("MarketCap")
            else None,
            "dividend_yield": _num((summary.get("Yield") or {}).get("value")),
            "industry": (summary.get("Industry") or {}).get("value"),
            "sector": (summary.get("Sector") or {}).get("value"),
            "source": "nasdaq:summary",
        }
        data = {key: value for key, value in data.items() if value is not None}
        # Nasdaq summary has no PE/PB/ROE; be explicit rather than inventing.
        return {
            "symbol": symbol,
            "data": data,
            "data_quality": "partial" if data else "missing",
        }

    # ------------------------------------------------------------------
    # benchmark
    # ------------------------------------------------------------------
    def get_benchmark(self, days: int = 120, as_of: Optional[str] = None, market: str = "cn") -> Dict[str, Any]:
        bars = self._history("SPY", max(2, days), as_of, assetclass="etf")
        if len(bars) < 2:
            return {"symbol": "SPY", "bars": bars, "data_quality": "missing"}
        ret = round((bars[-1]["close"] / bars[0]["close"] - 1) * 100, 2)
        return {
            "symbol": "SPY",
            "name": "S&P 500 ETF",
            "as_of": bars[-1]["date"],
            "bars": bars,
            "period_return_pct": ret,
            "data_quality": "ok",
        }
