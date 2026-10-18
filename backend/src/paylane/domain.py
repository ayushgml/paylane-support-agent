"""Pure policy. No model, network, or storage dependencies."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import BaseModel, ConfigDict

POLICY_VERSION = "paylane-v1"
FIXTURE_NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Transaction(StrictModel):
    id: str
    customer_id: str
    amount_cents: int
    date: datetime
    merchant: str
    status: Literal["settled", "pending", "refunded"]


class Decision(StrictModel):
    allowed: bool
    reason: str


def dollars_to_cents(value) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid_amount")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid_amount") from None
    if (
        not number.is_finite()
        or number <= 0
        or number * 100 != (number * 100).to_integral_value()
    ):
        raise ValueError("invalid_amount")
    return int(number * 100)


def refund_decision(txn: Transaction, now: datetime) -> Decision:
    reason = "eligible"
    if txn.amount_cents <= 0:
        reason = "invalid_amount"
    elif txn.date.tzinfo is None or now.tzinfo is None or txn.date > now:
        reason = "invalid_date"
    elif txn.status == "refunded":
        reason = "already_refunded"
    elif txn.status != "settled":
        reason = "not_settled"
    elif txn.amount_cents > 7500:
        reason = "amount_limit"
    elif now - txn.date >= timedelta(days=30):
        reason = "age_limit"
    return Decision(allowed=reason == "eligible", reason=reason)
