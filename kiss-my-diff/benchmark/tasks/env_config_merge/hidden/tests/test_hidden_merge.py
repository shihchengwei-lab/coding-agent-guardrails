from config.merge import resolve_config


def test_lists_and_ints_are_coerced_from_strings():
    defaults = {"allowed_hosts": ["localhost"], "workers": 2}
    env = {"allowed_hosts": "api.local, admin.local", "workers": "4"}

    assert resolve_config(defaults, env) == {
        "allowed_hosts": ["api.local", "admin.local"],
        "workers": 4,
    }


def test_unknown_keys_are_ignored():
    defaults = {"debug": False}

    assert resolve_config(defaults, {"debug": "yes", "secret": "oops"}) == {"debug": True}
