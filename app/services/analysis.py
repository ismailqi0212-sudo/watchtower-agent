"""Application service: orchestration, persistence and chat."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from app.agent.runner import AgentResult, run_agent
from app.config import Settings
from app.data.provider import UnknownSymbolError, normalize_symbol
from app.db import Database
from app.schemas import ACTION_LABELS
from app.services.chat import demo_answer, llm_answer
from app.services.reporting import render_markdown


class AnalysisError(RuntimeError):
    pass


class NotFoundError(RuntimeError):
    pass


class AnalysisService:
    def __init__(self, db: Database, provider: Any, settings: Settings):
        self.db = db
        self.provider = provider
        self.settings = settings

    # ------------------------------------------------------------------
    # watchlist
    # ------------------------------------------------------------------
    def seed(self) -> None:
        if self.db.count_stocks() > 0:
            return

        # Explicit STOCK_LIST is the deployment-friendly path: it works for
        # GitHub Actions, fresh containers and mixed A-share/US watchlists.
        if self.settings.stock_list:
            for raw in self.settings.stock_list:
                try:
                    stock = self.provider.resolve(raw)
                except Exception:
                    continue
                self.db.add_stock(
                    symbol=stock["symbol"],
                    name=stock["name"],
                    market=stock.get("market", "cn"),
                    industry=stock.get("industry", ""),
                )
            return

        if not self.settings.seed_demo:
            return
        for stock in self.provider.list_stocks():
            self.db.add_stock(
                symbol=stock["symbol"],
                name=stock["name"],
                market=stock.get("market", "cn"),
                industry=stock.get("industry", ""),
            )

    def add_stock(self, raw: str, name: Optional[str] = None) -> Dict[str, Any]:
        try:
            stock = self.provider.resolve(raw)
        except UnknownSymbolError as exc:
            raise AnalysisError(str(exc)) from exc
        self.db.add_stock(
            symbol=stock["symbol"],
            name=name or stock["name"],
            market=stock.get("market", "cn"),
            industry=stock.get("industry", ""),
        )
        return self.db.get_stock(stock["symbol"]) or {}

    def remove_stock(self, symbol: str) -> None:
        self.db.remove_stock(normalize_symbol(symbol))

    def list_watchlist(self) -> List[Dict[str, Any]]:
        stocks = self.db.list_stocks()

        def load(stock: Dict[str, Any]) -> Dict[str, Any]:
            symbol = stock["symbol"]
            try:
                bars = self.provider.get_history(symbol, days=40)
                quote = _quote_from_bars(symbol, bars, getattr(self.provider, "name", "provider"))
                sparkline = [bar["close"] for bar in bars[-30:]]
            except Exception:
                quote = {}
                sparkline = []
            latest = self.db.latest_report(symbol)
            return {
                **stock,
                "quote": quote,
                "sparkline": sparkline,
                "latest_report": self._report_summary(latest) if latest else None,
            }

        # The live providers fetch one request per symbol; a small thread pool
        # keeps the initial workspace load acceptable without hammering the
        # upstream data source.
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(stocks)))) as pool:
            return list(pool.map(load, stocks))

    def _report_summary(self, report: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": report.get("id"),
            "run_id": report.get("run_id"),
            "as_of": report.get("as_of"),
            "action": report.get("action"),
            "action_label": ACTION_LABELS.get(report.get("action", ""), report.get("action")),
            "score": report.get("score"),
            "confidence": report.get("confidence"),
            "data_quality": report.get("data_quality"),
            "summary": report.get("summary"),
            "plan": report.get("plan"),
            "created_at": report.get("created_at"),
        }

    # ------------------------------------------------------------------
    # analysis
    # ------------------------------------------------------------------
    def analyze(self, raw_symbol: str, trigger: str = "manual") -> Dict[str, Any]:
        try:
            stock = self.provider.resolve(raw_symbol)
        except UnknownSymbolError as exc:
            raise AnalysisError(str(exc)) from exc
        symbol = normalize_symbol(stock["symbol"])
        try:
            as_of = self.provider.latest_date(symbol)
        except Exception as exc:
            raise AnalysisError(f"无法获取 {symbol} 的真实行情：{exc}") from exc
        mode = "llm" if self.settings.llm_enabled else "demo"
        model = self.settings.llm_model if self.settings.llm_enabled else "demo-policy"
        run = self.db.create_run(symbol, mode=mode, model=model, trigger=trigger)
        started = time.perf_counter()
        try:
            result: AgentResult = run_agent(self.provider, stock, as_of, self.settings)
            for item in result.trace:
                self.db.add_trace(
                    run_id=run["id"],
                    step=item.get("step", 0),
                    kind=item.get("kind", "tool"),
                    tool=item.get("tool", ""),
                    args=item.get("args", {}),
                    result=item.get("result", {}),
                    ok=bool(item.get("ok", True)),
                    latency_ms=item.get("latency_ms", 0),
                    summary=item.get("summary", ""),
                    error=item.get("error"),
                )
            report = self.db.save_report(
                run_id=run["id"],
                symbol=symbol,
                report=result.report,
                markdown=render_markdown(result.report),
            )
            latency = int((time.perf_counter() - started) * 1000)
            status = "partial" if result.error else "success"
            self.db.finish_run(
                run["id"],
                status=status,
                latency_ms=latency,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cost_usd=result.cost_usd,
                error=result.error,
            )
            detail = self.get_run(run["id"])
            detail["report"] = report
            return detail
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            self.db.add_trace(
                run_id=run["id"],
                step=99,
                kind="error",
                summary="分析执行失败",
                error=str(exc),
                ok=False,
                latency_ms=latency,
            )
            self.db.finish_run(
                run["id"], status="failed", latency_ms=latency, error=str(exc)
            )
            raise AnalysisError(str(exc)) from exc

    def get_run(self, run_id: str) -> Dict[str, Any]:
        run = self.db.get_run(run_id)
        if not run:
            raise NotFoundError(f"run not found: {run_id}")
        report = self.db.get_report_by_run(run_id)
        return {
            "run": run,
            "report": report,
            "trace": self.db.list_traces(run_id),
            "chat": self.db.list_chat(run_id),
        }

    def list_runs(self, symbol: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        return self.db.list_runs(symbol=symbol, limit=limit)

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------
    def chat(self, run_id: str, message: str) -> Dict[str, Any]:
        detail = self.get_run(run_id)
        report = detail.get("report")
        if not report:
            raise NotFoundError(f"report not found for run: {run_id}")
        message = (message or "").strip()
        if not message:
            raise AnalysisError("message is empty")
        history = detail.get("chat", [])
        self.db.add_chat(run_id, "user", message)
        answer = ""
        if self.settings.llm_enabled:
            try:
                answer = llm_answer(self.settings, report, history, message)
            except Exception:
                answer = demo_answer(report, message)
        else:
            answer = demo_answer(report, message)
        self.db.add_chat(run_id, "assistant", answer)
        return {
            "answer": answer,
            "messages": self.db.list_chat(run_id),
        }


def _quote_from_bars(symbol: str, bars: List[Dict[str, Any]], source: str) -> Dict[str, Any]:
    if not bars:
        return {}
    last = bars[-1]
    prev = bars[-2] if len(bars) > 1 else last
    change_pct = (
        round((last["close"] / prev["close"] - 1) * 100, 2) if prev.get("close") else 0.0
    )
    return {
        "symbol": symbol,
        "as_of": last.get("date", ""),
        "price": last.get("close"),
        "open": last.get("open"),
        "high": last.get("high"),
        "low": last.get("low"),
        "prev_close": prev.get("close"),
        "change_pct": change_pct,
        "volume": last.get("volume", 0),
        "source": source,
        "data_quality": "ok",
    }
