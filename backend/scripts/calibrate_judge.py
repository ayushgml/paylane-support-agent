"""Authored reference-fixture calibration; outputs are NOT agent execution evidence."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import random
from pathlib import Path
from paylane.evals import deepeval_checks, provenance
from paylane.provider import BACKEND

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
fixtures = json.loads((BACKEND / "scenarios/judge-calibration.json").read_text())
random.Random(20261018).shuffle(fixtures)
report = {
    "purpose": "Judge calibration on authored contrastive reference outputs with shared policy/evidence. Labels, IDs and variant names are excluded from rendered judge prompts. Not actual agent trials; excluded from pass@k/pass^k. Labels are engineering expectations, not independent human validation.",
    "provenance": provenance(),
    "schedule": [f["id"] for f in fixtures],
    "fixtures": [],
}


def run(f):
    metrics = deepeval_checks(f, f["transcript"], [], True)
    panel = next(m for m in metrics if m["name"].startswith("Conversation quality"))
    return f | {
        "judge": panel,
        "correct": panel.get("passed") == f["expected_quality_pass"]
        and panel.get("kind") != "evaluation_error",
    }


with ThreadPoolExecutor(max_workers=3) as pool:
    for future in as_completed([pool.submit(run, f) for f in fixtures]):
        f = future.result()
        report["fixtures"].append(f)
        report["fixtures"].sort(key=lambda x: x["id"])
        report["correct"] = sum(x["correct"] for x in report["fixtures"])
        report["total"] = len(report["fixtures"])
        report["accuracy"] = report["correct"] / report["total"]
        (args.output / "calibration.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(
            f["id"],
            "CORRECT" if f["correct"] else "WRONG",
            f["judge"].get("score"),
            flush=True,
        )
lines = [
    "# Judge calibration",
    "",
    report["purpose"],
    "",
    f"Label agreement: {report['correct']}/{report['total']} ({report['accuracy']:.1%}).",
    "",
    "| Fixture | Authored reference label | Judge median | Agreement |",
    "|---|---|---|---|",
]
for f in report["fixtures"]:
    lines.append(
        f"| {f['id']} {f['title']} | {f['expected_quality_pass']} | {f['judge'].get('score', 'error')} | {f['correct']} |"
    )
(args.output / "calibration.md").write_text("\n".join(lines) + "\n")
raise SystemExit(0 if report["correct"] == report["total"] else 1)
