import unittest

from billing.subscriptions import is_active


class SubscriptionTests(unittest.TestCase):
    def test_active_status(self):
        self.assertTrue(is_active({"status": "active"}))

    def test_alias_status(self):
        self.assertTrue(is_active({"status": "PAID"}))

    def test_canceled_status(self):
        self.assertFalse(is_active({"status": "canceled"}))


if __name__ == "__main__":
    unittest.main()
