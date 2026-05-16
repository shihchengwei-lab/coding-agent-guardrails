"""AGENT_RUN_REPORT.md generator + manifest.json writer.

Plan sections:
  §5  — four rollback wording cases
  §9  — Exit Code Detail block
  §10 — manifest schema
  §11 — report-wide redaction surface (filenames in diff stat / changed files /
        risk evidence; redacted command argv only in markdown)
"""
from __future__ import annotations

import json
from pathlib import Path

from agentcam.models import (
    ChangedFile,
    ExitDetail,
    GitState,
    RiskFlag,
    RunManifest,
)
from agentcam.scanner import is_secret_like_filename


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def render_report(
    manifest: RunManifest,
    state_before: GitState,
    state_after: GitState,
    risk_flags: list[RiskFlag],
) -> str:
    """Render the full ``AGENT_RUN_REPORT.md`` as a string."""
    sections: list[str] = [
        _render_header(manifest),
        _render_verdict(risk_flags),
        _render_risk_flags(risk_flags),
        _render_changed_files(state_after),
        _render_diff_stat(state_after),
        _render_exit_detail(manifest.exit_detail),
        _render_verification_placeholder(),
        _render_rollback(manifest, state_after),
        _render_logs(manifest),
        _render_local_artifacts(manifest),
    ]
    return "\n\n".join(s for s in sections if s)


def serialize_manifest(m: RunManifest) -> dict:
    """Convert a :class:`RunManifest` to a JSON-serializable dict."""
    exit_detail_dict: dict | None = None
    if m.exit_detail:
        exit_detail_dict = {
            "wrapper_exit": m.exit_detail.wrapper_exit,
            "raw_returncode": m.exit_detail.raw_returncode,
            "raw_returncode_hex": m.exit_detail.raw_returncode_hex,
            "platform": m.exit_detail.platform,
            "interpretation": m.exit_detail.interpretation,
            "interpretation_source": m.exit_detail.interpretation_source,
        }
    paths_dict = {
        "run_dir": m.paths.run_dir,
        "manifest_json": m.paths.manifest_json,
        "report_md": m.paths.report_md,
        "stdout_raw": m.paths.stdout_raw,
        "stderr_raw": m.paths.stderr_raw,
        "stdout_redacted": m.paths.stdout_redacted,
        "stderr_redacted": m.paths.stderr_redacted,
    }
    return {
        "schema_version": m.schema_version,
        "run_id": m.run_id,
        "started_at": m.started_at.isoformat(),
        "ended_at": m.ended_at.isoformat() if m.ended_at else None,
        "duration_seconds": m.duration_seconds,
        "cwd": m.cwd,
        "git_root": m.git_root,
        "git_dir": m.git_dir,
        "branch": m.branch,
        "is_detached_head": m.is_detached_head,
        "head_before": m.head_before,
        "head_after": m.head_after,
        "pre_existing_op": m.pre_existing_op,
        "pre_run_dirty": m.pre_run_dirty,
        "command_argv_raw": m.command_argv_raw,
        "command_argv_redacted": m.command_argv_redacted,
        "exit_detail": exit_detail_dict,
        "shell_used": m.shell_used,
        "terminal_forward_degraded": m.terminal_forward_degraded,
        "platform": m.platform,
        "agentcam_version": m.agentcam_version,
        "paths": paths_dict,
    }


def write_manifest(m: RunManifest, path: Path) -> None:
    path.write_text(
        json.dumps(serialize_manifest(m), indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_header(m: RunManifest) -> str:
    started = m.started_at.isoformat()
    ended = m.ended_at.isoformat() if m.ended_at else "(in progress)"
    duration = (
        f"{m.duration_seconds:.3f}s"
        if m.duration_seconds is not None else "?"
    )
    branch = m.branch or ("(detached)" if m.is_detached_head else "(unknown)")
    head_before = m.head_before or "(no commits)"
    head_after = m.head_after or "(no commits)"
    cmd_str = " ".join(m.command_argv_redacted)
    return (
        "# Agent Run Report\n\n"
        "## Summary\n\n"
        f"- Run ID: `{m.run_id}`\n"
        f"- Command: `{cmd_str}`\n"
        f"- Started: {started}\n"
        f"- Ended: {ended}\n"
        f"- Duration: {duration}\n"
        f"- Git branch: {branch}\n"
        f"- Head before: `{head_before}`\n"
        f"- Head after: `{head_after}`\n"
        f"- Pre-run dirty: {'yes' if m.pre_run_dirty else 'no'}\n"
        f"- Pre-existing op: {m.pre_existing_op or 'none'}\n"
        f"- Platform: {m.platform}\n"
        f"- agentcam version: {m.agentcam_version}"
    )


def _render_verdict(flags: list[RiskFlag]) -> str:
    if any(f.level == "HIGH" for f in flags):
        overall, review = "HIGH", "yes"
    elif any(f.level == "MEDIUM" for f in flags):
        overall, review = "MEDIUM", "yes"
    else:
        overall, review = "LOW (no risk flags)", "no"
    return (
        "## Verdict\n\n"
        f"- Overall risk: **{overall}**\n"
        f"- Human review required: {review}\n\n"
        "> Risk flags are heuristics, not verdicts. They indicate where to "
        "look, not what happened. agentcam cannot judge intent or context."
    )


def _render_risk_flags(flags: list[RiskFlag]) -> str:
    if not flags:
        return "## Risk Flags\n\n_None._"
    rows = ["| Severity | Rule | Evidence |", "|---|---|---|"]
    for f in flags:
        rows.append(f"| {f.level} | {f.rule} | {f.evidence} |")
    return "## Risk Flags\n\n" + "\n".join(rows)


def _render_changed_files(state: GitState) -> str:
    visible = [cf for cf in state.changed_files if not _is_internal(cf.path)]
    if not visible:
        return "## Changed Files\n\n_None._"
    rows = ["| Status | File |", "|---|---|"]
    for cf in visible:
        if is_secret_like_filename(cf.path):
            display = "<redacted-secret-filename>"
        else:
            display = cf.path
        if cf.rename_from:
            # Codex source-review CRITICAL: the old name in a rename is
            # also a markdown surface; if it's secret-like, redact it too.
            old_display = (
                "<redacted-secret-filename>"
                if is_secret_like_filename(cf.rename_from)
                else cf.rename_from
            )
            display += f" (renamed from {old_display})"
        rows.append(f"| {cf.status} | {display} |")
    return "## Changed Files\n\n" + "\n".join(rows)


def _render_diff_stat(state: GitState) -> str:
    parts: list[str] = ["## Diff Stat"]
    if state.diff_stat_cached:
        parts.append(
            "### staged (--cached)\n\n```text\n"
            + _redact_filenames_in_diff_stat(state.diff_stat_cached)
            + "\n```"
        )
    if state.diff_stat:
        parts.append(
            "### unstaged\n\n```text\n"
            + _redact_filenames_in_diff_stat(state.diff_stat)
            + "\n```"
        )
    check_blocks: list[str] = []
    if state.diff_check_cached:
        check_blocks.append(
            "staged:\n\n```text\n"
            + _redact_filenames_in_diff_check(state.diff_check_cached)
            + "\n```"
        )
    if state.diff_check:
        check_blocks.append(
            "unstaged:\n\n```text\n"
            + _redact_filenames_in_diff_check(state.diff_check)
            + "\n```"
        )
    if check_blocks:
        parts.append("### diff --check\n\n" + "\n\n".join(check_blocks))
    if len(parts) == 1:
        parts.append("_No diff stats._")
    return "\n\n".join(parts)


def _redact_filenames_in_diff_check(text: str) -> str:
    """Replace secret-like filenames in ``git diff --check`` output.

    Format: ``<path>:<line>: <message>`` (or ``<path>:<line>:<col>: <message>``).
    Only the leading path is checked. (Codex source-review CRITICAL: the
    `diff --check` block was previously concatenated raw into markdown,
    bypassing the secret-filename redaction surface.)
    """
    if not text:
        return text
    out_lines: list[str] = []
    for line in text.splitlines():
        if ":" in line:
            path_part, sep, rest = line.partition(":")
            if is_secret_like_filename(path_part):
                line = "<redacted-secret-filename>" + sep + rest
        out_lines.append(line)
    return "\n".join(out_lines)


def _redact_filenames_in_diff_stat(diff_text: str) -> str:
    """Replace secret-like filenames in ``git diff --stat`` output.

    `git diff --stat` lines look like ``  src/auth/login.py | 5 +-``. The
    filename is the part before `` | `` (with leading whitespace). Footer
    lines (``N files changed``) don't contain `` | `` so are left untouched.
    """
    if not diff_text:
        return diff_text
    out_lines: list[str] = []
    for line in diff_text.splitlines():
        if " | " in line:
            fname_part, rest = line.split(" | ", 1)
            filename = fname_part.strip()
            if is_secret_like_filename(filename):
                indent_len = len(fname_part) - len(fname_part.lstrip())
                indent = fname_part[:indent_len]
                line = f"{indent}<redacted-secret-filename> | {rest}"
        out_lines.append(line)
    return "\n".join(out_lines)


def _render_exit_detail(d: ExitDetail | None) -> str:
    if d is None:
        return "## Exit Code Detail\n\n_(not available)_"
    raw_part = str(d.raw_returncode)
    if d.raw_returncode_hex:
        raw_part += f" ({d.raw_returncode_hex})"
    lines = [
        "## Exit Code Detail",
        "",
        f"- wrapper exit: {d.wrapper_exit}",
        f"- subprocess raw returncode: {raw_part}",
        f"- platform: {d.platform}",
        f"- interpretation: {d.interpretation}",
        f"- interpretation source: {d.interpretation_source}",
    ]
    if d.interpretation_source == "unknown":
        lines.append("")
        lines.append(
            "> agentcam does not maintain a full NTSTATUS table; "
            "unknown high returncodes are reported via `raw_returncode` "
            "and `raw_returncode_hex` so a human can look them up."
        )
    return "\n".join(lines)


def _render_verification_placeholder() -> str:
    return (
        "## Verification\n\n"
        "- Tests observed: unknown (heuristic detection deferred to v0.2)\n"
        "- Build observed: unknown\n"
        "- Lint observed: unknown"
    )


def _render_rollback(manifest: RunManifest, state: GitState) -> str:
    has_changes = any(not _is_internal(cf.path) for cf in state.changed_files)
    failed = (
        manifest.exit_detail is not None
        and manifest.exit_detail.wrapper_exit != 0
    )

    if failed and not has_changes:
        return (
            "## Rollback Notes\n\n"
            "No repo changes detected; no rollback needed."
        )

    if manifest.pre_run_dirty:
        return (
            "## Rollback Notes\n\n"
            "Working tree was already dirty before this run. A single safe "
            "rollback command cannot be expressed.\n\n"
            "Manual review required. Compare the lists above against your "
            "pre-run state."
        )

    untracked = [
        cf for cf in state.changed_files
        if cf.status == "untracked" and not _is_internal(cf.path)
    ]
    visible_untracked: list[str] = []
    for cf in untracked:
        if is_secret_like_filename(cf.path):
            visible_untracked.append("<redacted-secret-filename>")
        else:
            visible_untracked.append(cf.path)

    if not visible_untracked:
        return (
            "## Rollback Notes\n\n"
            "Working tree was clean before this run. To discard tracked "
            "changes from this run:\n\n"
            "```bash\n"
            "git restore --staged .\n"
            "git restore .\n"
            "```\n\n"
            "No untracked files were created."
        )

    bullets = "\n".join(f"  - {u}" for u in visible_untracked)
    return (
        "## Rollback Notes\n\n"
        "Working tree was clean before this run. Agent created the following "
        "new files (untracked):\n\n"
        f"{bullets}\n\n"
        "To discard tracked changes:\n\n"
        "```bash\n"
        "git restore --staged .\n"
        "git restore .\n"
        "```\n\n"
        "The untracked files above are NOT removed by the commands above. "
        "Delete them manually after review.\n\n"
        "Do not run `git clean -fd` blindly. It will also delete other "
        "untracked files you may want to keep."
    )


def _render_logs(m: RunManifest) -> str:
    stdout_path = _relative_to_git_root(m.paths.stdout_redacted, m.git_root)
    stderr_path = _relative_to_git_root(m.paths.stderr_redacted, m.git_root)
    return (
        "## Logs\n\n"
        f"- stdout (redacted): `{stdout_path}`\n"
        f"- stderr (redacted): `{stderr_path}`\n\n"
        "> Raw logs (`stdout.log`, `stderr.log`) are kept for forensic review "
        "but should not be shared. They live under `.git/`, so they are NOT "
        "tracked by git, but they CAN be picked up by cloud sync, system "
        "backups, or by sharing the entire `.git/` directory."
    )


def _render_local_artifacts(m: RunManifest) -> str:
    manifest_path = _relative_to_git_root(m.paths.manifest_json, m.git_root)
    report_path = _relative_to_git_root(m.paths.report_md, m.git_root)
    run_dir = _relative_to_git_root(m.paths.run_dir, m.git_root)
    return (
        "## Local Artifacts\n\n"
        f"- manifest: `{manifest_path}`\n"
        f"- this report: `{report_path}`\n"
        f"- run directory: `{run_dir}`"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_internal(path: str) -> bool:
    norm = path.replace("\\", "/")
    return norm.startswith(".git/agentcam/") or "/agentcam/runs/" in norm


def _relative_to_git_root(absolute_path: str, git_root: str) -> str:
    """Render ``absolute_path`` as a forward-slash path relative to git_root.

    Falls back to the original string if the path isn't under git_root
    (defensive). Avoids leaking absolute paths (which contain the username
    and full repo location) into the user-shareable Markdown report.
    Codex source-review HIGH.
    """
    try:
        abs_p = Path(absolute_path).resolve()
        root_p = Path(git_root).resolve()
        return abs_p.relative_to(root_p).as_posix()
    except (ValueError, OSError):
        return absolute_path
