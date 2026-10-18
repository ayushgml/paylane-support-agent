"""Layered guardrail signals. Semantic classifiers never grant account authority."""

import os
import re
import unicodedata
from collections import Counter
from typing import Literal
from .domain import StrictModel
from .privacy import scrub_input


class GuardrailDecision(StrictModel):
    layer: Literal["input", "routing", "tool", "output", "runtime"]
    rule: str
    action: Literal["allow", "redact", "clarify", "block", "handoff"]
    reason: str


def refunds_enabled():
    return os.getenv("PAYLANE_REFUNDS_ENABLED", "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def inspect_input(text):
    safe = scrub_input(text)
    decisions = []
    handoff = None

    def add(rule, action, reason):
        decisions.append(
            GuardrailDecision(
                layer="input", rule=rule, action=action, reason=reason
            ).model_dump()
        )

    if safe != text:
        add(
            "sensitive_input_redacted",
            "redact",
            "PAN/credential patterns removed before model calls",
        )
    if any(unicodedata.category(c) == "Cf" or "\uff01" <= c <= "\uff5e" for c in safe):
        add(
            "unsafe_unicode",
            "handoff",
            "Hidden controls or confusable ASCII require human review",
        )
        handoff = "unsafe_input"
    if re.search(
        r"(?is)\b(?:decode|execute|follow)\b.{0,60}\b(?:base64|rot13|hex encoded)\b",
        safe,
    ):
        add(
            "encoded_execution",
            "handoff",
            "Encoded instructions cannot authorize actions",
        )
        handoff = "unsafe_input"
    words = re.findall(r"\w+", safe.lower())
    if (words and max(Counter(words).values()) > 80) or re.search(r"(.)\1{500,}", safe):
        add(
            "resource_flood", "handoff", "Highly repetitive input requires human review"
        )
        handoff = "unsafe_input"
    if re.search(r"(?i)\bpartial\s+refund|refund\s+(?:only|just)\s+\$", safe):
        add(
            "partial_refund",
            "handoff",
            "Partial refunds are outside the approved automatic scope",
        )
        handoff = "partial_refund"
    if not decisions:
        add(
            "bounded_input",
            "allow",
            "Input within message bounds; authorization remains separate",
        )
    return safe, decisions, handoff
