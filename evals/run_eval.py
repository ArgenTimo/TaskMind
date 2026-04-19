#!/usr/bin/env python3
"""Run lightweight property checks against POST /process via TestClient.

Default: forces LLM_MODE=stub so cases stay deterministic (set EVAL_REAL=1 to use env LLM_MODE).

Usage (from repository root, with backend deps installed):
  PYTHONPATH=backend python3 evals/run_eval.py

Docker Compose (mount repo root into the container):
  docker compose run --rm -e PYTHONPATH=/project/backend -v "$(pwd):/project" -w /project \\
    backend python3 evals/run_eval.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Repository root: evals/
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_ROOT / "backend"))

# Cases assume stub output. Set EVAL_REAL=1 to keep LLM_MODE from the environment instead.
if os.environ.get("EVAL_REAL") != "1":
    os.environ["LLM_MODE"] = "stub"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("cases file must be a JSON array")
    return data


def _check_case(
    client: TestClient,
    case: dict[str, Any],
) -> tuple[bool, str]:
    cid = case.get("id", "?")
    text = case.get("text", "")
    mode = case.get("mode", "analyze")
    expect = case.get("expect", {})
    exp_status = int(expect.get("status", 200))

    response = client.post(
        "/process",
        json={"text": text, "mode": mode},
    )

    if response.status_code != exp_status:
        return False, f"HTTP {response.status_code} (expected {exp_status})"

    if exp_status != 200:
        return True, "ok"

    body = response.json()
    if expect.get("has_keys"):
        for key in expect["has_keys"]:
            if key not in body:
                return False, f"missing key {key!r}"

    if expect.get("summary_nonempty"):
        s = body.get("summary")
        if not isinstance(s, str) or not s.strip():
            return False, "summary missing or whitespace-only"

    if expect.get("intent_nonempty"):
        s = body.get("intent")
        if not isinstance(s, str) or not s.strip():
            return False, "intent missing or whitespace-only"

    if expect.get("reply_nonempty"):
        s = body.get("reply")
        if not isinstance(s, str) or not s.strip():
            return False, "reply missing or whitespace-only"

    if expect.get("tasks_is_list"):
        if not isinstance(body.get("tasks"), list):
            return False, "tasks is not a list"

    if expect.get("tasks_nonempty"):
        tasks = body.get("tasks")
        if not isinstance(tasks, list) or len(tasks) == 0:
            return False, "tasks empty or not a list"
        for i, t in enumerate(tasks):
            if not isinstance(t, str) or not t.strip():
                return False, f"task item {i} empty or not a non-empty string"

    if expect.get("tasks_no_empty_items"):
        tasks = body.get("tasks")
        if not isinstance(tasks, list):
            return False, "tasks is not a list"
        for i, t in enumerate(tasks):
            if not isinstance(t, str) or not t.strip():
                return False, f"task item {i} is empty after trim (guardrail check)"

    if "summary_max_length" in expect:
        cap = int(expect["summary_max_length"])
        s = body.get("summary", "")
        if not isinstance(s, str):
            return False, "summary is not a string"
        if len(s) > cap:
            return False, f"summary length {len(s)} > {cap}"

    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TaskMind /process eval cases")
    parser.add_argument(
        "--cases",
        type=Path,
        default=_ROOT / "evals" / "cases.json",
        help="Path to cases JSON (default: evals/cases.json)",
    )
    args = parser.parse_args()

    cases_path = args.cases.resolve()
    cases = _load_cases(cases_path)
    client = TestClient(app)

    results: list[tuple[str, str, bool, str]] = []
    for case in cases:
        cid = str(case.get("id", "?"))
        desc = str(case.get("description", ""))
        ok, detail = _check_case(client, case)
        results.append((cid, desc, ok, detail))

    passed = sum(1 for _, _, ok, _ in results if ok)
    total = len(results)
    width = max(len(r[0]) for r in results) if results else 10

    print(f"TaskMind eval  ({cases_path.name})  LLM_MODE={os.environ.get('LLM_MODE', 'stub')!r}")
    print("-" * 72)
    for cid, desc, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        tail = detail if not ok else (desc[:64] + ("…" if len(desc) > 64 else "") if desc else "")
        print(f"{cid:<{width}}  {status}  {tail}")
    print("-" * 72)
    print(f"Total: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
