from .money import cents_from_price


def order_totals(csv_text):
    lines = csv_text.strip().splitlines()
    totals = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        order_id, sku, quantity, price = line.split(",")
        totals[order_id] = totals.get(order_id, 0) + int(quantity) * cents_from_price(price)
    return totals
