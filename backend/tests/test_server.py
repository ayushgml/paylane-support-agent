import json
from fastapi.testclient import TestClient
from paylane.server import create_app
from paylane.store import Store
from paylane.domain import FIXTURE_NOW


class Provider:
    model = "test-only"

    def classify(self, *a, **kw):
        return {"route": "normal", "reason": "none"}

    def complete(self, *a, **kw):
        return {"content": json.dumps({"kind": "verify"}), "tool_calls": []}


def app(tmp_path, hosted=False):
    s = Store(tmp_path / "domain.db", clock=lambda: FIXTURE_NOW)
    s.seed()
    application = create_app(s, Provider(), hosted=hosted, invite="test-invite")
    application.state.store = s
    return application


def session(c):
    response = c.post(
        "/api/sessions", headers={"X-CSRF-Token": c.cookies.get("paylane_csrf", "")}
    )
    assert response.status_code == 200
    return response.json()["session_id"], {
        "X-CSRF-Token": c.cookies.get("paylane_csrf")
    }


def test_session_ownership_and_csrf(tmp_path):
    application = app(tmp_path)
    with TestClient(application) as a, TestClient(application) as b:
        sid, headers = session(a)
        assert (
            a.post(
                f"/api/sessions/{sid}/messages",
                json={"message": "Hi", "request_id": "r"},
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            a.post(
                f"/api/sessions/{sid}/messages",
                json={"message": "Hi", "request_id": "r2"},
            ).status_code
            == 403
        )
        session(b)
        assert b.get(f"/api/sessions/{sid}/requests/r").status_code == 404


def test_schema_and_explicit_verification(tmp_path):
    with TestClient(app(tmp_path)) as c:
        sid, h = session(c)
        assert (
            c.post(
                f"/api/sessions/{sid}/messages",
                headers=h,
                json={"message": "", "request_id": "r"},
            ).status_code
            == 422
        )
        assert c.post(
            f"/api/sessions/{sid}/verify",
            headers=h,
            json={"email": "alex@example.test", "card_last4": "4242"},
        ).json()["verified"]


def test_hosted_live_mode_requires_admission(tmp_path):
    with TestClient(app(tmp_path, hosted=True), base_url="https://testserver") as c:
        assert c.post("/api/sessions").status_code == 401
        assert c.post("/api/login", json={"invite": "wrong"}).status_code == 401
        assert c.post("/api/login", json={"invite": "test-invite"}).status_code == 200
        sid, h = session(c)
        assert (
            c.post(
                f"/api/sessions/{sid}/messages",
                headers=h,
                json={"message": "Hi", "request_id": "r"},
            ).status_code
            == 200
        )


def test_public_configuration_contains_no_key_or_account(tmp_path):
    with TestClient(app(tmp_path)) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert not any(x in r.text for x in ["sk-or-", "alex@", "card_last4"])
        assert len(c.get("/api/scenarios").json()["cases"]) == 12


def test_wrong_origin_is_rejected(tmp_path):
    with TestClient(app(tmp_path)) as c:
        sid, h = session(c)
        h["Origin"] = "https://evil.example"
        assert (
            c.post(
                f"/api/sessions/{sid}/messages",
                headers=h,
                json={"message": "Hi", "request_id": "r"},
            ).status_code
            == 403
        )


def test_relogin_cannot_reset_invite_request_budget(tmp_path):
    with TestClient(app(tmp_path, hosted=True), base_url="https://testserver") as c:
        assert c.post("/api/login", json={"invite": "test-invite"}).status_code == 200
        sid, h = session(c)
        store = c.app.state.store
        # Establish an exhausted budget even before any messages were submitted.
        with store.write() as db:
            owner = db.execute(
                "SELECT owner FROM session_owners WHERE session_id=?", (sid,)
            ).fetchone()[0]
            db.execute(
                "INSERT OR REPLACE INTO admissions VALUES(?,?,50)",
                (owner, FIXTURE_NOW.date().isoformat()),
            )
        assert c.post("/api/login", json={"invite": "test-invite"}).status_code == 200
        new_sid, h = session(c)
        assert (
            c.post(
                f"/api/sessions/{new_sid}/messages",
                headers=h,
                json={"message": "Hi", "request_id": "another"},
            ).status_code
            == 429
        )


def test_global_budget_survives_cookie_reset(tmp_path):
    application = app(tmp_path, hosted=True)
    with TestClient(application, base_url="https://testserver") as c:
        c.post("/api/login", json={"invite": "test-invite"})
        sid, h = session(c)
        with application.state.store.write() as db:
            db.execute(
                "INSERT OR REPLACE INTO admissions VALUES(?,?,200)",
                ("deployment", FIXTURE_NOW.date().isoformat()),
            )
        c.cookies.clear()
        c.post("/api/login", json={"invite": "test-invite"})
        sid, h = session(c)
        assert (
            c.post(
                f"/api/sessions/{sid}/messages",
                headers=h,
                json={"message": "Hi", "request_id": "new"},
            ).status_code
            == 429
        )


def test_session_creation_rejects_cross_origin_and_missing_csrf(tmp_path):
    with TestClient(app(tmp_path)) as c:
        assert (
            c.post(
                "/api/sessions", headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        session(c)
        assert c.post("/api/sessions").status_code == 403
