import unittest

from math_utils import clamp


class ClampTests(unittest.TestCase):
    def test_inside_range_returns_value(self):
        self.assertEqual(clamp(5, 1, 10), 5)

    def test_below_range_returns_minimum(self):
        self.assertEqual(clamp(-2, 1, 10), 1)

    def test_above_range_returns_maximum(self):
        self.assertEqual(clamp(12, 1, 10), 10)


if __name__ == "__main__":
    unittest.main()
