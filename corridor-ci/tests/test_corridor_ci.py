import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("corridor_ci", ROOT / "bin" / "corridor_ci.py")
corridor_ci = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = corridor_ci
SPEC.loader.exec_module(corridor_ci)


class CorridorV14Test(unittest.TestCase):
    def test_normalize_and_git_style_globs(self):
        self.assertEqual(corridor_ci.normalize_path("./src\\app.py"), "src/app.py")
        self.assertTrue(corridor_ci.path_matches("src/app.py", "src/*.py"))
        self.assertFalse(corridor_ci.path_matches("src/deep/app.py", "src/*.py"))
        self.assertTrue(corridor_ci.path_matches("src/deep/app.py", "src/**/*.py"))
        self.assertTrue(corridor_ci.path_matches("src", "src/**"))

    def test_product_fingerprint_excludes_only_fixed_review_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "src").mkdir()
            (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
            (repo / ".guardrails").mkdir()
            (repo / ".guardrails" / "review.json").write_text("{}", encoding="utf-8")
            product = corridor_ci.compute_current_product_fingerprint(
                repo, ["src/app.py", ".guardrails/review.json"]
            )
            without_metadata = corridor_ci.compute_current_product_fingerprint(repo, ["src/app.py"])
            self.assertEqual(product, without_metadata)
            legacy = corridor_ci.compute_current_product_fingerprint(
                repo, ["src/app.py", ".agentcam/manifest.redacted.json"]
            )
            self.assertNotEqual(legacy, without_metadata)

    def test_workflow_approval_is_exact_and_head_bound(self):
        head = "a" * 40
        approved = corridor_ci.evaluate_workflow_policy(
            changed_files=[".github/workflows/ci.yml"],
            comments=[{
                "body": f"Guardrails-Workflow-Approval: {head}",
                "author_association": "OWNER",
                "user": {"login": "owner"},
            }],
            head_sha=head,
            pr_author="owner",
        )
        stale = corridor_ci.evaluate_workflow_policy(
            changed_files=[".github/workflows/ci.yml"],
            comments=[{
                "body": f"Guardrails-Workflow-Approval: {'b' * 40}",
                "author_association": "OWNER",
                "user": {"login": "owner"},
            }],
            head_sha=head,
            pr_author="owner",
        )
        self.assertTrue(approved.ok)
        self.assertFalse(stale.ok)

    def test_member_cannot_approve_their_own_policy_change(self):
        head = "a" * 40
        decision = corridor_ci.evaluate_workflow_policy(
            changed_files=[".github/workflows/ci.yml"],
            comments=[{
                "body": f"Guardrails-Workflow-Approval: {head}",
                "author_association": "MEMBER",
                "user": {"login": "author"},
            }],
            head_sha=head,
            pr_author="author",
        )
        self.assertFalse(decision.ok)

    def test_dependency_approval_is_exact_and_head_bound(self):
        head = "c" * 40
        decision = corridor_ci.evaluate_dependency_policy(
            dependency_files=["requirements.txt"],
            comments=[{
                "body": f"Guardrails-Dependency-Approval: {head}",
                "author_association": "OWNER",
                "user": {"login": "owner"},
            }],
            head_sha=head,
            pr_author="owner",
        )
        self.assertTrue(decision.ok)

    def test_missing_head_sha_fails_closed_for_both_policies(self):
        # Regression: with an empty head SHA the compiled pattern reduced
        # to "label with no SHA", so a bare approval comment matched and
        # the head binding was silently lost.
        workflow = corridor_ci.evaluate_workflow_policy(
            changed_files=[".github/workflows/ci.yml"],
            comments=[{
                "body": "Guardrails-Workflow-Approval:",
                "author_association": "OWNER",
                "user": {"login": "owner"},
            }],
            head_sha="",
            pr_author="owner",
        )
        dependency = corridor_ci.evaluate_dependency_policy(
            dependency_files=["requirements.txt"],
            comments=[{
                "body": "Guardrails-Dependency-Approval:",
                "author_association": "OWNER",
                "user": {"login": "owner"},
            }],
            head_sha="",
            pr_author="owner",
        )
        self.assertFalse(workflow.ok)
        self.assertFalse(dependency.ok)

    def test_markdown_escape_blocks_structure_and_mentions(self):
        escaped = corridor_ci.escape_markdown("x\n# injected\n```\n@team")
        self.assertNotIn("\n# injected", escaped)
        self.assertNotIn("```", escaped)
        self.assertIn("@\u200bteam", escaped)

    def test_review_reader_rejects_malformed_and_oversized(self):
        with tempfile.TemporaryDirectory() as raw:
            malformed = Path(raw) / "bad.json"
            malformed.write_text("{", encoding="utf-8")
            value, note = corridor_ci.read_review_artifact(malformed)
            self.assertIsNone(value)
            self.assertIn("malformed", note)
            malformed.write_bytes(b"x" * (1024 * 1024 + 1))
            value, note = corridor_ci.read_review_artifact(malformed)
            self.assertIsNone(value)
            self.assertIn("1 MiB", note)

    def test_sticky_comment_updates_only_actions_bot_comment(self):
        calls = []

        def transport(method, url, token, payload):
            calls.append((method, url, payload))
            if method == "GET":
                return [
                    {
                        "id": 1,
                        "body": corridor_ci.COMMENT_MARKER,
                        "user": {"login": "attacker"},
                    },
                    {
                        "id": 2,
                        "body": corridor_ci.COMMENT_MARKER,
                        "user": {"login": "github-actions[bot]"},
                    },
                ]
            return {}

        corridor_ci.upsert_pr_comment(
            "report", token="token", repository="owner/repo", pr_number=4,
            transport=transport,
        )
        patches = [url for method, url, _ in calls if method == "PATCH"]
        self.assertEqual(len(patches), 1)
        self.assertTrue(patches[0].endswith("/comments/2"))

    def test_main_accepts_arbitrary_pr_body_with_valid_artifact(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "base.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
            subprocess.run(["git", "switch", "-qc", "feature"], cwd=repo, check=True)
            (repo / "src").mkdir()
            (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
            fingerprint = corridor_ci.compute_current_product_fingerprint(repo, ["src/app.py"])
            review = {
                "schema": 1,
                "generator": {
                    "agentcam_version": "0.6.0",
                    "runtime_revision": "test",
                },
                "delivery": {
                    "base_commit": None,
                    "product_fingerprint": fingerprint,
                    "changed_files": [{"path": "src/app.py", "status": "modified"}],
                    "outcomes": ["works"],
                    "scope": ["src/app.py"],
                    "scope_changes": [],
                    "review_first": "src/app.py",
                    "risk": "none-detected",
                },
                "verification": {
                    "level": "structural-only",
                    "checks": [{
                        "id": "structural",
                        "argv": ["git", "diff", "--check"],
                        "exit_code": 0,
                        "duration_ms": 1,
                        "state_fingerprint": fingerprint,
                    }],
                },
                "capture": {"terminal": "unavailable", "coverage": "partial"},
                "approval": None,
            }
            (repo / ".guardrails").mkdir()
            (repo / ".guardrails" / "review.json").write_text(json.dumps(review), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "feature"], cwd=repo, check=True)
            event = repo / "event.json"
            event.write_text(json.dumps({
                "number": 7,
                "pull_request": {
                    "body": "write anything here; there is no grammar",
                    "title": "Fix app",
                    "html_url": "https://example.test/pull/7",
                    "head": {"sha": "a" * 40},
                    "user": {"login": "author"},
                },
            }), encoding="utf-8")
            output = StringIO()
            with mock.patch.dict(os.environ, {
                "GITHUB_EVENT_PATH": str(event),
                "GITHUB_BASE_REF": "main",
            }, clear=False), redirect_stdout(output):
                code = corridor_ci.main(["--repo", str(repo)])
            self.assertEqual(code, 0, output.getvalue())
            self.assertIn("Corridor CI: PASS", output.getvalue())

if __name__ == "__main__":
    unittest.main()
