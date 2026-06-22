import unittest

from config.modules import enabled_modules


class EnabledModulesTests(unittest.TestCase):
    def test_ignores_blank_lines(self):
        self.assertEqual(enabled_modules("accounts\n\nbilling"), ["accounts", "billing"])

    def test_ignores_commented_lines(self):
        self.assertEqual(
            enabled_modules("accounts\n# billing\nsearch"),
            ["accounts", "search"],
        )


if __name__ == "__main__":
    unittest.main()
