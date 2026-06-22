import argparse
import json
import shutil
from pathlib import Path

from bench.score import load_tasks
from bench.tasks import select_task_ids


def prepare_run(task_id, variant, output_dir="bench/runs", force=False):
    repo_root = Path.cwd()
    tasks = load_tasks(repo_root / "bench" / "tasks.json")
    if task_id not in tasks:
        raise ValueError(f"Unknown task id: {task_id}")

    if variant not in {"baseline", "disciplined"}:
        raise ValueError("variant must be baseline or disciplined")

    task = tasks[task_id]
    fixture_dir = repo_root / task["fixture"]
    run_dir = repo_root / output_dir / variant / task_id
    work_dir = run_dir / "work"

    if run_dir.exists():
        if not force:
            raise FileExistsError(f"{run_dir} already exists; use --force to replace it")
        shutil.rmtree(run_dir)

    run_dir.mkdir(parents=True)
    shutil.copytree(fixture_dir, work_dir)

    prompt = build_prompt(task, variant, repo_root)
    (run_dir / "PROMPT.md").write_text(prompt, encoding="utf-8")
    (run_dir / "RUN.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "variant": variant,
                "work_dir": str(work_dir),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def prepare_runs(task_ids, variant, output_dir="bench/runs", force=False):
    return [
        prepare_run(task_id, variant, output_dir=output_dir, force=force)
        for task_id in task_ids
    ]


def build_prompt(task, variant, repo_root):
    template = (repo_root / "bench" / "prompts" / f"{variant}.md").read_text(
        encoding="utf-8"
    )
    agent_md = (repo_root / "AGENT.md").read_text(encoding="utf-8")
    variant_prompt = template.replace("{{AGENT_MD}}", agent_md.strip())

    return "\n".join(
        [
            variant_prompt.strip(),
            "",
            "# Task",
            task["prompt"],
            "",
            "# Verification",
            f"Run `{task['test_command']}` from the task workspace.",
            "",
        ]
    )


def main():
    parser = argparse.ArgumentParser(description="Prepare an isolated benchmark run.")
    parser.add_argument("task_id", nargs="?", help="Task id from bench/tasks.json.")
    parser.add_argument("variant", choices=["baseline", "disciplined"])
    parser.add_argument("--suite", help="Prepare every task in this suite.")
    parser.add_argument("--output-dir", default="bench/runs")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.suite:
        tasks = load_tasks(Path.cwd() / "bench" / "tasks.json")
        task_ids = select_task_ids(tasks, suite=args.suite)
        for run_dir in prepare_runs(
            task_ids,
            args.variant,
            output_dir=args.output_dir,
            force=args.force,
        ):
            print(run_dir)
    elif args.task_id:
        run_dir = prepare_run(
            args.task_id,
            args.variant,
            output_dir=args.output_dir,
            force=args.force,
        )
        print(run_dir)
    else:
        parser.error("task_id or --suite is required")


if __name__ == "__main__":
    main()
