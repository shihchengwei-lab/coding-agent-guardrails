def invoice_total(lines, tax_rate):
    subtotal = sum(line["unit_price"] * line["quantity"] for line in lines)
    return subtotal * (1 + tax_rate)
