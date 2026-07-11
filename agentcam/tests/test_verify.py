"""Tests for `agentcam verify` — checks recorded as run evidence.

End-to-end via real agentcam subprocesses against a real git repo,
mirroring tests/test_handoff.py.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cli_harness import _agentcam, _make_one_run, _manifest, _run_dir


def _manifest_evidence(repo: Path) -> dict:
    return _manifest(repo)["evidence"]


PASS_CMD = (sys.executable, "-c", "raise SystemExit(0)")
FAIL_CMD = (sys.executable, "-c", "raise SystemExit(3)")


class TestVerify:
    def test_records_passing_check(self, tmp_git_repo: Path):
        _make_one_run(tmp_git_repo)
        proc = _agentcam(tmp_git_repo, "verify", "--", *PASS_CMD)
        assert proc.returncode == 0, proc.stderr
        checks = _manifest_evidence(tmp_git_repo)["verifications"]
        assert len(checks) == 1
        assert checks[0]["exit_code"] == 0
        assert checks[0]["duration_seconds"] >= 0
        assert checks[0]["recorded_at"]
        assert "-c" in checks[0]["command"]
        assert checks[0]["record_id"]
        assert len(checks[0]["state_fingerprint"]) == 64

    def test_failing_check_passes_exit_code_through(
        self, tmp_git_repo: Path
    ):
        _make_one_run(tmp_git_repo)
        proc = _agentcam(tmp_git_repo, "verify", "--", *FAIL_CMD)
        assert proc.returncode == 3
        checks = _manifest_evidence(tmp_git_repo)["verifications"]
        assert checks[0]["exit_code"] == 3

    def test_appends_on_repeat(self, tmp_git_repo: Path):
        _make_one_run(tmp_git_repo)
        assert _agentcam(
            tmp_git_repo, "verify", "--", *PASS_CMD
        ).returncode == 0
        assert _agentcam(
            tmp_git_repo, "verify", "--", *FAIL_CMD
        ).returncode == 3
        checks = _manifest_evidence(tmp_git_repo)["verifications"]
        assert [c["exit_code"] for c in checks] == [0, 3]

    def test_no_command_errors(self, tmp_git_repo: Path):
        _make_one_run(tmp_git_repo)
        proc = _agentcam(tmp_git_repo, "verify")
        assert proc.returncode == 2
        assert b"no command" in proc.stderr

    def test_old_manifest_without_evidence_errors(
        self, tmp_git_repo: Path
    ):
        _make_one_run(tmp_git_repo)
        manifest_path = _run_dir(tmp_git_repo) / "manifest.json"
        data = json.loads(manifest_path.read_text("utf-8"))
        data.pop("evidence")
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        proc = _agentcam(tmp_git_repo, "verify", "--", *PASS_CMD)
        assert proc.returncode == 2
        assert b"older agentcam" in proc.stderr
        # Nothing was written back to the manifest.
        after = json.loads(manifest_path.read_text("utf-8"))
        assert "evidence" not in after

    def test_outside_git_repo_errors(self, tmp_path: Path):
        proc = _agentcam(tmp_path, "verify", "--", *PASS_CMD)
        assert proc.returncode == 2
        assert proc.stderr.startswith(b"agentcam:")

    def test_malformed_evidence_errors_before_running_check(
        self, tmp_git_repo: Path
    ):
        _make_one_run(tmp_git_repo)
        manifest_path = _run_dir(tmp_git_repo) / "manifest.json"
        data = json.loads(manifest_path.read_text("utf-8"))
        data["evidence"] = "corrupted"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        marker = tmp_git_repo / "check-ran.marker"
        proc = _agentcam(
            tmp_git_repo, "verify", "--",
            sys.executable, "-c",
            f"open(r'{marker}','w').write('x')",
        )
        assert proc.returncode == 2
        assert b"malformed" in proc.stderr
        # Fail-fast: the check must not have run.
        assert not marker.exists()

    def test_malformed_verifications_list_errors(
        self, tmp_git_repo: Path
    ):
        _make_one_run(tmp_git_repo)
        manifest_path = _run_dir(tmp_git_repo) / "manifest.json"
        data = json.loads(manifest_path.read_text("utf-8"))
        data["evidence"]["verifications"] = {"not": "a list"}
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        proc = _agentcam(tmp_git_repo, "verify", "--", *PASS_CMD)
        assert proc.returncode == 2
        assert b"malformed" in proc.stderr

    def test_check_that_edits_manifest_is_not_clobbered(
        self, tmp_git_repo: Path
    ):
        """A record appended while the check runs (e.g. a concurrent
        verify) must survive: verify re-reads before writing."""
        _make_one_run(tmp_git_repo)
        manifest_path = _run_dir(tmp_git_repo) / "manifest.json"
        inject = (
            "import json;"
            f"p=r'{manifest_path}';"
            "d=json.load(open(p,encoding='utf-8'));"
            "d['evidence'].setdefault('verifications',[]).append("
            "{'command':'other','exit_code':0,'duration_seconds':0.1,"
            "'recorded_at':'x'});"
            "open(p,'w',encoding='utf-8').write(json.dumps(d))"
        )
        proc = _agentcam(
            tmp_git_repo, "verify", "--", sys.executable, "-c", inject
        )
        assert proc.returncode == 0, proc.stderr
        checks = _manifest_evidence(tmp_git_repo)["verifications"]
        assert len(checks) == 2
        assert checks[0]["command"] == "other"

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="PATHEXT (.cmd) resolution is Windows-only",
    )
    def test_cmd_runner_on_path_resolves_by_bare_name(
        self, tmp_git_repo: Path
    ):
        """A PATHEXT-only runner on PATH (the `npm` shape: npm.cmd)
        must work by bare name — `verify` resolves via shutil.which."""
        (tmp_git_repo / "okcheck.cmd").write_text(
            "@exit /b 0\r\n", encoding="ascii"
        )
        _make_one_run(tmp_git_repo)
        env = {
            **os.environ,
            "PATH": f"{tmp_git_repo}{os.pathsep}"
            + os.environ.get("PATH", ""),
        }
        proc = _agentcam(tmp_git_repo, "verify", "--", "okcheck", env=env)
        assert proc.returncode == 0, proc.stderr


class TestVerifiedLineInHandoff:
    def test_handoff_fills_verified_from_passing_check(
        self, tmp_git_repo: Path
    ):
        _make_one_run(tmp_git_repo)
        assert _agentcam(
            tmp_git_repo, "verify", "--", *PASS_CMD
        ).returncode == 0
        proc = _agentcam(tmp_git_repo, "handoff")
        assert proc.returncode == 0, proc.stderr
        verified = proc.stdout.decode("utf-8").strip().splitlines()[3]
        assert verified.startswith("Verified: ")
        assert "(exit 0)" in verified
        assert "[locally recorded by agentcam]" in verified
        assert "<fill in" not in verified

    def test_handoff_keeps_fill_in_when_only_failed_checks(
        self, tmp_git_repo: Path
    ):
        _make_one_run(tmp_git_repo)
        assert _agentcam(
            tmp_git_repo, "verify", "--", *FAIL_CMD
        ).returncode == 3
        proc = _agentcam(tmp_git_repo, "handoff")
        assert proc.returncode == 0, proc.stderr
        verified = proc.stdout.decode("utf-8").strip().splitlines()[3]
        assert "<fill in" in verified
        assert "exit 3" in verified

    def test_newer_failure_overrides_older_pass(self, tmp_git_repo: Path):
        _make_one_run(tmp_git_repo)
        same_command = (
            sys.executable,
            "-c",
            "import os; raise SystemExit(int(os.environ['VERIFY_EXIT']))",
        )
        assert _agentcam(
            tmp_git_repo,
            "verify",
            "--",
            *same_command,
            env={**os.environ, "VERIFY_EXIT": "0"},
        ).returncode == 0
        assert _agentcam(
            tmp_git_repo,
            "verify",
            "--",
            *same_command,
            env={**os.environ, "VERIFY_EXIT": "3"},
        ).returncode == 3

        proc = _agentcam(tmp_git_repo, "handoff")

        assert proc.returncode == 0, proc.stderr
        verified = proc.stdout.decode("utf-8").strip().splitlines()[3]
        assert "<fill in" in verified
        assert "exit 3" in verified
        assert "locally recorded" not in verified

    def test_product_edit_after_verify_makes_handoff_stale(
        self, tmp_git_repo: Path
    ):
        _make_one_run(tmp_git_repo)
        assert _agentcam(tmp_git_repo, "verify", "--", *PASS_CMD).returncode == 0
        (tmp_git_repo / "produced.txt").write_text("changed later", encoding="utf-8")

        proc = _agentcam(tmp_git_repo, "handoff")

        assert proc.returncode == 2
        assert b"state changed after the recorded run" in proc.stderr

    def test_verify_latest_rejects_multiple_active_sessions(
        self, tmp_git_repo: Path
    ):
        _make_one_run(tmp_git_repo)
        sessions = tmp_git_repo / ".git" / "agentcam" / "sessions"
        for name in ("turn-a", "turn-b"):
            session = sessions / name
            session.mkdir(parents=True)
            (session / "state_before.pickle").write_bytes(b"snapshot")

        proc = _agentcam(tmp_git_repo, "verify", "--", *PASS_CMD)

        assert proc.returncode == 2
        assert b"multiple active sessions" in proc.stderr

    def test_concurrent_verifications_are_all_preserved(
        self, tmp_git_repo: Path
    ):
        _make_one_run(tmp_git_repo)

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(
                pool.map(
                    lambda _: _agentcam(tmp_git_repo, "verify", "--", *PASS_CMD),
                    range(6),
                )
            )

        assert all(proc.returncode == 0 for proc in results)
        handoff = _agentcam(tmp_git_repo, "handoff")
        assert handoff.returncode == 0, handoff.stderr
        records = list((_run_dir(tmp_git_repo) / "verifications").glob("*.json"))
        assert len(records) == 6
        assert all(json.loads(path.read_text("utf-8")) for path in records)

    def test_export_files_carries_verifications(
        self, tmp_git_repo: Path
    ):
        rid = _make_one_run(tmp_git_repo)
        assert _agentcam(
            tmp_git_repo, "verify", "--", *PASS_CMD
        ).returncode == 0
        dest = tmp_git_repo / ".agentcam"
        proc = _agentcam(tmp_git_repo, "export", rid, "--files", str(dest))
        assert proc.returncode == 0, proc.stderr
        redacted = json.loads(
            (dest / "manifest.redacted.json").read_text("utf-8")
        )
        checks = redacted["evidence"]["verifications"]
        assert checks and checks[0]["exit_code"] == 0
