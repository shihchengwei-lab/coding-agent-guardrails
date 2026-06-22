import unittest

from formatter import format_line


class FormatLineTests(unittest.TestCase):
    def test_without_currency_keeps_old_output(self):
        self.assertEqual(format_line({"name": "Tea", "amount": 2}), "Tea: 2")

    def test_with_currency_prefixes_amount(self):
        self.assertEqual(
            format_line({"name": "Coffee", "amount": 3, "currency": "$"}),
            "Coffee: $3",
        )


if __name__ == "__main__":
    unittest.main()
