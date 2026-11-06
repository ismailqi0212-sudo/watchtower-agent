"""Real US-market data via yfinance.

yfinance is free and key-less, but Yahoo aggressively rate-limits shared IPs.
The adapter keeps calls small, caches results, and surfaces failures as
``data_quality=missing`` rather than substituting synthetic data.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.data.provider import UnknownSymbolError, normalize_symbol


def _safe_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value)).date()
        except (ValueError, OSError):
            return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


class YFinanceProvider:
    name = "yfinance"

    def __init__(self, news_provider: Any = None):
        self.news_provider = news_provider
        self.meta = {"as_of": date.today().isoformat()}
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._tickers: Dict[str, Any] = {}
        self._yf = None

    @property
    def yf(self):
        if self._yf is None:
            try:
                import yfinance as yf
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("yfinance is not installed. Run: pip install yfinance") from exc
            self._yf = yf
        return self._yf

    def _ticker(self, symbol: str):
        symbol = normalize_symbol(symbol).upper()
        if symbol not in self._tickers:
            self._tickers[symbol] = self.yf.Ticker(symbol)
        return self._tickers[symbol]

    def _cached(self, key: str, ttl: float, fn):
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        value = fn()
        self._cache[key] = (now, value)
        return value

    def _call(self, fn):
        last: Optional[Exception] = None
        for attempt in range(2):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt == 0:
                    time.sleep(1.0)
        raise last  # type: ignore[misc]

    # ------------------------------------------------------------------
    # symbols
    # ------------------------------------------------------------------
    def _info(self, symbol: str) -> Dict[str, Any]:
        key = f"info:{symbol}"

        def load():
            try:
                return dict(self._ticker(symbol).info or {})
            except Exception:
                return {}

        try:
            return self._cached(key, 3600, load)
        except Exception:
            return {}

    def resolve(self, raw: str) -> Dict[str, Any]:
        symbol = normalize_symbol(raw).upper()
        if not symbol:
            raise UnknownSymbolError("empty symbol")
        info = self._info(symbol)
        name = info.get("shortName") or info.get("longName") or symbol
        return {
            "symbol": symbol,
            "name": str(name),
            "market": "us",
            "industry": str(info.get("sector") or info.get("industry") or ""),
            "exchange": str(info.get("exchange") or "US"),
        }

    def list_stocks(self) -> List[Dict[str, Any]]:
        return []

    # ------------------------------------------------------------------
    # history / quote
    # ------------------------------------------------------------------
    def _history(self, symbol: str, days: int, as_of: Optional[str]) -> List[Dict[str, Any]]:
        symbol = symbol.upper()
        end = _parse_date(as_of) or date.today()
        key = f"hist:{symbol}:{end.isoformat()}:{days}"

        def load():
            # Fetch a little extra so weekends/holidays still leave enough bars.
            start = end - timedelta(days=max(40, days * 2 + 45))
            frame = self._call(
                lambda: self._ticker(symbol).history(
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    auto_adjust=True,
                    actions=False,
                )
            )
            rows = []
            for index, row in frame.iterrows():
                day = _parse_date(index)
                close = _safe_float(row.get("Close"))
                if not day or close is None:
                    continue
                rows.append(
                    {
                        "date": day.isoformat(),
                        "open": _safe_float(row.get("Open")) or close,
                        "high": _safe_float(row.get("High")) or close,
                        "low": _safe_float(row.get("Low")) or close,
                        "close": close,
                        "volume": int(_safe_float(row.get("Volume")) or 0),
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
    # news
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
        if not items:
            items = self._native_news(symbol, days, as_of)
        return {
            "symbol": symbol,
            "items": items,
            "data_quality": "ok" if items else "missing",
            "source": self.name if items else "none",
        }

    def _native_news(
        self, symbol: str, days: int, as_of: Optional[str]
    ) -> List[Dict[str, Any]]:
        end = _parse_date(as_of) or date.today()
        cutoff = end - timedelta(days=max(1, days))
        key = f"news:{symbol}:{end.isoformat()}:{days}"

        def load():
            try:
                raw = self._ticker(symbol).news or []
            except Exception:
                return []
            items = []
            for index, entry in enumerate(raw):
                content = entry.get("content") if isinstance(entry, dict) else None
                if isinstance(content, dict):
                    title = str(content.get("title") or "").strip()
                    summary = str(content.get("summary") or content.get("description") or "").strip()
                    published = _parse_date(content.get("pubDate") or content.get("displayTime"))
                    provider = content.get("provider") or {}
                    source = str(
                        provider.get("displayName")
                        if isinstance(provider, dict)
                        else provider
                    )
                    url_obj = content.get("canonicalUrl") or {}
                    url = str(url_obj.get("url") if isinstance(url_obj, dict) else "")
                else:
                    title = str(entry.get("title") or "").strip()
                    summary = str(entry.get("summary") or "").strip()
                    published = _parse_date(entry.get("providerPublishTime"))
                    source = str(entry.get("publisher") or "Yahoo Finance")
                    url = str(entry.get("link") or "")
                if not title:
                    continue
                if published is None:
                    if as_of and end < date.today():
                        continue
                    published = end
                if published > end or published < cutoff:
                    continue
                items.append(
                    {
                        "id": f"yf-news:{symbol}:{published.isoformat()}:{index}",
                        "title": title,
                        "sentiment": _sentiment(title, summary),
                        "source": source or "Yahoo Finance",
                        "date": published.isoformat(),
                        "summary": summary[:400],
                        "url": url,
                    }
                )
            items.sort(key=lambda item: item["date"], reverse=True)
            return items[:8]

        try:
            return self._cached(key, 300, load)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # fundamentals
    # ------------------------------------------------------------------
    def get_fundamentals(self, symbol: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        symbol = normalize_symbol(symbol).upper()
        end = _parse_date(as_of) or date.today()
        if (date.today() - end).days > 3:
            return {
                "symbol": symbol,
                "data": {},
                "data_quality": "missing",
                "note": "historical point-in-time fundamentals unavailable from yfinance snapshot",
            }
        info = self._info(symbol)
        if not info:
            return {"symbol": symbol, "data": {}, "data_quality": "missing"}
        roe = _safe_float(info.get("returnOnEquity"))
        data = {
            "as_of": date.today().isoformat(),
            "pe": _safe_float(info.get("trailingPE")),
            "pb": _safe_float(info.get("priceToBook")),
            "roe": round(roe * 100, 2) if roe is not None else None,
            "market_cap_billion": round((_safe_float(info.get("marketCap")) or 0) / 1e9, 2)
            if info.get("marketCap")
            else None,
            "dividend_yield": round((_safe_float(info.get("dividendYield")) or 0) * 100, 2)
            if info.get("dividendYield") is not None
            else None,
            "revenue_growth": round((_safe_float(info.get("revenueGrowth")) or 0) * 100, 2)
            if info.get("revenueGrowth") is not None
            else None,
            "profit_growth": round((_safe_float(info.get("earningsGrowth")) or 0) * 100, 2)
            if info.get("earningsGrowth") is not None
            else None,
            "industry": info.get("sector") or info.get("industry") or "",
            "source": "yfinance:info",
        }
        data = {key: value for key, value in data.items() if value is not None}
        missing = [field for field in ("pe", "pb", "roe") if data.get(field) is None]
        return {
            "symbol": symbol,
            "data": data,
            "data_quality": "partial" if missing else "ok",
        }

    # ------------------------------------------------------------------
    # benchmark
    # ------------------------------------------------------------------
    def get_benchmark(self, days: int = 120, as_of: Optional[str] = None, market: str = "cn") -> Dict[str, Any]:
        end = _parse_date(as_of) or date.today()
        key = f"bench:^GSPC:{end.isoformat()}:{days}"

        def load():
            start = end - timedelta(days=max(40, days * 2 + 45))
            frame = self._call(
                lambda: self._ticker("^GSPC").history(
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    auto_adjust=True,
                    actions=False,
                )
            )
            rows = []
            for index, row in frame.iterrows():
                day = _parse_date(index)
                close = _safe_float(row.get("Close"))
                if not day or close is None or day > end:
                    continue
                rows.append(
                    {
                        "date": day.isoformat(),
                        "open": _safe_float(row.get("Open")) or close,
                        "high": _safe_float(row.get("High")) or close,
                        "low": _safe_float(row.get("Low")) or close,
                        "close": close,
                        "volume": int(_safe_float(row.get("Volume")) or 0),
                    }
                )
            rows.sort(key=lambda item: item["date"])
            return rows[-max(2, days) :]

        bars = self._cached(key, 300, load)
        if len(bars) < 2:
            return {"symbol": "SPX", "bars": bars, "data_quality": "missing"}
        ret = round((bars[-1]["close"] / bars[0]["close"] - 1) * 100, 2)
        return {
            "symbol": "SPX",
            "name": "S&P 500",
            "as_of": bars[-1]["date"],
            "bars": bars,
            "period_return_pct": ret,
            "data_quality": "ok",
        }


POSITIVE_WORDS = ("增长", "上调", "买入", "增持", "回购", "中标", "突破", "利好", "盈利", "新高", "beat", "upgrade", "growth")
NEGATIVE_WORDS = ("下滑", "下调", "减持", "亏损", "处罚", "风险", "下跌", "终止", "立案", "违约", "miss", "downgrade", "lawsuit")


def _sentiment(title: str, content: str = "") -> str:
    text = f"{title} {content}".lower()
    positive = sum(1 for word in POSITIVE_WORDS if word in text)
    negative = sum(1 for word in NEGATIVE_WORDS if word in text)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"
