import json
import unittest
from pathlib import Path


class TasksManifestTests(unittest.TestCase):
    def setUp(self):
        root = Path.cwd()
        self.root = root
        self.tasks = json.loads((root / "bench" / "tasks.json").read_text(encoding="utf-8"))[
            "tasks"
        ]

    def test_task_ids_are_unique(self):
        ids = [task["id"] for task in self.tasks]

        self.assertEqual(len(ids), len(set(ids)))

    def test_fixtures_and_quality_check_files_exist(self):
        for task in self.tasks:
            fixture = self.root / task["fixture"]
            self.assertTrue(fixture.exists(), task["id"])
            self.assertTrue((fixture / task["allowed_files"][0]).exists(), task["id"])
            for check in task.get("quality_checks", []):
                self.assertTrue((fixture / check["file"]).exists(), f"{task['id']}:{check['file']}")

    def test_weights_sum_to_one_when_present(self):
        for task in self.tasks:
            if "weights" not in task:
                continue
            self.assertAlmostEqual(sum(task["weights"].values()), 1.0, places=4, msg=task["id"])

    def test_natural_suite_has_enough_coverage_for_benchmark(self):
        natural_tasks = [task for task in self.tasks if task.get("suite") == "natural"]

        self.assertGreaterEqual(len(natural_tasks), 18)


if __name__ == "__main__":
    unittest.main()
