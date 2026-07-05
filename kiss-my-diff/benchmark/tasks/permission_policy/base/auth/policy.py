from .rules import ROLE_RULES


def has_permission(user, action):
    for role in user.get("roles", []):
        for effect, rule in ROLE_RULES.get(role, []):
            if effect != "allow":
                continue
            if rule == "*" or rule == action:
                return True
            if rule.endswith(":*") and action.startswith(rule[:-1]):
                return True
    return False
