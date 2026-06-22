import unittest

from profiles.display import display_name


class DisplayNameTests(unittest.TestCase):
    def test_existing_display_name(self):
        self.assertEqual(display_name({"display_name": "Ada"}), "Ada")

    def test_blank_display_name_uses_fallback(self):
        self.assertEqual(
            display_name({"display_name": " ", "email": "ada@example.com"}),
            "ada@example.com",
        )


if __name__ == "__main__":
    unittest.main()
