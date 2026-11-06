#!/usr/bin/env python3
"""Create a demo database and a few decision cards for the UI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.data.factory import build_provider  # noqa: E402
from app.db import Database  # noqa: E402
from app.services.analysis import AnalysisService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="analyze every demo stock")
    parser.add_argument("--limit", type=int, default=3, help="number of stocks")
    args = parser.parse_args()

    settings = get_settings()
    db = Database(settings.db_path)
    db.init_schema()
    provider = build_provider(settings)
    service = AnalysisService(db, provider, settings)
    service.seed()

    stocks = db.list_stocks()
    targets = stocks if args.all else stocks[: args.limit]
    for stock in targets:
        print(f"analyzing {stock['symbol']} {stock['name']}...")
        detail = service.analyze(stock["symbol"], trigger="seed")
        report = detail["report"]
        print(f"  -> {report['action']} score={report['score']} evidence={len(report['evidence'])}")
    print(f"database: {settings.db_path}")
    print(f"stocks: {len(stocks)}")


if __name__ == "__main__":
    main()
