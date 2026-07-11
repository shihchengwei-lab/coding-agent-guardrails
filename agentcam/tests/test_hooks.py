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
import os
import shutil
import subprocess
import sys
import time
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


def _codex_turn_payload(session_id: str, turn_id: str, cwd: Path, event: str) -> dict:
    payload = _hook_payload(session_id, cwd, event)
    payload["turn_id"] = turn_id
    return payload


class TestCodexTurnHooks:
    def test_user_prompt_to_stop_records_one_turn(self, tmp_git_repo: Path):
        sid = "codex-session"
        turn_id = "codex-turn-1"
        start = _codex_turn_payload(sid, turn_id, tmp_git_repo, "UserPromptSubmit")
        proc = _agentcam_hook(tmp_git_repo, "hook-turn-start", start)
        assert proc.returncode == 0, proc.stderr
        assert _session_dir(tmp_git_repo, turn_id).exists()

        (tmp_git_repo / "codex-made-this.txt").write_text("changed", encoding="utf-8")
        end = _codex_turn_payload(sid, turn_id, tmp_git_repo, "Stop")
        proc = _agentcam_hook(tmp_git_repo, "hook-turn-end", end)

        assert proc.returncode == 0, proc.stderr
        assert not _session_dir(tmp_git_repo, turn_id).exists()
        run = _first_run(tmp_git_repo)
        manifest = json.loads((run / "manifest.json").read_text("utf-8"))
        assert manifest["capture"]["mode"] == "codex_hook"
        assert manifest["evidence"]["overall_risk"] == "NONE_DETECTED"
        report = (run / "AGENT_RUN_REPORT.md").read_text("utf-8")
        assert "Overall risk: **UNKNOWN**" in report

    def test_missing_turn_id_is_noop(self, tmp_git_repo: Path):
        payload = _hook_payload("codex-session", tmp_git_repo, "UserPromptSubmit")
        proc = _agentcam_hook(tmp_git_repo, "hook-turn-start", payload)
        assert proc.returncode == 0
        sessions = tmp_git_repo / ".git" / "agentcam" / "sessions"
        assert not sessions.exists() or not any(sessions.iterdir())


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


# ---------------------------------------------------------------------------
# Orphan cleanup on probe / render failure (Codex review MEDIUM #5)
# ---------------------------------------------------------------------------

class TestOrphanCleanupOnFailure:
    """If anything between create_run_dir and write_manifest raises,
    the hook must:
    1. always exit 0 (never block Claude Code)
    2. remove the half-built run dir (no orphan placeholder logs)
    3. remove the session dir (so repeated failures don't accumulate)
    """

    def test_probe_failure_cleans_run_dir_and_session_dir(
        self, tmp_git_repo: Path, monkeypatch,
    ):
        # We bypass subprocess + stdin by calling the hook entry
        # points directly with a patched _read_hook_input. This lets
        # us inject a probe failure via monkeypatch.
        from agentcam import hooks
        from agentcam import dependency_probe

        sid = "orphan-test-sid"
        payload = {"session_id": sid, "cwd": str(tmp_git_repo)}
        monkeypatch.setattr(hooks, "_read_hook_input", lambda: payload)

        # SessionStart: snapshot baseline.
        rc = hooks.cmd_hook_session_start()
        assert rc == 0
        sdir = _session_dir(tmp_git_repo, sid)
        assert sdir.exists()

        # Make a real change so SessionEnd takes the report-writing
        # branch (not the no-diff cleanup branch).
        (tmp_git_repo / "agent_did_work.txt").write_text("x\n")

        # Inject failure in the probe.
        def boom(**kw):
            raise RuntimeError("simulated probe failure")
        monkeypatch.setattr(dependency_probe, "scan_dependencies", boom)

        # SessionEnd: should swallow the error, clean both dirs.
        rc = hooks.cmd_hook_session_end()
        assert rc == 0  # hook must NEVER block Claude Code

        # Session dir gone.
        assert not sdir.exists(), (
            "session dir must be cleaned even on failure"
        )

        # Run dir either never created or already removed -- no
        # orphan placeholder logs.
        runs = _runs_dir(tmp_git_repo)
        assert not runs.exists() or not any(runs.iterdir()), (
            "run dir must not be left as orphan with placeholder logs"
        )


# ---------------------------------------------------------------------------
# Capture Visibility metadata (Feature 2 / design.md #28)
# ---------------------------------------------------------------------------

class TestCaptureVisibilityHookMode:
    def _manifest(self, repo: Path) -> dict:
        run_dir = next(_runs_dir(repo).iterdir())
        return json.loads(
            (run_dir / "manifest.json").read_text(encoding="utf-8")
        )

    def _report(self, repo: Path) -> str:
        run_dir = next(_runs_dir(repo).iterdir())
        return (run_dir / "AGENT_RUN_REPORT.md").read_text(encoding="utf-8")

    def test_hook_mode_manifest_carries_claude_hook_capture(
        self, tmp_git_repo: Path,
    ):
        sid = "test-capture-1"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        (tmp_git_repo / "made_by_agent.txt").write_text("hi")
        _agentcam_hook(
            tmp_git_repo, "hook-session-end",
            _hook_payload(sid, tmp_git_repo, "SessionEnd"),
        )
        cap = self._manifest(tmp_git_repo)["capture"]
        assert cap["mode"] == "claude_hook"
        assert cap["stdout"] == "not_available"
        assert cap["stderr"] == "not_available"
        assert cap["output_risk_scan"] == "disabled_no_output_stream"
        assert cap["path_risk_scan"] == "enabled"
        # _hook_payload() includes transcript_path="/tmp/fake.jsonl" — so
        # the capture metadata should record availability, even though
        # we don't ingest it.
        assert cap["transcript"] == "available_not_ingested"

        report = self._report(tmp_git_repo)
        assert "## Capture Visibility" in report
        assert "claude_hook" in report
        assert "disabled_no_output_stream" in report

    def test_hook_mode_without_transcript_path_marks_unknown(
        self, tmp_git_repo: Path,
    ):
        sid = "test-capture-2"
        # Build a payload that has session_id + cwd but NO transcript_path,
        # to confirm the capture block reports `transcript = "unknown"`.
        bare_start = {
            "session_id": sid,
            "cwd": str(tmp_git_repo),
            "hook_event_name": "SessionStart",
        }
        bare_end = {
            "session_id": sid,
            "cwd": str(tmp_git_repo),
            "hook_event_name": "SessionEnd",
        }
        _agentcam_hook(tmp_git_repo, "hook-session-start", bare_start)
        (tmp_git_repo / "made_by_agent.txt").write_text("hi")
        _agentcam_hook(tmp_git_repo, "hook-session-end", bare_end)
        cap = self._manifest(tmp_git_repo)["capture"]
        assert cap["transcript"] == "unknown"


# ---------------------------------------------------------------------------
# Ruleset provenance (Feature 4 / design.md #29)
# ---------------------------------------------------------------------------

class TestRulesetProvenanceHookMode:
    def _manifest(self, repo: Path) -> dict:
        run_dir = next(_runs_dir(repo).iterdir())
        return json.loads(
            (run_dir / "manifest.json").read_text(encoding="utf-8")
        )

    def test_hook_mode_manifest_has_same_ruleset_shape_as_wrap(
        self, tmp_git_repo: Path,
    ):
        sid = "test-ruleset-1"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        (tmp_git_repo / "made_by_agent.txt").write_text("hi")
        _agentcam_hook(
            tmp_git_repo, "hook-session-end",
            _hook_payload(sid, tmp_git_repo, "SessionEnd"),
        )
        rs = self._manifest(tmp_git_repo)["ruleset"]
        assert rs["builtin_ruleset_id"] == "agentcam-default"
        assert set(rs) == {
            "builtin_ruleset_id",
            "builtin_ruleset_version",
            "rules_sha256",
        }
        assert rs["rules_sha256"].startswith("sha256:")


# ---------------------------------------------------------------------------
# `agentcam verify` during an in-progress hook session
# ---------------------------------------------------------------------------

def _verify(cwd: Path, *check: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agentcam.cli", "verify", "--", *check],
        cwd=cwd,
        capture_output=True,
        timeout=25,
    )


PASS_CMD = (sys.executable, "-c", "raise SystemExit(0)")


class TestVerifyDuringSession:
    def test_verify_attaches_to_session_not_previous_run(
        self, tmp_git_repo: Path
    ):
        # A previous wrap-mode run exists — the mis-attachment target.
        proc = subprocess.run(
            [
                sys.executable, "-m", "agentcam.cli", "run",
                "--backend", "pipe", "--",
                sys.executable, "-c", "open('old.txt','w').write('x')",
            ],
            cwd=tmp_git_repo, capture_output=True, timeout=25,
        )
        assert proc.returncode == 0, proc.stderr
        old_run = next(_runs_dir(tmp_git_repo).iterdir())

        sid = "live-session"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        proc = _verify(tmp_git_repo, *PASS_CMD)
        assert proc.returncode == 0, proc.stderr
        assert b"in-progress session" in proc.stderr

        # Stashed with the session; the previous run stays untouched.
        session_records = list(
            (_session_dir(tmp_git_repo, sid) / "verifications").glob("*.json")
        )
        assert len(session_records) == 1
        old_manifest = json.loads(
            (old_run / "manifest.json").read_text(encoding="utf-8")
        )
        assert old_manifest["evidence"].get("verifications", []) == []

        # Session ends with a diff -> its run carries the check.
        (tmp_git_repo / "by_agent.txt").write_text("hi")
        _agentcam_hook(
            tmp_git_repo, "hook-session-end",
            _hook_payload(sid, tmp_git_repo, "SessionEnd"),
        )
        session_run = next(
            d for d in _runs_dir(tmp_git_repo).iterdir()
            if "claude-session" in d.name
        )
        checks = json.loads(
            (session_run / "manifest.json").read_text(encoding="utf-8")
        )["evidence"]["verifications"]
        assert len(checks) == 1
        assert checks[0]["exit_code"] == 0
        assert checks[0]["command"]

    def test_verify_works_with_no_previous_runs(
        self, tmp_git_repo: Path
    ):
        sid = "first-ever-session"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        proc = _verify(tmp_git_repo, *PASS_CMD)
        assert proc.returncode == 0, proc.stderr
        assert b"in-progress session" in proc.stderr

    def test_verify_ignores_stale_crashed_session(
        self, tmp_git_repo: Path
    ):
        """A session that started >24h ago and never ended is a crash
        leftover (SessionEnd removes live sessions on the way out);
        verify must fall back to runs/ instead of stashing checks into
        a file nothing will ever merge."""
        proc = subprocess.run(
            [
                sys.executable, "-m", "agentcam.cli", "run",
                "--backend", "pipe", "--",
                sys.executable, "-c", "open('old.txt','w').write('x')",
            ],
            cwd=tmp_git_repo, capture_output=True, timeout=25,
        )
        assert proc.returncode == 0, proc.stderr
        run_dir = next(_runs_dir(tmp_git_repo).iterdir())

        sid = "crashed-session"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        stale = _session_dir(tmp_git_repo, sid)
        past = time.time() - 25 * 3600
        os.utime(stale / "state_before.pickle", (past, past))

        proc = _verify(tmp_git_repo, *PASS_CMD)
        assert proc.returncode == 0, proc.stderr
        assert not (stale / "verifications").exists()
        checks = json.loads(
            (run_dir / "manifest.json").read_text(encoding="utf-8")
        )["evidence"]["verifications"]
        assert len(checks) == 1

    def test_no_diff_session_drops_stashed_checks(
        self, tmp_git_repo: Path
    ):
        sid = "quiet-session"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        assert _verify(tmp_git_repo, *PASS_CMD).returncode == 0
        _agentcam_hook(
            tmp_git_repo, "hook-session-end",
            _hook_payload(sid, tmp_git_repo, "SessionEnd"),
        )
        # No diff -> no run, session dir (and the stash) cleaned up.
        assert not _session_dir(tmp_git_repo, sid).exists()
        runs = _runs_dir(tmp_git_repo)
        assert not runs.exists() or not any(runs.iterdir())

    def test_corrupt_record_does_not_break_the_report(
        self, tmp_git_repo: Path
    ):
        sid = "corrupt-stash"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        assert _verify(tmp_git_repo, *PASS_CMD).returncode == 0
        records = _session_dir(tmp_git_repo, sid) / "verifications"
        (records / "corrupt.json").write_text("not json\n", encoding="utf-8")
        (tmp_git_repo / "by_agent.txt").write_text("hi")
        _agentcam_hook(
            tmp_git_repo, "hook-session-end",
            _hook_payload(sid, tmp_git_repo, "SessionEnd"),
        )
        run_dir = next(_runs_dir(tmp_git_repo).iterdir())
        checks = json.loads(
            (run_dir / "manifest.json").read_text(encoding="utf-8")
        )["evidence"]["verifications"]
        # The good record survives; the corrupt line is dropped.
        assert len(checks) == 1

    def test_verify_skips_session_being_torn_down(
        self, tmp_git_repo: Path
    ):
        """A dir renamed to *.ending is a session mid-teardown
        (claimed by SessionEnd): verify must not stash checks there,
        even when it looks newer than the live session."""
        sid = "live-a"
        _agentcam_hook(
            tmp_git_repo, "hook-session-start",
            _hook_payload(sid, tmp_git_repo, "SessionStart"),
        )
        live = _session_dir(tmp_git_repo, sid)
        ending = live.parent / "old-b.ending"
        shutil.copytree(live, ending)
        future = time.time() + 300
        os.utime(ending / "state_before.pickle", (future, future))

        proc = _verify(tmp_git_repo, *PASS_CMD)
        assert proc.returncode == 0, proc.stderr
        assert b"live-a" in proc.stderr
        assert any((live / "verifications").glob("*.json"))
        assert not (ending / "verifications").exists()
