"""End-to-end tests for the Claude Code hooks integration.

Two new CLI subcommands, both read JSON from stdin (Claude Code's hook
payload) and both exit 0 unconditionally so the user's session is never
blocked:

  - ``agentcam hook-session-start`` — snapshot git state on SessionStart,
    persist to ``<git_dir>/agentcam/sessions/<session_id>/``
  - ``agentcam hook-session-end`` — compare to the persisted state, render
    a report under ``runs/<run_id>/`` if there's a diff, then clean up
    the session dir (same no-diff cleanup semantics as the wrapping path)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _agentcam_hook(
    cwd: Path,
    subcommand: str,
    payload: dict | None,
    *,
    raw_stdin: bytes | None = None,
) -> subprocess.CompletedProcess:
    """Invoke an agentcam hook subcommand with JSON on stdin.

    If ``raw_stdin`` is given it overrides ``payload`` (used to test
    bad-input handling).
    """
    if raw_stdin is None:
        raw_stdin = json.dumps(payload or {}).encode()
    return subprocess.run(
        [sys.executable, "-m", "agentcam.cli", subcommand],
        cwd=cwd,
        capture_output=True,
        timeout=25,
        input=raw_stdin,
    )


def _session_dir(repo: Path, session_id: str) -> Path:
    return repo / ".git" / "agentcam" / "sessions" / session_id


def _runs_dir(repo: Path) -> Path:
    return repo / ".git" / "agentcam" / "runs"


def _first_run(repo: Path) -> Path:
    return next(_runs_dir(repo).iterdir())


def _hook_payload(session_id: str, cwd: Path, event: str) -> dict:
    return {
        "session_id": session_id,
        "cwd": str(cwd),
        "hook_event_name": event,
        "transcript_path": "/tmp/fake.jsonl",
        "permission_mode": "default",
    }


# ---------------------------------------------------------------------------
# SessionStart
# ---------------------------------------------------------------------------

class TestSessionStart:
    def test_persists_state_before(self, tmp_git_repo: Path):
        sid = "test-session-1"
        payload = _hook_payload(sid, tmp_git_repo, "SessionStart")
        proc = _agentcam_hook(tmp_git_repo, "hook-session-start", payload)
        assert proc.returncode == 0
        sdir = _session_dir(tmp_git_repo, sid)
        assert sdir.exists(), "session dir should be created on SessionStart"
        assert (sdir / "state_before.pickle").exists(), (
            "state_before snapshot file should exist after SessionStart"
        )

    def test_not_in_git_repo_silent_noop(self, tmp_path: Path):
        sid = "test-session-2"
        payload = _hook_payload(sid, tmp_path, "SessionStart")
        proc = _agentcam_hook(tmp_path, "hook-session-start", payload)
        # Hook never blocks Claude Code — always exit 0.
        assert proc.returncode == 0
        # No agentcam state created when not in a git repo.
        assert not (tmp_path / ".git" / "agentcam").exists()

    def test_bad_stdin_silent_noop(self, tmp_git_repo: Path):
        proc = _agentcam_hook(
            tmp_git_repo, "hook-session-start", None,
            raw_stdin=b"not json at all",
        )
        assert proc.returncode == 0
        # Nothing should have been written.
        sessions = tmp_git_repo / ".git" / "agentcam" / "sessions"
        assert not sessions.exists() or not any(sessions.iterdir())

    def test_empty_stdin_silent_noop(self, tmp_git_repo: Path):
        proc = _agentcam_hook(
            tmp_git_repo, "hook-session-start", None,
            raw_stdin=b"",
        )
        assert proc.returncode == 0
        sessions = tmp_git_repo / ".git" / "agentcam" / "sessions"
        assert not sessions.exists() or not any(sessions.iterdir())

    def test_session_id_with_path_traversal_is_sanitized(
        self, tmp_git_repo: Path,
    ):
        # Adversarial session_id — must not escape the sessions/ directory.
        evil_sid = "../../../etc/passwd"
        payload = _hook_payload(evil_sid, tmp_git_repo, "SessionStart")
        proc = _agentcam_hook(tmp_git_repo, "hook-session-start", payload)
        assert proc.returncode == 0
        # The dangerous path must NOT have been created.
        assert not (tmp_git_repo / ".git" / "agentcam" / "sessions" / ".." / ".." / ".." / "etc").exists()
        # The sanitized session dir SHOULD exist somewhere under sessions/.
        sessions = tmp_git_repo / ".git" / "agentcam" / "sessions"
        assert sessions.exists()
        # Whatever directory was created must be a direct child of sessions/.
        children = list(sessions.iterdir())
        assert len(children) == 1
        assert children[0].parent == sessions


# ---------------------------------------------------------------------------
# SessionEnd
# ---------------------------------------------------------------------------

class TestSessionEnd:
    def test_diff_produces_report(self, tmp_git_repo: Path):
        sid = "test-session-3"
        start_payload = _hook_payload(sid, tmp_git_repo, "SessionStart")
        _agentcam_hook(tmp_git_repo, "hook-session-start", start_payload)

        # Simulate work happening during the session.
        (tmp_git_repo / "agent_made_this.txt").write_text("hi from agent")

        end_payload = _hook_payload(sid, tmp_git_repo, "SessionEnd")
        proc = _agentcam_hook(tmp_git_repo, "hook-session-end", end_payload)
        assert proc.returncode == 0

        # A run dir should exist under runs/ with a report.
        runs = _runs_dir(tmp_git_repo)
        assert runs.exists() and any(runs.iterdir())
        report = (_first_run(tmp_git_repo) / "AGENT_RUN_REPORT.md").read_text(
            encoding="utf-8",
        )
        assert "agent_made_this.txt" in report
        # The "command" field should identify this as a Claude session.
        assert "claude" in report.lower() or "session" in report.lower()

        # Session dir should be cleaned up after SessionEnd.
        assert not _session_dir(tmp_git_repo, sid).exists()

    def test_no_diff_cleans_up_no_report(self, tmp_git_repo: Path):
        sid = "test-session-4"
        start_payload = _hook_payload(sid, tmp_git_repo, "SessionStart")
        _agentcam_hook(tmp_git_repo, "hook-session-start", start_payload)
        # No work happens.
        end_payload = _hook_payload(sid, tmp_git_repo, "SessionEnd")
        proc = _agentcam_hook(tmp_git_repo, "hook-session-end", end_payload)
        assert proc.returncode == 0

        # No run dir — pure-alignment cleanup applies.
        runs = _runs_dir(tmp_git_repo)
        assert not runs.exists() or not any(runs.iterdir())
        # Session dir also cleaned up.
        assert not _session_dir(tmp_git_repo, sid).exists()

    def test_no_prior_session_start_silent_noop(self, tmp_git_repo: Path):
        sid = "test-session-5"
        end_payload = _hook_payload(sid, tmp_git_repo, "SessionEnd")
        proc = _agentcam_hook(tmp_git_repo, "hook-session-end", end_payload)
        assert proc.returncode == 0
        runs = _runs_dir(tmp_git_repo)
        assert not runs.exists() or not any(runs.iterdir())

    def test_not_in_git_repo_silent_noop(self, tmp_path: Path):
        sid = "test-session-6"
        end_payload = _hook_payload(sid, tmp_path, "SessionEnd")
        proc = _agentcam_hook(tmp_path, "hook-session-end", end_payload)
        assert proc.returncode == 0
        assert not (tmp_path / ".git" / "agentcam").exists()

    def test_bad_stdin_silent_noop(self, tmp_git_repo: Path):
        proc = _agentcam_hook(
            tmp_git_repo, "hook-session-end", None,
            raw_stdin=b"garbage",
        )
        assert proc.returncode == 0
        runs = _runs_dir(tmp_git_repo)
        assert not runs.exists() or not any(runs.iterdir())

    def test_session_id_mismatch_silent_noop(self, tmp_git_repo: Path):
        # SessionStart for sid_a; SessionEnd for sid_b -> no matching state_before
        sid_a = "session-A"
        sid_b = "session-B"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid_a, tmp_git_repo, "SessionStart"),
        )
        # Modify state (would normally produce a report)
        (tmp_git_repo / "modified.txt").write_text("x")
        proc = _agentcam_hook(
            tmp_git_repo, "hook-session-end",
            _hook_payload(sid_b, tmp_git_repo, "SessionEnd"),
        )
        assert proc.returncode == 0
        # No run dir — there was no matching SessionStart for sid_b.
        runs = _runs_dir(tmp_git_repo)
        assert not runs.exists() or not any(runs.iterdir())
        # sid_a's session dir is still there (it's orphaned, but
        # SessionEnd for B shouldn't touch A's data).
        assert _session_dir(tmp_git_repo, sid_a).exists()


# ---------------------------------------------------------------------------
# Round-1 Codex regressions
# ---------------------------------------------------------------------------

class TestCodexR1Regressions:
    def test_duplicate_session_start_preserves_first_snapshot(
        self, tmp_git_repo: Path,
    ):
        # Resume / clear / compact fire SessionStart again. The second
        # SessionStart MUST NOT overwrite the first snapshot, otherwise
        # any changes made between the two would silently disappear
        # from the eventual SessionEnd report.
        sid = "session-duplicate-start"

        # First SessionStart, clean tree.
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        # Capture mtime of the first snapshot file so we can detect
        # whether the second SessionStart overwrites it.
        state_file = _session_dir(tmp_git_repo, sid) / "state_before.pickle"
        assert state_file.exists()
        first_mtime_ns = state_file.stat().st_mtime_ns

        # Agent changes a file.
        (tmp_git_repo / "first_change.txt").write_text("first")

        # Second SessionStart -- should be a no-op (preserve first).
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        second_mtime_ns = state_file.stat().st_mtime_ns
        assert first_mtime_ns == second_mtime_ns, (
            "second SessionStart for the same session id must preserve "
            "the original snapshot; mtime should be unchanged"
        )

        # More agent work.
        (tmp_git_repo / "second_change.txt").write_text("second")

        # SessionEnd -- the report should reflect the diff against the
        # FIRST snapshot, so BOTH files appear.
        _agentcam_hook(
            tmp_git_repo, "hook-session-end",
            _hook_payload(sid, tmp_git_repo, "SessionEnd"),
        )
        report = (_first_run(tmp_git_repo) / "AGENT_RUN_REPORT.md").read_text(
            encoding="utf-8",
        )
        assert "first_change.txt" in report, (
            "change made between the two SessionStarts must appear in "
            "the report (proves first snapshot was preserved)"
        )
        assert "second_change.txt" in report

    def test_corrupted_state_before_cleans_up(self, tmp_git_repo: Path):
        # SessionStart, then corrupt the snapshot, then SessionEnd.
        # SessionEnd must silently no-op AND clean up the session dir,
        # not leak an orphan that would poison every future SessionEnd
        # for that session id.
        sid = "session-corrupted"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        sdir = _session_dir(tmp_git_repo, sid)
        # Overwrite with garbage that pickle.load cannot parse.
        (sdir / "state_before.pickle").write_bytes(b"\xde\xad\xbe\xef not a pickle")

        # Make a change so we know "no report" is from the corruption
        # path, not the no-diff cleanup.
        (tmp_git_repo / "would_have_been_recorded.txt").write_text("x")

        proc = _agentcam_hook(
            tmp_git_repo, "hook-session-end",
            _hook_payload(sid, tmp_git_repo, "SessionEnd"),
        )
        assert proc.returncode == 0
        # No run dir produced -- snapshot was corrupted, can't compare.
        runs = _runs_dir(tmp_git_repo)
        assert not runs.exists() or not any(runs.iterdir())
        # Session dir cleaned up -- next SessionStart for same sid will
        # start fresh, not inherit the broken snapshot.
        assert not sdir.exists()

    def test_loadable_but_malformed_snapshot_cleans_up(
        self, tmp_git_repo: Path,
    ):
        # Codex round-2 regression: a pickle that LOADS successfully
        # but contains the wrong types (state="x" instead of GitState,
        # started_at="x" instead of datetime) must not slip past
        # validation. Without isinstance checks on state/started_at,
        # this would explode inside render_report and leak an orphan
        # session dir via the outer except.
        import pickle as _pickle
        sid = "session-malformed"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        sdir = _session_dir(tmp_git_repo, sid)
        # Replace with a valid pickle of WRONG-typed values.
        malformed = {
            "schema_version": "0.1",
            "session_id": sid,
            "started_at": "not a datetime at all",
            "cwd": str(tmp_git_repo),
            "git_root": str(tmp_git_repo),
            "git_dir": str(tmp_git_repo / ".git"),
            "state": "not a GitState",
            "fingerprint": "abc123",
        }
        with (sdir / "state_before.pickle").open("wb") as f:
            _pickle.dump(malformed, f)

        # Add a real change so we know "no report" is from the
        # validation path, not the no-diff cleanup.
        (tmp_git_repo / "agent_did_work.txt").write_text("x")

        proc = _agentcam_hook(
            tmp_git_repo, "hook-session-end",
            _hook_payload(sid, tmp_git_repo, "SessionEnd"),
        )
        assert proc.returncode == 0
        runs = _runs_dir(tmp_git_repo)
        assert not runs.exists() or not any(runs.iterdir())
        # Critical: session dir cleaned up, not orphaned.
        assert not sdir.exists()
