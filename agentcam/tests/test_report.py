"""Tests for agentbox.report.

Covers plan §5 (four rollback wording cases), §9 (Exit Code Detail), §10
(manifest schema), §11 (report-wide redaction surface).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agentbox.models import (
    ChangedFile,
    ExitDetail,
    GitState,
    RunManifest,
    RunPaths,
)
from agentbox.report import render_report, serialize_manifest, write_manifest


def _empty_state(*, dirty: bool = False) -> GitState:
    files = (
        [ChangedFile(path="dirty.txt", status="unstaged_modified")]
        if dirty else []
    )
    return GitState(
        head="abc123",
        branch="main",
        is_detached_head=False,
        porcelain_raw=b"",
        diff_stat="",
        diff_stat_cached="",
        diff_name_status="",
        diff_name_status_cached="",
        diff_check="",
        diff_check_cached="",
        pre_existing_op=None,
        changed_files=files,
    )


def _state_with(*files: ChangedFile, **kw) -> GitState:
    return GitState(
        head=kw.get("head", "def456"),
        branch=kw.get("branch", "main"),
        is_detached_head=False,
        porcelain_raw=b"",
        diff_stat=kw.get("diff_stat", ""),
        diff_stat_cached=kw.get("diff_stat_cached", ""),
        diff_name_status=kw.get("diff_name_status", ""),
        diff_name_status_cached=kw.get("diff_name_status_cached", ""),
        diff_check=kw.get("diff_check", ""),
        diff_check_cached=kw.get("diff_check_cached", ""),
        pre_existing_op=None,
        changed_files=list(files),
    )


def _paths(tmp_path: Path) -> RunPaths:
    # Mirror production layout: <git_root>/.git/agentbox/runs/<run_id>/
    base = tmp_path / ".git" / "agentbox" / "runs" / "20260516-213055-742-test"
    base.mkdir(parents=True, exist_ok=True)
    return RunPaths(
        run_dir=str(base),
        manifest_json=str(base / "manifest.json"),
        report_md=str(base / "AGENT_RUN_REPORT.md"),
        stdout_raw=str(base / "stdout.log"),
        stderr_raw=str(base / "stderr.log"),
        stdout_redacted=str(base / "stdout.redacted.log"),
        stderr_redacted=str(base / "stderr.redacted.log"),
    )


def _manifest(
    tmp_path: Path,
    *,
    pre_run_dirty: bool = False,
    exit_detail: ExitDetail | None = None,
    argv_raw: list[str] | None = None,
    argv_red: list[str] | None = None,
) -> RunManifest:
    if exit_detail is None:
        exit_detail = ExitDetail(
            wrapper_exit=0,
            raw_returncode=0,
            raw_returncode_hex=None,
            platform="linux",
            interpretation="success",
            interpretation_source="known_table",
        )
    return RunManifest(
        schema_version="0.1",
        run_id="20260516-213055-742-test",
        started_at=datetime(
            2026, 5, 16, 21, 30, 55, 742000, tzinfo=timezone.utc
        ),
        ended_at=datetime(
            2026, 5, 16, 21, 33, 11, 103000, tzinfo=timezone.utc
        ),
        duration_seconds=135.361,
        cwd=str(tmp_path),
        git_root=str(tmp_path),
        git_dir=str(tmp_path / ".git"),
        branch="main",
        is_detached_head=False,
        head_before="abc123",
        head_after="def456",
        pre_existing_op=None,
        pre_run_dirty=pre_run_dirty,
        command_argv_raw=argv_raw or ["python", "-c", "pass"],
        command_argv_redacted=argv_red or ["python", "-c", "pass"],
        exit_detail=exit_detail,
        shell_used=False,
        terminal_forward_degraded=False,
        platform="linux",
        agentbox_version="0.1.0",
        paths=_paths(tmp_path),
    )


# ---------------------------------------------------------------------------
# Rollback wording (plan §5 — four cases)
# ---------------------------------------------------------------------------

class TestRollback:
    def test_case_clean_no_untracked(self, tmp_path: Path):
        m = _manifest(tmp_path, pre_run_dirty=False)
        after = _state_with(
            ChangedFile(path="a.py", status="unstaged_modified")
        )
        report = render_report(m, _empty_state(), after, [])
        assert "git restore --staged ." in report
        assert "git restore ." in report
        assert "No untracked files were created" in report

    def test_case_clean_with_untracked_warns(self, tmp_path: Path):
        m = _manifest(tmp_path, pre_run_dirty=False)
        after = _state_with(
            ChangedFile(path="new.py", status="untracked"),
            ChangedFile(path="other.py", status="unstaged_modified"),
        )
        report = render_report(m, _empty_state(), after, [])
        assert "new.py" in report
        assert "NOT removed" in report
        assert "git clean -fd" in report  # the warning line

    def test_case_dirty_no_blanket_rollback(self, tmp_path: Path):
        m = _manifest(tmp_path, pre_run_dirty=True)
        report = render_report(m, _empty_state(dirty=True),
                               _empty_state(dirty=True), [])
        assert "Manual review required" in report
        assert "git restore --staged ." not in report

    def test_case_failed_unchanged_no_rollback_section(self, tmp_path: Path):
        ed = ExitDetail(
            wrapper_exit=1, raw_returncode=2, raw_returncode_hex=None,
            platform="linux",
            interpretation="subprocess exited with user-defined non-zero code",
            interpretation_source="user_defined",
        )
        m = _manifest(tmp_path, exit_detail=ed)
        report = render_report(m, _empty_state(), _empty_state(), [])
        assert "no rollback needed" in report.lower()


# ---------------------------------------------------------------------------
# Exit Code Detail (plan §9)
# ---------------------------------------------------------------------------

class TestExitCodeDetail:
    def test_known_ntstatus_visible(self, tmp_path: Path):
        ed = ExitDetail(
            wrapper_exit=1, raw_returncode=0xC0000005,
            raw_returncode_hex="0xc0000005", platform="windows",
            interpretation="STATUS_ACCESS_VIOLATION",
            interpretation_source="known_table",
        )
        report = render_report(
            _manifest(tmp_path, exit_detail=ed),
            _empty_state(), _empty_state(), [],
        )
        assert "STATUS_ACCESS_VIOLATION" in report
        assert "0xc0000005" in report
        assert "interpretation source: known_table" in report

    def test_unknown_returncode_includes_disclaimer(self, tmp_path: Path):
        ed = ExitDetail(
            wrapper_exit=1, raw_returncode=0x12345678,
            raw_returncode_hex="0x12345678", platform="windows",
            interpretation="unknown high returncode",
            interpretation_source="unknown",
        )
        report = render_report(
            _manifest(tmp_path, exit_detail=ed),
            _empty_state(), _empty_state(), [],
        )
        assert "0x12345678" in report
        assert "NTSTATUS" in report  # disclaimer mentions NTSTATUS table


# ---------------------------------------------------------------------------
# Report-wide redaction (plan §11)
# ---------------------------------------------------------------------------

class TestReportRedaction:
    def test_command_uses_redacted_argv(self, tmp_path: Path):
        m = _manifest(
            tmp_path,
            argv_raw=["claude", "--api-key", "sk-AAAAAAAAAAAAAAAAAAAA"],
            argv_red=["claude", "--api-key", "[REDACTED:LLM_API_KEY]"],
        )
        report = render_report(m, _empty_state(), _empty_state(), [])
        assert "sk-AAAA" not in report
        assert "[REDACTED:LLM_API_KEY]" in report

    def test_secret_filename_redacted_in_changed_files(self, tmp_path: Path):
        after = _state_with(
            ChangedFile(path=".env.production", status="unstaged_modified"),
        )
        report = render_report(
            _manifest(tmp_path), _empty_state(), after, [],
        )
        assert ".env.production" not in report
        assert "<redacted-secret-filename>" in report

    def test_secret_filename_redacted_in_diff_stat(self, tmp_path: Path):
        diff = " .env.production | 1 +\n 1 file changed, 1 insertion(+)"
        after = _state_with(diff_stat=diff)
        report = render_report(
            _manifest(tmp_path), _empty_state(), after, [],
        )
        assert ".env.production" not in report
        assert "<redacted-secret-filename>" in report

    def test_normal_filename_visible_in_diff_stat(self, tmp_path: Path):
        diff = " src/main.py | 5 +-\n 1 file changed, 3 insertions(+), 2 deletions(-)"
        after = _state_with(diff_stat=diff)
        report = render_report(
            _manifest(tmp_path), _empty_state(), after, [],
        )
        assert "src/main.py" in report

    def test_internal_path_excluded_from_changed_files(self, tmp_path: Path):
        after = _state_with(
            ChangedFile(
                path=".git/agentbox/runs/20260516-x/stdout.log",
                status="untracked",
            ),
            ChangedFile(path="real.py", status="unstaged_modified"),
        )
        report = render_report(
            _manifest(tmp_path), _empty_state(), after, [],
        )
        # Check only the Changed Files section. The Logs / Local Artifacts
        # sections legitimately reference `.git/agentbox/runs/.../...` for
        # *this* run's own outputs.
        changed_section = report.split("## Changed Files")[1].split("\n## ")[0]
        assert "stdout.log" not in changed_section
        assert "real.py" in changed_section


# ---------------------------------------------------------------------------
# Manifest serialization (plan §10)
# ---------------------------------------------------------------------------

class TestManifestSerialization:
    def test_serialize_to_dict(self, tmp_path: Path):
        m = _manifest(tmp_path)
        d = serialize_manifest(m)
        # Round-trip via json to confirm it's serializable.
        loaded = json.loads(json.dumps(d))
        assert loaded["run_id"] == m.run_id
        assert loaded["schema_version"] == "0.1"
        assert loaded["exit_detail"]["wrapper_exit"] == 0
        assert loaded["paths"]["report_md"].endswith("AGENT_RUN_REPORT.md")

    def test_write_manifest(self, tmp_path: Path):
        m = _manifest(tmp_path)
        out = tmp_path / "manifest.json"
        write_manifest(m, out)
        assert out.is_file()
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["run_id"] == m.run_id

    def test_serialized_redacted_argv_in_manifest(self, tmp_path: Path):
        m = _manifest(
            tmp_path,
            argv_raw=["claude", "--api-key", "sk-AAAAAAAAAAAAAAAAAAAA"],
            argv_red=["claude", "--api-key", "[REDACTED:LLM_API_KEY]"],
        )
        d = serialize_manifest(m)
        # Manifest keeps both raw and redacted (plan §10).
        assert d["command_argv_raw"][2] == "sk-AAAAAAAAAAAAAAAAAAAA"
        assert d["command_argv_redacted"][2] == "[REDACTED:LLM_API_KEY]"


# ---------------------------------------------------------------------------
# Verdict overall
# ---------------------------------------------------------------------------

class TestVerdict:
    def test_no_flags_low(self, tmp_path: Path):
        report = render_report(
            _manifest(tmp_path), _empty_state(), _empty_state(), [],
        )
        assert "LOW" in report
        assert "Human review required: no" in report

    def test_high_flag_promotes(self, tmp_path: Path):
        from agentbox.models import RiskFlag
        flags = [RiskFlag(level="HIGH", rule="auth path", evidence="x")]
        report = render_report(
            _manifest(tmp_path), _empty_state(), _empty_state(), flags,
        )
        assert "**HIGH**" in report
        assert "Human review required: yes" in report


# ---------------------------------------------------------------------------
# Codex source-review CRITICAL regressions (added 2026-05-16)
# ---------------------------------------------------------------------------

class TestCriticalSecretLeakRegressions:
    """Codex source-review CRITICAL: every markdown surface must redact
    secret-like filenames (plan §11, design.md §12).
    """

    def test_renamed_from_secret_filename_redacted(self, tmp_path: Path):
        # Bug: report.py used cf.rename_from raw, leaking the old name
        # even when it was secret-like.
        after = _state_with(
            ChangedFile(
                path="config.txt",
                status="renamed",
                rename_from=".env.production",
            ),
        )
        report = render_report(
            _manifest(tmp_path), _empty_state(), after, [],
        )
        assert ".env.production" not in report

    def test_diff_check_unstaged_redacts_filename(self, tmp_path: Path):
        # `git diff --check` lines look like:
        #   <path>:<line>: <message>
        # The path was being concatenated raw into markdown. If it's
        # secret-like, the filename leaks.
        diff_check = ".env.production:5: trailing whitespace.\n"
        after = _state_with(diff_check=diff_check)
        report = render_report(
            _manifest(tmp_path), _empty_state(), after, [],
        )
        assert ".env.production" not in report

    def test_diff_check_cached_redacts_filename(self, tmp_path: Path):
        diff_check_cached = "config-secrets.yaml:1: indent with spaces.\n"
        after = _state_with(diff_check_cached=diff_check_cached)
        report = render_report(
            _manifest(tmp_path), _empty_state(), after, [],
        )
        assert "config-secrets.yaml" not in report


class TestHighAbsolutePathLeak:
    """Codex source-review HIGH: report must not echo absolute paths
    that leak username / repo location. Paths shown relative to git_root.
    """

    def test_report_does_not_contain_absolute_tmp_path(self, tmp_path: Path):
        m = _manifest(tmp_path)  # tmp_path is git_root
        report = render_report(m, _empty_state(), _empty_state(), [])
        # tmp_path on Windows looks like
        # C:\Users\<user>\AppData\Local\Temp\pytest-of-<user>\... — the
        # username segment must not appear in the user-shareable report.
        assert str(tmp_path) not in report
        assert str(tmp_path).replace("\\", "/") not in report

    def test_report_uses_relative_paths_for_logs_and_artifacts(self, tmp_path: Path):
        m = _manifest(tmp_path)
        report = render_report(m, _empty_state(), _empty_state(), [])
        # The redacted-log path should be shown as a relative POSIX-style
        # path under .git/agentbox/runs/, not the absolute version.
        assert ".git/agentbox/runs" in report
