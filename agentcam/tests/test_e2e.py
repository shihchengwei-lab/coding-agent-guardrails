"""End-to-end tests: real subprocess, real git repo, real ``agentcam run``.

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


def _agentcam(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke agentcam via the same Python that's running pytest (the venv)."""
    return subprocess.run(
        [sys.executable, "-m", "agentcam.cli", *args],
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
    runs = repo / ".git" / "agentcam" / "runs"
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
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "open('hello.txt','w').write('hi')",
        )
        assert proc.returncode == 0
        report = _report(tmp_git_repo)
        assert "hello.txt" in report

    def test_git_status_does_not_list_agentcam(self, tmp_git_repo: Path):
        # Plan §1: .git/agentcam/ must NOT appear in git status (git ignores
        # its own internals). Use a command that creates a file so a run dir
        # actually exists (without that, no-diff cleanup makes the test
        # trivially pass via "nothing under .git/agentcam at all").
        _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "open('artifact.txt','w').write('x')",
        )
        ps = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tmp_git_repo, capture_output=True, text=True, check=True,
        )
        assert "agentcam" not in ps.stdout
        assert ".git" not in ps.stdout


# ---------------------------------------------------------------------------
# Risk flag regressions (plan §Verification)
# ---------------------------------------------------------------------------

class TestRiskFlags:
    def test_delete_tracked_file_high(self, tmp_git_repo: Path):
        (tmp_git_repo / "tracked.txt").write_text("x")
        _git(tmp_git_repo, "add", "tracked.txt")
        _git(tmp_git_repo, "commit", "-q", "-m", "add")
        proc = _agentcam(
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
        proc = _agentcam(
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
        _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "open('author.md','a').write('# x\\n')",
        )
        report = _report(tmp_git_repo)
        assert "Overall risk: **HIGH**" not in report

    def test_dependency_manifest_medium(self, tmp_git_repo: Path):
        (tmp_git_repo / "package.json").write_text("{}")
        _git(tmp_git_repo, "add", ".")
        _git(tmp_git_repo, "commit", "-q", "-m", "pkg")
        _agentcam(
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

        # Agent also modifies state (creates a new file) so the no-diff
        # cleanup doesn't delete the report. The property under test —
        # "no blanket rollback when pre-dirty" — is what matters, and that
        # applies whenever there IS a report (i.e. the agent did something).
        _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('new_artifact.txt','w').write('hi')",
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
        proc = _agentcam(
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
        # --keep-empty: this test inspects logs, doesn't change git state.
        proc = _agentcam(
            tmp_git_repo, "run", "--keep-empty", "--",
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
        # --keep-empty: this test inspects logs, doesn't change git state.
        proc = _agentcam(
            tmp_git_repo, "run", "--keep-empty", "--",
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
        # --keep-empty: this test inspects report+manifest, no git change.
        secret = "sk-AAAAAAAAAAAAAAAAAAAA"
        _agentcam(
            tmp_git_repo, "run", "--keep-empty", "--",
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
        _agentcam(
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
        proc = _agentcam(
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
        # Wrap a command that also writes a file, so the no-diff cleanup
        # doesn't discard the report we want to inspect.
        _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('x.txt','w').write('x'); print('about to rm -rf /opt/old/data now')",
        )
        report = _report(tmp_git_repo)
        assert "HIGH" in report
        assert "rm -rf root-like path" in report
        # Risk Flags evidence cites pattern + line; the raw matched substring
        # must not leak via evidence. (The Command: section trivially echoes
        # whatever the user typed, so we only check the Risk Flags section.)
        risk_section = report.split("## Risk Flags")[1].split("\n## ")[0]
        assert "/opt/old/data" not in risk_section


# ---------------------------------------------------------------------------
# No-diff cleanup: "always record, throw away if no diff"
# ---------------------------------------------------------------------------

class TestNoDiffCleanup:
    """`agentcam run` deletes the run dir when the wrapped command produced
    no git-visible change AND exited 0. Pure-alignment sessions ('agent and
    user discussed but did not change code') leave no clutter under
    .git/agentcam/runs/. Failures and any state change still produce a
    report. Opt out per-invocation with --keep-empty."""

    def test_no_op_success_leaves_no_run_dir(self, tmp_git_repo: Path):
        runs_dir = tmp_git_repo / ".git" / "agentcam" / "runs"
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "pass",
        )
        assert proc.returncode == 0
        # No-diff + exit 0 → run dir cleaned up entirely.
        assert not runs_dir.exists() or not any(runs_dir.iterdir()), (
            "runs dir should be empty after no-diff success run, got: "
            f"{list(runs_dir.iterdir()) if runs_dir.exists() else 'no runs dir'}"
        )

    def test_no_op_pre_dirty_leaves_no_run_dir(self, tmp_git_repo: Path):
        # Pre-existing dirty state, agent does nothing → state_before ==
        # state_after → still no report (the dirty was there before the
        # run, not caused by it).
        (tmp_git_repo / "tracked.txt").write_text("init")
        _git(tmp_git_repo, "add", ".")
        _git(tmp_git_repo, "commit", "-q", "-m", "init")
        (tmp_git_repo / "tracked.txt").write_text("dirty")  # pre-existing

        runs_dir = tmp_git_repo / ".git" / "agentcam" / "runs"
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "pass",
        )
        assert proc.returncode == 0
        assert not runs_dir.exists() or not any(runs_dir.iterdir())

    def test_failed_run_keeps_report_even_no_diff(self, tmp_git_repo: Path):
        # Exit != 0 means the user needs the logs to debug, even when no
        # git change. Report must be preserved.
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "import sys; sys.exit(2)",
        )
        assert proc.returncode == 1
        report = _report(tmp_git_repo)
        assert "subprocess raw returncode: 2" in report

    def test_any_change_keeps_report(self, tmp_git_repo: Path):
        # Sanity: a real change still produces a report.
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "open('hello.txt','w').write('hi')",
        )
        assert proc.returncode == 0
        report = _report(tmp_git_repo)
        assert "hello.txt" in report

    def test_keep_empty_flag_preserves_report(self, tmp_git_repo: Path):
        # --keep-empty opts out of the cleanup: report is generated even
        # for no-diff success runs.
        proc = _agentcam(
            tmp_git_repo, "run", "--keep-empty", "--",
            sys.executable, "-c", "pass",
        )
        assert proc.returncode == 0
        # _report() would raise StopIteration if no run dir existed; the
        # successful read here proves the report was kept.
        report = _report(tmp_git_repo)
        assert len(report) > 0

    def test_content_swap_preserving_status_still_detected(
        self, tmp_git_repo: Path,
    ):
        # Edge case: file is dirty pre-run with content A, agent rewrites
        # it to content B. Porcelain status is identical (" M tracked.txt"
        # in both snapshots) but content differs. The diff fingerprint
        # must distinguish them so the report is kept.
        (tmp_git_repo / "tracked.txt").write_text("committed")
        _git(tmp_git_repo, "add", ".")
        _git(tmp_git_repo, "commit", "-q", "-m", "init")
        (tmp_git_repo / "tracked.txt").write_text("dirty version A")

        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('tracked.txt','w').write('dirty version B totally different')",
        )
        assert proc.returncode == 0
        report = _report(tmp_git_repo)
        assert "tracked.txt" in report

    def test_untracked_content_swap_still_detected(self, tmp_git_repo: Path):
        # Untracked file exists pre-run with content A. Agent rewrites it
        # to content B (same path, still untracked). Porcelain says
        # "?? scratch.txt" in BOTH snapshots and `git diff` ignores
        # untracked files entirely. Without hashing untracked content in
        # the fingerprint, cleanup would falsely fire and lose the work.
        # Regression test for the Codex review hole.
        (tmp_git_repo / "scratch.txt").write_text("content A")
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('scratch.txt','w').write('content B totally different')",
        )
        assert proc.returncode == 0
        report = _report(tmp_git_repo)
        assert "scratch.txt" in report

    def test_empty_commit_kept(self, tmp_git_repo: Path):
        # An empty commit moves HEAD without changing files. head_before
        # differs from head_after → cleanup must NOT apply, report exists.
        # (Set repo-level identity so the wrapped `git commit` succeeds
        # without inheriting the test fixture's -c flags.)
        subprocess.run(
            ["git", "config", "user.email", "t@t"],
            cwd=tmp_git_repo, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "t"],
            cwd=tmp_git_repo, check=True, capture_output=True,
        )
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            "git", "commit", "--allow-empty", "-m", "empty marker",
        )
        assert proc.returncode == 0
        report = _report(tmp_git_repo)
        assert len(report) > 0


# ---------------------------------------------------------------------------
# Capture Visibility (Feature 2 / design.md #28)
# ---------------------------------------------------------------------------

class TestCaptureVisibility:
    def test_wrap_mode_records_wrap_pipe_capture(self, tmp_git_repo: Path):
        proc = _agentcam(
            tmp_git_repo, "run", "--backend", "pipe", "--",
            sys.executable, "-c", "open('hi.txt','w').write('x')",
        )
        assert proc.returncode == 0
        m = _manifest(tmp_git_repo)
        cap = m.get("capture")
        assert cap is not None, "wrap mode manifest must carry capture block"
        assert cap["mode"] == "wrap_pipe"
        assert cap["stdout"] == "captured"
        assert cap["output_risk_scan"] == "enabled"
        assert cap["network_egress"] == "not_visible"
        assert cap["empty_run_policy"] == "auto_delete_clean_no_diff"

        report = _report(tmp_git_repo)
        assert "## Capture Visibility" in report
        assert "wrap_pipe" in report

    def test_wrap_mode_keep_empty_changes_policy(self, tmp_git_repo: Path):
        proc = _agentcam(
            tmp_git_repo, "run", "--keep-empty", "--",
            sys.executable, "-c", "open('hi.txt','w').write('x')",
        )
        assert proc.returncode == 0
        cap = _manifest(tmp_git_repo)["capture"]
        assert cap["empty_run_policy"] == "keep_empty_requested"


# ---------------------------------------------------------------------------
# Ruleset provenance (Feature 4 / design.md #29)
# ---------------------------------------------------------------------------

class TestRulesetProvenance:
    def test_wrap_mode_manifest_has_ruleset_block(self, tmp_git_repo: Path):
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "open('hi.txt','w').write('x')",
        )
        assert proc.returncode == 0
        rs = _manifest(tmp_git_repo).get("ruleset")
        assert rs is not None, "wrap mode manifest must carry ruleset block"
        assert rs["builtin_ruleset_id"] == "agentcam-default"
        assert rs["load_status"] == "builtin_only"
        assert rs["custom_rules_path"] is None
        assert rs["merged_rules_sha256"].startswith("sha256:")

        report = _report(tmp_git_repo)
        assert "## Scanner Ruleset" in report
        assert "agentcam-default" in report


# ---------------------------------------------------------------------------
# No-diff preservation when output risk evidence exists
# (Feature 6 / design.md #30)
# ---------------------------------------------------------------------------

class TestNoDiffPreservation:
    """The default no-diff cleanup deletes clean pure-alignment runs, but
    a no-diff run that emitted an output-risk pattern (`rm -rf`, `git
    push --force`, etc.) must be preserved -- the user needs to know
    the agent printed something dangerous, even though it didn't land
    in the working tree."""

    def test_no_diff_with_output_risk_preserved(self, tmp_git_repo: Path):
        # Agent makes NO git-visible change but prints a high-risk
        # output pattern. Pre-Feature-6 this would be auto-deleted as
        # a clean no-diff. Post-Feature-6 it must be preserved.
        runs_dir = tmp_git_repo / ".git" / "agentcam" / "runs"
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "print('about to git reset --hard origin/main if you say so')",
        )
        assert proc.returncode == 0
        # Run dir must exist with a report.
        assert runs_dir.exists() and any(runs_dir.iterdir()), (
            "no-diff run with output risk flags must be preserved"
        )
        report = _report(tmp_git_repo)
        assert "git reset --hard" in report  # the rule label
        # capture metadata records the preservation reason.
        cap = _manifest(tmp_git_repo)["capture"]
        assert cap["empty_run_policy"] == "preserve_visible_risk"
        # Report explains the preservation in human terms.
        assert "preserve_visible_risk" in report or "output risk" in report

    def test_clean_no_diff_still_auto_deleted(self, tmp_git_repo: Path):
        # Regression: pure-alignment, no risk patterns → still deleted.
        runs_dir = tmp_git_repo / ".git" / "agentcam" / "runs"
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c", "print('hello world')",
        )
        assert proc.returncode == 0
        assert not runs_dir.exists() or not any(runs_dir.iterdir())

    def test_keep_empty_still_kept_and_policy_overrides(
        self, tmp_git_repo: Path,
    ):
        # --keep-empty wins regardless of risk evidence. Policy label
        # is keep_empty_requested, not preserve_visible_risk.
        proc = _agentcam(
            tmp_git_repo, "run", "--keep-empty", "--",
            sys.executable, "-c", "print('git push --force or so')",
        )
        assert proc.returncode == 0
        cap = _manifest(tmp_git_repo)["capture"]
        assert cap["empty_run_policy"] == "keep_empty_requested"


# ---------------------------------------------------------------------------
# Stage 4: `agentcam run --backend` flag (roadmap §2)
# ---------------------------------------------------------------------------

class TestBackendFlag:
    """``agentcam run --backend X`` selects the wrap backend.

    Default is ``pty`` which auto-picks ``pty_posix`` on POSIX or
    ``pty_windows`` on Windows. The capture metadata reflects the
    resolved backend so reports indicate which observation surface
    was active.
    """

    def test_default_backend_is_platform_pty(self, tmp_git_repo: Path):
        import platform as _platform
        proc = _agentcam(
            tmp_git_repo, "run", "--keep-empty", "--",
            sys.executable, "-c", "print('default-pty')",
        )
        assert proc.returncode == 0
        m = json.loads(
            (_run_dir(tmp_git_repo) / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        expected = (
            "wrap_pty_windows"
            if _platform.system().lower() == "windows"
            else "wrap_pty_posix"
        )
        assert m["capture"]["mode"] == expected

    def test_explicit_backend_pipe(self, tmp_git_repo: Path):
        proc = _agentcam(
            tmp_git_repo, "run", "--keep-empty", "--backend", "pipe", "--",
            sys.executable, "-c", "print('pipe-explicit')",
        )
        assert proc.returncode == 0
        m = json.loads(
            (_run_dir(tmp_git_repo) / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert m["capture"]["mode"] == "wrap_pipe"

    def test_explicit_backend_pty_alias_expands(self, tmp_git_repo: Path):
        # ``--backend pty`` resolves to the platform-specific backend so
        # users can write one cross-platform invocation.
        import platform as _platform
        proc = _agentcam(
            tmp_git_repo, "run", "--keep-empty", "--backend", "pty", "--",
            sys.executable, "-c", "print('pty-alias')",
        )
        assert proc.returncode == 0
        m = json.loads(
            (_run_dir(tmp_git_repo) / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        expected = (
            "wrap_pty_windows"
            if _platform.system().lower() == "windows"
            else "wrap_pty_posix"
        )
        assert m["capture"]["mode"] == expected
