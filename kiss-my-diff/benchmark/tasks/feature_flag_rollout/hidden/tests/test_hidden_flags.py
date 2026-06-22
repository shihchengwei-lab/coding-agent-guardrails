from flags.bucket import stable_bucket
from flags.evaluator import is_enabled


def test_rollout_uses_stable_bucket():
    flags = {"new_checkout": {"enabled": True, "rollout": 50}}
    user = {"id": "user-123"}

    assert is_enabled(flags, "new_checkout", user) is (stable_bucket("user-123", "new_checkout") < 50)


def test_full_and_zero_rollouts_are_respected():
    user = {"id": "user-456"}

    assert is_enabled({"a": {"enabled": True, "rollout": 100}}, "a", user)
    assert not is_enabled({"a": {"enabled": True, "rollout": 0}}, "a", user)
