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
from datetime import datetime
from pathlib import Path

from agentcam import __version__
from agentcam.models import (
    CaptureCapability,
    ChangedFile,
    DependencyChange,
    ExitDetail,
    GitState,
    ReportBundle,
    RiskFlag,
    RulesetProvenance,
    RunManifest,
    RunPaths,
)
from agentcam.scanner import is_secret_like_filename


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def render_report(
    bundle_or_manifest: ReportBundle | RunManifest,
    state_before: GitState | None = None,
    state_after: GitState | None = None,
    risk_flags: list[RiskFlag] | None = None,
    dependency_changes: list[DependencyChange] | None = None,
) -> str:
    """Render the full ``AGENT_RUN_REPORT.md`` as a string.

    Two call shapes are accepted:

    1. **Bundle form (preferred for new code)** —
       ``render_report(bundle)`` where ``bundle`` is a
       :class:`ReportBundle`. New renderers (SARIF, PR-comment) will
       take a Bundle too, so consolidating on this shape keeps the
       producer/consumer contract narrow.

    2. **Legacy positional form** —
       ``render_report(manifest, state_before, state_after,
       risk_flags, dependency_changes=None)``. Kept so existing tests
       and any external callers don't break in one big-bang change;
       internally it just builds a Bundle and dispatches to the same
       code path.
    """
    if isinstance(bundle_or_manifest, ReportBundle):
        bundle = bundle_or_manifest
    else:
        # Legacy positional path. Use a proper TypeError instead of
        # `assert` so the requirement survives ``python -O`` and
        # surfaces clearly rather than as a downstream NoneType crash.
        if state_before is None or state_after is None:
            raise TypeError(
                "render_report: legacy positional form requires both "
                "state_before and state_after"
            )
        bundle = ReportBundle(
            manifest=bundle_or_manifest,
            state_before=state_before,
            state_after=state_after,
            risk_flags=list(risk_flags or []),
            dependency_changes=list(dependency_changes or []),
        )

    manifest = bundle.manifest
    sections: list[str] = [
        _render_header(manifest),
        _render_capture_visibility(manifest.capture),
        _render_verdict(bundle.risk_flags),
        _render_risk_flags(bundle.risk_flags),
        _render_changed_files(bundle.state_after),
        _render_dependency_changes(bundle.dependency_changes, manifest),
        _render_diff_stat(bundle.state_after),
        _render_exit_detail(manifest.exit_detail),
        _render_verification_placeholder(),
        _render_rollback(manifest, bundle.state_after),
        _render_logs(manifest),
        _render_scanner_ruleset(manifest.ruleset),
        _render_local_artifacts(manifest),
    ]
    return "\n\n".join(s for s in sections if s)


def write_run_artifacts(
    *,
    state_before: GitState,
    state_after: GitState,
    risk_flags: list[RiskFlag],
    cwd: Path,
    git_dir: Path,
    git_root: Path,
    run_paths: RunPaths,
    run_id: str,
    started_at: datetime,
    ended_at: datetime,
    command_argv_raw: list[str],
    command_argv_redacted: list[str],
    exit_detail: ExitDetail | None,
    shell_used: bool,
    terminal_forward_degraded: bool,
    platform_label: str,
    capture: CaptureCapability | None = None,
    ruleset: RulesetProvenance | None = None,
) -> ReportBundle:
    """Build manifest + Bundle, render report, write both artifacts.

    Shared post-run orchestration used by wrap mode (``cli.py``) and
    hook mode (``hooks.py``). The function:

    1. runs the dependency-manifest probe against ``state_after.changed_files``
    2. builds the :class:`RunManifest` from the supplied fields
    3. builds the :class:`ReportBundle` (manifest + states + flags + deps)
    4. writes ``AGENT_RUN_REPORT.md`` to ``run_paths.report_md``
    5. writes ``manifest.json`` to ``run_paths.manifest_json``
    6. returns the Bundle so callers (and tests) can inspect it

    Caller responsibilities:
    - Pass already-resolved, repo-trusted ``cwd`` / ``git_dir`` /
      ``git_root`` paths. The helper performs no path validation; it
      shells out to ``git show HEAD:<path>`` via ``cwd`` inside the
      dep probe, so an attacker-controlled ``cwd`` would shift the
      execution context. Callers obtain these from
      ``resolve_git_dir`` / ``resolve_git_root`` before any wrap- or
      hook-mode work begins.
    - Pass a pre-created ``run_paths`` whose ``run_dir`` already
      exists (callers use ``paths.create_run_dir`` for this). The
      helper writes report.md and manifest.json directly to
      ``run_paths`` without re-creating the parent.
    - Scan raw subprocess logs for output-pattern flags and combine
      into ``risk_flags`` before calling (hook mode has no logs, so
      passes a path-scan-only list).
    - Write any placeholder log files needed by the report's "Logs"
      section before calling (hook mode does this; wrap mode's tee
      threads already wrote real logs).
    - Wrap this call in try/except/finally if the call site has
      cleanup obligations (e.g. hook mode's orphan run-dir cleanup).
    """
    from agentcam.dependency_probe import scan_dependencies

    dependency_changes = scan_dependencies(
        cwd=cwd,
        changed_manifest_paths=[cf.path for cf in state_after.changed_files],
    )

    duration = (ended_at - started_at).total_seconds()
    manifest = RunManifest(
        schema_version="0.1",
        run_id=run_id,
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
        pre_run_dirty=bool(state_before.changed_files),
        command_argv_raw=command_argv_raw,
        command_argv_redacted=command_argv_redacted,
        exit_detail=exit_detail,
        shell_used=shell_used,
        terminal_forward_degraded=terminal_forward_degraded,
        platform=platform_label,
        agentcam_version=__version__,
        paths=run_paths,
        capture=capture,
        ruleset=ruleset,
    )

    bundle = ReportBundle(
        manifest=manifest,
        state_before=state_before,
        state_after=state_after,
        risk_flags=list(risk_flags),
        dependency_changes=dependency_changes,
    )

    Path(run_paths.report_md).write_text(
        render_report(bundle),
        encoding="utf-8",
    )
    write_manifest(manifest, Path(run_paths.manifest_json))

    return bundle


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
    out: dict = {
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
    if m.capture is not None:
        # Block is omitted (not set to null) for legacy manifests so
        # JSON consumers can use `"capture" in data` to detect schema
        # presence cleanly. New production manifests always carry it.
        out["capture"] = _serialize_capture(m.capture)
    if m.ruleset is not None:
        out["ruleset"] = _serialize_ruleset(m.ruleset)
    return out


def _serialize_ruleset(p: RulesetProvenance) -> dict:
    return {
        "builtin_ruleset_id": p.builtin_ruleset_id,
        "builtin_ruleset_version": p.builtin_ruleset_version,
        "custom_rules_path": p.custom_rules_path,
        "custom_rules_sha256": p.custom_rules_sha256,
        "merged_rules_sha256": p.merged_rules_sha256,
        "load_status": p.load_status,
    }


def _serialize_capture(c: CaptureCapability) -> dict:
    return {
        "mode": c.mode,
        "stdout": c.stdout,
        "stderr": c.stderr,
        "git_before_after": c.git_before_after,
        "path_risk_scan": c.path_risk_scan,
        "output_risk_scan": c.output_risk_scan,
        "dependency_probe": c.dependency_probe,
        "transcript": c.transcript,
        "internal_tool_calls": c.internal_tool_calls,
        "file_reads": c.file_reads,
        "network_egress": c.network_egress,
        "empty_run_policy": c.empty_run_policy,
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


_CAPTURE_NOTE: dict[str, str] = {
    # mode
    "wrap_pipe": "Subprocess wrapped via stdout/stderr PIPE; logs tee'd to disk.",
    "wrap_pty": "Subprocess wrapped via PTY (Windows ConPTY / POSIX pty).",
    "claude_hook": "Recorded via Claude Code SessionStart / SessionEnd hooks; "
                   "no subprocess wrapping, no terminal output.",
    "ci": "Recorded inside a CI runner.",
    # stdout / stderr
    "captured": "Streamed bytes preserved to raw log.",
    "not_available": "Not piped through agentcam in this mode.",
    "placeholder": "Empty file written so the report template renders.",
    # scans
    "enabled": "Scanner produced flags for this run.",
    "disabled_no_output_stream": "No output stream to scan in this mode.",
    "disabled": "Scanner intentionally off for this run.",
    # transcript
    "not_supported": "Mode has no transcript concept.",
    "available_not_ingested": "Hook payload exposed a transcript_path; "
                              "agentcam does not parse it yet (v0.3+ work).",
    "ingested_redacted": "Transcript text was parsed and redacted into the report.",
    # visibility (internal calls / file reads / network)
    "not_visible": "Outside agentcam's observation surface in this mode.",
    "partially_visible": "Some events observed; coverage is best-effort, not complete.",
    "visible": "Fully observed for this run.",
    # empty-run policy
    "auto_delete_clean_no_diff": "Default: a clean no-diff successful run would "
                                  "be auto-deleted (this run was kept because it "
                                  "had a diff, risk evidence, or a non-zero exit).",
    "keep_empty_requested": "--keep-empty: cleanup skipped this invocation.",
    "preserve_visible_risk": "No git-visible diff, but output risk flags were "
                             "observed; report preserved.",
    "unknown": "(unknown)",
}


def _render_capture_visibility(c: CaptureCapability | None) -> str:
    """Render the `## Capture Visibility` section.

    Returns "" when ``c`` is None — legacy callers / fixtures that don't
    set capture continue producing the previous report shape. New
    production reports (wrap mode + hook mode) always include this
    block.
    """
    if c is None:
        return ""

    def row(signal: str, status: str) -> str:
        note = _CAPTURE_NOTE.get(status, "")
        return f"| {signal} | `{status}` | {note} |"

    lines = [
        "## Capture Visibility",
        "",
        "> What agentcam observed for this run. Cells named `not_visible` / "
        "`not_available` / `disabled_*` describe agentcam's coverage limits "
        "in this mode — they are not statements about what the agent did.",
        "",
        "| Signal | Status | Notes |",
        "|---|---|---|",
        row("mode", c.mode),
        row("stdout", c.stdout),
        row("stderr", c.stderr),
        row("git_before_after", c.git_before_after),
        row("path_risk_scan", c.path_risk_scan),
        row("output_risk_scan", c.output_risk_scan),
        row("dependency_probe", c.dependency_probe),
        row("transcript", c.transcript),
        row("internal_tool_calls", c.internal_tool_calls),
        row("file_reads", c.file_reads),
        row("network_egress", c.network_egress),
        row("empty_run_policy", c.empty_run_policy),
    ]
    return "\n".join(lines)


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


def _render_dependency_changes(
    changes: list[DependencyChange],
    manifest: RunManifest,
) -> str:
    """Render the optional 'Dependency Changes' section.

    Returns an empty string (suppresses the section) when there are no
    changes — keeps the report tidy on runs that didn't touch any
    manifest. When pre_run_dirty=True we add a one-line caveat because
    the diff is computed vs HEAD, not vs the actual pre-run working
    tree state.
    """
    if not changes:
        return ""

    # Group by (ecosystem, manifest_path) so the report reads well when
    # multiple manifests are touched in one run.
    grouped: dict[tuple[str, str], list[DependencyChange]] = {}
    for c in changes:
        grouped.setdefault((c.ecosystem, c.manifest_path), []).append(c)

    parts: list[str] = ["## Dependency Changes"]
    if manifest.pre_run_dirty:
        parts.append(
            "> Working tree was dirty before this run. Dependency diffs "
            "are computed vs `HEAD`, so any manifest edits you had "
            "staged or unstaged pre-run are attributed to this run."
        )

    for (ecosystem, path), entries in grouped.items():
        rows = [
            f"### `{path}` ({ecosystem})",
            "",
            "| Kind | Name | Before | After |",
            "|---|---|---|---|",
        ]
        for e in entries:
            before = _fmt_version(e.old_version)
            after = _fmt_version(e.new_version)
            rows.append(f"| {e.kind} | `{e.name}` | {before} | {after} |")
        parts.append("\n".join(rows))

    return "\n\n".join(parts)


def _fmt_version(v: str | None) -> str:
    if v is None:
        return "—"
    if v == "":
        return "(unpinned)"
    return f"`{v}`"


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


def _render_scanner_ruleset(p: RulesetProvenance | None) -> str:
    """Render the `## Scanner Ruleset` section.

    Compact: 4-5 lines, placed near the bottom of the report so it
    doesn't compete with risk flags for attention. Returns "" when
    ``p`` is None (legacy callers).
    """
    if p is None:
        return ""
    custom_path = p.custom_rules_path or "none"
    custom_hash = p.custom_rules_sha256 or "—"
    merged_hash = p.merged_rules_sha256 or "—"
    return (
        "## Scanner Ruleset\n\n"
        f"- Built-in ruleset: `{p.builtin_ruleset_id}` / `{p.builtin_ruleset_version}`\n"
        f"- Custom rules: {custom_path}\n"
        f"- Custom rules hash: `{custom_hash}`\n"
        f"- Merged rules hash: `{merged_hash}`\n"
        f"- Load status: `{p.load_status}`"
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
