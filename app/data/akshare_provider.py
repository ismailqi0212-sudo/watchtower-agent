"""Real A-share data via AKShare.

AKShare is a free, key-less scraping library. Its endpoints are less stable
than a paid vendor, so this adapter is deliberately defensive:

- every call has a small retry;
- quotes/history/news/fundamentals/benchmark are cached in-process;
- missing fields degrade to ``partial`` instead of fabricating values;
- historical fundamentals are withheld to avoid look-ahead bias;
- no silent fallback to synthetic data. If the real source fails, the tool
  reports ``ok=false`` and the report carries a visible data-quality flag.

This is the provider used when ``DATA_PROVIDER=akshare``.
"""

from __future__ import annotations

import math
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.data.provider import UnknownSymbolError, normalize_symbol

FALLBACK_NAMES = {
    "600519": "贵州茅台",
    "300750": "宁德时代",
    "000001": "平安银行",
    "601318": "中国平安",
    "002594": "比亚迪",
    "600036": "招商银行",
}

POSITIVE_WORDS = ("增长", "上调", "买入", "增持", "回购", "中标", "突破", "利好", "盈利", "新高")
NEGATIVE_WORDS = ("下滑", "下调", "减持", "亏损", "处罚", "风险", "下跌", "终止", "立案", "违约")


def _safe_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _safe_int(value: Any) -> Optional[int]:
    result = _safe_float(value)
    return int(result) if result is not None else None


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _sentiment(title: str, content: str = "") -> str:
    text = f"{title} {content}"
    positive = sum(1 for word in POSITIVE_WORDS if word in text)
    negative = sum(1 for word in NEGATIVE_WORDS if word in text)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


class AkshareProvider:
    name = "akshare"

    def __init__(self, news_provider: Any = None):
        self.news_provider = news_provider
        self.meta = {"as_of": date.today().isoformat()}
        self._ak = None
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._name_map: Optional[Dict[str, str]] = None
        self._name_map_ts = 0.0

    # ------------------------------------------------------------------
    # lazy import / cache / retry
    # ------------------------------------------------------------------
    @property
    def ak(self):
        if self._ak is None:
            try:
                import akshare as ak
            except ImportError as exc:  # pragma: no cover - env dependent
                raise RuntimeError(
                    "AKShare is not installed. Run: pip install akshare"
                ) from exc
            self._ak = ak
        return self._ak

    def _cached(self, key: str, ttl: float, fn):
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        value = fn()
        self._cache[key] = (now, value)
        return value

    def _retry(self, fn):
        last: Optional[Exception] = None
        for attempt in range(2):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 - vendor errors vary
                last = exc
                if attempt == 0:
                    time.sleep(0.8)
        raise last  # type: ignore[misc]

    # ------------------------------------------------------------------
    # symbols
    # ------------------------------------------------------------------
    def _load_name_map(self) -> Dict[str, str]:
        now = time.time()
        if self._name_map is not None and now - self._name_map_ts < 86400:
            return self._name_map
        try:
            frame = self._retry(lambda: self.ak.stock_info_a_code_name())
            mapping = {
                str(row["code"]).zfill(6): str(row["name"]).strip()
                for row in frame.to_dict("records")
            }
            self._name_map = mapping
            self._name_map_ts = now
        except Exception:
            self._name_map = dict(FALLBACK_NAMES)
            self._name_map_ts = now
        return self._name_map

    def _name(self, symbol: str) -> str:
        if symbol in FALLBACK_NAMES:
            return FALLBACK_NAMES[symbol]
        return self._load_name_map().get(symbol, symbol)

    def resolve(self, raw: str) -> Dict[str, Any]:
        value = (raw or "").strip()
        if not value:
            raise UnknownSymbolError("empty symbol")
        symbol = normalize_symbol(value)
        if not re.fullmatch(r"\d{6}", symbol):
            # Try a name lookup for inputs such as "贵州茅台".
            for code, name in self._load_name_map().items():
                if value == name:
                    symbol = code
                    break
            else:
                raise UnknownSymbolError(f"unknown A-share symbol: {raw}")
        exchange = (
            "SSE" if symbol.startswith(("6", "9"))
            else "BSE" if symbol.startswith(("4", "8"))
            else "SZSE"
        )
        return {
            "symbol": symbol,
            "name": self._name(symbol),
            "market": "cn",
            "industry": "",
            "exchange": exchange,
        }

    def list_stocks(self) -> List[Dict[str, Any]]:
        # Watchlists are user-managed; do not auto-seed a real account with
        # thousands of A-share names.
        return []

    # ------------------------------------------------------------------
    # history / quote
    # ------------------------------------------------------------------
    def _history(self, symbol: str, days: int, as_of: Optional[str]) -> List[Dict[str, Any]]:
        end_text = (as_of or date.today().isoformat())[:10]
        end = _parse_date(end_text) or date.today()
        start = end - timedelta(days=max(30, days * 2 + 40))
        key = f"hist:{symbol}:{start.isoformat()}:{end.isoformat()}:{days}"

        def load():
            prefix = (
                "sh" if symbol.startswith(("6", "9"))
                else "bj" if symbol.startswith(("4", "8"))
                else "sz"
            )
            start_text = start.strftime("%Y%m%d")
            end_text_compact = end.strftime("%Y%m%d")

            def rows_from(frame, volume_multiplier: int):
                rows = []
                for row in frame.to_dict("records"):
                    day = _parse_date(
                        row.get("日期") or row.get("date") or row.get("时间")
                    )
                    close = _safe_float(
                        row.get("收盘") or row.get("close")
                    )
                    if not day or close is None:
                        continue
                    rows.append(
                        {
                            "date": day.isoformat(),
                            "open": _safe_float(row.get("开盘") or row.get("open"))
                            or close,
                            "high": _safe_float(row.get("最高") or row.get("high"))
                            or close,
                            "low": _safe_float(row.get("最低") or row.get("low"))
                            or close,
                            "close": close,
                            "volume": int(
                                (_safe_float(row.get("成交量") or row.get("volume")) or 0)
                                * volume_multiplier
                            ),
                        }
                    )
                rows.sort(key=lambda item: item["date"])
                return rows[-max(2, days) :]

            # Eastmoney is the richest source but intermittently blocked.
            errors = []
            try:
                frame = self._retry(
                    lambda: self.ak.stock_zh_a_hist(
                        symbol=symbol,
                        period="daily",
                        start_date=start_text,
                        end_date=end_text_compact,
                        adjust="qfq",
                    )
                )
                rows = rows_from(frame, 100)  # Eastmoney volume is in lots
                if rows:
                    return rows
            except Exception as exc:
                errors.append(f"eastmoney: {exc}")

            # Sina daily (volume already in shares).
            try:
                frame = self._retry(
                    lambda: self.ak.stock_zh_a_daily(
                        symbol=f"{prefix}{symbol}",
                        start_date=start_text,
                        end_date=end_text_compact,
                        adjust="qfq",
                    )
                )
                rows = rows_from(frame, 1)
                if rows:
                    return rows
            except Exception as exc:
                errors.append(f"sina: {exc}")

            # Tencent daily (volume already in shares).
            try:
                frame = self._retry(
                    lambda: self.ak.stock_zh_a_hist_tx(
                        symbol=f"{prefix}{symbol}",
                        start_date=start_text,
                        end_date=end_text_compact,
                        adjust="qfq",
                    )
                )
                rows = rows_from(frame, 1)
                if rows:
                    return rows
            except Exception as exc:
                errors.append(f"tencent: {exc}")

            raise RuntimeError("all A-share history sources failed: " + " | ".join(errors))

        return self._cached(key, 300, load)

    def get_history(
        self, symbol: str, days: int = 120, as_of: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self._history(normalize_symbol(symbol), max(2, int(days)), as_of)

    def latest_date(self, symbol: str) -> str:
        bars = self.get_history(symbol, days=5)
        if not bars:
            raise UnknownSymbolError(f"no daily data for {symbol}")
        return bars[-1]["date"]

    def get_quote(self, symbol: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        symbol = normalize_symbol(symbol)
        bars = self._history(symbol, 10, as_of)
        if not bars:
            raise UnknownSymbolError(f"no quote data for {symbol}")
        last = bars[-1]
        prev = bars[-2] if len(bars) > 1 else last
        change_pct = (
            round((last["close"] / prev["close"] - 1) * 100, 2)
            if prev["close"]
            else 0.0
        )
        return {
            "symbol": symbol,
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

    # ------------------------------------------------------------------
    # news
    # ------------------------------------------------------------------
    def _news_from_akshare(self, symbol: str, days: int, as_of: Optional[str]) -> List[Dict[str, Any]]:
        end = _parse_date(as_of) or date.today()
        cutoff = end - timedelta(days=max(1, days))
        key = f"news:{symbol}:{end.isoformat()}:{days}"

        def load():
            frame = self._retry(lambda: self.ak.stock_news_em(symbol=symbol))
            items = []
            for index, row in enumerate(frame.to_dict("records")):
                published = _parse_date(row.get("发布时间"))
                if not published or published > end or published < cutoff:
                    continue
                title = str(row.get("新闻标题") or "").strip()
                content = str(row.get("新闻内容") or "").strip()
                if not title:
                    continue
                items.append(
                    {
                        "id": f"ak-news:{symbol}:{published.isoformat()}:{index}",
                        "title": title,
                        "sentiment": _sentiment(title, content),
                        "source": str(row.get("文章来源") or "东方财富"),
                        "date": published.isoformat(),
                        "summary": content[:400],
                        "url": str(row.get("新闻链接") or ""),
                    }
                )
            items.sort(key=lambda item: item["date"], reverse=True)
            return items[:12]

        return self._cached(key, 300, load)

    def get_news(
        self, symbol: str, days: int = 14, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        symbol = normalize_symbol(symbol)
        # Eastmoney's stock-news feed is more relevant for A-shares than a
        # generic web search. Tavily is used only as a fallback when it is
        # empty, so enabling Tavily does not degrade the A-share feed.
        items: List[Dict[str, Any]] = []
        source = "none"
        try:
            items = self._news_from_akshare(symbol, days, as_of)
            if items:
                source = "akshare:eastmoney"
        except Exception:
            items = []
        if not items and self.news_provider is not None:
            try:
                items = self.news_provider.search(
                    symbol=symbol,
                    name=self._name(symbol),
                    days=days,
                    as_of=as_of,
                )
                if items:
                    source = "tavily"
            except Exception:
                items = []
        return {
            "symbol": symbol,
            "items": items,
            "data_quality": "ok" if items else "missing",
            "source": source,
        }

    # ------------------------------------------------------------------
    # fundamentals
    # ------------------------------------------------------------------
    def _valuation(self, symbol: str, indicator: str, as_of: Optional[str]) -> Optional[float]:
        end = _parse_date(as_of) or date.today()
        key = f"valuation:{symbol}:{indicator}:{end.isoformat()}"

        def load():
            frame = self._retry(
                lambda: self.ak.stock_zh_valuation_baidu(
                    symbol=symbol, indicator=indicator, period="近一年"
                )
            )
            rows = []
            for row in frame.to_dict("records"):
                day = _parse_date(row.get("date"))
                value = _safe_float(row.get("value"))
                if day and value is not None and day <= end:
                    rows.append((day, value))
            rows.sort(key=lambda item: item[0])
            return rows[-1][1] if rows else None

        try:
            return self._cached(key, 900, load)
        except Exception:
            return None

    def get_fundamentals(self, symbol: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        symbol = normalize_symbol(symbol)
        end = _parse_date(as_of) or date.today()
        # Current fundamentals are only safe for a live/near-live run.
        if (date.today() - end).days > 3:
            return {
                "symbol": symbol,
                "data": {},
                "data_quality": "missing",
                "note": "historical point-in-time fundamentals unavailable from AKShare snapshot",
            }
        key = f"fund:{symbol}:{end.isoformat()}"

        def load():
            frame = self._retry(lambda: self.ak.stock_financial_abstract(symbol=symbol))
            date_columns = [
                str(col) for col in frame.columns if re.fullmatch(r"\d{8}", str(col))
            ]
            date_columns.sort()
            if not date_columns:
                raise ValueError("no report-date columns")
            latest_col = date_columns[-1]
            by_metric = {}
            for row in frame.to_dict("records"):
                metric = str(row.get("指标") or "").strip()
                if metric and metric not in by_metric:
                    value = _safe_float(row.get(latest_col))
                    if value is not None:
                        by_metric[metric] = value
            pe = self._valuation(symbol, "市盈率(TTM)", as_of)
            pb = self._valuation(symbol, "市净率", as_of)
            data = {
                "as_of": f"{latest_col[:4]}-{latest_col[4:6]}-{latest_col[6:]}",
                "pe": pe,
                "pb": pb,
                "roe": by_metric.get("净资产收益率(ROE)")
                or by_metric.get("净资产收益率_平均"),
                "revenue_growth": by_metric.get("营业总收入增长率"),
                "profit_growth": by_metric.get("归属母公司净利润增长率"),
                "gross_margin": by_metric.get("毛利率"),
                "debt_ratio": by_metric.get("资产负债率"),
                "source": "akshare:financial_abstract+baidu_valuation",
            }
            data = {key: value for key, value in data.items() if value is not None}
            return data

        try:
            data = self._cached(key, 900, load)
        except Exception as exc:
            return {
                "symbol": symbol,
                "data": {},
                "data_quality": "missing",
                "note": f"AKShare fundamentals unavailable: {exc}",
            }
        required = ("pe", "pb", "roe")
        missing = [field for field in required if data.get(field) is None]
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
        key = f"bench:sh000300:{end.isoformat()}:{days}"

        def load():
            frame = self._retry(
                lambda: self.ak.stock_zh_index_daily(symbol="sh000300")
            )
            rows = []
            for row in frame.to_dict("records"):
                day = _parse_date(row.get("date"))
                close = _safe_float(row.get("close"))
                if not day or close is None or day > end:
                    continue
                rows.append(
                    {
                        "date": day.isoformat(),
                        "open": _safe_float(row.get("open")) or close,
                        "high": _safe_float(row.get("high")) or close,
                        "low": _safe_float(row.get("low")) or close,
                        "close": close,
                        "volume": int(_safe_float(row.get("volume")) or 0),
                    }
                )
            rows.sort(key=lambda item: item["date"])
            return rows[-max(2, days) :]

        bars = self._cached(key, 300, load)
        if len(bars) < 2:
            return {"symbol": "CSI300", "bars": bars, "data_quality": "missing"}
        period_return = round((bars[-1]["close"] / bars[0]["close"] - 1) * 100, 2)
        return {
            "symbol": "CSI300",
            "name": "沪深300",
            "as_of": bars[-1]["date"],
            "bars": bars,
            "period_return_pct": period_return,
            "data_quality": "ok",
        }
