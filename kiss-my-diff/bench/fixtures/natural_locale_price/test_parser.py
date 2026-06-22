import unittest
from decimal import Decimal

from pricing.parser import import_price


class ImportPriceTests(unittest.TestCase):
    def test_dot_decimal(self):
        self.assertEqual(import_price({"price": "12.50"}), Decimal("12.50"))

    def test_comma_decimal(self):
        self.assertEqual(import_price({"price": "12,50"}), Decimal("12.50"))


if __name__ == "__main__":
    unittest.main()
