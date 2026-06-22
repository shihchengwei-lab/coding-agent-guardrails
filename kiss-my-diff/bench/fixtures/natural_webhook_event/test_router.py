import unittest

from webhooks.router import route_event


class RouteEventTests(unittest.TestCase):
    def test_current_event_name(self):
        self.assertEqual(route_event({"type": "invoice_paid"}), "billing")

    def test_legacy_event_name(self):
        self.assertEqual(route_event({"type": "invoice.paid"}), "billing")


if __name__ == "__main__":
    unittest.main()
