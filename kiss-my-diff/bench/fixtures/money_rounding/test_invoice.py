import unittest
from decimal import Decimal

from invoice import invoice_total


class InvoiceTotalTests(unittest.TestCase):
    def test_rounds_half_up_to_cents(self):
        items = [{"price": "1.005", "quantity": 1}]

        self.assertEqual(invoice_total(items, "0"), Decimal("1.01"))

    def test_applies_tax_before_rounding(self):
        items = [{"price": "10.00", "quantity": 2}]

        self.assertEqual(invoice_total(items, "0.0825"), Decimal("21.65"))


if __name__ == "__main__":
    unittest.main()
