from flags.evaluator import is_enabled


def test_disabled_flag_is_false():
    flags = {"new_checkout": {"enabled": False}}

    assert not is_enabled(flags, "new_checkout", {"id": "u1"})


def test_missing_flag_is_false():
    assert not is_enabled({}, "missing", {"id": "u1"})
