#!/usr/bin/env python3
"""Generate deterministic offline market fixtures.

The demo is intentionally reproducible: a fixed seed, fixed as-of date, and
plain JSON files. This keeps screenshots, tests and the evaluation harness
stable without requiring a market-data vendor or network access.
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "demo"
AS_OF = date(2026, 10, 28)
DAYS = 180

STOCKS = [
    {
        "symbol": "600519",
        "name": "贵州茅台",
        "market": "cn",
        "industry": "白酒",
        "exchange": "SSE",
        "base": 1680.0,
        "drift": 0.00055,
        "vol": 0.012,
        "volume": 3_800_000,
        "seed": 11,
    },
    {
        "symbol": "300750",
        "name": "宁德时代",
        "market": "cn",
        "industry": "动力电池",
        "exchange": "SZSE",
        "base": 262.0,
        "drift": 0.00095,
        "vol": 0.022,
        "volume": 28_000_000,
        "seed": 22,
    },
    {
        "symbol": "000001",
        "name": "平安银行",
        "market": "cn",
        "industry": "股份制银行",
        "exchange": "SZSE",
        "base": 11.8,
        "drift": -0.00025,
        "vol": 0.011,
        "volume": 95_000_000,
        "seed": 33,
    },
    {
        "symbol": "601318",
        "name": "中国平安",
        "market": "cn",
        "industry": "保险",
        "exchange": "SSE",
        "base": 58.0,
        "drift": 0.00018,
        "vol": 0.014,
        "volume": 48_000_000,
        "seed": 44,
    },
    {
        "symbol": "002594",
        "name": "比亚迪",
        "market": "cn",
        "industry": "新能源车",
        "exchange": "SZSE",
        "base": 312.0,
        "drift": 0.00072,
        "vol": 0.020,
        "volume": 36_000_000,
        "seed": 55,
    },
    {
        "symbol": "600036",
        "name": "招商银行",
        "market": "cn",
        "industry": "股份制银行",
        "exchange": "SSE",
        "base": 42.0,
        "drift": 0.00032,
        "vol": 0.012,
        "volume": 52_000_000,
        "seed": 66,
    },
]

NEWS_TEMPLATES = {
    "600519": [
        ("机构上调贵州茅台目标价，维持“买入”评级", "positive", "机构研报", "多家机构认为高端白酒需求韧性仍在，直销渠道占比提升有望支撑利润率。"),
        ("贵州茅台三季度营收同比增长 9.8%", "positive", "公司公告", "公司披露三季度经营数据，营收与净利润均实现稳健增长，现金流保持充裕。"),
        ("北向资金连续三日净卖出白酒板块", "negative", "财联社", "外资对消费板块的配置出现短期波动，白酒龙头承压。"),
        ("贵州茅台宣布新一轮股份回购计划", "positive", "公司公告", "回购计划释放管理层对长期价值的信心，回购股份拟用于员工持股计划。"),
        ("白酒行业库存去化仍需时间", "neutral", "证券时报", "渠道调研显示部分区域库存仍高于去年同期，动销恢复呈现分化。"),
    ],
    "300750": [
        ("宁德时代发布新一代储能电池，循环寿命提升 30%", "positive", "公司公告", "新产品面向海外大型储能市场，预计明年开始批量交付。"),
        ("宁德时代获欧洲车企长期供货协议", "positive", "财联社", "协议覆盖未来五年动力电池需求，进一步巩固海外市场份额。"),
        ("锂价反弹引发电池成本担忧", "negative", "证券时报", "碳酸锂价格短期上行，市场担心二线电池厂盈利承压。"),
        ("宁德时代三季度出货量超预期", "positive", "机构研报", "动力与储能电池出货均保持增长，产能利用率环比提升。"),
        ("行业价格战延续，电池单价承压", "negative", "财联社", "国内动力电池市场竞争激烈，部分产品报价继续下探。"),
    ],
    "000001": [
        ("平安银行三季度净息差继续收窄", "negative", "公司公告", "贷款重定价与存款成本刚性对净息差形成压力，营收增速放缓。"),
        ("平安银行零售不良率环比改善", "positive", "机构研报", "零售风险指标出现企稳迹象，拨备覆盖率保持较高水平。"),
        ("银行板块获长线资金增配", "positive", "证券时报", "低估值高股息特征吸引保险与被动资金增配。"),
        ("平安银行调整零售信贷投放节奏", "neutral", "财联社", "公司主动压降高风险零售资产，短期规模增长放缓。"),
    ],
    "601318": [
        ("中国平安寿险新业务价值同比增长 12%", "positive", "公司公告", "代理人渠道改革逐步见效，新业务价值率同比提升。"),
        ("保险资金权益配置比例上升", "positive", "机构研报", "长期资金入市政策推进，头部险企投资端弹性增强。"),
        ("长端利率下行压制保险股估值", "negative", "财联社", "10 年期国债收益率走低，市场担忧险企利差损风险。"),
        ("中国平安完成年度分红派息", "positive", "公司公告", "公司维持稳定的分红政策，股息率具备吸引力。"),
    ],
    "002594": [
        ("比亚迪月度销量再创新高", "positive", "公司公告", "新能源乘用车销量同比增长，海外市场贡献持续提升。"),
        ("比亚迪高端品牌门店扩张提速", "positive", "财联社", "高端车型矩阵逐步完善，单车均价有望上行。"),
        ("欧盟关税政策带来短期不确定性", "negative", "证券时报", "海外贸易政策变化可能影响部分车型出口节奏。"),
        ("行业促销加剧，单车盈利承压", "negative", "机构研报", "国内价格竞争延续，市场关注毛利率变化。"),
    ],
    "600036": [
        ("招商银行财富管理收入环比修复", "positive", "公司公告", "代销保险与基金业务回暖，中间业务收入改善。"),
        ("招商银行资产质量保持稳健", "positive", "机构研报", "不良生成率处于低位，拨备覆盖率维持行业前列。"),
        ("零售信贷需求仍偏弱", "negative", "财联社", "居民加杠杆意愿不足，零售贷款增速低于预期。"),
        ("高股息银行股受配置资金青睐", "positive", "证券时报", "低利率环境下，稳定分红资产吸引力提升。"),
    ],
}

FUNDAMENTALS = {
    "600519": {
        "pe": 24.8,
        "pb": 8.1,
        "roe": 31.2,
        "market_cap_billion": 2180.0,
        "dividend_yield": 2.6,
        "revenue_growth": 9.8,
        "profit_growth": 11.4,
        "note": "高端白酒龙头，品牌壁垒与现金流质量突出。",
    },
    "300750": {
        "pe": 28.4,
        "pb": 5.2,
        "roe": 21.6,
        "market_cap_billion": 1140.0,
        "dividend_yield": 1.1,
        "revenue_growth": 18.5,
        "profit_growth": 22.3,
        "note": "动力与储能双轮驱动，海外扩张是主要增量。",
    },
    "000001": {
        "pe": 5.2,
        "pb": 0.55,
        "market_cap_billion": 228.0,
        "dividend_yield": 5.8,
        "revenue_growth": -2.1,
        "profit_growth": -3.4,
        "note": "零售银行转型中，净息差与资产质量是核心变量。",
    },
    "601318": {
        "pe": 7.6,
        "pb": 0.92,
        "roe": 11.8,
        "market_cap_billion": 1060.0,
        "dividend_yield": 5.2,
        "revenue_growth": 6.2,
        "profit_growth": 9.1,
        "note": "综合金融集团，寿险改革与投资端弹性是关键。",
    },
    "002594": {
        "pe": 22.1,
        "pb": 4.6,
        "roe": 19.4,
        "market_cap_billion": 910.0,
        "dividend_yield": 0.8,
        "revenue_growth": 24.6,
        "profit_growth": 28.9,
        "note": "新能源车龙头，规模效应与出海是主要看点。",
    },
    "600036": {
        "pe": 6.4,
        "pb": 0.88,
        "roe": 15.3,
        "market_cap_billion": 1050.0,
        "dividend_yield": 5.5,
        "revenue_growth": 1.8,
        "profit_growth": 3.2,
        "note": "零售银行标杆，财富管理与资产质量稳健。",
    },
}


def trading_days(end: date, count: int) -> list[date]:
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


def make_bars(stock: dict, dates: list[date]) -> list[dict]:
    rnd = random.Random(stock["seed"])
    price = stock["base"] * 0.82
    bars = []
    n = len(dates)
    for i, day in enumerate(dates):
        phase = math.sin(i / 17.0 + stock["seed"]) * stock["vol"] * 0.35
        regime = stock["drift"] * (1.0 + 0.8 * math.sin(i / 40.0))
        ret = regime + phase + rnd.gauss(0, stock["vol"])
        if i > n - 45:
            ret += stock["drift"] * 0.9
        prev = price
        price = max(0.5, prev * math.exp(ret))
        open_price = prev * (1 + rnd.gauss(0, stock["vol"] * 0.20))
        close = price
        high = max(open_price, close) * (1 + abs(rnd.gauss(0, stock["vol"] * 0.35)))
        low = min(open_price, close) * (1 - abs(rnd.gauss(0, stock["vol"] * 0.35)))
        volume = int(stock["volume"] * (0.65 + rnd.random() * 0.75))
        bars.append(
            {
                "date": day.isoformat(),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": volume,
            }
        )
    return bars


def make_benchmark(dates: list[date]) -> list[dict]:
    rnd = random.Random(2026)
    price = 3520.0
    bars = []
    for i, day in enumerate(dates):
        ret = 0.00018 + math.sin(i / 31.0) * 0.0004 + rnd.gauss(0, 0.008)
        prev = price
        price = max(100.0, prev * math.exp(ret))
        bars.append(
            {
                "date": day.isoformat(),
                "open": round(prev, 2),
                "high": round(max(prev, price) * 1.004, 2),
                "low": round(min(prev, price) * 0.996, 2),
                "close": round(price, 2),
                "volume": int(180_000_000 * (0.7 + rnd.random() * 0.6)),
            }
        )
    return bars


def make_news(stock: dict) -> list[dict]:
    items = NEWS_TEMPLATES[stock["symbol"]]
    news = []
    for idx, (title, sentiment, source, summary) in enumerate(items):
        day = AS_OF - timedelta(days=idx * 2 + 1)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        news.append(
            {
                "id": f"news-{stock['symbol']}-{idx + 1}",
                "title": title,
                "sentiment": sentiment,
                "source": source,
                "date": day.isoformat(),
                "summary": summary,
                "url": f"https://example.com/demo/{stock['symbol']}/{idx + 1}",
            }
        )
    return news


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bars").mkdir(parents=True, exist_ok=True)
    dates = trading_days(AS_OF, DAYS)

    stocks_out = []
    news_out = {}
    fundamentals_out = {}
    for stock in STOCKS:
        meta = {k: stock[k] for k in ("symbol", "name", "market", "industry", "exchange")}
        stocks_out.append(meta)
        bars = make_bars(stock, dates)
        (OUT / "bars" / f"{stock['symbol']}.json").write_text(
            json.dumps(bars, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        news_out[stock["symbol"]] = make_news(stock)
        fundamentals_out[stock["symbol"]] = {
            "as_of": AS_OF.isoformat(),
            "industry": stock["industry"],
            **FUNDAMENTALS[stock["symbol"]],
        }

    benchmark = make_benchmark(dates)
    (OUT / "stocks.json").write_text(
        json.dumps(stocks_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "news.json").write_text(
        json.dumps(news_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "fundamentals.json").write_text(
        json.dumps(fundamentals_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "benchmark.json").write_text(
        json.dumps(
            {"symbol": "CSI300", "name": "沪深300（演示）", "as_of": AS_OF.isoformat(), "bars": benchmark},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "meta.json").write_text(
        json.dumps(
            {
                "as_of": AS_OF.isoformat(),
                "days": DAYS,
                "disclaimer": "所有行情、新闻、基本面均为合成演示数据，仅用于产品与技术演示。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote demo fixtures to {OUT}")


if __name__ == "__main__":
    main()
