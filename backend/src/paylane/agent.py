"""One real LangGraph shared by CLI, FastAPI, and DeepEval."""

import json
import re
import threading
import time
from typing import Literal, TypedDict
from pydantic import ValidationError
from langgraph.graph import StateGraph, START, END
from .domain import StrictModel, refund_decision
from .gateway import Gateway, redact, sanitize
from .guardrails import inspect_input, refunds_enabled
from .provider import BACKEND, ProviderError


class ReplyIntent(StrictModel):
    kind: Literal[
        "verify",
        "clarify_transaction",
        "refund_confirmed",
        "refund_status",
        "already_refunded",
        "handoff_confirmed",
        "handoff_unavailable",
        "pending_payment",
        "payment_unavailable",
        "policy_help",
        "unsupported",
        "unavailable",
    ]
    txn_id: str | None = None
    ack: Literal["none", "frustrated"] = "none"
    topic: Literal["none", "refunds", "verification", "frozen", "transfers"] = "none"


class State(TypedDict, total=False):
    messages: list[dict]
    calls: int
    repairs: int
    last: dict
    intent: dict
    error: str | None
    usage: list[dict]
    text: str
    outcome: str
    customer_action: str
    tool_repairs: int
    retry_tool: bool


def effect_evidence(gateway):
    receipt = gateway.store.receipt(gateway.sid, request_id=gateway.request_id)
    refund = (
        {k: receipt[k] for k in ["id", "txn_id", "amount_cents"]} if receipt else None
    )
    return sanitize({"refund": refund, "ticket": gateway.store.ticket(gateway.sid)})


def render(intent: ReplyIntent, gateway: Gateway):
    s = gateway.session
    k = intent.kind
    prefix = "That sounds frustrating. " if intent.ack == "frustrated" else ""
    if k == "handoff_confirmed":
        ticket = gateway.store.ticket(gateway.sid)
        if not ticket:
            raise ValueError("ticket_evidence_missing")
        if ticket["reason"] == "closure":
            prior = any(
                ticket["id"] in m["content"]
                for m in gateway.store.history(gateway.sid)
                if m["role"] == "assistant"
            )
            text = (
                f"I haven’t closed your account. Your closure request is with support under ticket {ticket['id']}. "
                if prior
                else f"I’ve created support ticket {ticket['id']} for a person to review your closure request. I haven’t closed your account. "
            )
            return (
                prefix
                + text
                + "Please use this reference when following up with Paylane support.",
                k,
            )
        explanations = {
            "verification_failed": "I couldn’t verify those details, so I can’t discuss this account or refund a payment. ",
            "frozen": "I can’t see the freeze reason or unfreeze your card. ",
            "amount_limit": "That payment is above the $75 automatic-refund limit. ",
            "age_limit": "That payment is outside the under-30-day refund window. ",
            "invalid_date": "I couldn’t validate the payment date. ",
            "partial_refund": "I can’t issue a partial refund automatically. ",
            "unsafe_input": "I can’t safely carry out encoded, hidden or highly repetitive instructions. ",
            "automation_disabled": "Automatic actions are currently paused. ",
        }
        prior = any(
            ticket["id"] in m["content"]
            for m in gateway.store.history(gateway.sid)
            if m["role"] == "assistant"
        )
        acknowledgement = (
            "That sounds frustrating. "
            if not prefix
            and re.search(
                r"furious|angry|frustrat|ridiculous", gateway.input_text, re.I
            )
            else prefix
        )
        if prior:
            return (
                acknowledgement
                + f"Your request is already with support under ticket {ticket['id']}. I can’t bypass that review. Please keep this reference when following up with Paylane support.",
                k,
            )
        return (
            acknowledgement
            + explanations.get(ticket["reason"], "")
            + f"I’ve created support ticket {ticket['id']} for a person to review. Please keep this reference when following up with Paylane support.",
            k,
        )
    if k == "handoff_unavailable":
        return (
            prefix
            + "I couldn’t confirm a support ticket. Please contact Paylane support directly; I haven’t completed this request.",
            k,
        )
    if k == "policy_help":
        text = {
            "refunds": "Verified customers can receive a full refund for an eligible payment of $75 or less that is under 30 days old. Larger or older payments need human review.",
            "verification": "Before discussing your account, please confirm the email on your account and your card’s last four digits. Please don’t send your full card number.",
            "frozen": "A person needs to review frozen-card requests. I can’t unfreeze a card or see its freeze reason.",
            "transfers": "I can help explain support options for transfers. A person will need to review any transfer change.",
        }.get(
            intent.topic,
            "I can help with Paylane cards, payment refunds and support handoffs. What do you need help with?",
        )
        return prefix + text, k
    if not s["verified"] or k == "verify":
        if s["verified"]:
            return (
                "Your identity is confirmed. What is the transaction ID for the payment?",
                "clarify_transaction",
            )
        if s["failures"] > 0:
            return (
                prefix
                + "I couldn’t verify those details. Please re-enter both the email on your account and your card’s last four digits. I can’t share the email on file. If you can’t verify, I can connect you with support.",
                "verify",
            )
        if s.get("pending_email") and not s.get("pending_last4"):
            return (
                prefix
                + "Thanks. Please confirm your card’s last four digits. Please don’t send the full card number.",
                "verify",
            )
        if s.get("pending_last4") and not s.get("pending_email"):
            return (
                prefix + "Thanks. Please confirm the email on your account.",
                "verify",
            )
        return (
            prefix
            + "Please confirm the email on your account and your card’s last four digits before we discuss account details. Please don’t send your full card number.",
            "verify",
        )
    if k in {"refund_confirmed", "refund_status"}:
        if k == "refund_status" and (
            not intent.txn_id or not gateway.transaction_supplied(intent.txn_id)
        ):
            raise ValueError("transaction_not_supplied")
        r = gateway.store.receipt(
            gateway.sid,
            intent.txn_id,
            request_id=gateway.request_id if k == "refund_confirmed" else None,
        )
        if not r:
            raise ValueError("refund_evidence_missing")
        if k == "refund_status":
            return (
                prefix
                + f"The refund already issued for this payment was ${r['amount_cents'] / 100:.2f}. Reference: {r['id']}.",
                k,
            )
        return (
            prefix
            + f"Your ${r['amount_cents'] / 100:.2f} refund is confirmed. Reference: {r['id']}. Is there anything else I can help with?",
            k,
        )
    if k in {"already_refunded", "pending_payment"}:
        txn = gateway.reads.get(intent.txn_id)
        expected = "refunded" if k == "already_refunded" else "pending"
        if (
            not intent.txn_id
            or not gateway.transaction_supplied(intent.txn_id)
            or not txn
            or txn.status != expected
        ):
            raise ValueError("transaction_evidence_missing")
        return prefix + (
            "That payment has already been refunded, so I can’t refund it again."
            if expected == "refunded"
            else "That payment is still pending. I can’t refund it automatically; please contact support if it needs review."
        ), k
    if k == "payment_unavailable":
        return (
            prefix
            + "I couldn’t find that payment on your verified account. Please check the transaction ID in your payment record, or contact Paylane support.",
            k,
        )
    if k == "clarify_transaction":
        if len(set(re.findall(r"\bTXN-[A-Za-z0-9]+\b", gateway.selection_text))) > 1:
            return (
                prefix
                + "Which payment should I review? Please send a single transaction ID.",
                k,
            )
        if re.search(
            r"do not have|don't have|cannot find|can.t find|do not know|don't know|not have",
            gateway.input_text,
            re.I,
        ):
            return (
                prefix
                + "Please copy the transaction ID from your payment record so I can identify the right payment. If you can’t find it, I can connect you with support.",
                k,
            )
        return (
            prefix + "What is the transaction ID for the payment you want help with?",
            k,
        )
    if k == "unsupported":
        return (
            prefix
            + "I can help with Paylane cards, payment refunds and support handoffs. Could you tell me what you need?",
            k,
        )
    return (
        prefix
        + "I couldn’t complete this request right now. I haven’t confirmed any new action. Please try again or contact Paylane support.",
        "unavailable",
    )


class AgentService:
    def __init__(self, store, provider):
        self.store, self.provider = store, provider
        self._locks = {}
        self._lock_guard = threading.Lock()
        self.system = (
            (BACKEND / "prompts/system.md").read_text()
            + "\n"
            + (BACKEND / "prompts/rulebook.md").read_text()
        )

    def _lock(self, sid):
        with self._lock_guard:
            return self._locks.setdefault(sid, threading.Lock())

    def reply(self, sid, text, request_id):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
            raise ValueError("invalid_message")
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,80}", request_id
        ):
            raise ValueError("invalid_request_id")
        with self._lock(sid):
            return self._run(sid, text, request_id)

    def _run(self, sid, text, request_id):
        started = time.monotonic()
        deadline = started + 90
        cached = self.store.claim_request(sid, request_id, text)
        if cached and not cached.get("recover"):
            return cached
        g = Gateway(self.store, sid, request_id)
        if cached and cached.get("recover"):
            answer, outcome = render(ReplyIntent(kind="refund_confirmed"), g)
            result = {
                "text": answer,
                "outcome": outcome,
                "events": [],
                "verified": g.session["verified"],
                "usage": [],
                "error": None,
                "latency_ms": 0,
                "recovered": True,
                "effect_evidence": {
                    **effect_evidence(g),
                },
            }
            self.store.complete_request(sid, request_id, result)
            return result
        self.store.touch(sid)
        history = self.store.history(sid)
        raw_text = text
        text, guardrail_decisions, input_handoff = inspect_input(text)
        g.observe_input(raw_text)
        g.set_selection(text, history)
        context = {
            "verified": g.session["verified"],
            "customer_id": g.session["customer_id"]
            if g.session["verified"]
            else "anonymous:" + sid,
            "customer_supplied_transaction_ids": list(
                dict.fromkeys(
                    re.findall(
                        r"\bTXN-[A-Za-z0-9]+\b",
                        " ".join(m["content"] for m in history if m["role"] == "user")
                        + " "
                        + text,
                    )
                )
            ),
            "handoff_required": bool(g.session["handoff"]),
            "identity_issue": g.identity_issue,
            "now": self.store.now().isoformat(),
        }
        messages = (
            [
                {
                    "role": "system",
                    "content": self.system
                    + "\nTrusted session context: "
                    + json.dumps(context),
                }
            ]
            + history
            + [{"role": "user", "content": text}]
        )

        def preflight(state):
            usage = []
            error = None
            s = g.session
            if input_handoff or not refunds_enabled():
                reason = input_handoff or "automation_disabled"
            elif s["handoff"] or s["failures"] >= 3:
                reason = s["handoff"] or "verification_failed"
            else:
                try:
                    risk = self.provider.classify(
                        history + [{"role": "user", "content": text}], deadline=deadline
                    )
                    usage.append({k: v for k, v in risk.items() if k.startswith("_")})
                    g.event(
                        "risk_classifier",
                        "completed",
                        origin="preflight",
                        route=risk.get("route"),
                        reason=risk.get("reason"),
                        action=risk.get("action"),
                        latency_ms=risk.get("_latency_ms"),
                        http_attempts=risk.get("_http_attempts"),
                    )
                    reason = (
                        risk.get("reason", "uncertain")
                        if risk.get("route") != "normal"
                        else None
                    )
                except ProviderError as exc:
                    usage.extend(exc.attempts)
                    g.event(
                        "risk_classifier", "failed", origin="preflight", reason=str(exc)
                    )
                    reason = "uncertain"
                    error = "risk_preflight_unavailable"
            if len(history) >= 40:
                reason = "history_limit"
            guardrail_decisions.append(
                {
                    "layer": "routing",
                    "rule": "mandatory_handoff" if reason else "risk_preflight",
                    "action": "handoff" if reason else "allow",
                    "reason": reason or "normal",
                }
            )
            if reason:
                self.store.latch_handoff(sid, reason)
                try:
                    handoff_result = g.dispatch(
                        "escalate_to_human",
                        {
                            "customer_id": context["customer_id"],
                            "summary": redact(
                                "Customer-reported " + reason + ": " + text
                            )[:1000],
                        },
                        origin="preflight",
                    )
                    if not handoff_result.get("ticket_id"):
                        raise ValueError("ticket_not_created")
                    intent = {
                        "kind": "handoff_confirmed",
                        "topic": "frozen" if reason == "frozen" else "none",
                    }
                except Exception:
                    intent = {"kind": "handoff_unavailable"}
                    error = "handoff_unavailable"
                return {"intent": intent, "usage": usage, "error": error, "calls": 1}
            g.refund_requested = risk.get("action") == "refund_request"
            if g.refund_requested and (
                not s["verified"] or not context["customer_supplied_transaction_ids"]
            ):
                return {
                    "intent": {
                        "kind": "verify" if not s["verified"] else "clarify_transaction"
                    },
                    "usage": usage,
                    "calls": risk.get("_logical_calls", 1),
                    "error": None,
                }
            if (
                g.refund_requested
                and len(set(re.findall(r"\bTXN-[A-Za-z0-9]+\b", g.selection_text))) > 1
            ):
                guardrail_decisions.append(
                    {
                        "layer": "routing",
                        "rule": "ambiguous_transaction",
                        "action": "clarify",
                        "reason": "No unique refund target",
                    }
                )
                return {
                    "intent": {"kind": "clarify_transaction"},
                    "usage": usage,
                    "calls": 1,
                    "error": None,
                }
            return {
                "usage": usage,
                "calls": risk.get("_logical_calls", 1),
                "error": None,
                "customer_action": risk.get("action", "other"),
            }

        main_calls = [0]

        def model(state):
            if state["calls"] >= 8 or time.monotonic() >= deadline:
                return {"intent": {"kind": "unavailable"}, "error": "run_limit"}
            try:
                money_done = any(
                    e.get("tool") == "issue_refund"
                    and e.get("phase") == "executed"
                    and e.get("result", {}).get("ok")
                    for e in g.events
                )
                need_read = bool(
                    not money_done
                    and g.session["verified"]
                    and not g.reads
                    and context["customer_supplied_transaction_ids"]
                    and re.search(
                        r"refund|payment|transaction|charge|merchant|amount|TXN-",
                        text,
                        re.I,
                    )
                )
                available = g.schemas() if state.get("repairs", 0) == 0 else []
                need_refund = bool(
                    not money_done
                    and state.get("customer_action") == "refund_request"
                    and any(
                        refund_decision(t, self.store.now()).allowed
                        for t in g.reads.values()
                    )
                )
                forced = (
                    "get_transaction"
                    if need_read
                    else "issue_refund"
                    if need_refund
                    else None
                )
                if forced and available:
                    available = [
                        t for t in available if t["function"]["name"] == forced
                    ]
                main_calls[0] += 1
                r = self.provider.complete(
                    state["messages"],
                    available,
                    deadline=deadline,
                    require_tool=bool(forced and available),
                    response_schema=ReplyIntent.model_json_schema()
                    if not available
                    else None,
                )
                g.event(
                    "agent_model",
                    "completed",
                    origin="model",
                    latency_ms=r.get("_latency_ms"),
                    http_attempts=r.get("_http_attempts"),
                    provider=r.get("_provider"),
                    finish_reason=r.get("_finish_reason"),
                )
                metadata = {k: v for k, v in r.items() if k.startswith("_")}
                proposed = r.get("tool_calls") or []
                offered = {t["function"]["name"] for t in available}
                unexpected = []
                if isinstance(proposed, list):
                    for proposal in proposed:
                        if not isinstance(proposal, dict) or not isinstance(
                            proposal.get("function"), dict
                        ):
                            continue
                        fn = proposal["function"]
                        name = fn.get("name", "unknown")
                        g.event(
                            name,
                            "proposed",
                            origin="model",
                            arguments=fn.get("arguments", "{}"),
                        )
                        if name not in offered:
                            unexpected.append(name)
                            g.event(
                                name,
                                "blocked",
                                origin="model",
                                reason="tool_not_offered",
                                security_relevant=True,
                            )
                contract_error = (
                    "tool_not_offered"
                    if unexpected
                    else "required_tool_missing"
                    if forced and available and not proposed
                    else None
                )
                if contract_error:
                    try:
                        draft = json.loads(r.get("content") or "{}")
                    except (ValueError, TypeError):
                        draft = {}
                    kind = draft.get("kind") if isinstance(draft, dict) else None
                    if (
                        kind == "refund_confirmed"
                        and not self.store.receipt(sid, request_id=request_id)
                    ) or (kind == "handoff_confirmed" and not self.store.ticket(sid)):
                        g.event(
                            "response",
                            "blocked",
                            origin="backend",
                            proposal_origin="model",
                            reason="unbacked_effect_claim",
                            draft=json.dumps({"kind": kind}),
                        )
                    g.event(
                        "agent_model",
                        "contract_violation",
                        origin="model",
                        reason=contract_error,
                        required_tool=forced,
                    )
                    common = {
                        "calls": state["calls"] + 1,
                        "usage": state["usage"] + [metadata],
                    }
                    if state.get("tool_repairs", 0) >= 1:
                        return common | {
                            "intent": {"kind": "unavailable"},
                            "error": contract_error,
                            "retry_tool": False,
                        }
                    return common | {
                        "tool_repairs": 1,
                        "retry_tool": True,
                        "messages": state["messages"]
                        + [
                            {
                                "role": "system",
                                "content": f"The previous response violated the supplied tool contract ({contract_error}). Use only the supplied tools. Required tool: {forced or 'none; answer with ReplyIntent JSON if no tools are supplied'}. Do not answer payment facts from customer text or transaction-ID spelling.",
                            }
                        ],
                    }
                m = {"role": "assistant", "content": r.get("content")}
                if r.get("tool_calls"):
                    m["tool_calls"] = r["tool_calls"]
                return {
                    "last": r,
                    "retry_tool": False,
                    "tool_repairs": 0,
                    "messages": state["messages"] + [m],
                    "calls": state["calls"] + 1,
                    "usage": state["usage"]
                    + [{k: v for k, v in r.items() if k.startswith("_")}],
                }
            except ProviderError as e:
                fallback = (
                    "refund_confirmed"
                    if self.store.receipt(sid, request_id=request_id)
                    and any(
                        e.get("tool") == "issue_refund"
                        and e.get("phase") == "executed"
                        and e.get("result", {}).get("ok")
                        for e in g.events
                    )
                    else "unavailable"
                )
                return {"intent": {"kind": fallback}, "error": str(e)}

        def tools(state):
            calls = state["last"].get("tool_calls") or []
            messages = list(state["messages"])
            terminal_intent = None
            if not isinstance(calls, list) or any(
                not isinstance(c, dict)
                or not isinstance(c.get("function"), dict)
                or not isinstance(c.get("id"), str)
                for c in calls
            ):
                return {"intent": {"kind": "unavailable"}, "error": "invalid_tool_call"}
            # An explicit escalation in a batch wins over every refund in that batch.
            if any(
                c.get("function", {}).get("name") == "escalate_to_human" for c in calls
            ):
                self.store.latch_handoff(sid, "customer_request")
            if len(calls) > 2:
                for c in calls:
                    fn = c.get("function", {})
                    g.event(fn.get("name", "unknown"), "blocked", reason="batch_limit")
                return {"intent": {"kind": "unavailable"}, "error": "tool_batch_limit"}
            for c in sorted(
                calls,
                key=lambda x: x.get("function", {}).get("name") != "escalate_to_human",
            ):
                fn = c.get("function", {})
                out = g.dispatch(fn.get("name", "unknown"), fn.get("arguments", "{}"))
                if fn.get("name") == "issue_refund" and out.get("ok"):
                    terminal_intent = {
                        "kind": "refund_confirmed",
                        "txn_id": (
                            g.store.receipt(g.sid, request_id=g.request_id) or {}
                        ).get("txn_id"),
                    }
                if fn.get("name") == "escalate_to_human" and out.get("ticket_id"):
                    terminal_intent = {"kind": "handoff_confirmed"}
                if fn.get("name") == "get_transaction":
                    if out.get("error") in {"not_found", "not_authorized"}:
                        terminal_intent = terminal_intent or {
                            "kind": "payment_unavailable"
                        }
                    txn_id = (
                        json.loads(fn["arguments"])["txn_id"]
                        if isinstance(fn.get("arguments"), str)
                        else fn.get("arguments", {}).get("txn_id")
                    )
                    txn = g.reads.get(txn_id)
                    if txn:
                        decision = refund_decision(txn, self.store.now())
                        reason = (
                            "partial_refund"
                            if not g.consent_allows(txn)
                            else decision.reason
                        )
                        if reason in {
                            "amount_limit",
                            "age_limit",
                            "invalid_date",
                            "invalid_amount",
                            "partial_refund",
                        }:
                            self.store.latch_handoff(sid, reason)
                            ticket = g.dispatch(
                                "escalate_to_human",
                                {
                                    "customer_id": context["customer_id"],
                                    "summary": f"Customer payment request for {txn.id}; automatic action requires human review: {reason}.",
                                },
                                origin="policy_guard",
                            )
                            guardrail_decisions.append(
                                {
                                    "layer": "tool",
                                    "rule": "authoritative_payment_policy",
                                    "action": "handoff",
                                    "reason": reason,
                                }
                            )
                            terminal_intent = {
                                "kind": "handoff_confirmed"
                                if ticket.get("ticket_id")
                                else "handoff_unavailable"
                            }
                        if reason in {"not_settled", "already_refunded"}:
                            g.event(
                                "response_route",
                                "resolved",
                                origin="policy_guard",
                                reason=reason,
                            )
                            terminal_intent = terminal_intent or {
                                "kind": "pending_payment"
                                if reason == "not_settled"
                                else "refund_status"
                                if self.store.receipt(sid, txn.id)
                                else "already_refunded",
                                "txn_id": txn.id,
                            }
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": c.get("id", "invalid"),
                        "content": json.dumps(out),
                    }
                )
            return {"messages": messages} | (
                {"intent": terminal_intent} if terminal_intent else {}
            )

        def response(state):
            try:
                intent = ReplyIntent.model_validate(
                    state.get("intent")
                    or json.loads(state.get("last", {}).get("content") or "{}")
                )
                answer, outcome = render(intent, g)
                return {
                    "text": redact(answer),
                    "outcome": outcome,
                    "intent": intent.model_dump(),
                }
            except (ValidationError, ValueError, TypeError):
                g.event(
                    "response",
                    "blocked",
                    origin="backend",
                    proposal_origin="backend" if state.get("intent") else "model",
                    reason="unsupported_response_claim",
                    draft=(state.get("last", {}).get("content") or "")[:1000],
                )
                if (
                    state.get("repairs", 0) < 1
                    and state["calls"] < 8
                    and not state.get("intent")
                ):
                    return {
                        "repairs": 1,
                        "messages": state["messages"]
                        + [
                            {
                                "role": "user",
                                "content": "Return valid ReplyIntent JSON using only actual tool evidence. Do not call tools.",
                            }
                        ],
                    }
                answer, outcome = render(ReplyIntent(kind="unavailable"), g)
                return {
                    "text": answer,
                    "outcome": outcome,
                    "error": state.get("error") or "invalid_response",
                    "intent": {"kind": "unavailable"},
                }

        builder = StateGraph(State)
        for name, node in [
            ("preflight", preflight),
            ("model", model),
            ("tools", tools),
            ("render", response),
        ]:
            builder.add_node(name, node)
        builder.add_edge(START, "preflight")
        builder.add_conditional_edges(
            "preflight", lambda s: "render" if s.get("intent") else "model"
        )
        builder.add_conditional_edges(
            "model",
            lambda s: "model"
            if s.get("retry_tool")
            else "render"
            if s.get("intent") or not s.get("last", {}).get("tool_calls")
            else "tools",
        )
        builder.add_conditional_edges(
            "tools", lambda s: "render" if s.get("intent") else "model"
        )
        builder.add_conditional_edges(
            "render", lambda s: END if s.get("text") else "model"
        )
        graph = builder.compile()
        try:
            state = graph.invoke(
                {"messages": messages, "calls": 0, "repairs": 0, "usage": []},
                config={"recursion_limit": 32},
            )
        except Exception:
            receipt = self.store.receipt(sid, request_id=request_id)
            state = {"error": "internal_error", "usage": []}
            state["text"], state["outcome"] = render(
                ReplyIntent(kind="refund_confirmed" if receipt else "unavailable"), g
            )
        result = {
            "text": state["text"],
            "outcome": state["outcome"],
            "events": g.events,
            "guardrails": guardrail_decisions
            + [
                {
                    "layer": "tool",
                    "rule": e.get("reason", "authorized_execution"),
                    "action": "block" if e["phase"] == "blocked" else "allow",
                    "reason": e.get("reason", e["tool"]),
                }
                for e in g.events
                if e["phase"] in {"blocked", "executed"}
            ]
            + [
                {
                    "layer": "output",
                    "rule": "evidence_bound_renderer",
                    "action": "allow",
                    "reason": "Approved template and sensitive-data projection",
                }
            ],
            "effect_evidence": {
                **effect_evidence(g),
            },
            "verified": g.session["verified"],
            "usage": state.get("usage", []),
            "main_model_calls": main_calls[0],
            "error": state.get("error"),
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
        self.store.save_history(
            sid,
            sanitize(
                history
                + [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": result["text"]},
                ]
            ),
        )
        self.store.complete_request(sid, request_id, result)
        return result
