def has_permission(user, permission):
    return permission in user.get("permissions", [])
