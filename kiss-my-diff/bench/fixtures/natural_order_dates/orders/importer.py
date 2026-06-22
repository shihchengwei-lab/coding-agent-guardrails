from datetime import date


def import_order(row):
    year, month, day = row["ordered_at"].split("-")
    return {
        "id": row["id"],
        "ordered_at": date(int(year), int(month), int(day)),
    }
