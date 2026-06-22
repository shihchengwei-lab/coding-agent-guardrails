import unittest
from pathlib import Path

from bench.report import filter_rows_by_suite, result_context, summarize_by_model_variant


class ResultContextTests(unittest.TestCase):
    def test_extracts_model_variant_and_task_from_result_path(self):
        path = Path("bench/runs/gpt-5.4-mini/disciplined/one_line_clamp/result.json")

        context = result_context(path)

        self.assertEqual(
            context,
            {
                "model": "gpt-5.4-mini",
                "variant": "disciplined",
                "task_id": "one_line_clamp",
            },
        )

    def test_extracts_context_from_named_runs_directory(self):
        path = Path("bench/runs-natural/gpt-5.4-mini/disciplined/natural_email_search/result.json")

        context = result_context(path)

        self.assertEqual(context["model"], "gpt-5.4-mini")
        self.assertEqual(context["variant"], "disciplined")
        self.assertEqual(context["task_id"], "natural_email_search")

    def test_rejects_paths_outside_runs_layout(self):
        with self.assertRaises(ValueError):
            result_context(Path("bench/results/result.json"))


class SummaryTests(unittest.TestCase):
    def test_summarizes_by_model_and_variant(self):
        rows = [
            {
                "model": "gpt-5.4",
                "variant": "baseline",
                "total": 100.0,
                "tests": 100.0,
                "quality": 100.0,
                "line_delta": 4,
                "dependency_incidents": 0,
            },
            {
                "model": "gpt-5.4",
                "variant": "baseline",
                "total": 80.0,
                "tests": 0.0,
                "quality": 50.0,
                "line_delta": 8,
                "dependency_incidents": 1,
            },
            {
                "model": "gpt-5.4",
                "variant": "disciplined",
                "total": 100.0,
                "tests": 100.0,
                "quality": 100.0,
                "line_delta": 2,
                "dependency_incidents": 0,
            },
        ]

        summary = summarize_by_model_variant(rows)

        self.assertEqual(summary[0]["model"], "gpt-5.4")
        self.assertEqual(summary[0]["variant"], "baseline")
        self.assertEqual(summary[0]["runs"], 2)
        self.assertEqual(summary[0]["total_avg"], 90.0)
        self.assertEqual(summary[0]["pass_rate"], 50.0)
        self.assertEqual(summary[0]["quality_avg"], 75.0)
        self.assertEqual(summary[0]["avg_line_delta"], 6.0)
        self.assertEqual(summary[0]["dependency_incidents"], 1)
        self.assertEqual(summary[1]["variant"], "disciplined")

    def test_filters_rows_by_suite(self):
        tasks = {
            "a": {"id": "a", "suite": "natural"},
            "b": {"id": "b", "suite": "core"},
        }
        rows = [
            {"task_id": "a", "model": "m", "variant": "baseline"},
            {"task_id": "b", "model": "m", "variant": "baseline"},
        ]

        filtered = filter_rows_by_suite(rows, tasks, "natural")

        self.assertEqual(filtered, [rows[0]])


if __name__ == "__main__":
    unittest.main()
