"""agentbox command-line entry point.

Subcommands:
  - ``agentbox version``           — print version and exit
  - ``agentbox run -- <argv...>``  — wrap a command, record raw + redacted
                                     logs, generate AGENT_RUN_REPORT.md

``run`` is intentionally argv-only; for shell features (pipes, redirects,
variable expansion) wrap your own shell explicitly, e.g.::

    agentbox run -- bash -lc "echo hi > out.txt"
    agentbox run -- pwsh -Command "Get-Process | Out-File procs.txt"
    agentbox run -- cmd /c "dir > files.txt"

See ``docs/design.md`` (forthcoming) for the rationale.
"""
from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from agentbox import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentbox",
        description=(
            "Local-first CLI wrapper that records what your AI coding agent "
            "changed in your repo."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    sub.add_parser("version", help="Print agentbox version and exit.")

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
        "argv",
        nargs=argparse.REMAINDER,
        help="The command to run, after a `--` separator.",
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
        print(f"agentbox {__version__}")
        return 0

    if args.cmd == "run":
        return _run_command(args)

    parser.error(f"unknown subcommand: {args.cmd}")
    return 2  # unreachable; parser.error exits


# ---------------------------------------------------------------------------
# `agentbox run` orchestrator
# ---------------------------------------------------------------------------

def _run_command(args) -> int:
    # Imports are local so `agentbox version` doesn't pay for them at startup.
    from agentbox.git_state import (
        NotAGitRepoError,
        collect_git_state,
        is_working_tree_dirty,
        resolve_git_dir,
        resolve_git_root,
    )
    from agentbox.models import RunManifest
    from agentbox.paths import RunIdCollisionError, create_run_dir
    from agentbox.redaction import StreamingRedactor, redact_argv
    from agentbox.report import render_report, write_manifest
    from agentbox.runner import CommandNotFoundError, run_wrapped
    from agentbox.scanner import scan_output, scan_paths

    run_argv = _strip_leading_dashdash(args.argv or [])
    if not run_argv:
        print(
            "agentbox run: no command provided. "
            "Usage: agentbox run -- <command...>",
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
            "agentbox: not in a git repository. "
            "Initialize one with 'git init' first.",
            file=sys.stderr,
        )
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"agentbox: git error: {e}", file=sys.stderr)
        return 2

    # 2) Collect pre-run git state.
    try:
        state_before = collect_git_state(cwd, is_after=False)
    except NotAGitRepoError:
        print(
            "agentbox: not in a git repository. "
            "Initialize one with 'git init' first.",
            file=sys.stderr,
        )
        return 2
    pre_run_dirty = is_working_tree_dirty(state_before)

    # 3) Create the run directory under <git_dir>/agentbox/runs/<run_id>/.
    started_at = datetime.now(timezone.utc).astimezone()
    try:
        run_id, run_paths = create_run_dir(
            git_dir, started_at, name=args.name
        )
    except RunIdCollisionError as e:
        print(f"agentbox: {e}", file=sys.stderr)
        return 2

    # 4) Run the wrapped subprocess with threads-based tee.
    try:
        run_result = run_wrapped(
            run_argv,
            cwd=cwd,
            stdout_raw_path=Path(run_paths.stdout_raw),
            stderr_raw_path=Path(run_paths.stderr_raw),
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
    state_after = collect_git_state(cwd, is_after=True)

    # 7) Scan paths + raw output for risk flags.
    risk_flags = scan_paths(state_after.changed_files)
    risk_flags.extend(_scan_log(Path(run_paths.stdout_raw), "stdout.log"))
    risk_flags.extend(_scan_log(Path(run_paths.stderr_raw), "stderr.log"))

    # 8) Assemble the manifest.
    manifest = RunManifest(
        schema_version="0.1",
        run_id=run_id.text,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration,
        cwd=str(cwd),
        git_root=str(git_root),
        git_dir=str(git_dir),
        branch=state_before.branch,
        is_detached_head=state_before.is_detached_head,
        head_before=state_before.head,
        head_after=state_after.head,
        pre_existing_op=(
            state_before.pre_existing_op or state_after.pre_existing_op
        ),
        pre_run_dirty=pre_run_dirty,
        command_argv_raw=list(run_argv),
        command_argv_redacted=redact_argv(list(run_argv)),
        exit_detail=run_result.exit_detail,
        shell_used=run_result.shell_used,
        terminal_forward_degraded=run_result.terminal_forward_degraded,
        platform=platform.system().lower(),
        agentbox_version=__version__,
        paths=run_paths,
    )

    # 9) Write report + manifest.
    Path(run_paths.report_md).write_text(
        render_report(manifest, state_before, state_after, risk_flags),
        encoding="utf-8",
    )
    write_manifest(manifest, Path(run_paths.manifest_json))

    # 10) Tell the user where to find the report (stderr so it doesn't pollute
    # programmatic stdout consumers).
    print(
        f"\nagentbox: run report at {run_paths.report_md}",
        file=sys.stderr,
    )

    # 11) Return the wrapper exit code (0 if subprocess succeeded, else 1).
    return run_result.exit_detail.wrapper_exit


def _redact_log(raw_path: Path, redacted_path: Path) -> None:
    """Stream raw_path through StreamingRedactor into redacted_path."""
    from agentbox.redaction import StreamingRedactor

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
    from agentbox.scanner import scan_output

    try:
        text = raw_path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        text = ""
    return scan_output(text, stream_label=label)


if __name__ == "__main__":
    sys.exit(main())
