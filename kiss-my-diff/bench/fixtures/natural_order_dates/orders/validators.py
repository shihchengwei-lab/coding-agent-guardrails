def require_id(row):
    if not row.get("id"):
        raise ValueError("missing id")
