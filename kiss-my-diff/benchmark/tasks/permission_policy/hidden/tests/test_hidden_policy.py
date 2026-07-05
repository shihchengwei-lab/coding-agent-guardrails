from auth.policy import has_permission


def test_aliases_are_expanded_for_rules_and_requested_actions():
    support = {"roles": ["support"]}

    assert has_permission(support, "read_invoice")


def test_deny_wins_even_when_another_role_allows():
    user = {"roles": ["owner", "billing_admin"]}

    assert not has_permission(user, "invoice:delete")
    assert has_permission(user, "invoice:read")
