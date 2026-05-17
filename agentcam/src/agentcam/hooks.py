"""Claude Code hooks: SessionStart / SessionEnd integration.

The wrapping path (``agentcam run -- ...``) records one session per
invocation; the user has to remember to type ``cr "task"`` for every
recording. The hooks path records every Claude Code session
automatically via ``~/.claude/settings.json`` wiring, with no command
memorization required.

Settings.json wiring (one-time setup, e.g. ``~/.claude/settings.json``)::

    {
      "hooks": {
        "SessionStart": [{"matcher": "", "hooks": [
          {"type": "command", "command": "agentcam hook-session-start"}
        ]}],
        "SessionEnd": [{"matcher": "", "hooks": [
          {"type": "command", "command": "agentcam hook-session-end"}
        ]}]
      }
    }

Both hook commands read the Claude Code hook payload JSON from stdin
and extract ``session_id`` + ``cwd``. Both exit 0 unconditionally
(never block Claude Code, even on internal errors).

State storage:
``<git_dir>/agentcam/sessions/<sanitized-session-id>/state_before.pickle``
— pickle is used because :class:`GitState` contains bytes and nested
dataclasses; JSON would need a custom serializer for each. Files are
local-only under ``.git/`` (same trust model as the rest of agentcam's
artifacts: if the attacker can write here, they already own the user).

The session dir is removed on SessionEnd whether or not a report is
generated. If SessionEnd never fires (Claude Code crash), the session
dir is left orphaned — orphan cleanup is a future improvement.
"""
from __future__ import annotations

import json
import os
import pickle
import platform as _platform
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from agentcam import __version__

# Snapshot schema version. Bump when changing the persisted dict shape so
# stale snapshots from older agentcam versions are detected on load and
# silently discarded instead of producing a broken report.
_SNAPSHOT_SCHEMA_VERSION = "0.1"

# Cap on the on-disk session id length and character set. Defends
# against path traversal (``..``) and exotic filesystems.
_SESSION_ID_MAX_LEN = 64
_SESSION_ID_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")


# ---------------------------------------------------------------------------
# Stdin / payload helpers
# ---------------------------------------------------------------------------

def _read_hook_input() -> dict | None:
    """Read JSON payload from stdin. Return None on any parse error.

    Claude Code pipes a single JSON object on stdin. We accept anything
    that decodes to a dict; everything else returns None so the caller
    can silently no-op.
    """
    try:
        data = sys.stdin.buffer.read()
    except OSError:
        return None
    if not data:
        return None
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _extract_session(payload: dict) -> tuple[str, Path] | None:
    """Extract (session_id, cwd) from a hook payload.

    Returns None if either is missing or empty. The session_id is kept
    raw (sanitization happens at the filesystem boundary, not here).
    """
    sid = payload.get("session_id")
    cwd_str = payload.get("cwd")
    if not isinstance(sid, str) or not sid:
        return None
    if not isinstance(cwd_str, str) or not cwd_str:
        return None
    return sid, Path(cwd_str)


def _safe_session_id(sid: str) -> str:
    """Sanitize a session id for use as a directory name.

    Replaces anything outside [a-zA-Z0-9_-] with '_', caps length. The
    resulting name is always a single path segment — no '..' traversal,
    no slashes, no NUL bytes, no shell metacharacters.
    """
    safe = _SESSION_ID_SAFE_RE.sub("_", sid)[:_SESSION_ID_MAX_LEN]
    return safe or "unknown_session"


def _short_sid(sid: str) -> str:
    """First 8 chars of the sanitized session id, for run-id slug use."""
    return _safe_session_id(sid)[:8] or "session"


# ---------------------------------------------------------------------------
# Subcommand entry points (called from cli.py)
# ---------------------------------------------------------------------------

def cmd_hook_session_start() -> int:
    """SessionStart hook: snapshot git state, persist for SessionEnd.

    Exit code is always 0 — Claude Code must not be blocked even on
    internal errors. Failures here mean "no report will be generated
    for this session", which is degraded but acceptable.
    """
    try:
        return _do_session_start()
    except Exception:  # noqa: BLE001 — never crash Claude Code
        return 0


def _do_session_start() -> int:
    from agentcam.git_state import (
        NotAGitRepoError,
        collect_git_state,
        compute_diff_fingerprint,
        resolve_git_dir,
        resolve_git_root,
    )

    payload = _read_hook_input()
    if payload is None:
        return 0
    extracted = _extract_session(payload)
    if extracted is None:
        return 0
    session_id, cwd = extracted

    if not cwd.exists():
        return 0

    try:
        git_dir = resolve_git_dir(cwd)
        git_root = resolve_git_root(cwd)
        state = collect_git_state(cwd, is_after=False)
        fingerprint = compute_diff_fingerprint(cwd)
    except NotAGitRepoError:
        return 0
    except (OSError, RuntimeError, FileNotFoundError):
        return 0

    started_at = datetime.now(timezone.utc).astimezone()
    session_dir = git_dir / "agentcam" / "sessions" / _safe_session_id(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    state_file = session_dir / "state_before.pickle"
    # Duplicate SessionStart for the same session_id (resume, clear,
    # compact) MUST NOT overwrite the original baseline -- otherwise
    # any changes made before the duplicate would silently disappear
    # from the eventual SessionEnd report. Preserve first.
    if state_file.exists():
        return 0

    snapshot = {
        "schema_version": _SNAPSHOT_SCHEMA_VERSION,
        "session_id": session_id,
        "started_at": started_at,
        "cwd": str(cwd),
        "git_root": str(git_root),
        "git_dir": str(git_dir),
        "state": state,
        "fingerprint": fingerprint,
    }
    # NOTE: pickle is acceptable here -- files live under .git/agentcam/
    # which is local-only and write-controlled by the user. Same trust
    # model as the existing stdout.log / manifest.json artifacts.
    # Atomic write: dump to .tmp then os.replace, so SessionEnd can
    # never see a half-written pickle if it fires mid-write.
    tmp_path = session_dir / "state_before.pickle.tmp"
    with tmp_path.open("wb") as f:
        pickle.dump(snapshot, f)
    os.replace(tmp_path, state_file)

    return 0


def cmd_hook_session_end() -> int:
    """SessionEnd hook: compare against the persisted SessionStart
    snapshot, render a report if there's a diff, then clean up the
    session dir."""
    try:
        return _do_session_end()
    except Exception:  # noqa: BLE001
        # Don't crash Claude Code on agentcam bugs. Emit one stderr
        # line so the user can see something happened if they're
        # looking -- but the print itself might raise if stderr is
        # closed/broken, so guard that too.
        try:
            print(
                "agentcam: hook-session-end failed silently (internal error)",
                file=sys.stderr,
            )
        except Exception:  # noqa: BLE001
            pass
        return 0


def _do_session_end() -> int:
    from agentcam.git_state import (
        NotAGitRepoError,
        collect_git_state,
        compute_diff_fingerprint,
        resolve_git_dir,
    )
    from agentcam.models import RunManifest
    from agentcam.paths import create_run_dir
    from agentcam.report import render_report, write_manifest
    from agentcam.scanner import scan_paths

    payload = _read_hook_input()
    if payload is None:
        return 0
    extracted = _extract_session(payload)
    if extracted is None:
        return 0
    session_id, cwd = extracted

    if not cwd.exists():
        return 0

    try:
        git_dir = resolve_git_dir(cwd)
    except NotAGitRepoError:
        return 0
    except (OSError, RuntimeError, FileNotFoundError):
        return 0

    session_dir = git_dir / "agentcam" / "sessions" / _safe_session_id(session_id)
    state_file = session_dir / "state_before.pickle"
    if not state_file.exists():
        # No matching SessionStart — silent no-op. Common cases: hook
        # registered mid-session; SessionEnd from a different session id.
        return 0

    # Codex round-1: catch broadly. pickle can raise ValueError /
    # TypeError / RecursionError; dict extraction below can raise
    # KeyError / TypeError on malformed snapshots; any of those should
    # discard-and-continue, not leak orphan session dirs via the outer
    # except.
    try:
        with state_file.open("rb") as f:
            snapshot = pickle.load(f)
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot is not a dict")
        if snapshot.get("schema_version") != _SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"snapshot schema_version mismatch: "
                f"{snapshot.get('schema_version')!r}"
            )
        state_before = snapshot["state"]
        fingerprint_before = snapshot["fingerprint"]
        started_at = snapshot["started_at"]
        git_root_str = snapshot["git_root"]
        # Type checks for every field used downstream. Codex round-2
        # caught that without state/started_at validation, a loadable
        # but malformed snapshot (e.g. state="x") would slip past this
        # block, raise inside render_report, and hit the outer except
        # leaving the bad session dir behind.
        from agentcam.models import GitState
        if not isinstance(state_before, GitState):
            raise ValueError("snapshot['state'] is not a GitState")
        if not isinstance(started_at, datetime):
            raise ValueError("snapshot['started_at'] is not a datetime")
        if not isinstance(fingerprint_before, str):
            raise ValueError("fingerprint not a str")
        if not isinstance(git_root_str, str):
            raise ValueError("git_root not a str")
    except Exception:  # noqa: BLE001 — degrade gracefully
        # Corrupted, stale-schema, or malformed snapshot -- discard
        # and bail. We MUST clean up so a permanently-bad snapshot
        # doesn't poison every future SessionEnd for that session id.
        shutil.rmtree(session_dir, ignore_errors=True)
        return 0

    state_after = collect_git_state(cwd, is_after=True)
    fingerprint_after = compute_diff_fingerprint(cwd)

    no_change = (
        state_before.head == state_after.head
        and state_before.porcelain_raw == state_after.porcelain_raw
        and fingerprint_before == fingerprint_after
    )
    if no_change:
        # Pure-alignment session: agent and user discussed, nothing
        # changed. Clean up session dir, no report.
        shutil.rmtree(session_dir, ignore_errors=True)
        return 0

    # There's a diff — render a report under runs/<run_id>/
    ended_at = datetime.now(timezone.utc).astimezone()
    duration = (ended_at - started_at).total_seconds()
    run_id, run_paths = create_run_dir(
        git_dir, started_at,
        name=f"claude-session-{_short_sid(session_id)}",
    )

    # No stdout/stderr in hook mode — the hook can't access Claude
    # Code's transcript. Write empty placeholder log files so the
    # report's Logs section has paths to point to.
    for log_path_str in (
        run_paths.stdout_raw, run_paths.stderr_raw,
        run_paths.stdout_redacted, run_paths.stderr_redacted,
    ):
        Path(log_path_str).write_bytes(b"")

    # Path-based risk scan only — output-pattern scan needs logs we
    # don't have in hook mode.
    risk_flags = scan_paths(state_after.changed_files)

    manifest = RunManifest(
        schema_version="0.1",
        run_id=run_id.text,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration,
        cwd=str(cwd),
        git_root=git_root_str,
        git_dir=str(git_dir),
        branch=state_before.branch,
        is_detached_head=state_before.is_detached_head,
        head_before=state_before.head,
        head_after=state_after.head,
        pre_existing_op=(
            state_before.pre_existing_op or state_after.pre_existing_op
        ),
        pre_run_dirty=bool(state_before.changed_files),
        command_argv_raw=["(claude code session)", session_id],
        command_argv_redacted=["(claude code session)", session_id],
        exit_detail=None,  # no subprocess in hook mode
        shell_used=False,
        terminal_forward_degraded=False,
        platform=_platform.system().lower(),
        agentcam_version=__version__,
        paths=run_paths,
    )

    Path(run_paths.report_md).write_text(
        render_report(manifest, state_before, state_after, risk_flags),
        encoding="utf-8",
    )
    write_manifest(manifest, Path(run_paths.manifest_json))

    # Cleanup session dir — best effort.
    shutil.rmtree(session_dir, ignore_errors=True)
    return 0
