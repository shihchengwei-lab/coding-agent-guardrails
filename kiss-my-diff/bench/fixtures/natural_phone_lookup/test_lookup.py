import unittest

from customers.lookup import find_by_phone


class FindByPhoneTests(unittest.TestCase):
    def test_exact_match(self):
        customers = [{"id": 1, "phone": "5551234567"}]

        self.assertEqual(find_by_phone(customers, "5551234567")["id"], 1)

    def test_formatting_is_ignored(self):
        customers = [{"id": 1, "phone": "5551234567"}]

        self.assertEqual(find_by_phone(customers, "(555) 123-4567")["id"], 1)


if __name__ == "__main__":
    unittest.main()
