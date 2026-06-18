"""JSON-file note store. Single source of truth — one file, a list of notes."""
import json
import os
import time

DEFAULT_STORE = os.environ.get("NOTES_STORE", "notes.json")


def load(path=None):
    path = path or DEFAULT_STORE
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save(notes, path=None):
    path = path or DEFAULT_STORE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)


def add(text, path=None):
    notes = load(path)
    note = {
        "id": max((n["id"] for n in notes), default=0) + 1,
        "text": text,
        "created_at": time.time(),
    }
    notes.append(note)
    save(notes, path)
    return note
