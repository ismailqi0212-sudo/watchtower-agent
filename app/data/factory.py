"""Select a market-data provider from environment configuration."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.config import Settings
from app.data.provider import DemoProvider

logger = logging.getLogger(__name__)


def _build_news_provider(settings: Settings):
    if not settings.tavily_api_key:
        return None
    mode = (settings.news_provider or "auto").lower()
    if mode not in {"auto", "tavily"}:
        return None
    from app.data.tavily_news import TavilyNewsProvider

    logger.info("news provider: tavily")
    return TavilyNewsProvider(settings.tavily_api_key)


def build_provider(settings: Settings) -> Any:
    kind = (settings.data_provider or "demo").strip().lower()
    news = _build_news_provider(settings)

    if kind in {"demo", "fixture", ""}:
        return DemoProvider(settings.demo_dir)

    if kind in {"auto", "multi", "both"}:
        from app.data.akshare_provider import AkshareProvider
        from app.data.composite_provider import CompositeProvider
        from app.data.nasdaq_provider import NasdaqProvider

        cn = AkshareProvider(news_provider=news)
        cn.ak  # fail fast if the optional dependency is missing
        us = NasdaqProvider(news_provider=news)
        logger.info("market data provider: auto (akshare + nasdaq)")
        return CompositeProvider(cn, us)

    if kind in {"akshare", "a-share", "ashare", "cn"}:
        from app.data.akshare_provider import AkshareProvider

        provider = AkshareProvider(news_provider=news)
        provider.ak  # import early so a missing dependency fails at startup
        logger.info("market data provider: akshare")
        return provider

    if kind in {"nasdaq", "us", "us-stock"}:
        from app.data.nasdaq_provider import NasdaqProvider

        logger.info("market data provider: nasdaq")
        return NasdaqProvider(news_provider=news)

    if kind in {"yfinance", "yahoo"}:
        from app.data.yfinance_provider import YFinanceProvider

        provider = YFinanceProvider(news_provider=news)
        provider.yf  # import early so a missing dependency fails at startup
        logger.info("market data provider: yfinance")
        return provider

    raise ValueError(
        f"Unknown DATA_PROVIDER={settings.data_provider!r}. "
        "Use demo, akshare, or yfinance."
    )
