import unittest

from shop.coupons import is_valid_coupon


class CouponTests(unittest.TestCase):
    def test_exact_code(self):
        self.assertTrue(is_valid_coupon("SAVE10"))

    def test_spaces_and_case(self):
        self.assertTrue(is_valid_coupon(" save10 "))

    def test_unknown_code(self):
        self.assertFalse(is_valid_coupon("NOPE"))


if __name__ == "__main__":
    unittest.main()
