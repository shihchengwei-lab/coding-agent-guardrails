import unittest

from text_utils import slugify


class SlugifyTests(unittest.TestCase):
    def test_basic_slug(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_accented_latin_characters(self):
        self.assertEqual(slugify("Café au lait"), "cafe-au-lait")

    def test_collapses_separators(self):
        self.assertEqual(slugify(" one --- two "), "one-two")


if __name__ == "__main__":
    unittest.main()
