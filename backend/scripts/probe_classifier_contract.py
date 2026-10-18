"""Live risk-schema probe, separate from release evidence.

Makes 12 paid classifier requests using synthetic fixtures and the ignored
backend/.env key. C01 user-only controls are not a replay of assistant history.
"""

import json, time
from pathlib import Path
import httpx
from paylane.provider import OpenRouter, RiskAssessment, BACKEND, ProviderError
from paylane.guardrails import inspect_input
from paylane.privacy import sanitize
import argparse
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output
    if out.exists():
        raise SystemExit(
            "Use a new output directory; existing evidence is never overwritten."
        )
    out.mkdir(parents=True)
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=BACKEND.parent, text=True
    ).strip()
    records = []

    class Recorder:
        def __init__(self, schema):
            self.client = httpx.Client(timeout=20)
            self.schema = schema
            self.requests = []

        def close(self):
            self.client.close()

        def post(self, url, **kw):
            if self.schema:
                kw["json"]["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "risk_assessment",
                        "strict": True,
                        "schema": RiskAssessment.model_json_schema(),
                    },
                }
            r = self.client.post(url, **kw)
            e = {
                "response_format": kw["json"]["response_format"],
                "http_status": r.status_code,
            }
            try:
                d = r.json()
                choice = d.get("choices", [{}])[0]
                e.update(
                    provider=d.get("provider"),
                    finish_reason=choice.get("finish_reason"),
                    message=sanitize(choice.get("message", {})),
                )
            except (ValueError, IndexError):
                e["invalid_response_body"] = True
            self.requests.append(e)
            return r

    cases = json.loads((BACKEND / "scenarios/cases.json").read_text())
    for case_id in ["C03", "C01"]:
        case = next(c for c in cases if c["id"] == case_id)
        # User-only schema controls, not a replay of the original assistant history.
        messages = [
            {"role": "user", "content": inspect_input(m)[0]}
            for m in case["messages"][: 1 if case_id == "C03" else 3]
        ]
        for schema in [False, True]:
            for trial in range(1, 4):
                recorder = Recorder(schema)
                p = OpenRouter(client=recorder)
                try:
                    result = p.classify(messages)
                    valid = True
                    error = None
                except ProviderError as exc:
                    result = None
                    valid = False
                    error = str(exc)
                finally:
                    p.close()
                records.append(
                    {
                        "case_id": case_id,
                        "variant": "strict_schema" if schema else "json_object",
                        "trial": trial,
                        "input_note": "Original first customer turn"
                        if case_id == "C03"
                        else "Three original customer turns, user messages only; not an exact replay of original assistant history",
                        "valid": valid,
                        "error": error,
                        "risk": {
                            k: v
                            for k, v in (result or {}).items()
                            if not k.startswith("_")
                        },
                        "requests": recorder.requests,
                    }
                )
                (out / "classifier-contract-probe.json").write_text(
                    json.dumps(
                        {
                            "purpose": "Targeted diagnostic, not release evidence; 3 observations per setting, no reliability claim",
                            "source_commit": source_commit,
                            "observations": records,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                print(
                    case_id,
                    "schema" if schema else "json",
                    trial,
                    "valid",
                    valid,
                    "risk",
                    records[-1]["risk"],
                    "error",
                    error,
                    flush=True,
                )
                time.sleep(1)


if __name__ == "__main__":
    main()
