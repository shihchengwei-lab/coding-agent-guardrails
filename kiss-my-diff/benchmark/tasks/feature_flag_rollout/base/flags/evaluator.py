def is_enabled(flags, name, user):
    flag = flags[name]
    if flag.get("enabled") is False:
        return False
    rollout = flag.get("rollout")
    if rollout is None:
        return True
    return hash(user["id"]) % 100 < rollout
