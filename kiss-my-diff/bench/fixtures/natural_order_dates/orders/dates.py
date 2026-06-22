from datetime import date


def parse_order_date(value):
    if "-" in value:
        year, month, day = value.split("-")
    else:
        year, month, day = value.split("/")
    return date(int(year), int(month), int(day))
