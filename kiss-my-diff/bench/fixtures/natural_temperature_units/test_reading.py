import unittest

from weather.reading import import_reading


class ImportReadingTests(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(import_reading({"station": "TPE", "temperature": "21.5"})["temperature_c"], 21.5)

    def test_unit_suffix(self):
        self.assertEqual(import_reading({"station": "TPE", "temperature": "21.5 °C"})["temperature_c"], 21.5)


if __name__ == "__main__":
    unittest.main()
