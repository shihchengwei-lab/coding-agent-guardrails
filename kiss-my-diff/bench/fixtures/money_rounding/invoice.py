def invoice_total(items, tax_rate):
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    return subtotal * (1 + tax_rate)
