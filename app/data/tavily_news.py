"""Optional Tavily news adapter.

Tavily is used to broaden A-share/US news coverage beyond what a single market
data vendor exposes. If the key is missing or the call fails, callers fall back
to the provider's native news source.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional


class TavilyNewsProvider:
    name = "tavily"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(
        self,
        symbol: str,
        name: str,
        days: int = 14,
        as_of: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []
        from tavily import TavilyClient

        end = _parse_date(as_of) or date.today()
        cutoff = end - timedelta(days=max(1, days))
        client = TavilyClient(api_key=self.api_key)
        query = f"{name} {symbol} latest stock news earnings announcement"
        response = client.search(
            query=query,
            topic="news",
            days=max(1, int(days)),
            search_depth="basic",
            max_results=8,
            include_answer=False,
            include_raw_content=False,
        )
        items: List[Dict[str, Any]] = []
        for index, result in enumerate(response.get("results", [])):
            published = _parse_date(result.get("published_date"))
            # Tavily sometimes omits the publish date. For a historical run,
            # that is unsafe, so skip undated results rather than inject
            # current news into a past signal.
            if published is None:
                if as_of and end < date.today():
                    continue
                published = end
            if published > end or published < cutoff:
                continue
            title = str(result.get("title") or "").strip()
            content = str(result.get("content") or "").strip()
            if not title:
                continue
            items.append(
                {
                    "id": f"tavily:{symbol}:{published.isoformat()}:{index}",
                    "title": title,
                    "sentiment": _sentiment(title, content),
                    "source": str(result.get("source") or "Tavily"),
                    "date": published.isoformat(),
                    "summary": content[:400],
                    "url": str(result.get("url") or ""),
                }
            )
        items.sort(key=lambda item: item["date"], reverse=True)
        return items[:8]


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            return parsed.date()
    except (TypeError, ValueError):
        pass
    text = text[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


POSITIVE_WORDS = ("增长", "上调", "买入", "增持", "回购", "中标", "突破", "利好", "盈利", "新高")
NEGATIVE_WORDS = ("下滑", "下调", "减持", "亏损", "处罚", "风险", "下跌", "终止", "立案", "违约")


def _sentiment(title: str, content: str = "") -> str:
    text = f"{title} {content}"
    positive = sum(1 for word in POSITIVE_WORDS if word in text)
    negative = sum(1 for word in NEGATIVE_WORDS if word in text)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"
