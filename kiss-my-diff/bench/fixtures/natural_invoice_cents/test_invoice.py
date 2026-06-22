import unittest
from decimal import Decimal

from billing.invoice import invoice_total


class InvoiceTotalTests(unittest.TestCase):
    def test_rounds_half_up(self):
        self.assertEqual(
            invoice_total([{"unit_price": "1.005", "quantity": 1}], "0"),
            Decimal("1.01"),
        )

    def test_applies_tax_before_rounding(self):
        self.assertEqual(
            invoice_total([{"unit_price": "10.00", "quantity": 2}], "0.0825"),
            Decimal("21.65"),
        )


if __name__ == "__main__":
    unittest.main()
