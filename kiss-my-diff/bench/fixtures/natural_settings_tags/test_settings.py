import unittest

from app.settings import load_settings


class LoadSettingsTests(unittest.TestCase):
    def test_list_tags_still_work(self):
        self.assertEqual(
            load_settings({"name": " Demo ", "tags": ["ops", "beta"]}),
            {"name": "Demo", "tags": ["ops", "beta"]},
        )

    def test_comma_separated_tags_are_split(self):
        self.assertEqual(
            load_settings({"name": "Demo", "tags": "ops, beta,,internal"})["tags"],
            ["ops", "beta", "internal"],
        )


if __name__ == "__main__":
    unittest.main()
