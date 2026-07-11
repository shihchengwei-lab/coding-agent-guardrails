"""Lifecycle-hook recording for Claude Code sessions and Codex turns.

The wrapping path (``agentcam run -- ...``) records one subprocess. Hook
recording removes that manual wrapper step while preserving honest partial
capture metadata.

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

Codex uses ``hook-turn-start`` on UserPromptSubmit and ``hook-turn-end`` on
Stop. Those commands key snapshots by ``turn_id`` because Codex has no
SessionEnd event. All four commands share the same snapshot/report pipeline.

State storage:
``<git_dir>/agentcam/sessions/<sanitized-session-id>/state_before.pickle``
— pickle is used because :class:`GitState` contains bytes and nested
dataclasses; JSON would need a custom serializer for each. Files are
local-only under ``.git/`` (same trust model as the rest of agentcam's
artifacts: if the attacker can write here, they already own the user).

The session dir is removed on SessionEnd whether or not a report is
generated. If SessionEnd never fires (Claude Code crash), verify ignores the
leftover after its stale-session threshold.
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


def _extract_session(
    payload: dict, *, id_field: str = "session_id"
) -> tuple[str, Path] | None:
    """Extract a recording id and cwd from a hook payload.

    Returns None if either is missing or empty. The session_id is kept
    raw (sanitization happens at the filesystem boundary, not here).
    """
    sid = payload.get(id_field)
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


def cmd_hook_turn_start() -> int:
    """Codex UserPromptSubmit hook: snapshot one turn by turn_id."""
    try:
        return _do_session_start(id_field="turn_id")
    except Exception:  # noqa: BLE001 — observation must not block Codex
        return 0


def _do_session_start(*, id_field: str = "session_id") -> int:
    from agentcam.git_state import (
        NotAGitRepoError,
        collect_git_state,
        compute_diff_fingerprint,
        read_declared_scope,
        resolve_git_dir,
        resolve_git_root,
    )

    payload = _read_hook_input()
    if payload is None:
        return 0
    extracted = _extract_session(payload, id_field=id_field)
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
        "declared_scope": read_declared_scope(git_root),
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


def cmd_hook_turn_end() -> int:
    """Codex Stop hook: finish one turn recording by turn_id."""
    try:
        return _do_session_end(id_field="turn_id", recorder="codex-turn")
    except Exception:  # noqa: BLE001
        try:
            print(
                "agentcam: hook-turn-end failed silently (internal error)",
                file=sys.stderr,
            )
        except Exception:  # noqa: BLE001
            pass
        return 0


def _do_session_end(
    *, id_field: str = "session_id", recorder: str = "claude-session"
) -> int:
    from agentcam.git_state import (
        NotAGitRepoError,
        collect_git_state,
        compute_diff_fingerprint,
        compute_final_state_fingerprint,
        derive_turn_delta,
        resolve_git_dir,
    )
    from agentcam.models import capture_for_claude_hook, capture_for_codex_hook
    from agentcam.paths import create_run_dir
    from agentcam.report import write_run_artifacts
    from agentcam.scanner import provenance_for_builtin_ruleset, scan_paths

    payload = _read_hook_input()
    if payload is None:
        return 0
    extracted = _extract_session(payload, id_field=id_field)
    if extracted is None:
        return 0
    session_id, cwd = extracted
    # transcript_path is the only currently-documented richer-visibility
    # signal Claude Code exposes to hooks; record whether it was advertised.
    transcript_available = isinstance(payload.get("transcript_path"), str)

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

    # Claim the session dir before anything else: rename it so a
    # concurrent `agentcam verify` cannot keep stashing checks into a
    # session that is ending — its append fails loudly (exit 2) instead
    # of claiming success for a record that the cleanup below would
    # delete. POSIX: an append already in flight follows the rename and
    # is still merged. Windows: the rename fails while the stash file
    # is momentarily open — fall back to the unclaimed dir; the stash
    # is loaded after the (slow) render, so the residual loss window is
    # the merge+cleanup instants, not the whole render.
    claimed = session_dir.with_name(session_dir.name + ".ending")
    try:
        shutil.rmtree(claimed, ignore_errors=True)  # stale claim, if any
        os.rename(session_dir, claimed)
        session_dir = claimed
        state_file = session_dir / "state_before.pickle"
    except OSError:
        pass

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
        declared_scope = snapshot.get("declared_scope", [])
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
        if not isinstance(declared_scope, list) or not all(
            isinstance(value, str) for value in declared_scope
        ):
            raise ValueError("declared_scope not a list of strings")
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
    state_after = derive_turn_delta(Path(git_root_str), state_before, state_after)

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
    run_id, run_paths = create_run_dir(
        git_dir, started_at,
        name=f"{recorder}-{_short_sid(session_id)}",
    )

    # Codex review MEDIUM #5: from here until the report is written,
    # any exception (scan failure, probe failure, render error, disk
    # full mid-write) would leave a half-built run dir AND the
    # session dir behind, because the outer cmd_hook_session_end
    # try/except swallows it and returns 0. The try/except/finally
    # below guarantees:
    #   - any failure: the half-built run dir is removed (no
    #     orphan partial artifacts without a report)
    #   - all paths: session dir is removed (it served its purpose
    #     once we have state_after, regardless of report success)
    #   - failures still re-raise so the outer catch can stderr-log.
    try:
        # Path-based risk scan only — output-pattern scan needs logs
        # we don't have in hook mode.
        risk_flags = scan_paths(state_after.changed_files)

        # Shared post-run pipeline: dep probe + manifest + bundle +
        # render + write. Same helper called from wrap mode (cli.py).
        # `capture` records that hook mode has no stdout/stderr stream
        # so report readers don't confuse "no output flags" with "no risk".
        capture_factory = (
            capture_for_codex_hook
            if recorder == "codex-turn"
            else capture_for_claude_hook
        )
        capture = capture_factory(
            transcript_available=transcript_available,
            empty_run_policy="auto_delete_clean_no_diff",
        )
        write_run_artifacts(
            state_before=state_before,
            state_after=state_after,
            risk_flags=risk_flags,
            cwd=cwd,
            git_dir=git_dir,
            git_root=Path(git_root_str),
            run_paths=run_paths,
            run_id=run_id.text,
            started_at=started_at,
            ended_at=ended_at,
            command_argv_raw=[f"({recorder})", session_id],
            command_argv_redacted=[f"({recorder})", session_id],
            exit_detail=None,  # no subprocess in hook mode
            shell_used=False,
            terminal_forward_degraded=False,
            platform_label=_platform.system().lower(),
            capture=capture,
            ruleset=provenance_for_builtin_ruleset(),
            declared_scope=declared_scope,
            final_state_fingerprint=compute_final_state_fingerprint(
                Path(git_root_str)
            ),
        )
        # Transfer records only after the report exists. Each verify owns
        # one atomic file, so concurrent checks never share a read-modify-write
        # target. The manifest is a derived compatibility view.
        from .verification import sync_manifest, transfer_records

        transfer_records(session_dir, Path(run_paths.run_dir))
        sync_manifest(Path(run_paths.run_dir))
    except Exception:
        # Half-written run dir is worse than no run dir — it confuses
        # the user (partial artifacts, no report, unclear what
        # happened). Best-effort remove; re-raise so the outer catch
        # can stderr-log.
        shutil.rmtree(run_paths.run_dir, ignore_errors=True)
        raise
    finally:
        # session_dir served its purpose once state_after was
        # collected. Clean up regardless of report-write outcome so
        # repeated SessionEnd failures don't accumulate stale
        # snapshots. Best-effort only (ignore_errors=True) because
        # the hook MUST exit 0; a filesystem hiccup here cannot be
        # allowed to block Claude Code on the next SessionEnd.
        # Codex review NIT: if this rmtree itself fails (locked file,
        # antivirus, etc.), the stale session dir will persist until
        # next manual cleanup -- accepted trade-off.
        shutil.rmtree(session_dir, ignore_errors=True)

    return 0
