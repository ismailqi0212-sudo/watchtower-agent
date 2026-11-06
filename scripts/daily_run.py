#!/usr/bin/env python3
"""Daily job entry point (GitHub Actions / cron / systemd timer).

Runs every watchlist stock, writes a JSON artifact, and exits non-zero only if
every analysis failed. A single bad symbol must not break the whole batch.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.data.factory import build_provider  # noqa: E402
from app.db import Database  # noqa: E402
from app.services.analysis import AnalysisService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", default="schedule")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    settings = get_settings()
    db = Database(settings.db_path)
    db.init_schema()
    provider = build_provider(settings)
    service = AnalysisService(db, provider, settings)
    service.seed()

    stocks = db.list_stocks()
    if not stocks:
        print("watchlist is empty; nothing to do")
        return

    results = []
    failures = 0
    for stock in stocks:
        try:
            detail = service.analyze(stock["symbol"], trigger=args.trigger)
            report = detail["report"]
            results.append(
                {
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "run_id": detail["run"]["id"],
                    "action": report["action"],
                    "score": report["score"],
                    "confidence": report["confidence"],
                    "data_quality": report["data_quality"],
                    "summary": report["summary"],
                }
            )
            print(
                f"{stock['symbol']} {stock['name']}: {report['action']} "
                f"score={report['score']} quality={report['data_quality']}"
            )
        except Exception as exc:
            failures += 1
            print(f"{stock['symbol']} {stock['name']}: FAILED {exc}", file=sys.stderr)

    payload = {
        "date": date.today().isoformat(),
        "trigger": args.trigger,
        "mode": settings.mode,
        "total": len(stocks),
        "succeeded": len(results),
        "failed": failures,
        "results": results,
    }
    out = Path(args.out) if args.out else ROOT / "reports" / f"daily-{payload['date']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"artifact: {out}")

    if failures == len(stocks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
