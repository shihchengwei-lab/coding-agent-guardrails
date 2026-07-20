import importlib.machinery
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


PATCH_COST = Path(__file__).resolve().parents[1] / "bin" / "patch-cost"
loader = importlib.machinery.SourceFileLoader("slime_patch_cost", str(PATCH_COST))
spec = importlib.util.spec_from_loader(loader.name, loader)
slime = importlib.util.module_from_spec(spec)
loader.exec_module(slime)


class TrustedChecksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        (self.repo / "base.txt").write_text("base", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=self.repo, check=True)
        self.git_dir = Path(
            subprocess.run(
                ["git", "rev-parse", "--absolute-git-dir"], cwd=self.repo,
                check=True, capture_output=True, text=True,
            ).stdout.strip()
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_config(self, checks):
        target = self.git_dir / "guardrails" / "config.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"schema": 1, "checks": checks}), encoding="utf-8")

    def test_valid_argv_runs_without_shell(self):
        self.write_config({"primary": {"argv": [
            sys.executable, "-c", "import sys; assert sys.argv[1] == '&&'", "&&",
        ]}})
        checks, error = slime.load_trusted_checks(self.repo)

        self.assertIsNone(error)
        self.assertEqual(slime.run_trusted_check(self.repo, checks["primary"], "primary")[0], 0)

    def test_missing_malformed_unknown_and_empty_config_fail_closed(self):
        checks, error = slime.load_trusted_checks(self.repo)
        self.assertEqual(checks, {})
        self.assertIn("config.json", error)

        for value in (
            {"schema": 2, "checks": {}},
            {"schema": 1, "checks": {"UPPER": {"argv": ["python"]}}},
            {"schema": 1, "checks": {"primary": {"argv": []}}},
            {"schema": 1, "checks": {"primary": {"argv": ["python"], "timeout_seconds": 0}}},
        ):
            with self.subTest(value=value):
                target = self.git_dir / "guardrails" / "config.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(value), encoding="utf-8")
                self.assertIsNotNone(slime.load_trusted_checks(self.repo)[1])

    def test_timeout_blocks(self):
        self.write_config({"slow": {"argv": [
            sys.executable, "-c", "import time; time.sleep(2)",
        ], "timeout_seconds": 1}})
        checks, error = slime.load_trusted_checks(self.repo)
        self.assertIsNone(error)
        code, message = slime.run_trusted_check(self.repo, checks["slow"], "slow")
        self.assertEqual(code, 124)
        self.assertIn("timed out", message)

    def test_legacy_command_environment_is_not_an_execution_source(self):
        marker = self.repo / "should-not-exist"
        with mock.patch.dict(
            os.environ,
            {
                "SLIME_TEST_CMD": f"echo forbidden > {marker}",
                "SLIME_TYPECHECK_CMD": f"echo forbidden > {marker}",
            },
        ):
            checks, error = slime._run_review_checks(self.repo, "fingerprint")

        self.assertIsNone(error)
        self.assertEqual([item["id"] for item in checks], ["structural"])
        self.assertFalse(marker.exists())

    def test_dirty_signature_batch_reads_index_once_for_200_files(self):
        for index in range(200):
            (self.repo / f"file-{index:03}.txt").write_text("before", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "many files"], cwd=self.repo, check=True)
        for index in range(200):
            (self.repo / f"file-{index:03}.txt").write_text("after", encoding="utf-8")

        real_git = slime.git
        calls = []

        def counted_git(cwd, *args):
            calls.append(args)
            return real_git(cwd, *args)

        with mock.patch.object(slime, "git", side_effect=counted_git):
            signatures = slime.dirty_signatures(self.repo)

        self.assertEqual(len(signatures), 200)
        index_calls = [args for args in calls if args[:2] == ("ls-files", "--stage")]
        self.assertEqual(index_calls, [("ls-files", "--stage", "-z")])

    def test_bash_feedback_reports_missing_git_local_scope_after_write(self):
        (self.repo / "product.txt").write_text("shell delta", encoding="utf-8")
        output = StringIO()

        with redirect_stdout(output):
            slime.post_tool({
                "tool_name": "Bash",
                "cwd": str(self.repo),
                "tool_input": {"command": "write product"},
            })

        self.assertIn('"decision": "block"', output.getvalue())
        self.assertIn("declared its intent", output.getvalue())

    def test_delivery_risk_flags_cargo_manifest_as_dependency_change(self):
        # Regression: delivery_risk lowercases paths before calling
        # is_dependency_manifest, whose set held the mixed-case literal
        # "Cargo.toml" — Rust dependency edits bypassed the high-risk gate.
        for path in (
            "Cargo.toml", "backend/Cargo.toml", "package.json",
            # Lockfiles must stay aligned with Corridor CI's floor, or
            # the local artifact underreports and the PR gate rejects it.
            "uv.lock", "package-lock.json", "poetry.lock", "go.sum",
        ):
            level, reasons = slime.delivery_risk(
                [{"path": path, "status": "modified"}]
            )
            self.assertEqual(level, "high", path)
            self.assertIn("dependency manifest changed", reasons, path)

    def _git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def test_scope_set_absorbs_stale_delivery_after_base_was_merged(self):
        # Regression: delivery state is keyed by branch name, and a branch
        # rebuilt after its delivery merged silently inherited the old
        # base_commit, misfiring every scope check.
        default = self._git("rev-parse", "--abbrev-ref", "HEAD")
        old_base = self._git("rev-parse", "HEAD")
        self._git("switch", "-qc", "feature")
        (self.repo / "work.txt").write_text("v1", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-qm", "delivery one")
        slime.set_delivery_scope(self.repo, "first delivery", ["work.txt"])
        self.assertEqual(
            slime.read_delivery_scope(self.repo)["base_commit"], old_base
        )
        approval = Path(slime._approval_path(self.repo))
        approval.parent.mkdir(parents=True, exist_ok=True)
        approval.write_text("{}", encoding="utf-8")

        # Delivery merges; the branch is rebuilt from the advanced base.
        self._git("switch", "-q", default)
        self._git("merge", "-q", "--no-ff", "-m", "merge one", "feature")
        new_base = self._git("rev-parse", "HEAD")
        self._git("branch", "-qf", "feature", default)
        self._git("switch", "-q", "feature")
        (self.repo / "work2.txt").write_text("v2", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-qm", "delivery two")

        slime.set_delivery_scope(self.repo, "second delivery", ["work2.txt"])
        self.assertEqual(
            slime.read_delivery_scope(self.repo)["base_commit"], new_base
        )
        self.assertFalse(approval.exists(), "stale approval must be dropped")

    def test_scope_set_keeps_base_across_turns_without_upstream(self):
        # Single-branch fallback (resolve_delivery_base == HEAD): committing
        # mid-delivery and re-declaring scope must keep aggregating from the
        # original base, exactly as before.
        base = self._git("rev-parse", "HEAD")
        slime.set_delivery_scope(self.repo, "delivery", ["work.txt"])
        (self.repo / "work.txt").write_text("v1", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-qm", "mid-delivery commit")
        slime.set_delivery_scope(self.repo, "delivery continued", ["work.txt"])
        self.assertEqual(
            slime.read_delivery_scope(self.repo)["base_commit"], base
        )

    def test_is_dependency_manifest_consistent_across_call_sites(self):
        # sync_pr_approval passes original-case paths; delivery_risk passes
        # lowercased ones. Both spellings must classify identically.
        self.assertTrue(slime.is_dependency_manifest("Cargo.toml"))
        self.assertTrue(slime.is_dependency_manifest("cargo.toml"))
        self.assertFalse(slime.is_dependency_manifest("src/main.rs"))


class ReviewFirstTest(unittest.TestCase):
    def test_workflow_outranks_changelog(self):
        self.assertEqual(
            slime.choose_review_first([
                {"path": "CHANGELOG.md", "status": "modified"},
                {"path": ".github/workflows/corridor.yml", "status": "modified"},
            ]),
            ".github/workflows/corridor.yml",
        )

    def test_dependency_manifest_outranks_plain_source(self):
        self.assertEqual(
            slime.choose_review_first([
                {"path": "setup.py", "status": "modified"},
                {"path": "src/api.py", "status": "modified"},
            ]),
            "setup.py",
        )

    def test_high_risk_segment_outranks_plain_source(self):
        self.assertEqual(
            slime.choose_review_first([
                {"path": "src/api.py", "status": "modified"},
                {"path": "src/auth/tokens.py", "status": "modified"},
            ]),
            "src/auth/tokens.py",
        )

    def test_plain_source_outranks_tests_and_docs(self):
        # Alphabetical order alone would pick the docs file.
        self.assertEqual(
            slime.choose_review_first([
                {"path": "docs/guide.md", "status": "modified"},
                {"path": "src/zz_util.py", "status": "modified"},
                {"path": "tests/test_api.py", "status": "modified"},
            ]),
            "src/zz_util.py",
        )

    def test_deletion_leads_within_a_tier(self):
        self.assertEqual(
            slime.choose_review_first([
                {"path": "src/b.py", "status": "modified"},
                {"path": "src/z.py", "status": "deleted"},
            ]),
            "src/z.py",
        )

    def test_ties_break_alphabetically(self):
        self.assertEqual(
            slime.choose_review_first([
                {"path": "src/b.py", "status": "modified"},
                {"path": "src/a.py", "status": "modified"},
            ]),
            "src/a.py",
        )

    def test_every_delivery_risk_path_signal_outranks_plain_source(self):
        plain = slime.review_first_tier("src/app.py")
        for path in (
            ".github/workflows/deploy.yml",
            "requirements.txt",
            "Cargo.toml",
            "src/auth/login.py",
            "infra/terraform/main.tf",
        ):
            self.assertLess(slime.review_first_tier(path), plain, path)


if __name__ == "__main__":
    unittest.main()
