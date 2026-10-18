"""Backend-first entry point. No Node/frontend installation is required."""

import json
from pathlib import Path
import os
import uuid
import typer
from .provider import BACKEND, OpenRouter, ProviderError
from .store import Store
from .agent import AgentService

app = typer.Typer(
    help="Paylane support agent: chat, evaluate, and serve synthetic mock support.",
    no_args_is_help=True,
)


@app.command()
def chat():
    """Chat with the real OpenRouter-backed LangGraph agent."""
    try:
        provider = OpenRouter()
    except ProviderError as e:
        typer.echo(str(e))
        raise typer.Exit(1)
    store = Store(BACKEND / os.getenv("PAYLANE_DATA_DIR", ".runtime") / "domain.db")
    store.seed()
    service = AgentService(store, provider)
    sid = store.create_session()
    typer.echo(
        "Paylane · synthetic mock environment. Type /quit to exit. /new starts a new conversation; refund history is retained."
    )
    typer.echo(
        "Demo: alex@example.test, card last four 4242, payment TXN-1042. Only use these synthetic details."
    )
    while True:
        try:
            message = typer.prompt("You")
        except (EOFError, KeyboardInterrupt):
            break
        if message.strip() == "/quit":
            break
        if message.strip() == "/new":
            sid = store.create_session()
            typer.echo("New conversation.")
            continue
        try:
            typer.echo(
                "Paylane: " + service.reply(sid, message, uuid.uuid4().hex)["text"]
            )
        except ValueError as e:
            typer.echo("Request could not be processed: " + str(e))


@app.command("eval")
def evaluate(
    output: Path = typer.Option(
        None, help="Report directory; defaults to backend/reports."
    ),
    case: list[str] = typer.Option(
        None, "--case", "-c", help="Run selected case IDs; repeat option."
    ),
    deterministic_only: bool = typer.Option(
        False, help="Skip the conversation judge. Still runs the actual agent."
    ),
):
    """Run authored conversations with actual model calls and DeepEval checks."""
    try:
        OpenRouter()
        from .evals import run_suite

        report = run_suite(output, with_judge=not deterministic_only, only=case)
    except (ProviderError, ImportError) as e:
        typer.echo("Evaluation setup error: " + str(e))
        raise typer.Exit(1)
    typer.echo(json.dumps(report["score"], indent=2))
    if deterministic_only:
        typer.echo(
            "Conversation quality was not evaluated; this is a partial evaluation."
        )
    if report["score"]["passed"] != report["score"]["total"]:
        raise typer.Exit(1)


@app.command("reliability")
def reliability(
    output: Path = typer.Option(
        ...,
        help="New cohort directory; resumes only with identical frozen configuration.",
    ),
    runs: int = typer.Option(
        7, min=7, help="Repetitions per required, adversarial and control case."
    ),
    workers: int = typer.Option(3, min=1, max=6),
):
    """Run an immutable repeated reliability and adversarial cohort with DeepEval."""
    from .reliability import run_cohort

    try:
        report = run_cohort(output, repetitions=runs, workers=workers)
    except (ValueError, ProviderError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)
    summary = report["summary"]
    typer.echo(
        json.dumps(
            {
                k: summary[k]
                for k in [
                    "expected",
                    "completed",
                    "passed",
                    "release_gate_passed",
                    "macro",
                    "security",
                ]
            },
            indent=2,
        )
    )
    if not summary["release_gate_passed"]:
        raise typer.Exit(1)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, read_only: bool = False):
    """Serve the API and, if built separately, frontend/dist."""
    import uvicorn
    from .server import create_app

    exposed = host not in {"127.0.0.1", "localhost", "::1"}
    if exposed and not read_only and not os.getenv("PAYLANE_DEMO_INVITE"):
        typer.echo(
            "Set PAYLANE_DEMO_INVITE before exposing live inference, or use --read-only. Use HTTPS behind a reverse proxy."
        )
        raise typer.Exit(1)
    uvicorn.run(
        create_app(hosted=exposed, live_enabled=not read_only), host=host, port=port
    )
