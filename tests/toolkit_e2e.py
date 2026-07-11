"""Installed-toolkit end to end check for POSIX and Windows CI.

This intentionally executes commands read from the installed hooks JSON. It
does not import installer internals or synthesize Agentcam evidence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def run(argv, *, cwd: Path, env=None, input_text=None, check=True):
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        shell=isinstance(argv, str),
    )
    if check and proc.returncode:
        raise AssertionError(
            f"command failed ({proc.returncode}): {argv}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def git(repo: Path, *args: str):
    return run(["git", *args], cwd=repo)


def execute_hooks(
    hooks: dict,
    event: str,
    payload: dict,
    *,
    repo: Path,
    env: dict[str, str],
    command_key: str,
    matcher: str | None = None,
) -> str:
    outputs: list[str] = []
    hook_payload = dict(payload)
    hook_payload["hook_event_name"] = event
    for group in hooks.get(event, []):
        if matcher is not None and str(group.get("matcher", "")) != matcher:
            continue
        for hook in group.get("hooks", []):
            command = hook.get(command_key) or hook.get("command")
            assert command, (event, group)
            proc = run(
                command,
                cwd=repo,
                env=env,
                input_text=json.dumps(hook_payload),
            )
            outputs.extend((proc.stdout, proc.stderr))
    return "".join(outputs)


def write_corridor(repo: Path, python: Path) -> None:
    (repo / ".slime" / "corridor.md").write_text(
        """# Corridor: toolkit-e2e

## Rigor
normal

## Outcome
The installed product loop reaches a Corridor PASS from recorded evidence.

## Scope
Exercise the installed product loop.

## Paths
- src/app.py

## Semantic Delta
Change the installed E2E fixture.

## Non-goals
No dependency or public API changes.

## Goal Frontier
The installed hooks, recorder, export, and checker agree.

## Start Frontier
The repository has a committed installation and fixture.

## Evidence
- Supports: installed commands produce a matching local recording.
- Would falsify: any hook, verification, export, or corridor check fails.

## Stop Condition
- Check: primary
""",
        encoding="utf-8",
    )
    git_dir = Path(git(repo, "rev-parse", "--absolute-git-dir").stdout.strip())
    config = git_dir / "guardrails" / "config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "schema": 1,
                "checks": {
                    "primary": {
                        "argv": [
                            str(python),
                            "-c",
                            "from pathlib import Path; assert 'changed' in "
                            "Path('src/app.py').read_text()",
                        ],
                        "timeout_seconds": 60,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("posix", "windows"), required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="guardrails e2e ") as temp_text:
        temp = Path(temp_text)
        repo = temp / "project with spaces"
        venv = temp / "venv with spaces"
        toolkit = temp / "toolkit clone with spaces"
        shutil.copytree(
            ROOT,
            toolkit,
            ignore=shutil.ignore_patterns(
                ".git", ".pytest_cache", "__pycache__", "*.pyc", "dist", "build"
            ),
        )
        repo.mkdir()
        run([sys.executable, "-m", "venv", str(venv)], cwd=temp)
        bootstrap_python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        bindir = bootstrap_python.parent
        env = os.environ.copy()
        env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")

        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "e2e@example.com")
        git(repo, "config", "user.name", "Toolkit E2E")
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("original = True\n", encoding="utf-8")

        if args.platform == "posix":
            run(["bash", str(toolkit / "install.sh"), str(repo)], cwd=toolkit, env=env)
            hooks_path = repo / ".claude" / "settings.json"
            command_key = "command"
            id_field = "session_id"
            start_event, end_event = "SessionStart", "SessionEnd"
        else:
            run(
                [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(toolkit / "install.ps1"),
                    "-Project", str(repo), "-Python", str(bootstrap_python),
                ],
                cwd=toolkit,
                env=env,
            )
            hooks_path = repo / ".codex" / "hooks.json"
            command_key = "commandWindows"
            id_field = "turn_id"
            start_event, end_event = "UserPromptSubmit", "Stop"

        git_dir = Path(git(repo, "rev-parse", "--absolute-git-dir").stdout.strip())
        manifest = json.loads(
            (git_dir / "guardrails" / "install.json").read_text(encoding="utf-8")
        )
        python = Path(manifest["python"])
        assert python.is_file(), manifest
        assert str(toolkit) not in hooks_path.read_text(encoding="utf-8-sig")
        shutil.rmtree(toolkit)

        hooks = json.loads(hooks_path.read_text(encoding="utf-8-sig"))["hooks"]
        write_corridor(repo, python)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "installed baseline")
        git(repo, "switch", "-qc", "feature/e2e")

        payload = {id_field: "toolkit-e2e", "cwd": str(repo)}
        execute_hooks(
            hooks, start_event, payload, repo=repo, env=env,
            command_key=command_key,
        )
        # Claude's turn baseline is refreshed through UserPromptSubmit while
        # Agentcam keeps the original SessionStart snapshot.
        if args.platform == "posix":
            execute_hooks(
                hooks, "UserPromptSubmit", payload, repo=repo, env=env,
                command_key=command_key,
            )

        (repo / "src" / "app.py").write_text("changed = True\n", encoding="utf-8")
        verify = run(
            [str(python), "-m", "agentcam.cli", "verify", "--", str(python), "-c", "print('verified')"],
            cwd=repo,
            env=env,
        )
        assert verify.returncode == 0

        if args.platform == "posix":
            stop_output = execute_hooks(
                hooks, "Stop", payload, repo=repo, env=env,
                command_key=command_key,
            )
            assert '"block"' not in stop_output, stop_output
            execute_hooks(
                hooks, end_event, payload, repo=repo, env=env,
                command_key=command_key,
            )
        else:
            stop_output = execute_hooks(
                hooks, end_event, payload, repo=repo, env=env,
                command_key=command_key,
            )
            assert '"block"' not in stop_output, stop_output

        handoff = run(
            [str(python), "-m", "agentcam.cli", "handoff", "latest"],
            cwd=repo,
            env=env,
        ).stdout.strip()
        assert "[locally recorded by agentcam]" in handoff, handoff
        lines = []
        for line in handoff.splitlines():
            if line.startswith("Decision:"):
                line = "Decision: https://example.invalid/issues/1"
            elif line.startswith("Scope:"):
                line += ", .agentcam/**"
            lines.append(line)
        handoff = "\n".join(lines)
        run(
            [str(python), "-m", "agentcam.cli", "export", "latest", "--files", ".agentcam/"],
            cwd=repo,
            env=env,
        )
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "exercise product loop")

        event = temp / "event.json"
        event.write_text(
            json.dumps({"pull_request": {"number": 1, "body": handoff}}),
            encoding="utf-8",
        )
        corridor_env = env | {
            "GITHUB_EVENT_PATH": str(event),
            "GITHUB_BASE_REF": "main",
        }
        checked = run(
            [str(python), str(ROOT / "corridor-ci" / "bin" / "corridor_ci.py"), "--repo", str(repo)],
            cwd=repo,
            env=corridor_env,
        )
        assert "# Corridor CI: PASS" in checked.stdout, checked.stdout
        assert "local-recorded" in checked.stdout, checked.stdout

        # A later shell write outside the corridor is observable immediately
        # after Bash and remains a final Stop blocker.
        outside_payload = {id_field: "outside-e2e", "cwd": str(repo), "tool_name": "Bash"}
        execute_hooks(
            hooks, start_event, outside_payload, repo=repo, env=env,
            command_key=command_key,
        )
        (repo / "outside.txt").write_text("outside\n", encoding="utf-8")
        post_output = execute_hooks(
            hooks, "PostToolUse", outside_payload, repo=repo, env=env,
            command_key=command_key, matcher="Bash",
        )
        assert '"block"' in post_output and "already occurred" in post_output, post_output
        stop_output = execute_hooks(
            hooks, "Stop", outside_payload, repo=repo, env=env,
            command_key=command_key,
        )
        assert '"block"' in stop_output, stop_output

    print(f"toolkit E2E ({args.platform}) OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
