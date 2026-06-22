import unittest

from flags import is_enabled


class FeatureFlagTests(unittest.TestCase):
    def test_explicit_enabled_flag(self):
        self.assertTrue(is_enabled({"new_nav": True}, "new_nav"))

    def test_missing_flags_use_default(self):
        self.assertFalse(is_enabled(None, "new_nav"))

    def test_unknown_flag_is_disabled(self):
        self.assertFalse(is_enabled({"new_nav": True}, "unknown"))


if __name__ == "__main__":
    unittest.main()
