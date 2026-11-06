"""FastAPI application factory and production static-file server."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.config import Settings, get_settings
from app.data.factory import build_provider
from app.db import Database
from app.documents.service import DocumentService
from app.services.analysis import AnalysisService
from app.services.research import ResearchService
from app.services.research_reports import ResearchReportService

VERSION = "0.1.0"


def create_app(
    settings: Optional[Settings] = None,
    db: Optional[Database] = None,
    provider: Optional[Any] = None,
) -> FastAPI:
    settings = settings or get_settings()
    database = db or Database(settings.db_path)
    database.init_schema()
    market_provider = provider or build_provider(settings)
    service = AnalysisService(database, market_provider, settings)
    service.seed()

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    document_service = DocumentService(database, settings.uploads_dir)
    research_service = ResearchService(database, document_service, market_provider)
    report_service = ResearchReportService(database, research_service)

    app = FastAPI(
        title="Watchtower",
        description="A lightweight, evidence-bound watchlist review agent.",
        version=VERSION,
    )
    app.state.service = service
    app.state.research = research_service
    app.state.research_reports = report_service
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    dist = Path(settings.web_dist)
    assets = dist / "assets"
    if dist.exists() and (dist / "index.html").exists():
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}")
        def serve_spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    else:

        @app.get("/")
        def dev_root():
            return {
                "message": "Watchtower API is running. Frontend not built yet.",
                "docs": "/docs",
                "api": "/api/health",
                "hint": "cd web && npm install && npm run dev",
            }

    return app


app = create_app()
