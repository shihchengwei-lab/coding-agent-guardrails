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
Risk: none-detected
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
        # wins, so fenced fields must never shadow the real handoff below.
        body = (
            "```md\n"
            "Decision: <fill in: issue, discussion, or short decision>\n"
            "Scope: <fill in: repo-relative path or glob>\n"
            "Review first: <fill in: changed file>\n"
            "Verified: <fill in: completed command or manual check>\n"
            "Risk: <fill in: high, medium, none-detected, or unknown>\n"
            "```\n"
            "\n"
            "Decision: #456\n"
            "Scope: src/real.py\n"
            "Review first: src/real.py\n"
            "Verified: pytest\n"
            "Risk: none-detected\n"
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
            "Scope: <fill in: repo-relative path or glob>\n"
            "```\n"
        )
        handoff = corridor_ci.extract_compact_handoff(body)
        self.assertEqual(handoff["Scope"], "")
        self.assertEqual(handoff["Decision"], "")

    def test_tilde_fence_is_also_skipped(self):
        body = (
            "~~~\n"
            "Scope: <fill in: repo-relative path or glob>\n"
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
        self.assertIn("Scope: <fill in: repo-relative path or glob>", markdown)

    def test_small_change_without_handoff_still_fails(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text=None,
        )

        self.assertFalse(report.ok)
        self.assertIn("compact handoff is required", "\n".join(report.issues))

    def test_small_change_with_plain_prose_body_still_fails(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text="Fix typo in docs.",
        )

        self.assertFalse(report.ok)
        self.assertIn("no handoff fields were found", "\n".join(report.issues))

    def test_small_change_with_context_heading_body_still_fails(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text="## Context\nJust fixing a typo.",
        )

        self.assertFalse(report.ok)
        self.assertIn("no handoff fields were found", "\n".join(report.issues))

    def test_partial_handoff_requires_every_field(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md"],
            corridor_text="Risk: none-detected",
        )

        self.assertFalse(report.ok)
        self.assertIn("compact handoff is missing `Decision`", "\n".join(report.issues))
        self.assertIn("compact handoff is missing `Scope`", "\n".join(report.issues))
        self.assertIn("compact handoff is missing `Review first`", "\n".join(report.issues))
        self.assertIn("compact handoff is missing `Verified`", "\n".join(report.issues))

    def test_fill_in_placeholders_do_not_complete_required_fields(self):
        base = (
            "Decision: #123\n"
            "Scope: src/a.py\n"
            "Review first: src/a.py\n"
            "Verified: manual check passed\n"
            "Risk: none-detected\n"
        )
        for label, placeholder in (
            ("Decision", "<fill in>"),
            ("Risk", "<fill in>"),
            ("Decision", "n/a"),
            ("Risk", "tbd"),
        ):
            body = re.sub(
                rf"(?m)^{label}: .+$",
                f"{label}: {placeholder}",
                base,
            )
            with self.subTest(label=label, placeholder=placeholder):
                report = corridor_ci.evaluate(
                    changed_files=["src/a.py"],
                    corridor_text=body,
                )
                self.assertFalse(report.ok)
                self.assertIn("placeholder", "\n".join(report.issues))

    def test_missing_handoff_and_dependency_change_both_fail(self):
        report = corridor_ci.evaluate(
            changed_files=["package.json"],
            corridor_text=None,
        )

        self.assertFalse(report.ok)
        self.assertIn("compact handoff is required", "\n".join(report.issues))
        self.assertIn("head-bound trusted approval", "\n".join(report.issues))

    def test_missing_handoff_fails_for_multiple_files(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md", "docs/setup.md"],
            corridor_text=None,
        )

        self.assertFalse(report.ok)
        self.assertIn("compact handoff is required", "\n".join(report.issues))

    def test_prose_without_handoff_fields_reports_missing_handoff(self):
        report = corridor_ci.evaluate(
            changed_files=["README.md", "docs/setup.md"],
            corridor_text="Fix typo in docs.",
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

    def test_review_first_accepts_backticked_path(self):
        handoff = VALID_HANDOFF.replace(
            "Review first: frontend/src/components/ui/rating.tsx",
            "Review first: `frontend/src/components/ui/rating.tsx`",
        )

        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=handoff,
        )

        self.assertTrue(report.ok, report.issues)

    def test_changed_files_keep_non_ascii_names_unquoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            src = root / "src"
            src.mkdir()
            (src / "base.py").write_text("old\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(["git", "checkout", "-b", "feature"], cwd=root, check=True, capture_output=True, text=True)
            (src / "café.py").write_text("new\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "add cafe file"], cwd=root, check=True, capture_output=True, text=True)

            old_base_ref = os.environ.get("GITHUB_BASE_REF")
            os.environ["GITHUB_BASE_REF"] = "main"
            try:
                changed = corridor_ci.extract_changed_files(root)
            finally:
                if old_base_ref is None:
                    os.environ.pop("GITHUB_BASE_REF", None)
                else:
                    os.environ["GITHUB_BASE_REF"] = old_base_ref

        # git's default core.quotepath would report "src/caf\303\251.py",
        # which can never match a Scope pattern like src/*.py.
        self.assertEqual(changed, ["src/café.py"])
        report = corridor_ci.evaluate(
            changed_files=changed,
            corridor_text=(
                "Decision: #1\n"
                "Scope: src/*.py\n"
                "Review first: src/café.py\n"
                "Verified: manual filename check passed\n"
                "Risk: none\n"
            ),
        )
        self.assertTrue(report.ok, report.issues)

    def test_scope_auto_is_rejected_because_it_declares_no_boundary(self):
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

        self.assertFalse(report.ok)
        self.assertEqual(report.allowed_paths, [])
        self.assertIn("Scope must declare explicit paths", "\n".join(report.issues))

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
        )

        self.assertFalse(report.ok)
        self.assertIn("head-bound trusted approval", "\n".join(report.issues))

    def test_scope_matching_everything_is_rejected(self):
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

        self.assertFalse(report.ok)
        self.assertIn("carries no information", "\n".join(report.issues))

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

    def test_cli_defaults_to_fail_mode(self):
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

        self.assertEqual(code, 1)

    def test_parser_does_not_expose_file_count_escape_hatches(self):
        parser = corridor_ci.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--max-changed-files", "12"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["--small-change-max-files", "1"])

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
                return [{
                    "id": 42,
                    "body": "old\n<!-- corridor-ci -->\nbody",
                    "user": {"login": "github-actions[bot]"},
                }]
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
                return [{
                    "id": 200,
                    "body": "<!-- corridor-ci -->\nold report",
                    "user": {"login": "github-actions[bot]"},
                }]
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

    def test_upsert_pr_comment_never_edits_author_marker(self):
        calls = []

        def fake_transport(method, url, token, payload=None):
            calls.append((method, url, token, payload))
            if method == "GET":
                return [{
                    "id": 9,
                    "body": "<!-- corridor-ci -->\nspoofed",
                    "user": {"login": "pull-request-author"},
                }]
            return {"id": 10}

        corridor_ci.upsert_pr_comment(
            "# Corridor CI: PASS\n", token="token", repository="owner/repo",
            pr_number=7, transport=fake_transport,
        )

        self.assertEqual([call[0] for call in calls], ["GET", "POST"])

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
        self.assertNotIn("allow_dependencies", action)

    def test_readme_has_no_dependency_bypass_input(self):
        repo = Path(__file__).resolve().parents[1]
        readme = (repo / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("allow_dependencies", readme)
        self.assertIn("Guardrails-Dependency-Approval", readme)

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

    def test_dogfood_workflow_pins_published_v13_checker(self):
        monorepo_root = Path(__file__).resolve().parents[2]
        workflow = (monorepo_root / ".github" / "workflows" / "corridor.yml").read_text(encoding="utf-8")

        self.assertIn(
            "coding-agent-guardrails/corridor-ci@corridor-ci-v13.0.0",
            workflow,
        )
        self.assertNotIn("coding-agent-guardrails/corridor-ci@corridor-ci-v12", workflow)
        self.assertNotIn("uses: ./corridor-ci", workflow)

    def test_example_pr_template_contains_copyable_handoff(self):
        repo = Path(__file__).resolve().parents[1]
        template = (repo / "examples" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

        self.assertIn("Copy this file to .github/PULL_REQUEST_TEMPLATE.md", template)
        self.assertIn(corridor_ci.COPYABLE_REVIEW_HANDOFF, template)

    def test_readme_and_example_share_action_tag(self):
        repo = Path(__file__).resolve().parents[1]
        readme = (repo / "README.md").read_text(encoding="utf-8")
        workflow = (repo / "examples" / "workflow.yml").read_text(encoding="utf-8")
        readme_tag = re.search(r"corridor-ci@(corridor-ci-v\d+\.\d+\.\d+)", readme)
        workflow_tag = re.search(r"corridor-ci@(corridor-ci-v\d+\.\d+\.\d+)", workflow)

        self.assertIsNotNone(readme_tag)
        self.assertIsNotNone(workflow_tag)
        self.assertEqual(readme_tag.group(1), workflow_tag.group(1))
        self.assertEqual(readme_tag.group(1), "corridor-ci-v13.0.0")

    # -- base-branch policy gate --------------------------------------

    def test_policy_gate_allows_pr_without_workflow_changes(self):
        decision = corridor_ci.evaluate_workflow_policy(
            changed_files=["src/app.py"],
            comments=[],
            head_sha="a" * 40,
            pr_author="author",
        )

        self.assertTrue(decision.ok)
        self.assertEqual(decision.changed_workflows, [])

    def test_policy_gate_blocks_workflow_change_without_external_approval(self):
        decision = corridor_ci.evaluate_workflow_policy(
            changed_files=[".github/workflows/agentcam.yml"],
            comments=[],
            head_sha="b" * 40,
            pr_author="author",
        )

        self.assertFalse(decision.ok)
        self.assertIn("Guardrails-Workflow-Approval", decision.reason)

    def test_policy_gate_owner_approval_is_bound_to_exact_head(self):
        head = "c" * 40
        decision = corridor_ci.evaluate_workflow_policy(
            changed_files=[".github/workflows/toolkit.yml"],
            comments=[
                {
                    "body": f"Guardrails-Workflow-Approval: {head}",
                    "author_association": "OWNER",
                    "user": {"login": "author"},
                }
            ],
            head_sha=head,
            pr_author="author",
        )

        self.assertTrue(decision.ok)
        self.assertEqual(decision.approved_by, "author")

    def test_policy_gate_rejects_stale_or_author_member_approval(self):
        head = "d" * 40
        comments = [
            {
                "body": f"Guardrails-Workflow-Approval: {'e' * 40}",
                "author_association": "OWNER",
                "user": {"login": "owner"},
            },
            {
                "body": f"Guardrails-Workflow-Approval: {head}",
                "author_association": "MEMBER",
                "user": {"login": "author"},
            },
        ]

        decision = corridor_ci.evaluate_workflow_policy(
            changed_files=[".github/workflows/corridor.yml"],
            comments=comments,
            head_sha=head,
            pr_author="author",
        )

        self.assertFalse(decision.ok)

    def test_policy_gate_accepts_non_author_member_approval(self):
        head = "f" * 40
        decision = corridor_ci.evaluate_workflow_policy(
            changed_files=[".github/workflows/corridor.yml"],
            comments=[
                {
                    "body": f"Guardrails-Workflow-Approval: {head}",
                    "author_association": "MEMBER",
                    "user": {"login": "maintainer"},
                }
            ],
            head_sha=head,
            pr_author="author",
        )

        self.assertTrue(decision.ok)
        self.assertEqual(decision.approved_by, "maintainer")

    def test_ci_bootstrap_contracts(self):
        root = Path(__file__).resolve().parents[2]
        workflows = root / ".github" / "workflows"
        policy = (workflows / "policy-gate.yml").read_text(encoding="utf-8")

        self.assertIn("pull_request_target:", policy)
        self.assertIn("name: Policy Gate", policy)
        self.assertIn("contents: read", policy)
        self.assertIn("pull-requests: read", policy)
        self.assertNotIn("pull-requests: write", policy)
        self.assertIn("--policy-gate", policy)

        pr_workflows = (
            "agentcam.yml",
            "corridor.yml",
            "corridor-ci.yml",
            "kiss.yml",
            "slime-coding.yml",
            "toolkit.yml",
            "policy-gate.yml",
        )
        for name in pr_workflows:
            text = (workflows / name).read_text(encoding="utf-8")
            self.assertIn("concurrency:", text, name)
            self.assertIn("cancel-in-progress: true", text, name)

        self.assertIn(
            "name: Agentcam tests",
            (workflows / "agentcam.yml").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "working-directory: .",
            (workflows / "agentcam.yml").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "name: Slime tests",
            (workflows / "slime-coding.yml").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "working-directory: .",
            (workflows / "slime-coding.yml").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "name: Toolkit tests",
            (workflows / "toolkit.yml").read_text(encoding="utf-8"),
        )

    # -- agentcam verification evidence -------------------------------

    @staticmethod
    def _sample_evidence_manifest() -> dict:
        return {
            "schema_version": "0.1",
            "final_state_fingerprint": "state-bound",
            "capture": {
                "mode": "wrap_pipe",
                "stdout": "captured",
                "stderr": "captured",
                "output_risk_scan": "enabled",
            },
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
                "product_fingerprint": "a" * 64,
                "verifications": [
                    {
                        "record_id": "record-1",
                        "command": "pytest -q",
                        "exit_code": 0,
                        "state_fingerprint": "state-bound",
                        "duration_seconds": 2.3,
                        "recorded_at": "2026-07-05T12:00:00+00:00",
                    }
                ],
            },
        }

    def test_product_fingerprint_must_match_current_pr(self):
        manifest = self._sample_evidence_manifest()
        stale = corridor_ci.classify_verification_provenance(
            "pytest -q (exit 0) [locally recorded by agentcam]",
            manifest,
            current_product_fingerprint="b" * 64,
        )

        self.assertEqual(stale.status, "unverified")
        self.assertIn("stale", "\n".join(stale.warnings).lower())

    def test_recorded_grammar_is_exact_and_exit_zero_is_integer(self):
        for verified, exit_code in (
            ("pytest -q (exit 0) [locally recorded by agentcam] trailing", 0),
            ("pytest -q (exit 0) [locally recorded by agentcam]", False),
            ("pytest -q (exit 00) [locally recorded by agentcam]", 0),
        ):
            with self.subTest(verified=verified, exit_code=exit_code):
                manifest = self._sample_evidence_manifest()
                manifest["evidence"]["verifications"][0]["exit_code"] = exit_code
                assessment = corridor_ci.classify_verification_provenance(
                    verified,
                    manifest,
                    current_product_fingerprint="a" * 64,
                )
                self.assertEqual(assessment.status, "unverified")

    def test_legacy_recorded_marker_is_rejected(self):
        assessment = corridor_ci.classify_verification_provenance(
            "pytest -q (exit 0) [recorded by agentcam]",
            self._sample_evidence_manifest(),
            current_product_fingerprint="a" * 64,
        )

        self.assertEqual(assessment.status, "unverified")

    def test_legacy_recorded_marker_parser_is_pruned(self):
        source = Path(corridor_ci.__file__).read_text(encoding="utf-8")
        self.assertNotIn("LEGACY_RECORDED_MARKER", source)
        self.assertNotIn("legacy_marker_present", source)

    def test_risk_enum_and_manifest_floor_are_enforced(self):
        invalid = corridor_ci.apply_manifest_policy(
            corridor_ci.evaluate(
                changed_files=["frontend/src/components/ui/rating.tsx"],
                corridor_text=VALID_HANDOFF.replace(
                    "Scope: frontend/src/components/ui/rating.tsx, frontend/tests/rating.spec.ts",
                    "Scope: frontend/src/components/ui/rating.tsx",
                ).replace("Risk: none-detected", "Risk: low"),
            ),
            self._sample_evidence_manifest(),
        )
        underreported = corridor_ci.apply_manifest_policy(
            corridor_ci.evaluate(
                changed_files=["frontend/src/components/ui/rating.tsx"],
                corridor_text=VALID_HANDOFF.replace(
                    "Scope: frontend/src/components/ui/rating.tsx, frontend/tests/rating.spec.ts",
                    "Scope: frontend/src/components/ui/rating.tsx",
                ).replace("Risk: none-detected", "Risk: medium"),
            ),
            self._sample_evidence_manifest(),
        )

        self.assertFalse(invalid.ok)
        self.assertIn("Risk must be one of", "\n".join(invalid.issues))
        self.assertFalse(underreported.ok)
        self.assertIn("underreports", "\n".join(underreported.issues))

    def test_fixed_agentcam_files_are_metadata_not_scope_escape(self):
        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                ".agentcam/AGENT_RUN_REPORT.md",
                ".agentcam/manifest.redacted.json",
            ],
            corridor_text=VALID_HANDOFF.replace(
                "Scope: frontend/src/components/ui/rating.tsx, frontend/tests/rating.spec.ts",
                "Scope: frontend/src/components/ui/rating.tsx",
            ).replace(
                "Review first: frontend/src/components/ui/rating.tsx",
                "Review first: frontend/src/components/ui/rating.tsx",
            ),
        )

        self.assertTrue(report.ok)
        self.assertEqual(len(report.changed_files), 3)
        self.assertEqual(report.outside_files, [])

    def test_dependency_approval_is_external_and_head_bound(self):
        head = "c" * 40
        comments = [{
            "body": f"Guardrails-Dependency-Approval: {head}",
            "author_association": "OWNER",
            "user": {"login": "owner"},
        }]
        approved = corridor_ci.evaluate_dependency_policy(
            dependency_files=["pyproject.toml"], comments=comments,
            head_sha=head, pr_author="owner",
        )
        stale = corridor_ci.evaluate_dependency_policy(
            dependency_files=["pyproject.toml"], comments=comments,
            head_sha="d" * 40, pr_author="owner",
        )

        self.assertTrue(approved.ok)
        self.assertFalse(stale.ok)

    def test_manifest_size_limit_and_markdown_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.redacted.json"
            path.write_bytes(b" " * (1024 * 1024 + 1))
            manifest, note = corridor_ci.read_agentcam_manifest(path)

        self.assertIsNone(manifest)
        self.assertIn("1 MiB", note)
        escaped = corridor_ci.escape_markdown("x\n# injected\n```\n@team")
        self.assertNotIn("\n# injected", escaped)
        self.assertNotIn("```", escaped)

    def test_agentcam_render_escapes_manifest_markdown(self):
        evidence = self._sample_evidence_manifest()["evidence"]
        evidence["risk_flags"] = [{
            "level": "HIGH\n# injected",
            "rule": "```md\n@team",
            "evidence": "x`\n## forged",
        }]

        rendered = "\n".join(corridor_ci.render_agentcam_section(evidence, None))

        self.assertNotIn("\n# injected", rendered)
        self.assertNotIn("\n## forged", rendered)
        self.assertNotIn("```md", rendered)
        self.assertNotIn("\n@team", rendered)

    def test_read_agentcam_manifest_preserves_capture_and_evidence(self):
        sample = self._sample_evidence_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.redacted.json"
            path.write_text(json.dumps(sample), encoding="utf-8")
            manifest, note = corridor_ci.read_agentcam_manifest(path)

        self.assertIsNone(note)
        self.assertEqual(manifest["capture"]["mode"], "wrap_pipe")
        self.assertEqual(manifest["evidence"], sample["evidence"])

    def test_verification_provenance_local_recorded_requires_matching_pass(self):
        assessment = corridor_ci.classify_verification_provenance(
            "pytest -q (exit 0) [locally recorded by agentcam]",
            self._sample_evidence_manifest(),
            current_product_fingerprint="a" * 64,
        )

        self.assertEqual(assessment.status, "local-recorded")
        self.assertFalse(assessment.partial)
        self.assertEqual(assessment.warnings, [])

    def test_legacy_recorded_marker_compatibility_is_removed(self):
        assessment = corridor_ci.classify_verification_provenance(
            "pytest -q (exit 0) [recorded by agentcam]",
            self._sample_evidence_manifest(),
            current_product_fingerprint="a" * 64,
        )

        self.assertEqual(assessment.status, "unverified")

    def test_verification_provenance_manual_without_matching_record(self):
        assessment = corridor_ci.classify_verification_provenance(
            "python -m unittest",
            self._sample_evidence_manifest(),
        )

        self.assertEqual(assessment.status, "manual")
        self.assertIn("does not match", "\n".join(assessment.warnings))

    def test_verification_provenance_unverified_placeholders_and_fake_marker(self):
        for value in (
            "<fill in: agentcam did not observe a test run>",
            "n/a",
            "none",
            "none - documentation only",
            "not run",
            "not run: environment unavailable",
            "unverified",
            "unverified pending CI",
            "ruff check . (exit 0) [recorded by agentcam]",
        ):
            with self.subTest(value=value):
                assessment = corridor_ci.classify_verification_provenance(
                    value,
                    self._sample_evidence_manifest(),
                )
                self.assertEqual(assessment.status, "unverified")
                self.assertTrue(assessment.warnings)

    def test_verification_provenance_marks_hook_and_legacy_capture_partial(self):
        hook = self._sample_evidence_manifest()
        hook["capture"] = {
            "mode": "claude_hook",
            "stdout": "not_available",
            "output_risk_scan": "disabled_no_output_stream",
        }
        hook_assessment = corridor_ci.classify_verification_provenance(
            "pytest -q (exit 0) [recorded by agentcam]", hook
        )
        legacy = self._sample_evidence_manifest()
        legacy.pop("capture")
        legacy_assessment = corridor_ci.classify_verification_provenance(
            "pytest -q (exit 0) [recorded by agentcam]", legacy
        )

        self.assertTrue(hook_assessment.partial)
        self.assertTrue(legacy_assessment.partial)
        self.assertIn("partial", "\n".join(hook_assessment.warnings))

    def test_verification_provenance_tolerates_adversarial_manifest(self):
        assessment = corridor_ci.classify_verification_provenance(
            "manual browser check",
            {"capture": ["bad"], "evidence": {"verifications": 42}},
        )

        self.assertEqual(assessment.status, "manual")
        self.assertTrue(assessment.partial)

    def test_manual_verification_remains_valid_but_visible(self):
        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=VALID_HANDOFF,
        )
        assessment = corridor_ci.classify_verification_provenance(
            report.handoff["Verified"], None
        )
        enforced = corridor_ci.apply_verification_policy(report, assessment)
        rendered = corridor_ci.render_markdown(
            enforced, verification_provenance=assessment
        )

        self.assertTrue(enforced.ok)
        self.assertEqual(corridor_ci.exit_code(enforced, mode="fail"), 0)
        self.assertIn("# Corridor CI: PASS", rendered)
        self.assertIn("## Verification Provenance", rendered)
        self.assertIn("status: manual", rendered)
        self.assertIn("## Warnings", rendered)

    def test_unverified_or_fake_recorded_claim_blocks(self):
        for verified in (
            "<fill in: test command>",
            "not run",
            "ruff check . (exit 0) [recorded by agentcam]",
        ):
            with self.subTest(verified=verified):
                handoff = VALID_HANDOFF.replace(
                    "Verified: python -m unittest", f"Verified: {verified}"
                )
                report = corridor_ci.evaluate(
                    changed_files=[
                        "frontend/src/components/ui/rating.tsx",
                        "frontend/tests/rating.spec.ts",
                    ],
                    corridor_text=handoff,
                )
                assessment = corridor_ci.classify_verification_provenance(
                    report.handoff["Verified"], self._sample_evidence_manifest()
                )
                enforced = corridor_ci.apply_verification_policy(report, assessment)

                self.assertFalse(enforced.ok)
                self.assertIn("verification is unverified", "\n".join(enforced.issues))

    def test_render_markdown_includes_recorded_evidence(self):
        report = corridor_ci.evaluate(
            changed_files=[
                "frontend/src/components/ui/rating.tsx",
                "frontend/tests/rating.spec.ts",
            ],
            corridor_text=VALID_HANDOFF,
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
        # Committed manifests are author-controlled; no shape may crash the
        # renderer before policy and reporting complete.
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
                json.dumps({"pull_request": {"body": VALID_HANDOFF.replace(
                    "Risk: none-detected", "Risk: high"
                )}}),
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
