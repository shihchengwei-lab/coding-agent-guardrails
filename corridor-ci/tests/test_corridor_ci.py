import json
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
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

    def test_fenced_example_does_not_shadow_real_handoff(self):
        # The PR template seeds a fenced example; first-non-empty-value
        # wins, so without fence-awareness "Scope: auto" in the example
        # would disable the corridor check for the real handoff below.
        body = (
            "```md\n"
            "Decision: #123 or small fix\n"
            "Scope: auto\n"
            "Review first: path/to/file\n"
            "Verified: test command or manual check\n"
            "Risk: none\n"
            "```\n"
            "\n"
            "Decision: #456\n"
            "Scope: src/real.py\n"
            "Review first: src/real.py\n"
            "Verified: pytest\n"
            "Risk: low\n"
        )
        handoff = corridor_ci.extract_compact_handoff(body)
        self.assertEqual(handoff["Scope"], "src/real.py")
        self.assertEqual(handoff["Decision"], "#456")
        self.assertEqual(handoff["Review first"], "src/real.py")

    def test_body_with_only_fenced_example_is_missing_handoff(self):
        body = (
            "Some prose.\n"
            "```\n"
            "Decision: #123\n"
            "Scope: auto\n"
            "```\n"
        )
        handoff = corridor_ci.extract_compact_handoff(body)
        self.assertEqual(handoff["Scope"], "")
        self.assertEqual(handoff["Decision"], "")

    def test_tilde_fence_is_also_skipped(self):
        body = (
            "~~~\n"
            "Scope: auto\n"
            "~~~\n"
            "Scope: src/x.py\n"
        )
        handoff = corridor_ci.extract_compact_handoff(body)
        self.assertEqual(handoff["Scope"], "src/x.py")

    def test_near_miss_detection_ignores_fenced_examples(self):
        body = (
            "```md\n"
            "**Scope**: example\n"
            "```\n"
        )
        self.assertEqual(corridor_ci.detect_near_miss_fields(body), {})

    def test_single_star_does_not_cross_directories(self):
        self.assertTrue(corridor_ci.path_matches("src/app.py", "src/*.py"))
        self.assertFalse(
            corridor_ci.path_matches("src/vendor/evil/deep.py", "src/*.py")
        )
        self.assertFalse(corridor_ci.path_matches("nested/dir/readme.md", "*.md"))
        self.assertFalse(corridor_ci.path_matches("src/a/b.py", "src/?.py"))

    def test_double_star_matches_zero_or_more_directories(self):
        self.assertTrue(corridor_ci.path_matches("src/top.py", "src/**/*.py"))
        self.assertTrue(corridor_ci.path_matches("src/a/b/deep.py", "src/**/*.py"))
        self.assertFalse(corridor_ci.path_matches("other/top.py", "src/**/*.py"))

    def test_trailing_double_star_still_matches_subtree(self):
        self.assertTrue(corridor_ci.path_matches("src", "src/**"))
        self.assertTrue(corridor_ci.path_matches("src/a/b.py", "src/**"))
        self.assertFalse(corridor_ci.path_matches("srcx/a.py", "src/**"))

    def test_scope_fails_when_star_pattern_hides_nested_file(self):
        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
                "frontend/src/components/vendor/injected.tsx",
            ],
            corridor_text=(
                "Decision: #123\n"
                "Scope: frontend/src/components/*.tsx, frontend/src/components/ui/*.tsx, frontend/tests/*.ts\n"
                "Review first: frontend/src/components/ui/rating.tsx\n"
                "Verified: python -m unittest\n"
                "Risk: none\n"
            ),
        )
        self.assertFalse(report.ok)
        self.assertIn(
            "frontend/src/components/vendor/injected.tsx", report.outside_files
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

    def test_alias_labels_are_not_handoff_fields(self):
        handoff = corridor_ci.extract_compact_handoff(
            "Issue: #123\nContext: background\nPaths: a.py\nVerification: pytest"
        )

        self.assertEqual(handoff["Decision"], "")
        self.assertEqual(handoff["Scope"], "")
        self.assertEqual(handoff["Verified"], "")

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
        self.assertIn("Scope: path/or/glob", markdown)

    def test_small_change_without_handoff_can_pass(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text=None,
            small_change_max_files=1,
        )

        self.assertTrue(report.ok)
        self.assertIn("small change fast path", "\n".join(report.warnings))

    def test_small_change_with_plain_prose_body_can_pass(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text="Fix typo in docs.",
            small_change_max_files=1,
        )

        self.assertTrue(report.ok)
        self.assertIn("small change fast path", "\n".join(report.warnings))

    def test_small_change_with_context_heading_body_can_pass(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text="## Context\nJust fixing a typo.",
            small_change_max_files=1,
        )

        self.assertTrue(report.ok)
        self.assertIn("small change fast path", "\n".join(report.warnings))

    def test_partial_handoff_does_not_use_small_change_fast_path(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text="Risk: low",
            small_change_max_files=1,
        )

        self.assertFalse(report.ok)
        self.assertNotIn("small change fast path", "\n".join(report.warnings))
        self.assertIn("compact handoff is missing `Decision`", "\n".join(report.issues))
        self.assertIn("compact handoff is missing `Scope`", "\n".join(report.issues))
        self.assertIn("compact handoff is missing `Review first`", "\n".join(report.issues))
        self.assertIn("compact handoff is missing `Verified`", "\n".join(report.issues))

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

    def test_prose_without_fast_path_reports_no_handoff_fields(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md", "docs/setup.md"],
            corridor_text="Fix typo in docs.",
            small_change_max_files=1,
        )

        self.assertFalse(report.ok)
        self.assertIn(
            "compact handoff is required, but no handoff fields were found",
            "\n".join(report.issues),
        )

    def test_bold_handoff_field_gets_format_hint(self):
        handoff = VALID_HANDOFF.replace("Decision: #123", "**Decision:** #123")

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertFalse(report.ok)
        self.assertIn(
            "compact handoff is missing `Decision` (found `**Decision:**` - fields must be plain `Decision: value` lines, no bold, bullets, or headings)",
            "\n".join(report.issues),
        )

    def test_bullet_handoff_field_gets_format_hint(self):
        handoff = VALID_HANDOFF.replace("Decision: #123", "- Decision: #123")

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertFalse(report.ok)
        self.assertIn(
            "compact handoff is missing `Decision` (found `- Decision:` - fields must be plain `Decision: value` lines, no bold, bullets, or headings)",
            "\n".join(report.issues),
        )

    def test_heading_handoff_field_gets_format_hint(self):
        handoff = VALID_HANDOFF.replace("Decision: #123", "### Decision")

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertFalse(report.ok)
        self.assertIn(
            "compact handoff is missing `Decision` (found `### Decision` - fields must be plain `Decision: value` lines, no bold, bullets, or headings)",
            "\n".join(report.issues),
        )

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

    def test_scope_matching_everything_warns_without_blocking(self):
        handoff = VALID_HANDOFF.replace(
            "Scope: frontend/src/components/ui/rating.tsx, frontend/tests/rating.spec.ts",
            "Scope: **/*",
        )

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertTrue(report.ok)
        self.assertIn("carries no information", "\n".join(report.warnings))

    def test_decision_without_reference_warns_without_blocking(self):
        handoff = VALID_HANDOFF.replace("Decision: #123", "Decision: small fix")

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertTrue(report.ok)
        self.assertIn("does not point to an issue/discussion/URL", "\n".join(report.warnings))

    def test_verbose_body_warns_without_blocking(self):
        handoff = VALID_HANDOFF + "\n".join(f"note {index}" for index in range(56))

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertTrue(report.ok)
        self.assertIn("61 lines", "\n".join(report.warnings))
        self.assertIn("compact handoff", "\n".join(report.warnings))

    def test_warn_mode_does_not_fail_process(self):
        report = corridor_ci.evaluate(
            changed_files=["frontend/src/routes/admin.tsx"],
            corridor_text=VALID_HANDOFF,
        )

        self.assertEqual(corridor_ci.exit_code(report, mode="warn"), 0)
        self.assertEqual(corridor_ci.exit_code(report, mode="fail"), 1)

    def test_cli_defaults_to_warn_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "README.md").write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True, text=True)

            old_input_mode = os.environ.pop("INPUT_MODE", None)
            old_base_ref = os.environ.pop("GITHUB_BASE_REF", None)
            try:
                code = corridor_ci.main(["--repo", str(root)])
            finally:
                if old_input_mode is not None:
                    os.environ["INPUT_MODE"] = old_input_mode
                if old_base_ref is not None:
                    os.environ["GITHUB_BASE_REF"] = old_base_ref

        self.assertEqual(code, 0)

    def test_parser_default_max_changed_files_is_12_when_unset(self):
        old_max_changed_files = os.environ.pop("INPUT_MAX_CHANGED_FILES", None)
        try:
            args = corridor_ci.build_parser().parse_args([])
        finally:
            if old_max_changed_files is not None:
                os.environ["INPUT_MAX_CHANGED_FILES"] = old_max_changed_files

        self.assertEqual(args.max_changed_files, 12)

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

    def test_upsert_pr_comment_creates_when_marker_is_absent(self):
        calls = []

        def fake_transport(method, url, token, payload=None):
            calls.append((method, url, token, payload))
            if method == "GET":
                return [{"id": 1, "body": "older comment"}]
            return {"id": 2}

        corridor_ci.upsert_pr_comment(
            "# Corridor CI: PASS\n",
            token="token",
            repository="owner/repo",
            pr_number=7,
            transport=fake_transport,
        )

        self.assertEqual(calls[0][0], "GET")
        self.assertIn("/repos/owner/repo/issues/7/comments?per_page=100", calls[0][1])
        self.assertEqual(calls[1][0], "POST")
        self.assertIn("/repos/owner/repo/issues/7/comments", calls[1][1])
        self.assertEqual(calls[1][3]["body"].splitlines()[0], "<!-- corridor-ci -->")

    def test_upsert_pr_comment_updates_when_marker_is_present(self):
        calls = []

        def fake_transport(method, url, token, payload=None):
            calls.append((method, url, token, payload))
            if method == "GET":
                return [{"id": 42, "body": "old\n<!-- corridor-ci -->\nbody"}]
            return {"id": 42}

        corridor_ci.upsert_pr_comment(
            "# Corridor CI: PASS\n",
            token="token",
            repository="owner/repo",
            pr_number=7,
            transport=fake_transport,
        )

        self.assertEqual([call[0] for call in calls], ["GET", "PATCH"])
        self.assertIn("/repos/owner/repo/issues/comments/42", calls[1][1])
        self.assertEqual(calls[1][3]["body"].splitlines()[0], "<!-- corridor-ci -->")

    def test_upsert_pr_comment_skips_without_token(self):
        calls = []

        def fake_transport(method, url, token, payload=None):
            calls.append((method, url, token, payload))
            return []

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            corridor_ci.upsert_pr_comment(
                "# Corridor CI: PASS\n",
                token="",
                repository="owner/repo",
                pr_number=7,
                transport=fake_transport,
            )

        self.assertEqual(calls, [])
        self.assertIn("missing GITHUB_TOKEN", out.getvalue())

    def test_upsert_pr_comment_swallows_http_errors(self):
        def fake_transport(method, url, token, payload=None):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            corridor_ci.upsert_pr_comment(
                "# Corridor CI: PASS\n",
                token="token",
                repository="owner/repo",
                pr_number=7,
                transport=fake_transport,
            )

        self.assertIn("PR comment skipped", out.getvalue())

    def test_upsert_pr_comment_finds_marker_beyond_first_page(self):
        calls = []

        def fake_transport(method, url, token, payload=None):
            calls.append((method, url, token, payload))
            if method == "GET":
                if url.endswith("&page=1"):
                    return [{"id": index, "body": f"noise {index}"} for index in range(100)]
                return [{"id": 200, "body": "<!-- corridor-ci -->\nold report"}]
            return {"id": 200}

        corridor_ci.upsert_pr_comment(
            "# Corridor CI: PASS\n",
            token="token",
            repository="owner/repo",
            pr_number=7,
            transport=fake_transport,
        )

        self.assertEqual([call[0] for call in calls], ["GET", "GET", "PATCH"])
        self.assertIn("&page=1", calls[0][1])
        self.assertIn("&page=2", calls[1][1])
        self.assertIn("/repos/owner/repo/issues/comments/200", calls[2][1])

    def test_upsert_pr_comment_creates_after_paging_all_comments(self):
        calls = []

        def fake_transport(method, url, token, payload=None):
            calls.append((method, url, token, payload))
            if method == "GET":
                if url.endswith("&page=1"):
                    return [{"id": index, "body": f"noise {index}"} for index in range(100)]
                return [{"id": 100, "body": "noise 100"}]
            return {"id": 101}

        corridor_ci.upsert_pr_comment(
            "# Corridor CI: PASS\n",
            token="token",
            repository="owner/repo",
            pr_number=7,
            transport=fake_transport,
        )

        self.assertEqual([call[0] for call in calls], ["GET", "GET", "POST"])

    def test_action_comment_input_is_wired(self):
        repo = Path(__file__).resolve().parents[1]
        action = (repo / "action.yml").read_text(encoding="utf-8")

        self.assertIn("\n  comment:", action)
        self.assertIn("INPUT_COMMENT: ${{ inputs.comment }}", action)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", action)

    def test_pull_request_body_edits_rerun_corridor(self):
        repo = Path(__file__).resolve().parents[1]
        monorepo_root = repo.parent  # dogfood workflow lives at the monorepo root
        expected = "on:\n  pull_request:\n    types: [opened, edited, synchronize, reopened]"

        self.assertIn(expected, (monorepo_root / ".github" / "workflows" / "corridor.yml").read_text(encoding="utf-8"))
        self.assertIn(expected, (repo / "examples" / "workflow.yml").read_text(encoding="utf-8"))
        self.assertIn(expected, (repo / "README.md").read_text(encoding="utf-8"))

    def test_dogfood_workflow_writes_sticky_comment(self):
        monorepo_root = Path(__file__).resolve().parents[2]  # dogfood workflow lives at the monorepo root
        workflow = (monorepo_root / ".github" / "workflows" / "corridor.yml").read_text(encoding="utf-8")

        self.assertIn("contents: read", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertIn("comment: true", workflow)

    def test_example_pr_template_contains_copyable_handoff(self):
        repo = Path(__file__).resolve().parents[1]
        template = (repo / "examples" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

        self.assertIn("Copy this file to .github/PULL_REQUEST_TEMPLATE.md", template)
        self.assertIn(corridor_ci.COPYABLE_REVIEW_HANDOFF, template)

    def test_readme_and_example_share_action_tag(self):
        repo = Path(__file__).resolve().parents[1]
        readme = (repo / "README.md").read_text(encoding="utf-8")
        workflow = (repo / "examples" / "workflow.yml").read_text(encoding="utf-8")
        readme_tag = re.search(r"corridor-ci@(corridor-ci-v\d+)", readme)
        workflow_tag = re.search(r"corridor-ci@(corridor-ci-v\d+)", workflow)

        self.assertIsNotNone(readme_tag)
        self.assertIsNotNone(workflow_tag)
        self.assertEqual(readme_tag.group(1), workflow_tag.group(1))

    # -- agentcam recorded evidence (display-only) --------------------

    @staticmethod
    def _sample_evidence_manifest() -> dict:
        return {
            "schema_version": "0.1",
            "evidence": {
                "changed_files": [
                    {
                        "path": "frontend/src/components/ui/rating.tsx",
                        "status": "unstaged_modified",
                        "secret_like_name": False,
                    }
                ],
                "risk_flags": [
                    {
                        "level": "HIGH",
                        "rule": "auth path",
                        "evidence": "frontend/src/components/ui/rating.tsx",
                    }
                ],
                "overall_risk": "HIGH",
                "diff_stat": " 1 file changed, 1 insertion(+)",
                "diff_stat_cached": "",
                "verifications": [
                    {
                        "command": "pytest -q",
                        "exit_code": 0,
                        "duration_seconds": 2.3,
                        "recorded_at": "2026-07-05T12:00:00+00:00",
                    }
                ],
            },
        }

    def test_read_agentcam_evidence_missing_file_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence, note = corridor_ci.read_agentcam_evidence(
                Path(tmp) / "nope" / "manifest.redacted.json"
            )
        self.assertIsNone(evidence)
        self.assertIsNone(note)

    def test_read_agentcam_evidence_malformed_yields_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.redacted.json"
            path.write_text("{not json", encoding="utf-8")
            evidence, note = corridor_ci.read_agentcam_evidence(path)
        self.assertIsNone(evidence)
        self.assertIn("could not be read", note)

    def test_read_agentcam_evidence_without_evidence_key_yields_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.redacted.json"
            path.write_text(
                json.dumps({"schema_version": "0.1"}), encoding="utf-8"
            )
            evidence, note = corridor_ci.read_agentcam_evidence(path)
        self.assertIsNone(evidence)
        self.assertIn("no evidence section", note)

    def test_render_markdown_includes_recorded_evidence(self):
        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=VALID_HANDOFF,
            allow_dependencies=False,
            max_changed_files=12,
            small_change_max_files=0,
        )
        evidence = self._sample_evidence_manifest()["evidence"]
        with_evidence = corridor_ci.render_markdown(
            report, agentcam_evidence=evidence
        )
        self.assertIn("## Recorded Evidence (agentcam)", with_evidence)
        self.assertIn("overall risk: HIGH", with_evidence)
        self.assertIn("HIGH | auth path", with_evidence)
        self.assertIn(
            "recorded check: `pytest -q` | exit 0 (2.3s)", with_evidence
        )
        without = corridor_ci.render_markdown(report)
        self.assertNotIn("Recorded Evidence", without)
        with_note = corridor_ci.render_markdown(
            report, agentcam_note="agentcam manifest could not be read"
        )
        self.assertIn("could not be read", with_note)

    def test_render_evidence_tolerates_malformed_verifications(self):
        evidence = self._sample_evidence_manifest()["evidence"]
        evidence["verifications"] = [
            "not-a-dict",
            {"command": "ruff check ."},
        ]
        rendered = "\n".join(
            corridor_ci.render_agentcam_section(evidence, None)
        )
        self.assertIn("recorded check: `ruff check .` | exit ?", rendered)
        self.assertNotIn("not-a-dict", rendered)

    def test_render_evidence_never_raises_on_adversarial_shapes(self):
        # Committed manifests are author-controlled; display-only means
        # no shape may crash the renderer before the verdict is set.
        evidence = self._sample_evidence_manifest()["evidence"]
        evidence["risk_flags"] = ["not-a-dict", {"level": "HIGH"}]
        evidence["verifications"] = 42
        evidence["changed_files"] = "abc"
        evidence["diff_stat"] = ["not", "a", "string"]
        rendered = "\n".join(
            corridor_ci.render_agentcam_section(evidence, None)
        )
        self.assertIn("HIGH | ? | ``", rendered)
        self.assertNotIn("not-a-dict", rendered)
        self.assertNotIn("recorded changed files", rendered)
        self.assertNotIn("```", rendered)

    def test_cli_appends_evidence_section_without_affecting_verdict(self):
        import contextlib
        import io

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

            evidence_dir = root / ".agentcam"
            evidence_dir.mkdir()
            (evidence_dir / "manifest.redacted.json").write_text(
                json.dumps(self._sample_evidence_manifest()),
                encoding="utf-8",
            )

            event = root / "event.json"
            event.write_text(
                json.dumps({"pull_request": {"body": VALID_HANDOFF}}),
                encoding="utf-8-sig",
            )

            old_event_path = os.environ.get("GITHUB_EVENT_PATH")
            old_base_ref = os.environ.get("GITHUB_BASE_REF")
            os.environ["GITHUB_EVENT_PATH"] = str(event)
            os.environ["GITHUB_BASE_REF"] = "main"
            stdout = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout):
                    code = corridor_ci.main(["--repo", str(root), "--mode", "fail"])
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
        output = stdout.getvalue()
        self.assertIn("# Corridor CI: PASS", output)
        self.assertIn("## Recorded Evidence (agentcam)", output)
        self.assertIn("overall risk: HIGH", output)


if __name__ == "__main__":
    unittest.main()
