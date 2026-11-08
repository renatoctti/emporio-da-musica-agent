"""`python -m emporio.evals`: run the cases against a real model and print a report."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from emporio.config import load_settings
from emporio.evals.cases import CASES
from emporio.evals.runner import gate, run_case, with_model
from emporio.llm import MissingApiKeyError, OpenAIChatClient


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio.evals", description=__doc__)
    parser.add_argument("--model", help="override LLM_MODEL for this run")
    parser.add_argument(
        "--case", action="append", metavar="ID", help="run only this case (repeatable)"
    )
    parser.add_argument("--tag", help="run only the cases with this tag")
    parser.add_argument("--report", metavar="FILE", help="write the full JSON report here")
    parser.add_argument(
        "--baseline",
        metavar="FILE",
        help="a previous JSON report; a case that passed there and fails now blocks the run",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        metavar="RATE",
        help="block the run when the pass rate (0 to 1) is under this floor",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    settings = with_model(load_settings(), args.model)
    try:
        client = OpenAIChatClient(settings)
    except MissingApiKeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    cases = [
        c
        for c in CASES
        if (not args.case or c.id in args.case) and (not args.tag or args.tag in c.tags)
    ]
    results = []
    for case in cases:
        result = run_case(case, client, settings)
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {case.id} tools={result.tool_names}")
        for failure in result.failures:
            print(f"     - {failure}")

    passed = sum(r.passed for r in results)
    calls = sum(len(r.tool_names) for r in results)
    print(f"\n{passed}/{len(results)} passed, {calls} tool calls, model {settings.llm_model}")
    print(f"tokens: {client.usage['prompt_tokens']} in, {client.usage['completion_tokens']} out")
    mean_latency = sum(r.latency_ms for r in results) / len(results) if results else 0
    print(f"mean latency per case: {mean_latency:.0f} ms")

    report = {
        "model": settings.llm_model,
        "date": date.today().isoformat(),
        "passed": passed,
        "total": len(results),
        "tool_calls": calls,
        "usage": client.usage,
        "mean_latency_ms": round(mean_latency),
        "cases": [
            {
                "id": r.case_id,
                "passed": r.passed,
                "failures": r.failures,
                "tools": r.tool_names,
                "replies": r.replies,
                "latency_ms": r.latency_ms,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
            }
            for r in results
        ],
    }
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"report written to {args.report}")

    baseline = None
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    problems = gate(report, baseline, args.fail_under)
    for problem in problems:
        print(f"GATE: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
