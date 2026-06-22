import re


def slugify(text):
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    return cleaned.strip("-")
