import unittest

from content.slugs import make_slug


class MakeSlugTests(unittest.TestCase):
    def test_basic_slug(self):
        self.assertEqual(make_slug("Launch Notes"), "launch-notes")

    def test_stopwords_removed(self):
        self.assertEqual(make_slug("The State of AI"), "state-ai")


if __name__ == "__main__":
    unittest.main()
