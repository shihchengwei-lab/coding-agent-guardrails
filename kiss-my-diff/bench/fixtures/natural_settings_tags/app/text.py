def parse_tag_list(value):
    if isinstance(value, list):
        return value
    return [part.strip() for part in value.split(",") if part.strip()]
