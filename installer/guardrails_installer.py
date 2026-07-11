#!/usr/bin/env python3
"""Transactional, per-repository installer for coding-agent-guardrails.

The shell and PowerShell entrypoints intentionally delegate here so install,
upgrade, doctor, and uninstall share one ownership model on every platform.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence
import uuid


SCHEMA = 1
DEFAULT_TIMEOUT = 600
OFFICIAL_WORKFLOW_HASHES = {
    # corridor-ci/examples/workflow.yml from the immutable v13.0.0 release.
    "bf11e60c97edb5323cf0df4042335013d2f24818efae7a63d343a013ffa901e8",
}
CHECK_ID = re.compile(r"^[a-z0-9_-]{1,64}$")
BLOCK_START = "<!-- coding-agent-guardrails:discipline:start -->"
BLOCK_END = "<!-- coding-agent-guardrails:discipline:end -->"
MANAGED_HOOK_TOKENS = (
    "guardrails_managed",
    "patch-cost",
    # Upgrade cleanup only: recognize hooks installed by pre-v14 releases.
    "prune-inject",
    "hook-turn-start",
    "hook-turn-end",
    "hook-session-start",
    "hook-session-end",
)
MANAGED_RELATIVE_PATHS = {
    "AGENTS.md",
    "CLAUDE.md",
    ".codex/hooks.json",
    ".claude/settings.json",
    ".github/workflows/corridor.yml",
    "guardrails",
    "guardrails.cmd",
}


class InstallerError(RuntimeError):
    """An expected, user-actionable installer failure."""


@dataclass(frozen=True)
class Repository:
    root: Path
    git_dir: Path


def _run(
    argv: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [str(value) for value in argv],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    if check and process.returncode:
        detail = (process.stderr or process.stdout).strip()
        raise InstallerError(f"command failed ({process.returncode}): {' '.join(map(str, argv))}\n{detail}")
    return process


def discover_repository(project: str | os.PathLike[str]) -> Repository:
    requested = Path(project).expanduser().resolve()
    if not requested.exists() or not requested.is_dir():
        raise InstallerError(f"target does not exist or is not a directory: {requested}")
    bare = _run(
        ["git", "-C", requested, "rev-parse", "--is-bare-repository"],
        check=False,
    )
    if bare.returncode == 0 and bare.stdout.strip() == "true":
        raise InstallerError(f"target must be a worktree; bare repositories are not supported: {requested}")
    top = _run(["git", "-C", requested, "rev-parse", "--show-toplevel"], check=False)
    if top.returncode:
        raise InstallerError(f"target must be a git worktree: {requested}")
    root = Path(top.stdout.strip()).resolve()
    if requested != root:
        raise InstallerError(f"target must be the worktree top-level: {root}")
    git_dir = Path(
        _run(["git", "-C", root, "rev-parse", "--absolute-git-dir"]).stdout.strip()
    ).resolve()
    return Repository(root=root, git_dir=git_dir)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_text = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(temporary_text)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


class FileTransaction:
    """Back up a finite set of paths and restore them unless committed."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.journal = Path(tempfile.mkdtemp(prefix="guardrails-journal-"))
        self._snapshots: dict[Path, tuple[str, Path | None]] = {}
        self._created_parents: set[Path] = set()
        self._committed = False

    def __enter__(self) -> "FileTransaction":
        return self

    def _snapshot(self, path: Path) -> None:
        # Keep the path identity itself. resolve() would turn a symlink into
        # its target and make rollback restore the wrong filesystem object.
        path = Path(os.path.abspath(path))
        if path in self._snapshots:
            return
        if not path.exists() and not path.is_symlink():
            self._snapshots[path] = ("missing", None)
            parent = path.parent
            while parent != parent.parent and not parent.exists():
                self._created_parents.add(parent)
                parent = parent.parent
            return
        backup = self.journal / str(len(self._snapshots))
        if path.is_dir() and not path.is_symlink():
            shutil.copytree(path, backup, symlinks=True)
            self._snapshots[path] = ("dir", backup)
        else:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup, follow_symlinks=False)
            self._snapshots[path] = ("file", backup)

    def write_bytes(self, path: Path, data: bytes) -> None:
        self._snapshot(path)
        _atomic_write(path, data)

    def write_text(self, path: Path, text: str) -> None:
        self.write_bytes(path, text.encode("utf-8"))

    def replace_tree(self, path: Path, source: Path) -> None:
        self._snapshot(path)
        temporary = path.with_name(path.name + ".tmp." + uuid.uuid4().hex)
        _remove(temporary)
        temporary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, temporary, symlinks=True)
        _remove(path)
        os.replace(temporary, path)

    def remove(self, path: Path) -> None:
        self._snapshot(path)
        _remove(path)

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        for path, (kind, backup) in reversed(list(self._snapshots.items())):
            _remove(path)
            if kind == "dir" and backup is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(backup, path, symlinks=True)
            elif kind == "file" and backup is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, path, follow_symlinks=False)
        for parent in sorted(self._created_parents, key=lambda item: len(item.parts), reverse=True):
            try:
                parent.rmdir()
            except OSError:
                pass

    def __exit__(self, exc_type, exc, traceback) -> bool:
        try:
            if exc_type is not None or not self._committed:
                self.rollback()
        finally:
            shutil.rmtree(self.journal, ignore_errors=True)
        return False


def _managed_hook(hook: dict[str, Any]) -> bool:
    if hook.get("guardrails_managed"):
        return True
    commands = f"{hook.get('command', '')} {hook.get('commandWindows', '')}"
    return any(token in commands for token in MANAGED_HOOK_TOKENS[1:])


def merge_hooks(existing: dict[str, Any], managed: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Replace only our hook entries, retaining user hooks in mixed groups."""
    result = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    hooks = result.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        result["hooks"] = hooks
    events = set(hooks) | set(managed)
    for event in events:
        kept_groups: list[dict[str, Any]] = []
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            groups = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            filtered = [
                hook
                for hook in group.get("hooks", [])
                if isinstance(hook, dict) and not _managed_hook(hook)
            ]
            if filtered:
                preserved = copy.deepcopy(group)
                preserved["hooks"] = filtered
                kept_groups.append(preserved)
        hooks[event] = kept_groups + copy.deepcopy(managed.get(event, []))
    return result


def _remove_managed_hooks(existing: dict[str, Any]) -> dict[str, Any]:
    return merge_hooks(existing, {})


def _managed_block(original: str, body: str) -> str:
    block = f"{BLOCK_START}\n{body.strip()}\n{BLOCK_END}"
    pattern = re.compile(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), re.DOTALL)
    if pattern.search(original):
        updated = pattern.sub(block, original)
    else:
        prefix = original
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        updated = prefix + ("\n" if prefix else "") + block + "\n"
    return updated.rstrip() + "\n"


def _remove_managed_block(original: str) -> str:
    pattern = re.compile(
        r"\n?" + re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n?",
        re.DOTALL,
    )
    return pattern.sub("\n" if original.strip() else "", original).strip("\n") + (
        "\n" if pattern.search(original) and pattern.sub("", original).strip() else ""
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        return _sha256_file(path)
    if not path.exists():
        return ""
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _source_revision(source: Path) -> str:
    digest = hashlib.sha256()
    roots = [
        source / "agentcam",
        source / "slime-coding" / "bin",
        source / "templates" / "DISCIPLINE.md",
        source / "corridor-ci" / "examples" / "workflow.yml",
        source / "installer",
    ]
    for root in roots:
        children = [root] if root.is_file() else sorted(root.rglob("*"))
        for child in children:
            if not child.is_file() or "__pycache__" in child.parts:
                continue
            digest.update(child.relative_to(source).as_posix().encode())
            digest.update(b"\0")
            digest.update(child.read_bytes())
    return digest.hexdigest()[:16]


def _validate_source(source: Path) -> None:
    required = [
        "agentcam/pyproject.toml",
        "slime-coding/bin/patch-cost",
        "templates/DISCIPLINE.md",
        "corridor-ci/examples/workflow.yml",
        "installer/guardrails_installer.py",
    ]
    for relative in required:
        if not (source / relative).is_file():
            raise InstallerError(f"required installer source is missing: {source / relative}")


def validate_managed_destinations(root: Path) -> None:
    """Refuse writes that would traverse a user-controlled symbolic link."""
    root = root.absolute()
    relatives = set(MANAGED_RELATIVE_PATHS)
    for relative in relatives:
        candidate = root
        for part in Path(relative).parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise InstallerError(f"managed destination traverses a symbolic link: {candidate}")


def _python_in_env(env_dir: Path) -> Path:
    return env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _validate_python(python: Path) -> None:
    result = _run(
        [python, "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"],
        check=False,
    )
    if result.returncode:
        raise InstallerError("Python 3.11 or newer is required")


def _copy_runtime(source: Path, destination: Path) -> None:
    (destination / "slime-coding").mkdir(parents=True)
    shutil.copytree(source / "slime-coding" / "bin", destination / "slime-coding" / "bin")
    shutil.copytree(
        source / "installer",
        destination / "installer",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (destination / "templates").mkdir()
    shutil.copy2(source / "templates" / "DISCIPLINE.md", destination / "templates" / "DISCIPLINE.md")
    (destination / "corridor-ci").mkdir()
    shutil.copy2(
        source / "corridor-ci" / "examples" / "workflow.yml",
        destination / "corridor-ci" / "workflow.yml",
    )


@dataclass(frozen=True)
class PreparedVersion:
    revision: str
    runtime: Path
    env: Path
    python: Path
    created_runtime: bool
    created_env: bool


def _prepare_version(repo: Repository, source: Path, python: Path) -> PreparedVersion:
    revision = _source_revision(source)
    guardrails = repo.git_dir / "guardrails"
    runtime = guardrails / "runtime" / revision
    env = guardrails / "envs" / revision
    staging = guardrails / "staging" / uuid.uuid4().hex
    created_runtime = False
    created_env = False
    staging.mkdir(parents=True, exist_ok=False)
    try:
        if not runtime.exists():
            staged_runtime = staging / "runtime"
            _copy_runtime(source, staged_runtime)
            runtime.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_runtime, runtime)
            created_runtime = True
        if not env.exists():
            env.parent.mkdir(parents=True, exist_ok=True)
            _run([python, "-m", "venv", env])
            created_env = True
            env_python = _python_in_env(env)
            _run([env_python, "-m", "pip", "install", "--quiet", "--upgrade", source / "agentcam"])
        env_python = _python_in_env(env)
        version = _run([env_python, "-m", "agentcam.cli", "version"]).stdout.strip()
        if version != "agentcam 0.6.0":
            raise InstallerError(f"installed Agentcam version mismatch: {version}")
        return PreparedVersion(revision, runtime, env, env_python, created_runtime, created_env)
    except Exception:
        if created_env:
            shutil.rmtree(env, ignore_errors=True)
        if created_runtime:
            shutil.rmtree(runtime, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        try:
            staging.parent.rmdir()
        except OSError:
            pass


def _quote_posix(argv: Iterable[Path | str]) -> str:
    return shlex.join(str(value) for value in argv)


def _quote_windows(argv: Iterable[Path | str]) -> str:
    return subprocess.list2cmdline([str(value) for value in argv])


def _hook(command: Sequence[Path | str], managed_id: str, status: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": "command",
        "command": _quote_posix(command),
        "commandWindows": _quote_windows(command),
        "guardrails_managed": managed_id,
    }
    if status:
        item["statusMessage"] = status
    return item


def _managed_hooks(prepared: PreparedVersion, *, codex: bool) -> dict[str, list[dict[str, Any]]]:
    patch = [prepared.python, prepared.runtime / "slime-coding" / "bin" / "patch-cost"]
    pre_matcher = "Edit|Write|apply_patch" if codex else "Edit|Write"
    managed: dict[str, list[dict[str, Any]]] = {
        "UserPromptSubmit": [{"hooks": [_hook(patch, "guardrails-coordinator", "Starting Guardrails turn")]}],
        "PreToolUse": [{"matcher": pre_matcher, "hooks": [_hook(patch, "guardrails-coordinator", "Checking intended edit")]}],
        "PostToolUse": [{"matcher": "Bash", "hooks": [_hook(patch, "guardrails-coordinator", "Checking shell delta")]}],
        "Stop": [{"hooks": [_hook(patch, "guardrails-coordinator", "Finishing Guardrails review")]}],
        "SessionEnd": [{"hooks": [_hook(patch, "guardrails-coordinator", "Cleaning Guardrails state")]}],
    }
    return managed


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallerError(f"existing JSON is invalid and was preserved: {path}: {error}") from error
    if not isinstance(value, dict):
        raise InstallerError(f"existing JSON root must be an object: {path}")
    return value


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _official_workflow_action(path: Path, template: Path) -> str:
    if not path.exists():
        return "create"
    text = path.read_text(encoding="utf-8-sig")
    marker = "# coding-agent-guardrails:managed corridor-ci-v"
    existing_hash = _sha256_bytes(text.replace("\r\n", "\n").encode())
    current_hash = _sha256_bytes(
        template.read_text(encoding="utf-8").replace("\r\n", "\n").encode()
    )
    if text.startswith(marker) and existing_hash in {
        *OFFICIAL_WORKFLOW_HASHES,
        current_hash,
    }:
        return "upgrade"
    return "preserve"


def _launcher_text(python: Path, installer_script: Path, repo: Path) -> tuple[str, str]:
    posix = (
        "#!/usr/bin/env sh\nGUARDRAILS_REPO="
        + shlex.quote(str(repo))
        + " exec "
        + _quote_posix([python, installer_script])
        + ' "$@"\n'
    )
    windows = (
        "@set \"GUARDRAILS_REPO="
        + str(repo)
        + "\" && "
        + _quote_windows([python, installer_script])
        + " %* & exit /b\r\n"
    )
    return posix, windows


def _record(files: dict[str, Any], repo: Path, relative: str, kind: str) -> None:
    path = repo / relative
    files[relative] = {"kind": kind, "sha256": _tree_hash(path)}


def merge_owned_versions(previous: dict[str, Any], current: dict[str, str]) -> list[dict[str, str]]:
    """Carry forward only well-formed version paths that an install recorded."""
    versions: list[dict[str, str]] = []
    candidates = previous.get("owned_versions", []) if isinstance(previous, dict) else []
    if not candidates and isinstance(previous, dict) and previous.get("revision"):
        candidates = [previous]
    for candidate in [*candidates, current]:
        if not isinstance(candidate, dict):
            continue
        item = {
            key: str(candidate.get(key, ""))
            for key in ("revision", "runtime", "environment")
        }
        if not all(item.values()) or item in versions:
            continue
        versions.append(item)
    return versions


def install_project(
    project: Path,
    *,
    source: Path,
    python: Path,
    dry_run: bool = False,
) -> int:
    repo = discover_repository(project)
    source = source.resolve()
    python = python.resolve()
    _validate_python(python)
    _validate_source(source)
    validate_managed_destinations(repo.root)
    if (repo.git_dir / "guardrails").is_symlink():
        raise InstallerError(
            f"guardrails state directory must not be a symbolic link: {repo.git_dir / 'guardrails'}"
        )
    revision = _source_revision(source)
    if dry_run:
        print(f"DRY RUN: install revision {revision} into {repo.root}")
        print(f"  runtime: {repo.git_dir / 'guardrails' / 'runtime' / revision}")
        print(f"  environment: {repo.git_dir / 'guardrails' / 'envs' / revision}")
        print("  update AGENTS.md and CLAUDE.md managed blocks")
        print("  merge Claude Code and Codex hooks without removing user hooks")
        print("  install repo-local launchers; existing .slime state is preserved but archived")
        workflow = repo.root / ".github" / "workflows" / "corridor.yml"
        action = _official_workflow_action(
            workflow,
            source / "corridor-ci" / "examples" / "workflow.yml",
        )
        if action == "preserve":
            print(f"  custom workflow preserved: {workflow}")
        else:
            print(f"  {action} managed Corridor workflow: {workflow}")
        return 0

    prepared = _prepare_version(repo, source, python)
    guardrails = repo.git_dir / "guardrails"
    manifest_path = guardrails / "install.json"
    discipline = (prepared.runtime / "templates" / "DISCIPLINE.md").read_text(encoding="utf-8")
    workflow_template = prepared.runtime / "corridor-ci" / "workflow.yml"
    files: dict[str, Any] = {}
    previous_manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and loaded.get("schema") == SCHEMA:
                previous_manifest = loaded
        except (OSError, json.JSONDecodeError):
            pass
    try:
        with FileTransaction(repo.root) as transaction:
            for relative in ("AGENTS.md", "CLAUDE.md"):
                path = repo.root / relative
                original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
                transaction.write_text(path, _managed_block(original, discipline))
                _record(files, repo.root, relative, "managed-block")

            for relative, codex in ((".codex/hooks.json", True), (".claude/settings.json", False)):
                path = repo.root / relative
                merged = merge_hooks(_read_json(path), _managed_hooks(prepared, codex=codex))
                transaction.write_text(path, _json_text(merged))
                _record(files, repo.root, relative, "hooks")

            workflow = repo.root / ".github" / "workflows" / "corridor.yml"
            action = _official_workflow_action(workflow, workflow_template)
            if action in {"create", "upgrade"}:
                transaction.write_bytes(workflow, workflow_template.read_bytes())
                _record(files, repo.root, ".github/workflows/corridor.yml", "managed-file")
            else:
                print(f"warning: custom workflow preserved: {workflow}")

            launcher, launcher_cmd = _launcher_text(
                python,
                prepared.runtime / "installer" / "guardrails_installer.py",
                repo.root,
            )
            transaction.write_text(repo.root / "guardrails", launcher)
            try:
                (repo.root / "guardrails").chmod(0o755)
            except OSError:
                pass
            transaction.write_bytes(repo.root / "guardrails.cmd", launcher_cmd.encode())
            _record(files, repo.root, "guardrails", "managed-file")
            _record(files, repo.root, "guardrails.cmd", "managed-file")

            manifest = {
                "schema": SCHEMA,
                "revision": prepared.revision,
                "runtime": str(prepared.runtime),
                "environment": str(prepared.env),
                "python": str(prepared.python),
                "installer_python": str(python),
                "agentcam_version": "0.6.0",
                "files": files,
            }
            manifest["owned_versions"] = merge_owned_versions(
                previous_manifest,
                {
                    "revision": prepared.revision,
                    "runtime": str(prepared.runtime),
                    "environment": str(prepared.env),
                },
            )
            transaction.write_text(manifest_path, _json_text(manifest))
            transaction.commit()
    except Exception:
        if prepared.created_env:
            shutil.rmtree(prepared.env, ignore_errors=True)
        if prepared.created_runtime:
            shutil.rmtree(prepared.runtime, ignore_errors=True)
        raise
    ensure_detected_primary(repo)
    print(f"Done. Installed guardrails revision {prepared.revision} into {repo.root}")
    return 0


def _load_manifest(repo: Repository) -> tuple[Path, dict[str, Any]]:
    guardrails = repo.git_dir / "guardrails"
    if guardrails.is_symlink():
        raise InstallerError(f"guardrails state directory must not be a symbolic link: {guardrails}")
    path = guardrails / "install.json"
    if not path.is_file():
        raise InstallerError(f"guardrails is not installed in this repository: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InstallerError(f"install manifest is malformed: {path}: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise InstallerError(f"unsupported install manifest: {path}")
    return path, manifest


def remote_context_problem(contexts: set[str]) -> str | None:
    if "Corridor" not in contexts:
        return "remote active rulesets do not require the Corridor check"
    return None


def _remote_required_contexts(repo: Repository) -> set[str]:
    gh = shutil.which("gh")
    if not gh:
        raise InstallerError("gh is required for guardrails doctor --remote")
    identity = _run(
        [gh, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        cwd=repo.root,
    ).stdout.strip()
    if not re.fullmatch(r"[^/]+/[^/]+", identity):
        raise InstallerError("could not resolve the GitHub repository for --remote")
    try:
        summaries = json.loads(_run([gh, "api", f"repos/{identity}/rulesets"], cwd=repo.root).stdout)
    except json.JSONDecodeError as error:
        raise InstallerError(f"GitHub ruleset response was malformed: {error}") from error
    contexts: set[str] = set()
    for summary in summaries:
        if not isinstance(summary, dict) or summary.get("enforcement") != "active":
            continue
        ruleset_id = summary.get("id")
        try:
            detail = json.loads(
                _run([gh, "api", f"repos/{identity}/rulesets/{ruleset_id}"], cwd=repo.root).stdout
            )
        except json.JSONDecodeError as error:
            raise InstallerError(f"GitHub ruleset response was malformed: {error}") from error
        for rule in detail.get("rules", []):
            if rule.get("type") != "required_status_checks":
                continue
            for check in rule.get("parameters", {}).get("required_status_checks", []):
                context = check.get("context")
                if isinstance(context, str):
                    contexts.add(context)
    return contexts


def doctor(project: Path, *, remote: bool = False) -> int:
    repo = discover_repository(project)
    _, manifest = _load_manifest(repo)
    failures: list[str] = []
    runtime = Path(str(manifest.get("runtime", "")))
    python = Path(str(manifest.get("python", "")))
    if not runtime.is_dir():
        failures.append(f"runtime missing: {runtime}")
    if not python.is_file():
        failures.append(f"versioned Python missing: {python}")
    else:
        result = _run([python, "-m", "agentcam.cli", "version"], check=False)
        expected = f"agentcam {manifest.get('agentcam_version')}"
        if result.returncode or result.stdout.strip() != expected:
            failures.append(f"Agentcam version mismatch: expected {expected!r}")
    for relative in (".codex/hooks.json", ".claude/settings.json"):
        path = repo.root / relative
        try:
            hooks = _read_json(path)
        except InstallerError as error:
            failures.append(str(error))
            continue
        commands = " ".join(
            str(hook.get(key, ""))
            for groups in hooks.get("hooks", {}).values()
            if isinstance(groups, list)
            for group in groups
            if isinstance(group, dict)
            for hook in group.get("hooks", [])
            if isinstance(hook, dict)
            for key in ("command", "commandWindows")
            if _managed_hook(hook)
        )
        if str(runtime) not in commands or str(python) not in commands:
            failures.append(f"managed hook targets are stale or missing: {path}")
    check_mode = "structural-only"
    config = repo.git_dir / "guardrails" / "config.json"
    if config.exists():
        try:
            value = json.loads(config.read_text(encoding="utf-8"))
            if value.get("schema") != 1 or not isinstance(value.get("checks"), dict):
                raise ValueError("expected schema 1 and checks object")
            primary = value["checks"].get("primary")
            if isinstance(primary, dict):
                check_mode = "detected" if primary.get("source") == "detected" else "configured"
        except (OSError, ValueError, json.JSONDecodeError) as error:
            failures.append(f"trusted check config is invalid: {config}: {error}")
    workflow = repo.root / ".github" / "workflows" / "corridor.yml"
    if workflow.exists():
        text = workflow.read_text(encoding="utf-8-sig")
        if not re.search(r"(?m)^\s{4}name: Corridor\s*$", text) or "corridor-ci@corridor-ci-v14.0.0" not in text:
            failures.append(f"Corridor workflow has unexpected check name or version: {workflow}")
    if remote:
        try:
            problem = remote_context_problem(_remote_required_contexts(repo))
            if problem:
                failures.append(problem)
        except InstallerError as error:
            failures.append(str(error))
    if failures:
        print("guardrails doctor: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    archived = "; archived .slime state present" if (repo.root / ".slime").exists() else ""
    print(
        f"guardrails doctor: OK ({manifest['revision']}; checks: {check_mode}{archived})"
    )
    return 0


def _safe_owned_path(path: Path, guardrails: Path) -> bool:
    try:
        path.resolve().relative_to(guardrails.resolve())
    except ValueError:
        return False
    return True


def _safe_manifest_relative(relative: Any) -> bool:
    if not isinstance(relative, str) or not relative:
        return False
    normalized = relative.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute() or path.drive or ".." in path.parts:
        return False
    return normalized in MANAGED_RELATIVE_PATHS


def uninstall(project: Path, *, dry_run: bool = False, purge_state: bool = False) -> int:
    repo = discover_repository(project)
    manifest_path, manifest = _load_manifest(repo)
    guardrails = repo.git_dir / "guardrails"
    actions: list[str] = []
    warnings: list[str] = []
    files = manifest.get("files", {})
    deferred_windows_launcher: Path | None = None

    def plan(message: str) -> None:
        actions.append(message)

    safe_files: list[tuple[str, dict[str, Any]]] = []
    if not isinstance(files, dict):
        warnings.append("malformed files map ignored")
        files = {}
    for relative, record in files.items():
        if not _safe_manifest_relative(relative) or not isinstance(record, dict):
            warnings.append(f"unsafe manifest path preserved: {relative}")
            continue
        safe_files.append((relative, record))

    for relative, record in safe_files:
        path = repo.root / relative
        kind = record.get("kind")
        if kind in {"managed-block", "hooks"}:
            plan(f"remove managed content from {relative}")
        elif path.exists() and _tree_hash(path) == record.get("sha256"):
            plan(f"remove {relative}")
        elif path.exists():
            warnings.append(f"modified managed path preserved: {relative}")
    owned_versions = merge_owned_versions(manifest, {})
    for version in owned_versions:
        plan(f"remove runtime revision {version.get('revision')}")
    if purge_state:
        plan("purge .slime and trusted guardrails state")
    if dry_run:
        print("DRY RUN: uninstall")
        for action in actions:
            print(f"  {action}")
        for warning in warnings:
            print(f"warning: {warning}")
        return 0

    with FileTransaction(repo.root) as transaction:
        for relative, record in safe_files:
            path = repo.root / relative
            kind = record.get("kind")
            if kind == "managed-block" and path.exists():
                updated = _remove_managed_block(path.read_text(encoding="utf-8-sig"))
                if updated:
                    transaction.write_text(path, updated)
                else:
                    transaction.remove(path)
            elif kind == "hooks" and path.exists():
                updated = _remove_managed_hooks(_read_json(path))
                transaction.write_text(path, _json_text(updated))
            elif path.exists() and _tree_hash(path) == record.get("sha256"):
                if os.name == "nt" and relative == "guardrails.cmd":
                    deferred_windows_launcher = path
                else:
                    transaction.remove(path)
        transaction.remove(manifest_path)
        if purge_state:
            transaction.remove(repo.root / ".slime")
        transaction.commit()
    for version in owned_versions:
        for key in ("runtime", "environment"):
            path = Path(version[key])
            if _safe_owned_path(path, guardrails):
                _remove(path)
    if purge_state:
        shutil.rmtree(guardrails, ignore_errors=True)
    if deferred_windows_launcher is not None:
        cleanup = (
            "import pathlib,time; time.sleep(1); "
            f"pathlib.Path({str(deferred_windows_launcher)!r}).unlink(missing_ok=True)"
        )
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            [str(manifest.get("installer_python") or sys.executable), "-c", cleanup],
            creationflags=flags,
            close_fds=True,
        )
    for warning in warnings:
        print(f"warning: {warning}")
    print("Done. Guardrails managed content was uninstalled.")
    return 0


def detect_primary_check(project: Path) -> list[str] | None:
    """Return one unambiguous root test command; never guess for monorepos."""
    candidates: list[list[str]] = []
    if (project / "pytest.ini").is_file():
        candidates.append(["python", "-m", "pytest", "-q"])
    elif (project / "tox.ini").is_file():
        try:
            if "[pytest]" in (project / "tox.ini").read_text(encoding="utf-8"):
                candidates.append(["python", "-m", "pytest", "-q"])
        except OSError:
            pass
    elif (project / "pyproject.toml").is_file():
        try:
            if "[tool.pytest" in (project / "pyproject.toml").read_text(encoding="utf-8"):
                candidates.append(["python", "-m", "pytest", "-q"])
        except OSError:
            pass

    package = project / "package.json"
    if package.is_file():
        try:
            value = json.loads(package.read_text(encoding="utf-8"))
            script = value.get("scripts", {}).get("test") if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            script = None
        placeholder = "no test specified" in str(script or "").lower()
        if isinstance(script, str) and script.strip() and not placeholder:
            candidates.append(["npm", "test"])

    if (project / "Cargo.toml").is_file():
        candidates.append(["cargo", "test"])
    if (project / "go.mod").is_file():
        candidates.append(["go", "test", "./..."])
    pubspec = project / "pubspec.yaml"
    if pubspec.is_file():
        try:
            flutter = "sdk: flutter" in pubspec.read_text(encoding="utf-8")
        except OSError:
            flutter = False
        if flutter:
            candidates.append(["flutter", "test"])
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    return candidate if shutil.which(candidate[0]) else None


def ensure_detected_primary(repo: Repository) -> None:
    path = repo.git_dir / "guardrails" / "config.json"
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        checks = value.get("checks") if isinstance(value, dict) else None
        if isinstance(checks, dict) and "primary" in checks:
            return
    candidate = detect_primary_check(repo.root)
    if candidate:
        set_check(repo.root, "primary", candidate, DEFAULT_TIMEOUT)
        value = json.loads(path.read_text(encoding="utf-8"))
        value["checks"]["primary"]["source"] = "detected"
        _atomic_write(path, _json_text(value).encode())


def remove_check(project: Path, check_id: str) -> int:
    if not CHECK_ID.fullmatch(check_id):
        raise InstallerError("check ID must match [a-z0-9_-]{1,64}")
    repo = discover_repository(project)
    path = repo.git_dir / "guardrails" / "config.json"
    if not path.is_file():
        print(f"trusted check {check_id!r} was not configured")
        return 0
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InstallerError(f"trusted check config is malformed: {path}: {error}") from error
    checks = config.get("checks") if isinstance(config, dict) else None
    if config.get("schema") != 1 or not isinstance(checks, dict):
        raise InstallerError(f"trusted check config must use schema 1: {path}")
    checks.pop(check_id, None)
    _atomic_write(path, _json_text(config).encode())
    print(f"trusted check {check_id!r} removed from {path}")
    return 0


def run_runtime_action(project: Path, argv: Sequence[str], *, interactive: bool = False) -> int:
    repo = discover_repository(project)
    _, manifest = _load_manifest(repo)
    python = Path(str(manifest.get("python") or ""))
    runtime = Path(str(manifest.get("runtime") or "")) / "slime-coding" / "bin" / "patch-cost"
    if not python.is_file() or not runtime.is_file():
        raise InstallerError("installed Guardrails runtime is incomplete; run guardrails doctor")
    command = [str(python), str(runtime), *argv, "--repo", str(repo.root)]
    if interactive:
        return subprocess.run(command).returncode
    result = subprocess.run(command, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode:
        raise InstallerError((result.stderr or result.stdout).strip() or "runtime action failed")
    return 0


def set_check(project: Path, check_id: str, argv: Sequence[str], timeout: int) -> int:
    if not CHECK_ID.fullmatch(check_id):
        raise InstallerError("check ID must match [a-z0-9_-]{1,64}")
    if not argv or any(not isinstance(value, str) or not value for value in argv):
        raise InstallerError("check argv must be a non-empty string array")
    if timeout < 1 or timeout > 3600:
        raise InstallerError("check timeout must be between 1 and 3600 seconds")
    repo = discover_repository(project)
    path = repo.git_dir / "guardrails" / "config.json"
    config: dict[str, Any] = {"schema": 1, "checks": {}}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InstallerError(f"trusted check config is malformed: {path}: {error}") from error
        if loaded.get("schema") != 1 or not isinstance(loaded.get("checks"), dict):
            raise InstallerError(f"trusted check config must use schema 1: {path}")
        config = loaded
    config["checks"][check_id] = {"argv": list(argv), "timeout_seconds": timeout}
    _atomic_write(path, _json_text(config).encode())
    print(f"trusted check {check_id!r} updated in {path}")
    return 0


def _default_python() -> Path:
    return Path(sys.executable).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="guardrails")
    commands = parser.add_subparsers(dest="command", required=True)
    default_repo = os.environ.get("GUARDRAILS_REPO", ".")
    install_parser = commands.add_parser("install")
    install_parser.add_argument("project", nargs="?", default=default_repo)
    install_parser.add_argument("--source", required=True)
    install_parser.add_argument("--python", default=str(_default_python()))
    install_parser.add_argument("--dry-run", action="store_true")
    doctor_parser = commands.add_parser("doctor")
    doctor_parser.add_argument("project", nargs="?", default=default_repo)
    doctor_parser.add_argument("--remote", action="store_true")
    uninstall_parser = commands.add_parser("uninstall")
    uninstall_parser.add_argument("project", nargs="?", default=default_repo)
    uninstall_parser.add_argument("--dry-run", action="store_true")
    uninstall_parser.add_argument("--purge-state", action="store_true")
    check_parser = commands.add_parser("check")
    check_commands = check_parser.add_subparsers(dest="check_command", required=True)
    set_parser = check_commands.add_parser("set")
    set_parser.add_argument("check_id")
    set_parser.add_argument("--repo", default=default_repo)
    set_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    remove_parser = check_commands.add_parser("remove")
    remove_parser.add_argument("check_id")
    remove_parser.add_argument("--repo", default=default_repo)
    internal = commands.add_parser("internal")
    internal_commands = internal.add_subparsers(dest="internal_command", required=True)
    internal_scope = internal_commands.add_parser("scope")
    internal_scope_commands = internal_scope.add_subparsers(dest="scope_command", required=True)
    internal_set = internal_scope_commands.add_parser("set")
    internal_set.add_argument("--outcome", required=True)
    internal_set.add_argument("--path", action="append", required=True)
    internal_set.add_argument("--repo", default=default_repo)
    internal_add = internal_scope_commands.add_parser("add")
    internal_add.add_argument("--path", action="append", required=True)
    internal_add.add_argument("--reason", required=True)
    internal_add.add_argument("--repo", default=default_repo)
    internal_sync = internal_commands.add_parser("pr-sync")
    internal_sync.add_argument("--repo", default=default_repo)
    approve_parser = commands.add_parser("approve")
    approve_parser.add_argument("nonce")
    approve_parser.add_argument("--repo", default=default_repo)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    check_argv: list[str] | None = None
    if raw[:2] == ["check", "set"]:
        if "--" not in raw:
            raise InstallerError("guardrails check set requires '--' before the command argv")
        boundary = raw.index("--")
        check_argv = raw[boundary + 1 :]
        raw = raw[:boundary]
    args = build_parser().parse_args(raw)
    if args.command == "install":
        return install_project(
            Path(args.project),
            source=Path(args.source),
            python=Path(args.python),
            dry_run=args.dry_run,
        )
    if args.command == "doctor":
        return doctor(Path(args.project), remote=args.remote)
    if args.command == "uninstall":
        return uninstall(Path(args.project), dry_run=args.dry_run, purge_state=args.purge_state)
    if args.command == "approve":
        return run_runtime_action(Path(args.repo), ["approve", args.nonce], interactive=True)
    if args.command == "internal":
        if args.internal_command == "pr-sync":
            return run_runtime_action(Path(args.repo), ["pr-sync"])
        values = ["scope", args.scope_command]
        if args.scope_command == "set":
            values += ["--outcome", args.outcome]
        else:
            values += ["--reason", args.reason]
        for path in args.path:
            values += ["--path", path]
        return run_runtime_action(Path(args.repo), values)
    if args.check_command == "set":
        return set_check(Path(args.repo), args.check_id, check_argv or [], args.timeout)
    return remove_check(Path(args.repo), args.check_id)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstallerError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
