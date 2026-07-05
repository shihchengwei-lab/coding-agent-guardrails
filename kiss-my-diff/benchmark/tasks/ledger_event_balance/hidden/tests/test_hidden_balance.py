from ledger.balance import balance_for_account


def test_duplicate_event_ids_are_counted_once():
    events = [
        {"id": "e1", "account_id": "a1", "type": "credit", "amount": 1000},
        {"id": "e1", "account_id": "a1", "type": "credit", "amount": 1000},
        {"id": "e2", "account_id": "a1", "type": "debit", "amount": 300},
    ]

    assert balance_for_account(events, "a1") == 700


def test_missing_ids_are_deduped_by_event_key():
    events = [
        {"account_id": "a1", "type": "credit", "amount": 500},
        {"account_id": "a1", "type": "credit", "amount": 500},
        {"account_id": "a1", "type": "debit", "amount": 125},
    ]

    assert balance_for_account(events, "a1") == 375
