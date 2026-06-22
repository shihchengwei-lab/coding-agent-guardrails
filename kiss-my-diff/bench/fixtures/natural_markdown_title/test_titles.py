import unittest

from docs.titles import extract_title


class ExtractTitleTests(unittest.TestCase):
    def test_plain_heading(self):
        self.assertEqual(extract_title("# Report"), "Report")

    def test_indented_heading(self):
        self.assertEqual(extract_title("  # Report"), "Report")


if __name__ == "__main__":
    unittest.main()
