import re


def make_slug(title):
    words = re.findall(r"[a-z0-9]+", title.lower())
    return "-".join(words)
