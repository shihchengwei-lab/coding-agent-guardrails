def import_reading(row):
    return {
        "station": row["station"],
        "temperature_c": float(row["temperature"]),
    }
