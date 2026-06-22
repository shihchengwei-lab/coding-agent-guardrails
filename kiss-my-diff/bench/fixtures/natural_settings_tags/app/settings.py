def load_settings(payload):
    return {
        "name": payload["name"].strip(),
        "tags": payload.get("tags", []),
    }
