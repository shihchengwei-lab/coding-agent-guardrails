import unittest

from cart import total


class CartTests(unittest.TestCase):
    def test_total_without_discount(self):
        items = [{"price": 12.5, "quantity": 2}]
        self.assertEqual(total(items), 25.0)

    def test_total_with_item_discount(self):
        items = [{"price": 10.0, "quantity": 2, "discount": 0.10}]
        self.assertEqual(total(items), 18.0)

    def test_mixed_discounted_and_full_price_items(self):
        items = [
            {"price": 10.0, "quantity": 1, "discount": 0.25},
            {"price": 5.0, "quantity": 2},
        ]
        self.assertEqual(total(items), 17.5)


if __name__ == "__main__":
    unittest.main()
