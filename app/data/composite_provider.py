"""Route A-share and US symbols to their respective providers.

The rest of the app sees one provider. This is what makes a mixed watchlist
(600519 + AAPL) work without branching inside the agent or UI.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.data.provider import UnknownSymbolError, normalize_symbol


class CompositeProvider:
    name = "multi"

    def __init__(self, cn_provider: Any, us_provider: Any):
        self.cn = cn_provider
        self.us = us_provider
        self.meta = {"as_of": None}

    @staticmethod
    def _is_cn(symbol: str) -> bool:
        return bool(re.fullmatch(r"\d{6}", normalize_symbol(symbol)))

    def _route(self, symbol: str):
        return self.cn if self._is_cn(symbol) else self.us

    def list_stocks(self) -> List[Dict[str, Any]]:
        return []

    def resolve(self, raw: str) -> Dict[str, Any]:
        value = (raw or "").strip()
        if not value:
            raise UnknownSymbolError("empty symbol")
        if self._is_cn(value) or re.search(r"[\u4e00-\u9fff]", value):
            return self.cn.resolve(value)
        return self.us.resolve(value)

    def latest_date(self, symbol: str) -> str:
        return self._route(symbol).latest_date(symbol)

    def get_quote(self, symbol: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        return self._route(symbol).get_quote(symbol, as_of=as_of)

    def get_history(
        self, symbol: str, days: int = 120, as_of: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self._route(symbol).get_history(symbol, days=days, as_of=as_of)

    def get_news(
        self, symbol: str, days: int = 14, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._route(symbol).get_news(symbol, days=days, as_of=as_of)

    def get_fundamentals(
        self, symbol: str, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._route(symbol).get_fundamentals(symbol, as_of=as_of)

    def get_benchmark(
        self, days: int = 120, as_of: Optional[str] = None, market: str = "cn"
    ) -> Dict[str, Any]:
        provider = self.cn if (market or "cn").lower() == "cn" else self.us
        return provider.get_benchmark(days=days, as_of=as_of, market=market)
