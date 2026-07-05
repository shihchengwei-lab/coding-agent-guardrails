"""Path layout and run-id generation for agentcam.

Run output is always written under ``<git_dir>/agentcam/runs/<run_id>/``.
``git_dir`` must be resolved by ``git rev-parse --git-dir`` so that worktree
and submodule gitlink cases (where ``<repo>/.git`` is a file, not a dir) are
handled correctly. See plan section 1 (output location) and section 4 (git
state collection).
"""
from __future__ import annotations

import os
import re
import secrets
from datetime import datetime
from pathlib import Path

from agentcam.models import RunId, RunPaths

# Maximum slug length (after sanitization). Keeps run-id readable.
_SLUG_MAX_LEN = 40
# Number of collision-retry attempts before giving up.
_COLLISION_RETRIES = 3
# Default slug when --name is not provided.
_DEFAULT_SLUG = "run"


class RunIdCollisionError(RuntimeError):
    """Raised when no unique run directory can be created after retries.

    The CLI maps this to exit code 2 (distinct from "wrapped subprocess
    failed = 1"). See plan section 13.
    """


def slugify(name: str | None) -> str:
    """Lowercase, replace non-[a-z0-9-] with '-', collapse, trim length."""
    if not name:
        return _DEFAULT_SLUG
    s = name.lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        return _DEFAULT_SLUG
    trimmed = s[:_SLUG_MAX_LEN].rstrip("-")
    return trimmed or _DEFAULT_SLUG


def format_run_id(now: datetime, slug: str, suffix: str | None = None) -> RunId:
    """Format a run id: ``YYYYMMDD-HHMMSS-<ms>-<slug>[-<hex>]``."""
    ms = f"{now.microsecond // 1000:03d}"
    parts = [now.strftime("%Y%m%d-%H%M%S"), ms, slug]
    if suffix:
        parts.append(suffix)
    return RunId("-".join(parts))


def make_run_paths(run_dir: Path) -> RunPaths:
    """Compute the per-run file layout under ``run_dir``."""
    return RunPaths(
        run_dir=str(run_dir),
        manifest_json=str(run_dir / "manifest.json"),
        report_md=str(run_dir / "AGENT_RUN_REPORT.md"),
        stdout_raw=str(run_dir / "stdout.log"),
        stderr_raw=str(run_dir / "stderr.log"),
        stdout_redacted=str(run_dir / "stdout.redacted.log"),
        stderr_redacted=str(run_dir / "stderr.redacted.log"),
    )


def create_run_dir(
    git_dir: Path,
    now: datetime,
    name: str | None = None,
) -> tuple[RunId, RunPaths]:
    """Create ``<git_dir>/agentcam/runs/<run_id>/`` with collision retry.

    Uses ``os.makedirs(exist_ok=False)`` so concurrent runs cannot silently
    share a directory. Retries up to ``_COLLISION_RETRIES`` times with a fresh
    4-char hex suffix on collision; raises :class:`RunIdCollisionError` if all
    retries collide (extremely unlikely outside contrived race conditions).
    """
    slug = slugify(name)
    base = git_dir / "agentcam" / "runs"

    tried: list[str] = []
    suffix: str | None = None
    for _ in range(_COLLISION_RETRIES + 1):
        run_id = format_run_id(now, slug, suffix)
        run_dir = base / run_id.text
        try:
            os.makedirs(run_dir, exist_ok=False)
        except FileExistsError:
            tried.append(run_id.text)
            suffix = secrets.token_hex(2)  # 4 hex chars
            continue
        return run_id, make_run_paths(run_dir)

    raise RunIdCollisionError(
        "Another agentcam run is starting at the same millisecond. "
        "Wait 1 second and retry, or pass `--name` with a unique slug. "
        f"Tried: {tried}"
    )
