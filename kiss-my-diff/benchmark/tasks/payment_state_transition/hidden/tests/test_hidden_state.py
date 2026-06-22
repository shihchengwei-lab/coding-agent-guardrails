import pytest

from payments.errors import InvalidTransition
from payments.state import apply_event


def test_canceled_payment_cannot_be_captured():
    with pytest.raises(InvalidTransition):
        apply_event("canceled", "capture")


def test_unknown_events_raise_instead_of_preserving_state():
    with pytest.raises(InvalidTransition):
        apply_event("created", "chargeback")
