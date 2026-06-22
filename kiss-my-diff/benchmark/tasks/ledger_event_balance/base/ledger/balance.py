def balance_for_account(events, account_id):
    total = 0
    for event in events:
        if event["account_id"] != account_id:
            continue
        if event["type"] == "credit":
            total += event["amount"]
        elif event["type"] == "debit":
            total -= event["amount"]
    return total
