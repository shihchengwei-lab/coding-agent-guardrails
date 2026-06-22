ALIASES = {
    "manage_users": "users:write",
    "read_reports": "reports:read",
}


def canonical_permission(value):
    return ALIASES.get(value, value)
