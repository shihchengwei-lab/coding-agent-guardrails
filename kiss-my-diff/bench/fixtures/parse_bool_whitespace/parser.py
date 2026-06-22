def parse_bool(value):
    if isinstance(value, bool):
        return value
    if value in ("yes", "true", "1"):
        return True
    if value in ("no", "false", "0"):
        return False
    raise ValueError(f"Unknown boolean value: {value}")
