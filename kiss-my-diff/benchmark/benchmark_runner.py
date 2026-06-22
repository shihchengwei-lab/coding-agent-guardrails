import argparse
import contextlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import benchmark_core as core


MODELS = [
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex-spark",
]
VARIANTS = ["baseline", "kiss", "kiss_one_line"]
KISS_ONE_LINE_AGENT = "Follow the KISS principle (Keep It Simple, Stupid).\n"


def load_tasks(lab_dir: Path) -> list[dict]:
    return json.loads((lab_dir / "tasks.json").read_text(encoding="utf-8"))["tasks"]


def prepare_run(
    task: dict,
    lab_dir: Path,
    run_root: Path,
    model: str,
    variant: str,
    force: bool,
) -> Path:
    run_dir = run_root / model / variant / task["id"]
    work_dir = run_dir / "work"
    if run_dir.exists():
        if not force:
            raise FileExistsError(f"{run_dir} exists")
        shutil.rmtree(run_dir)

    run_dir.mkdir(parents=True)
    shutil.copytree(
        lab_dir / "tasks" / task["id"] / "base",
        work_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    if variant == "kiss":
        shutil.copy2(agent_file(lab_dir), work_dir / "AGENT.md")
    elif variant == "kiss_one_line":
        (work_dir / "AGENT.md").write_text(KISS_ONE_LINE_AGENT, encoding="utf-8")

    (run_dir / "PROMPT.md").write_text(_build_prompt(task, variant), encoding="utf-8")
    (run_dir / "RUN.json").write_text(
        json.dumps(
            {
                "task_id": task["id"],
                "model": model,
                "variant": variant,
                "work_dir": str(work_dir),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def run_agent(run_dir: Path, model: str, timeout_seconds: int = 600) -> None:
    prompt = (run_dir / "PROMPT.md").read_text(encoding="utf-8")
    output_file = run_dir / "AGENT_OUTPUT.md"
    completed = subprocess.run(
        codex_command()
        + [
            "exec",
            "-m",
            model,
            "-C",
            str(run_dir / "work"),
            "-s",
            "workspace-write",
            "--skip-git-repo-check",
            "--ignore-rules",
            "--ephemeral",
            "-o",
            str(output_file),
            prompt,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    (run_dir / "codex_stdout.txt").write_text(completed.stdout or "", encoding="utf-8")
    (run_dir / "codex_stderr.txt").write_text(completed.stderr or "", encoding="utf-8")
    (run_dir / "codex_returncode.txt").write_text(str(completed.returncode), encoding="utf-8")


def codex_command() -> list[str]:
    for name in ("codex.cmd", "codex.exe", "codex"):
        path = shutil.which(name)
        if path:
            return [path]
    return ["codex"]


def agent_file(lab_dir: Path) -> Path:
    local = lab_dir / "AGENT.md"
    if local.exists():
        return local
    return lab_dir.parent / "AGENT.md"


def collect_result(task: dict, lab_dir: Path, run_dir: Path, timeout_seconds: int = 60) -> dict:
    base_dir = lab_dir / "tasks" / task["id"] / "base"
    work_dir = run_dir / "work"
    stats = core.diff_stats(base_dir, work_dir, ignored_paths={"AGENT.md"})
    dep_incidents = core.dependency_incidents(base_dir, work_dir, stats.changed_files)
    with verification_tree(task, lab_dir, work_dir, include_hidden=False) as verify_dir:
        public = _run_command(task["public_command"], verify_dir, timeout_seconds)
    with verification_tree(task, lab_dir, work_dir, include_hidden=True) as verify_dir:
        hidden = _run_command(task["hidden_command"], verify_dir, timeout_seconds)
    quality_hits, quality_total = _quality_score(task, work_dir)
    raw = core.RawResult(
        public_passed=public.returncode == 0,
        hidden_passed=hidden.returncode == 0,
        changed_files=stats.changed_files,
        line_delta=stats.line_delta,
        dependency_incidents=dep_incidents,
        quality_hits=quality_hits,
        quality_total=quality_total,
    )
    score = core.score_result(raw, task["max_files"], task["max_line_delta"])
    result = {
        "task_id": task["id"],
        "model": json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))["model"],
        "variant": json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))["variant"],
        "public_passed": raw.public_passed,
        "hidden_passed": raw.hidden_passed,
        "changed_files": raw.changed_files,
        "line_delta": raw.line_delta,
        "dependency_incidents": raw.dependency_incidents,
        "quality_hits": raw.quality_hits,
        "quality_total": raw.quality_total,
        "capability": score.capability,
        "discipline": score.discipline,
        "total": score.total,
        "public_stdout": public.stdout,
        "public_stderr": public.stderr,
        "hidden_stdout": hidden.stdout,
        "hidden_stderr": hidden.stderr,
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def find_results(run_root: Path) -> list[dict]:
    rows = []
    for path in sorted(run_root.rglob("result.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def write_summary(rows: list[dict], output: Path) -> None:
    summary = _summarize(rows)
    lines = [
        "| model | variant | runs | capability | discipline | total |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        lines.append(
            "| {model} | {variant} | {runs} | {capability:.2f} | {discipline:.2f} | {total:.2f} |".format(
                **row
            )
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_prompt(task: dict, variant: str) -> str:
    lines = [
        "You are a coding agent. Complete the task using the files in this workspace.",
    ]
    if variant != "baseline":
        lines.append("Follow the local AGENT.md while making the change.")
    lines.extend(
        [
            "",
            "Task:",
            task["prompt"],
            "",
            "Verification:",
            f"Run `{task['public_command']}` from this workspace.",
            "",
            "Keep the final answer concise.",
        ]
    )
    return "\n".join(lines)


def _quality_score(task: dict, work_dir: Path) -> tuple[int, int]:
    checks = task.get("quality_checks", [])
    hits = 0
    for check in checks:
        content = (work_dir / check["file"]).read_text(encoding="utf-8")
        value = check["value"]
        if check["type"] == "contains" and value in content:
            hits += 1
        elif check["type"] == "not_contains" and value not in content:
            hits += 1
        elif check["type"] == "regex" and __import__("re").search(value, content, __import__("re").MULTILINE):
            hits += 1
    return hits, len(checks)


@contextlib.contextmanager
def verification_tree(task: dict, lab_dir: Path, work_dir: Path, include_hidden: bool):
    with tempfile.TemporaryDirectory(prefix=f"kiss-bench-{task['id']}-") as temp_name:
        verify_dir = Path(temp_name) / "verify"
        shutil.copytree(
            work_dir,
            verify_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        tests_dir = verify_dir / "tests"
        if tests_dir.exists():
            shutil.rmtree(tests_dir)
        base_tests = lab_dir / "tasks" / task["id"] / "base" / "tests"
        if base_tests.exists():
            shutil.copytree(base_tests, tests_dir)
        if include_hidden:
            hidden_dir = lab_dir / "tasks" / task["id"] / "hidden"
            for path in hidden_dir.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(hidden_dir)
                    target = verify_dir / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
        yield verify_dir


def _run_command(command: str, cwd: Path, timeout_seconds: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def _summarize(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        grouped.setdefault((row["model"], row["variant"]), []).append(row)
    summary = []
    for (model, variant), group in sorted(grouped.items()):
        summary.append(
            {
                "model": model,
                "variant": variant,
                "runs": len(group),
                "capability": _average(group, "capability"),
                "discipline": _average(group, "discipline"),
                "total": _average(group, "total"),
            }
        )
    return summary


def _average(rows: list[dict], key: str) -> float:
    return round(sum(row[key] for row in rows) / len(rows), 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the kiss-my-diff benchmark lab.")
    parser.add_argument("command", choices=["prepare", "run", "collect", "summary"])
    parser.add_argument("--lab-dir", default=".")
    parser.add_argument("--run-root", default="runs")
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--variant", choices=VARIANTS)
    parser.add_argument("--task")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    lab_dir = Path(args.lab_dir).resolve()
    run_root = (lab_dir / args.run_root).resolve()
    tasks = load_tasks(lab_dir)
    selected = [task for task in tasks if args.task in {None, task["id"]}]

    if args.command == "prepare":
        for task in selected:
            for model in ([args.model] if args.model else MODELS):
                for variant in ([args.variant] if args.variant else VARIANTS):
                    print(prepare_run(task, lab_dir, run_root, model, variant, args.force))
    elif args.command == "run":
        for task in selected:
            if not args.model or not args.variant:
                raise SystemExit("--model and --variant are required for run")
            run_dir = run_root / args.model / args.variant / task["id"]
            run_agent(run_dir, args.model)
    elif args.command == "collect":
        for task in selected:
            for model in ([args.model] if args.model else MODELS):
                for variant in ([args.variant] if args.variant else VARIANTS):
                    run_dir = run_root / model / variant / task["id"]
                    print(json.dumps(collect_result(task, lab_dir, run_dir), indent=2))
    elif args.command == "summary":
        output = run_root / "summary.md"
        write_summary(find_results(run_root), output)
        print(output)


if __name__ == "__main__":
    main()
