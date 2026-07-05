def event_key(event):
    return event.get("id") or f"{event['account_id']}:{event['type']}:{event['amount']}"


def is_voided(event):
    return event.get("status") in {"void", "voided", "reversed"}
