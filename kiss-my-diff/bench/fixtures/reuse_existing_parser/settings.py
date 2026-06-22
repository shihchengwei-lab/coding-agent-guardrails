def load_settings(raw):
    return {
        "name": raw["name"].strip(),
        "tags": raw.get("tags", []),
    }
