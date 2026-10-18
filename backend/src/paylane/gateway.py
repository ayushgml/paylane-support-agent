"""Only entry point for model-requested business tools."""

import json
import re
from decimal import Decimal
from pydantic import Field, StrictStr, ValidationError
from .domain import StrictModel, dollars_to_cents, refund_decision

from .privacy import EMAIL, PAN, LAST4, redact, sanitize
from .guardrails import refunds_enabled


class GetCustomer(StrictModel):
    email: StrictStr = Field(min_length=1, max_length=254)


class GetTransaction(StrictModel):
    customer_id: StrictStr = Field(min_length=1, max_length=80)
    txn_id: StrictStr = Field(min_length=1, max_length=80)


class IssueRefund(StrictModel):
    txn_id: StrictStr = Field(min_length=1, max_length=80)
    amount: Decimal


class Escalate(StrictModel):
    customer_id: StrictStr = Field(min_length=1, max_length=100)
    summary: StrictStr = Field(min_length=1, max_length=1000)


ARGUMENTS = {
    "get_customer": GetCustomer,
    "get_transaction": GetTransaction,
    "issue_refund": IssueRefund,
    "escalate_to_human": Escalate,
}
DESCRIPTIONS = {
    "get_customer": "Look up the customer using their supplied email. Lookup alone does NOT verify identity. Returns a sanitized result; before verification no account details are disclosed.",
    "get_transaction": "Read a transaction belonging to the verified session customer. Never guess a transaction ID.",
    "issue_refund": "Refund the exact original amount ONLY after a successful eligible transaction read in this turn. Requires verified identity, owned settled unrefunded transaction, amount <= $75 and age strictly under 30 days. No split/partial refunds.",
    "escalate_to_human": "Create a human-support ticket for legal action, fraud, closure, frozen-card help or an ineligible refund. Works before verification using an anonymous session; customer_id cannot grant access.",
}


class MockAPI:
    """Assignment JSON API with actor/operation context injected by the gateway."""

    def __init__(self, store, sid, operation):
        self.store, self.sid, self.operation = store, sid, operation

    def get_customer(self, email):
        return self.store.customer(email) or {"error": "not_found"}

    def get_transaction(self, customer_id, txn_id):
        t = self.store.transaction(customer_id, txn_id)
        if not t:
            return {"error": "not_found"}
        return {
            "amount": t.amount_cents / 100,
            "date": t.date.isoformat(),
            "merchant": t.merchant,
            "status": t.status,
        }

    def issue_refund(self, txn_id, amount):
        return self.store.refund(
            self.sid, txn_id, dollars_to_cents(amount), self.operation
        )

    def escalate_to_human(self, customer_id, summary):
        return self.store.escalate(
            self.sid,
            self.store.session(self.sid)["handoff"] or "customer_request",
            redact(summary),
        )


class Gateway:
    def __init__(self, store, sid, request_id):
        self.store, self.sid, self.request_id = store, sid, request_id
        self.events = []
        self.reads = {}
        self.identity_issue = None
        self.tool_count = 0
        self.input_text = ""
        self.refund_requested = False
        self.selection_text = ""
        self.consent_text = ""

    @property
    def session(self):
        return self.store.session(self.sid)

    def event(self, tool, phase, origin="model", **attributes):
        e = sanitize({"tool": tool, "phase": phase, "origin": origin, **attributes})
        self.events.append(e)
        self.store.audit(self.sid, self.request_id, e)

    def set_selection(self, text, history=()):
        # Mock transaction references have the TXN- prefix. The newest customer
        # selection replaces earlier selections; assistant/tool text never grants scope.
        previous = [
            m["content"]
            for m in history
            if m["role"] == "user" and re.search(r"\bTXN-[A-Za-z0-9]+\b", m["content"])
        ]
        self.selection_text = (
            text
            if re.search(r"\bTXN-[A-Za-z0-9]+\b", text)
            else (previous[-1] if previous else text)
        )
        previous_refs = (
            set(re.findall(r"\bTXN-[A-Za-z0-9]+\b", previous[-1]))
            if previous
            else set()
        )
        current_refs = set(re.findall(r"\bTXN-[A-Za-z0-9]+\b", text))
        self.consent_text = (
            text
            if current_refs and previous_refs and current_refs != previous_refs
            else " ".join(m["content"] for m in history if m["role"] == "user")
            + " "
            + text
        )

    def consent_amount(self):
        matches = re.findall(
            r"(?i)\b(?:refund|return|credit)(?:\s+(?:me|my|the|only|just|of|exactly|for|please)){0,4}\s+\$(\d{1,7}(?:\.\d{1,2})?)",
            self.consent_text,
        )
        if not matches:
            return None
        try:
            return dollars_to_cents(matches[-1])
        except ValueError:
            return -1

    def consent_allows(self, txn):
        cents = self.consent_amount()
        return cents is None or cents == txn.amount_cents

    def transaction_supplied(self, txn_id):
        return bool(
            re.search(
                r"(?<![\w-])" + re.escape(txn_id) + r"(?![\w-])", self.selection_text
            )
        )

    def refund_target(self, txn_id):
        refs = set(re.findall(r"\bTXN-[A-Za-z0-9]+\b", self.selection_text))
        return self.transaction_supplied(txn_id) and len(refs) <= 1

    def observe_input(self, text):
        self.input_text = text
        self.set_selection(text)
        emails = list(dict.fromkeys(x.casefold() for x in EMAIL.findall(text)))
        # Four-digit candidates must be explicit card proof, not TXN suffixes.
        candidates = (
            LAST4.findall(PAN.sub("", text))
            if re.search(r"card|last\s*(?:four|4)|digits|ending", text, re.I)
            else ([text.strip()] if re.fullmatch("[0-9]{4}", text.strip()) else [])
        )
        cards = list(dict.fromkeys(candidates))
        if len(emails) > 1 or len(cards) > 1:
            self.identity_issue = "ambiguous_identity"
            return
        if not emails and not cards:
            return
        email, card = self.store.pending(
            self.sid, emails[0] if emails else None, cards[0] if cards else None
        )
        if email and card:
            ok = self.store.verify(self.sid, email, card)
            self.identity_issue = None if ok else "verification_failed"
            self.event("verification", "verified" if ok else "failed", origin="backend")

    def available_tools(self):
        s = self.session
        names = ["escalate_to_human"]
        if s["verified"]:
            names.append("get_customer")
        if s["verified"] and not s["handoff"]:
            names.append("get_transaction")
            if (
                self.refund_requested
                and refunds_enabled()
                and any(
                    refund_decision(t, self.store.now()).allowed
                    and self.consent_allows(t)
                    for t in self.reads.values()
                )
            ):
                names.append("issue_refund")
        return names

    def schemas(self):
        schemas = []
        for name in self.available_tools():
            schema = ARGUMENTS[name].model_json_schema()
            # Amount JSON is a number at the API boundary, not a numeric-string union.
            if name == "issue_refund":
                schema["properties"]["amount"] = {
                    "type": "number",
                    "exclusiveMinimum": 0,
                }
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": DESCRIPTIONS[name],
                        "parameters": schema,
                    },
                }
            )
        return schemas

    def dispatch(self, name, arguments, origin="model"):
        self.tool_count += 1
        self.event(name, "attempted", origin=origin, arguments=arguments)

        def deny(reason):
            self.event(
                name,
                "blocked",
                origin=origin,
                reason=reason,
                security_relevant=reason != "not_found",
            )
            return (
                {"error": reason, "ok": False}
                if name == "issue_refund"
                else {"error": reason}
            )

        if self.tool_count > 8:
            return deny("tool_budget_exceeded")
        if name not in ARGUMENTS:
            return deny("unknown_tool")
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            args = ARGUMENTS[name].model_validate(arguments).model_dump()
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
            return deny("invalid_arguments")
        s = self.session
        api = MockAPI(
            self.store,
            self.sid,
            self.sid + ":" + self.request_id + ":" + name + ":" + str(self.tool_count),
        )
        if name == "escalate_to_human":
            self.store.latch_handoff(self.sid, s["handoff"] or "customer_request")
            result = api.escalate_to_human(
                "anonymous:" + self.sid if not s["verified"] else s["customer_id"],
                args["summary"],
            )
        elif name == "get_customer":
            if not s["verified"]:
                return deny("verification_required")
            record = api.get_customer(args["email"])
            if record.get("id") != s["customer_id"]:
                return deny("not_authorized")
            result = {k: record[k] for k in ["id", "name", "status"]} | {
                "verified": True
            }
        else:
            if not s["verified"]:
                return deny("verification_required")
            if s["handoff"]:
                return deny("mandatory_handoff")
            if name == "get_transaction":
                if args["customer_id"] != s["customer_id"]:
                    return deny("not_authorized")
                if not self.transaction_supplied(args["txn_id"]):
                    return deny("transaction_not_supplied")
                t = self.store.transaction(s["customer_id"], args["txn_id"])
                if not t:
                    return deny("not_found")
                result = api.get_transaction(s["customer_id"], args["txn_id"])
                self.reads[t.id] = t
                result["policy"] = refund_decision(t, self.store.now()).model_dump()
            else:
                if not self.refund_requested:
                    return deny("refund_not_requested")
                if not refunds_enabled():
                    return deny("automation_disabled")
                if not self.refund_target(args["txn_id"]):
                    return deny("transaction_not_supplied")
                t = self.store.transaction(s["customer_id"], args["txn_id"])
                if not t:
                    return deny("not_authorized")
                if not self.consent_allows(t):
                    return deny("consent_amount_mismatch")
                if t.id not in self.reads:
                    return deny("transaction_read_required")
                decision = refund_decision(t, self.store.now())
                if not decision.allowed:
                    return deny(decision.reason)
                try:
                    cents = dollars_to_cents(args["amount"])
                except ValueError:
                    return deny("invalid_amount")
                if cents != t.amount_cents:
                    return deny("amount_mismatch")
                result = api.issue_refund(t.id, args["amount"])
                self.reads.pop(t.id, None)
        self.event(name, "executed", origin=origin, result=result)
        return sanitize(result)
