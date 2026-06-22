import unittest

from parser import parse_bool


class ParseBoolTests(unittest.TestCase):
    def test_boolean_values_pass_through(self):
        self.assertTrue(parse_bool(True))
        self.assertFalse(parse_bool(False))

    def test_string_values(self):
        self.assertTrue(parse_bool("true"))
        self.assertFalse(parse_bool("no"))

    def test_case_and_whitespace(self):
        self.assertTrue(parse_bool(" YES "))
        self.assertFalse(parse_bool("\tFalse\n"))

    def test_unknown_value_still_raises(self):
        with self.assertRaises(ValueError):
            parse_bool("maybe")


if __name__ == "__main__":
    unittest.main()
