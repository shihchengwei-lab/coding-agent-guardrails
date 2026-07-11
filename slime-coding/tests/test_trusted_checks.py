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

    def write_corridor(self, stop, high=""):
        target = self.repo / ".slime" / "corridor.md"
        target.parent.mkdir(exist_ok=True)
        target.write_text(
            "# Corridor: trusted-check\n\n## Rigor\n"
            + ("high" if high else "trivial")
            + "\n\n## Outcome\nworks\n\n## Paths\n- product.txt\n\n"
            + ("## Evidence\n- Supports: test\n- Would falsify: fail\n\n" if high else "")
            + f"## Stop Condition\n{stop}\n"
            + (f"\n## High-risk Controls\n- Failure mode: bad\n- Rollback: revert\n{high}\n" if high else ""),
            encoding="utf-8",
        )

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

    def test_inline_command_and_legacy_env_are_never_executed(self):
        marker = self.repo / "should-not-exist"
        self.write_corridor(f"- Command: {sys.executable} -c \"open(r'{marker}','w').write('bad')\"")
        (self.repo / "product.txt").write_text("delta", encoding="utf-8")
        blocks = slime.stop_blocks(self.repo)
        self.assertTrue(any("migration" in block.lower() for block in blocks))
        self.assertFalse(marker.exists())

        self.write_corridor("- Manual: inspected generated output")
        with mock.patch.dict(os.environ, {"SLIME_TEST_CMD": "echo forbidden"}):
            blocks = slime.stop_blocks(self.repo)
        self.assertTrue(any("SLIME_TEST_CMD" in block for block in blocks))

    def test_unknown_check_and_high_duplicate_argv_block(self):
        self.write_config({
            "primary": {"argv": [sys.executable, "-c", "raise SystemExit(0)"]},
            "same": {"argv": [sys.executable, "-c", "raise SystemExit(0)"]},
        })
        self.write_corridor("- Check: missing")
        self.assertTrue(any("unknown check" in block.lower() for block in slime.stop_blocks(self.repo)))

        self.write_corridor("- Check: primary", "- Independent check: same")
        self.assertTrue(any("same argv" in block.lower() for block in slime.stop_blocks(self.repo)))

    def test_legacy_corridor_blocks_product_delta(self):
        target = self.repo / ".slime" / "corridor.md"
        target.parent.mkdir()
        target.write_text(
            "# Corridor: old\n\n## Paths\n- product.txt\n\n## Stop Condition\n- Manual: checked\n",
            encoding="utf-8",
        )
        (self.repo / "product.txt").write_text("delta", encoding="utf-8")

        blocks = slime.stop_blocks(self.repo)

        self.assertTrue(any("Rigor" in block and "migration" in block for block in blocks))

    def test_bash_feedback_reports_missing_corridor_after_write(self):
        (self.repo / "product.txt").write_text("shell delta", encoding="utf-8")
        output = StringIO()

        with redirect_stdout(output):
            slime.post_tool({
                "tool_name": "Bash",
                "cwd": str(self.repo),
                "tool_input": {"command": "write product"},
            })

        self.assertIn('"decision": "block"', output.getvalue())
        self.assertIn("corridor.md is missing", output.getvalue())


if __name__ == "__main__":
    unittest.main()
