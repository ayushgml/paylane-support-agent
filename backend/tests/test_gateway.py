from paylane.domain import FIXTURE_NOW
from paylane.store import Store
from paylane.gateway import Gateway, redact
import pytest


@pytest.fixture
def gateway(tmp_path):
    s = Store(tmp_path / "domain.db", clock=lambda: FIXTURE_NOW)
    s.seed()
    g = Gateway(s, s.create_session(), "r1")
    g.refund_requested = True
    return g


def verify(g, txn="TXN-1042"):
    g.observe_input("My email is alex@example.test and my card ends in 4242.")
    g.selection_text = txn


def test_lookup_cannot_establish_verification(gateway):
    result = gateway.dispatch("get_customer", {"email": "alex@example.test"})
    assert result == {"error": "verification_required"}
    assert not gateway.session["verified"]
    assert not any(x in str(result) for x in ["Alex", "4242", "active"])


def test_model_cannot_supply_verification_proof(gateway):
    gateway.dispatch(
        "get_customer", {"email": "alex@example.test", "card_last4": "4242"}
    )
    assert not gateway.session["verified"]


def test_split_turn_identity_and_no_model_generated_verification(gateway):
    gateway.observe_input("My email is alex@example.test")
    assert not gateway.session["verified"]
    gateway.observe_input("My card last four digits are 4242")
    assert gateway.session["verified"]


def test_ambiguous_factors_require_clarification(gateway):
    gateway.observe_input(
        "alex@example.test or sam@example.test. Card last four 4242 or 0088"
    )
    assert not gateway.session["verified"]
    assert gateway.identity_issue == "ambiguous_identity"


@pytest.mark.parametrize(
    "txn,reason",
    [
        ("TXN-OVER", "amount_limit"),
        ("TXN-30D", "age_limit"),
        ("TXN-PENDING", "not_settled"),
    ],
)
def test_no_forbidden_refund_api_invocation(gateway, txn, reason):
    verify(gateway, txn)
    gateway.dispatch("get_transaction", {"customer_id": "cus_alex", "txn_id": txn})
    out = gateway.dispatch("issue_refund", {"txn_id": txn, "amount": 100})
    assert not out.get("ok", False)
    assert not any(
        e["tool"] == "issue_refund" and e["phase"] == "executed" for e in gateway.events
    )
    assert gateway.store.count("refunds") == 0


def test_cross_customer_hidden(gateway):
    verify(gateway)
    out = gateway.dispatch(
        "get_transaction", {"customer_id": "cus_sam", "txn_id": "TXN-OTHER"}
    )
    assert out["error"] == "not_authorized"
    assert "Harbor" not in str(out)


def test_refund_requires_current_turn_read(gateway):
    verify(gateway)
    assert (
        gateway.dispatch("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5})[
            "error"
        ]
        == "transaction_read_required"
    )


def test_eligible_refund_and_duplicate_attempt(gateway):
    verify(gateway)
    gateway.dispatch(
        "get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}
    )
    assert "issue_refund" in gateway.available_tools()
    result = gateway.dispatch("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5})
    assert result["ok"]
    assert gateway.store.count("refunds") == 1
    assert "issue_refund" not in gateway.available_tools()


def test_redaction_and_anonymous_ticket(gateway):
    result = gateway.dispatch(
        "escalate_to_human",
        {
            "customer_id": "cus_sam",
            "summary": "Legal action. alex@example.test 4242 4111111111111111",
        },
    )
    assert result["ticket_id"]
    with gateway.store.connection() as db:
        r = dict(db.execute("SELECT * FROM tickets").fetchone())
    assert r["customer_id"].startswith("anonymous:")
    assert (
        "alex@" not in r["summary"]
        and "4242" not in r["summary"]
        and "411111" not in r["summary"]
    )


def test_public_events_never_echo_sensitive_args(gateway):
    gateway.dispatch("get_customer", {"email": "alex@example.test"})
    assert "alex@example.test" not in str(gateway.events)
    assert (
        redact("email a@b.test card 4111 1111 1111 1111 last four 4242")
        == "email [email redacted] card [card redacted] last four [last four redacted]"
    )


def test_status_question_cannot_authorize_money_movement(gateway):
    verify(gateway)
    gateway.dispatch(
        "get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}
    )
    gateway.refund_requested = False
    assert "issue_refund" not in gateway.available_tools()
    assert (
        gateway.dispatch("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5})[
            "error"
        ]
        == "refund_not_requested"
    )
    assert gateway.store.count("refunds") == 0


def test_current_selection_cannot_be_substituted_by_prior_reference(gateway):
    verify(gateway)
    gateway.set_selection(
        "Refund TXN-75.", [{"role": "user", "content": "Earlier payment TXN-1042"}]
    )
    assert (
        gateway.dispatch(
            "get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}
        )["error"]
        == "transaction_not_supplied"
    )


def test_multiple_targets_require_clarification_before_refund(gateway):
    verify(gateway)
    gateway.set_selection("Refund TXN-1042 or TXN-75, not sure which.")
    gateway.dispatch(
        "get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}
    )
    assert (
        gateway.dispatch("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5})[
            "error"
        ]
        == "transaction_not_supplied"
    )
    assert gateway.store.count("refunds") == 0
