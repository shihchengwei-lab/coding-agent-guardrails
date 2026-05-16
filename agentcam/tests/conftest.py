"""Shared pytest fixtures for agentbox tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _run_git(cwd: Path, *args: str) -> None:
    """Run git with --quiet-friendly settings, raising on failure."""
    env_args = [
        "-c", "user.email=test@example.com",
        "-c", "user.name=Test",
        "-c", "commit.gpgsign=false",
        "-c", "tag.gpgsign=false",
    ]
    subprocess.run(
        ["git", *env_args, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """A temporary git repo with an initial empty commit on `main`.

    Returns the working tree root. Use this for any test that needs a real
    git directory (e.g. git_state, runner end-to-end).
    """
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    _run_git(tmp_path, "commit", "-q", "--allow-empty", "-m", "init")
    return tmp_path
