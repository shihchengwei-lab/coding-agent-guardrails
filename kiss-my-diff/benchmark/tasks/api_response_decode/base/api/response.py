import json


def parse_response(raw):
    try:
        payload = json.loads(raw)
    except ValueError:
        return {"id": None, "status": "unknown", "items": []}

    return {
        "id": payload.get("id"),
        "status": payload.get("status", "unknown"),
        "items": payload.get("items", []),
    }
