from decimal import Decimal


def parse_price(value):
    return Decimal(str(value).strip().replace(",", "."))
