import tempfile
import unittest
from pathlib import Path

import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import corridor_ci


VALID_PACKET = """# Review Packet: rating-widget

## What Changed
- Add a controlled rating input.

## Why
- The app needs a reusable rating control.

## Non-goals
- Do not refactor forms or add dependencies.

## Paths
- frontend/src/components/ui/**
- frontend/tests/**

## Verification
- Existing frontend tests still pass.

## Risk
- Low: isolated UI component.
"""


class CorridorCiTest(unittest.TestCase):
    def test_normalize_preserves_dot_directory(self):
        self.assertEqual(
            corridor_ci.normalize_path(".github/workflows/corridor.yml"),
            ".github/workflows/corridor.yml",
        )
        self.assertEqual(
            corridor_ci.normalize_path("./.github/workflows/corridor.yml"),
            ".github/workflows/corridor.yml",
        )

    def test_pr_body_reads_utf8_sig_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(
                json.dumps({"pull_request": {"body": VALID_PACKET}}),
                encoding="utf-8-sig",
            )

            old_event_path = os.environ.get("GITHUB_EVENT_PATH")
            os.environ["GITHUB_EVENT_PATH"] = str(event)
            try:
                body = corridor_ci.find_pr_body()
            finally:
                if old_event_path is None:
                    os.environ.pop("GITHUB_EVENT_PATH", None)
                else:
                    os.environ["GITHUB_EVENT_PATH"] = old_event_path

        self.assertEqual(body, VALID_PACKET)

    def test_missing_required_corridor_fails(self):
        report = corridor_ci.evaluate(
            changed_files=["frontend/src/components/ui/rating.tsx"],
            corridor_text=None,
            corridor_required=True,
        )

        self.assertFalse(report.ok)
        self.assertIn("review packet is required", report.issues[0])

    def test_small_change_without_packet_can_pass(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text=None,
            corridor_required=True,
            small_change_max_files=1,
        )

        self.assertTrue(report.ok)
        self.assertIn("small change fast path", "\n".join(report.warnings))

    def test_small_change_fast_path_does_not_allow_dependencies(self):
        report = corridor_ci.evaluate(
            changed_files=["package.json"],
            corridor_text=None,
            corridor_required=True,
            small_change_max_files=1,
        )

        self.assertFalse(report.ok)
        self.assertIn("dependency manifest changed", "\n".join(report.issues))

    def test_missing_packet_fails_above_small_change_limit(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md", "docs/setup.md"],
            corridor_text=None,
            corridor_required=True,
            small_change_max_files=1,
        )

        self.assertFalse(report.ok)
        self.assertIn("review packet is required", "\n".join(report.issues))

    def test_changed_files_must_stay_inside_declared_paths(self):
        report = corridor_ci.evaluate(
            changed_files=[
                ".slime/corridor.md",
                "frontend/src/components/ui/rating.tsx",
                "frontend/src/routes/admin.tsx",
            ],
            corridor_text=VALID_PACKET,
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
            corridor_text=VALID_PACKET.replace(
                "- frontend/tests/**",
                "- frontend/tests/**\n- frontend/package.json",
            ),
            corridor_required=True,
            allow_dependencies=False,
        )

        self.assertFalse(report.ok)
        self.assertIn("dependency manifest changed", "\n".join(report.issues))

    def test_missing_review_packet_field_fails(self):
        incomplete = VALID_PACKET.replace(
            "## Why\n- The app needs a reusable rating control.\n\n",
            "",
        )

        report = corridor_ci.evaluate(
            changed_files=["frontend/src/components/ui/rating.tsx"],
            corridor_text=incomplete,
            corridor_required=True,
        )

        self.assertFalse(report.ok)
        self.assertIn("review packet is missing `## Why`", "\n".join(report.issues))

    def test_summary_includes_review_packet_and_changed_files(self):
        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=VALID_PACKET,
            corridor_required=True,
        )

        markdown = corridor_ci.render_markdown(report)

        self.assertTrue(report.ok)
        self.assertIn("## Review Packet", markdown)
        self.assertIn("### What Changed", markdown)
        self.assertIn("Add a controlled rating input", markdown)
        self.assertIn("frontend/src/components/ui/rating.tsx", markdown)
        self.assertIn("### Verification", markdown)
        self.assertIn("### Risk", markdown)

    def test_warn_mode_does_not_fail_process(self):
        report = corridor_ci.evaluate(
            changed_files=["frontend/src/routes/admin.tsx"],
            corridor_text=VALID_PACKET,
            corridor_required=True,
        )

        self.assertEqual(corridor_ci.exit_code(report, mode="warn"), 0)
        self.assertEqual(corridor_ci.exit_code(report, mode="fail"), 1)

    def test_cli_reads_changed_files_from_argument_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corridor = root / ".slime" / "corridor.md"
            corridor.parent.mkdir()
            corridor.write_text(VALID_PACKET, encoding="utf-8")
            changed = root / "changed.txt"
            changed.write_text("frontend/src/components/ui/rating.tsx\n", encoding="utf-8")

            code = corridor_ci.main(
                [
                    "--repo",
                    str(root),
                    "--changed-files",
                    f"@{changed}",
                    "--mode",
                    "fail",
                ]
            )

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
