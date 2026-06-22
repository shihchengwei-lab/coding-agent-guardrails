from auth.policy import has_permission


def test_viewer_can_read_but_not_refund():
    user = {"roles": ["viewer"]}

    assert has_permission(user, "invoice:read")
    assert not has_permission(user, "invoice:refund")


def test_billing_admin_cannot_delete_invoice():
    user = {"roles": ["billing_admin"]}

    assert has_permission(user, "invoice:refund")
    assert not has_permission(user, "invoice:delete")


def test_support_refund_alias_is_allowed():
    user = {"roles": ["support"]}

    assert has_permission(user, "refund")
    assert has_permission(user, "invoice:refund")
