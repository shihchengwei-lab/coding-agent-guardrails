from decimal import Decimal


def import_price(row):
    return Decimal(row["price"])
