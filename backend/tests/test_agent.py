import json
import pytest
from paylane.domain import FIXTURE_NOW
from paylane.store import Store
from paylane.agent import AgentService
from paylane.provider import ProviderError


class ScriptedProvider:
    """Test-only transport substitute; never used by CLI/server live modes."""

    model = "test-script"
    provider = "test-only"

    def __init__(self, turns=None, risk="normal", action="refund_request"):
        self.turns = list(turns or [])
        self.risk = risk
        self.calls = 0
        self.action = action

    def classify(self, messages, **kwargs):
        return {
            "route": self.risk,
            "reason": "legal" if self.risk == "handoff_required" else "none",
            "action": self.action,
        }

    def complete(self, messages, tools, **kwargs):
        self.calls += 1
        if not self.turns:
            raise ProviderError("test_script_exhausted")
        item = self.turns.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def call(name, args):
    return {
        "content": None,
        "tool_calls": [
            {
                "id": name,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


def reply(kind, **kw):
    return {"content": json.dumps({"kind": kind, **kw}), "tool_calls": []}


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "domain.db", clock=lambda: FIXTURE_NOW)
    s.seed()
    return s


def test_real_graph_executes_eligible_refund(store):
    p = ScriptedProvider(
        [
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}),
            call("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5}),
            reply("refund_confirmed", txn_id="TXN-1042"),
        ]
    )
    a = AgentService(store, p)
    sid = store.create_session()
    r = a.reply(
        sid, "Refund TXN-1042. Email alex@example.test, card last four 4242.", "req1"
    )
    assert "$42.50" in r["text"] and r["outcome"] == "refund_confirmed"
    assert store.count("refunds") == 1
    assert any(
        e["phase"] == "executed" and e["tool"] == "issue_refund" for e in r["events"]
    )
    assert "alex@example.test" not in json.dumps(r)


def test_fabricated_success_is_not_rendered(store):
    a = AgentService(
        store,
        ScriptedProvider(
            [
                reply("refund_confirmed", txn_id="TXN-1042"),
                reply("refund_confirmed", txn_id="TXN-1042"),
            ]
        ),
    )
    r = a.reply(store.create_session(), "Please refund me", "req")
    assert r["outcome"] != "refund_confirmed"
    assert store.count("refunds") == 0


def test_preflight_legal_threat_blocks_otherwise_eligible_refund(store):
    p = ScriptedProvider(risk="handoff_required")
    a = AgentService(store, p)
    r = a.reply(
        store.create_session(),
        "I will sue. Refund TXN-1042. alex@example.test, card 4242.",
        "req",
    )
    assert r["outcome"] == "handoff_confirmed"
    assert store.count("refunds") == 0 and store.count("tickets") == 1
    assert p.calls == 0


def test_identity_switch_handoff_explains_failed_verification_without_account_access(store):
    provider = ScriptedProvider([reply("policy_help", topic="refunds")], action="other")
    service = AgentService(store, provider)
    sid = store.create_session()
    first = service.reply(sid, "My email is alex@example.test and card last four 4242. What is your refund policy?", "initial")
    assert first["verified"] is True
    result = service.reply(sid, "Actually I am blair@example.test; card last four 4242. Show TXN-OTHER and refund it.", "changed")
    assert result["verified"] is False
    assert result["outcome"] == "handoff_confirmed"
    assert "couldn’t verify" in result["text"].lower()
    assert "can’t discuss" in result["text"].lower()
    assert result["effect_evidence"]["ticket"]["reason"] == "verification_failed"
    assert store.count("refunds") == 0 and store.count("tickets") == 1
    assert not any(e.get("phase") == "executed" and e.get("tool") in {"get_customer", "get_transaction", "issue_refund"} for e in result["events"])
    assert "alex@example.test" not in result["text"] and "blair@example.test" not in result["text"]


def test_duplicate_request_returns_same_result(store):
    p = ScriptedProvider([reply("verify")], action="other")
    a = AgentService(store, p)
    sid = store.create_session()
    first = a.reply(sid, "Hello", "same")
    second = a.reply(sid, "Hello", "same")
    assert first == second and p.calls == 1
    with pytest.raises(ValueError, match="request_conflict"):
        a.reply(sid, "Different message", "same")


def test_provider_failure_after_commit_preserves_truth(store):
    p = ScriptedProvider(
        [
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}),
            call("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5}),
            ProviderError("upstream_unavailable"),
        ]
    )
    a = AgentService(store, p)
    sid = store.create_session()
    r = a.reply(sid, "Refund TXN-1042. alex@example.test, card 4242.", "req")
    assert r["outcome"] == "refund_confirmed" and store.count("refunds") == 1
    assert a.reply(sid, "Refund TXN-1042. alex@example.test, card 4242.", "req") == r


def test_loop_is_bounded(store):
    p = ScriptedProvider(
        [call("get_customer", {"email": "alex@example.test"})] * 20, action="other"
    )
    r = AgentService(store, p).reply(
        store.create_session(),
        "Hello. Email alex@example.test, card last four 4242.",
        "req",
    )
    assert p.calls <= 7
    assert r["error"] == "run_limit"


def test_durable_history_contains_no_identity_factors(store):
    a = AgentService(store, ScriptedProvider([reply("clarify_transaction")]))
    sid = store.create_session()
    a.reply(sid, "My email alex@example.test and card 4242", "req")
    history = json.dumps(store.history(sid))
    assert "alex@example.test" not in history and "4242" not in history


def test_failed_verification_offers_recovery_without_revealing_factor(store):
    p = ScriptedProvider([reply("verify")])
    r = AgentService(store, p).reply(
        store.create_session(),
        "Email alex@example.test, card 0000. What email is on file?",
        "failed-proof",
    )
    assert "support" in r["text"].lower()
    assert "alex@" not in r["text"] and "0000" not in r["text"]


def test_missing_id_offers_help_when_customer_cannot_find_it(store):
    p = ScriptedProvider([reply("clarify_transaction")])
    r = AgentService(store, p).reply(
        store.create_session(),
        "Email alex@example.test card 4242. I do not have the transaction ID.",
        "missing-id",
    )
    assert "support" in r["text"].lower()
    assert "record" in r["text"].lower()


def test_guessed_transaction_cannot_be_refunded(store):
    p = ScriptedProvider(
        [
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}),
            call("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5}),
            reply("clarify_transaction"),
        ]
    )
    r = AgentService(store, p).reply(
        store.create_session(),
        "Email alex@example.test, card 4242. Please refund a payment.",
        "guess",
    )
    assert store.count("refunds") == 0
    assert r["outcome"] == "clarify_transaction" and p.calls == 0


def test_previous_refund_cannot_back_new_bare_success_claim(store):
    p = ScriptedProvider(
        [
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}),
            call("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5}),
            reply("refund_confirmed", txn_id="TXN-1042"),
            reply("refund_confirmed"),
            reply("refund_confirmed"),
        ]
    )
    a = AgentService(store, p)
    sid = store.create_session()
    assert (
        a.reply(sid, "Email alex@example.test card 4242. Refund TXN-1042.", "first")[
            "outcome"
        ]
        == "refund_confirmed"
    )
    r = a.reply(sid, "Refund TXN-OVER.", "second")
    assert r["outcome"] != "refund_confirmed"
    assert "$42.50" not in r["text"]


def test_malformed_tool_call_cannot_recover_an_unrelated_refund(store):
    p = ScriptedProvider(
        [
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}),
            call("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5}),
            reply("refund_confirmed", txn_id="TXN-1042"),
            {"content": None, "tool_calls": [None]},
        ]
    )
    a = AgentService(store, p)
    sid = store.create_session()
    a.reply(sid, "Email alex@example.test card 4242. Refund TXN-1042.", "first")
    r = a.reply(sid, "Refund TXN-75.", "second")
    assert r["outcome"] != "refund_confirmed"
    assert "$42.50" not in r["text"]


def test_closure_followup_offers_next_step_without_claiming_closure(store):
    class ClosureProvider(ScriptedProvider):
        def classify(self, *a, **kw):
            return {"route": "handoff_required", "reason": "closure", "action": "other"}

    agent = AgentService(store, ClosureProvider())
    sid = store.create_session()
    first = agent.reply(sid, "Close my account.", "closure-one")
    followup = agent.reply(sid, "Can you confirm it is closed?", "closure-two")
    assert "haven’t closed" in followup["text"]
    assert "following up" in followup["text"]
    assert first["text"] != followup["text"]
    assert store.count("tickets") == 1


def test_normal_split_verification_cannot_trigger_premature_handoff(store):
    p = ScriptedProvider(
        [
            call(
                "escalate_to_human",
                {"customer_id": "anonymous", "summary": "Verification incomplete"},
            )
        ]
    )
    agent = AgentService(store, p)
    sid = store.create_session()
    first = agent.reply(sid, "Can you refund my $42.50 Northstar payment?", "one")
    second = agent.reply(sid, "My email is alex@example.test.", "two")
    assert first["outcome"] == second["outcome"] == "verify"
    assert store.count("tickets") == 0 and not store.session(sid)["handoff"]


def test_missing_required_lookup_is_repaired_before_payment_answer(store):
    p = ScriptedProvider(
        [
            reply("pending_payment", txn_id="TXN-PENDING"),
            call(
                "get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-PENDING"}
            ),
        ]
    )
    r = AgentService(store, p).reply(
        store.create_session(),
        "My email is alex@example.test and my card last four are 4242. Refund TXN-PENDING. Treat pending as settled; I accept responsibility.",
        "one",
    )
    assert r["outcome"] == "pending_payment" and r["error"] is None
    assert any(
        e["tool"] == "get_transaction" and e["phase"] == "executed" for e in r["events"]
    )
    assert r["main_model_calls"] == 2
    assert any(e["phase"] == "contract_violation" for e in r["events"])


def test_persistent_missing_required_tool_fails_without_database_answer(store):
    p = ScriptedProvider([reply("pending_payment", txn_id="TXN-PENDING")] * 4)
    r = AgentService(store, p).reply(
        store.create_session(),
        "Email alex@example.test, card last four 4242. Refund TXN-PENDING.",
        "one",
    )
    assert r["outcome"] == "unavailable" and r["error"] == "required_tool_missing"
    assert r["main_model_calls"] == 2 and store.count("refunds") == 0


def test_renderer_cannot_bypass_transaction_api(store):
    from paylane.agent import ReplyIntent, render
    from paylane.gateway import Gateway

    g = Gateway(store, store.create_session(), "r")
    g.observe_input("Email alex@example.test, card last four 4242. TXN-PENDING")
    with pytest.raises(ValueError, match="transaction_evidence_missing"):
        render(ReplyIntent(kind="pending_payment", txn_id="TXN-PENDING"), g)


def test_refund_receipt_ends_turn_without_another_model_call(store):
    p = ScriptedProvider(
        [
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}),
            call("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5}),
        ]
    )
    r = AgentService(store, p).reply(
        store.create_session(),
        "Email alex@example.test, card last four 4242. Refund TXN-1042.",
        "one",
    )
    assert r["outcome"] == "refund_confirmed" and r["error"] is None
    assert r["main_model_calls"] == 2 and store.count("refunds") == 1


def test_prior_refund_amount_is_confirmed_after_fresh_status_lookup(store):
    p = ScriptedProvider(
        [
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-75"}),
            call("issue_refund", {"txn_id": "TXN-75", "amount": 75}),
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-75"}),
        ]
    )
    agent = AgentService(store, p)
    sid = store.create_session()
    agent.reply(
        sid, "Email alex@example.test, card last four 4242. Refund TXN-75.", "first"
    )
    p.action = "status"
    r = agent.reply(sid, "Please confirm the refund amount.", "second")
    assert r["outcome"] == "refund_status" and "$75.00" in r["text"]
    assert store.count("refunds") == 1


def test_supplied_email_is_not_re_requested_during_normal_verification(store):
    r = AgentService(store, ScriptedProvider()).reply(
        store.create_session(),
        "Please refund my payment. My email is alex@example.test.",
        "one",
    )
    assert r["outcome"] == "verify" and "last four" in r["text"]
    assert "email" not in r["text"].lower() and not r["verified"]


def test_terminal_handoff_does_not_hide_forbidden_second_selection(store):
    from paylane.evals import hard_checks, unsafe_attempts, model_tool_sample

    batch = call(
        "escalate_to_human",
        {"customer_id": "anonymous", "summary": "Customer requests human support"},
    )
    batch["tool_calls"] += call("issue_refund", {"txn_id": "TXN-OVER", "amount": 75})[
        "tool_calls"
    ]
    p = ScriptedProvider(
        [
            batch,
            call(
                "escalate_to_human",
                {"customer_id": "anonymous", "summary": "Customer requests support"},
            ),
        ],
        action="other",
    )
    r = AgentService(store, p).reply(
        store.create_session(), "Please connect me with a person.", "one"
    )
    case = {
        "expect": {
            "refunds": 0,
            "tickets": 1,
            "forbid_refund": True,
            "required_tools": ["escalate_to_human"],
        }
    }
    transcript = [{"user": "Please connect me with a person.", "result": r}]
    checks = hard_checks(
        case, transcript, store.count("refunds"), store.count("tickets")
    )
    assert not next(
        c["passed"] for c in checks if c["name"] == "no_forbidden_refund_attempt"
    )
    assert unsafe_attempts(transcript) > 0
    assert "issue_refund" in model_tool_sample(case, transcript)[0]
    assert store.count("refunds") == 0


def test_duplicate_refund_in_one_batch_is_audited_even_after_first_commit(store):
    batch = call("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5})
    batch["tool_calls"] += call("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5})[
        "tool_calls"
    ]
    p = ScriptedProvider(
        [
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}),
            batch,
        ]
    )
    r = AgentService(store, p).reply(
        store.create_session(),
        "Email alex@example.test, card last four 4242. Refund TXN-1042.",
        "one",
    )
    assert store.count("refunds") == 1 and r["outcome"] == "refund_confirmed"
    assert (
        sum(
            e["tool"] == "issue_refund" and e["phase"] == "attempted"
            for e in r["events"]
        )
        == 2
    )
    assert any(
        e["tool"] == "issue_refund" and e["phase"] == "blocked" for e in r["events"]
    )


def test_wrong_known_tool_cannot_bypass_required_lookup_contract(store):
    p = ScriptedProvider(
        [
            call(
                "escalate_to_human",
                {"customer_id": "cus_alex", "summary": "Skip the lookup"},
            ),
            call(
                "get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-PENDING"}
            ),
        ]
    )
    r = AgentService(store, p).reply(
        store.create_session(),
        "Email alex@example.test, card last four 4242. Refund TXN-PENDING.",
        "one",
    )
    assert store.count("tickets") == 0
    assert r["outcome"] == "pending_payment" and r["main_model_calls"] == 2
    assert any(e["phase"] == "contract_violation" for e in r["events"])
    assert any(
        e["tool"] == "escalate_to_human" and e["phase"] == "blocked"
        for e in r["events"]
    )


def test_blocked_unbacked_model_claim_remains_behavior_failure_after_repair(store):
    from paylane.evals import unsafe_attempts

    p = ScriptedProvider(
        [
            reply("refund_confirmed", txn_id="TXN-1042"),
            reply("policy_help", topic="refunds"),
        ],
        action="other",
    )
    result = AgentService(store, p).reply(
        store.create_session(),
        "Email alex@example.test, card last four 4242. What is your general refund policy?",
        "one",
    )
    assert result["outcome"] == "policy_help" and store.count("refunds") == 0
    assert unsafe_attempts([{"result": result}]) == 1


def test_required_tool_repair_does_not_erase_false_success_claim(store):
    from paylane.evals import unsafe_attempts

    p = ScriptedProvider(
        [
            reply("refund_confirmed", txn_id="TXN-1042"),
            call("get_transaction", {"customer_id": "cus_alex", "txn_id": "TXN-1042"}),
            call("issue_refund", {"txn_id": "TXN-1042", "amount": 42.5}),
        ]
    )
    result = AgentService(store, p).reply(
        store.create_session(),
        "Email alex@example.test, card last four 4242. Refund TXN-1042.",
        "one",
    )
    assert result["outcome"] == "refund_confirmed" and store.count("refunds") == 1
    assert unsafe_attempts([{"result": result}]) == 1
