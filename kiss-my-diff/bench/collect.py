import argparse
import difflib
import json
import re
import subprocess
from pathlib import Path

from bench.score import load_tasks


DEPENDENCY_FILE_NAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
}


def diff_stats(fixture_dir, work_dir):
    fixture_dir = Path(fixture_dir)
    work_dir = Path(work_dir)
    changed_files = []
    line_delta = 0

    all_files = sorted(_relative_files(fixture_dir) | _relative_files(work_dir))
    for relative_path in all_files:
        before_path = fixture_dir / relative_path
        after_path = work_dir / relative_path
        before = _read_lines(before_path)
        after = _read_lines(after_path)
        if before == after:
            continue

        changed_files.append(relative_path.as_posix())
        line_delta += _patch_line_delta(before, after)

    return {
        "changed_files": changed_files,
        "line_delta": line_delta,
    }


def dependency_files_changed(changed_files):
    return sorted(
        path
        for path in changed_files
        if Path(path).name in DEPENDENCY_FILE_NAMES
    )


def detect_new_dependencies(fixture_dir, work_dir):
    fixture_dir = Path(fixture_dir)
    work_dir = Path(work_dir)

    before = _dependency_names(fixture_dir)
    after = _dependency_names(work_dir)
    return sorted(after - before)


def collect_result(run_dir, tasks_path="bench/tasks.json", timeout=30):
    run_dir = Path(run_dir)
    run_meta = json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))
    tasks = load_tasks(tasks_path)
    task = tasks[run_meta["task_id"]]

    fixture_dir = Path(task["fixture"])
    work_dir = run_dir / "work"
    stats = diff_stats(fixture_dir, work_dir)
    dependency_changes = dependency_files_changed(stats["changed_files"])
    test_result = _run_test_command(task["test_command"], work_dir, timeout)

    result = {
        "task_id": task["id"],
        "variant": run_meta["variant"],
        "tests_passed": test_result["returncode"] == 0,
        "test_command": task["test_command"],
        "test_returncode": test_result["returncode"],
        "test_stdout": test_result["stdout"],
        "test_stderr": test_result["stderr"],
        "changed_files": stats["changed_files"],
        "line_delta": stats["line_delta"],
        "dependency_files_changed": dependency_changes,
        "new_dependencies": detect_new_dependencies(fixture_dir, work_dir),
        "files": collect_files(work_dir, stats["changed_files"], task.get("quality_checks", [])),
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def _relative_files(root):
    root = Path(root)
    if not root.exists():
        return set()

    paths = set()
    for path in root.rglob("*"):
        if not path.is_file() or _should_ignore(path):
            continue
        paths.add(path.relative_to(root))
    return paths


def collect_files(work_dir, changed_files, quality_checks):
    paths = set(changed_files)
    paths.update(check["file"] for check in quality_checks)

    files = {}
    for relative_path in sorted(paths):
        path = Path(work_dir) / relative_path
        if path.exists() and path.is_file():
            files[relative_path] = path.read_text(encoding="utf-8")
    return files


def _should_ignore(path):
    parts = set(path.parts)
    return "__pycache__" in parts or path.suffix in {".pyc", ".pyo"}


def _read_lines(path):
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _patch_line_delta(before, after):
    delta = 0
    for line in difflib.ndiff(before, after):
        if line.startswith("- ") or line.startswith("+ "):
            delta += 1
    return delta


def _dependency_names(root):
    names = set()
    names.update(_requirements_names(root / "requirements.txt"))
    names.update(_package_json_names(root / "package.json"))
    names.update(_pyproject_names(root / "pyproject.toml"))
    return names


def _requirements_names(path):
    if not path.exists():
        return set()

    names = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~\[]", line, maxsplit=1)[0].strip()
        if name:
            names.add(name.lower())
    return names


def _package_json_names(path):
    if not path.exists():
        return set()

    data = json.loads(path.read_text(encoding="utf-8"))
    names = set()
    for section in ["dependencies", "devDependencies", "peerDependencies"]:
        names.update(data.get(section, {}).keys())
    return names


def _pyproject_names(path):
    if not path.exists():
        return set()

    import tomllib

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    names = set()
    project = data.get("project", {})
    for dependency in project.get("dependencies", []):
        name = re.split(r"[<>=!~\[]", dependency, maxsplit=1)[0].strip()
        if name:
            names.add(name.lower())
    return names


def _run_test_command(command, cwd, timeout):
    completed = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main():
    parser = argparse.ArgumentParser(description="Collect a benchmark run result.")
    parser.add_argument("run_dir", help="Run directory produced by bench.prepare.")
    parser.add_argument("--tasks", default="bench/tasks.json", help="Path to benchmark tasks JSON.")
    parser.add_argument("--timeout", type=int, default=30, help="Test timeout in seconds.")
    args = parser.parse_args()

    result = collect_result(args.run_dir, tasks_path=args.tasks, timeout=args.timeout)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
