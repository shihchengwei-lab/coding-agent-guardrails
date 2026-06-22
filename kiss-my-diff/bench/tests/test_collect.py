import tempfile
import unittest
from pathlib import Path

from bench.collect import collect_files, dependency_files_changed, diff_stats, detect_new_dependencies


class CollectTests(unittest.TestCase):
    def test_diff_stats_reports_changed_files_and_patch_size(self):
        with tempfile.TemporaryDirectory() as fixture, tempfile.TemporaryDirectory() as work:
            fixture_dir = Path(fixture)
            work_dir = Path(work)
            (fixture_dir / "text_utils.py").write_text("value = 1\n", encoding="utf-8")
            (work_dir / "text_utils.py").write_text("value = 2\n", encoding="utf-8")
            (work_dir / "helpers.py").write_text("def helper():\n    return 1\n", encoding="utf-8")

            stats = diff_stats(fixture_dir, work_dir)

        self.assertEqual(stats["changed_files"], ["helpers.py", "text_utils.py"])
        self.assertEqual(stats["line_delta"], 4)

    def test_dependency_files_changed_flags_common_dependency_files(self):
        changed = ["text_utils.py", "requirements.txt", "package.json"]

        self.assertEqual(
            dependency_files_changed(changed),
            ["package.json", "requirements.txt"],
        )

    def test_detect_new_dependencies_from_requirements_txt(self):
        with tempfile.TemporaryDirectory() as fixture, tempfile.TemporaryDirectory() as work:
            fixture_dir = Path(fixture)
            work_dir = Path(work)
            (fixture_dir / "requirements.txt").write_text("pytest==8.0.0\n", encoding="utf-8")
            (work_dir / "requirements.txt").write_text(
                "pytest==8.0.0\npython-slugify==8.0.4\n",
                encoding="utf-8",
            )

            new_dependencies = detect_new_dependencies(fixture_dir, work_dir)

        self.assertEqual(new_dependencies, ["python-slugify"])

    def test_collect_files_includes_changed_and_quality_check_files(self):
        with tempfile.TemporaryDirectory() as work:
            work_dir = Path(work)
            (work_dir / "app.py").write_text("print('changed')\n", encoding="utf-8")
            (work_dir / "helpers.py").write_text("def helper():\n    pass\n", encoding="utf-8")

            files = collect_files(
                work_dir,
                ["app.py"],
                [{"type": "required_substring", "file": "helpers.py", "value": "helper"}],
            )

        self.assertEqual(set(files), {"app.py", "helpers.py"})
        self.assertIn("changed", files["app.py"])
        self.assertIn("helper", files["helpers.py"])


if __name__ == "__main__":
    unittest.main()
