from app.data.indicators import (
    annualized_volatility,
    compute_indicators,
    max_drawdown,
    pct_change,
    rsi,
    sma,
    volume_ratio,
)


def test_sma_and_pct_change():
    values = [1, 2, 3, 4, 5, 6]
    assert sma(values, 3) == 5.0
    assert sma(values, 8) is None
    assert pct_change(values, 2) == 50.0


def test_rsi_bounds_and_direction():
    up = list(range(1, 40))
    down = list(range(40, 1, -1))
    assert rsi(up) == 100.0
    assert rsi(down) == 0.0
    assert 0 <= rsi([10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]) <= 100


def test_volume_ratio_and_drawdown():
    volumes = [100] * 20 + [200] * 5
    assert volume_ratio(volumes) == 2.0
    assert max_drawdown([100, 120, 60, 80]) == -50.0


def test_compute_indicators_on_fixture(provider):
    bars = provider.get_history("600519", days=120)
    snapshot = compute_indicators(bars)
    assert snapshot["close"] > 0
    assert snapshot["ma5"] is not None
    assert snapshot["ma20"] is not None
    assert snapshot["trend"] in {"多头排列", "空头排列", "震荡整理"}
    assert 0 <= snapshot["rsi14"] <= 100
    assert snapshot["support_20d"] <= snapshot["resistance_20d"]
    assert annualized_volatility([bar["close"] for bar in bars]) is not None
