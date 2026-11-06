"""Application configuration.

The project is intentionally dependency-light: it runs fully offline in demo
mode, and switches to an OpenAI-compatible chat model only when a key is set.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - environment without dotenv
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "watchtower.db"
DEFAULT_DEMO_DIR = BASE_DIR / "data" / "demo"
DEFAULT_WEB_DIST = BASE_DIR / "web" / "dist"
DEFAULT_UPLOADS_DIR = BASE_DIR / "data" / "uploads"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "Watchtower"
    db_path: Path = DEFAULT_DB_PATH
    demo_dir: Path = DEFAULT_DEMO_DIR
    web_dist: Path = DEFAULT_WEB_DIST
    uploads_dir: Path = DEFAULT_UPLOADS_DIR

    data_provider: str = "demo"
    news_provider: str = "auto"
    tavily_api_key: str = ""
    stock_list: List[str] = field(default_factory=list)

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2

    agent_max_steps: int = 8
    agent_timeout_seconds: int = 90
    seed_demo: bool = True

    cors_origins: List[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key.strip())

    @property
    def mode(self) -> str:
        return "llm" if self.llm_enabled else "demo"


def _split_origins(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        db_path=Path(os.getenv("WATCHTOWER_DB", str(DEFAULT_DB_PATH))).expanduser(),
        demo_dir=Path(os.getenv("WATCHTOWER_DEMO_DIR", str(DEFAULT_DEMO_DIR))).expanduser(),
        web_dist=Path(os.getenv("WATCHTOWER_WEB_DIST", str(DEFAULT_WEB_DIST))).expanduser(),
        uploads_dir=Path(os.getenv("WATCHTOWER_UPLOADS_DIR", str(DEFAULT_UPLOADS_DIR))).expanduser(),
        data_provider=(os.getenv("DATA_PROVIDER") or "demo").strip().lower(),
        news_provider=(os.getenv("NEWS_PROVIDER") or "auto").strip().lower(),
        tavily_api_key=(os.getenv("TAVILY_API_KEY") or "").strip(),
        stock_list=[
            item.strip()
            for item in re.split(r"[,\s;\uFF0C\u3001]+", os.getenv("STOCK_LIST") or "")
            if item.strip()
        ],
        llm_api_key=os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip(),
        llm_base_url=(
            os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).strip(),
        llm_model=(os.getenv("LLM_MODEL") or "gpt-4o-mini").strip(),
        llm_temperature=_env_float("LLM_TEMPERATURE", 0.2),
        agent_max_steps=_env_int("AGENT_MAX_STEPS", 8),
        agent_timeout_seconds=_env_int("AGENT_TIMEOUT_SECONDS", 90),
        seed_demo=_env_bool("SEED_DEMO", True),
        cors_origins=_split_origins(
            os.getenv(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            )
        ),
    )
