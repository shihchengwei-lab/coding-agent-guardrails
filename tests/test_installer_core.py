from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from installer import guardrails_installer as installer


ROOT = Path(__file__).resolve().parents[1]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
    ).stdout.strip()


def init_repo(path: Path) -> Path:
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    return path


def test_repository_discovery_requires_worktree_root(tmp_path: Path):
    repo = init_repo(tmp_path / "repo")
    subdir = repo / "src"
    subdir.mkdir()

    discovered = installer.discover_repository(repo)
    assert discovered.root == repo.resolve()
    assert discovered.git_dir == Path(
        git(repo, "rev-parse", "--absolute-git-dir")
    ).resolve()

    with pytest.raises(installer.InstallerError, match="worktree top-level"):
        installer.discover_repository(subdir)

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    with pytest.raises(installer.InstallerError, match="bare"):
        installer.discover_repository(bare)


def test_hook_merge_removes_only_managed_hook_from_mixed_group():
    existing = {
        "hooks": {
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {"type": "command", "command": "user-existing-hook"},
                        {
                            "type": "command",
                            "command": "python old/patch-cost",
                        },
                    ],
                }
            ]
        }
    }
    managed = {
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "/git/guardrails/env/python /git/runtime/patch-cost",
                        "guardrails_managed": "slime-stop",
                    }
                ]
            }
        ]
    }

    merged = installer.merge_hooks(existing, managed)
    commands = [
        hook["command"]
        for group in merged["hooks"]["Stop"]
        for hook in group["hooks"]
    ]
    assert "user-existing-hook" in commands
    assert not any("old/patch-cost" in command for command in commands)
    assert any("/git/runtime/patch-cost" in command for command in commands)


def test_atomic_transaction_restores_files_and_removes_new_paths(tmp_path: Path):
    existing = tmp_path / "AGENTS.md"
    created = tmp_path / ".codex" / "hooks.json"
    existing.write_text("user text\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="fault"):
        with installer.FileTransaction(tmp_path) as transaction:
            transaction.write_text(existing, "changed\n")
            transaction.write_text(created, "{}\n")
            raise RuntimeError("fault injection")

    assert existing.read_text(encoding="utf-8") == "user text\n"
    assert not created.exists()
    assert not list(tmp_path.rglob("*.bak-*"))


def test_dry_run_reports_plan_without_mutating_repo(tmp_path: Path, capsys):
    repo = init_repo(tmp_path / "repo")
    workflow = repo / ".github" / "workflows" / "corridor.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("# user workflow\n", encoding="utf-8")

    result = installer.main(
        ["install", str(repo), "--source", str(ROOT), "--dry-run"]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "DRY RUN" in output
    assert "update AGENTS.md and CLAUDE.md" in output
    assert "custom workflow preserved" in output
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / ".codex").exists()
    assert not (installer.discover_repository(repo).git_dir / "guardrails").exists()


def test_shell_entrypoints_are_thin_python_launchers():
    posix = (ROOT / "install.sh").read_text(encoding="utf-8")
    powershell = (ROOT / "install.ps1").read_text(encoding="utf-8-sig")

    for entrypoint in (posix, powershell):
        assert "installer/guardrails_installer.py" in entrypoint.replace("\\", "/")
        assert "pip install" not in entrypoint
        assert "coding-agent-guardrails:discipline:start" not in entrypoint
        assert "hook-turn-start" not in entrypoint


@pytest.mark.parametrize("readme_name", ["README.md", "README.zh-TW.md"])
def test_readmes_document_installer_lifecycle(readme_name: str):
    readme = (ROOT / readme_name).read_text(encoding="utf-8")

    assert "<git-dir>/guardrails/" in readme
    assert "guardrails check set primary --" in readme
    assert "guardrails doctor" in readme
    assert "guardrails uninstall --dry-run" in readme
    assert "--purge-state" in readme


def test_installed_workflow_has_stable_context_and_minimal_permissions():
    workflow = (ROOT / "corridor-ci" / "examples" / "workflow.yml").read_text(
        encoding="utf-8"
    )

    assert "permissions:\n  contents: read" in workflow
    assert "jobs:\n  corridor:\n    name: Corridor" in workflow
    assert "corridor-ci@corridor-ci-v13.0.0" in workflow
    assert "pull-requests: write" not in workflow


def test_toolkit_ci_watches_shared_installer_core():
    workflow = (ROOT / ".github" / "workflows" / "toolkit.yml").read_text(
        encoding="utf-8"
    )
    assert "'installer/**'" in workflow


def test_doctor_remote_is_explicit_opt_in():
    local = installer.build_parser().parse_args(["doctor"])
    remote = installer.build_parser().parse_args(["doctor", "--remote"])
    assert local.remote is False
    assert remote.remote is True


def test_remote_context_evaluation_requires_corridor():
    assert installer.remote_context_problem({"Corridor", "Tests"}) is None
    assert "Corridor" in installer.remote_context_problem({"Tests"})


def test_check_set_writes_trusted_argv_without_shell_string(tmp_path: Path):
    repo = init_repo(tmp_path / "repo")
    git_dir = installer.discover_repository(repo).git_dir

    assert installer.main(
        [
            "check",
            "set",
            "primary",
            "--repo",
            str(repo),
            "--",
            "python",
            "-m",
            "pytest",
            "-q",
        ]
    ) == 0

    config = json.loads(
        (git_dir / "guardrails" / "config.json").read_text(encoding="utf-8")
    )
    assert config == {
        "schema": 1,
        "checks": {
            "primary": {
                "argv": ["python", "-m", "pytest", "-q"],
                "timeout_seconds": 600,
            }
        },
    }


def test_upgrade_manifest_retains_owned_versions_for_uninstall():
    previous = {
        "owned_versions": [
            {"revision": "old", "runtime": "/git/runtime/old", "environment": "/git/envs/old"}
        ]
    }
    current = {
        "revision": "new",
        "runtime": "/git/runtime/new",
        "environment": "/git/envs/new",
    }

    assert installer.merge_owned_versions(previous, current) == [
        {"revision": "old", "runtime": "/git/runtime/old", "environment": "/git/envs/old"},
        {"revision": "new", "runtime": "/git/runtime/new", "environment": "/git/envs/new"},
    ]


def test_uninstall_preserves_state_unless_purge_is_explicit(tmp_path: Path):
    repo = init_repo(tmp_path / "repo")
    git_dir = installer.discover_repository(repo).git_dir
    guardrails = git_dir / "guardrails"
    guardrails.mkdir()
    manifest = {"schema": 1, "revision": "test", "files": {}, "owned_versions": []}
    (guardrails / "install.json").write_text(json.dumps(manifest), encoding="utf-8")
    (guardrails / "config.json").write_text('{"schema":1,"checks":{}}', encoding="utf-8")
    (guardrails / "history.json").write_text("{}", encoding="utf-8")
    (repo / ".slime").mkdir()
    (repo / ".slime" / "PRUNED.md").write_text("history", encoding="utf-8")

    assert installer.uninstall(repo) == 0
    assert (guardrails / "config.json").is_file()
    assert (guardrails / "history.json").is_file()
    assert (repo / ".slime" / "PRUNED.md").is_file()

    (guardrails / "install.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert installer.uninstall(repo, purge_state=True) == 0
    assert not guardrails.exists()
    assert not (repo / ".slime").exists()


def test_uninstall_never_follows_manifest_paths_outside_repo(tmp_path: Path, capsys):
    repo = init_repo(tmp_path / "repo")
    outside = tmp_path / "outside.txt"
    outside.write_text("do not delete\n", encoding="utf-8")
    guardrails = installer.discover_repository(repo).git_dir / "guardrails"
    guardrails.mkdir()
    manifest = {
        "schema": 1,
        "revision": "tampered",
        "files": {
            "../outside.txt": {
                "kind": "managed-file",
                "sha256": installer._tree_hash(outside),
            }
        },
        "owned_versions": [],
    }
    (guardrails / "install.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert installer.uninstall(repo) == 0
    assert outside.read_text(encoding="utf-8") == "do not delete\n"
    assert "unsafe manifest path preserved" in capsys.readouterr().out


def test_install_rejects_managed_path_through_symlink(tmp_path: Path, monkeypatch):
    repo = init_repo(tmp_path / "repo")
    original = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == repo / ".codex" or original(path),
    )

    with pytest.raises(installer.InstallerError, match="symbolic link"):
        installer.validate_managed_destinations(repo)


@pytest.mark.parametrize("check_id", ["UPPER", "has space", "", "x" * 65])
def test_check_set_rejects_invalid_ids(tmp_path: Path, check_id: str):
    repo = init_repo(tmp_path / ("repo-" + str(len(check_id))))
    with pytest.raises(installer.InstallerError, match="check ID"):
        installer.set_check(repo, check_id, ["python", "-V"], 600)
