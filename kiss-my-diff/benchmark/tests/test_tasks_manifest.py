import json
from pathlib import Path


def test_tasks_have_public_and_hidden_tests():
    lab = Path(__file__).resolve().parents[1]
    tasks = json.loads((lab / "tasks.json").read_text(encoding="utf-8"))["tasks"]

    assert len(tasks) >= 6
    for task in tasks:
        task_dir = lab / "tasks" / task["id"]
        assert (task_dir / "base").is_dir(), task["id"]
        assert (task_dir / "hidden").is_dir(), task["id"]
        assert list((task_dir / "hidden").rglob("test_*.py")), task["id"]
        assert "pytest" in task["public_command"], task["id"]
        assert "pytest" in task["hidden_command"], task["id"]
        assert task["max_files"] >= 1, task["id"]
        assert task["max_line_delta"] >= 1, task["id"]


def test_tasks_cover_error_and_invalid_state_discipline():
    lab = Path(__file__).resolve().parents[1]
    tasks = json.loads((lab / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    disciplines = {task.get("discipline") for task in tasks}

    assert "fail_fast" in disciplines
    assert "invalid_state" in disciplines
