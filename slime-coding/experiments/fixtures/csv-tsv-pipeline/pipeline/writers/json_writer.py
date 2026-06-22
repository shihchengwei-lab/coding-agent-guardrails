"""JSON writer: write a list of dicts to a JSON file."""
import json


def write(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
