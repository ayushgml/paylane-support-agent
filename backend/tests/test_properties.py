from datetime import timedelta
from hypothesis import given, settings, strategies as st
from paylane.domain import Transaction, refund_decision, FIXTURE_NOW


@settings(max_examples=80, derandomize=True)
@given(st.integers(min_value=7501, max_value=10**9))
def test_any_amount_above_limit_is_ineligible(cents):
    t = Transaction(
        id="t",
        customer_id="c",
        amount_cents=cents,
        date=FIXTURE_NOW - timedelta(days=1),
        merchant="Shop",
        status="settled",
    )
    assert refund_decision(t, FIXTURE_NOW).allowed is False


@settings(max_examples=80, derandomize=True)
@given(st.integers(min_value=30 * 86400, max_value=365 * 86400))
def test_any_transaction_at_or_beyond_age_limit_is_ineligible(age_seconds):
    t = Transaction(
        id="t",
        customer_id="c",
        amount_cents=100,
        date=FIXTURE_NOW - timedelta(seconds=age_seconds),
        merchant="Shop",
        status="settled",
    )
    assert refund_decision(t, FIXTURE_NOW).allowed is False
