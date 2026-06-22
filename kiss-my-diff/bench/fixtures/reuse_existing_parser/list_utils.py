def split_csv(value):
    return [part.strip() for part in value.split(",") if part.strip()]
