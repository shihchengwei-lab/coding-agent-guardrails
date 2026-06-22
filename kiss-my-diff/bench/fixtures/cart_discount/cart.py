def total(items):
    amount = 0
    for item in items:
        amount += item["price"] * item["quantity"]
    return round(amount, 2)
