import unittest

from imports.csv_importer import parse_row


class ParseRowTests(unittest.TestCase):
    def test_clean_headers(self):
        self.assertEqual(parse_row(["email", "name"], ["a@example.com", "Ada"])["email"], "a@example.com")

    def test_spaced_headers(self):
        row = parse_row([" Email ", "Full Name"], ["a@example.com", "Ada"])

        self.assertEqual(row["email"], "a@example.com")
        self.assertEqual(row["full_name"], "Ada")


if __name__ == "__main__":
    unittest.main()
