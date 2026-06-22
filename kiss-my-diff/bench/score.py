import argparse
import json
import re
from pathlib import Path


DEFAULT_WEIGHTS = {
    "tests": 0.50,
    "scope": 0.15,
    "simplicity": 0.15,
    "dependencies": 0.10,
    "quality": 0.10,
}


def load_tasks(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {task["id"]: task for task in data["tasks"]}


def load_results(paths):
    results = []
    for path in paths:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
        results.append(result)
    return results


def score_result(task, result):
    weights = task.get("weights", DEFAULT_WEIGHTS)
    scores = {
        "tests": 100.0 if result.get("tests_passed") else 0.0,
        "scope": _scope_score(task, result),
        "simplicity": _simplicity_score(task, result),
        "dependencies": _dependency_score(result),
        "quality": _quality_score(task, result),
    }
    total = sum(scores[name] * weights[name] for name in weights)

    return {
        "task_id": result["task_id"],
        "variant": result["variant"],
        **scores,
        "total": round(total, 2),
    }


def summarize_results(scored_results):
    grouped = {}
    for result in scored_results:
        grouped.setdefault(result["variant"], []).append(result)

    summary = {}
    for variant, rows in grouped.items():
        summary[variant] = {"runs": len(rows)}
        for metric in ["total", "tests", "scope", "simplicity", "dependencies", "quality"]:
            avg = sum(row.get(metric, 0.0) for row in rows) / len(rows)
            summary[variant][f"{metric}_avg"] = round(avg, 2)
    return summary


def format_markdown(scored_results, summary):
    lines = [
        "| variant | task | total | tests | scope | simplicity | dependencies | quality |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(scored_results, key=lambda item: (item["variant"], item["task_id"])):
        lines.append(
            "| {variant} | {task_id} | {total:.2f} | {tests:.2f} | {scope:.2f} | "
            "{simplicity:.2f} | {dependencies:.2f} | {quality:.2f} |".format(**row)
        )

    lines.extend(
        [
            "",
            "| variant | runs | total avg | tests avg | scope avg | simplicity avg | dependencies avg | quality avg |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for variant, row in sorted(summary.items()):
        lines.append(
            "| {variant} | {runs} | {total_avg:.2f} | {tests_avg:.2f} | {scope_avg:.2f} | "
            "{simplicity_avg:.2f} | {dependencies_avg:.2f} | {quality_avg:.2f} |".format(
                variant=variant, **row
            )
        )
    return "\n".join(lines)


def _scope_score(task, result):
    changed_files = result.get("changed_files", [])
    if not changed_files:
        return 0.0

    allowed = set(task.get("allowed_files", []))
    allowed_count = sum(1 for path in changed_files if path in allowed)
    allowed_ratio = allowed_count / len(changed_files)

    max_changed_files = task.get("max_changed_files", len(changed_files))
    count_score = min(1.0, max_changed_files / len(changed_files))

    return round(allowed_ratio * count_score * 100, 2)


def _simplicity_score(task, result):
    max_line_delta = task.get("max_line_delta", 0)
    line_delta = abs(result.get("line_delta", 0))
    if max_line_delta <= 0:
        return 100.0 if line_delta == 0 else 0.0
    if line_delta <= max_line_delta:
        return 100.0

    overage = line_delta - max_line_delta
    score = max(0.0, 1.0 - (overage / max_line_delta)) * 100
    return round(score, 2)


def _dependency_score(result):
    dependency_files_changed = result.get("dependency_files_changed", [])
    new_dependencies = result.get("new_dependencies", [])
    return 0.0 if dependency_files_changed or new_dependencies else 100.0


def _quality_score(task, result):
    checks = task.get("quality_checks", [])
    if not checks:
        return 100.0

    files = result.get("files", {})
    passed = 0
    for check in checks:
        content = files.get(check["file"], "")
        if _quality_check_passed(check, content):
            passed += 1
    return round((passed / len(checks)) * 100, 2)


def _quality_check_passed(check, content):
    check_type = check["type"]
    value = check["value"]
    if check_type == "required_substring":
        return value in content
    if check_type == "forbidden_substring":
        return value not in content
    if check_type == "required_regex":
        return re.search(value, content, re.MULTILINE) is not None
    if check_type == "forbidden_regex":
        return re.search(value, content, re.MULTILINE) is None
    raise ValueError(f"Unknown quality check type: {check_type}")


def main():
    parser = argparse.ArgumentParser(description="Score agent benchmark result JSON files.")
    parser.add_argument("results", nargs="+", help="Path(s) to result.json files.")
    parser.add_argument("--tasks", default="bench/tasks.json", help="Path to benchmark tasks JSON.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    tasks = load_tasks(args.tasks)
    scored = []
    for result in load_results(args.results):
        scored.append(score_result(tasks[result["task_id"]], result))

    summary = summarize_results(scored)
    if args.format == "json":
        print(json.dumps({"results": scored, "summary": summary}, indent=2))
    else:
        print(format_markdown(scored, summary))


if __name__ == "__main__":
    main()
