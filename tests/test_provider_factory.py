from __future__ import annotations

import importlib.util

import pytest

from app.config import Settings
from app.data.factory import build_provider
from app.data.provider import DemoProvider, normalize_symbol


def test_demo_provider_is_default():
    provider = build_provider(Settings())
    assert isinstance(provider, DemoProvider)
    assert provider.get_quote("600519")["source"] == "demo-fixture"


def test_unknown_provider_fails_fast():
    with pytest.raises(ValueError, match="Unknown DATA_PROVIDER"):
        build_provider(Settings(data_provider="nope"))


@pytest.mark.skipif(
    importlib.util.find_spec("akshare") is None,
    reason="akshare not installed",
)
def test_akshare_provider_resolves_known_name_without_network():
    from app.data.akshare_provider import AkshareProvider

    provider = AkshareProvider()
    stock = provider.resolve("600519")
    assert stock["symbol"] == "600519"
    assert stock["name"] == "贵州茅台"
    assert stock["market"] == "cn"


def test_normalize_symbol_variants():
    assert normalize_symbol("SH600519") == "600519"
    assert normalize_symbol("600519.SH") == "600519"
    assert normalize_symbol("aapl") == "AAPL"


@pytest.mark.skipif(
    importlib.util.find_spec("akshare") is None,
    reason="akshare not installed",
)
def test_auto_provider_routes_cn_and_us_symbols():
    provider = build_provider(Settings(data_provider="auto"))
    assert provider.name == "multi"
    assert provider.resolve("600519")["market"] == "cn"
    assert provider.resolve("AAPL")["market"] == "us"
    assert provider._route("600519") is provider.cn
    assert provider._route("AAPL") is provider.us
