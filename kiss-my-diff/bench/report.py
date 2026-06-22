import argparse
import json
from pathlib import Path

from bench.score import load_tasks, score_result


def result_context(path):
    parts = Path(path).parts
    for index in range(len(parts) - 4):
        if parts[index] == "bench" and parts[index + 1].startswith("runs"):
            return {
                "model": parts[index + 2],
                "variant": parts[index + 3],
                "task_id": parts[index + 4],
            }
    raise ValueError(f"Result path is outside bench/runs* layout: {path}")


def load_scored_rows(result_paths, tasks_path="bench/tasks.json"):
    tasks = load_tasks(tasks_path)
    rows = []
    for result_path in result_paths:
        path = Path(result_path)
        result = json.loads(path.read_text(encoding="utf-8"))
        context = result_context(path)
        scored = score_result(tasks[result["task_id"]], result)
        rows.append(
            {
                **context,
                **scored,
                "line_delta": result.get("line_delta", 0),
                "dependency_incidents": len(result.get("dependency_files_changed", []))
                + len(result.get("new_dependencies", [])),
            }
        )
    return rows


def summarize_by_model_variant(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault((row["model"], row["variant"]), []).append(row)

    summary = []
    for (model, variant), group in grouped.items():
        summary.append(
            {
                "model": model,
                "variant": variant,
                "runs": len(group),
                "total_avg": _average(group, "total"),
                "pass_rate": _average(group, "tests"),
                "quality_avg": _average(group, "quality"),
                "avg_line_delta": _average(group, "line_delta"),
                "dependency_incidents": sum(row["dependency_incidents"] for row in group),
            }
        )
    return sorted(summary, key=lambda row: (row["model"], row["variant"]))


def filter_rows_by_suite(rows, tasks, suite):
    if suite is None:
        return rows
    return [row for row in rows if tasks[row["task_id"]].get("suite") == suite]


def format_summary_markdown(summary):
    lines = [
        "| model | variant | runs | total avg | pass rate | quality avg | avg line delta | dependency incidents |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        lines.append(
            "| {model} | {variant} | {runs} | {total_avg:.2f} | {pass_rate:.2f} | "
            "{quality_avg:.2f} | {avg_line_delta:.2f} | {dependency_incidents} |".format(**row)
        )
    return "\n".join(lines)


def find_result_paths(root="bench/runs"):
    return sorted(Path(root).rglob("result.json"))


def _average(rows, key):
    return round(sum(row[key] for row in rows) / len(rows), 2)


def main():
    parser = argparse.ArgumentParser(description="Summarize benchmark results by model and variant.")
    parser.add_argument("results", nargs="*", help="Optional result.json paths.")
    parser.add_argument("--tasks", default="bench/tasks.json", help="Path to benchmark tasks JSON.")
    parser.add_argument("--runs", default="bench/runs", help="Runs directory used when no results are passed.")
    parser.add_argument("--suite", help="Only summarize tasks in this suite.")
    args = parser.parse_args()

    result_paths = args.results or find_result_paths(args.runs)
    rows = load_scored_rows(result_paths, tasks_path=args.tasks)
    rows = filter_rows_by_suite(rows, load_tasks(args.tasks), args.suite)
    print(format_summary_markdown(summarize_by_model_variant(rows)))


if __name__ == "__main__":
    main()
