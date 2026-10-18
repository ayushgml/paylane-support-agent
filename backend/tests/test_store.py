from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from paylane.domain import FIXTURE_NOW
from paylane.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "domain.db", clock=lambda: FIXTURE_NOW)
    s.seed()
    return s


def verified(store):
    sid = store.create_session()
    assert store.verify(sid, "alex@example.test", "4242")
    return sid


def test_atomic_refund_under_concurrency(store):
    sid = verified(store)

    def refund(i):
        return store.refund(sid, "TXN-1042", 4250, f"op-{i}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(refund, range(8)))
    assert sum(r.get("ok", False) for r in results) == 1
    assert store.count("refunds") == 1
    assert store.transaction("cus_alex", "TXN-1042").status == "refunded"


def test_same_operation_replays_receipt_without_second_mutation(store):
    sid = verified(store)
    a = store.refund(sid, "TXN-1042", 4250, "stable-op")
    b = store.refund(sid, "TXN-1042", 4250, "stable-op")
    assert a["refund_id"] == b["refund_id"]
    assert b["replayed"] is True
    assert store.count("refunds") == 1


@pytest.mark.parametrize(
    "txn,cents,reason",
    [
        ("TXN-OVER", 10000, "amount_limit"),
        ("TXN-30D", 2500, "age_limit"),
        ("TXN-PENDING", 2000, "not_settled"),
        ("TXN-OTHER", 2500, "not_authorized"),
        ("TXN-1042", 100, "amount_mismatch"),
        ("TXN-REFUNDED", 2000, "already_refunded"),
    ],
)
def test_domain_rechecks_eligibility(store, txn, cents, reason):
    assert store.refund(verified(store), txn, cents, "op")["reason"] == reason
    assert store.count("refunds") == 0


def test_handoff_latch_blocks_refund_even_if_ticket_fails(store):
    sid = verified(store)
    store.latch_handoff(sid, "legal")
    assert store.refund(sid, "TXN-1042", 4250, "op")["reason"] == "mandatory_handoff"


def test_session_does_not_verify_on_lookup(store):
    sid = store.create_session()
    assert store.customer("alex@example.test")["verified"] is False
    assert not store.session(sid)["verified"]


def test_wrong_details_and_identity_switch_revoke_authority(store):
    sid = verified(store)
    assert not store.verify(sid, "sam@example.test", "9999")
    assert not store.session(sid)["verified"]


def test_verification_expiry_checked_at_refund(store):
    sid = verified(store)
    store.clock = lambda: FIXTURE_NOW + timedelta(minutes=16)
    assert store.refund(sid, "TXN-1042", 4250, "op")["reason"] == "not_verified"


def test_ticket_retry_is_idempotent(store):
    sid = store.create_session()
    a = store.escalate(sid, "legal", "Customer reports legal action")
    b = store.escalate(sid, "legal", "Customer repeats legal action")
    assert a["ticket_id"] == b["ticket_id"]
    assert store.count("tickets") == 1


def test_restart_preserves_refund(store):
    sid = verified(store)
    store.refund(sid, "TXN-1042", 4250, "op")
    restarted = Store(store.path, clock=lambda: FIXTURE_NOW)
    assert (
        restarted.refund(sid, "TXN-1042", 4250, "different")["reason"]
        == "already_refunded"
    )


def test_mismatch_locks_after_three_attempts(store):
    sid = store.create_session()
    for _ in range(3):
        assert not store.verify(sid, "alex@example.test", "0000")
    assert not store.verify(sid, "alex@example.test", "4242")


def test_request_recovery_uses_exact_namespace_not_sql_wildcards(store):
    sid = verified(store)
    store.claim_request(sid, "req_a", "A")
    store.claim_request(sid, "reqXa", "B")
    store.refund(sid, "TXN-1042", 4250, sid + ":reqXa:issue_refund:1")
    with pytest.raises(ValueError, match="request_in_progress"):
        store.claim_request(sid, "req_a", "A")
    assert store.claim_request(sid, "reqXa", "B") == {"recover": True}
    assert store.receipt(sid, request_id="req_a") is None
    assert store.receipt(sid, request_id="reqXa")["txn_id"] == "TXN-1042"


def test_expired_session_erases_pending_proof(store):
    sid = store.create_session()
    store.pending(sid, "alex@example.test", "4242")
    store.clock = lambda: FIXTURE_NOW + timedelta(minutes=31)
    with pytest.raises(ValueError, match="session_expired"):
        store.session(sid)
    with store.connection() as db:
        r = db.execute(
            "SELECT pending_email,pending_last4 FROM sessions WHERE id=?", (sid,)
        ).fetchone()
    assert tuple(r) == (None, None)
