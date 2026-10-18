from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from paylane.domain import Transaction, refund_decision, dollars_to_cents

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "cents,age,status,reason",
    [
        (7500, 29, "settled", "eligible"),
        (7501, 1, "settled", "amount_limit"),
        (7500, 30, "settled", "age_limit"),
        (7500, 31, "settled", "age_limit"),
        (100, -1, "settled", "invalid_date"),
        (100, 1, "pending", "not_settled"),
        (100, 1, "refunded", "already_refunded"),
        (0, 1, "settled", "invalid_amount"),
    ],
)
def test_refund_boundaries(cents, age, status, reason):
    txn = Transaction(
        id="t1",
        customer_id="c1",
        amount_cents=cents,
        date=NOW - timedelta(days=age),
        merchant="Shop",
        status=status,
    )
    assert refund_decision(txn, NOW).reason == reason


@pytest.mark.parametrize("value", [True, False, -1, 0, "NaN", "Infinity", "1.001"])
def test_bad_money_rejected(value):
    with pytest.raises(ValueError):
        dollars_to_cents(value)


def test_decimal_money_is_exact():
    assert dollars_to_cents(Decimal("42.50")) == 4250
    assert dollars_to_cents(0.29) == 29


def test_sub_day_age_boundary():
    t = Transaction(
        id="t1",
        customer_id="c1",
        amount_cents=7500,
        date=NOW - timedelta(days=30) + timedelta(microseconds=1),
        merchant="Shop",
        status="settled",
    )
    assert refund_decision(t, NOW).allowed
