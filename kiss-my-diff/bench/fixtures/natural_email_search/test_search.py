import unittest

from users.search import find_user


class FindUserTests(unittest.TestCase):
    def test_exact_email_match(self):
        users = [{"id": 1, "email": "ada@example.com"}]

        self.assertEqual(find_user(users, "ada@example.com")["id"], 1)

    def test_case_and_space_insensitive_match(self):
        users = [{"id": 1, "email": "ada@example.com"}]

        self.assertEqual(find_user(users, " ADA@EXAMPLE.COM ")["id"], 1)


if __name__ == "__main__":
    unittest.main()
