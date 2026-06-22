import unittest

from auth.permissions import has_permission


class HasPermissionTests(unittest.TestCase):
    def test_current_permission(self):
        self.assertTrue(has_permission({"permissions": ["users:write"]}, "users:write"))

    def test_legacy_permission_alias(self):
        self.assertTrue(has_permission({"permissions": ["manage_users"]}, "users:write"))


if __name__ == "__main__":
    unittest.main()
