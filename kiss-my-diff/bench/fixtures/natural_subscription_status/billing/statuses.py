ALIASES = {
    "paid": "active",
    "current": "active",
    "trialing": "active",
}


def canonical_status(value):
    key = value.strip().lower()
    return ALIASES.get(key, key)
