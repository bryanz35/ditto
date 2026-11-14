"""Run every prompt in evals/prompts.yaml N times through the real API and write a pass-rate CSV.

    uv run --env-file .env python -m evals.run_evals --runs 5 --out evals/results.csv

Costs money: every run calls the model. A run passes when every pipeline stage and the checks end
passed (simulate may be skipped), the event stream is well formed and the run directory satisfies
every invariant in tests/integration/invariants.py.
"""

import argparse
import asyncio
import csv
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.contracts.runner import run_dir_for
from backend.contracts.spec import UserContext
from tests.e2e.harness import api_client, start_run, wait_for_done
from tests.integration import invariants as inv

PROMPTS = Path(__file__).with_name("prompts.yaml")
COLUMNS = ["prompt_id", "run", "run_id", "passed", "seconds", "problems"]


@dataclass
class Outcome:
    run_id: str
    problems: list[str]
    seconds: float


RunOnce = Callable[[str, UserContext], Awaitable[Outcome]]


def load_prompts(path: Path = PROMPTS) -> list[dict]:
    return [p for p in yaml.safe_load(path.read_text()) if p.get("prompt")]


async def run_once(prompt: str, user: UserContext) -> Outcome:
    start = time.monotonic()
    async with api_client() as client:
        run_id = await start_run(client, prompt, user)
        events = await wait_for_done(run_id)
    problems = inv.check_events(events) + inv.failed_stages(events)
    problems += inv.check_run_dir(run_dir_for(run_id))
    return Outcome(run_id, problems, round(time.monotonic() - start, 1))


async def evaluate(
    prompts: list[dict], runs: int, run: RunOnce = run_once
) -> list[dict]:
    """One row per run; a run that raises counts as a failure with the exception as its problem."""
    rows = []
    for p in prompts:
        user = UserContext.model_validate(p.get("user", {}))
        for i in range(1, runs + 1):
            try:
                outcome = await run(p["prompt"], user)
            # A crashed run is a failed run: record it and keep evaluating the rest.
            except Exception as e:  # noqa: BLE001
                outcome = Outcome("", [f"{type(e).__name__}: {e}"], 0.0)
            rows.append(
                {
                    "prompt_id": p["id"],
                    "run": i,
                    "run_id": outcome.run_id,
                    "passed": not outcome.problems,
                    "seconds": outcome.seconds,
                    "problems": "; ".join(outcome.problems),
                }
            )
    return rows


def pass_rates(rows: list[dict]) -> dict[str, float]:
    ids = dict.fromkeys(r["prompt_id"] for r in rows)
    return {
        pid: sum(r["passed"] for r in rows if r["prompt_id"] == pid)
        / sum(r["prompt_id"] == pid for r in rows)
        for pid in ids
    }


def write_csv(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--prompts", type=Path, default=PROMPTS)
    parser.add_argument("--out", type=Path, default=Path("evals/results.csv"))
    args = parser.parse_args(argv)
    rows = asyncio.run(evaluate(load_prompts(args.prompts), args.runs))
    write_csv(rows, args.out)
    for pid, rate in pass_rates(rows).items():
        print(f"{pid}: {rate:.0%} of {args.runs} runs passed")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
