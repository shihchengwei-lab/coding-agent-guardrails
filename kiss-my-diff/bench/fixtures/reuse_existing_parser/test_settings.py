import unittest

from settings import load_settings


class LoadSettingsTests(unittest.TestCase):
    def test_existing_tag_list_still_works(self):
        settings = load_settings({"name": " Demo ", "tags": ["alpha", "beta"]})

        self.assertEqual(settings, {"name": "Demo", "tags": ["alpha", "beta"]})

    def test_comma_separated_tags_are_split_and_trimmed(self):
        settings = load_settings({"name": "Demo", "tags": "alpha, beta,,gamma"})

        self.assertEqual(settings["tags"], ["alpha", "beta", "gamma"])

    def test_missing_tags_defaults_to_empty_list(self):
        settings = load_settings({"name": "Demo"})

        self.assertEqual(settings["tags"], [])


if __name__ == "__main__":
    unittest.main()
