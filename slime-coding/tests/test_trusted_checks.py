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

    def test_is_dependency_manifest_consistent_across_call_sites(self):
        # sync_pr_approval passes original-case paths; delivery_risk passes
        # lowercased ones. Both spellings must classify identically.
        self.assertTrue(slime.is_dependency_manifest("Cargo.toml"))
        self.assertTrue(slime.is_dependency_manifest("cargo.toml"))
        self.assertFalse(slime.is_dependency_manifest("src/main.rs"))


if __name__ == "__main__":
    unittest.main()
