ACTION_ALIASES = {
    "refund": "invoice:refund",
    "read_invoice": "invoice:read",
}

ROLE_RULES = {
    "viewer": [("allow", "invoice:read")],
    "billing_admin": [
        ("allow", "invoice:*"),
        ("deny", "invoice:delete"),
    ],
    "support": [
        ("allow", "invoice:read"),
        ("allow", "refund"),
    ],
    "owner": [("allow", "*")],
}


def expand_action(action):
    return ACTION_ALIASES.get(action, action)
