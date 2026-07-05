from ledger.balance import balance_for_account


def test_balance_tracks_credit_and_debit():
    events = [
        {"id": "e1", "account_id": "a1", "type": "credit", "amount": 1000},
        {"id": "e2", "account_id": "a1", "type": "debit", "amount": 250},
        {"id": "e3", "account_id": "a2", "type": "credit", "amount": 999},
    ]

    assert balance_for_account(events, "a1") == 750


def test_voided_events_are_ignored():
    events = [
        {"id": "e1", "account_id": "a1", "type": "credit", "amount": 1000},
        {"id": "e2", "account_id": "a1", "type": "debit", "amount": 250, "status": "voided"},
    ]

    assert balance_for_account(events, "a1") == 1000


def test_duplicate_event_ids_are_counted_once():
    events = [
        {"id": "e1", "account_id": "a1", "type": "credit", "amount": 1000},
        {"id": "e1", "account_id": "a1", "type": "credit", "amount": 1000},
        {"id": "e2", "account_id": "a1", "type": "debit", "amount": 300},
    ]

    assert balance_for_account(events, "a1") == 700
