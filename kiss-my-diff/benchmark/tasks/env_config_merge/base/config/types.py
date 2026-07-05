def coerce_value(raw, template):
    if isinstance(template, bool):
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(template, list):
        return [part.strip() for part in str(raw).split(",") if part.strip()]
    if isinstance(template, int):
        return int(raw)
    return raw
