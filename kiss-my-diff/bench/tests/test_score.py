import unittest

from bench.score import score_result, summarize_results


def small_task():
    return {
        "id": "small_fix",
        "allowed_files": ["text_utils.py"],
        "max_changed_files": 1,
        "max_line_delta": 8,
        "weights": {
            "tests": 0.50,
            "scope": 0.15,
            "simplicity": 0.15,
            "dependencies": 0.10,
            "quality": 0.10,
        },
    }


class ScoreResultTests(unittest.TestCase):
    def test_perfect_result_scores_100(self):
        result = {
            "task_id": "small_fix",
            "variant": "disciplined",
            "tests_passed": True,
            "changed_files": ["text_utils.py"],
            "line_delta": 4,
            "dependency_files_changed": [],
            "new_dependencies": [],
        }

        score = score_result(small_task(), result)

        self.assertEqual(score["total"], 100.0)
        self.assertEqual(score["tests"], 100.0)
        self.assertEqual(score["scope"], 100.0)
        self.assertEqual(score["simplicity"], 100.0)
        self.assertEqual(score["dependencies"], 100.0)
        self.assertEqual(score["quality"], 100.0)

    def test_failed_tests_dominate_score_but_other_metrics_remain_visible(self):
        result = {
            "task_id": "small_fix",
            "variant": "baseline",
            "tests_passed": False,
            "changed_files": ["text_utils.py"],
            "line_delta": 4,
            "dependency_files_changed": [],
            "new_dependencies": [],
        }

        score = score_result(small_task(), result)

        self.assertEqual(score["tests"], 0.0)
        self.assertEqual(score["scope"], 100.0)
        self.assertEqual(score["simplicity"], 100.0)
        self.assertEqual(score["dependencies"], 100.0)
        self.assertEqual(score["total"], 50.0)

    def test_unexpected_files_and_too_many_files_lower_scope_score(self):
        result = {
            "task_id": "small_fix",
            "variant": "baseline",
            "tests_passed": True,
            "changed_files": ["text_utils.py", "helpers.py", "README.md"],
            "line_delta": 4,
            "dependency_files_changed": [],
            "new_dependencies": [],
        }

        score = score_result(small_task(), result)

        self.assertLess(score["scope"], 100.0)
        self.assertGreater(score["scope"], 0.0)
        self.assertEqual(score["total"], 86.67)

    def test_large_line_delta_lowers_simplicity_score(self):
        result = {
            "task_id": "small_fix",
            "variant": "baseline",
            "tests_passed": True,
            "changed_files": ["text_utils.py"],
            "line_delta": 16,
            "dependency_files_changed": [],
            "new_dependencies": [],
        }

        score = score_result(small_task(), result)

        self.assertEqual(score["simplicity"], 0.0)
        self.assertEqual(score["total"], 85.0)

    def test_dependency_changes_zero_dependency_score(self):
        result = {
            "task_id": "small_fix",
            "variant": "baseline",
            "tests_passed": True,
            "changed_files": ["text_utils.py", "requirements.txt"],
            "line_delta": 6,
            "dependency_files_changed": ["requirements.txt"],
            "new_dependencies": ["leftpad"],
        }

        score = score_result(small_task(), result)

        self.assertEqual(score["dependencies"], 0.0)
        self.assertLess(score["total"], 100.0)

    def test_quality_checks_lower_score_without_breaking_other_metrics(self):
        task = small_task()
        task["quality_checks"] = [
            {"type": "required_substring", "file": "text_utils.py", "value": "normalize"},
            {"type": "forbidden_substring", "file": "text_utils.py", "value": "TODO"},
        ]
        result = {
            "task_id": "small_fix",
            "variant": "baseline",
            "tests_passed": True,
            "changed_files": ["text_utils.py"],
            "line_delta": 4,
            "dependency_files_changed": [],
            "new_dependencies": [],
            "files": {"text_utils.py": "def slugify(text):\n    return text\n# TODO\n"},
        }

        score = score_result(task, result)

        self.assertEqual(score["quality"], 0.0)
        self.assertEqual(score["tests"], 100.0)
        self.assertEqual(score["total"], 90.0)

    def test_quality_checks_support_regex(self):
        task = small_task()
        task["quality_checks"] = [
            {"type": "required_regex", "file": "text_utils.py", "value": r"def\s+format_line\(row\):"},
            {"type": "forbidden_regex", "file": "text_utils.py", "value": r"import\s+slugify"},
        ]
        result = {
            "task_id": "small_fix",
            "variant": "disciplined",
            "tests_passed": True,
            "changed_files": ["text_utils.py"],
            "line_delta": 4,
            "dependency_files_changed": [],
            "new_dependencies": [],
            "files": {"text_utils.py": "def format_line(row):\n    return row['name']\n"},
        }

        score = score_result(task, result)

        self.assertEqual(score["quality"], 100.0)


class SummarizeResultsTests(unittest.TestCase):
    def test_summarizes_by_variant(self):
        scored = [
            {"variant": "baseline", "total": 80.0, "tests": 100.0, "quality": 100.0},
            {"variant": "baseline", "total": 60.0, "tests": 0.0, "quality": 0.0},
            {"variant": "disciplined", "total": 90.0, "tests": 100.0, "quality": 100.0},
        ]

        summary = summarize_results(scored)

        self.assertEqual(summary["baseline"]["runs"], 2)
        self.assertEqual(summary["baseline"]["total_avg"], 70.0)
        self.assertEqual(summary["baseline"]["tests_avg"], 50.0)
        self.assertEqual(summary["baseline"]["quality_avg"], 50.0)
        self.assertEqual(summary["disciplined"]["runs"], 1)
        self.assertEqual(summary["disciplined"]["total_avg"], 90.0)


if __name__ == "__main__":
    unittest.main()
