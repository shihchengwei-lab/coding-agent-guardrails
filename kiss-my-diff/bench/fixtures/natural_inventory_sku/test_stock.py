import unittest

from inventory.stock import find_stock


class FindStockTests(unittest.TestCase):
    def test_exact_sku(self):
        self.assertEqual(find_stock([{"sku": "ABC123", "quantity": 4}], "ABC123"), 4)

    def test_formatted_sku(self):
        self.assertEqual(find_stock([{"sku": "ABC123", "quantity": 4}], "abc-123"), 4)


if __name__ == "__main__":
    unittest.main()
