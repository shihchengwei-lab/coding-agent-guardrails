import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import corridor_ci


VALID_HANDOFF = """Decision: #123
Scope: frontend/src/components/ui/rating.tsx, frontend/tests/rating.spec.ts
Review first: frontend/src/components/ui/rating.tsx
Verified: python -m unittest
Risk: none
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
                json.dumps({"pull_request": {"body": VALID_HANDOFF}}),
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

        self.assertEqual(body, VALID_HANDOFF)

    def test_missing_required_handoff_fails(self):
        report = corridor_ci.evaluate(
            changed_files=["frontend/src/components/ui/rating.tsx"],
            corridor_text=None,
        )

        self.assertFalse(report.ok)
        self.assertIn("compact handoff is required", report.issues[0])

        markdown = corridor_ci.render_markdown(report)
        self.assertIn("## Copyable Review Handoff", markdown)
        self.assertIn("Decision:", markdown)
        self.assertIn("Scope: auto", markdown)

    def test_small_change_without_handoff_can_pass(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text=None,
            small_change_max_files=1,
        )

        self.assertTrue(report.ok)
        self.assertIn("small change fast path", "\n".join(report.warnings))

    def test_small_change_fast_path_does_not_allow_dependencies(self):
        report = corridor_ci.evaluate(
            changed_files=["package.json"],
            corridor_text=None,
            small_change_max_files=1,
        )

        self.assertFalse(report.ok)
        self.assertIn("dependency manifest changed", "\n".join(report.issues))

    def test_missing_handoff_fails_above_small_change_limit(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md", "docs/setup.md"],
            corridor_text=None,
            small_change_max_files=1,
        )

        self.assertFalse(report.ok)
        self.assertIn("compact handoff is required", "\n".join(report.issues))

    def test_handoff_passes_and_renders(self):
        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=VALID_HANDOFF,
        )

        markdown = corridor_ci.render_markdown(report)

        self.assertTrue(report.ok)
        self.assertIn("## Review Handoff", markdown)
        self.assertIn("### Decision", markdown)
        self.assertIn("#123", markdown)
        self.assertIn("frontend/src/components/ui/rating.tsx", markdown)

    def test_handoff_scope_must_cover_changed_files(self):
        handoff = VALID_HANDOFF.replace(
            "Scope: frontend/src/components/ui/rating.tsx, frontend/tests/rating.spec.ts",
            "Scope: frontend/src/components/ui/rating.tsx",
        )

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertFalse(report.ok)
        self.assertIn("frontend/tests/rating.spec.ts", "\n".join(report.issues))

    def test_review_first_must_be_changed_file(self):
        handoff = VALID_HANDOFF.replace(
            "Review first: frontend/src/components/ui/rating.tsx",
            "Review first: frontend/src/routes/admin.tsx",
        )

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertFalse(report.ok)
        self.assertIn("review first is not a changed file", "\n".join(report.issues))

    def test_scope_auto_uses_changed_files(self):
        handoff = VALID_HANDOFF.replace(
            "Scope: frontend/src/components/ui/rating.tsx, frontend/tests/rating.spec.ts",
            "Scope: auto",
        )

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertTrue(report.ok)
        self.assertEqual(
            report.allowed_paths,
            [
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
        )

    def test_dependency_manifests_are_flagged_by_default(self):
        handoff = VALID_HANDOFF.replace(
            "Scope: frontend/src/components/ui/rating.tsx, frontend/tests/rating.spec.ts",
            "Scope: frontend/src/components/ui/rating.tsx, frontend/package.json",
        )

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/package.json",
            ],
            corridor_text=handoff,
            allow_dependencies=False,
        )

        self.assertFalse(report.ok)
        self.assertIn("dependency manifest changed", "\n".join(report.issues))

    def test_warn_mode_does_not_fail_process(self):
        report = corridor_ci.evaluate(
            changed_files=["frontend/src/routes/admin.tsx"],
            corridor_text=VALID_HANDOFF,
        )

        self.assertEqual(corridor_ci.exit_code(report, mode="warn"), 0)
        self.assertEqual(corridor_ci.exit_code(report, mode="fail"), 1)

    def test_cli_defaults_to_warn_mode(self):
        old_input_mode = os.environ.pop("INPUT_MODE", None)
        try:
            code = corridor_ci.main(["--repo", "."])
        finally:
            if old_input_mode is not None:
                os.environ["INPUT_MODE"] = old_input_mode

        self.assertEqual(code, 0)

    def test_cli_reads_pr_body_and_git_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            src = root / "frontend" / "src" / "components" / "ui"
            tests = root / "frontend" / "tests"
            src.mkdir(parents=True)
            tests.mkdir(parents=True)
            (src / "rating.tsx").write_text("old\n", encoding="utf-8")
            (tests / "rating.spec.ts").write_text("old\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "checkout", "-b", "feature"], cwd=root, check=True, capture_output=True, text=True)
            (src / "rating.tsx").write_text("new\n", encoding="utf-8")
            (tests / "rating.spec.ts").write_text("new\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "change rating"], cwd=root, check=True, capture_output=True, text=True)

            event = root / "event.json"
            event.write_text(
                json.dumps({"pull_request": {"body": VALID_HANDOFF}}),
                encoding="utf-8-sig",
            )

            old_event_path = os.environ.get("GITHUB_EVENT_PATH")
            old_base_ref = os.environ.get("GITHUB_BASE_REF")
            os.environ["GITHUB_EVENT_PATH"] = str(event)
            os.environ["GITHUB_BASE_REF"] = "main"
            try:
                code = corridor_ci.main(
                    [
                        "--repo",
                        str(root),
                        "--mode",
                        "fail",
                    ]
                )
            finally:
                if old_event_path is None:
                    os.environ.pop("GITHUB_EVENT_PATH", None)
                else:
                    os.environ["GITHUB_EVENT_PATH"] = old_event_path
                if old_base_ref is None:
                    os.environ.pop("GITHUB_BASE_REF", None)
                else:
                    os.environ["GITHUB_BASE_REF"] = old_base_ref

        self.assertEqual(code, 0)

    def test_action_surface_is_minimal(self):
        repo = Path(__file__).resolve().parents[1]
        action = (repo / "action.yml").read_text(encoding="utf-8")

        self.assertNotIn("profile:", action)
        self.assertNotIn("corridor_required:", action)
        self.assertNotIn("base_ref:", action)
        self.assertNotIn("\n  changed_files:", action)
        self.assertNotIn("INPUT_PROFILE", action)
        self.assertNotIn("INPUT_CORRIDOR_REQUIRED", action)
        self.assertNotIn("INPUT_BASE_REF", action)
        self.assertNotIn("INPUT_CHANGED_FILES", action)

    def test_runner_has_no_removed_branches(self):
        repo = Path(__file__).resolve().parents[1]
        runner = (repo / "bin" / "corridor_ci.py").read_text(encoding="utf-8")

        self.assertNotIn("REVIEW_PACKET", runner)
        self.assertNotIn("extract_review_packet", runner)
        self.assertNotIn("profile", runner)
        self.assertNotIn("corridor_required", runner)
        self.assertNotIn("changed_files_arg", runner)
        self.assertNotIn("--changed-files", runner)
        self.assertNotIn("--base-ref", runner)

    def test_readme_has_no_removed_branches(self):
        repo = Path(__file__).resolve().parents[1]
        readme = (repo / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("Expanded Mode", readme)
        self.assertNotIn("Review Packet", readme)
        self.assertNotIn("profile", readme)
        self.assertNotIn("corridor_required", readme)
        self.assertNotIn("base_ref", readme)
        self.assertNotIn("| `changed_files` |", readme)
        self.assertIn("Add this to the PR body", readme)

    def test_examples_present_compact_handoff_as_only_path(self):
        repo = Path(__file__).resolve().parents[1]
        workflow = (repo / "examples" / "workflow.yml").read_text(encoding="utf-8")

        self.assertIn("shihchengwei-lab/corridor-ci@v7", workflow)
        self.assertNotIn("profile:", workflow)
        self.assertFalse((repo / "examples" / "corridor.md").exists())


if __name__ == "__main__":
    unittest.main()
