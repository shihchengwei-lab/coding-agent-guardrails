from decimal import Decimal, ROUND_HALF_UP


def cents_from_price(value):
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    amount = Decimal(cleaned)
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
