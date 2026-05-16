"""Data structures used across agentbox modules.

Plain dataclasses (no Pydantic) to keep dependencies to the standard library
only. JSON serialization is done by ``report.py`` and the manifest writer, not
by these classes.

See ``docs/design.md`` (forthcoming) for the schema design rationale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

# Two-level risk taxonomy (v0.1). LOW was dropped — see design.md decision 8.
RiskLevel = Literal["HIGH", "MEDIUM"]

ChangeStatus = Literal[
    "staged",
    "staged_deleted",
    "unstaged_modified",
    "unstaged_deleted",
    "untracked",
    "renamed",
    "unmerged",
]

# Source of the exit interpretation in manifest.exit_detail.
InterpretationSource = Literal[
    "known_table",
    "signal",
    "user_defined",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class RunId:
    """Identifier for an agentbox run.

    Format: ``YYYYMMDD-HHMMSS-<ms>-<slug>[-<hex>]``
    where ``<hex>`` is a 4-char collision-avoidance suffix added on retry.
    """

    text: str

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class RunPaths:
    """Filesystem layout for a single agentbox run.

    All paths live under ``<git_dir>/agentbox/runs/<run_id>/``. ``git_dir`` is
    the *real* git dir as resolved by ``git rev-parse --git-dir`` (handles
    worktrees and submodule gitlinks correctly).
    """

    run_dir: str
    manifest_json: str
    report_md: str
    stdout_raw: str
    stderr_raw: str
    stdout_redacted: str
    stderr_redacted: str


@dataclass
class ChangedFile:
    """A file modified between pre-run and post-run git state."""

    path: str
    status: ChangeStatus
    rename_from: str | None = None
    secret_like_name: bool = False  # True if filename matches secret-like pattern


@dataclass
class RiskFlag:
    """A single risk observation. evidence must not contain raw secrets."""

    level: RiskLevel
    rule: str
    evidence: str


@dataclass
class GitState:
    """Snapshot of git state (before or after the wrapped command)."""

    head: str | None
    branch: str | None
    is_detached_head: bool
    porcelain_raw: bytes
    diff_stat: str
    diff_stat_cached: str
    diff_name_status: str
    diff_name_status_cached: str
    diff_check: str = ""
    diff_check_cached: str = ""
    pre_existing_op: str | None = None  # 'merge' | 'rebase' | 'cherry-pick' | ...
    changed_files: list[ChangedFile] = field(default_factory=list)


@dataclass
class ExitDetail:
    """Exit status detail, written to manifest and Exit Code Detail section.

    See plan section 9 (Exit code pass-through).
    """

    wrapper_exit: int  # 0 or 1
    raw_returncode: int
    raw_returncode_hex: str | None
    platform: str
    interpretation: str
    interpretation_source: InterpretationSource


@dataclass
class RunManifest:
    """Top-level run manifest, serialized to ``manifest.json``."""

    schema_version: str
    run_id: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float | None
    cwd: str
    git_root: str
    git_dir: str
    branch: str | None
    is_detached_head: bool
    head_before: str | None
    head_after: str | None
    pre_existing_op: str | None
    pre_run_dirty: bool
    command_argv_raw: list[str]
    command_argv_redacted: list[str]
    exit_detail: ExitDetail | None
    shell_used: bool
    terminal_forward_degraded: bool
    platform: str
    agentbox_version: str
    paths: RunPaths
