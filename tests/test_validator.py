from app.agent.runner import run_demo_agent
from app.agent.validator import validate_and_repair
from app.config import Settings


def test_validator_repairs_bad_report(provider, settings):
    stock = provider.resolve("600519")
    as_of = provider.latest_date("600519")
    result = run_demo_agent(provider, stock, as_of)
    evidence = result.report["evidence"]
    bad = {
        "symbol": "",
        "name": "",
        "as_of": "2099-01-01",
        "action": "moon",
        "score": 160,
        "confidence": 2.0,
        "summary": "",
        "thesis": [{"text": "无证据的结论", "evidence_ids": ["fake-id"]}],
        "risks": [],
        "plan": {
            "entry_low": 50,
            "entry_high": 40,
            "stop_loss": 100,
            "target_price": 30,
            "position_pct": 99,
        },
        "data_quality": "missing",
    }
    report = validate_and_repair(
        bad,
        evidence=evidence,
        symbol="600519",
        name="贵州茅台",
        as_of=as_of,
        generated_by="test",
    )
    assert 0 <= report["score"] <= 100
    assert report["action"] in {"buy", "add", "hold", "reduce", "sell", "watch", "avoid"}
    assert report["as_of"] <= as_of
    assert report["plan"]["stop_loss"] < report["plan"]["entry_low"]
    assert report["plan"]["entry_low"] <= report["plan"]["entry_high"]
    assert report["plan"]["target_price"] > report["plan"]["entry_high"]
    assert 0 <= report["plan"]["position_pct"] <= 40
    assert report["data_quality"] in {"ok", "partial", "stale"}
    assert all(
        eid in {item["id"] for item in report["evidence"]}
        for item in report["thesis"]
        for eid in item["evidence_ids"]
    )
    assert report["validation_notes"]


def test_demo_report_is_schema_valid(provider):
    stock = provider.resolve("300750")
    as_of = provider.latest_date("300750")
    result = run_demo_agent(provider, stock, as_of)
    report = result.report
    assert report["symbol"] == "300750"
    assert report["thesis"]
    assert report["risks"]
    assert report["evidence"]
    assert report["generated_by"] == "demo"
    assert len(result.trace) == 8
    assert {item["tool"] for item in result.trace if item["kind"] == "tool"} == {
        "get_quote",
        "get_history",
        "compute_indicators",
        "search_news",
        "get_fundamentals",
        "get_benchmark",
    }
