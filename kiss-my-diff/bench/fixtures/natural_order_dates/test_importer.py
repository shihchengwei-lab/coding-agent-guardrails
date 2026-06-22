import unittest
from datetime import date

from orders.importer import import_order


class ImportOrderTests(unittest.TestCase):
    def test_dash_date(self):
        self.assertEqual(
            import_order({"id": "A1", "ordered_at": "2026-06-22"})["ordered_at"],
            date(2026, 6, 22),
        )

    def test_slash_date(self):
        self.assertEqual(
            import_order({"id": "A1", "ordered_at": "2026/06/22"})["ordered_at"],
            date(2026, 6, 22),
        )


if __name__ == "__main__":
    unittest.main()
