import re


def safe_filename(value):
    name = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return name or "report"
