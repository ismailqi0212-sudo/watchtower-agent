from __future__ import annotations

import json


def test_health_and_seeded_watchlist(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["mode"] == "demo"
    stocks = client.get("/api/stocks").json()["items"]
    assert len(stocks) >= 6
    assert stocks[0]["symbol"] == "600519"


def test_add_analyze_and_fetch_run(client):
    added = client.post("/api/stocks", json={"symbol": "600519"})
    assert added.status_code == 200

    response = client.post("/api/analyze", json={"symbol": "600519"})
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["run"]["status"] == "success"
    assert detail["report"]["action"] in {"buy", "add", "hold", "reduce", "sell", "watch", "avoid"}
    assert len(detail["trace"]) == 8
    assert detail["report"]["evidence"]

    fetched = client.get(f"/api/runs/{detail['run']['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["report"]["symbol"] == "600519"


def test_chat_is_persisted(client):
    detail = client.post("/api/analyze", json={"symbol": "600519"}).json()
    run_id = detail["run"]["id"]
    response = client.post(
        "/api/chat", json={"run_id": run_id, "message": "止损位是多少？"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "止损" in payload["answer"]
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][1]["role"] == "assistant"


def test_invalid_symbol_returns_400(client):
    response = client.post("/api/stocks", json={"symbol": "NOT_A_STOCK"})
    assert response.status_code == 400


def test_eval_endpoints(client):
    run = client.post("/api/evals/run")
    assert run.status_code == 200, run.text
    data = run.json()
    assert data["cases"] == 8
    assert data["schema_validity"] == 1.0

    latest = client.get("/api/evals/latest")
    assert latest.status_code == 200
    assert latest.json()["available"] is True


def test_backtest_endpoints(client):
    run = client.post("/api/backtest/run")
    assert run.status_code == 200, run.text
    data = run.json()
    assert data["signals"] > 0
    assert 0 <= data["direction_hit_rate"] <= 1
    assert data["results"]

    latest = client.get("/api/backtest/latest")
    assert latest.status_code == 200
    assert json.loads(json.dumps(latest.json()))["available"] is True
