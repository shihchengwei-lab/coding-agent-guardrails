def fallback_name(user):
    return user.get("email", "Unknown user")
