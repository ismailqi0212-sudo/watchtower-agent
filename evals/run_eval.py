#!/usr/bin/env python3
"""Golden-set evaluation for the review agent.

The point is not a vanity benchmark: it catches the failure modes that make
agent demos look good but behave badly in production — skipped tools, invalid
JSON, claims without evidence, and action/score drift.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agent.runner import run_agent  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.data.provider import DemoProvider  # noqa: E402
from app.schemas import DecisionReport  # noqa: E402


def _p95(values: List[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return float(ordered[index])


def run_golden_eval(
    provider: DemoProvider,
    settings: Settings,
    golden_path: Path,
    output_path: Path,
    live: bool = False,
) -> Dict[str, Any]:
    # Reproducibility is the point of the golden set. Unless explicitly asked
    # for a live run, force the deterministic policy even if the app has an
    # LLM key configured.
    if not live and settings.llm_enabled:
        settings = dataclasses.replace(settings, llm_api_key="")
    cases = json.loads(Path(golden_path).read_text(encoding="utf-8"))
    results: List[Dict[str, Any]] = []
    coverage_values: List[float] = []
    schema_values: List[float] = []
    action_values: List[float] = []
    evidence_values: List[float] = []
    latencies: List[int] = []

    for case in cases:
        started = time.perf_counter()
        issues: List[str] = []
        try:
            stock = provider.resolve(case["symbol"])
            as_of = provider.latest_date(stock["symbol"])
            result = run_agent(provider, stock, as_of, settings)
            latency = int((time.perf_counter() - started) * 1000)
            called_tools = {item["tool"] for item in result.trace if item.get("kind") == "tool"}
            required = case.get("required_tools", [])
            coverage = (
                sum(1 for tool in required if tool in called_tools) / len(required)
                if required
                else 1.0
            )
            if coverage < 1.0:
                missing = [tool for tool in required if tool not in called_tools]
                issues.append(f"missing tools: {missing}")

            report = result.report
            valid = True
            try:
                DecisionReport.model_validate(report)
            except Exception as exc:
                valid = False
                issues.append(f"schema invalid: {exc}")

            valid_ids = {item["id"] for item in report.get("evidence", [])}
            claims = report.get("thesis", [])
            evidenced = sum(
                1
                for item in claims
                if any(eid in valid_ids for eid in item.get("evidence_ids", []))
            )
            evidence_coverage = evidenced / len(claims) if claims else 0.0
            if evidence_coverage < 0.8:
                issues.append(f"evidence coverage {evidence_coverage:.0%}")

            kinds = {item.get("kind") for item in report.get("evidence", [])}
            for kind in case.get("must_have_evidence_kinds", []):
                if kind not in kinds:
                    issues.append(f"missing evidence kind: {kind}")

            expected_actions = case.get("expected_actions", [])
            action_ok = not expected_actions or report.get("action") in expected_actions
            if not action_ok:
                issues.append(
                    f"action {report.get('action')} not in {expected_actions}"
                )

            max_steps = case.get("max_steps", settings.agent_max_steps + 6)
            if len(result.trace) > max_steps:
                issues.append(f"trace steps {len(result.trace)} > {max_steps}")

            if case.get("expect_partial_data"):
                if report.get("data_quality") == "ok":
                    issues.append("expected partial data quality, got ok")

            passed = (
                coverage >= 1.0
                and valid
                and evidence_coverage >= 0.8
                and action_ok
                and not any("missing evidence kind" in item for item in issues)
            )
            results.append(
                {
                    "id": case["id"],
                    "symbol": stock["symbol"],
                    "label": case.get("label", ""),
                    "passed": passed,
                    "required_tool_coverage": round(coverage, 3),
                    "schema_valid": valid,
                    "action": report.get("action"),
                    "score": report.get("score"),
                    "evidence_coverage": round(evidence_coverage, 3),
                    "data_quality": report.get("data_quality"),
                    "steps": len(result.trace),
                    "latency_ms": latency,
                    "issues": issues,
                }
            )
            coverage_values.append(coverage)
            schema_values.append(1.0 if valid else 0.0)
            action_values.append(1.0 if action_ok else 0.0)
            evidence_values.append(evidence_coverage)
            latencies.append(latency)
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            issues.append(f"run failed: {exc}")
            results.append(
                {
                    "id": case.get("id", "unknown"),
                    "symbol": case.get("symbol", ""),
                    "label": case.get("label", ""),
                    "passed": False,
                    "required_tool_coverage": 0.0,
                    "schema_valid": False,
                    "action": "",
                    "score": 0,
                    "evidence_coverage": 0.0,
                    "data_quality": "missing",
                    "steps": 0,
                    "latency_ms": latency,
                    "issues": issues,
                }
            )
            coverage_values.append(0.0)
            schema_values.append(0.0)
            action_values.append(0.0)
            evidence_values.append(0.0)
            latencies.append(latency)

    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": settings.mode,
        "cases": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "required_tool_coverage": round(
            sum(coverage_values) / len(coverage_values), 3
        )
        if coverage_values
        else 0.0,
        "schema_validity": round(sum(schema_values) / len(schema_values), 3)
        if schema_values
        else 0.0,
        "action_accuracy": round(sum(action_values) / len(action_values), 3)
        if action_values
        else 0.0,
        "evidence_coverage": round(sum(evidence_values) / len(evidence_values), 3)
        if evidence_values
        else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "p95_latency_ms": _p95(latencies),
        "results": results,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="evaluate with the configured LLM")
    args = parser.parse_args()
    settings = get_settings()
    provider = DemoProvider(settings.demo_dir)
    summary = run_golden_eval(
        provider,
        settings,
        ROOT / "evals" / "golden_set.json",
        ROOT / "evals" / "results" / "golden_latest.json",
        live=args.live,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    for item in summary["results"]:
        mark = "PASS" if item["passed"] else "FAIL"
        print(f"{mark} {item['id']} {item['symbol']} {item['action']} score={item['score']} {item['issues']}")


if __name__ == "__main__":
    main()
