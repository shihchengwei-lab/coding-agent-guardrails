"""End-to-end tests: real subprocess, real git repo, real ``agentbox run``.

Slower than unit tests (real subprocess + git per case), but they're the only
way to confirm cli.py wires the modules correctly. Also the regression suite
for plan §Verification.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


GIT_AUTHOR = ["-c", "user.email=t@t", "-c", "user.name=t"]


def _agentbox(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke agentbox via the same Python that's running pytest (the venv)."""
    return subprocess.run(
        [sys.executable, "-m", "agentbox.cli", *args],
        cwd=cwd,
        capture_output=True,
        timeout=25,
    )


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *GIT_AUTHOR, *args],
        cwd=cwd, check=True, capture_output=True,
    )


def _run_dir(repo: Path) -> Path:
    runs = repo / ".git" / "agentbox" / "runs"
    return next(runs.iterdir())


def _report(repo: Path) -> str:
    return (_run_dir(repo) / "AGENT_RUN_REPORT.md").read_text(encoding="utf-8")


def _manifest(repo: Path) -> dict:
    return json.loads(
        (_run_dir(repo) / "manifest.json").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Smoke + self-pollution
# ---------------------------------------------------------------------------

class TestSmoke:
    def test_create_file(self, tmp_git_repo: Path):
        proc = _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "open('hello.txt','w').write('hi')",
        )
        assert proc.returncode == 0
        report = _report(tmp_git_repo)
        assert "hello.txt" in report

    def test_git_status_does_not_list_agentbox(self, tmp_git_repo: Path):
        # Plan §1: .git/agentbox/ must NOT appear in git status (git ignores
        # its own internals).
        _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "pass",
        )
        ps = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tmp_git_repo, capture_output=True, text=True, check=True,
        )
        assert "agentbox" not in ps.stdout
        assert ".git" not in ps.stdout


# ---------------------------------------------------------------------------
# Risk flag regressions (plan §Verification)
# ---------------------------------------------------------------------------

class TestRiskFlags:
    def test_delete_tracked_file_high(self, tmp_git_repo: Path):
        (tmp_git_repo / "tracked.txt").write_text("x")
        _git(tmp_git_repo, "add", "tracked.txt")
        _git(tmp_git_repo, "commit", "-q", "-m", "add")
        proc = _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "import os; os.remove('tracked.txt')",
        )
        assert proc.returncode == 0
        report = _report(tmp_git_repo)
        assert "HIGH" in report
        assert "tracked file deleted" in report

    def test_auth_path_high(self, tmp_git_repo: Path):
        (tmp_git_repo / "src").mkdir()
        (tmp_git_repo / "src" / "auth").mkdir()
        (tmp_git_repo / "src" / "auth" / "login.py").write_text("x")
        _git(tmp_git_repo, "add", ".")
        _git(tmp_git_repo, "commit", "-q", "-m", "auth")
        proc = _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('src/auth/login.py','a').write('# c\\n')",
        )
        assert proc.returncode == 0
        report = _report(tmp_git_repo)
        assert "Overall risk: **HIGH**" in report
        assert "auth path" in report

    def test_author_md_not_promoted_to_high(self, tmp_git_repo: Path):
        # Regression: 'auth' segment must not match 'author'.
        (tmp_git_repo / "author.md").write_text("x")
        _git(tmp_git_repo, "add", ".")
        _git(tmp_git_repo, "commit", "-q", "-m", "author")
        _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "open('author.md','a').write('# x\\n')",
        )
        report = _report(tmp_git_repo)
        assert "Overall risk: **HIGH**" not in report

    def test_dependency_manifest_medium(self, tmp_git_repo: Path):
        (tmp_git_repo / "package.json").write_text("{}")
        _git(tmp_git_repo, "add", ".")
        _git(tmp_git_repo, "commit", "-q", "-m", "pkg")
        _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('package.json','w').write('{\"name\":\"x\"}\\n')",
        )
        report = _report(tmp_git_repo)
        assert "MEDIUM" in report
        assert "npm package manifest" in report


# ---------------------------------------------------------------------------
# Pre-run dirty
# ---------------------------------------------------------------------------

class TestPreRunDirty:
    def test_dirty_no_blanket_rollback(self, tmp_git_repo: Path):
        (tmp_git_repo / "tracked.txt").write_text("first")
        _git(tmp_git_repo, "add", ".")
        _git(tmp_git_repo, "commit", "-q", "-m", "init")
        (tmp_git_repo / "tracked.txt").write_text("dirty")  # uncommitted modify

        _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "print('noop')",
        )
        report = _report(tmp_git_repo)
        assert "Manual review required" in report
        # Plan §5: pre-run dirty must NOT suggest a blanket rollback command.
        assert "git restore --staged ." not in report


# ---------------------------------------------------------------------------
# Command failure → still reports + wrapper exit 1
# ---------------------------------------------------------------------------

class TestCommandFailure:
    def test_failure_still_reports(self, tmp_git_repo: Path):
        proc = _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "import sys; sys.exit(2)",
        )
        # Plan §9: any non-zero subprocess returncode -> wrapper exit 1.
        assert proc.returncode == 1
        report = _report(tmp_git_repo)
        assert "subprocess raw returncode: 2" in report
        m = _manifest(tmp_git_repo)
        assert m["exit_detail"]["wrapper_exit"] == 1
        assert m["exit_detail"]["raw_returncode"] == 2


# ---------------------------------------------------------------------------
# Redaction: raw preserved, redacted scrubbed (plan §6, §11)
# ---------------------------------------------------------------------------

class TestRedaction:
    def test_secret_in_stdout(self, tmp_git_repo: Path):
        token = "ghp_" + "A" * 40
        proc = _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", f"print('GITHUB_TOKEN={token}')",
        )
        assert proc.returncode == 0
        rd = _run_dir(tmp_git_repo)
        raw = (rd / "stdout.log").read_text(encoding="utf-8")
        red = (rd / "stdout.redacted.log").read_text(encoding="utf-8")
        assert token in raw, "raw must preserve the secret for forensics"
        assert token not in red, "redacted log must not leak the secret"
        assert "REDACTED" in red

    def test_pem_streaming(self, tmp_git_repo: Path):
        # PEM block emitted as multiple print() calls (i.e. multiple read
        # chunks from the runner's perspective).
        script = (
            "print('-----BEGIN RSA PRIVATE KEY-----')\n"
            "print('AAAAAAAA')\n"
            "print('BBBBBBBB')\n"
            "print('-----END RSA PRIVATE KEY-----')\n"
        )
        proc = _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", script,
        )
        assert proc.returncode == 0
        red = (_run_dir(tmp_git_repo) / "stdout.redacted.log").read_text(
            encoding="utf-8"
        )
        assert "BEGIN RSA" not in red
        assert "AAAAAAAA" not in red
        assert "[REDACTED:PEM]" in red

    def test_command_argv_redaction(self, tmp_git_repo: Path):
        # Plan §11: command argv passes through redact_argv before going
        # into the markdown report; raw stays only in manifest.
        secret = "sk-AAAAAAAAAAAAAAAAAAAA"
        _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "import sys; sys.argv  # noqa",
            "--api-key", secret,
        )
        report = _report(tmp_git_repo)
        m = _manifest(tmp_git_repo)
        assert secret not in report
        assert "[REDACTED:LLM_API_KEY]" in report
        assert secret in m["command_argv_raw"]
        assert "[REDACTED:LLM_API_KEY]" in m["command_argv_redacted"]


# ---------------------------------------------------------------------------
# Secret-like filename in markdown
# ---------------------------------------------------------------------------

class TestSecretFilenameRedaction:
    def test_dot_env_production_redacted(self, tmp_git_repo: Path):
        _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('.env.production','w').write('FAKE=x')",
        )
        report = _report(tmp_git_repo)
        # Filename never appears in markdown.
        assert ".env.production" not in report
        assert "<redacted-secret-filename>" in report


# ---------------------------------------------------------------------------
# Staged-only changes (plan §4 cached diff regression guard)
# ---------------------------------------------------------------------------

class TestStagedOnly:
    def test_staged_only_change_visible(self, tmp_git_repo: Path):
        # Agent stages a new file. Without --cached diff, this would be
        # invisible in the diff stat / name-status sections.
        script = (
            "import subprocess\n"
            "open('new.py','w').write('x')\n"
            "subprocess.run(['git','add','new.py'], check=True)\n"
        )
        proc = _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", script,
        )
        assert proc.returncode == 0
        report = _report(tmp_git_repo)
        assert "new.py" in report


# ---------------------------------------------------------------------------
# Output scanner end-to-end
# ---------------------------------------------------------------------------

class TestOutputScanner:
    def test_rm_rf_in_stdout_high(self, tmp_git_repo: Path):
        _agentbox(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "print('about to rm -rf /opt/old/data now')",
        )
        report = _report(tmp_git_repo)
        assert "HIGH" in report
        assert "rm -rf root-like path" in report
        # Risk Flags evidence cites pattern + line; the raw matched substring
        # must not leak via evidence. (The Command: section trivially echoes
        # whatever the user typed, so we only check the Risk Flags section.)
        risk_section = report.split("## Risk Flags")[1].split("\n## ")[0]
        assert "/opt/old/data" not in risk_section
