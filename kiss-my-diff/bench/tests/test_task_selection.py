import unittest

from bench.tasks import select_task_ids


class TaskSelectionTests(unittest.TestCase):
    def test_selects_tasks_by_suite(self):
        tasks = {
            "core_fix": {"id": "core_fix", "suite": "core"},
            "natural_bug": {"id": "natural_bug", "suite": "natural"},
            "legacy": {"id": "legacy"},
        }

        self.assertEqual(select_task_ids(tasks, suite="natural"), ["natural_bug"])

    def test_selects_all_tasks_without_suite(self):
        tasks = {
            "b": {"id": "b", "suite": "natural"},
            "a": {"id": "a"},
        }

        self.assertEqual(select_task_ids(tasks), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
