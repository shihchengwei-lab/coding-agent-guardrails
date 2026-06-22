import pytest

from payments.errors import InvalidTransition
from payments.state import apply_event


def test_valid_payment_flow():
    state = "created"
    state = apply_event(state, "authorize")
    state = apply_event(state, "capture")
    state = apply_event(state, "refund")

    assert state == "refunded"


def test_cannot_capture_before_authorization():
    with pytest.raises(InvalidTransition):
        apply_event("created", "capture")


def test_cannot_refund_before_capture():
    with pytest.raises(InvalidTransition):
        apply_event("authorized", "refund")
