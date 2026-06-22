def find_stock(items, sku):
    for item in items:
        if item["sku"] == sku:
            return item["quantity"]
    return 0
