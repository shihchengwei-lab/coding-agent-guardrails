"""Shared subprocess harness for the CLI-driving test modules.

test_e2e / test_export / test_handoff / test_verify all drive agentcam
as a real subprocess; these helpers were duplicated per file and are
consolidated here so the backend-injection logic has a single locus.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Routine coverage runs `agentcam run` on the cheap PIPE backend (the
# PTY default costs a ConPTY/pty spawn per test on top of the
# subprocess). PTY-specific behavior is exercised by the dedicated
# backend tests, which opt out via run_backend=None.
LIGHTWEIGHT_RUN_BACKEND = "pipe"


def _agentcam(
    cwd: Path,
    *args: str,
    env: dict | None = None,
    run_backend: str | None = LIGHTWEIGHT_RUN_BACKEND,
) -> subprocess.CompletedProcess:
    """Invoke agentcam via the same Python that's running pytest."""
    argv = list(args)
    if argv and argv[0] == "run" and run_backend and "--backend" not in argv:
        argv[1:1] = ["--backend", run_backend]
    return subprocess.run(
        [sys.executable, "-m", "agentcam.cli", *argv],
        cwd=cwd,
        capture_output=True,
        timeout=25,
        env=env,
    )


def _run_dir(repo: Path) -> Path:
    return next((repo / ".git" / "agentcam" / "runs").iterdir())


def _report(repo: Path) -> str:
    return (_run_dir(repo) / "AGENT_RUN_REPORT.md").read_text(encoding="utf-8")


def _manifest(repo: Path) -> dict:
    return json.loads(
        (_run_dir(repo) / "manifest.json").read_text(encoding="utf-8")
    )


def _make_one_run(
    repo: Path,
    py_body: str = "open('produced.txt','w').write('hi')",
) -> str:
    """Produce one diff-bearing run and return its run_id."""
    proc = _agentcam(repo, "run", "--", sys.executable, "-c", py_body)
    assert proc.returncode == 0, proc.stderr
    return _run_dir(repo).name
