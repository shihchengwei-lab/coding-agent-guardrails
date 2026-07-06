"""agentcam command-line entry point.

Subcommands:
  - ``agentcam version``            — print version and exit
  - ``agentcam run -- <argv...>``   — wrap a command, record raw + redacted
                                      logs, generate AGENT_RUN_REPORT.md
  - ``agentcam verify -- <argv>``   — run a check, record command / exit
                                      code / duration into run evidence
  - ``agentcam handoff [run_id]``   — print the five-line corridor handoff
                                      drafted from a recorded run
  - ``agentcam export <run_id>``    — share-safe redacted bundle (zip, or
                                      committable files via ``--files``)
  - ``agentcam hook-session-start`` / ``hook-session-end``
                                    — Claude Code session hooks

``run`` is intentionally argv-only; for shell features (pipes, redirects,
variable expansion) wrap your own shell explicitly, e.g.::

    agentcam run -- bash -lc "echo hi > out.txt"
    agentcam run -- pwsh -Command "Get-Process | Out-File procs.txt"
    agentcam run -- cmd /c "dir > files.txt"

See ``docs/design.md`` for the rationale.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from agentcam import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentcam",
        description=(
            "Local-first CLI wrapper that records what your AI coding agent "
            "changed in your repo."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    sub.add_parser("version", help="Print agentcam version and exit.")

    sub.add_parser(
        "hook-session-start",
        help=(
            "Claude Code SessionStart hook: snapshot git state. Reads "
            "JSON payload from stdin. Wire via ~/.claude/settings.json."
        ),
    )
    sub.add_parser(
        "hook-session-end",
        help=(
            "Claude Code SessionEnd hook: compare against the SessionStart "
            "snapshot, render a report under .git/agentcam/runs/ if there's "
            "a git-visible diff. Reads JSON payload from stdin."
        ),
    )

    run = sub.add_parser(
        "run",
        help="Wrap a command and record the agent run.",
        description=(
            "Wraps an argv-style command. Use `bash -lc \"...\"`, "
            "`pwsh -Command \"...\"`, or `cmd /c \"...\"` for shell features "
            "(pipes, redirects, variable expansion)."
        ),
    )
    run.add_argument(
        "--name",
        default=None,
        help="Slug included in the run id (e.g. 'claude-fix-login').",
    )
    run.add_argument(
        "--keep-empty",
        action="store_true",
        help=(
            "Keep the run report even when the wrapped command produced no "
            "git-visible changes. Default is to delete the run dir on a "
            "no-diff success, so pure-alignment sessions don't clutter "
            ".git/agentcam/runs/."
        ),
    )
    run.add_argument(
        "--backend",
        choices=["pipe", "pty", "pty_posix", "pty_windows"],
        default="pty",
        help=(
            "Wrap backend. 'pipe' is the original subprocess pipe path "
            "(TUI agents won't render). 'pty' (default) auto-picks "
            "pty_posix or pty_windows by platform; explicit "
            "pty_posix / pty_windows force one. See ROADMAP §2."
        ),
    )
    run.add_argument(
        "argv",
        nargs=argparse.REMAINDER,
        help="The command to run, after a `--` separator.",
    )

    export = sub.add_parser(
        "export",
        help="Build a share-safe redacted ZIP bundle for one run.",
        description=(
            "Produces agentcam-export-<run_id>.zip in the current "
            "directory by default. Bundle includes report, redacted "
            "manifest, redacted logs, sha256 checksums, and export "
            "notes. Raw logs are excluded unless --include-raw is given."
        ),
    )
    export.add_argument(
        "run_id",
        help=(
            "Run id under .git/agentcam/runs/, or the literal "
            "'latest' to select the most recently modified run."
        ),
    )
    export.add_argument(
        "--output",
        default=None,
        help=(
            "Destination zip path. Defaults to "
            "./agentcam-export-<run_id>.zip in the current directory."
        ),
    )
    export.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output path if it already exists.",
    )
    export.add_argument(
        "--include-raw",
        action="store_true",
        help=(
            "Include raw stdout.log / stderr.log in the bundle. Raw "
            "logs may contain secrets the redactor missed; off by "
            "default for safer sharing."
        ),
    )
    export.add_argument(
        "--files",
        default=None,
        metavar="DIR",
        help=(
            "Instead of a zip, write AGENT_RUN_REPORT.md and "
            "manifest.redacted.json into DIR — the committable form "
            "corridor-ci reads as recorded evidence. Logs are never "
            "included in this mode."
        ),
    )

    handoff = sub.add_parser(
        "handoff",
        help=(
            "Print a corridor-ci five-line handoff draft from a "
            "recorded run."
        ),
        description=(
            "Reads the run's manifest evidence and prints the compact "
            "handoff (Decision / Scope / Review first / Verified / "
            "Risk) for the pull request body. Decision is left for the "
            "author: agentcam records what changed, not why. Verified "
            "is drafted from checks recorded by `agentcam verify`; "
            "without a passing recorded check it stays a fill-in."
        ),
    )
    handoff.add_argument(
        "run_id",
        nargs="?",
        default="latest",
        help=(
            "Run id under .git/agentcam/runs/, or 'latest' (default) "
            "for the most recently modified run."
        ),
    )

    verify = sub.add_parser(
        "verify",
        help=(
            "Run a check command and record its result into a run's "
            "evidence."
        ),
        description=(
            "Runs the given command (typically the test suite) with "
            "agentcam as the parent process, then appends the redacted "
            "command line, exit code, and duration to the run's "
            "manifest evidence. `agentcam handoff` drafts the Verified "
            "line from checks recorded with exit code 0. The check's "
            "exit code is passed through."
        ),
    )
    verify.add_argument(
        "--run",
        default="latest",
        metavar="RUN_ID",
        help=(
            "Run id under .git/agentcam/runs/ to attach the check to, "
            "or 'latest' (default): the in-progress Claude Code session "
            "if one exists, otherwise the most recently modified run."
        ),
    )
    verify.add_argument(
        "argv",
        nargs=argparse.REMAINDER,
        help="The check command, after a `--` separator.",
    )

    return parser


def _strip_leading_dashdash(argv: list[str]) -> list[str]:
    """argparse.REMAINDER keeps a leading `--`; strip it for cleanliness."""
    if argv and argv[0] == "--":
        return argv[1:]
    return argv


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "version":
        print(f"agentcam {__version__}")
        return 0

    if args.cmd == "run":
        try:
            return _run_command(args)
        except Exception as e:  # noqa: BLE001
            # Flight-recorder rule: never dump a traceback on the user's
            # terminal. The main way to get here is the wrapped agent
            # destroying the repo mid-run (rm -rf .git takes the run dir
            # and its raw logs with it, since they live under .git/).
            print(
                f"agentcam: unexpected error: {type(e).__name__}: {e}. "
                "Run artifacts may be incomplete or missing (did the "
                "wrapped command delete or corrupt the repository?).",
                file=sys.stderr,
            )
            return 1

    if args.cmd == "hook-session-start":
        from agentcam.hooks import cmd_hook_session_start
        return cmd_hook_session_start()

    if args.cmd == "hook-session-end":
        from agentcam.hooks import cmd_hook_session_end
        return cmd_hook_session_end()

    if args.cmd == "export":
        return _export_command(args)

    if args.cmd == "handoff":
        return _handoff_command(args)

    if args.cmd == "verify":
        return _verify_command(args)

    parser.error(f"unknown subcommand: {args.cmd}")
    return 2  # unreachable; parser.error exits


def _export_command(args) -> int:
    from agentcam.export import ExportError, export, resolve_run_dir
    from agentcam.git_state import NotAGitRepoError, resolve_git_dir

    cwd = Path.cwd()
    try:
        git_dir = resolve_git_dir(cwd)
    except NotAGitRepoError:
        print(
            "agentcam: not in a git repository. agentcam export needs "
            "to find runs under <git_dir>/agentcam/runs/.",
            file=sys.stderr,
        )
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"agentcam: git error: {e}", file=sys.stderr)
        return 2

    # Resolve the run early so we can name the default output zip
    # after the *effective* run_id ('latest' becomes a real id here).
    try:
        run_dir = resolve_run_dir(git_dir, args.run_id)
    except ExportError as e:
        print(f"agentcam: {e}", file=sys.stderr)
        return 2

    if args.files:
        from agentcam.export import export_files

        if args.include_raw:
            print(
                "agentcam: --include-raw cannot be combined with "
                "--files; raw logs are not safe to commit.",
                file=sys.stderr,
            )
            return 2
        try:
            written = export_files(
                run_dir, Path(args.files), force=args.force
            )
        except ExportError as e:
            print(f"agentcam: {e}", file=sys.stderr)
            return 2
        for out in written:
            print(f"agentcam: export written to {out}", file=sys.stderr)
        return 0

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = cwd / f"agentcam-export-{run_dir.name}.zip"

    try:
        export(
            git_dir=git_dir,
            run_id=run_dir.name,  # already-resolved id; bypass 'latest'
            output_path=out_path,
            force=args.force,
            include_raw=args.include_raw,
        )
    except ExportError as e:
        print(f"agentcam: {e}", file=sys.stderr)
        return 2

    print(
        f"agentcam: export written to {out_path}",
        file=sys.stderr,
    )
    return 0


def _pick_review_first(paths: list[str], flags: list[dict]) -> str:
    """Highest-severity flagged file that is in the changed set, else
    the first changed file."""
    for level in ("HIGH", "MEDIUM"):
        for flag in flags:
            if flag.get("level") == level and flag.get("evidence") in paths:
                return flag["evidence"]
    return paths[0]


def _verified_line(verifications: list) -> str:
    """Draft the handoff Verified line from recorded checks.

    Only checks agentcam itself ran (exit code observed, not claimed)
    fill the line; with no passing check it stays a fill-in — the
    claim belongs to the author, and red must not read as verified.
    """
    recorded = [v for v in verifications if isinstance(v, dict)]
    passing = [v for v in recorded if v.get("exit_code") == 0]
    if passing:
        checks = "; ".join(
            f"{v.get('command', '?')} (exit 0)" for v in passing
        )
        return f"{checks} [recorded by agentcam]"
    if recorded:
        last = recorded[-1]
        return (
            "<fill in: recorded check failed: "
            f"{last.get('command', '?')} (exit {last.get('exit_code')})>"
        )
    return "<fill in: agentcam did not observe a test run>"


def _handoff_command(args) -> int:
    from agentcam.export import ExportError, resolve_run_dir
    from agentcam.git_state import NotAGitRepoError, resolve_git_dir

    cwd = Path.cwd()
    try:
        git_dir = resolve_git_dir(cwd)
    except NotAGitRepoError:
        print(
            "agentcam: not in a git repository. agentcam handoff needs "
            "to find runs under <git_dir>/agentcam/runs/.",
            file=sys.stderr,
        )
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"agentcam: git error: {e}", file=sys.stderr)
        return 2

    try:
        run_dir = resolve_run_dir(git_dir, args.run_id)
    except ExportError as e:
        print(f"agentcam: {e}", file=sys.stderr)
        return 2

    manifest_path = run_dir / "manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(
            f"agentcam: could not read {manifest_path}: {e}",
            file=sys.stderr,
        )
        return 2

    evidence = data.get("evidence")
    if evidence is None:
        print(
            f"agentcam: run {run_dir.name} has no evidence section "
            "(recorded by an older agentcam). Re-record the run with "
            "this version to generate a handoff.",
            file=sys.stderr,
        )
        return 2

    changed = evidence.get("changed_files") or []
    if not changed:
        print(
            f"agentcam: run {run_dir.name} recorded no changed files; "
            "nothing to hand off.",
            file=sys.stderr,
        )
        return 2

    paths = [cf["path"] for cf in changed]
    review_first = _pick_review_first(
        paths, evidence.get("risk_flags") or []
    )
    risk = str(evidence.get("overall_risk") or "low").lower()

    # The handoff is drafted to be pasted into a PR body: secret-like
    # filenames must not leave the machine here any more than they do in
    # the report or the redacted export.
    from agentcam.scanner import is_secret_like_filename

    def _display(path: str) -> str:
        return (
            "<redacted-secret-filename>"
            if is_secret_like_filename(path)
            else path
        )

    print("Decision: <fill in: issue or decision link>")
    print(f"Scope: {', '.join(_display(p) for p in paths)}")
    print(f"Review first: {_display(review_first)}")
    print(f"Verified: {_verified_line(evidence.get('verifications') or [])}")
    print(f"Risk: {risk}")
    return 0


# An in-progress hook session older than this is treated as a crash
# leftover by `verify --run latest` (SessionEnd normally removes the dir
# within the session's lifetime; real Claude Code sessions do not span days).
_SESSION_STALE_SECONDS = 24 * 3600


def _latest_in_progress_session(git_dir: Path) -> Path | None:
    """Most recently started in-progress hook session, or None.

    A session dir with a state_before.pickle is a Claude Code session
    that started but has not ended (SessionEnd removes the dir).
    Sessions older than ``_SESSION_STALE_SECONDS`` are ignored: a crash
    that skipped SessionEnd leaves the dir behind forever, and treating
    it as in-progress would stash every later ``verify`` into a file
    nothing will ever merge.
    """
    import time

    sessions_root = git_dir / "agentcam" / "sessions"
    try:
        now = time.time()
        candidates = [
            d
            for d in sessions_root.iterdir()
            # *.ending = session mid-teardown (claimed by SessionEnd,
            # hooks.py); it no longer accepts checks.
            if not d.name.endswith(".ending")
            and (d / "state_before.pickle").is_file()
            and (
                now - (d / "state_before.pickle").stat().st_mtime
                < _SESSION_STALE_SECONDS
            )
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda d: (d / "state_before.pickle").stat().st_mtime,
        )
    except OSError:
        return None


def _verify_command(args) -> int:
    import shutil
    import subprocess

    from agentcam.export import ExportError, resolve_run_dir
    from agentcam.git_state import NotAGitRepoError, resolve_git_dir
    from agentcam.redaction import redact_argv

    check_argv = _strip_leading_dashdash(args.argv or [])
    if not check_argv:
        print(
            "agentcam verify: no command provided. "
            "Usage: agentcam verify -- <command...>",
            file=sys.stderr,
        )
        return 2

    cwd = Path.cwd()
    try:
        git_dir = resolve_git_dir(cwd)
    except NotAGitRepoError:
        print(
            "agentcam: not in a git repository. agentcam verify needs "
            "to find runs under <git_dir>/agentcam/runs/.",
            file=sys.stderr,
        )
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"agentcam: git error: {e}", file=sys.stderr)
        return 2

    # Hook mode: an in-progress Claude Code session has a snapshot under
    # sessions/ but no run under runs/ yet (the run is rendered at
    # SessionEnd), so `latest` would pin the check to a PREVIOUS
    # session's run. Stash it in the session dir instead; SessionEnd
    # merges it into the run it renders. An explicit --run ID still
    # targets runs/.
    session_dir = None
    if args.run == "latest":
        session_dir = _latest_in_progress_session(git_dir)

    if session_dir is None:
        try:
            run_dir = resolve_run_dir(git_dir, args.run)
        except ExportError as e:
            print(f"agentcam: {e}", file=sys.stderr)
            return 2

        manifest_path = run_dir / "manifest.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(
                f"agentcam: could not read {manifest_path}: {e}",
                file=sys.stderr,
            )
            return 2

        evidence = data.get("evidence")
        if evidence is None:
            print(
                f"agentcam: run {run_dir.name} has no evidence section "
                "(recorded by an older agentcam). Re-record the run with "
                "this version before recording checks.",
                file=sys.stderr,
            )
            return 2
        if not isinstance(evidence, dict) or not isinstance(
            evidence.get("verifications", []), list
        ):
            print(
                f"agentcam: run {run_dir.name} has a malformed evidence "
                "section; refusing to record checks into it.",
                file=sys.stderr,
            )
            return 2

    # Resolve via PATH like the run backend (runner.py) so PATHEXT-only
    # runners (`npm`, `pytest.cmd`) work without a shell; the recorded
    # command keeps the form the author typed.
    exec_argv = list(check_argv)
    resolved = shutil.which(exec_argv[0])
    if resolved:
        exec_argv[0] = resolved

    started_at = datetime.now(timezone.utc).astimezone()
    try:
        proc = subprocess.run(exec_argv, cwd=cwd)
    except FileNotFoundError:
        print(
            f"agentcam: command not found: {check_argv[0]}",
            file=sys.stderr,
        )
        return 2
    except OSError as e:
        print(f"agentcam: could not run check: {e}", file=sys.stderr)
        return 2
    duration = (
        datetime.now(timezone.utc).astimezone() - started_at
    ).total_seconds()

    record = {
        "command": " ".join(redact_argv(list(check_argv))),
        "exit_code": proc.returncode,
        "duration_seconds": round(duration, 3),
        "recorded_at": started_at.isoformat(),
    }

    if session_dir is not None:
        try:
            with (session_dir / "verifications.jsonl").open(
                "a", encoding="utf-8"
            ) as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            print(
                f"agentcam: check finished (exit {proc.returncode}) but "
                f"could not record it for session {session_dir.name}: "
                f"{e}; nothing was recorded.",
                file=sys.stderr,
            )
            return 2
        print(
            f"agentcam: recorded check (exit {proc.returncode}) for "
            f"in-progress session {session_dir.name}; it attaches to "
            "the session's run when the session ends",
            file=sys.stderr,
        )
        return proc.returncode

    # Re-read before writing: the check itself (or a concurrent verify)
    # may have modified the manifest while it ran, and appending to the
    # pre-check copy would clobber those records.
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(
            f"agentcam: check finished (exit {proc.returncode}) but "
            f"{manifest_path} could not be re-read: {e}; nothing was "
            "recorded.",
            file=sys.stderr,
        )
        return 2
    evidence = data.get("evidence")
    if not isinstance(evidence, dict) or not isinstance(
        evidence.get("verifications", []), list
    ):
        print(
            f"agentcam: check finished (exit {proc.returncode}) but the "
            "manifest evidence is malformed; nothing was recorded.",
            file=sys.stderr,
        )
        return 2

    # The check ran as agentcam's direct child, so command / exit code /
    # duration are observed facts, not the wrapped agent's claims. The
    # command line is stored redacted because it rides into the
    # committable manifest.redacted.json via `export --files`.
    evidence.setdefault("verifications", []).append(record)
    manifest_path.write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    print(
        f"agentcam: recorded check (exit {proc.returncode}) "
        f"in run {run_dir.name}",
        file=sys.stderr,
    )
    return proc.returncode


# ---------------------------------------------------------------------------
# `agentcam run` orchestrator
# ---------------------------------------------------------------------------

def _run_command(args) -> int:
    # Imports are local so `agentcam version` doesn't pay for them at startup.
    from agentcam.git_state import (
        NotAGitRepoError,
        collect_git_state,
        compute_diff_fingerprint,
        is_working_tree_dirty,
        resolve_git_dir,
        resolve_git_root,
    )
    from agentcam.models import (
        capture_for_wrap_pipe,
        capture_for_wrap_pty_posix,
        capture_for_wrap_pty_windows,
    )
    from agentcam.paths import RunIdCollisionError, create_run_dir
    from agentcam.redaction import redact_argv
    from agentcam.report import write_run_artifacts
    from agentcam.runner import CommandNotFoundError, run_wrapped
    from agentcam.scanner import provenance_for_builtin_ruleset, scan_paths

    run_argv = _strip_leading_dashdash(args.argv or [])
    if not run_argv:
        print(
            "agentcam run: no command provided. "
            "Usage: agentcam run -- <command...>",
            file=sys.stderr,
        )
        return 2

    cwd = Path.cwd()

    # 1) Confirm we're in a git repo and resolve git dir.
    try:
        git_dir = resolve_git_dir(cwd)
        git_root = resolve_git_root(cwd)
    except NotAGitRepoError:
        print(
            "agentcam: not in a git repository. "
            "Initialize one with 'git init' first.",
            file=sys.stderr,
        )
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"agentcam: git error: {e}", file=sys.stderr)
        return 2

    # 2) Collect pre-run git state.
    try:
        state_before = collect_git_state(cwd, is_after=False)
    except NotAGitRepoError:
        print(
            "agentcam: not in a git repository. "
            "Initialize one with 'git init' first.",
            file=sys.stderr,
        )
        return 2
    pre_run_dirty = is_working_tree_dirty(state_before)

    # Diff fingerprint for the no-diff cleanup decision (step 6.5).
    # Computed only when cleanup might fire — `--keep-empty` skips the
    # untracked-content hashing cost entirely (was a doc lie before the
    # Codex round-2 fix; fingerprint used to be always computed inside
    # collect_git_state regardless of --keep-empty).
    fingerprint_before = (
        compute_diff_fingerprint(cwd) if not args.keep_empty else ""
    )

    # 3) Create the run directory under <git_dir>/agentcam/runs/<run_id>/.
    started_at = datetime.now(timezone.utc).astimezone()
    try:
        run_id, run_paths = create_run_dir(
            git_dir, started_at, name=args.name
        )
    except RunIdCollisionError as e:
        print(f"agentcam: {e}", file=sys.stderr)
        return 2

    # 4) Resolve `pty` alias to the platform-specific backend, then run.
    backend = args.backend
    if backend == "pty":
        backend = (
            "pty_windows" if platform.system().lower() == "windows"
            else "pty_posix"
        )
    try:
        run_result = run_wrapped(
            run_argv,
            cwd=cwd,
            stdout_raw_path=Path(run_paths.stdout_raw),
            stderr_raw_path=Path(run_paths.stderr_raw),
            backend=backend,
        )
    except CommandNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    ended_at = datetime.now(timezone.utc).astimezone()
    duration = (ended_at - started_at).total_seconds()

    # 5) Produce redacted logs from the raw logs.
    _redact_log(Path(run_paths.stdout_raw), Path(run_paths.stdout_redacted))
    _redact_log(Path(run_paths.stderr_raw), Path(run_paths.stderr_redacted))

    # 6) Collect post-run git state (is_after=True triggers diff --check).
    # Guarded: the wrapped agent may have destroyed the repo (rm -rf .git
    # is exactly the kind of event a flight recorder must land a report
    # for), so a git failure here degrades to an empty after-state and a
    # HIGH risk flag instead of a traceback with no artifacts.
    from agentcam.models import GitState, RiskFlag

    post_git_error: str | None = None
    try:
        state_after = collect_git_state(cwd, is_after=True)
        fingerprint_after = (
            compute_diff_fingerprint(cwd) if not args.keep_empty else ""
        )
    except Exception as e:  # noqa: BLE001
        post_git_error = f"{type(e).__name__}: {e}"
        state_after = GitState(
            head=None,
            branch=None,
            is_detached_head=False,
            porcelain_raw=b"",
            diff_stat="",
            diff_stat_cached="",
            diff_name_status="",
            diff_name_status_cached="",
        )
        fingerprint_after = "post-run-git-state-unavailable"
        print(
            "agentcam: warning: could not read git state after the run "
            f"({post_git_error}); the report records pre-run state only",
            file=sys.stderr,
        )

    # 7) Scan paths + raw output for risk flags. Output scan is
    # wrap-mode-only (hook mode has no transcript to scan).
    # Order intentional: output scanning happens BEFORE the no-diff
    # cleanup decision so a session that printed `rm -rf` without
    # changing the working tree is preserved -- the user needs to see
    # what was emitted even though no diff landed
    # (see docs/design.md #30).
    output_risk_flags = (
        _scan_log(Path(run_paths.stdout_raw), "stdout.log")
        + _scan_log(Path(run_paths.stderr_raw), "stderr.log")
    )
    path_risk_flags = scan_paths(state_after.changed_files)
    risk_flags = path_risk_flags + output_risk_flags
    if post_git_error is not None:
        risk_flags.append(
            RiskFlag(
                level="HIGH",
                rule="post-run git state unavailable",
                evidence=post_git_error[:200],
            )
        )

    # 6.5) "No-diff = no report": if the run made no git-visible
    # changes AND succeeded AND no output risk evidence, delete the
    # run dir. Output risk evidence is preserved even with no git
    # diff -- "agent shouted `rm -rf /` but didn't run it" is still
    # the kind of thing a flight recorder should keep.
    exit_ok = run_result.exit_detail.wrapper_exit == 0
    if args.keep_empty:
        no_git_change_raw = False  # cleanup disabled — skip comparison
        empty_run_policy = "keep_empty_requested"
    else:
        no_git_change_raw = (
            post_git_error is None
            and state_before.head == state_after.head
            and state_before.porcelain_raw == state_after.porcelain_raw
            and fingerprint_before == fingerprint_after
        )
        if no_git_change_raw and exit_ok and output_risk_flags:
            empty_run_policy = "preserve_visible_risk"
        else:
            empty_run_policy = "auto_delete_clean_no_diff"

    # Cleanup fires only when nothing in this run is worth keeping:
    # no git change AND succeeded AND no output risk evidence.
    cleanup_fires = (
        no_git_change_raw
        and exit_ok
        and not output_risk_flags
        and not args.keep_empty
    )
    if cleanup_fires:
        import shutil
        try:
            shutil.rmtree(run_paths.run_dir)
        except OSError as e:
            # On Windows, held file handles or AV scanners can make
            # rmtree fail mid-deletion. Two sub-cases:
            #   (a) Run dir still exists → fall through to normal report
            #       generation so the user has *something*.
            #   (b) Run dir itself was already removed (partial failure
            #       on a sibling write or race) → write_text on report.md
            #       would FileNotFoundError. Log and exit clean instead.
            if not Path(run_paths.run_dir).exists():
                print(
                    f"agentcam: cleanup of {run_paths.run_dir} partially "
                    f"succeeded then failed ({e}); no report could be "
                    "written.",
                    file=sys.stderr,
                )
                return 0
            print(
                f"agentcam: cleanup of {run_paths.run_dir} failed ({e}); "
                "generating report normally.",
                file=sys.stderr,
            )
        else:
            print(
                "agentcam: no git-visible changes; report skipped "
                "(use --keep-empty to override).",
                file=sys.stderr,
            )
            return 0

    # If the run had no git diff but is being preserved due to risk
    # evidence, tell the user up front -- otherwise the "report at
    # ..." message at step 10 alone might make it look like a normal
    # diff-bearing run.
    if empty_run_policy == "preserve_visible_risk":
        print(
            "agentcam: no git-visible changes, but output risk flags "
            "were observed; report kept (use --keep-empty for full "
            "history, or review the report below).",
            file=sys.stderr,
        )

    # 8-9) Shared post-run pipeline: dep probe + manifest + bundle +
    # render + write. Same helper called from hook mode. `capture`
    # records what observation surface was active for this run --
    # `empty_run_policy` distinguishes a normal run from one preserved
    # only because the scanner saw a risky output pattern. See
    # docs/design.md #28 + #30.
    if backend == "pipe":
        capture = capture_for_wrap_pipe(empty_run_policy=empty_run_policy)
    elif backend == "pty_posix":
        capture = capture_for_wrap_pty_posix(empty_run_policy=empty_run_policy)
    elif backend == "pty_windows":
        capture = capture_for_wrap_pty_windows(empty_run_policy=empty_run_policy)
    write_run_artifacts(
        state_before=state_before,
        state_after=state_after,
        risk_flags=risk_flags,
        cwd=cwd,
        git_dir=git_dir,
        git_root=git_root,
        run_paths=run_paths,
        run_id=run_id.text,
        started_at=started_at,
        ended_at=ended_at,
        command_argv_raw=list(run_argv),
        command_argv_redacted=redact_argv(list(run_argv)),
        exit_detail=run_result.exit_detail,
        shell_used=run_result.shell_used,
        terminal_forward_degraded=run_result.terminal_forward_degraded,
        platform_label=platform.system().lower(),
        capture=capture,
        ruleset=provenance_for_builtin_ruleset(),
    )

    # 10) Tell the user where to find the report (stderr so it doesn't pollute
    # programmatic stdout consumers).
    print(
        f"\nagentcam: run report at {run_paths.report_md}",
        file=sys.stderr,
    )

    # 11) Return the wrapper exit code (0 if subprocess succeeded, else 1).
    return run_result.exit_detail.wrapper_exit


def _redact_log(raw_path: Path, redacted_path: Path) -> None:
    """Stream raw_path through StreamingRedactor into redacted_path."""
    from agentcam.redaction import StreamingRedactor

    with raw_path.open("rb") as in_fp, redacted_path.open("wb") as out_fp:
        r = StreamingRedactor(out_fp)
        while True:
            chunk = in_fp.read(4096)
            if not chunk:
                break
            r.feed(chunk)
        r.close()


def _scan_log(raw_path: Path, label: str):
    """Scan a raw log for output-pattern risk flags."""
    from agentcam.scanner import scan_output

    try:
        text = raw_path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        text = ""
    return scan_output(text, stream_label=label)


if __name__ == "__main__":
    sys.exit(main())
