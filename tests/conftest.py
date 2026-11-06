from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import BASE_DIR, Settings
from app.data.provider import DemoProvider
from app.db import Database
from app.main import create_app


@pytest.fixture()
def demo_dir() -> Path:
    return BASE_DIR / "data" / "demo"


@pytest.fixture()
def settings(tmp_path: Path, demo_dir: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "test.db",
        demo_dir=demo_dir,
        web_dist=tmp_path / "missing-dist",
        seed_demo=True,
    )


@pytest.fixture()
def provider(demo_dir: Path) -> DemoProvider:
    return DemoProvider(demo_dir)


@pytest.fixture()
def db(settings: Settings) -> Database:
    database = Database(settings.db_path)
    database.init_schema()
    return database


@pytest.fixture()
def client(settings: Settings, db: Database, provider: DemoProvider) -> TestClient:
    app = create_app(settings=settings, db=db, provider=provider)
    return TestClient(app)
