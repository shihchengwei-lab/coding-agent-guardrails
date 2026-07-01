import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import corridor_ci


VALID_CORRIDOR = """# Corridor: rating-widget

## Semantic Delta
- Add a controlled rating input.

## Non-goals
- Do not refactor forms or add dependencies.

## Paths
- frontend/src/components/ui/**
- frontend/tests/**

## Stop Condition
- Existing frontend tests still pass.
"""


class CorridorCiTest(unittest.TestCase):
    def test_missing_required_corridor_fails(self):
        report = corridor_ci.evaluate(
            changed_files=["frontend/src/components/ui/rating.tsx"],
            corridor_text=None,
            corridor_required=True,
        )

        self.assertFalse(report.ok)
        self.assertIn("corridor is required", report.issues[0])

    def test_changed_files_must_stay_inside_declared_paths(self):
        report = corridor_ci.evaluate(
            changed_files=[
                ".slime/corridor.md",
                "frontend/src/components/ui/rating.tsx",
                "frontend/src/routes/admin.tsx",
            ],
            corridor_text=VALID_CORRIDOR,
            corridor_required=True,
        )

        self.assertFalse(report.ok)
        self.assertIn("frontend/src/routes/admin.tsx", "\n".join(report.issues))
        self.assertNotIn(".slime/corridor.md", "\n".join(report.issues))

    def test_dependency_manifests_are_flagged_by_default(self):
        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/package.json",
            ],
            corridor_text=VALID_CORRIDOR + "\n- frontend/package.json\n",
            corridor_required=True,
            allow_dependencies=False,
        )

        self.assertFalse(report.ok)
        self.assertIn("dependency manifest changed", "\n".join(report.issues))

    def test_warn_mode_does_not_fail_process(self):
        report = corridor_ci.evaluate(
            changed_files=["frontend/src/routes/admin.tsx"],
            corridor_text=VALID_CORRIDOR,
            corridor_required=True,
        )

        self.assertEqual(corridor_ci.exit_code(report, mode="warn"), 0)
        self.assertEqual(corridor_ci.exit_code(report, mode="fail"), 1)

    def test_cli_reads_changed_files_from_argument_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corridor = root / ".slime" / "corridor.md"
            corridor.parent.mkdir()
            corridor.write_text(VALID_CORRIDOR, encoding="utf-8")
            changed = root / "changed.txt"
            changed.write_text("frontend/src/components/ui/rating.tsx\n", encoding="utf-8")

            code = corridor_ci.main(
                [
                    "--repo",
                    str(root),
                    "--changed-files",
                    str(changed),
                    "--mode",
                    "fail",
                ]
            )

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
