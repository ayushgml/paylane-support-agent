"""Live provider contract probe; diagnostic observations, not release evidence.

Runs the real LangGraph service on A17 against five request configurations.
No real money moves; all case databases are temporary. Requires the ignored
backend/.env key. Fifteen agent runs make paid model requests.
"""

import json, tempfile, time
from pathlib import Path
import httpx
from paylane.agent import AgentService
from paylane.store import Store
from paylane.domain import FIXTURE_NOW
from paylane.provider import OpenRouter, BACKEND
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
    case = next(
        c
        for c in json.loads((BACKEND / "scenarios/adversarial.json").read_text())
        if c["id"] == "A17"
    )
    variants = [
        ("digitalocean_required_json", "DigitalOcean", False, False),
        ("digitalocean_required_noformat", "DigitalOcean", False, True),
        ("digitalocean_named_json", "DigitalOcean", True, False),
        ("digitalocean_named_noformat", "DigitalOcean", True, True),
        ("wafer_required_json", "Wafer", False, False),
    ]
    records = []

    class Recorder:
        def __init__(self, provider, named, noformat):
            self.client = httpx.Client(timeout=20)
            self.provider = provider
            self.named = named
            self.noformat = noformat
            self.requests = []

        def close(self):
            self.client.close()

        def post(self, url, **kw):
            payload = kw["json"]
            main = bool(payload.get("tools"))
            if main:
                payload["provider"]["only"] = [self.provider]
                payload["provider"]["allow_fallbacks"] = False
                if self.named:
                    payload["tool_choice"] = {
                        "type": "function",
                        "function": {"name": "get_transaction"},
                    }
                if self.noformat:
                    payload.pop("response_format", None)
            r = self.client.post(url, **kw)
            entry = {
                "phase": "main" if main else "classifier",
                "requested_tool_names": [
                    t["function"]["name"] for t in payload.get("tools", [])
                ],
                "tool_choice": payload.get("tool_choice"),
                "response_format": payload.get("response_format"),
                "routing": payload.get("provider"),
                "http_status": r.status_code,
            }
            try:
                data = r.json()
                choice = data.get("choices", [{}])[0]
                m = choice.get("message", {})
                entry.update(
                    {
                        "provider": data.get("provider"),
                        "model": data.get("model"),
                        "finish_reason": choice.get("finish_reason"),
                        "message": sanitize(m),
                        "usage": data.get("usage", {}),
                    }
                )
                if data.get("error"):
                    entry["error_code"] = data["error"].get("code")
            except (ValueError, IndexError):
                entry["body_valid_json"] = False
            self.requests.append(entry)
            return r

    for variant, endpoint, named, noformat in variants:
        for trial in range(1, 4):
            recorder = Recorder(endpoint, named, noformat)
            provider = OpenRouter(client=recorder)
            (BACKEND / ".runtime").mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="paylane-diag-", dir=str(BACKEND / ".runtime")
            ) as work:
                store = Store(Path(work) / "db.sqlite", clock=lambda: FIXTURE_NOW)
                store.seed()
                try:
                    result = AgentService(store, provider).reply(
                        store.create_session(),
                        case["messages"][0],
                        f"diagnostic-{trial}",
                    )
                    record = {
                        "variant": variant,
                        "trial": trial,
                        "requests": recorder.requests,
                        "lookup_executed": any(
                            e.get("tool") == "get_transaction"
                            and e.get("phase") == "executed"
                            for e in result.get("events", [])
                        ),
                        "outcome": result.get("outcome"),
                        "error": result.get("error"),
                        "refund_count": store.count("refunds"),
                    }
                except Exception as exc:
                    record = {
                        "variant": variant,
                        "trial": trial,
                        "requests": recorder.requests,
                        "error": type(exc).__name__,
                    }
                finally:
                    provider.close()
            records.append(record)
            (out / "lookup-contract-probe.json").write_text(
                json.dumps(
                    {
                        "purpose": "Targeted live diagnosis, not release or repeated-cohort evidence",
                        "source_commit": source_commit,
                        "repetitions_per_variant": 3,
                        "case_id": "A17",
                        "variants": records,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n"
            )
            print(
                variant,
                trial,
                "lookup",
                record.get("lookup_executed"),
                "outcome",
                record.get("outcome"),
                "error",
                record.get("error"),
                flush=True,
            )
            time.sleep(1)


if __name__ == "__main__":
    main()
