"""Thin same-origin demo transport. No model key or unchecked tools are exposed."""

import hashlib
import hmac
import json
import os
import secrets
import threading
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, StrictStr
from .agent import AgentService
from .domain import StrictModel
from .provider import BACKEND, OpenRouter, ProviderError
from .store import Store, uid


class Message(StrictModel):
    request_id: StrictStr = Field(
        min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"
    )
    message: StrictStr = Field(min_length=1, max_length=4000)


class Proof(StrictModel):
    email: StrictStr = Field(min_length=3, max_length=254)
    card_last4: StrictStr = Field(pattern=r"^[0-9]{4}$")


class Login(StrictModel):
    invite: StrictStr = Field(min_length=1, max_length=256)


def create_app(
    store=None, provider=None, *, hosted=False, invite=None, live_enabled=True
):
    store = store or Store(
        BACKEND / os.getenv("PAYLANE_DATA_DIR", ".runtime") / "domain.db"
    )
    store.seed()
    if provider is None and live_enabled:
        try:
            provider = OpenRouter()
        except ProviderError:
            provider = None
    service = AgentService(store, provider) if provider and live_enabled else None
    app = FastAPI(title="Paylane support agent", docs_url=None if hosted else "/docs")
    invite = invite if invite is not None else os.getenv("PAYLANE_DEMO_INVITE", "")
    concurrency = threading.BoundedSemaphore(3)
    with store.connection() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS session_owners(session_id TEXT PRIMARY KEY,owner TEXT NOT NULL)"
        )

    def signed(owner):
        return (
            owner
            + "."
            + hmac.new(store.signing_key, owner.encode(), hashlib.sha256).hexdigest()
        )

    def principal(request, required=True):
        cookie = request.cookies.get("paylane_browser", "")
        if "." in cookie:
            owner, signature = cookie.rsplit(".", 1)
            if hmac.compare_digest(signed(owner), cookie):
                return owner
        if required:
            raise HTTPException(
                401, "demo_login_required" if hosted else "create_session_first"
            )
        return None

    def set_cookies(response, owner):
        response.set_cookie(
            "paylane_browser",
            signed(owner),
            httponly=True,
            secure=hosted,
            samesite="lax",
            max_age=3600,
        )
        response.set_cookie(
            "paylane_csrf",
            secrets.token_urlsafe(24),
            secure=hosted,
            samesite="lax",
            max_age=3600,
        )

    def mutation(request):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "origin_not_allowed")
        token = request.cookies.get("paylane_csrf", "")
        if not token or not hmac.compare_digest(
            token, request.headers.get("x-csrf-token", "")
        ):
            raise HTTPException(403, "csrf_required")

    def own(sid, request):
        owner = principal(request)
        with store.connection() as db:
            r = db.execute(
                "SELECT owner FROM session_owners WHERE session_id=?", (sid,)
            ).fetchone()
        if not r or r["owner"] != owner:
            raise HTTPException(404, "session_not_found")
        try:
            store.session(sid)
        except ValueError as e:
            raise HTTPException(410, str(e)) from None
        return owner

    @app.get("/api/health")
    def health(request: Request):
        return {
            "status": "ready",
            "live_available": service is not None,
            "admitted": not hosted or principal(request, False) is not None,
            "hosted": hosted,
            "model": getattr(provider, "model", None),
            "environment": "synthetic mock",
        }

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "origin_not_allowed")
        if not invite or not hmac.compare_digest(invite, body.invite):
            raise HTTPException(401, "invalid_invite")
        set_cookies(response, principal(request, False) or uid("demo"))
        return {"ok": True}

    @app.post("/api/sessions")
    def new_session(request: Request, response: Response):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "origin_not_allowed")
        owner = principal(request, False)
        if owner:
            mutation(request)
        if not owner:
            if hosted:
                raise HTTPException(401, "demo_login_required")
            owner = uid("local")
            set_cookies(response, owner)
        day = store.now().date().isoformat()
        with store.write() as db:
            for key, limit in [("sessions:" + owner, 20), ("sessions:deployment", 200)]:
                db.execute("INSERT OR IGNORE INTO admissions VALUES(?,?,0)", (key, day))
                if (
                    db.execute(
                        "SELECT count FROM admissions WHERE principal=? AND day=?",
                        (key, day),
                    ).fetchone()[0]
                    >= limit
                ):
                    raise HTTPException(429, "session_limit")
                db.execute(
                    "UPDATE admissions SET count=count+1 WHERE principal=? AND day=?",
                    (key, day),
                )
        sid = store.create_session()
        with store.write() as db:
            db.execute("INSERT INTO session_owners VALUES(?,?)", (sid, owner))
        return {"session_id": sid, "verified": False}

    @app.post("/api/sessions/{sid}/verify")
    def verify(sid: str, body: Proof, request: Request):
        own(sid, request)
        mutation(request)
        return {"verified": store.verify(sid, body.email, body.card_last4)}

    @app.post("/api/sessions/{sid}/messages")
    def message(sid: str, body: Message, request: Request):
        owner = own(sid, request)
        mutation(request)
        if service is None:
            raise HTTPException(503, "configure_backend_openrouter_key")
        now = store.now()
        day = now.date().isoformat()
        with store.connection() as db:
            existing = db.execute(
                "SELECT 1 FROM requests WHERE session_id=? AND request_id=?",
                (sid, body.request_id),
            ).fetchone()
        if existing:
            try:
                return service.reply(sid, body.message, body.request_id)
            except ValueError as e:
                raise HTTPException(409, str(e)) from None
        with store.write() as db:
            from datetime import timedelta

            recent = db.execute(
                "SELECT COUNT(*) FROM requests r JOIN session_owners o ON r.session_id=o.session_id WHERE o.owner=? AND r.created>?",
                (owner, (now - timedelta(minutes=1)).isoformat()),
            ).fetchone()[0]
            if recent >= 5:
                raise HTTPException(429, "minute_limit")
            for key, limit in [(owner, 50), ("deployment", 200)]:
                db.execute("INSERT OR IGNORE INTO admissions VALUES(?,?,0)", (key, day))
                if (
                    db.execute(
                        "SELECT count FROM admissions WHERE principal=? AND day=?",
                        (key, day),
                    ).fetchone()[0]
                    >= limit
                ):
                    raise HTTPException(429, "daily_limit")
                db.execute(
                    "UPDATE admissions SET count=count+1 WHERE principal=? AND day=?",
                    (key, day),
                )
        if not concurrency.acquire(blocking=False):
            raise HTTPException(429, "demo_busy")
        try:
            return service.reply(sid, body.message, body.request_id)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        finally:
            concurrency.release()

    @app.get("/api/sessions/{sid}/requests/{rid}")
    def request_result(sid: str, rid: str, request: Request):
        own(sid, request)
        with store.connection() as db:
            r = db.execute(
                "SELECT status,response FROM requests WHERE session_id=? AND request_id=?",
                (sid, rid),
            ).fetchone()
        if not r:
            raise HTTPException(404, "request_not_found")
        return {
            "status": r["status"],
            "result": json.loads(r["response"]) if r["response"] else None,
        }

    @app.get("/api/scenarios")
    def scenarios():
        data = json.loads((BACKEND / "scenarios/cases.json").read_text())
        return {
            "cases": data,
            "data_notice": "Authored synthetic fixtures, not account lookup results.",
        }

    @app.get("/api/policy")
    def policy():
        return {"text": (BACKEND / "prompts/rulebook.md").read_text()}

    @app.get("/api/reports/latest")
    def report():
        path = BACKEND / "reports/latest.json"
        return (
            json.loads(path.read_text())
            if path.exists()
            else {"status": "not_run", "cases": []}
        )

    @app.get("/api/reports/download/{kind}")
    def download(kind: str):
        names = {
            "transcripts": "transcripts.md",
            "evaluation": "evaluation.md",
            "json": "latest.json",
            "reliability": "reliability.md",
        }
        if kind not in names:
            raise HTTPException(404)
        path = BACKEND / "reports" / names[kind]
        if not path.exists():
            raise HTTPException(404, "report_not_run")
        return FileResponse(path, filename=path.name)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = (
            "no-store" if request.url.path.startswith("/api/") else "no-cache"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    frontend = BACKEND.parent / "frontend/dist"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="demo")
    return app
