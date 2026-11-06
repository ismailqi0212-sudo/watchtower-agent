"""HTTP API consumed by the React workspace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

from app.config import BASE_DIR, Settings
from app.schemas import (
    AnalyzeRequest,
    ChatRequest,
    ResearchAskRequest,
    ResearchCandidateConfirm,
    ResearchReportCreate,
    ResearchReportUpdate,
    ResearchSessionCreate,
    StockCreate,
)
from app.services.analysis import AnalysisError, AnalysisService, NotFoundError
from app.services.research import ResearchService

router = APIRouter(prefix="/api")
RESULTS_DIR = BASE_DIR / "evals" / "results"


def _service(request: Request) -> AnalysisService:
    return request.app.state.service


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _research(request: Request) -> ResearchService:
    return request.app.state.research


def _read_result(name: str) -> Dict[str, Any]:
    path = RESULTS_DIR / name
    if not path.exists():
        return {"available": False, "message": "尚未运行，点击页面上的运行按钮生成结果。"}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"available": True, **data}


@router.get("/health")
def health(request: Request) -> Dict[str, Any]:
    settings = _settings(request)
    service = _service(request)
    return {
        "status": "ok",
        "mode": settings.mode,
        "model": settings.llm_model if settings.llm_enabled else "demo-policy",
        "provider": service.provider.name,
        "news_provider": "tavily" if settings.tavily_api_key else "native",
        "stocks": len(service.db.list_stocks()),
    }


@router.get("/meta")
def meta(request: Request) -> Dict[str, Any]:
    settings = _settings(request)
    service = _service(request)
    return {
        "app": "Watchtower",
        "mode": settings.mode,
        "provider": service.provider.name,
        "as_of": service.provider.meta.get("as_of"),
        "disclaimer": "公开行情、新闻与年报可能存在延迟或缺失；本项目仅供研究与演示，不构成投资建议。",
        "tools": [
            "get_quote",
            "get_history",
            "compute_indicators",
            "search_news",
            "get_fundamentals",
            "get_benchmark",
        ],
    }


@router.get("/stocks")
def list_stocks(request: Request) -> Dict[str, Any]:
    service = _service(request)
    return {"items": service.list_watchlist()}


@router.post("/stocks")
def add_stock(payload: StockCreate, request: Request) -> Dict[str, Any]:
    service = _service(request)
    try:
        stock = service.add_stock(payload.symbol, payload.name)
    except AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": stock}


@router.delete("/stocks/{symbol}")
def delete_stock(symbol: str, request: Request) -> Dict[str, Any]:
    _service(request).remove_stock(symbol)
    return {"ok": True}


@router.get("/runs")
def list_runs(
    request: Request,
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> Dict[str, Any]:
    return {"items": _service(request).list_runs(symbol=symbol, limit=limit)}


@router.post("/analyze")
def analyze(payload: AnalyzeRequest, request: Request) -> Dict[str, Any]:
    service = _service(request)
    try:
        return service.analyze(payload.symbol, trigger=payload.trigger)
    except AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> Dict[str, Any]:
    try:
        return _service(request).get_run(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/chat")
def chat(payload: ChatRequest, request: Request) -> Dict[str, Any]:
    try:
        return _service(request).chat(payload.run_id, payload.message)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/evals/latest")
def latest_eval() -> Dict[str, Any]:
    return _read_result("golden_latest.json")


@router.post("/evals/run")
def run_eval(request: Request) -> Dict[str, Any]:
    from evals.run_eval import run_golden_eval

    settings = _settings(request)
    from app.data.provider import DemoProvider

    # Golden-set evaluation is fixture-based by design: it must stay
    # reproducible even when the live app uses AKShare or yfinance.
    provider = DemoProvider(settings.demo_dir)
    summary = run_golden_eval(
        provider,
        settings,
        BASE_DIR / "evals" / "golden_set.json",
        RESULTS_DIR / "golden_latest.json",
    )
    return {"available": True, **summary}


@router.get("/backtest/latest")
def latest_backtest() -> Dict[str, Any]:
    return _read_result("backtest_latest.json")


@router.post("/backtest/run")
def run_backtest(request: Request) -> Dict[str, Any]:
    from evals.run_backtest import run_backtest as execute_backtest

    settings = _settings(request)
    from app.data.provider import DemoProvider

    provider = DemoProvider(settings.demo_dir)
    summary = execute_backtest(
        provider,
        settings,
        RESULTS_DIR / "backtest_latest.json",
    )
    return {"available": True, **summary}


# ---------------------------------------------------------------------------
# research / document APIs
# ---------------------------------------------------------------------------
@router.post("/research/bootstrap")
def research_bootstrap(request: Request) -> Dict[str, Any]:
    """Load the four sample annual reports and build the first worksheet.

    This is intentionally idempotent. Later the same endpoint can be replaced
    by an upload/session endpoint without changing the read model.
    """
    service = _research(request)
    return service.bootstrap_yanji()


@router.post("/research/sessions")
def research_create(payload: ResearchSessionCreate, request: Request) -> Dict[str, Any]:
    try:
        return _research(request).ensure_session(
            payload.symbol, payload.name, payload.question
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/sessions")
def research_sessions(
    request: Request, symbol: Optional[str] = Query(default=None)
) -> Dict[str, Any]:
    return {"items": _research(request).list_sessions(symbol)}


@router.get("/research/sessions/{session_id}")
def research_session(session_id: str, request: Request) -> Dict[str, Any]:
    item = _research(request).get_session(session_id)
    if not item:
        raise HTTPException(status_code=404, detail="研究不存在")
    return item


@router.post("/research/sessions/{session_id}/documents")
async def research_upload(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    year: Optional[int] = Form(default=None),
) -> Dict[str, Any]:
    settings = _settings(request)
    filename = Path(file.filename or "document.pdf").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持 PDF")
    if year is None:
        import re

        match = re.search(r"(20\d{2})", filename)
        year = int(match.group(1)) if match else None
    target = settings.uploads_dir / f"upload_{session_id[:8]}_{filename}"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            handle.write(chunk)
    try:
        return _research(request).add_document(session_id, target, year=year, name=filename)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/sessions/{session_id}/reports")
def research_reports(session_id: str, request: Request) -> Dict[str, Any]:
    service = request.app.state.research_reports
    return {"items": service.db.list_research_reports(session_id)}


@router.post("/research/sessions/{session_id}/reports")
def research_report_create(
    session_id: str, payload: ResearchReportCreate, request: Request
) -> Dict[str, Any]:
    service = request.app.state.research_reports
    try:
        return service.generate(
            session_id,
            template=payload.template,
            metric_keys=payload.metric_keys,
            message_ids=payload.message_ids,
            snippets=payload.snippets,
            title=payload.title,
            settings=_settings(request),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/reports/{report_id}")
def research_report_get(report_id: str, request: Request) -> Dict[str, Any]:
    report = request.app.state.research_reports.db.get_research_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="研报不存在")
    return report


@router.put("/research/reports/{report_id}")
def research_report_update(
    report_id: str, payload: ResearchReportUpdate, request: Request
) -> Dict[str, Any]:
    service = request.app.state.research_reports
    try:
        return service.update(report_id, payload.title, payload.sections, payload.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研报不存在") from exc


@router.get("/research/reports/{report_id}/versions")
def research_report_versions(report_id: str, request: Request) -> Dict[str, Any]:
    return {"items": request.app.state.research_reports.versions(report_id)}


@router.get("/research/reports/{report_id}/versions/{version}")
def research_report_version(report_id: str, version: int, request: Request) -> Dict[str, Any]:
    item = request.app.state.research_reports.db.get_report_version(report_id, version)
    if not item:
        raise HTTPException(status_code=404, detail="版本不存在")
    return item


@router.post("/research/reports/{report_id}/versions/{version}/restore")
def research_report_restore(report_id: str, version: int, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.research_reports.restore(report_id, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="版本不存在") from exc


@router.post("/research/reports/{report_id}/polish")
def research_report_polish(report_id: str, request: Request) -> Dict[str, Any]:
    try:
        return request.app.state.research_reports.polish(report_id, _settings(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研报不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/research/reports/{report_id}/markdown")
def research_report_markdown(report_id: str, request: Request) -> PlainTextResponse:
    service = request.app.state.research_reports
    report = service.db.get_research_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="研报不存在")
    from urllib.parse import quote

    filename = quote(f"{report['title']}.md", safe="")
    return PlainTextResponse(
        service.markdown(report),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/research/sessions/{session_id}/metrics/confirm")
def research_confirm_metrics(
    session_id: str, payload: ResearchCandidateConfirm, request: Request
) -> Dict[str, Any]:
    try:
        return _research(request).confirm_candidates(session_id, payload.ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究不存在") from exc


@router.post("/research/sessions/{session_id}/ask")
def research_ask(session_id: str, payload: ResearchAskRequest, request: Request) -> Dict[str, Any]:
    try:
        return _research(request).ask(session_id, payload.question, _settings(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/documents/{document_id}/file")
def document_file(document_id: str, request: Request) -> FileResponse:
    service = _research(request).documents
    try:
        path = service.file_path(document_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/documents/{document_id}/pages/{page}.png")
def document_page_png(document_id: str, page: int, request: Request) -> Response:
    service = _research(request).documents
    try:
        content = service.render_page(document_id, page)
    except (FileNotFoundError, IndexError) as exc:
        raise HTTPException(status_code=404, detail="页面不存在") from exc
    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
