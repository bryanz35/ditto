"""The eval runner's bookkeeping, with a fake run in place of a real model run."""

import csv

from evals.run_evals import Outcome, evaluate, load_prompts, pass_rates, write_csv


def test_prompts_file_loads():
    prompts = load_prompts()
    assert "plant_monitor" in {p["id"] for p in prompts}
    assert all(p["prompt"] for p in prompts)  # empty placeholders are skipped


async def test_pass_rate_csv(tmp_path):
    results = iter(
        [
            Outcome("r1", [], 1.0),
            Outcome("r2", ["bom: failed"], 2.0),
            RuntimeError("boom"),
        ]
    )

    async def fake_run(prompt, user):
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    prompts = [{"id": "a", "prompt": "x", "user": {"budget_usd": 10}}]
    rows = await evaluate(prompts, 3, fake_run)
    assert [r["passed"] for r in rows] == [True, False, False]
    assert rows[2]["problems"] == "RuntimeError: boom"
    assert pass_rates(rows) == {"a": 1 / 3}

    write_csv(rows, tmp_path / "out.csv")
    with (tmp_path / "out.csv").open() as f:
        written = list(csv.DictReader(f))
    assert [r["run_id"] for r in written] == ["r1", "r2", ""]
    assert written[1]["problems"] == "bom: failed"
