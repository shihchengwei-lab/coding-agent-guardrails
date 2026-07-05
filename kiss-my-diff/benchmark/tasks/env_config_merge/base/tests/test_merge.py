from config.merge import resolve_config


def test_blank_values_do_not_override_defaults():
    defaults = {"debug": False, "host": "127.0.0.1"}

    assert resolve_config(defaults, {"host": ""}) == defaults


def test_boolean_values_are_coerced_from_strings():
    defaults = {"debug": False}

    assert resolve_config(defaults, {"debug": "true"}) == {"debug": True}


def test_unknown_keys_are_ignored():
    defaults = {"debug": False}

    assert resolve_config(defaults, {"debug": "yes", "secret": "oops"}) == {"debug": True}
